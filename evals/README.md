# Tierwise evaluations

Two harnesses. The head-to-head evaluation reported in the README and in [docs/evaluation.md](../docs/evaluation.md) lives in [`workflow-arms/`](workflow-arms/): its measured data ([`evaluation.json`](workflow-arms/evaluation.json)), the hidden acceptance suite and the workflow scripts. This page describes the second, a small-task harness for running Tierwise against single-model Claude Code on your own machine.

## Tasks

Each task is a small Python repository (standard library only), a prompt, and hidden acceptance tests the agent never sees.

| Task | Kind | What the hidden tests check |
| --- | --- | --- |
| `shop-export` | Medium feature | CSV export: header and row order, two-decimal amounts, commas / quotes / line breaks that round-trip, spreadsheet formula injection neutralised, a total that excludes cancelled orders, exit codes, the existing report unchanged (8 tests) |
| `pricing-stale` | Bug with a misleading symptom | The report blames the cache's ten-minute TTL; the real cause is that a price change clears only the US-dollar cache entry. The tests require the fix in every currency and reject the lazy fixes: disabling the cache, clearing all of it, or shortening the TTL (5 tests) |
| `notify-config` | Refactor across four modules | A global settings dictionary becomes a frozen `Config` passed explicitly; behaviour pinned exactly (truncation, retries, dry run, the command line), the old module gone, no global state left (8 tests) |

Each task has a reference solution in `reference/`. `check_task.sh <task dir>` proves the hidden tests: they must fail on the untouched repository and pass with the reference. All three do.

## Running

```
python3 evals/run_pilot.py                            # 3 tasks, Tierwise vs all-Fable, one run each
python3 evals/run_pilot.py --arms opus,fable,tierwise  # add an all-Opus side
python3 evals/run_pilot.py --runs 3 --jobs 3          # three runs each, for a firmer comparison
```

Sides: `fable` and `opus` run Claude Code on that model for the whole task without Tierwise; `tierwise` runs Claude Code on Opus with Tierwise loaded. Plugins synced from your claude.ai account are switched off in each run's own project settings, so both sides run in the same plain environment. Every run starts from a fresh git copy of the task repository with the same prompt.

Output in `evals/results/<name>/`: `summary.md`, `results.json` (cost and tokens per model, minutes, hidden and own tests, the final answer, Tierwise's ledger), one diff per run, and a blind review packet.

## Judging quality

1. **Hidden tests** are the main score: they encode the requirements and the traps.
2. **Blind review:** `blind/<task>/A.diff`, `B.diff`, ... are the sides' changes in random order; `blind/key.json` says which is which. Read the diffs, write down which is better and why, then open the key.
3. **Cost** is Claude Code's own list-price figure for the run. On a subscription it is usage of your plan's limits, not a bill.

Single runs vary; treat one run per side as a pilot, not a benchmark.
