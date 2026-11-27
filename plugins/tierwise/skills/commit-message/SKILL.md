---
name: commit-message
description: Write a commit message for the staged change in Conventional Commits form. The user runs /tierwise:commit-message; it outputs the message and does not commit.
disable-model-invocation: true
---

# Commit message

Read the staged diff (`git diff --cached`), then output one message in a code block. Do not run `git commit`.

- Subject: `type(scope): imperative summary`, types `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`, `revert`. Aim for 50 characters, never over 72, no full stop.
- Body only when the reason is not obvious, for a breaking change, a migration, a security fix or a revert (those always get one). Wrap at 72 columns; bullets with `-`.
- `BREAKING CHANGE:` footer when callers must change; issue references in the footer.
- Never "this commit", "I" or "we", emoji, or an AI attribution line unless the project's rules ask for a trailer.
