# Capability inventory: what Tierwise owns, what it leaves out

Sources: Superpowers 7.0.2, Caveman 4.2.0, Ponytail 5.3.3, read on 26 November 2026. Tierwise's versions are written fresh for Tierwise, shorter, and adapted to its pinned agents, ledger and completion gate; no text is copied. Ideas are credited in the README.

**Proof** says how each kept item is checked: *unit* (automated tests in `tests/`), *consistency* (the test that every skill and agent Tierwise names exists), or *eval* (a live scenario in the evaluation suite, because a prose rule can only be proven by behaviour).

## Owned by Tierwise

| Capability | Source | Lives in Tierwise as | Proof |
| --- | --- | --- | --- |
| Plan format: tasks with files, interfaces (consumes / produces), expected outputs; global constraints; review focus; self-review; decisions, not code transcripts | Superpowers writing-plans | `agents/planner.md` + `templates/plan.md` (no separate skill) | consistency; eval "planned feature" |
| Test-first: failing test first and for the right reason, minimal pass, full suite, failing repro for bugs, test-quality rules | Superpowers test-driven-development | skill `tierwise:tdd`, preloaded into builder and debugger | consistency; red-green script (unit); eval "bug fix" |
| Root-cause debugging: no fix before root cause, four phases, one hypothesis per change, boundary instrumentation, poll instead of sleep, three failed fixes means question the design | Superpowers systematic-debugging | skill `tierwise:root-cause` (no effort key), preloaded into debugger and principal; `tierwise:debug` is rung 1 and points to it | consistency; eval "hard bug" |
| Brainstorm before building when the request is under-specified or R3: triage what is known, look before asking, one question at a time, 2–3 approaches, written design, approval gate | Superpowers brainstorming (without the browser companion) | skill `tierwise:brainstorm`; design saved in `.tierwise/specs/` | consistency; card names it (unit); eval "vague feature" |
| Plan execution loop: ledger with plan identity and resume, base commit per unit, brief and report by file, review from a diff, three severities, fix loop capped at five rounds with a stronger model in rounds 4–5, deferred minors, rulings list, one final review, only four reasons to stop | Superpowers subagent-driven-development and executing-plans | skill `tierwise:execute`, using Tierwise's builder, reviewer and ladder | consistency; review package (unit); eval "planned feature" |
| Handling review feedback: verify before changing, clarify everything unclear first, no performative agreement, push back with evidence, check usage before adding "proper" features, one fix at a time with a test | Superpowers receiving-code-review | `skills/orchestrate/reference/review.md` | eval |
| Evidence before claims: name the command, run it, read the output; check the diff, not an agent's report | Superpowers verification-before-completion | orchestrate rule; enforced by the Stop gate | unit (gate) |
| Finishing a branch: green suite first, three options (merge locally, push and open a PR, keep), test the merged result, discard only on the explicit word, no `--force`, clean up only Tierwise's own worktrees | Superpowers finishing-a-development-branch | skill `tierwise:finish` | consistency; eval |
| Isolation: detect an existing worktree, prefer the native worktree tool | Superpowers using-git-worktrees | builder `isolation: worktree`; two lines in `tierwise:execute` | live (builder) |
| Parallel work: only independent units with disjoint files, one message, integrate with a full-suite run | Superpowers dispatching-parallel-agents | `tierwise:execute` + guard cap of three builders | unit (cap) |
| Compact report formats: locator rows `path:line — note`; builder receipt with `verified:`; review findings `path:line: severity: problem. fix.` with totals | Caveman cavecrew agents, caveman-review | agent prompts (scout, builder, reviewer, security-reviewer) | unit (report contract) |
| Smallest complete change: the six-step ladder, finish every caller and test, never-cut list, `shortcut:` comments that name the limit and the upgrade trigger | Ponytail | builder and debugger prompts; orchestrate rule for the main session | eval |
| Review checklist: correct, safe, holds under load, tested, fast, lean; no concrete failing case, no finding; grep callers when a signature changes; a named `shortcut:` is a decision, not a finding | Ponytail review and audit | reviewer prompt | eval |
| Terse voice (user-invoked): answer first, no ceremony, never drop negations, numbers, paths or error text, plain prose for security, irreversible steps and anything persisted | Caveman core | skill `tierwise:terse` (user-invoked only) | consistency |
| Commit messages: conventional commits, imperative, short subject, body only for why, breaking change or migration | Caveman caveman-commit | skill `tierwise:commit-message` (user-invoked only) | consistency |
| Shortcut ledger: list every `shortcut:` comment with its limit and trigger, flag those with no trigger | Ponytail debt | skill `tierwise:debt` (user-invoked only) | consistency |
| Memory-file compression, done by the session itself with a backup, keeping code, paths and headings exact | Caveman caveman-compress (without its external model call) | skill `tierwise:compress-memory` (user-invoked only) | consistency |

## Left out

| Capability | Why |
| --- | --- |
| Superpowers session bootstrap ("load every skill that might apply") | The routing card replaces it, per prompt. |
| Brainstorming browser companion (Node web server, ~1,700 lines) | Heavy, needs Node.js, separate state. |
| Superpowers scripts (task-brief, workspace, find-polluter) | Tierwise's `review-package` and ledger cover them; find-polluter is npm-only. |
| writing-skills, diagnosing-superpowers | Not about developing the user's software. |
| Caveman Cloud: setup, discover, learn, manage, optimize, evidence review, auto routing, gateway, proxy, telemetry | Route LLM traffic or send prompts, memory files and machine data to a third party; telemetry is on by default. A public plugin must not do this by default. |
| Caveman hooks, statusline, stats history | Node.js state machinery; Tierwise has its own mode handling. |
| Ultracave and Classical Chinese voices | Novelty; no measured benefit. |
| Ponytail hooks, band, board, band import | Node.js; the band reads past session history. Tierwise's savings panel replaces the useful part, measured from the current session. |
| Ponytail levels and its gain card | Levels add mode state; the gain card is the author's own benchmark. |

## Dependencies

- **Optional:** `security-guidance` from Anthropic's official marketplace (`claude-plugins-official`). Installed with Tierwise by default; users may switch it off; Tierwise never needs it.
- **None** on Superpowers, Caveman or Ponytail. Tierwise still works beside them: the guard refuses built-in agents they dispatch and sends the work to Tierwise's agents.
