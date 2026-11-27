import json
import os
import time

from helpers import PLUGIN, RepoTest
from mlib import flow
from mlib.common import load_state, mdir
from test_guard_flow import GuardBase

AWS = "AKIAABCDEFGHIJKLMNOP"


class LadderBase(GuardBase):
    def setUp(self):
        super().setUp()
        self.config({"checks": {"unit": "test -f PASS"}})

    def gate(self, **inp):
        return flow.gate(self.root, {"cwd": self.root, **inp})

    def change(self, n, text=None):
        self.write("app/core.py", text or f"def add(a, b):\n    return a * b  # attempt {n}\n")
        t = time.time() + n
        os.utime(os.path.join(self.root, "app/core.py"), (t, t))

    def ledger_text(self):
        with open(mdir(self.root, "ledger.md")) as f:
            return f.read()


class SyntaxAndSecretsOutsideTheLadder(LadderBase):
    def test_syntax_failure_does_not_climb_and_names_the_fix(self):
        self.start(tier="R1")
        for n in (1, 2, 3):
            self.change(n, "def add(a, b:\n    return a\n")
            out = self.gate()
            self.assertEqual(out["decision"], "block")
            self.assertIn("FAIL syntax", out["reason"])
            self.assertIn("Fix the file named", out["reason"])
            self.assertNotIn("Ladder rung", out["reason"])
        t = load_state(self.root)["task"]
        self.assertEqual((t["rung"], t["attempts"]), (0, {}))
        self.assertIsNone(load_state(self.root)["effortFloor"])
        self.assertNotIn("ladder:", self.ledger_text())

    def test_syntax_failure_skips_unit_which_is_not_a_failure(self):
        self.start(tier="R1")
        self.change(1, "def add(a, b:\n    return a\n")
        out = self.gate()
        self.assertIn("SKIPPED unit", out["reason"])
        self.assertEqual(load_state(self.root)["verification"]["failed"], ["syntax"])

    def test_secret_failure_does_not_climb_and_says_how_to_allowlist(self):
        self.start(tier="R1")
        self.write("PASS", "")
        for n in (1, 2):
            self.change(n, f"KEY = '{AWS}'\n")
            out = self.gate()
            self.assertEqual(out["decision"], "block")
            self.assertIn("FAIL secrets", out["reason"])
            self.assertIn("secrets.allow", out["reason"])
            self.assertNotIn("Ladder rung", out["reason"])
        self.assertEqual(load_state(self.root)["task"]["rung"], 0)

    def test_other_failures_keep_the_ladder_alongside(self):
        self.start(tier="R1")
        self.change(1, f"KEY = '{AWS}'\n")  # secrets fail and unit fails (no PASS file)
        out = self.gate()
        self.assertIn("secrets.allow", out["reason"])
        self.assertIn("Ladder rung 1", out["reason"])
        t = load_state(self.root)["task"]
        self.assertEqual((t["rung"], t["attempts"]), (1, {"unit": 1}))

    def test_a_pass_after_syntax_failures_resets_nothing_wrongly(self):
        self.start(tier="R0")
        self.write("PASS", "")
        self.change(1, "def add(a, b:\n")
        self.assertEqual(self.gate()["decision"], "block")
        self.change(2, "def add(a, b):\n    return a\n")
        out = self.gate()
        self.assertNotEqual(out.get("decision"), "block")
        self.assertEqual(load_state(self.root)["verification"]["status"], "pass")


class EscalationAudit(LadderBase):
    def test_each_rise_is_written_to_the_ledger(self):
        self.start(tier="R1")
        task_id = load_state(self.root)["task"]["id"]
        self.change(1)
        self.gate()
        self.change(2)
        self.gate(stop_hook_active=True)
        text = self.ledger_text()
        first = flow.RUNG_ACTION[1].split(". ")[0].rstrip(".")
        second = flow.RUNG_ACTION[2].split(". ")[0].rstrip(".")
        self.assertIn(f"ladder: task {task_id} rung 0 -> 1 on unit: {first}.", text)
        self.assertIn(f"ladder: task {task_id} rung 1 -> 2 on unit: {second}.", text)

    def test_no_line_when_the_rung_does_not_rise(self):
        self.start(tier="R1")
        self.change(1)
        self.gate()
        self.gate(stop_hook_active=True)  # nothing changed: released, no climb
        self.assertEqual(self.ledger_text().count("ladder:"), 1)


class Template(RepoTest):
    def test_template_has_the_new_keys(self):
        with open(os.path.join(PLUGIN, "templates", "tierwise.json")) as f:
            cfg = json.load(f)
        self.assertIn("affected", cfg["checks"])
        self.assertIsNone(cfg["checks"]["affected"])
        self.assertEqual(cfg["secrets"], {"rules": [], "allow": {"paths": [], "regexes": []}})
        self.assertEqual(cfg["caps"]["taskBudgetUsd"], 25)
