# Project security rules

Read by the security-guidance plugin's reviews and by Tierwise's security-reviewer. Copy to `.claude/claude-security-guidance.md` and edit.

## Trust boundaries

- <e.g. Public HTTP API under `api/`; authenticated with session cookies.>

## Assets to protect

- <e.g. User records in `db/users`, payment tokens, API keys in the environment.>

## Project rules

- <e.g. All SQL goes through the query builder; no string-built SQL.>
- <e.g. File paths from requests are resolved under `UPLOAD_ROOT` and checked.>
- <e.g. Secrets come from the environment, never from files in the repository.>

## Accepted risks

- <Known findings the team has accepted, with the reason, so reviews do not re-raise them.>
