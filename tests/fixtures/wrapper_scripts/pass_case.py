"""Fixture for tests/test_wrapper_exit_codes.py.

A single passing test, used to verify that bin\\oc-pytest.cmd reports exit
code 0 for a clean run (not just "any nonzero code got swallowed").
"""


def test_deliberately_passes() -> None:
    assert True


# NOTE: this file is intentionally named `pass_case.py` (not `test_*.py`) so
# that it is never auto-collected by a bare `pytest`/`oc-pytest tests` run
# (testpaths = ["tests"] in pyproject.toml). It is only ever invoked by
# explicitly naming its path, e.g. `oc-pytest tests/fixtures/wrapper_scripts/pass_case.py`.
