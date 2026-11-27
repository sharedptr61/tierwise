---
name: execute
description: Carry out a written Tierwise plan unit by unit - routing each unit to you or a builder, reviewing from diffs, running a capped fix loop, and keeping the ledger so work resumes after compaction. Use when a plan in .tierwise/plans/ is ready to implement.
---

# Execute a plan

Scripts: `B=${CLAUDE_SKILL_DIR}/../../bin`. The plan is `task.plan` in `.tierwise/state.json`.

## Setup

- Read the plan and its spec once. Check `.tierwise/ledger.md` for this plan: if units are already recorded as complete, resume at the first one that is not, and trust the ledger and `git log` over your memory.
- First line for a new plan: `$B/state ledger "plan <path>: execution started"`.
- Before unit 1, scan for conflicts: pairs of units that share a file or an interface, and units whose text contradicts itself. Rule on each, with the spec as the authority, and record the ruling.
- If you want to isolate the whole task, use the native worktree tool; builders isolate themselves.

## Each unit

1. Record the base: `git rev-parse HEAD` (or the task base for the first unit).
2. Route it as the plan says: dependent work inline (you, test first with `tierwise:tdd`); an independent, specified unit with an acceptance check to `tierwise:builder` with a brief from `templates/brief.md` saved under `.tierwise/briefs/`. Point to files; never paste the plan or your history. Builders run in parallel only when their files do not overlap (at most three).
3. Read the report. `blocked` or `partial`: add the missing context, split the unit, or rule on a plan defect; never re-send it unchanged.
4. Review by tier: at R2 and R3 after each unit; at R0 and R1 the units fold into one final review. Build the package with `$B/review-package --base <unit base>` and give the reviewer only its path, the unit's brief and the plan's global constraints. Do not tell the reviewer what to ignore.
5. Findings come back as Critical, Important or Minor. Check each against the code (`reference/review.md` in the orchestrate skill). Minor findings go to the ledger as deferred.
6. **Fix loop** for Critical, Important, or a spec gap you confirmed: rounds 1–2 go back to the same builder with the findings word for word (SendMessage); rounds 3–5 go to a fresh builder, briefed from a short failure summary (`templates/dossier.md`), one model up from round 4 (`model: opus`), because success decays after two or three attempts in one context. Each round ends with a review of the fix diff only. After round 5, rule (park it, or decide and carry the decision forward) and record it.
7. Ledger line: `$B/state ledger "unit N complete: commits a..b, review clean"` (or `... parked: <why>`).

Rulings use one form: `$B/state ledger "Ruling: <what> - <why> - <cost if wrong>"`.

## Keep going

Do not pause between units. Stop only for: an irreversible or destructive step, a security-sensitive action, an effect outside the repository (merge, shared push, publish, deploy), or a plan so wrong that every next step is a guess. Everything else is a recorded ruling.

## Finish

One review of the whole diff (`$B/review-package`), by the reviewer the tier calls for. Fix its Critical and Important findings in one pass, test first, then one review of that fix. Your final message lists **Rulings I made** and **Deferred minor findings**. Then `tierwise:finish` if the work is on a branch.
