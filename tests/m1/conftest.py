from __future__ import annotations

import sys
from pathlib import Path

# Ensure `opencell` resolves to THIS worktree's local package, not whatever
# is currently checked out in the main repo the shared WSL venv's editable
# install points at (see tests/unit/conftest.py for the repo-wide precedent
# of this exact pattern, and bin/oc-py.cmd's docstring for why the editable
# install is shared across worktrees). Without this, tests in this directory
# would silently import and exercise a DIFFERENT, uncontrolled copy of
# `opencell.m1.fva` -- verified empirically 2026-07-29 while validating the
# L2.2 FVA performance fix: plain `python`/pytest runs of tests/m1/test_fva.py
# resolved `opencell.m1.fva.__file__` to `/mnt/e/opencell/opencell/m1/fva.py`
# (the main checkout) instead of this worktree's modified copy.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for module_name in list(sys.modules):
            if module_name == "opencell" or module_name.startswith("opencell."):
                del sys.modules[module_name]
