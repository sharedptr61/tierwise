"""The scripts as Claude Code runs them: hook JSON on stdin, JSON or text on stdout."""
import json
import os
import unittest

from helpers import RepoTest
from mlib.common import load_state, prompt_hash, locked_state


class ClassifyRiskCli(RepoTest):
    def hook(self, prompt):
        return self.script("classify-risk", "--hook", stdin=json.dumps({"prompt": prompt, "cwd": self.root}))

    def test_fallback_hook_adds_card_and_starts_task(self):
        code, out, err = self.hook("Add a CSV exporter to app/core.py")
        self.assertEqual(code, 0, err)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith("[tierwise] route: feature · R1"))
        self.assertIn("wrote .claude/tierwise.json", ctx)
        st = load_state(self.root)
        self.assertEqual((st["task"]["class"], st["cardBy"]), ("feature", "hook"))

    def test_question_routes_without_task(self):
        code, out, _ = self.hook("Where is add defined?")
        self.assertIn("route: question", out)
        self.assertNotIn("task", load_state(self.root))

    def test_handbacks_and_commands_are_not_routed(self):
        for p in ("<agent-message from=\"a1\">\n[Subagent hand-back] PONG", "<task-notification>x", "/compact"):
            self.assertEqual(self.hook(p)[1], "", p)

    def test_skips_prompt_the_mod_already_routed(self):
        prompt = "Add a CSV exporter to app/core.py"
        os.makedirs(os.path.join(self.root, ".tierwise"))
        with locked_state(self.root) as s:
            s.update(cardBy="mod", cardHash=prompt_hash(prompt), cardAt=__import__("time").time())
        self.assertEqual(self.hook(prompt)[1], "")

    def test_outside_git_the_hook_stays_silent(self):
        code, out, _ = self.script("classify-risk", "--hook", stdin=json.dumps({"prompt": "Add x", "cwd": self.tmp}),
                                   cwd=self.tmp)
        self.assertEqual((code, out), (0, ""))

    def test_mod_mode_defers_recording_when_unclear(self):
        code, out, _ = self.script("classify-risk", "--mod", stdin=json.dumps({"prompt": "Update the reports module for the March changes", "cwd": "."}))
        r = json.loads(out)
        self.assertTrue(r["unclear"] and r["allowModel"])
        self.assertNotIn("recorded", r)
        code, out, _ = self.script("classify-risk", "--mod", "--label", "feature",
                                   stdin=json.dumps({"prompt": "Update the reports module for the March changes", "cwd": "."}))
        r = json.loads(out)
        self.assertEqual((r["class"], r["source"], r["recorded"], r["root"]), ("feature", "model", True, self.root))

    def test_plain_cli_prints_route(self):
        code, out, _ = self.script("classify-risk", "Split the orders table and migrate the data")
        self.assertEqual(json.loads(out)["tier"], "R3")


class OtherClis(RepoTest):
    def test_guard_spawn_cli(self):
        code, out, _ = self.script("guard-spawn", "pre-handback", stdin=json.dumps(
            {"agent_type": "tierwise:scout", "tool_input": {"message": "hi"}}))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.script("guard-spawn", "bogus")[0], 2)
        code, out, _ = self.script("guard-spawn", "pre-agent", stdin="")
        self.assertEqual((code, out), (0, ""))

    def test_gate_cli_blocks_and_run_checks_digest(self):
        self.config({"checks": {"unit": "echo 'AssertionError: 2 != 3'; exit 1"}})
        self.script("classify-risk", "--hook", stdin=json.dumps({"prompt": "Fix the bug in app/core.py",
                                                                "cwd": self.root}))
        self.write("app/core.py", "def add(a, b):\n    return a + b + 1\n")
        code, out, _ = self.script("run-checks", "--gate", stdin=json.dumps({"cwd": self.root}))
        gate = json.loads(out)
        self.assertEqual(gate["decision"], "block")
        self.assertIn("AssertionError: 2 != 3", gate["reason"])
        code, out, _ = self.script("run-checks")
        self.assertEqual(code, 1)
        self.assertIn("FAIL unit", out)
        code, out, _ = self.script("select-checks")
        self.assertEqual([c["id"] for c in json.loads(out)["checks"]], ["syntax", "secrets", "unit"])

    def test_state_cli(self):
        self.assertEqual(self.script("state", "init")[0], 0)
        self.script("state", "set", 'task={"id":"t1","phase":"route","tier":"R1","class":"feature"}')
        self.assertEqual(json.loads(self.script("state", "get", "task.tier")[1]), "R1")
        self.script("state", "ledger", "hello", "ledger")
        self.script("state", "decision", "use CSV · simpler · rejected XLSX · user")
        self.script("state", "record-review", "code")
        code, out, _ = self.script("state", "hook", "session-start", stdin=json.dumps({"cwd": self.root}))
        self.assertIn("Active task t1", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.script("state", "close")
        self.assertEqual(self.script("state", "hook", "session-start", stdin=json.dumps({"cwd": self.root}))[1], "")
        with open(os.path.join(self.root, ".tierwise", "ledger.md")) as f:
            log = f.read()
        self.assertIn("hello ledger", log)
        self.assertIn("task t1 closed", log)
        with open(os.path.join(self.root, ".tierwise", "decisions.md")) as f:
            self.assertIn("rejected XLSX", f.read())

    def test_review_package_has_diff_and_new_files_but_no_reasoning(self):
        self.script("classify-risk", "--hook", stdin=json.dumps({"prompt": "Add a mul helper to app/core.py",
                                                                "cwd": self.root}))
        self.write("app/core.py", "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n")
        self.write("app/extra.py", "Y = 2\n")
        code, out, _ = self.script("review-package")
        with open(os.path.join(self.root, out.strip())) as f:
            pkg = f.read()
        self.assertIn("+def mul(a, b):", pkg)
        self.assertIn("## New file `app/extra.py`", pkg)
        self.assertIn("Task prompt: Add a mul helper", pkg)

    def test_red_green_cli(self):
        self.write("tests/test_core.py", "import sys, unittest\nsys.path.insert(0, '.')\nfrom app.core import add\n"
                                         "class T(unittest.TestCase):\n    def test_s(self):\n"
                                         "        self.assertEqual(add('a', 1), 'a1')\n")
        self.write("app/core.py", "def add(a, b):\n    return f'{a}{b}' if isinstance(a, str) else a + b\n")
        code, out, _ = self.script("red-green", "--cmd", "python3 -m unittest -q tests.test_core",
                                   "--tests", "tests/test_core.py")
        self.assertEqual(code, 0, out)
        self.assertTrue(json.loads(out)["ok"])

    def test_scripts_outside_git(self):
        for name in ("select-checks", "run-checks", "review-package"):
            self.assertEqual(self.script(name, cwd=self.tmp)[0], 2, name)


if __name__ == "__main__":
    unittest.main()
