import unittest

from helpers import RepoTest  # noqa: F401  (sets sys.path)
from mlib.common import default_config
from mlib.route import named_paths, route, rule_class

CFG = default_config()


def r(prompt, **kw):
    return route(prompt, CFG, **kw)


class DesignScenarios(unittest.TestCase):
    """The seven scenarios in tierwise-design.md (6 are prompts) route as the design says."""

    def test_question(self):
        x = r("Where is rate limiting configured?")
        self.assertEqual((x["class"], x["tier"], x["residentEffort"], x["plan"]), ("question", "R0", "low", False))
        self.assertEqual(x["agents"], ["scout"])
        self.assertFalse(x["startsTask"])

    def test_trivial_edit_outside_risky_paths_is_r0(self):
        x = r("Rename `getUser` to `fetchUser` in `api/users.ts`")
        self.assertEqual((x["class"], x["tier"], x["residentEffort"]), ("trivial-edit", "R0", "low"))
        self.assertEqual(x["agents"], [])
        self.assertIn("secrets", x["security"])

    def test_feature_with_request_handler_is_r2(self):
        x = r("Add CSV export to reports: endpoint, service, and a button")
        self.assertEqual((x["class"], x["tier"], x["residentEffort"], x["plan"]), ("feature", "R2", "high", True))
        self.assertIn("planner", x["agents"])
        self.assertIn("security-reviewer(high)", x["agents"])
        self.assertIn("sast", x["security"])

    def test_login_failure_is_r3_investigation(self):
        x = r("Login fails after the session times out")
        self.assertEqual((x["class"], x["tier"], x["residentEffort"], x["plan"]), ("investigation", "R3", "xhigh", True))
        self.assertIn("regression test (red-green)", x["tests"])

    def test_bulk_mechanical_r1_uses_haiku_builders(self):
        x = r("Move 200 files from the old logging API to the new one")
        self.assertEqual((x["class"], x["tier"], x["plan"]), ("bulk", "R1", True))
        self.assertIn("builder(haiku, per-file check)", x["agents"])

    def test_data_migration_is_high_risk(self):
        x = r("Split the `orders` table and migrate the data")
        self.assertEqual((x["class"], x["tier"], x["residentEffort"]), ("high-risk", "R3", "xhigh"))
        self.assertIn("principal(xhigh review)", x["agents"])
        self.assertIn("threat model (STRIDE)", x["security"])


class Rules(unittest.TestCase):
    def test_local_fix_needs_paths_or_trace(self):
        self.assertEqual(rule_class("Fix the TypeError in app/core.py", named_paths("app/core.py")), "local-fix")
        trace = "fix this\nTraceback (most recent call last):\n  File \"x.py\", line 3\nValueError: bad"
        self.assertEqual(rule_class(trace, []), "local-fix")

    def test_errors_in_a_specification_are_not_bug_reports(self):
        p = ("Add a CSV export to the shop CLI in shop/export.py. A missing input file prints an error to stderr "
             "and exits with status 1.")
        self.assertEqual(rule_class(p, named_paths(p)), "feature")
        self.assertEqual(rule_class("Fix the error in app/core.py", ["app/core.py"]), "local-fix")
        self.assertEqual(rule_class("Clicking export throws an error in shop/export.py", ["shop/export.py"]), "local-fix")

    def test_failure_without_pointers_is_investigation(self):
        self.assertEqual(rule_class("The export is broken", []), "investigation")

    def test_unclear_prompt_takes_model_label(self):
        x = r("Update the reports module for the March changes")
        self.assertTrue(x["unclear"])
        y = r("Update the reports module for the March changes", label="bulk")
        self.assertEqual((y["class"], y["source"], y["unclear"]), ("bulk", "model", False))

    def test_high_risk_label_without_r3_signal_becomes_r2_feature(self):
        x = r("Update the reports module for the March changes", label="high-risk")
        self.assertEqual((x["class"], x["tier"]), ("feature", "R2"))
        y = r("Update the reports module for the March changes in billing/charge.py", label="high-risk")
        self.assertEqual((y["class"], y["tier"]), ("high-risk", "R3"))

    def test_model_label_alone_never_opens_a_code_task(self):
        x = r("Reply with the word ok.", label="trivial-edit")
        self.assertEqual((x["class"], x["startsTask"]), ("question", False))
        y = r("Make the export faster for big reports", label="investigation")
        self.assertTrue(y["startsTask"])

    def test_card_tells_the_session_which_skills_to_load(self):
        card = r("Fix the crash in app/core.py")["card"]
        self.assertIn("Use the Skill tool now, once each, for: tierwise:root-cause, tierwise:tdd. Load no other process skills.", card)
        feature = r("Add a CSV exporter to app/report.py")["card"]
        self.assertIn("Load tierwise:orchestrate before you delegate or plan.", feature)
        self.assertIn("Ruling: no plan", feature)  # an R1 feature may skip the plan, on the record
        self.assertIn("Ruling: no plan", r("Add CSV export to reports: endpoint, service, and a button")["card"])  # R2
        r3 = r("Split the orders table and migrate the data")["card"]
        self.assertNotIn("Ruling: no plan", r3)
        self.assertIn("the plan comes first", r3)

    def test_unknown_label_is_ignored(self):
        self.assertTrue(r("lorem ipsum dolor", label="none")["unclear"])

    def test_named_paths(self):
        self.assertEqual(named_paths("see src/a.py and docs/ and https://x.io/a.py, e.g. 1.2.3"),
                         ["src/a.py", "docs/"])

    def test_changed_files_raise_tier(self):
        x = r("Add a helper to format dates", changed=["src/auth/session.py"])
        self.assertEqual((x["tier"], x["class"]), ("R3", "high-risk"))

    def test_questions_that_mention_edit_verbs(self):
        for q in ("Where is add defined?", "What does the fix_dates helper do?", "How do I add a column?",
                  "Explain how update_user works"):
            self.assertEqual(rule_class(q, []), "question", q)
        for req in ("Can you add CSV export?", "Where is add defined? Rename it to plus.",
                    "Could you please fix the export?", "What is wrong here? Fix app/core.py"):
            self.assertNotEqual(rule_class(req, named_paths(req)), "question", req)

    def test_question_never_starts_task_even_on_risky_words(self):
        x = r("How does the auth middleware validate tokens?")
        self.assertEqual(x["class"], "question")
        self.assertFalse(x["startsTask"])


class LiveRunRegressions(unittest.TestCase):
    """Prompts that misrouted in the first live run."""

    def test_regression_test_is_not_an_investigation(self):
        x = r("Fix the bug in app/core.py: add(-1, -1) returns 2 instead of -2. Add a regression test. "
              "When you spawn the reviewer, pass effort low.")
        self.assertEqual(x["class"], "local-fix")
        self.assertEqual(x["residentEffort"], "medium")  # "pass effort low" was for the reviewer
        self.assertIsNone(x["effortOverride"])

    def test_performance_regression_is_an_investigation(self):
        self.assertEqual(r("There is a performance regression in the export since Monday")["class"], "investigation")


class Overrides(unittest.TestCase):
    def test_effort_words(self):
        self.assertEqual(r("Add a CSV exporter, use max effort")["residentEffort"], "max")
        self.assertEqual(r("Add a CSV exporter. effort: high")["residentEffort"], "high")
        self.assertEqual(r("Use xhigh. Add a CSV exporter")["residentEffort"], "xhigh")
        x = r("Add a CSV exporter at xhigh")
        self.assertEqual((x["residentEffort"], x["effortOverride"]), ("xhigh", "xhigh"))

    def test_max_overrides_a_lower_configured_planner_effort(self):
        cfg = dict(CFG, planner=dict(CFG["planner"], effort="high"))
        self.assertEqual(route("Add a CSV exporter", cfg)["plannerEffort"], "high")
        self.assertEqual(route("Add a CSV exporter, use max", cfg)["plannerEffort"], "max")

    def test_no_plan_and_no_builders(self):
        x = r("Add a CSV exporter to reports, no plan, skip the builders")
        self.assertFalse(x["plan"])
        self.assertFalse(any(a.startswith("builder") for a in x["agents"]))

    def test_plan_requested_for_local_fix(self):
        self.assertTrue(r("Fix the crash in app/core.py, plan it first")["plan"])


class Card(unittest.TestCase):
    def test_card_line_and_notes(self):
        x = r("Add CSV export to reports: endpoint, service, and a button", sg_installed=False)
        first, notes = x["card"].split("\n", 1)
        self.assertTrue(first.startswith("[tierwise] route: feature · R2 · plan: planner (Fable, xhigh) · resident: high"))
        self.assertIn("tierwise:orchestrate", notes)
        self.assertIn("Recommended: install security-guidance", notes)

    def test_card_narrows_skills_and_names_planner_effort(self):
        self.assertIn("Use the Skill tool now, once each, for:", r("Add a CSV exporter to reports")["card"])
        self.assertIn("No process skill is needed", r("Where is add defined?")["card"])
        self.assertNotIn("Spawn tierwise:planner with effort", r("Add a CSV exporter to reports")["card"])
        self.assertIn("Spawn tierwise:planner with effort: max", r("Split the orders table and migrate the data")["card"])

    def test_card_names_tierwise_process_skills(self):
        self.assertEqual(r("Fix the crash in app/core.py")["skills"], ["tierwise:root-cause", "tierwise:tdd"])
        self.assertEqual(r("Add CSV export to reports: endpoint, service, and a button")["skills"],
                         ["tierwise:tdd", "tierwise:execute"])
        self.assertEqual(r("Split the orders table and migrate the data")["skills"],
                         ["tierwise:brainstorm", "tierwise:tdd", "tierwise:execute"])
        self.assertEqual(r("Where is add defined?")["skills"], [])

    def test_planner_effort_by_tier(self):
        self.assertEqual(r("Add CSV export to reports: endpoint, service, and a button")["plannerEffort"], "xhigh")
        self.assertEqual(r("Split the orders table and migrate the data")["plannerEffort"], "max")
        self.assertEqual(r("Add a CSV exporter, use max effort")["plannerEffort"], "max")

    def test_r3_card_asks_for_sign_off(self):
        self.assertIn("signs off", r("Rotate the payment signing keys")["card"])


if __name__ == "__main__":
    unittest.main()
