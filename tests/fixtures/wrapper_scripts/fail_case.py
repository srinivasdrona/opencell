"""Fixture for tests/test_wrapper_exit_codes.py.

A single deliberately-failing test, used to verify that bin\\oc-pytest.cmd
propagates pytest's real (nonzero, "tests failed") exit code rather than
always reporting success.
"""


def test_deliberately_fails() -> None:
    raise AssertionError("intentional failure fixture for wrapper exit-code tests")


# NOTE: this file is intentionally named `fail_case.py` (not `test_*.py`) so
# that it is never auto-collected by a bare `pytest`/`oc-pytest tests` run
# (testpaths = ["tests"] in pyproject.toml). It is only ever invoked by
# explicitly naming its path, e.g. `oc-pytest tests/fixtures/wrapper_scripts/fail_case.py`.
