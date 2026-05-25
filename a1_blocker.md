# Track-A1 Blocker — RESOLVED (2026-05-25)

## Original blocking condition
Codex agent used the default `python` (Python 3.14) which has broken `vivarium`/`pint`/`numpy`/`jax` deps in this repo.

## Resolution
Use `py -3.12` (Python 3.12.10) which has clean deps. Validated by operator:
- `py -3.12 -m pytest tests/unit -k strict_zero -q` -> 15 passed
- `py -3.12 -m pytest tests/unit -q --ignore=tests/gates` -> 369 passed, 11 skipped, 0 regressions

The A5 agent had already used `py -3.12` and passed 354 tests. Future Track-A delegations to Codex should pin `py -3.12` in the prompt.
