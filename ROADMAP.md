# Roadmap

Tierwise's aim: the quality of the strongest models where it matters, at a fraction of the cost of running them everywhere. These are the next steps; suggestions are welcome as issues.

## Next
- **macOS and Windows.** Tierwise currently supports Ubuntu only. Test and fix on macOS and Windows (the hooks call `python3` and use POSIX paths), then release with support for all three.
- **Build consistency.** Reduce run-to-run variation in build quality: tighter specifications in builder briefs, and an edit-time syntax check so builders never stack changes on a broken file.
- **Research breadth.** Close the remaining gap to all-Fable research on coverage of sources.

## Later
- A larger evaluation: more tasks, more runs per approach, and interactive sessions that exercise the hooks and the check gate.
- User-editable model prices for the savings panel, for when list prices change.
- A routing regression set with a held-out split, so routing rules are tuned without overfitting.
- Behaviour on plans without Fable access, and for API-key users.

## Done
- 1.0.2: fixes and a full account of what runs on your machine.
- 1.0.1: Tierwise never changes Claude Code's settings files.
- 1.0.0: first public release, Ubuntu. See [CHANGELOG.md](CHANGELOG.md).
