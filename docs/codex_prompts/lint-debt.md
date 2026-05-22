# Lint debt cleanup

Clear the 1101 pre-existing ruff errors. Bring CI from advisory to strict.

## CRITICAL: WSL venv ONLY

```
wsl -e bash -lc "cd /mnt/e/opencell-worktrees/lint-debt && /mnt/e/opencell/.venv-wsl/bin/ruff check ."
wsl -e bash -lc "cd /mnt/e/opencell-worktrees/lint-debt && /mnt/e/opencell/.venv-wsl/bin/pytest tests/ -q"
```

## Standard preamble
Overwrite STATUS.md with "Lint debt cleanup started at <timestamp>" as first action.

## Approach

1. `ruff check . --fix --unsafe-fixes` — gets most auto-fixable issues (ANN201, ANN001, I-imports).
2. `ruff check .` again to see what remains.
3. For remaining: add explicit annotations; use `# noqa: <rule>` for justified exceptions; format with `ruff format .`.
4. Real bugs (B-series, F-series): triage; fix if clearly a bug.
5. Update `pyproject.toml` to remove advisory-mode override (lint becomes strict).
6. Run `pytest tests/ -q`: confirm no behavioral change (same test count + same SKIP/xfail).

## Constraints

- DO NOT change docstrings, variable/function names, or test behavior
- Make 2-5 small commits grouped by rule category (annotations, imports, format, real-bugs)

## Acceptance

- `ruff check .` clean
- `pytest tests/ -q` unchanged from baseline
- CI strict in pyproject
- STATUS reports: starting → ending error counts, # noqa markers added, files touched
- Final commit: `lint: clear 1101 pre-existing ruff errors; CI now strict`

Time-box: 60 min.
