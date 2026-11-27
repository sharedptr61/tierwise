---
name: amend
description: Amend an existing Tierwise plan for a local change (a renamed interface, a unit split in two, a new check) without a full replan. Raises effort to high. Use when the plan in .tierwise/plans/ is still right overall; replan with tierwise:planner when it is not.
effort: high
---

# Amend a plan

Use this when a plan exists and the change is local. If the change invalidates the plan's structure (units, ownership, the approach), stop: that is a replan, `tierwise:planner`, one per task without asking the user.

1. Read the active plan (`task.plan` in `.tierwise/state.json`) and `.tierwise/decisions.md`.
2. State the amendment in one sentence and the reason for it.
3. Check its reach: which units, owned files, acceptance checks, `Checks:` lines and tests change. A unit that becomes dependent on another moves to the resident; two parallel units must still own disjoint files.
4. Edit the plan in place (Edit, not a rewrite). Mark the change with `> Amended <date>: <one line>` under the units it touches.
5. Record it: `${CLAUDE_SKILL_DIR}/../../bin/state decision "<amendment> · <reason> · <rejected option> · resident"`.
6. If a builder is working on a changed unit, send it the change (SendMessage) instead of spawning a new builder.
7. At R2/R3, an amendment that changes an interface, a threat-model assumption or an irreversible step goes back to `tierwise:reviewer` for a plan review scoped to the amendment.
