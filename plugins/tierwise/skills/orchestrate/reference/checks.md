# Checks reference

Models write tests, triage findings and review. They never decide whether a check passed: scripts do.

## Configuration: `.claude/tierwise.json`

Written by auto-detection on the first code-changing prompt in a repository (`"confirmed": false`); show it to the user once and set `"confirmed": true`. Each check id maps to a shell command run from the repository root, or `null` when no tool exists.

| Id | Runs when | Typical command |
| --- | --- | --- |
| syntax | code or config changed | built-in parse of changed `.py`, `.json`, `.toml` (Python 3.11+) and `.js` files (needs node); runs first |
| secrets | every change | built-in scan of added lines, always on |
| affected | code or tests changed, when configured | fast run of the tests the change touches; the command reads `TIERWISE_CHANGED_FILES` (newline-separated paths) |
| unit | code or tests changed | `python3 -m pytest -q -x`, `npm test`, `go test ./...`, `cargo test` |
| typecheck, lint | code changed and configured | `tsc --noEmit`, `mypy .`, `ruff check .`, `go vet ./...` |
| docs | docs-only change | `markdownlint` |
| sca | manifest or lockfile changed | `pip-audit`, `npm audit`, `govulncheck`, `cargo audit` |
| sast | R2/R3 code change | `semgrep scan --metrics off --config .semgrep.yml --error`, only with the project's own Semgrep config (never the online registry) |
| iac | IaC, Dockerfile, CI config changed | `checkov`, `hadolint` |
| migration | migration files changed | your up/down/rollback script on a scratch database |
| race | investigation or high-risk task | `go test -race ./...` |
| mutation | R3 code, when configured | `mutmut run`, `stryker run` |

A plan adds checks with a `Checks:` line per unit. A check with no command is reported as MISSING in the gate's message and the ledger, never skipped silently. Ask the user before installing a scanner.

**Syntax and affected** fail fast: after either fails, the other non-security checks are reported as SKIPPED ("an earlier check failed") and run on the next pass. Secrets, sast, sca and iac still run. A skipped check is not a pass.

**Secret scan.** Built-in, always on, over added lines only. Provider token patterns match as they are; generic assignments (`key = "..."`) must also pass an entropy filter and are ignored when the value looks like a placeholder. Add rules and allowances in `.claude/tierwise.json`, in Gitleaks' rule form:

```json
"secrets": {
  "rules": [{"id": "acme-key", "regex": "acme_[a-z0-9]{24}", "minEntropy": 3.5}],
  "allow": {"paths": ["tests/fixtures/**"], "regexes": ["acme_FAKE"]}
}
```

An allow regex is tested against the matched secret only, never the rest of the line, and every match on a line is checked: a placeholder early on a line cannot hide a real key after it, and a comment cannot allowlist one. A bad rule, regex or `minEntropy` (it must be a finite number, 0 or more) is reported as a config error in the result, not ignored. A check that crashes is reported as a failed check with the error, never as a pass.

**Syntax exclusions.** The syntax check cannot be switched off, but it can be told to leave files alone, for files that are valid for the project's own tools: test fixtures that are broken on purpose, generated code, syntax newer than the hook's `python3`. `.js` files that node rejects only because they contain JSX are skipped automatically, and `tsconfig*.json`, `jsconfig*.json`, `.vscode/` and `devcontainer.json` files may contain comments.

```json
"syntax": {"exclude": ["tests/fixtures/**", "src/generated/**"]}
```

**Task budget.** `caps.taskBudgetUsd` (list-price equivalent; usage of your limits on a subscription): once the task's measured cost reaches it, the guard refuses new planner, principal and debugger spawns and asks the user to continue or stop. Scouts, analysts, builders and reviewers still run. It needs the mod, which measures the usage.

**Ladder audit.** Each climb is one ledger line: `ladder: task <id> rung <a> -> <b> on <checks>: <action>`, followed by the gate line. Syntax and secrets failures do not climb the ladder.

## Scripts

- `select-checks`: the checks the current change needs, as JSON.
- `run-checks [--only a,b]`: run them now; digest on stdout, full logs in `.tierwise/reports/checks/<time>/`.
- `run-checks --gate`: the Stop hook. Defers while Tierwise agents still run in the background; blocks while checks fail (with the ladder rung) or required reviews are missing; gives up after `caps.gateBlocksPerTask` blocks or rung 5 and tells the user.
- `red-green --cmd "<cmd>" --tests <files>`: the regression test must fail on the task base and pass now.

## Tests by kind of change

Bug fix: a regression test proven with red-green. New behaviour: unit tests, plus an integration test at each new boundary. Public interface: contract or integration tests plus the callers' tests. Parsing or serialization: property or fuzz tests. Concurrency: a race detector or stress run. Migration: up, down, rollback on a scratch database with row counts. UI: component tests and a screenshot check. Hot path: a benchmark against the base. R3: all that apply, plus mutation testing where a tool exists.
