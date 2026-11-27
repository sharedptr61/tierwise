import json
import os
import unittest

from helpers import RepoTest
from mlib import checks as C
from mlib.common import (changed_files, default_config, deep_merge, ensure_layout, glob_match, load_config,
                         locked_state, load_state, max_effort, max_tier, path_tier, snapshot, week_key)

CFG = default_config()


class Globs(unittest.TestCase):
    def test_double_star_matches_zero_or_more_dirs(self):
        self.assertTrue(glob_match("auth/login.py", "**/auth/**"))
        self.assertTrue(glob_match("src/app/auth/x/y.py", "**/auth/**"))
        self.assertFalse(glob_match("src/author.py", "**/auth/**"))
        self.assertTrue(glob_match(".github/workflows/ci.yml", "**/.github/workflows/**"))
        self.assertTrue(glob_match("./infra/main.tf", "**/*.tf"))

    def test_path_tiers(self):
        self.assertEqual(path_tier("src/billing/charge.py", CFG), "R3")
        self.assertEqual(path_tier("api/routes/users.py", CFG), "R2")
        self.assertEqual(path_tier("package.json", CFG), "R2")
        self.assertEqual(path_tier("docs/guide.md", CFG), "R0")
        self.assertEqual(path_tier("tests/test_core.py", CFG), "R0")
        self.assertEqual(path_tier("app/core.py", CFG), "R1")

    def test_orderings(self):
        self.assertEqual(max_effort("low", None, "xhigh", "medium"), "xhigh")
        self.assertIsNone(max_effort(None, "bogus"))
        self.assertEqual(max_tier("R1", None, "R3"), "R3")

    def test_deep_merge(self):
        self.assertEqual(deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}), {"a": {"b": 1, "c": 3}})

    def test_week_key_format(self):
        self.assertRegex(week_key(), r"^\d{4}-W\d{2}$")


class Repo(RepoTest):
    def test_config_merges_project_file(self):
        self.config({"planner": {"effort": "xhigh"}, "checks": {"unit": "make test"}})
        cfg = load_config(self.root)
        self.assertEqual(cfg["planner"]["effort"], "xhigh")
        self.assertEqual(cfg["planner"]["fallbackModel"], "opus")  # defaults kept
        self.assertEqual(cfg["checks"]["unit"], "make test")

    def test_layout_excludes_tierwise_from_git(self):
        ensure_layout(self.root)
        ensure_layout(self.root)  # idempotent
        with open(os.path.join(self.root, ".git", "info", "exclude")) as f:
            exclude = f.read()
        self.assertEqual(exclude.count(".tierwise/"), 1)
        self.assertNotIn(".tierwise", self.git("status", "--porcelain"))

    def test_changed_files_since_snapshot(self):
        self.write("app/core.py", "def add(a, b):\n    return a - b\n")  # dirty before the task
        base, untracked = snapshot(self.root)
        self.write("scratch.txt", "pre-existing untracked\n")
        base2, untracked2 = snapshot(self.root)
        self.assertEqual(changed_files(self.root, base2, untracked2), [])
        self.write("app/new.py", "x = 1\n")
        self.write("README.md", "# changed\n")
        self.assertEqual(changed_files(self.root, base2, untracked2), ["README.md", "app/new.py"])
        self.write("app/__pycache__/new.cpython-313.pyc", "x")
        self.write(".claude/tierwise.json", "{}")
        self.write(".claude/settings.local.json", "{}")
        self.assertEqual(changed_files(self.root, base2, untracked2), ["README.md", "app/new.py"])

    def test_locked_state_round_trip(self):
        with locked_state(self.root) as s:
            s["task"] = {"id": "t1", "phase": "route"}
        self.assertEqual(load_state(self.root)["task"]["id"], "t1")


class Selection(unittest.TestCase):
    def test_code_change(self):
        ids = [c["id"] for c in C.select(CFG, ["app/core.py"], "R1")]
        self.assertEqual(ids, ["syntax", "secrets", "unit"])

    def test_docs_only(self):
        self.assertEqual([c["id"] for c in C.select(CFG, ["README.md"], "R0")], ["secrets", "docs"])

    def test_r2_manifest_iac_migration(self):
        files = ["api/routes/x.py", "package.json", "Dockerfile", "db/migrations/001.sql"]
        ids = {c["id"] for c in C.select(CFG, files, "R3", "high-risk")}
        self.assertTrue({"secrets", "unit", "sca", "iac", "migration", "sast"} <= ids)

    def test_missing_tools_have_no_command_and_secrets_are_builtin(self):
        sel = {c["id"]: c["cmd"] for c in C.select(CFG, ["api/routes/x.py"], "R2")}
        self.assertIsNone(sel["sast"])
        self.assertEqual(sel["secrets"], "builtin:secrets")

    def test_nothing_changed(self):
        self.assertEqual(C.select(CFG, [], "R1"), [])

    def test_plan_lists_checks(self):
        ids = [c["id"] for c in C.select(CFG, ["README.md"], "R0", extra=["race", "integration"])]
        self.assertIn("race", ids)
        self.assertIn("unit", ids)


class Checks(RepoTest):
    def test_plan_checks_parsed(self):
        self.write(".tierwise/plans/p.md", "### Unit 1\n- **Checks:** unit, sast\n- Checks: race; iac\n")
        self.assertEqual(C.plan_checks(self.root, ".tierwise/plans/p.md"), {"unit", "sast", "race", "iac"})

    def test_secret_scan_flags_real_keys_not_placeholders(self):
        base, _ = snapshot(self.root)
        self.write("app/core.py", 'KEY = "AKIAABCDEFGHIJKLMNOP"\npassword = "changeme-placeholder"\n'
                                  'api_key = "q8Zr2LmV9xTe4KpW"\n')
        found = C.scan_secrets(self.root, base, ["app/core.py"])
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any("aws-access-key" in f for f in found))
        self.assertTrue(any("assigned-secret" in f for f in found))

    def test_run_selected_pass_fail_missing(self):
        base, _ = snapshot(self.root)
        self.write("app/core.py", "x = 1\n")
        sel = [{"id": "unit", "cmd": "echo ok", "reason": "r"},
               {"id": "lint", "cmd": "echo 'E501 line too long'; echo 'error: bad' >&2; exit 3", "reason": "r"},
               {"id": "sast", "cmd": None, "reason": "r"}]
        res, logdir = C.run_selected(self.root, sel, base, ["app/core.py"])
        status = {x["id"]: x["status"] for x in res}
        self.assertEqual(status, {"unit": "pass", "lint": "fail", "sast": "missing"})
        lint = next(x for x in res if x["id"] == "lint")
        self.assertIn("error: bad", lint["digest"])
        self.assertTrue(os.path.exists(os.path.join(self.root, lint["log"])))
        text = C.summary(res)
        self.assertIn("FAIL lint", text)
        self.assertIn("MISSING sast", text)

    def test_detect_python_project(self):
        self.write("tests/test_core.py", "import unittest\n")
        found = C.detect(self.root)
        self.assertIn("unit", found)
        self.assertIn("python3 -m", found["unit"])

    def test_detect_node_project(self):
        self.write("package.json", json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}))
        found = C.detect(self.root)
        self.assertEqual((found["unit"], found["lint"]), ("npm test --silent", "npm run lint"))

    def test_red_green(self):
        self.write("tests/test_core.py",
                   "import sys, unittest\nsys.path.insert(0, '.')\nfrom app.core import add\n"
                   "class T(unittest.TestCase):\n    def test_neg(self):\n        self.assertEqual(add(-1, -1), -2)\n"
                   "    def test_str(self):\n        self.assertEqual(add('a', 1), 'a1')\n")
        cmd = "python3 -m unittest -q tests.test_core"
        res = C.red_green(self.root, cmd, "HEAD", ["tests/test_core.py"])
        self.assertTrue(res["red"])        # base code fails the new test
        self.assertFalse(res["green"])     # not fixed yet
        self.write("app/core.py", "def add(a, b):\n    return f'{a}{b}' if isinstance(a, str) else a + b\n")
        res = C.red_green(self.root, cmd, "HEAD", ["tests/test_core.py"])
        self.assertTrue(res["ok"], res)
        self.assertNotIn("tierwise-redgreen", self.git("worktree", "list"))  # cleaned up

    def test_red_green_rejects_test_that_already_passes(self):
        self.write("tests/test_ok.py", "import unittest\nclass T(unittest.TestCase):\n"
                                       "    def test_ok(self):\n        pass\n")
        res = C.red_green(self.root, "python3 -m unittest -q tests.test_ok", "HEAD", ["tests/test_ok.py"])
        self.assertFalse(res["ok"])
        self.assertFalse(res["red"])


if __name__ == "__main__":
    unittest.main()
