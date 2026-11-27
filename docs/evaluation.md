# Tierwise evaluation

How Tierwise compares with running every agent on one model: what was measured, how, and what the results do and do not show. Raw data: [`evals/workflow-arms/evaluation.json`](../evals/workflow-arms/evaluation.json). Charts: [`docs/assets/`](assets/), drawn from that file by [`make_charts.py`](assets/make_charts.py). Interactive version: [`docs/report.html`](report.html).

## The comparison

Three approaches did the same two jobs:

| Approach | Models |
| --- | --- |
| **Tierwise** | Each agent on the model Tierwise routes it to (see below) |
| **All-Opus** | Every agent on Opus |
| **All-Fable** | Every agent on Fable |

**Job 1: research and evaluation.** Four researchers search GitHub, Hugging Face and the literature for capabilities that could improve the plugin; two evaluators then score the findings, verify sources and write integration plans.

**Job 2: build, test, review, fix.** Four builders implement a specified change to the plugin in four units (a syntax check and secret-scan improvements, a gate change, a per-task budget cap, documentation); a test runner runs all suites; a reviewer reviews the whole diff; fixers address blocking findings, at most two rounds.

Tierwise's routing in these jobs:

| Step | Model |
| --- | --- |
| Researchers | Sonnet ×3, Opus ×1 |
| Evaluators | Fable, Opus |
| Builders | Opus (secret and syntax checks), Sonnet (gate), Opus (budget guard), Sonnet (docs) |
| Test runner | Haiku |
| Reviewer and fixer | Opus |

The scripts that ran both jobs are in [`evals/workflow-arms/workflows/`](../evals/workflow-arms/workflows/), with the prompts as run.

## Keeping it fair

- **Identical conditions.** Same scripts, prompts, stages, reasoning effort per agent and review loop for every approach; only the model of each agent differed.
- **Identical starting code.** Every build started from its own byte-identical copy of the same code, checked with a recursive diff before launch.
- **Hidden tests.** A 19-test acceptance suite ([`hidden_acceptance.py`](../evals/workflow-arms/hidden_acceptance.py)), written from the specification and never shown to the builders, scores every build. It fails 17 of 19 on the starting code.
- **Blind judging.** Two judges, one Opus and one Fable so neither model family grades only itself, scored anonymised outputs under shuffled letters, with every model name and folder path removed. They read them in opposite orders and had to verify claims against the code. All outputs of a stage were scored together in one panel, so the scores share a scale.
- **Measured cost.** Every API request is priced by its own model and token type: uncached input, cache reads, 5-minute and 1-hour cache writes, output, at list price. The same method reproduces Claude Code's own cost figures to the cent.
- **Measured time.** Wall-clock time from each run's first model request to its last.

## Results

### Per job

| | Tierwise (avg of 3) | Tierwise runs | All-Opus | All-Fable |
| --- | ---: | --- | ---: | ---: |
| API cost | **$10.66** | $11.39 · $10.63 · $9.97 | $11.44 | $35.34 |
| Minutes | **29.8** | 29.3 · 30.0 · 30.0 | 33.3 | 60.5 |
| Hidden tests passed | **19/19** | 19 · 19 · 19 | 19/19 | 18/19 |
| Research score (of 100) | 83.7 | 86 · 83 · 82 | 83.0 | **91.0** |
| Build score (% of max) | 67.2% | 61.7% · 63.3% · 76.7% | **75.0%** | 60.8% |
| Important build defects found by judges | 3.0 avg | 5 · 4 · 0 | 1 | 4 |

- **Cost:** Tierwise is 70% cheaper than all-Fable (1 − 10.66 / 35.34) and 7% cheaper than all-Opus (1 − 10.66 / 11.44).
- **Time:** 2.0× faster than all-Fable (60.5 / 29.8) and 11% faster than all-Opus.
- **Scores:** a research score is the sum of both judges' scores on accuracy, relevance, actionability, judgement and coverage (each 1–10), out of 100. A build score is the sum of both judges' scores on correctness, robustness, security, tests, maintainability and fit to the specification, as a share of 120.

### Where Tierwise's money goes

Average per job across the three runs: Opus $7.01 (66%), Fable $2.75 (26%), Sonnet $0.89 (8%), Haiku $0.01. The two premium models take 92% of the spend, on the steps that decide quality.

## Savings, worked out

The starting point is one user who spends $200 on API usage for this kind of work without Tierwise. Every figure follows from the measured per-job cost and time above:

| Step | vs all-Fable | vs all-Opus |
| --- | ---: | ---: |
| Jobs in a $200 spend | 200 / 35.34 = 5.6593 | 200 / 11.44 = 17.4825 |
| Tierwise cost of the same jobs | 5.6593 × 10.66 = **$60.33** | 17.4825 × 10.66 = $186.36 |
| Saved per user | **$139.67 (69.8%)** | $13.64 (6.8%) |
| Jobs the $200 pays for with Tierwise | 200 / 10.66 = 18.76 (3.32×) | 18.76 (1.07×) |
| Waiting time, without → with | 5.6593 × 60.5 = 342 min → 5.6593 × 29.8 = 169 min | 17.4825 × 33.3 = 582 min → 17.4825 × 29.8 = 521 min |
| Waiting time saved per user | **173 min = 2 h 53 min (50.6%)** | 61 min (10.5%) |

Each per-user figure is rounded once (to the cent, or the minute), and the scaled figures are exactly that figure times the number of users:

| Projection | 1,000 users | 2,000 users |
| --- | ---: | ---: |
| Saved vs all-Fable | 1,000 × $139.67 = **$139,670** | **$279,340** |
| Waiting time saved vs all-Fable | 1,000 × 173 min = **2,883.3 h** (360.4 working days) | **5,766.7 h** (720.8 working days) |
| Saved vs all-Opus | $13,640 | $27,280 |
| Waiting time saved vs all-Opus | 1,016.7 h (127.1 working days) | 2,033.3 h (254.2 working days) |

Working days are 8 hours. Each user saves their own time; the totals add up time across people.

**What "waiting time" is.** It is how long the user waits for the agents to finish. It is not the sum of every agent's working time, and it does not include time spent writing requests or reviewing results, which was not measured and is assumed to be the same with and without Tierwise.

## What the results show, and what they do not

**Supported by the data:**
- Tierwise did the same work for 70% less than all-Fable and 7% less than all-Opus, in half the time of all-Fable.
- Every Tierwise build passed all 19 hidden tests; all-Fable passed 18.
- Tierwise's research scored level with all-Opus.
- Tierwise's builds scored above all-Fable on average, each run at or above it.
- The top-scoring build in the panel was a Tierwise run: first with the Opus judge, second with the Fable judge, no important defects.

**Not supported, or still a gap:**
- Tierwise's research scored below all-Fable (83.7 vs 91.0), mainly on breadth of sources.
- Tierwise's build quality varied between runs. Two of the three scored below all-Opus, with 5 and 4 important defects between the two judges, mostly in how the secret scan reads its settings. Tierwise is not equal to all-Opus on every build.

**Limits of the evaluation:**
- Three Tierwise runs and one run each of all-Opus and all-Fable is a small sample.
- The evaluation ran on Linux with Claude Code 2.1.332. Tierwise 1.0.0 is supported on Ubuntu.
- All-Opus and all-Fable ran on 26 November 2026, Tierwise on 27 November, with the same scripts and prompts.
- The judging panel held six outputs per stage: the five here, plus one from an earlier Tierwise configuration (not reported).
- These runs measure Tierwise's model routing in multi-agent workflows. They do not exercise the plugin's hooks or check gate in an interactive session.
- The judges are models too.
- The savings projections assume users' work resembles the measured jobs.
- Costs are list-price equivalents. On a subscription they are usage of the plan's limits, not a bill.

## Reproducing

- [`evals/workflow-arms/evaluation.json`](../evals/workflow-arms/evaluation.json): every measured figure above, per run and per approach.
- [`docs/assets/make_charts.py`](assets/make_charts.py): redraws every chart and prints the savings arithmetic from that file.
- [`evals/workflow-arms/hidden_acceptance.py`](../evals/workflow-arms/hidden_acceptance.py) `<plugin dir>`: the hidden test suite.
- [`evals/workflow-arms/workflows/`](../evals/workflow-arms/workflows/): the two Claude Code workflow scripts, runnable with the Workflow tool against your own copy of the starting code.
- [`evals/run_pilot.py`](../evals/run_pilot.py): a separate small-task harness that runs Claude Code headless, with and without Tierwise, on three tasks with hidden tests.
