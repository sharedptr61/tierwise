import os
import shutil
import unittest
from unittest import mock

from helpers import RepoTest
from mlib import checks as C
from mlib.common import default_config, snapshot

CFG = default_config()
HAS_NODE = bool(shutil.which("node"))
try:
    import tomllib  # noqa: F401
    HAS_TOMLLIB = True
except ImportError:
    HAS_TOMLLIB = False


def ids(cfg, files, tier="R1"):
    return [c["id"] for c in C.select(cfg, files, tier)]


class SelectOrder(unittest.TestCase):
    def test_syntax_first_for_code_and_config(self):
        self.assertEqual(ids(CFG, ["app/core.py"]), ["syntax", "secrets", "unit"])
        self.assertEqual(ids(CFG, ["tests/test_x.py"])[0], "syntax")
        self.assertEqual(ids(CFG, ["package.json"], "R2")[0], "syntax")
        self.assertEqual(ids(CFG, ["conf/app.toml"])[0], "syntax")

    def test_no_syntax_for_docs_only(self):
        self.assertEqual(ids(CFG, ["README.md"], "R0"), ["secrets", "docs"])

    def test_syntax_and_secrets_are_builtin_whatever_config_says(self):
        cfg = {"checks": {"secrets": "gitleaks protect --staged", "syntax": "true"}}
        cmds = {c["id"]: c["cmd"] for c in C.select(cfg, ["a.py"], "R1")}
        self.assertEqual(cmds["syntax"], "builtin:syntax")
        self.assertEqual(cmds["secrets"], "builtin:secrets")

    def test_affected_only_when_configured_and_just_before_unit(self):
        self.assertNotIn("affected", ids(CFG, ["app/core.py"]))
        cfg = {"checks": {"affected": "pytest --picked"}}
        self.assertEqual(ids(cfg, ["app/core.py"]), ["syntax", "secrets", "affected", "unit"])
        self.assertNotIn("affected", ids(cfg, ["README.md"], "R0"))
        cmds = {c["id"]: c["cmd"] for c in C.select(cfg, ["app/core.py"], "R1")}
        self.assertEqual(cmds["affected"], "pytest --picked")

    def test_detect_never_configures_gitleaks(self):
        with mock.patch("shutil.which", return_value="/usr/bin/x"), self.subTest("all tools on PATH"):
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                self.assertNotIn("secrets", C.detect(d))


class SyntaxCheck(RepoTest):
    def test_python_good_and_bad(self):
        self.write("ok.py", "x = 1\n")
        self.write("bad.py", "def f(:\n    pass\n")
        broken, checked = C.syntax_check(self.root, ["ok.py", "bad.py"])
        self.assertEqual(checked, 2)
        self.assertEqual(len(broken), 1)
        self.assertTrue(broken[0].startswith("bad.py:1: "), broken)

    def test_python_line_number_and_no_pycache(self):
        self.write("pkg/m.py", "a = 1\nb = 2\nif a:\nc = 3\n")
        broken, _ = C.syntax_check(self.root, ["pkg/m.py"])
        self.assertTrue(broken[0].startswith("pkg/m.py:4: "), broken)
        for dirpath, dirs, _ in os.walk(self.root):
            self.assertNotIn("__pycache__", dirs)

    def test_json(self):
        self.write("a.json", '{"a": 1}')
        self.write("b.json", '{\n"a": 1,\n}')
        broken, checked = C.syntax_check(self.root, ["a.json", "b.json"])
        self.assertEqual(checked, 2)
        self.assertEqual(len(broken), 1)
        # Python 3.13 reports a trailing comma on its own line (2); older versions on the closing brace (3).
        self.assertRegex(broken[0], r"^b\.json:[23]: ", broken)

    def test_jsonc_config_is_not_judged(self):
        self.write("tsconfig.json", '{\n // comment\n "a": 1}')
        self.assertEqual(C.syntax_check(self.root, ["tsconfig.json"]), ([], 0))

    @unittest.skipUnless(HAS_TOMLLIB, "tomllib needs Python 3.11+")
    def test_toml(self):
        self.write("ok.toml", 'a = 1\n')
        self.write("bad.toml", 'a = 1\nb = = 2\n')
        broken, _ = C.syntax_check(self.root, ["ok.toml", "bad.toml"])
        self.assertEqual(len(broken), 1)
        self.assertTrue(broken[0].startswith("bad.toml:2: "), broken)

    def test_toml_skipped_without_tomllib(self):
        self.write("bad.toml", 'b = = 2\n')
        with mock.patch.dict("sys.modules", {"tomllib": None}):
            self.assertEqual(C.syntax_check(self.root, ["bad.toml"]), ([], 0))

    @unittest.skipUnless(HAS_NODE, "node not installed")
    def test_javascript(self):
        self.write("ok.js", "const a = 1;\n")
        self.write("bad.mjs", "const a = ;\n")
        self.write("bad.cjs", "\nfunction (\n")
        broken, checked = C.syntax_check(self.root, ["ok.js", "bad.mjs", "bad.cjs"])
        self.assertEqual(checked, 3)
        self.assertEqual(sorted(b.split(":")[0] for b in broken), ["bad.cjs", "bad.mjs"])
        self.assertTrue(any(b.startswith("bad.mjs:1: ") for b in broken), broken)
        self.assertTrue(any(b.startswith("bad.cjs:2: ") for b in broken), broken)

    def test_javascript_skipped_without_node(self):
        self.write("bad.js", "const a = ;\n")
        with mock.patch("mlib.checks.shutil.which", return_value=None):
            self.assertEqual(C.syntax_check(self.root, ["bad.js"]), ([], 0))

    @unittest.skipUnless(HAS_NODE, "node not installed")
    def test_jsx_in_a_js_file_is_not_a_syntax_error(self):
        self.write("src/App.js", "const App = () => <div>Hello</div>;\n")
        self.write("src/bad.js", "const = ;\n")
        self.write("src/App.mjs", "const App = () => <div>Hello</div>;\n")
        broken, checked = C.syntax_check(self.root, ["src/App.js", "src/bad.js", "src/App.mjs"])
        self.assertEqual(sorted(b.split(":")[0] for b in broken), ["src/App.mjs", "src/bad.js"])
        self.assertEqual(checked, 2)

    def test_devcontainer_json_may_have_comments(self):
        self.write(".devcontainer/devcontainer.json", '{\n // comment\n "name": "x"\n}\n')
        self.write("devcontainer.json", '{\n // comment\n "name": "x"\n}\n')
        self.write(".devcontainer.json", '{\n // comment\n "name": "x"\n}\n')
        files = [".devcontainer/devcontainer.json", "devcontainer.json", ".devcontainer.json"]
        self.assertEqual(C.syntax_check(self.root, files), ([], 0))

    def test_exclude_globs_skip_files(self):
        self.write("tests/fixtures/invalid.json", "{nope")
        self.write("src/bad.py", "def (\n")
        files = ["tests/fixtures/invalid.json", "src/bad.py"]
        self.assertEqual(len(C.syntax_check(self.root, files)[0]), 2)
        cfg = {"syntax": {"exclude": ["tests/fixtures/**"]}}
        broken, checked = C.syntax_check(self.root, files, cfg)
        self.assertEqual([b.split(":")[0] for b in broken], ["src/bad.py"])
        self.assertEqual(checked, 1)
        self.assertEqual(C.syntax_check(self.root, files, {"syntax": {"exclude": ["**"]}}), ([], 0))
        for bad in ({"syntax": None}, {"syntax": {"exclude": "src/**"}}, {"syntax": {"exclude": [3, None]}}):
            self.assertEqual(len(C.syntax_check(self.root, files, bad)[0]), 2)

    def test_run_selected_applies_syntax_exclude(self):
        base, _ = snapshot(self.root)
        self.write("gen/bad.py", "def (\n")
        sel = [{"id": "syntax", "cmd": "builtin:syntax", "reason": "r"}]
        res, _ = C.run_selected(self.root, sel, base, ["gen/bad.py"], cfg={"syntax": {"exclude": ["gen/**"]}})
        self.assertEqual(res[0]["status"], "pass")

    def test_missing_deleted_large_and_other_files_skipped(self):
        self.write("big.py", "x = (\n" + "#" * 2_000_000)
        self.write("notes.txt", "def f(:\n")
        self.assertEqual(C.syntax_check(self.root, ["gone.py", "big.py", "notes.txt"]), ([], 0))

    def test_run_selected_syntax_pass_and_fail(self):
        base, _ = snapshot(self.root)
        self.write("good.py", "x = 1\n")
        sel = [{"id": "syntax", "cmd": "builtin:syntax", "reason": "r"}]
        res, _ = C.run_selected(self.root, sel, base, ["good.py"])
        self.assertEqual(res[0]["status"], "pass")
        self.write("bad.py", "def (\n")
        res, _ = C.run_selected(self.root, sel, base, ["good.py", "bad.py"])
        self.assertEqual(res[0]["status"], "fail")
        self.assertIn("bad.py:1:", res[0]["digest"])
        self.assertNotIn("good.py", res[0]["digest"])
        self.assertIn("FAIL syntax", C.summary(res))


class Secrets(RepoTest):
    def scan(self, cfg=None, files=("app/core.py",), allowed=None):
        base, _ = snapshot(self.root)
        return C.scan_secrets(self.root, base, list(files), cfg, allowed)

    def test_entropy_values(self):
        self.assertEqual(C.entropy(""), 0.0)
        self.assertEqual(C.entropy("aaaa"), 0.0)
        self.assertAlmostEqual(C.entropy("abcd"), 2.0)
        self.assertGreater(C.entropy("q8Zr2LmV9xTe4KpW"), 3.0)

    def test_low_entropy_assigned_value_is_not_a_secret(self):
        self.write("app/core.py", 'password = "abababababab"\napi_key = "aaaaaaaaaaaaaaaa"\n')
        self.assertEqual(self.scan(), [])

    def test_high_entropy_assigned_value_is_a_secret(self):
        self.write("app/core.py", 'api_key = "q8Zr2LmV9xTe4KpW"\n')
        found = self.scan()
        self.assertEqual(len(found), 1)
        self.assertIn("assigned-secret", found[0])

    def test_entropy_filter_applies_only_to_assigned_secret(self):
        self.write("app/core.py", 'KEY = "AKIAAAAAAAAAAAAAAAAA"\n')
        self.assertIn("aws-access-key", self.scan()[0])

    def test_user_rule(self):
        self.write("app/core.py", 'x = "corp_9f8e7d6c5b4a"\ny = "corp_aaaaaaaaaaaa"\n')
        cfg = {"secrets": {"rules": [{"id": "corp-token", "regex": r"corp_[0-9a-z]{12}"}]}}
        self.assertEqual(len(self.scan(cfg)), 2)
        cfg["secrets"]["rules"][0]["minEntropy"] = 3.0
        found = self.scan(cfg)
        self.assertEqual(len(found), 1)
        self.assertIn("corp-token (added line 1)", found[0])

    def test_user_rule_entropy_uses_capture_group(self):
        self.write("app/core.py", 'tok: aaaaaaaaaaaa-q8Zr2LmV9xTe\n')
        cfg = {"secrets": {"rules": [{"id": "t", "regex": r"tok: a+-(\w+)", "minEntropy": 3}]}}
        self.assertEqual(len(self.scan(cfg)), 1)

    def test_bad_user_rule_is_reported(self):
        self.write("app/core.py", "x = 1\n")
        found = self.scan({"secrets": {"rules": [{"id": "broken", "regex": "("}], "allow": {"regexes": ["["]}}})
        self.assertEqual(len(found), 2)
        self.assertTrue(all(f.startswith("secrets config:") for f in found), found)

    def test_bad_min_entropy_is_a_config_error_not_a_crash(self):
        self.write("config.py", 'ACME = "Zx9Qw3Er7Ty1Ui5Op2"\n')
        for bad in ("high", [3], {"a": 1}):
            found = self.scan({"secrets": {"rules": [{"id": "acme", "regex": "ACME", "minEntropy": bad}]}},
                              ("config.py",))
            self.assertEqual(len(found), 1, found)
            self.assertTrue(found[0].startswith("secrets config: bad rule"), found)
        ok = self.scan({"secrets": {"rules": [{"id": "acme", "regex": "ACME", "minEntropy": "1.5"}]}}, ("config.py",))
        self.assertEqual(ok, ["config.py: acme (added line 1)"])

    def test_allow_path_lists_hit_without_failing(self):
        self.write("app/core.py", 'api_key = "q8Zr2LmV9xTe4KpW"\n')
        self.write("fixtures/keys.py", 'KEY = "AKIAABCDEFGHIJKLMNOP"\n')
        cfg = {"secrets": {"allow": {"paths": ["**/fixtures/**"]}}}
        allowed = []
        found = self.scan(cfg, ("app/core.py", "fixtures/keys.py"), allowed)
        self.assertEqual(len(found), 1)
        self.assertIn("app/core.py", found[0])
        self.assertEqual(allowed, ["allowed: fixtures/keys.py: aws-access-key (added line 1)"])

    def test_allow_regex_matches_only_the_matched_text(self):
        # A known fake key is allowlisted by its own text; a comment elsewhere on a line allowlists nothing.
        self.write("app/core.py", 'KEY = "AKIAFAKEFAKEFAKEFAKE"\n'
                                  'OTHER = "AKIAQRSTUVWXYZABCDEF"  # FAKE docs example\n')
        allowed = []
        found = self.scan({"secrets": {"allow": {"regexes": ["FAKE"]}}}, allowed=allowed)
        self.assertEqual(len(found), 1)
        self.assertIn("line 2", found[0])
        self.assertEqual(len(allowed), 1)
        self.assertIn("line 1", allowed[0])

    def test_every_match_on_a_line_is_judged(self):
        # A placeholder first on the line used to hide a real value after it.
        self.write("app/core.py", 'api_key="xxxxxxxxxxxxxxxx"; api_key="q8Zr2LmV9xTe4KpW7bN3"\n')
        self.assertEqual(len(self.scan({})), 1)

    def test_allowlisted_only_when_every_hit_on_the_line_is(self):
        self.write("app/core.py", 'K = ["AKIAFAKEFAKEFAKEFAKE", "AKIAQRSTUVWXYZABCDEF"]\n')
        self.assertEqual(len(self.scan({"secrets": {"allow": {"regexes": ["FAKE"]}}})), 1)

    def test_min_entropy_must_be_a_finite_number(self):
        for bad in ("nan", "inf", -1, "high"):
            cfg = {"secrets": {"rules": [{"id": "acme", "regex": "ACME-[0-9]{8}", "minEntropy": bad}]}}
            self.write("app/core.py", "x = 1\n")
            found = self.scan(cfg)
            self.assertTrue(any("bad rule" in f for f in found), bad)

    def test_run_selected_secrets_allowed_listed_and_passes(self):
        self.config({"secrets": {"allow": {"paths": ["app/**"]}}})
        base, _ = snapshot(self.root)
        self.write("app/core.py", 'KEY = "AKIAABCDEFGHIJKLMNOP"\n')
        sel = [{"id": "secrets", "cmd": "builtin:secrets", "reason": "r"}]
        res, _ = C.run_selected(self.root, sel, base, ["app/core.py"])
        self.assertEqual(res[0]["status"], "pass")
        with open(os.path.join(self.root, res[0]["log"])) as f:
            log = f.read()
        self.assertIn("allowed: app/core.py: aws-access-key", log)

    def test_run_selected_secrets_failure_digest_lists_allowed_too(self):
        base, _ = snapshot(self.root)
        self.write("app/core.py", 'KEY = "AKIAABCDEFGHIJKLMNOP"\n')
        self.write("fx/k.py", 'KEY = "AKIAQRSTUVWXYZABCDEF"\n')
        cfg = {"secrets": {"allow": {"paths": ["fx/**"]}}}
        sel = [{"id": "secrets", "cmd": "builtin:secrets", "reason": "r"}]
        res, _ = C.run_selected(self.root, sel, base, ["app/core.py", "fx/k.py"], cfg=cfg)
        self.assertEqual(res[0]["status"], "fail")
        self.assertIn("app/core.py: aws-access-key", res[0]["digest"])
        self.assertIn("allowed: fx/k.py", res[0]["digest"])


class RunSelected(RepoTest):
    def run_sel(self, sel, files=("app/core.py",)):
        base, _ = snapshot(self.root)
        return C.run_selected(self.root, sel, base, list(files))

    def test_changed_files_env(self):
        sel = [{"id": "unit", "cmd": 'printf %s "$TIERWISE_CHANGED_FILES" > seen.txt', "reason": "r"}]
        res, _ = self.run_sel(sel, ("app/core.py", "docs/a b.md", "x/y.py"))
        self.assertEqual(res[0]["status"], "pass")
        with open(os.path.join(self.root, "seen.txt")) as f:
            self.assertEqual(f.read(), "app/core.py\ndocs/a b.md\nx/y.py")

    def test_env_is_restored_afterwards(self):
        os.environ.pop("TIERWISE_CHANGED_FILES", None)
        self.run_sel([{"id": "unit", "cmd": "true", "reason": "r"}])
        self.assertNotIn("TIERWISE_CHANGED_FILES", os.environ)

    def test_huge_file_list_does_not_break_exec(self):
        files = [f"dir/file_{i:06d}.py" for i in range(20000)]
        res, _ = self.run_sel([{"id": "unit", "cmd": 'test -n "$TIERWISE_CHANGED_FILES"', "reason": "r"}], files)
        self.assertEqual(res[0]["status"], "pass")

    def sel(self, first_status):
        return [{"id": "syntax", "cmd": "builtin:syntax", "reason": "r"},
                {"id": "secrets", "cmd": "builtin:secrets", "reason": "r"},
                {"id": "affected", "cmd": "exit 1" if first_status == "fail" else "true", "reason": "r"},
                {"id": "unit", "cmd": "touch unit-ran", "reason": "tests changed"},
                {"id": "lint", "cmd": None, "reason": "r"},
                {"id": "sast", "cmd": "touch sast-ran", "reason": "r"}]

    def test_a_crashing_check_is_a_failure_not_an_escape(self):
        sel = [{"id": "syntax", "cmd": "builtin:syntax", "reason": "r"},
               {"id": "secrets", "cmd": "builtin:secrets", "reason": "r"}]
        with mock.patch.object(C, "scan_secrets", side_effect=ValueError("boom")):
            res, _ = self.run_sel(sel)
        status = {r["id"]: r["status"] for r in res}
        self.assertEqual(status, {"syntax": "pass", "secrets": "fail"})
        self.assertIn("crashed: ValueError: boom", res[1]["digest"])
        self.assertIn("FAIL secrets", C.summary(res))

    def test_failed_affected_skips_later_non_security_checks(self):
        res, _ = self.run_sel(self.sel("fail"))
        status = {r["id"]: r["status"] for r in res}
        self.assertEqual(status, {"syntax": "pass", "secrets": "pass", "affected": "fail", "unit": "skipped",
                                  "lint": "skipped", "sast": "pass"})
        skipped = next(r for r in res if r["id"] == "unit")
        self.assertEqual(skipped["reason"], "an earlier check failed")
        self.assertFalse(os.path.exists(os.path.join(self.root, "unit-ran")))
        self.assertTrue(os.path.exists(os.path.join(self.root, "sast-ran")))
        text = C.summary(res)
        self.assertIn("SKIPPED unit: an earlier check failed", text)
        self.assertIn("SKIPPED lint", text)
        self.assertNotIn("MISSING", text)

    def test_failed_syntax_skips_everything_but_secrets(self):
        self.write("app/core.py", "def (\n")
        sel = [{"id": "syntax", "cmd": "builtin:syntax", "reason": "r"},
               {"id": "secrets", "cmd": "builtin:secrets", "reason": "r"},
               {"id": "unit", "cmd": "touch unit-ran", "reason": "r"}]
        res, _ = self.run_sel(sel)
        self.assertEqual([r["status"] for r in res], ["fail", "pass", "skipped"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "unit-ran")))

    def test_secrets_runs_even_before_a_failing_check_and_finds_keys(self):
        self.write("app/core.py", 'KEY = "AKIAABCDEFGHIJKLMNOP"\nx = (\n')
        sel = [{"id": "syntax", "cmd": "builtin:syntax", "reason": "r"},
               {"id": "secrets", "cmd": "builtin:secrets", "reason": "r"}]
        res, _ = self.run_sel(sel)
        self.assertEqual([r["status"] for r in res], ["fail", "fail"])

    def test_passing_fast_checks_skip_nothing(self):
        res, _ = self.run_sel(self.sel("pass"))
        self.assertEqual([r["status"] for r in res], ["pass", "pass", "pass", "pass", "missing", "pass"])


if __name__ == "__main__":
    unittest.main()
