#!/usr/bin/env bash
# OpenCell bootstrap — run from inside WSL, from the repo root.
#
# What this does:
#   1. Creates and activates .venv-wsl (Python 3.12)
#   2. Installs the project in editable mode with dev+viz+oracle extras
#   3. Fetches upstream Karr 2012 sources into data/m1_sources/
#   4. Runs the M1 fixture validator + the pytest suite
#
# What this does NOT do:
#   - Install MATLAB (only needed for fixture re-extraction; see BOOTSTRAP.md §6)
#   - Restore agent session-state from another machine (see BOOTSTRAP.md final §)
#   - Restore the PM OS files (those come from OneDrive sync)
#
# Usage:
#   wsl -e bash -lc "cd /mnt/e/opencell && ./scripts/bootstrap.sh"

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
echo "==> Bootstrapping OpenCell at: $REPO_ROOT"

# --- 1. Python venv ---------------------------------------------------------
if [[ ! -d ".venv-wsl" ]]; then
    echo "==> Creating .venv-wsl"
    python3 -m venv .venv-wsl
else
    echo "==> .venv-wsl already exists, reusing"
fi

# shellcheck disable=SC1091
source .venv-wsl/bin/activate

PYVER="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$PYVER" in
    3.12|3.13) echo "==> Python $PYVER OK" ;;
    *) echo "ERROR: Python $PYVER detected; project requires >=3.12,<3.14" >&2; exit 1 ;;
esac

echo "==> Upgrading pip"
pip install --quiet --upgrade pip

echo "==> Installing opencell with dev+viz+oracle extras (this may take 5-10 minutes)"
pip install --quiet -e ".[dev,viz,oracle]"

# --- 2. Upstream Karr sources -----------------------------------------------
mkdir -p data/m1_sources

clone_if_missing() {
    local url="$1"
    local dest="$2"
    if [[ -d "$dest/.git" ]]; then
        echo "==> $dest already cloned, skipping"
    else
        echo "==> Cloning $url -> $dest"
        git clone --quiet "$url" "$dest"
    fi
}

clone_if_missing https://github.com/CovertLab/WholeCell   data/m1_sources/WholeCell
clone_if_missing https://github.com/CovertLab/WholeCellKB data/m1_sources/WholeCellKB

# --- 3. Validate fixtures ---------------------------------------------------
echo "==> Validating M1 per-process fixtures"
if python scripts/validate_per_process_fixtures.py; then
    echo "==> Fixture validation passed"
else
    echo "WARNING: fixture validation reported mismatches; inspect output above" >&2
fi

# --- 4. Run the test suite --------------------------------------------------
echo "==> Running tests/m1/ (fast subset)"
pytest tests/m1/ -q --no-header

echo "==> Running full test suite (this is the real correctness gate)"
pytest -q --no-header || {
    echo "WARNING: some tests failed; expected baseline is ~578 pass / ~11 skip / ~4 xfail" >&2
    echo "Compare against 'tests baseline' in plan.md before treating this as a regression." >&2
}

# --- 5. Done ----------------------------------------------------------------
cat <<'EOF'

==============================================================================
Bootstrap complete.

Next steps:
  - Read plan.md and SESSION_CONTEXT.md to see where work stands
  - sqlite3 opencell_tasks.db "SELECT id,title FROM todos WHERE status='pending'"
  - For fixture re-extraction (optional, MATLAB required):
      see BOOTSTRAP.md §6

Activate the env in future shells with:
  source .venv-wsl/bin/activate
==============================================================================
EOF
