# Changelog

All notable changes to Tierwise are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-11-27

### Changed
- Tierwise never changes Claude Code's settings files. It used to set `SECURITY_REVIEW_MODEL` in a project's `.claude/settings.local.json` when security-guidance was installed; it now suggests the setting once, for you to add.
- The README lists everything Tierwise writes and stores in a project.

## [1.0.0] - 2026-11-27

First public release.

### Added
- Per-prompt routing card: task class, risk tier R0–R3, plan decision, effort, agents, tests and security checks.
- Eight pinned-model agents: planner and principal (Fable), reviewer, security reviewer and debugger (Opus), builder and analyst (Sonnet), scout (Haiku).
- Spawn guard: model and effort policy, review effort floors by risk, escalation caps, nothing below Opus for high-risk code, research and judgement kept off Haiku, a per-task usage cap.
- Completion gate: built-in syntax check and secret scan (entropy filter, custom rules, allowlist), the project's tests, type checks, dependency and static analysis where configured; a debugging ladder that escalates only on a repeated failure; an audit line in the ledger for every escalation.
- Cost measurement for every request, a status line and the `/tierwise-savings` panel against all-Opus and all-Fable estimates.
- Process skills written for Tierwise: brainstorm, test-driven development, root-cause debugging, plan execution, finishing a branch, plus terse replies, commit messages, a shortcut ledger and CLAUDE.md compression on request.
- Evaluation against all-Opus and all-Fable with hidden acceptance tests and blind judging (`docs/evaluation.md`).

### Platform
- Supported on Ubuntu 22.04 and 24.04 LTS, tested in CI with Python 3.8, 3.10 and 3.12. Developed with Claude Code 2.1.332.
- macOS and Windows are not supported in this release.

[1.0.1]: https://github.com/sharedptr61/tierwise/releases/tag/v1.0.1
[1.0.0]: https://github.com/sharedptr61/tierwise/releases/tag/v1.0.0
