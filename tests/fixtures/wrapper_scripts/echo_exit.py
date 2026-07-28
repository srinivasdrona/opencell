"""Fixture for tests/test_wrapper_exit_codes.py.

Exits with the integer status code given as the first CLI argument. Used to
verify that bin\\oc-py.cmd both forwards arguments correctly and propagates
the child Python process's exit code unchanged through to Windows.
"""

import sys

if __name__ == "__main__":
    sys.exit(int(sys.argv[1]))
