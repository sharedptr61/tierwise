# Routing reference

## Classes (rules first; Haiku labels only what the rules leave unclear)

| Class | Example | Plan | Resident effort | Agents |
| --- | --- | --- | --- | --- |
| question | where is rate limiting configured? | no | low | scout |
| trivial-edit | rename in one file | no | low | none |
| local-fix | clear error in one or two files, or a stack trace | no | medium | scout; the ladder if checks fail |
| feature | new behaviour across files | planner | medium; high at R2 | scout, analyst, builders for independent units |
| bulk | the same change in many files | planner | medium | Haiku builders with per-file checks (Sonnet at R2+) |
| investigation | intermittent failure, performance | planner (diagnosis plan) | high | scout, debugger |
| high-risk | R3 feature or fix | planner | xhigh | security-reviewer, principal |

An R3 tier turns feature, local-fix and trivial-edit into high-risk.

## Risk tiers

| Tier | Typical content |
| --- | --- |
| R0 | docs, comments, test-only changes, trivial edits outside R2/R3 paths |
| R1 | ordinary feature and bug work |
| R2 | shared modules, public interfaces, request handling, concurrency, performance-critical paths, dependency changes |
| R3 | authentication, cryptography, payments, personal data, migrations, infrastructure, deploy, destructive operations |

The tier is the highest of: paths named in the prompt, files already changed in the task, and words in the prompt. Path patterns live in `.claude/tierwise.json` under `risk` (defaults in the plugin's `templates/tierwise.json`). The prompt can raise a tier, never lower it. Within a task the tier only rises.

## Plain-word overrides

| Words | Effect |
| --- | --- |
| "use max", "at xhigh", "effort: high", "max effort" | resident effort for this prompt; "max" also lets the planner and principal run at max |
| "no plan", "skip the plan" | no planner |
| "plan it first", "make a plan" | planner even for a local fix |
| "skip the builders", "no builders" | builders removed from the card |

The completion gate and R3 reviews cannot be switched off by words.

## Where routing runs

- The mod (`hooks/register.js`) routes each prompt you type, adds the card, sets the main session's effort on every request of that prompt, and keeps Tierwise agents on their model map.
- Without the mod, a `UserPromptSubmit` hook applies the same rules (no Haiku label) and adds the same card. The resident's effort then stays at the session default; `tierwise:amend` and `tierwise:debug` raise it where it matters.
- Hand-backs and task notifications are never routed.
- Built-in `Explore`, `general-purpose` and `Plan` agents inherit the main model. In a project with `.tierwise/` the guard refuses them and names the Tierwise agent to use; set `"allowBuiltinAgents": true` in `.claude/tierwise.json` to allow them.
