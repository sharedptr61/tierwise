#!/usr/bin/env python3
"""Hidden acceptance tests for the research-integration build (workflow 2). Never shown to the building agents.

  python3 evals/workflow-arms/hidden_acceptance.py <plugin dir>     # prints "passed N/M" and the failures

Written from the specification the agents received, using only the names it fixed: check ids "syntax",
"secrets", "affected", status "skipped", TIERWISE_CHANGED_FILES, .tierwise/usage.json {task: {cost, ...}},
caps.taskBudgetUsd, the ledger line "ladder: task <id> rung <old> -> <new>", config secrets.rules / secrets.allow.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

PLUGIN = os.path.abspath(sys.argv.pop(1)) if len(sys.argv) > 1 else os.path.abspath("plugins/tierwise")
sys.path.insert(0, os.path.join(PLUGIN, "bin"))
GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}

from mlib import checks as C  # noqa: E402
from mlib import flow, guard  # noqa: E402
from mlib.common import default_config, load_config, load_state, locked_state  # noqa: E402
from mlib.route import route  # noqa: E402


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.realpath(os.path.join(self.tmp, "repo"))
        os.makedirs(self.root)
        self.env = dict(os.environ)
        os.environ.update(GIT)
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.tmp, "cfg")
        self.git("init", "-q", "-b", "main")
        self.write("app/core.py", "def add(a, b):\n    return a + b\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *a):
        return subprocess.run(["git", "-C", self.root, *a], capture_output=True, text=True, check=True).stdout

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)

    def config(self, cfg):
        self.write(".claude/tierwise.json", json.dumps(cfg))

    def run_sel(self, files, cfg=None):
        cfg = cfg or load_config(self.root)
        sel = C.select(cfg, files, "R1", "feature")
        res, _ = C.run_selected(self.root, sel, self.base, files)
        return sel, {r["id"]: r for r in res}


class SyntaxCheck(Repo):
    def test_selected_first_for_code(self):
        sel = C.select(default_config(), ["app/core.py"], "R1", "feature")
        self.assertEqual(sel[0]["id"], "syntax")

    def test_broken_python_fails_with_location_and_no_pycache(self):
        self.write("app/core.py", "def add(a, b)\n    return a + b\n")
        _, r = self.run_sel(["app/core.py"])
        self.assertEqual(r["syntax"]["status"], "fail")
        self.assertIn("app/core.py:1", r["syntax"]["digest"] + open(os.path.join(self.root, r["syntax"]["log"])).read())
        self.assertFalse(os.path.exists(os.path.join(self.root, "app", "__pycache__")))

    def test_broken_json_fails_valid_files_pass(self):
        self.write("conf/settings.json", "{\"a\": 1,}")
        _, r = self.run_sel(["conf/settings.json"])
        self.assertEqual(r["syntax"]["status"], "fail")
        self.write("conf/settings.json", "{\"a\": 1}")
        _, r = self.run_sel(["conf/settings.json"])
        self.assertEqual(r["syntax"]["status"], "pass")

    def test_broken_js_fails_when_node_is_installed(self):
        if not shutil.which("node"):
            self.skipTest("node not installed")
        self.write("web/app.js", "function f( {\n")
        _, r = self.run_sel(["web/app.js"])
        self.assertEqual(r["syntax"]["status"], "fail")


class Secrets(Repo):
    def test_builtin_scan_always_runs_even_if_gitleaks_configured(self):
        cfg = default_config()
        cfg["checks"]["secrets"] = "gitleaks protect --staged --no-banner --redact"
        sel = {c["id"]: c["cmd"] for c in C.select(cfg, ["app/core.py"], "R1", "feature")}
        self.assertEqual(sel["secrets"], "builtin:secrets")

    def test_detect_no_longer_replaces_the_scan(self):
        self.assertNotIn("gitleaks", json.dumps(C.detect(self.root)))

    def test_entropy_filter(self):
        self.write("app/core.py", 'password = "aaaaaaaaaaaaaaaaaa"\n')
        self.assertEqual(C.scan_secrets(self.root, self.base, ["app/core.py"]), [])
        self.write("app/core.py", 'password = "q8Zr2LmV9xTe4KpW7bN3"\n')
        self.assertEqual(len(C.scan_secrets(self.root, self.base, ["app/core.py"])), 1)

    def test_user_rule_and_allowlist(self):
        self.config({"secrets": {"rules": [{"id": "acme", "regex": "ACME-[0-9]{8}"}], "allow": {"paths": ["fixtures/**"], "regexes": []}}})
        self.write("app/core.py", 'KEY = "ACME-12345678"\n')
        _, r = self.run_sel(["app/core.py"])
        self.assertEqual(r["secrets"]["status"], "fail")
        self.write("app/core.py", "x = 1\n")
        self.write("fixtures/keys.txt", "AKIAABCDEFGHIJKLMNOP\n")
        _, r = self.run_sel(["app/core.py", "fixtures/keys.txt"])
        self.assertEqual(r["secrets"]["status"], "pass")
        with open(os.path.join(self.root, r["secrets"]["log"])) as f:
            self.assertIn("allowed", f.read().lower())


class ChangedFilesAndAffected(Repo):
    def test_changed_files_are_exported(self):
        cfg = load_config(self.root)
        cfg["checks"]["unit"] = 'printf "%s" "$TIERWISE_CHANGED_FILES" > .changed.txt'
        self.write("app/core.py", "x = 2\n")
        self.run_sel(["app/core.py"], cfg)
        with open(os.path.join(self.root, ".changed.txt")) as f:
            self.assertIn("app/core.py", f.read())

    def test_affected_runs_before_unit_and_failure_skips_the_rest(self):
        cfg = load_config(self.root)
        cfg["checks"]["affected"] = "false"
        cfg["checks"]["unit"] = "true"
        self.write("app/core.py", "x = 2\n")
        sel, r = self.run_sel(["app/core.py"], cfg)
        ids = [c["id"] for c in sel]
        self.assertLess(ids.index("affected"), ids.index("unit"))
        self.assertEqual(r["affected"]["status"], "fail")
        self.assertEqual(r["unit"]["status"], "skipped")
        self.assertIn(r["secrets"]["status"], ("pass", "fail"))
        self.assertIn("SKIPPED", C.summary(list(r.values())).upper())


class GateLadder(Repo):
    def start(self, prompt="Add a CSV exporter to app/core.py"):
        r = route(prompt, load_config(self.root))
        flow.record_route(self.root, r, prompt, "test")

    def test_syntax_failure_does_not_climb_the_ladder(self):
        self.config({"checks": {"unit": "true"}})
        self.start()
        self.write("app/core.py", "def add(a, b)\n")
        out = flow.gate(self.root, {"cwd": self.root})
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("Ladder rung", out["reason"])
        self.assertIn("syntax", out["reason"].lower())
        self.assertEqual(load_state(self.root)["task"]["rung"], 0)

    def test_secret_failure_does_not_climb_and_mentions_allowlist(self):
        self.config({"checks": {"unit": "true"}})
        self.start()
        self.write("app/core.py", 'T = "ghp_' + "a1B2" * 9 + '"\n')
        out = flow.gate(self.root, {"cwd": self.root})
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("Ladder rung", out["reason"])
        self.assertIn("allowlist", out["reason"].lower())
        self.assertEqual(load_state(self.root)["task"]["rung"], 0)

    def test_escalation_is_audited_in_the_ledger(self):
        self.config({"checks": {"unit": "false"}})
        self.start()
        self.write("app/core.py", "x = 3\n")
        out = flow.gate(self.root, {"cwd": self.root})
        self.assertIn("Ladder rung 1", out["reason"])
        tid = load_state(self.root)["task"]["id"]
        with open(os.path.join(self.root, ".tierwise", "ledger.md")) as f:
            log = f.read()
        self.assertIn(f"ladder: task {tid} rung 0 -> 1", log)


class TaskBudget(Repo):
    def start(self):
        r = route("Add a CSV exporter to app/core.py", load_config(self.root))
        flow.record_route(self.root, r, "p", "test")
        return load_state(self.root)["task"]["id"]

    def spawn(self, agent):
        out = guard.pre_agent({"cwd": self.root, "permission_mode": "default",
                               "tool_input": {"subagent_type": agent, "prompt": "go", "description": "d"}})
        return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")

    def usage(self, tid, cost):
        self.write(".tierwise/usage.json", json.dumps({tid: {"cost": cost, "tokens": 1, "requests": 1}}))

    def test_template_defaults(self):
        cfg = default_config()
        self.assertEqual(cfg["caps"]["taskBudgetUsd"], 25)
        self.assertIn("affected", cfg["checks"])
        self.assertIn("rules", cfg["secrets"])

    def test_over_budget_stops_escalation_not_verification(self):
        tid = self.start()
        self.usage(tid, 30.0)
        for agent in ("tierwise:planner", "tierwise:principal", "tierwise:debugger"):
            self.assertEqual(self.spawn(agent), "deny", agent)
        for agent in ("tierwise:scout", "tierwise:reviewer", "tierwise:security-reviewer"):
            self.assertNotEqual(self.spawn(agent), "deny", agent)

    def test_under_budget_missing_file_or_cap_off(self):
        tid = self.start()
        self.assertNotEqual(self.spawn("tierwise:planner"), "deny")
        self.usage(tid, 10.0)
        self.assertNotEqual(self.spawn("tierwise:principal"), "deny")
        self.usage(tid, 30.0)
        self.config({"caps": {"taskBudgetUsd": None}})
        self.assertNotEqual(self.spawn("tierwise:debugger"), "deny")


class Docs(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(PLUGIN, rel)) as f:
            return f.read()

    def test_templates(self):
        self.assertIn("Plan unit", self.read("templates/brief.md"))
        self.assertIn("Approach", self.read("templates/brief.md"))
        self.assertIn("one line per attempt", self.read("templates/dossier.md").lower())

    def test_fix_loop_goes_fresh_from_round_three(self):
        text = self.read("skills/execute/SKILL.md").lower()
        self.assertTrue("rounds 3" in text or "round 3" in text or "rounds 3-5" in text or "rounds 3–5" in text, text[:200])

    def test_readme_documents_the_new_controls(self):
        readme = self.read("README.md")
        for term in ("taskBudgetUsd", "TIERWISE_CHANGED_FILES", "syntax", "secrets.allow"):
            self.assertIn(term, readme, term)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=0).result
    total = result.testsRun
    bad = len(result.failures) + len(result.errors)
    print(f"\npassed {total - bad - len(result.skipped)}/{total - len(result.skipped)} (skipped {len(result.skipped)})")
    sys.exit(0 if bad == 0 else 1)
