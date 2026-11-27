"""Fixes from the blind evaluation of 2026-11-26: ladder failure signatures, unique task ids, the Semgrep
default, the check digest and environment limit, and the scout's scope."""
import os
import time

from helpers import RepoTest
from mlib import checks as C
from mlib import flow
from mlib.common import load_state
from test_flow_research import LadderBase
from test_guard_flow import GuardBase, decision


class FailureSignatures(LadderBase):
    def setUp(self):
        super().setUp()
        self.config({"checks": {"unit": "cat FAILMSG; test -f PASS"}})

    def attempt(self, n, message):
        self.write("FAILMSG", message + "\n")
        self.change(n)
        return self.gate()

    def rung(self):
        return load_state(self.root)["task"]["rung"]

    def test_the_same_failure_climbs(self):
        self.start(tier="R1")
        for n in (1, 2, 3):
            self.attempt(n, "FAILED test_total: assert 3 == 4 (line 12, 0.02s)")
            self.assertEqual(self.rung(), n)

    def test_numbers_alone_do_not_make_a_new_failure(self):
        self.start(tier="R1")
        self.attempt(1, "FAILED test_total: assert 3 == 4 (line 12, 0.02s)")
        self.attempt(2, "FAILED test_total: assert 3 == 4 (line 14, 0.05s)")
        self.assertEqual(self.rung(), 2)

    def test_a_new_failure_is_progress_not_escalation(self):
        self.start(tier="R1")
        self.attempt(1, "FAILED test_total: assert 3 == 4")
        self.attempt(2, "FAILED test_total: assert 3 == 4")
        self.assertEqual(self.rung(), 2)
        out = self.attempt(3, "FAILED test_export: KeyError 'currency'")
        self.assertEqual(self.rung(), 1)
        self.assertIn("Ladder rung 1", out["reason"])

    def test_going_back_to_an_old_failure_climbs(self):
        self.start(tier="R1")
        self.attempt(1, "FAILED test_total: assert 3 == 4")
        self.attempt(2, "FAILED test_export: KeyError 'currency'")
        self.attempt(3, "FAILED test_total: assert 3 == 4")
        self.assertEqual(self.rung(), 2)

    def test_a_pass_forgets_the_signatures(self):
        self.start(tier="R1")
        self.attempt(1, "FAILED test_total: assert 3 == 4")
        self.write("PASS", "")
        self.change(2)
        self.gate()
        st = load_state(self.root)
        self.assertEqual(st["verification"]["status"], "pass")
        self.assertEqual(st["task"].get("signatures"), {})


class TaskIds(RepoTest):
    def test_ids_differ_within_one_second(self):
        ids = {flow.new_task_id() for _ in range(3) if not time.sleep(0.002)}
        self.assertEqual(len(ids), 3)
        self.assertRegex(next(iter(ids)), r"^t\d{8}-\d{6}-\d{3}$")


class SemgrepStaysLocal(RepoTest):
    def fake_semgrep(self):
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir, exist_ok=True)
        p = os.path.join(bindir, "semgrep")
        with open(p, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(p, 0o755)
        os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]

    def test_no_registry_rules_without_a_local_config(self):
        self.fake_semgrep()
        self.assertNotIn("sast", C.detect(self.root))

    def test_local_config_with_metrics_off(self):
        self.fake_semgrep()
        self.write(".semgrep.yml", "rules: []\n")
        cmd = C.detect(self.root)["sast"]
        self.assertIn("--metrics off", cmd)
        self.assertIn("--config .semgrep.yml", cmd)
        self.assertNotIn("auto", cmd)


class DigestAndEnvironment(RepoTest):
    def test_digest_keeps_the_first_and_last_errors(self):
        text = "\n".join(f"ERROR case {i}" for i in range(100))
        out = C.digest(text, limit=10).splitlines()
        self.assertEqual(out[0], "ERROR case 0")
        self.assertEqual(out[-1], "ERROR case 99")
        self.assertIn("more error lines", out[5])
        self.assertEqual(len(out), 10)

    def test_short_digest_unchanged(self):
        self.assertEqual(C.digest("ok\nERROR one\nERROR two"), "ERROR one\nERROR two")

    def test_changed_files_limit_counts_bytes(self):
        files = [f"dossier/é{i:05d}.txt" for i in range(9000)]  # 2 bytes per é
        text = C._changed_env(files, limit=120_000)
        self.assertLessEqual(len(text.encode()), 120_000)
        self.assertTrue(text.endswith(".txt"))


class ScoutScope(GuardBase):
    def test_scout_may_locate(self):
        self.start()
        self.assertNotEqual(decision(self.spawn("tierwise:scout", prompt="Where is add defined? List its callers.")), "deny")

    def test_judgment_goes_to_the_analyst(self):
        self.start()
        for brief in ("Evaluate these three libraries", "Research GitHub for retry helpers",
                      "Which is better, A or B?", "Recommend an approach for caching"):
            out = self.spawn("tierwise:scout", prompt=brief)
            self.assertEqual(decision(out), "deny", brief)
            self.assertIn("tierwise:analyst", out["hookSpecificOutput"]["permissionDecisionReason"])
