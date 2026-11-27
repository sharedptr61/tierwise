---
name: debt
description: List every shortcut a developer or agent knowingly took, from `shortcut:` comments in the code, with each one's limit and the trigger for revisiting it. The user runs /tierwise:debt; it changes nothing.
disable-model-invocation: true
---

# Shortcut ledger

1. Find the markers, respecting `.gitignore`:
   `git grep -nE '(#|//|/\*|--) ?shortcut:'` (also accept a marker word the user names, such as `TODO`).
2. For each, one row grouped by file: `<file>:<line> - <what was simplified>. limit: <the limit>. upgrade when: <trigger>.`
3. A marker that names no trigger gets `no-trigger`: those are the ones that rot.
4. End with `<N> shortcuts, <M> without a trigger.` or `No shortcuts recorded.`

Write the list to a file only if the user asks.
