---
name: debug
description: "Rung 1 of Tierwise's debugging ladder. Use after the first failed check (the gate says \"Ladder rung 1\"), or whenever a fix attempt has failed once. Raises effort to high and gives the order of work before handing up to tierwise:debugger."
effort: high
---

# Debug: rung 1

The gate blocked completion with a failure digest. You get one more attempt yourself, at high effort, before the ladder moves the problem to a fresh context.

1. Read the digest and open the full log it names (`.tierwise/reports/checks/<time>/<check>.log`). Find the first real error, not the last line.
2. Reproduce it with the exact command from the log. Not reproducible: say so; flaky checks are an investigation, not a fix.
3. Follow `tierwise:root-cause`: find the cause before you change code, one hypothesis at a time, each checked against evidence.
4. Fix the root cause, in the shared code. Never weaken, skip or delete a test to make it pass.
5. For a bug, keep a regression test and prove it: `${CLAUDE_SKILL_DIR}/../../bin/red-green --cmd "<test command>" --tests <test file>`.
6. Log the attempt: `${CLAUDE_SKILL_DIR}/../../bin/state ledger "rung 1: <hypothesis> → <result>"`.

If the same check fails again, the gate moves to rung 2. Then write a failure dossier from `templates/dossier.md` (in the plugin) to `.tierwise/briefs/dossier-<unit>.md`: what was tried, the exact failing output, hypotheses ruled out and why, pointers by path and line. Spawn `tierwise:debugger` with only the dossier's path. Do not keep patching in this context: a fresh context beats one full of failed attempts.
