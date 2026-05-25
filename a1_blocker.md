# Track-A1 Blocker

## Blocking condition
I completed the strict-zero code/test changes and the strict-zero test pack passes, but the required broader validation runs are blocked by environment dependency incompatibilities:

- `pytest tests/unit -v` fails during collection because `jax` is not installed (`ModuleNotFoundError: No module named 'jax'`).
- `vivarium` import path fails against the installed `pint`/`numpy`/Python 3.14 combination (examples include `numpy` lacking `cumproduct`, missing `pint.quantity`/`pint.unit`, and `pint` dataclass initialization errors).
- The 10-tick chassis smoke run fails at import time for the same `vivarium`/`pint` incompatibility.

## Unblocking question
Can you provide (or allow me to install) a test-compatible environment matching the project’s expected matrix (for example Python 3.11 with compatible `numpy`/`pint` and `jax`) so I can run the full unit suite and chassis 10-tick smoke exactly as mandated?
