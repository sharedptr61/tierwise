# Security policy

## Reporting a vulnerability

Please report security problems privately by email to **onur.aktastr@gmail.com**, not through a public issue. Include what you found, how to reproduce it, and its impact. You will get an acknowledgement within 7 days and a plan for a fix once the report is confirmed.

## What is in scope

Tierwise runs on your machine with your permissions:
- **Hooks** (`plugins/tierwise/hooks/hooks.json`) run Python scripts from `plugins/tierwise/bin/` at prompt, tool-use and stop events.
- **The mod** (`plugins/tierwise/hooks/register.js`) runs in Claude Code's process once you approve it.
- **Checks** run the commands configured in your project's `.claude/tierwise.json`.

Reports about any of these are in scope: a way to make Tierwise run unintended commands, write outside the project, leak data, or let a check pass that should fail (for example, a secret the scan should catch).

## Supported versions

Security fixes go into the latest release.
