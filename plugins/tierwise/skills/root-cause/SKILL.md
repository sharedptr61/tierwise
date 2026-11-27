---
name: root-cause
description: Root-cause debugging for any bug, failing test, flaky behaviour, performance problem or build failure. Use before proposing a fix, and again after a fix has failed. Find the cause first, one hypothesis at a time.
---

# Root cause first

**Rule: no fix until you can name the cause and show the evidence for it.** A fix without a cause is a guess, and guesses pile up.

## 1. Investigate

- Read the whole error and stack trace, not the last line.
- Reproduce it with an exact command. If you cannot, collect data (logs, inputs, timing) instead of guessing.
- Check what changed: the diff, dependency and configuration changes, the environment.
- Where several components hand data along, log what enters and leaves each boundary, run once, and see which layer goes wrong. Then dig in that layer only.
- Trace the bad value backwards to where it was first wrong.

## 2. Compare

Find similar code that works. Read it fully and list every difference from the broken path, including assumptions and dependencies.

## 3. One hypothesis at a time

Write it down: "X causes this because Y". Test it with the smallest change, changing one thing. If it is wrong, form a new hypothesis from what you learned; never stack a second change on a failed one. Say "I do not understand X" when that is true.

## 4. Fix

Write a failing test that reproduces the bug (`tierwise:tdd`), then fix the cause, once, in the shared code. No refactors in the same change. Then run the checks.

## When fixes keep failing

Each failed fix goes back to step 1 with the new evidence. After **three** failed fixes, stop patching: the design or the plan is probably wrong. Write that in the failure dossier; Tierwise's debugging ladder moves the problem to a fresh context or a replan, and in the end to the user.

## Useful habits

- Flaky tests: wait for the actual condition (poll it, with a hard timeout) instead of sleeping a fixed time.
- After the fix, consider a guard at the entry point and in the environment, so the same bad value is caught earlier next time.
- Environmental or timing causes: write down what you ruled out, add handling (retry, timeout, clear message) and logging.
