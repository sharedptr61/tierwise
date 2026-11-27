"""The per-task usage cap: past caps.taskBudgetUsd the guard stops escalation (planner, principal, debugger)
and leaves verification (scouts, analysts, builders, reviewers) running."""
import json
import os
import unittest

from helpers import RepoTest
from mlib import flow, guard
from mlib.common import default_config, load_config, load_state, locked_state
from mlib.route import route

ESCALATING = ["tierwise:planner", "tierwise:principal", "tierwise:debugger"]
VERIFYING = ["tierwise:scout", "tierwise:analyst", "tierwise:builder", "tierwise:reviewer", "tierwise:security-reviewer"]


def decision(out):
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")


def reason(out):
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


class Budget(RepoTest):
    def setUp(self):
        super().setUp()
        prompt = "Add a CSV exporter to app/core.py"
        flow.record_route(self.root, route(prompt, load_config(self.root)), prompt, "test")
        self.task_id = load_state(self.root)["task"]["id"]

    def usage(self, entries):
        self.write(".tierwise/usage.json", json.dumps(entries))

    def spend(self, cost, task_id=None):
        self.usage({task_id or self.task_id: {"cost": cost, "tokens": 1000, "requests": 3}})

    def spawn(self, subagent, permission_mode="default"):
        return guard.pre_agent({"cwd": self.root, "tool_name": "Agent", "permission_mode": permission_mode,
                                "tool_input": {"subagent_type": subagent, "prompt": "go", "description": "d"}})

    def test_default_cap_is_read_from_the_template(self):
        self.assertEqual(default_config()["caps"]["taskBudgetUsd"], 25)
        self.assertEqual(load_config(self.root)["caps"]["taskBudgetUsd"], 25)

    def test_escalation_denied_at_and_past_the_cap(self):
        for cost in (25, 31.5):
            self.spend(cost)
            for agent in ESCALATING:
                out = self.spawn(agent)
                self.assertEqual(decision(out), "deny", (agent, cost))
                text = reason(out)
                self.assertIn(f"${cost:.2f} of its $25.00", text)
                self.assertIn("list-price equivalent", text)
                self.assertIn("on a subscription this is usage of your limits, not a bill", text)
                self.assertIn("ask the user", text)
                self.assertIn("caps.taskBudgetUsd", text)

    def test_escalation_allowed_below_the_cap(self):
        self.spend(24.99)
        for agent in ESCALATING:
            self.assertNotEqual(decision(self.spawn(agent)), "deny", agent)

    def test_verification_stays_allowed_past_the_cap(self):
        self.spend(100)
        for agent in VERIFYING:
            self.assertNotEqual(decision(self.spawn(agent)), "deny", agent)

    def test_denied_spawn_is_not_counted(self):
        self.spend(30)
        self.spawn("tierwise:planner")
        self.assertNotIn("planner", load_state(self.root)["task"].get("counters", {}))

    def test_cap_denies_before_auto_mode_asks_for_a_reissue(self):
        self.spend(30)
        self.assertIn("task budget reached", reason(self.spawn("tierwise:planner", permission_mode="auto")))

    def test_project_cap_overrides_the_default(self):
        self.spend(6)
        self.config({"caps": {"taskBudgetUsd": 5}})
        self.assertIn("$6.00 of its $5.00", reason(self.spawn("tierwise:debugger")))
        self.config({"caps": {"taskBudgetUsd": 50}})
        self.assertNotEqual(decision(self.spawn("tierwise:debugger")), "deny")

    def test_null_cap_switches_it_off(self):
        self.spend(1000)
        self.config({"caps": {"taskBudgetUsd": None}})
        for agent in ESCALATING:
            self.assertNotEqual(decision(self.spawn(agent)), "deny", agent)

    def test_missing_or_unreadable_usage_file_is_skipped(self):
        self.assertFalse(os.path.exists(os.path.join(self.root, ".tierwise", "usage.json")))
        self.assertNotEqual(decision(self.spawn("tierwise:debugger")), "deny")
        self.write(".tierwise/usage.json", "{ not json")
        self.assertNotEqual(decision(self.spawn("tierwise:debugger")), "deny")
        self.usage({self.task_id: {"cost": "lots"}})
        self.assertNotEqual(decision(self.spawn("tierwise:debugger")), "deny")

    def test_only_the_active_tasks_usage_counts(self):
        self.usage({"t-earlier": {"cost": 500, "tokens": 1, "requests": 1},
                    self.task_id: {"cost": 2, "tokens": 1, "requests": 1}})
        self.assertNotEqual(decision(self.spawn("tierwise:planner")), "deny")

    def test_no_cap_without_an_active_task(self):
        self.spend(500)
        with locked_state(self.root) as s:
            s["task"]["phase"] = "closed"
        self.assertNotEqual(decision(self.spawn("tierwise:planner")), "deny")


class TaskUsage(RepoTest):
    def test_reads_the_tasks_cost(self):
        self.write(".tierwise/usage.json", json.dumps({"t1": {"cost": 1.25}, "t2": {"cost": 3}}))
        self.assertEqual(guard.task_usage(self.root, "t1"), 1.25)
        self.assertEqual(guard.task_usage(self.root, "t2"), 3.0)
        self.assertIsNone(guard.task_usage(self.root, "t3"))

    def test_unknown_when_missing_or_malformed(self):
        self.assertIsNone(guard.task_usage(self.root, "t1"))
        for text in ("[]", "{\"t1\": 4}", "{\"t1\": {\"cost\": true}}", "{\"t1\": {}}", "nope"):
            self.write(".tierwise/usage.json", text)
            self.assertIsNone(guard.task_usage(self.root, "t1"), text)


if __name__ == "__main__":
    unittest.main()
