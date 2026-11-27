# Handoff reference

| Artifact | Written by | Read by | Size |
| --- | --- | --- | --- |
| `.tierwise/state.json` | hooks and scripts only | hooks, resident | small |
| `.tierwise/ledger.md` | hooks; resident (`state ledger`) | resident after compaction; the user | 1–3 lines per event |
| `.tierwise/decisions.md` | resident; principal (`state decision`) | every planner and reviewer | a few lines per decision |
| `.tierwise/briefs/<unit>.md` | resident | the delegate | ≤ 500 words |
| `.tierwise/reports/<unit>.md` | the delegate | resident, on demand | unbounded |
| hand-back report | the delegate | resident | ≤ 150 words, fixed fields |
| review package | `bin/review-package` | reviewers | diff + spec + checks, no author reasoning |
| failure dossier | resident | debugger, principal | ≈ 400 words + pointers |

Templates for the brief, plan, report and dossier are in the plugin's `templates/` folder.

What a delegate gets without being told: its own prompt, your task message, the project's CLAUDE.md files (scout opts out), and a git status snapshot. Nothing else: write down what it needs, once, and point to it.

`.tierwise/` is kept out of git through `.git/info/exclude`; no tracked file is changed.
