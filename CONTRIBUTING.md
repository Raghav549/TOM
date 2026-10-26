# Contributing to TOM

Thanks for helping make TOM a more useful, safe, local-first agent runtime.

## Before you start

- Search existing issues before opening a new one.
- For substantial changes, open an issue first so we can align on the problem and approach.
- Keep changes focused. Separate refactors from behaviour changes whenever possible.
- Never add secrets, tokens, private data, or generated model assets to the repository.

## Development setup

TOM requires Python 3.11 or newer.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run the quality checks before sending a pull request:

```bash
ruff check .
pytest -q
python scripts/validate_production.py
```

Optional capabilities have their own extras. See [Quickstart.md](Quickstart.md) for browser, voice, Android, and model-provider setup.

## What makes a good contribution

- Describe the user-facing problem and the intended behaviour.
- Preserve TOM's approval gates, permission checks, and truthful capability reporting.
- Add or update tests when behaviour changes.
- Document configuration, availability, and any safety constraints.
- Avoid claiming an integration or verifier works unless it is actually configured and tested.

## Pull requests

1. Create a branch from `main`.
2. Make one coherent change.
3. Run the checks above.
4. Explain what changed, how it was tested, and any remaining limitations.
5. Use the pull-request template and respond to review feedback.

By contributing, you agree that your contributions may be distributed under the repository's [Apache-2.0 license](LICENSE).
