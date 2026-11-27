# Effort reference

| Role | Model | Effort |
| --- | --- | --- |
| Prompt classifier (mod) | Haiku | default; one label, about 2 s, only when rules are unclear |
| scout | Haiku | low; medium for digests |
| planner | Fable | xhigh; max for R3 plans, replans, and when the user asks (`planner.effort`, `planner.effortR3`, `planner.replanEffort` in `.claude/tierwise.json`) |
| plan amendment | resident | high (`tierwise:amend`) |
| plan review R2 / R3 | Opus | high / xhigh |
| resident | Opus | per card: low, medium, high or xhigh |
| analyst | Sonnet | high |
| builder | Sonnet | medium; failures re-run at high |
| builder, mechanical batch | Haiku | medium |
| reviewer R1 / R2 / R3 | Opus | medium / high / xhigh |
| security-reviewer R2 / R3 | Opus | high / xhigh |
| principal | Fable | xhigh; max only on ladder rung 4 |
| debugger | Opus | xhigh |

Rules: effort rises before the model changes, except where risk sets the model. max is never the default for an agentic loop. Sonnet stays at high or below. `CLAUDE_CODE_EFFORT_LEVEL`, `CLAUDE_CODE_SUBAGENT_EFFORT` and `CLAUDE_CODE_SUBAGENT_MODEL(_FORCE)` must stay unset: they override every agent.

Measured in this workspace (feasibility test 6): one Fable-max plan of a small task took 39 minutes and 263K output tokens (about $17 at list price). That is why the default is xhigh, Fable's best measured setting, with max kept for R3 and replans. The planner and principal also keep a one-hour prompt cache (`experimental.cacheTtl: 1h` in their definitions): in that run 38% of the cost was re-writing context after the five-minute cache expired during long steps. On the Max plan, Fable may use up to 50% of the weekly limit at no extra cost. Tierwise keeps a weekly tally of Fable output in `.tierwise/state.json` and warns at `caps.fableWeeklyOutputTokensWarn`. When a planner or principal stops on the Fable limit, the next spawn runs on Opus (max for the planner) and the ledger says so.
