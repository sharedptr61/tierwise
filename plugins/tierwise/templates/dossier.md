# Failure dossier: <unit>

> Task `<task-id>` · tier `<tier>` · ladder rung `<n>` · keep this near 400 words plus pointers

**Expected.** What should happen, and the check that says so.

**Failing command and output.** The exact command, and the decisive lines of output (the first real error, not the tail). Full log: `.tierwise/reports/checks/<time>/<check>.log`.

**What was tried.** Each attempt in one line: hypothesis → change → result.

**Working tree.** Say whether the failed attempts are still applied or were reverted (with the diff or commit). One line per attempt; no patch bodies or transcripts.

**Ruled out.** Hypotheses eliminated, and the evidence that eliminated each.

**Still plausible.** Remaining hypotheses, most likely first.

**Pointers.** `path:line`: why it matters.

**Constraints.** What must not change (interfaces, decisions in `.tierwise/decisions.md`).
