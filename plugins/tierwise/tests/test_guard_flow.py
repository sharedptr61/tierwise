import json
from unittest import mock
import os
import time
import unittest

from helpers import RepoTest
from mlib import flow, guard
from mlib.common import load_config, load_state, locked_state, week_key
from mlib.route import route
from mlib.common import default_config


def decision(out):
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")


def updated(out):
    return (out or {}).get("hookSpecificOutput", {}).get("updatedInput")


class GuardBase(RepoTest):
    def start(self, prompt="Add a CSV exporter to app/core.py", tier=None):
        r = route(prompt, load_config(self.root))
        if tier:
            r["tier"] = tier
        flow.record_route(self.root, r, prompt, "test")
        return load_state(self.root)

    def spawn(self, subagent, caller=None, permission_mode="default", **ti):
        inp = {"cwd": self.root, "tool_name": "Agent", "permission_mode": permission_mode,
               "tool_input": {"subagent_type": subagent, "prompt": "go", "description": "d", **ti}}
        if caller:
            inp["agent_type"] = caller
        return guard.pre_agent(inp)


class PreAgent(GuardBase):
    def test_other_agents_pass_untouched(self):
        self.start()
        self.assertIsNone(self.spawn("some-plugin:agent"))
        self.assertIsNone(self.spawn("fork"))

    def test_builtin_agents_are_sent_to_tierwise_agents(self):
        self.assertIsNone(self.spawn("Explore"))  # project not set up for tierwise yet
        self.start()
        out = self.spawn("Explore", description="find the CSV writer")
        self.assertEqual(decision(out), "deny")
        self.assertIn("for the job: tierwise:scout", out["hookSpecificOutput"]["permissionDecisionReason"])
        out = self.spawn("general-purpose", description="Review the diff for task 2")
        self.assertIn("for the job: tierwise:reviewer", out["hookSpecificOutput"]["permissionDecisionReason"])
        out = self.spawn("general-purpose", description="Implement task 3: CSV escaping")
        self.assertIn("for the job: tierwise:builder", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.config({"allowBuiltinAgents": True})
        self.assertIsNone(self.spawn("general-purpose", description="anything"))

    def test_wrong_model_denied(self):
        self.start()
        out = self.spawn("tierwise:security-reviewer", model="fable")
        self.assertEqual(decision(out), "deny")
        self.assertIn("opus", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_reviewer_effort_floor_by_tier(self):
        self.start(tier="R3")
        out = self.spawn("tierwise:reviewer", effort="medium")
        self.assertEqual(updated(out)["effort"], "xhigh")
        self.assertIsNone(decision(out))  # permissions stay the user's
        self.assertEqual(updated(self.spawn("tierwise:security-reviewer"))["effort"], "xhigh")

    def test_auto_mode_gets_a_fix_to_reissue_not_a_rewrite(self):
        self.start(tier="R2")
        out = self.spawn("tierwise:reviewer", effort="medium", permission_mode="auto")
        self.assertEqual(decision(out), "deny")
        self.assertIn("re-issue this Agent call with effort: high", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.spawn("tierwise:reviewer", effort="high", permission_mode="auto"))
        self.assertEqual(load_state(self.root)["task"]["counters"]["reviewer"], 1)  # only the call that ran

    def test_r1_reviewer_gets_medium(self):
        self.start(tier="R1")
        self.assertEqual(updated(self.spawn("tierwise:reviewer"))["effort"], "medium")

    def test_builder_below_opus_denied_at_r3(self):
        self.start(tier="R3")
        self.assertEqual(decision(self.spawn("tierwise:builder")), "deny")
        self.assertIsNone(self.spawn("tierwise:builder", model="opus"))

    def test_haiku_builder_denied_at_r2(self):
        self.start(tier="R2")
        self.assertEqual(decision(self.spawn("tierwise:builder", model="haiku")), "deny")

    def test_parallel_builder_cap(self):
        self.start(tier="R1")
        for _ in range(3):
            self.assertIsNone(self.spawn("tierwise:builder"))
        self.assertEqual(decision(self.spawn("tierwise:builder")), "deny")
        guard.subagent_stop({"cwd": self.root, "agent_type": "tierwise:builder", "agent_transcript_path": "/none"})
        self.assertIsNone(self.spawn("tierwise:builder"))

    def test_replan_cap_and_replan_at_max(self):
        self.start()
        self.assertIsNone(self.spawn("tierwise:planner"))  # first plan at its pinned xhigh
        self.assertEqual(updated(self.spawn("tierwise:planner"))["effort"], "max")  # the one replan allowed
        self.assertEqual(decision(self.spawn("tierwise:planner")), "deny")

    def test_replan_in_auto_mode_asks_for_max(self):
        self.start()
        self.spawn("tierwise:planner", permission_mode="auto")
        out = self.spawn("tierwise:planner", permission_mode="auto")
        self.assertIn("re-issue this Agent call with effort: max", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.spawn("tierwise:planner", effort="max", permission_mode="auto"))

    def test_principal_max_only_on_last_rung(self):
        self.start()
        self.assertEqual(updated(self.spawn("tierwise:principal", effort="max"))["effort"], "xhigh")
        with locked_state(self.root) as s:
            s["task"]["rung"] = 4
        self.assertIsNone(self.spawn("tierwise:principal", effort="max"))
        self.assertEqual(decision(self.spawn("tierwise:principal")), "deny")  # cap of two

    def test_fable_exhausted_routes_planner_to_opus_max(self):
        self.start()
        with locked_state(self.root) as s:
            s["fable"] = {"week": week_key(), "output": 0, "exhausted": week_key()}
        up = updated(self.spawn("tierwise:planner"))
        self.assertEqual((up["model"], up["effort"]), ("opus", "max"))

    def test_planner_effort_from_card(self):
        self.start("Add a CSV exporter to app/core.py")
        self.assertIsNone(self.spawn("tierwise:planner"))  # R1 feature: xhigh, the pinned level
        self.start("Rotate the payment signing keys in billing/keys.py")  # R3 task: max
        self.assertEqual(updated(self.spawn("tierwise:planner"))["effort"], "max")

    def test_planner_effort_from_config(self):
        self.config({"planner": {"effort": "high"}})
        self.start()
        self.assertEqual(updated(self.spawn("tierwise:planner"))["effort"], "high")

    def test_depth_one(self):
        self.start()
        self.assertEqual(decision(self.spawn("tierwise:scout", caller="tierwise:builder")), "deny")

    def test_cavecrew_builder_denied_during_task(self):
        self.assertIsNone(self.spawn("caveman:cavecrew-builder"))  # no task yet
        self.start()
        self.assertEqual(decision(self.spawn("caveman:cavecrew-builder")), "deny")

    def test_spawns_are_logged(self):
        self.start()
        self.spawn("tierwise:scout")
        with open(os.path.join(self.root, ".tierwise", "ledger.md")) as f:
            self.assertIn("spawn tierwise:scout", f.read())


class PreWriteAndHandback(GuardBase):
    def write_by(self, agent, path):
        return guard.pre_write({"cwd": self.root, "agent_type": agent, "tool_input": {"file_path": path}})

    def test_planner_writes_only_plans(self):
        self.assertIsNone(self.write_by("tierwise:planner", ".tierwise/plans/p.md"))
        self.assertEqual(decision(self.write_by("tierwise:planner", "app/core.py")), "deny")
        self.assertEqual(decision(self.write_by("tierwise:planner", ".tierwise/plans/../../app/x.py")), "deny")
        self.assertIsNone(self.write_by("tierwise:planner", os.path.join(self.root, ".tierwise/plans/q.md")))

    def test_readers_write_only_reports(self):
        self.assertIsNone(self.write_by("tierwise:reviewer", ".tierwise/reports/r.md"))
        self.assertEqual(decision(self.write_by("tierwise:scout", "app/core.py")), "deny")

    def test_builder_and_main_session_unrestricted(self):
        self.assertIsNone(self.write_by("tierwise:builder", "app/core.py"))
        self.assertIsNone(guard.pre_write({"cwd": self.root, "tool_input": {"file_path": "app/core.py"}}))

    def test_report_contract(self):
        good = "STATUS: done\nCHANGED: app/core.py\nCHECKS: unit pass\nRISKS: none\nREPORT: none"
        self.assertEqual(guard.check_report(good), [])
        self.assertEqual(guard.check_report("**STATUS:** done\n**CHANGED:** none\n**CHECKS:** none\n"
                                            "**RISKS:** none\n**REPORT:** none"), [])
        self.assertIn("missing field(s): CHANGED, CHECKS, RISKS, REPORT", guard.check_report("STATUS: done")[0])
        self.assertTrue(any("STATUS must" in p for p in guard.check_report(good.replace("done", "great"))))
        self.assertTrue(any("characters" in p for p in guard.check_report(good + "x" * 2000)))
        out = guard.pre_handback({"agent_type": "tierwise:scout", "tool_input": {"message": "PONG"}})
        self.assertEqual(decision(out), "deny")
        self.assertIsNone(guard.pre_handback({"agent_type": "other:agent", "tool_input": {"message": "PONG"}}))


class ReadOnlyBash(GuardBase):
    def bash(self, agent, command):
        return guard.pre_bash({"cwd": self.root, "agent_type": agent, "tool_input": {"command": command}})

    def test_reviewers_may_read(self):
        for cmd in ("git diff HEAD", "git log --oneline -5", "git show HEAD~1:app/core.py", "git status --short",
                    "grep -rn add app/", "python3 -m unittest discover -q", "git -C /x diff", "cat app/core.py 2>/dev/null",
                    "python3 -m pytest -q > /dev/null 2>&1", "git config --get user.name"):
            self.assertIsNone(self.bash("tierwise:reviewer", cmd), cmd)

    def test_reviewers_may_not_change_state(self):
        for cmd in ("git stash", "git stash && python3 -m unittest && git stash pop", "git checkout HEAD~1 -- app/core.py",
                    "git reset --hard", "git commit -am x", "rm -rf build", "echo x > app/core.py", "sed -i s/a/b/ f.py",
                    "python3 -m unittest; git restore .", "cat a | tee out.txt", "git -C /x stash", "pip install requests"):
            self.assertEqual(decision(self.bash("tierwise:reviewer", cmd)), "deny", cmd)
        self.assertEqual(decision(self.bash("tierwise:security-reviewer", "git stash")), "deny")

    def test_builders_and_main_session_are_not_limited(self):
        self.assertIsNone(self.bash("tierwise:builder", "git commit -am 'unit 1'"))
        self.assertIsNone(self.bash("", "git stash"))
        self.assertIsNone(self.bash("other:agent", "rm -rf x"))


class R3PlanFirst(GuardBase):
    def edit_main(self, path):
        return guard.pre_write({"cwd": self.root, "tool_input": {"file_path": path}})

    def test_r3_edits_wait_for_the_plan(self):
        self.start("Split the orders table and migrate the data in db/migrations/0002.sql")
        self.assertEqual(decision(self.edit_main("db/migrations/0002.sql")), "deny")
        self.assertIsNone(self.edit_main(".tierwise/briefs/planner.md"))  # briefs for the planner are fine
        with locked_state(self.root) as s:
            s["task"]["plan"] = ".tierwise/plans/t-split.md"
        self.assertIsNone(self.edit_main("db/migrations/0002.sql"))

    def test_user_can_say_no_plan_and_lower_tiers_are_free(self):
        self.start("Split the orders table and migrate the data, no plan")
        self.assertIsNone(self.edit_main("db/migrations/0002.sql"))
        self.start("Add a CSV exporter to app/core.py")
        self.assertIsNone(self.edit_main("app/core.py"))


class SubagentStop(GuardBase):
    def transcript(self, model, out_tokens, handback=True, error=None):
        rows = [{"type": "assistant", "message": {"model": model, "usage": {"output_tokens": out_tokens},
                                                  "content": [{"type": "text", "text": "thinking"}]}}]
        if handback:
            rows.append({"type": "assistant", "message": {"model": model, "usage": {"output_tokens": 5}, "content": [
                {"type": "tool_use", "name": "SubagentHandback", "input": {"message": "STATUS: done"}}]}})
        if error:
            rows.append({"type": "assistant", "isApiErrorMessage": True,
                         "message": {"model": "<synthetic>", "content": [{"type": "text", "text": error}]}})
        path = os.path.join(self.tmp, f"t{time.time()}.jsonl")
        with open(path, "w") as f:
            f.write("\n".join(json.dumps(r) for r in rows))
        return path

    def stop(self, agent, path):
        return guard.subagent_stop({"cwd": self.root, "agent_type": agent, "agent_transcript_path": path,
                                    "effort": {"level": "max"}})

    def test_logs_model_and_records_review(self):
        self.start()
        self.stop("tierwise:reviewer", self.transcript("claude-opus-5-5", 100))
        st = load_state(self.root)
        self.assertIn("code", st["task"]["reviews"])
        with open(os.path.join(self.root, ".tierwise", "ledger.md")) as f:
            log = f.read()
        self.assertIn("return tierwise:reviewer ran on claude-opus-5-5 · effort max · 105 output tokens", log)

    def test_fable_tally_and_warning(self):
        self.config({"caps": {"fableWeeklyOutputTokensWarn": 1000}})
        self.start()
        self.assertIsNone(self.stop("tierwise:principal", self.transcript("claude-fable-5-2", 600)))
        out = self.stop("tierwise:principal", self.transcript("claude-fable-5-2", 600))
        self.assertIn("past the warning level", out["systemMessage"])
        self.assertEqual(load_state(self.root)["fable"]["output"], 1210)

    def test_planner_on_fable_limit_marks_exhausted(self):
        self.start()
        out = self.stop("tierwise:planner", self.transcript("claude-fable-5-2", 10, handback=False,
                                                           error="Fable limit reached · continuing uses usage credits"))
        self.assertIn("runs on opus", out["systemMessage"])
        self.assertEqual(load_state(self.root)["fable"]["exhausted"], week_key())

    def test_planner_report_records_plan(self):
        self.start()
        self.write(".tierwise/plans/t-x.md", "# plan\n")
        self.stop("tierwise:planner", self.transcript("claude-fable-5-2", 10))
        self.assertEqual(load_state(self.root)["task"]["plan"], ".tierwise/plans/t-x.md")

    def test_off_fable_planner_is_flagged(self):
        self.start()
        self.stop("tierwise:planner", self.transcript("claude-opus-4-8", 10))
        with open(os.path.join(self.root, ".tierwise", "ledger.md")) as f:
            self.assertIn("did not run on Fable", f.read())


class Worktrees(GuardBase):
    """Builders run in their own git worktree; tierwise's state stays in the main checkout."""

    def add_worktree(self):
        path = os.path.join(self.tmp, "wt")
        self.git("worktree", "add", "-q", "-b", "unit-1", path)
        return os.path.realpath(path)

    def test_main_root_from_a_worktree(self):
        from mlib.common import git_root, main_root
        wt = self.add_worktree()
        self.assertEqual(main_root(wt), self.root)
        self.assertEqual(git_root(wt), wt)
        self.assertEqual(main_root(self.root), self.root)
        self.assertIsNone(main_root(self.tmp))

    def test_builder_return_from_a_worktree_is_logged_and_frees_its_slot(self):
        self.start(tier="R1")
        for _ in range(3):
            self.assertIsNone(self.spawn("tierwise:builder"))
        wt = self.add_worktree()
        guard.subagent_stop({"cwd": wt, "agent_type": "tierwise:builder", "agent_transcript_path": "/none"})
        self.assertEqual(load_state(self.root)["inflight"]["builder"], 2)
        with open(os.path.join(self.root, ".tierwise", "ledger.md")) as f:
            self.assertIn("return tierwise:builder", f.read())
        self.assertFalse(os.path.exists(os.path.join(wt, ".tierwise")))

    def test_gate_checks_the_worktree_and_logs_in_the_main_checkout(self):
        self.config({"checks": {"unit": "test -f PASS"}})
        self.start(tier="R0")
        wt = self.add_worktree()
        with open(os.path.join(wt, "README.md"), "w") as f:
            f.write("# changed in the worktree\n")
        out = flow.gate(self.root, {"cwd": wt})
        self.assertIsNotNone(out)  # the change in the worktree was seen
        self.assertIn("checks pass (secrets)", out["systemMessage"])
        self.assertTrue(os.path.isdir(os.path.join(self.root, ".tierwise", "reports", "checks")))
        self.assertFalse(os.path.exists(os.path.join(wt, ".tierwise")))


class Gate(GuardBase):
    def setUp(self):
        super().setUp()
        self.config({"checks": {"unit": "test -f PASS"}})

    def gate(self, **inp):
        return flow.gate(self.root, {"cwd": self.root, **inp})

    def test_no_task_no_gate(self):
        self.assertIsNone(self.gate())

    def test_no_changes_no_gate(self):
        self.start()
        self.assertIsNone(self.gate())

    def test_failing_check_blocks_and_climbs_the_ladder(self):
        self.start(tier="R1")
        self.write("app/core.py", "def add(a, b):\n    return a * b\n")
        out = self.gate()
        self.assertEqual(out["decision"], "block")
        self.assertIn("FAIL unit", out["reason"])
        self.assertIn("Ladder rung 1", out["reason"])
        self.assertEqual(load_state(self.root)["effortFloor"], "high")
        self.touch_change(2)
        self.assertIn("Ladder rung 2", self.gate(stop_hook_active=True)["reason"])

    def touch_change(self, n):
        self.write("app/core.py", f"def add(a, b):\n    return a * b  # attempt {n}\n")
        t = time.time() + n
        os.utime(os.path.join(self.root, "app/core.py"), (t, t))

    def test_stop_without_a_new_change_is_released_not_looped(self):
        self.start(tier="R1")
        self.touch_change(1)
        self.assertEqual(self.gate()["decision"], "block")
        out = self.gate(stop_hook_active=True)  # e.g. the session is asking the user a question
        self.assertNotIn("decision", out)
        self.assertIn("checks still fail (unit)", out["systemMessage"])
        self.assertIn("not verified", out["systemMessage"])
        st = load_state(self.root)["task"]
        self.assertEqual((st["phase"], st["rung"]), ("verify", 1))  # the ladder did not climb

    def test_missing_review_is_never_verified(self):
        self.start(tier="R2")
        self.write("PASS", "")
        self.touch_change(1)
        self.write("app/core.py", "def add(a, b):\n    return a + b\n")
        self.assertEqual(self.gate()["decision"], "block")
        out = self.gate()
        self.assertIn("required review(s) not run: tierwise:reviewer, tierwise:security-reviewer",
                      out["systemMessage"])
        self.assertEqual(load_state(self.root)["task"]["phase"], "review")

    def test_pass_then_review_then_verified(self):
        self.start(tier="R1")
        self.write("app/core.py", "def add(a, b):\n    return a + b  # ok\n")
        self.write("PASS", "")
        out = self.gate()
        self.assertEqual(out["decision"], "block")
        self.assertIn("tierwise:reviewer at medium", out["reason"])
        with locked_state(self.root) as s:
            s["task"]["reviews"]["code"] = time.time() + 1
        out = self.gate()
        self.assertNotIn("decision", out)
        self.assertIn("checks pass", out["systemMessage"])
        self.assertEqual(load_state(self.root)["task"]["phase"], "verified")
        self.assertIsNone(self.gate())  # nothing changed since the pass

    def test_r0_needs_no_review(self):
        self.start("Fix typo in README.md", tier="R0")
        self.write("README.md", "# demo, fixed\n")
        self.config({"checks": {"docs": "true"}})
        out = self.gate()
        self.assertIn("checks pass", out["systemMessage"])

    def test_defers_while_tierwise_agents_run(self):
        self.start()
        self.write("app/core.py", "x = 1\n")
        running = [{"type": "subagent", "status": "running", "agent_type": "tierwise:builder"}]
        self.assertIsNone(self.gate(background_tasks=running))
        other = [{"type": "shell", "status": "running"}]
        self.assertEqual(self.gate(background_tasks=other)["decision"], "block")

    def test_gives_up_at_rung_five_and_tells_user(self):
        self.start()
        for n in range(1, 5):
            self.touch_change(n)
            self.assertEqual(self.gate()["decision"], "block")
        self.touch_change(5)
        out = self.gate()
        self.assertNotIn("decision", out)
        self.assertIn("ladder or the gate cap is exhausted", out["systemMessage"])
        self.assertEqual(load_state(self.root)["task"]["phase"], "blocked")

    def test_secret_in_change_blocks(self):
        self.start(tier="R1")
        self.write("PASS", "")
        self.write("app/core.py", 'TOKEN = "ghp_' + "a" * 36 + '"\n')
        out = self.gate()
        self.assertIn("FAIL secrets", out["reason"])

    def test_record_route_continues_task_and_raises_tier(self):
        st = self.start("Add a CSV exporter to app/core.py")
        tid = st["task"]["id"]
        self.write("app/core.py", "def add(a, b):\n    return a + b + 0\n")  # work in progress keeps its task
        flow.record_route(self.root, route("Also update billing/charge.py to log exports", default_config()),
                          "also", "test")
        st = load_state(self.root)
        self.assertEqual((st["task"]["id"], st["task"]["tier"]), (tid, "R3"))

    def test_a_task_with_no_changes_gives_way_to_the_next(self):
        first = self.start("Rename add to plus in app/core.py")["task"]["id"]
        time.sleep(1.1)  # task ids carry the second
        second = self.start("Fix the crash in app/core.py")["task"]
        self.assertNotEqual(second["id"], first)
        self.assertEqual(second["class"], "local-fix")
        with open(os.path.join(self.root, ".tierwise", "ledger.md")) as f:
            self.assertIn(f"task {first} replaced", f.read())
        self.write("app/core.py", "x = 2\n")
        third = self.start("Add a CSV exporter to app/core.py")["task"]
        self.assertEqual(third["id"], second["id"])  # work in progress keeps its task

    def first_task_note(self, sg):
        os.remove(os.path.join(self.root, ".claude", "tierwise.json"))
        r = route("Add a CSV exporter to app/core.py", default_config())
        with mock.patch.object(flow, "sg_installed", return_value=sg):
            notes = flow.record_route(self.root, r, "p", "test")
        self.assertTrue(os.path.exists(os.path.join(self.root, ".claude", "tierwise.json")))
        self.assertIn("confirm", notes[0])
        return notes[0]

    def test_first_task_writes_its_config_and_never_claude_settings(self):
        for sg in (True, False):
            self.first_task_note(sg)
            self.assertFalse(os.path.exists(os.path.join(self.root, ".claude", "settings.local.json")), sg)

    def test_suggests_the_review_model_only_to_security_guidance_users(self):
        self.assertIn('"SECURITY_REVIEW_MODEL": "claude-sonnet-5-5"', self.first_task_note(True))
        self.assertNotIn("SECURITY_REVIEW_MODEL", self.first_task_note(False))
        self.write(".claude/settings.local.json", json.dumps({"env": {"SECURITY_REVIEW_MODEL": "claude-opus-5-5"}}))
        self.assertNotIn("SECURITY_REVIEW_MODEL", self.first_task_note(True))  # the user's own choice stands
        self.assertIsNone(flow.ensure_config(self.root))  # nothing more once a project is configured

    def transcript_of(self, model):
        path = os.path.join(self.tmp, f"main-{model}.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "x"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {"model": model, "content": []}}) + "\n")
        return path

    def test_main_model_from_transcript(self):
        self.assertEqual(flow.main_model(self.transcript_of("claude-fable-5-2")), "claude-fable-5-2")
        self.assertIsNone(flow.main_model("/nonexistent"))
        self.assertIsNone(flow.main_model(None))

    def test_r3_code_by_fable_is_reviewed_by_opus(self):
        self.start(tier="R3")
        self.write("PASS", "")
        self.write("app/core.py", "def add(a, b):\n    return a + b  # r3\n")
        out = self.gate(transcript_path=self.transcript_of("claude-fable-5-2"))
        self.assertIn("tierwise:reviewer at xhigh", out["reason"])
        self.assertIn("Fable wrote this code, so Opus reviews it", out["reason"])
        self.assertNotIn("tierwise:principal", out["reason"])
        with locked_state(self.root) as s:
            s["task"]["reviews"].update(principal=time.time() + 1, security=time.time() + 1)
        out = self.gate(transcript_path=self.transcript_of("claude-fable-5-2"))
        self.assertIn("required review(s) not run: tierwise:reviewer", out["systemMessage"])  # principal does not count

    def test_r3_code_by_opus_is_reviewed_by_the_principal(self):
        self.start(tier="R3")
        self.write("PASS", "")
        self.write("app/core.py", "def add(a, b):\n    return a + b  # r3\n")
        out = self.gate(transcript_path=self.transcript_of("claude-opus-5-5"))
        self.assertIn("tierwise:principal at xhigh", out["reason"])
        with locked_state(self.root) as s:
            s["task"]["reviews"].update(principal=time.time() + 1, security=time.time() + 1)
        self.assertIn("checks pass", self.gate(transcript_path=self.transcript_of("claude-opus-5-5"))["systemMessage"])


if __name__ == "__main__":
    unittest.main()
