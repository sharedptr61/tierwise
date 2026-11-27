---
name: orchestrate
description: Tierwise's routing rules. Use whenever a "[Tierwise] route:" card is in context, before delegating any work, writing a brief, reviewing, or claiming a task is done. Covers which agent gets which work, the eligibility rule, the debugging ladder, reviews by risk tier, handoffs and the ledger.
---

# tierwise: routing rules for the main session

You are the resident: you keep the conversation on one model for the whole task and never switch it. Other models arrive as Tierwise agents with pinned model and effort, and leave when they report. A hook or the mod has already classified the prompt; its routing card names the class, risk tier, plan, your effort, the agents, tests, security checks and process skills for this prompt. Follow the card. Plain words from the user override it ("no plan", "use max", "skip the builders"), except that the completion gate and R3 reviews always run.

Scripts: `B=${CLAUDE_SKILL_DIR}/../../bin`. Templates: `${CLAUDE_SKILL_DIR}/../../templates`. Detail: `reference/` beside this file, read on demand.

## 1. Who does what

| Work | Who | Notes |
| --- | --- | --- |
| Lookups, inventories, log and test digests | `tierwise:scout` (Haiku) | Batch questions into one brief. |
| Explaining a subsystem, impact maps, context pack, triage | `tierwise:analyst` (Sonnet) | |
| First plan; replan when the plan is invalidated | `tierwise:planner` (Fable, xhigh) | Only when the card says plan, or the ladder says replan. At R3, for a replan, or when the user asks for max, pass `effort: max` (the card says so). |
| Plan amendment (a local change to an existing plan) | You, with `tierwise:amend` | |
| Trivial edits; dependent implementation | You, inline | A brief costs more than a small edit. |
| Independent, specified unit with an acceptance check | `tierwise:builder` (Sonnet), own worktree | At most 3 at once; disjoint files. |
| Mechanical batch with a per-file check, R0/R1 only | `tierwise:builder` with `model: haiku` | |
| R3 core logic | You, or `tierwise:builder` with `model: opus` | Never below Opus. |
| Code review | `tierwise:reviewer` (Opus) | Effort set by tier. |
| Security review | `tierwise:security-reviewer` (Opus) | Never Fable. |
| R3 diff review; disagreement; ladder rungs 3–4 | `tierwise:principal` (Fable) | At most 2 per task. |

**Eligibility rule.** A model below Opus may take a unit only when it is bounded and specified, something objective checks the result (tests, types, a schema, citations you can open), and the tier allows it. No check, no downgrade.

**Delegate only** when a unit needs isolation, is independent, or needs more than about three file reads. Send follow-ups to a live agent (SendMessage) instead of spawning a new one. Tierwise agents never spawn agents. Built-in `Explore`, `general-purpose` and `Plan` agents run on your own model's prices, so the guard refuses them in a Tierwise project and names the Tierwise agent to use instead: `tierwise:scout` for lookups and exploration, `tierwise:analyst` for explanations, `tierwise:builder` for an implementation unit, `tierwise:reviewer` for a review, `tierwise:planner` for a plan. Never use `caveman:cavecrew-builder` (it inherits Opus); `caveman:cavecrew-reviewer` never counts as a review.

## 2. The lifecycle

1. **Route.** The card. If the class looks wrong, say so in one line and re-route in plain words.
2. **Orient.** One scout brief with all your questions; an analyst for what needs judgment. For a planned task the analyst writes the context pack `.tierwise/reports/context-<task>.md`.
3. **Plan** (when the card says so). At R1 and R2 you may skip the plan if the change is small and fully specified (about three files or fewer): record `$B/state ledger "Ruling: no plan - <why>"` first; the tier's reviews still run, and the tier never drops. At R3 the plan always comes first: the guard refuses your edits until the planner has written it. If the card names `tierwise:brainstorm`, settle the design with the user first. Spawn `tierwise:planner` with a brief pointing at the context pack and the design. Carry the plan out with `tierwise:execute`. At R2/R3 send the plan to `tierwise:reviewer` (it reviews plans too); resolve each objection and record the outcome with `$B/state decision "..."`. If the brief asks for decisions from the user, ask them before implementing.
4. **Implement.** Dependent units inline at the card's effort; independent units to builders, each with a brief from `templates/brief.md` saved under `.tierwise/briefs/`. Test first.
5. **Verify.** The Stop gate runs the checks the change needs (`$B/select-checks` shows which) and blocks completion while they fail, with a digest and the ladder rung. You can run them earlier: `$B/run-checks`. For a bug fix prove the regression test: `$B/red-green --cmd "<test command>" --tests <test file>`.
6. **Review.** By tier (below). Build the package with `$B/review-package` and give each reviewer only its path. Confirm each finding against the code before fixing; then the checks run again and one review scoped to the fix follows.
7. **Close.** Your final report states which checks ran and passed, which models actually ran (from `.tierwise/ledger.md`), and anything left open. At R3, ask the user to sign off. If the work is on a branch, `tierwise:finish` decides how to integrate it.

## 3. Reviews by risk tier

| Tier | Plan review | Code review | Security review |
| --- | --- | --- | --- |
| R0 | none | none (checks only) | pattern checks |
| R1 | none | reviewer, medium, once at the end | security-guidance end-of-turn |
| R2 | reviewer, high | reviewer, high | security-reviewer, high |
| R3 | reviewer, xhigh | principal (Fable, xhigh); `tierwise:reviewer` at xhigh instead when your session runs on Fable (the gate enforces this: no model reviews its own code) | security-reviewer, xhigh; user sign-off |

Pass the tier's effort on every review spawn (`effort: medium` at R1, `high` at R2, `xhigh` at R3). The guard enforces it: outside auto mode it corrects the call; in auto mode it refuses the call and names the fix, because a hook may not change a call auto mode has already approved. Reviews always run in a fresh context: never paste your reasoning into a review brief. One round of disagreement goes to `tierwise:principal`, or to the user at R3.

## 4. The debugging ladder

Each failed check moves the unit one rung when it fails the same way again; a failure the check has not shown before is progress and restarts at rung 1. The gate tells you the rung.

| Rung | Trigger | Action |
| --- | --- | --- |
| 0 | start | you, at the card's effort |
| 1 | first failure | you, under `tierwise:debug` (effort high) |
| 2 | second failure on the same check | write a dossier (`templates/dossier.md`), spawn `tierwise:debugger` |
| 3 | debugger fails, or the failure spans subsystems or contradicts the plan | `tierwise:principal`, xhigh, with the dossier |
| 4 | rung 3 fails | `tierwise:principal` with `effort: max`, once |
| 5 | rung 4 fails, a cap is hit, an irreversible step or ambiguous requirement | stop and ask the user, with the diagnosis |

If the failure shows the plan is wrong, replan with `tierwise:planner` instead of climbing (one replan per task without asking). Counters reset when the checks pass.

## 5. Handoffs

- **Point, do not paste.** A brief names files and lines; the agent reads them. Briefs stay under about 500 words: goal, acceptance checks, files in scope, out of scope, constraints, pointers, report format. Template: `templates/brief.md`.
- **Reports** come back in the fixed form (STATUS, CHANGED, CHECKS, RISKS, REPORT); a hook rejects any other. Open the REPORT file only when you need the detail.
- **Decisions** go to `.tierwise/decisions.md` once, with the reason and the options rejected (`$B/state decision`), so no later model re-derives or silently reverses them.
- **Ledger.** Hooks log routes, spawns, the model each agent actually ran on, and gate results to `.tierwise/ledger.md`. Add a line for anything a later session needs: `$B/state ledger "..."`.
- **After compaction or a restart**, read `.tierwise/state.json`, the end of the ledger and the decisions before doing anything else.
- **Compression.** A terse voice (such as `/tierwise:terse`) is fine for chat and reports. Never compress plans, briefs, reviews, specs or decisions.

## 6. How code gets written

- **Process skills.** Load only the skills the card names: `tierwise:brainstorm` (under-specified or R3), `tierwise:tdd` (every code change), `tierwise:root-cause` (bugs and failures), `tierwise:execute` (a plan to carry out), `tierwise:finish` (work on a branch). Other plugins' process skills are not needed beside these.
- **Smallest complete change.** Take the first option that fully works: is it needed at all; already in the codebase; standard library; an installed dependency; one readable line; only then new code. Finish every caller, test and fixture the change touches. Never cut validation at trust boundaries, error handling that prevents data loss, security, accessibility, or anything the user asked for. Mark a known limit with `shortcut: <limit>, <when to revisit>`.
- **Evidence before claims.** Before saying done, fixed or passing, run the command that proves it and read its output; check the diff, not an agent's report. The gate re-runs the checks, but your report must not claim what you did not see.
- **Review feedback** (from Tierwise's reviewers or the user): `reference/review.md` says how to handle it.

## 7. Never traded for tokens

The gate runs on every code change, whoever wrote it. The review tier is set by risk and never lowered. No objective check, no cheaper model. R3 core logic stays on Opus or above. Every cap ends in a question to the user, never a silent pass. Missing scanners are reported, never skipped silently.

More: `reference/routing.md` (classes, tiers, overrides), `reference/effort.md`, `reference/checks.md` (check catalogue, configuration), `reference/handoff.md` (brief, report, dossier, ledger formats), `reference/review.md`.
