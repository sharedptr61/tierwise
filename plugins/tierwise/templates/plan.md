# <Task name> plan

> Task `<task-id>` · class `<class>` · tier `<R0–R3>` · planner `<model, effort>` · <date>
> Spec: `<path to the spec or design>` · Context pack: `.tierwise/reports/context-<task>.md`

**Goal.** What "done" means, as checks someone can run.

**Approach.** The design in a few sentences: what changes, what is reused, what is deliberately not done.

**Global constraints.** Project-wide requirements from the spec, with exact values. Every unit respects them.

**Review focus.** The five inputs most likely to break this change, each pinned by a test in the unit that owns it.

## Decisions to confirm

Choices the user must make before implementation, recommended option first. Empty if none.

## Risks

R2+: concurrency, interface and dependency risks.

## Threat model (R3 only)

STRIDE per new or changed trust boundary (spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege), each with its mitigation and the test or check that proves it. Rollback plan. Irreversible steps, each marked **sign-off required**.

## File map

| File | Create / modify | Responsibility |
| --- | --- | --- |

## Units

### Unit 1: <name>

- **Route:** resident | builder | builder(haiku) | builder(opus)
- **Files:** create `path/a.py`; modify `path/b.py:40-80`; test `tests/test_a.py` (no other parallel unit touches these)
- **Interfaces:** consumes `<signature from unit N>`; produces `<exact signature>`
- **Behaviour:** what it does, including edge cases
- **Tests:** `test_name`: what it asserts (written first)
- **Steps:** write the failing test → run `<command>` (Expected: `<failure>`) → implement → run `<command>` (Expected: `<pass>`)
- **Acceptance:** commands that must pass
- **Checks:** unit, sast
- **Security:** what this unit must not allow

### Unit 2: …

## Order

Which units run in parallel, which in sequence, and where the main session integrates.

<!-- Under about 400 lines. Code only where an exact snippet is the spec (a regex, a schema, a migration step). -->
