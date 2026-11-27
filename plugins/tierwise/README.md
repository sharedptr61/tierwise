# Tierwise

Adaptive model orchestration for Claude Code. You describe a development task; Tierwise decides which model does each part of it, at what effort, which tests and security checks it needs, and refuses to call it done while they fail. You never touch a model switch.

The main session stays on Opus for the whole task, so its prompt cache is never thrown away. Other models arrive as subagents with a pinned model and effort, and leave when they report:

| Role | Agent | Model, effort |
| --- | --- | --- |
| First plan, replans | `tierwise:planner` | Fable, xhigh; max for R3 plans and replans |
| Lookups, digests | `tierwise:scout` | Haiku, low |
| Explanations, impact maps, context packs, triage | `tierwise:analyst` | Sonnet, high |
| Independent specified units, in a worktree | `tierwise:builder` | Sonnet, medium (Haiku for mechanical batches, Opus at R3) |
| Fresh-context debugging (ladder rung 2) | `tierwise:debugger` | Opus, xhigh |
| Code and plan review | `tierwise:reviewer` | Opus, medium/high/xhigh by risk |
| Security review | `tierwise:security-reviewer` | Opus, high/xhigh (never Fable) |
| R3 diff review, ladder rungs 3–4 | `tierwise:principal` | Fable, xhigh (max once) |

## How it works

1. **Route.** For each prompt you type, the mod (`hooks/register.js`) runs the routing rules (`bin/classify-risk`), asks Haiku for a label only when the rules are unclear, and adds a one-line routing card: class, risk tier (R0–R3), plan or not, the main session's effort, agents, tests, security checks and the process skills to load. It then sets the main session's effort on every request of that prompt. Effort changes kept the prompt cache in our measurements (Claude Code 2.1.332).
2. **Enforce.** A `PreToolUse` guard (`bin/guard-spawn`) checks every Tierwise spawn: model map, review effort floors by tier, caps (one replan, two principal calls, three parallel builders), no Haiku edits at R2+, nothing below Opus for R3 core logic, depth one. The planner can write only under `.tierwise/plans/`, readers only under `.tierwise/reports/`. Every report must come back in a fixed form (STATUS, CHANGED, CHECKS, RISKS, REPORT) or it is sent back.
3. **Verify.** At every stop, the gate (`bin/run-checks --gate`) runs the checks the change needs (unit tests, type checks, a built-in secret scan, dependency and static analysis where configured), blocks completion with a short digest while they fail, walks the debugging ladder, and requires the reviews the risk tier calls for.
4. **Remember.** `.tierwise/` in each project holds `state.json`, an append-only `ledger.md` (routes, the model each agent actually ran on, gate results), `decisions.md`, plans, briefs and reports. After compaction or a restart a hook points the session back at it.

Without the mod (hooks only), a `UserPromptSubmit` hook adds the same card from the same rules; the main session's effort then stays at the session default.

## What it saves, shown as you work

Tierwise measures every request of the session, in the main session and in every subagent, from the usage the API reports, and prices it at list price for the model that served it. The status line keeps a running comparison against doing the same work on your main session's model alone:

```
tierwise $1.30 measured · all-Opus est. $0.81–$0.87 · costs 49–62% more
```

`/tierwise-savings` opens a panel with the measured cost and tokens by model and by agent, the estimate for all-Opus and for all-Fable, and how the estimate is made. At the end of a session the totals go into `.tierwise/ledger.md`.

- **Measured** figures are exact for the session's usage at list price (checked against Claude Code's own totals). On a subscription they show usage of your plan's limits in dollars, not a bill.
- **Estimated** figures are a range for one model doing everything Tierwise did, reviews included, in one session. The low end reprices the same tokens without each subagent's start-up context; the high end adds what one growing session re-reads. A model's different thinking length, retries and success rate are not modelled.
- A loss is shown as a loss. The example above is real: a Fable plan made that session cost more than all-Opus, and 16–20% less than all-Fable.

## Install

From Claude Code:

```
/plugin marketplace add sharedptr61/tierwise
/plugin install tierwise@tierwise
```

Restart Claude Code (or run `/reload-plugins`). The first time you load it, Claude Code asks whether to run the plugin's mod (in-process code with your permissions); Tierwise works without it, with coarser effort control.

Requirements: Claude Code 2.1.299 or later (2.1.332 tested), Python 3.8+, git. Projects must be git repositories for task state and the gate. Install or update Claude Code with the native installer (`curl -fsSL https://claude.ai/install.sh | bash`); the npm package can lag behind the required version.

**Platform:** Ubuntu (22.04 and 24.04 LTS). macOS and Windows are not supported in this release; support is planned once they have been tested.

### Process skills (built in)

Tierwise needs no other plugin. It ships its own process skills, loaded only when the routing card names them:

| Skill | Used for |
| --- | --- |
| `tierwise:brainstorm` | Settling an under-specified or R3 request into an approved design before planning |
| `tierwise:tdd` | Test-first changes; preloaded into the builder and debugger |
| `tierwise:root-cause` | Finding the cause before fixing; preloaded into the debugger and principal |
| `tierwise:execute` | Carrying out a plan unit by unit, with reviews, a capped fix loop and a resumable ledger |
| `tierwise:finish` | Merging, opening a pull request for, or keeping a finished branch |
| `tierwise:amend`, `tierwise:debug` | Changing a plan locally; the first rung of the debugging ladder (both raise effort to high) |

You can also run these yourself: `/tierwise:terse` (terse replies until "normal mode"), `/tierwise:commit-message`, `/tierwise:debt` (lists `shortcut:` comments), `/tierwise:compress-memory <file>` (shortens a CLAUDE.md in this session, with a backup).

### Recommended companion

- **security-guidance**, Anthropic's official security plugin, works well beside Tierwise; install it with `/plugin install security-guidance@claude-plugins-official`. It adds per-edit pattern warnings, an end-of-turn security review and a commit review. Tierwise never changes Claude Code's settings files. When security-guidance is installed, Tierwise suggests once per project that you add `"env": {"SECURITY_REVIEW_MODEL": "claude-sonnet-5-5"}` to `.claude/settings.local.json`, which runs its end-of-turn review on Sonnet (a full model ID: with a claude.ai sign-in the plugin passes the value straight to the API, which does not accept the `sonnet` alias). Put project rules in `.claude/claude-security-guidance.md` (template in `templates/`); Tierwise's security reviewer reads them too.

Tierwise also works beside other plugins. If one dispatches built-in `Explore`, `general-purpose` or `Plan` agents, Tierwise's guard sends that work to its own agents, so it runs on the intended model.

## Per-project configuration

On the first code-changing prompt in a repository Tierwise writes `.claude/tierwise.json` from auto-detection (test, lint, type-check and scanner commands) with `"confirmed": false`, and asks you to confirm it once. Defaults, including the risk path patterns, are in `templates/tierwise.json`; anything in the project file overrides them. Useful keys:

- `planner.effort` (`xhigh`), `planner.effortR3` and `planner.replanEffort` (`max`): one Fable-max plan of a small task measured 39 minutes and 263K output tokens, so max is kept for the plans that need it. The planner and principal keep a one-hour prompt cache between their long steps.
- `allowBuiltinAgents` (`false`): built-in `Explore`, `general-purpose` and `Plan` agents run on the main model's prices, so the guard sends their work to Tierwise agents. Set `true` to allow them.
- `checks.<id>`: the command for each check, or `null` when the tool is missing (reported, never skipped silently).
- `risk.R3` / `risk.R2` / `risk.R0`: path globs per tier.
- `checks.syntax` and `checks.secrets` are built in and always on: the syntax check parses changed Python, JSON, TOML (Python 3.11+) and JavaScript (needs node) files; the secret scan reads added lines, with an entropy filter on generic assignments. `checks.affected` is optional: a fast command for the affected tests that reads `TIERWISE_CHANGED_FILES` (newline-separated paths). After a failed syntax or affected check the other non-security checks are reported as skipped.
- `syntax.exclude` (path globs): files the syntax check skips, such as test fixtures that are broken on purpose. JSX in `.js` files and comments in `devcontainer.json` are tolerated without it.
- `secrets.rules` (`id`, `regex`, optional `minEntropy`) and `secrets.allow` (`paths` globs, `regexes`): your own secret patterns and allowances. An allow regex is tested against the matched secret only, never the rest of the line, so a comment beside a real key cannot allowlist it; every match on a line is checked.
- `caps.taskBudgetUsd`: once a task's measured cost reaches it, planner, principal and debugger spawns stop and Tierwise asks you; scouts, analysts, builders and reviewers still run. Needs the mod.
- The ledger records every debugging-ladder climb (`ladder: task <id> rung <a> -> <b> ...`) beside each gate result. The ladder climbs only when a check fails the same way again (numbers such as line numbers and timings are ignored); a failure the check has not shown before counts as progress and restarts at rung 1, so fixing one bug and uncovering the next does not call in the debugger or the principal.
- Static analysis (`sast`) runs Semgrep only with your project's own `.semgrep.yml`, with `--metrics off`: Tierwise never pulls rules from the Semgrep registry, which would send data about your project out.
- `caps.*`: replans, principal calls, parallel builders, gate blocks, check timeout, the weekly Fable warning level.

`.tierwise/` is excluded from git through `.git/info/exclude`; Tierwise changes no tracked file except `.claude/tierwise.json`, which it creates.

## Scripts

All in `bin/`, Python standard library only, usable by hand from a project directory:

| Script | Use |
| --- | --- |
| `classify-risk "prompt"` | show the route a prompt would get |
| `select-checks` | the checks the current change needs |
| `run-checks [--only a,b]` | run them now; digest plus full logs |
| `red-green --cmd "…" --tests f` | the regression test fails on the base and passes now |
| `review-package` | diff + spec + check results for a reviewer, no author reasoning |
| `state show\|set\|close\|ledger\|decision\|record-review\|detect` | task state and ledger |
| `guard-spawn` | the subagent hooks |

## Tests

```
python3 -m unittest discover -s plugins/tierwise/tests -v   # from the marketplace root
claude plugin test plugins/tierwise                          # the mod's rules
claude plugin validate plugins/tierwise
```

## Not in this version

Agent teams, `opusplan`, the advisor tool, non-Claude models and the optional per-file review workflow. The evaluation behind Tierwise's performance figures is described in [docs/evaluation.md](../../docs/evaluation.md).

## Credits

Several of Tierwise's process skills and report formats were shaped by ideas from [Superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT), [Caveman](https://github.com/JuliusBrussee/caveman) by Julius Brussee (MIT and Apache-2.0) and Ponytail by Dietrich Gebert (MIT). Tierwise's versions are written from scratch for its own architecture; none of their text is included. The full list of what came from where is in [docs/inventory.md](../../docs/inventory.md).

The syntax check and its fail-fast order draw on [SWE-agent](https://github.com/SWE-agent/SWE-agent)'s lint-on-edit interface, the secret rule format on [Gitleaks](https://github.com/gitleaks/gitleaks), the affected-tests check on Agentless's test selection, the fix loop's fresh start on the debugging-decay study (arXiv 2506.18403), the brief's approach line on Aider's architect/editor split, and the model ladder on a review of routing versus cascades. No code from them is included.
