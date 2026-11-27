# Contributing to Tierwise

Thank you for helping. Bug reports, evaluation results from your own projects, and pull requests are all welcome.

## Reporting a problem

Open an issue with:
- what you asked Claude Code to do, and the routing card Tierwise showed;
- what happened and what you expected;
- the relevant lines from `.tierwise/ledger.md` in your project (remove anything private);
- your Claude Code version, operating system and Python version.

Security problems: please follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Making a change

1. Fork the repository and create a branch.
2. Keep the plugin's scripts to the Python 3.8+ standard library and the mod to plain JavaScript.
3. Add or update tests for any behaviour you change.
4. Run everything before opening a pull request:

   ```
   python3 -m unittest discover -s plugins/tierwise/tests
   claude plugin test plugins/tierwise
   claude plugin validate --strict .
   ```

5. Describe what changed and why in the pull request, and add a line to `CHANGELOG.md` under "Unreleased".

## Changing routing or prices

Routing rules (`bin/mlib/route.py`, `templates/tierwise.json`) and prices (`hooks/savings.js`) drive the savings Tierwise reports. A change to either should say what evidence it rests on. If you update the evaluation data, regenerate the charts with `python3 docs/assets/make_charts.py`.

## Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
