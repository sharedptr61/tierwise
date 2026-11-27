---
name: compress-memory
description: Shorten a project memory file such as CLAUDE.md so it costs fewer tokens on every request, keeping every instruction and exact value. The user runs /tierwise:compress-memory <path>. Done in this session; nothing is sent anywhere else.
disable-model-invocation: true
---

# Compress a memory file

Only for a prose file the user names (`.md`, `.txt`, or an extensionless rules file), never for code or configuration.

1. Copy the original to `.tierwise/backups/<name>.<date>.md` first, and say where.
2. Rewrite the prose shorter: drop filler, hedging and repetition, merge duplicate bullets, keep one example per pattern, prefer imperative sentences.
3. Keep exactly as they are: code blocks and inline code, commands, paths, URLs, names, versions, numbers, environment variables, headings, list nesting, tables and frontmatter. Keep every rule; a rule may get shorter, never weaker.
4. Show the user the size before and after (characters) and the three most important cuts, then write the file.
5. If any instruction became ambiguous, restore that passage from the backup.

Tell the user how to restore the backup.
