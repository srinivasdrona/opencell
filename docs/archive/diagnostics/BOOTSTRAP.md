# Bootstrapping OpenCell on a Fresh Machine

This guide gets a fresh Windows + WSL machine from `git clone` to passing
test suite, ready to resume development.

For automated setup, run [`scripts/bootstrap.sh`](scripts/bootstrap.sh)
inside WSL after cloning.

---

## ⚠️ DO NOT run Python from PowerShell — use WSL

This project's hard rule (see `.github/copilot-instructions.md` →
"Execution Environment: WSL is the Source of Truth"): all Python,
pytest, and script execution happens **inside WSL**, never from a
PowerShell prompt.

The Windows-side venv is incidental and will silently break things
because the oracle stack (`libroadrunner`, `tellurium`, `pysces`) is
Linux-only. Symptoms of a wrong-venv invocation include:

- `ModuleNotFoundError: No module named 'vivarium.core'` (or similar)
  even though the package is listed in `pyproject.toml`
- `pytest` summary showing `skipped > 5` — the expected skip count for
  a correctly-run suite is **exactly 5** (Thattai paper-cache tests).
  Any other number means you're on the wrong environment.

**Correct invocation pattern:**

```powershell
wsl -e bash -lc "cd /mnt/<drive>/opencell && source .venv-wsl/bin/activate && <command>"
```

**Wrong invocation pattern (will fail or silently mislead):**

```powershell
D:\opencell\venvs\opencell\Scripts\python.exe -m pytest tests\m1
```

If you don't have WSL yet, install it first (`wsl --install -d Ubuntu`,
then reboot) before proceeding past §2.

---

## 0. Prerequisites

| Component | Version | Notes |
|---|---|---|
| Windows 11 | — | WSL2 enabled |
| WSL (Ubuntu) | 22.04+ | All Python execution lives here |
| Python (inside WSL) | 3.12.x | `requires-python = ">=3.12,<3.14"` in `pyproject.toml` |
| Git | any recent | Configured with your GitHub credentials |
| MATLAB R2026a (Windows) | optional | Only needed to **re-extract** per-process fixtures from raw MCOS classes. Existing fixtures in `data/karr_fixtures/per_process/` are already committed. |

---

## 1. Clone

```bash
# In WSL, under /mnt/<drive>/<path>/ that's also accessible from Windows
git clone https://github.com/srinivasdrona/opencell.git
cd opencell
```

## 2. Python environment (WSL is the source of truth)

Per [`.github/copilot-instructions.md`](.github/copilot-instructions.md),
all execution happens in WSL. The Windows venv is incidental.

```bash
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install --upgrade pip
pip install -e ".[dev,viz,oracle]"
```

Notes:
- `oracle` extra pulls `libroadrunner`, `tellurium`, `pysces` — these are
  **Linux-only** in our stack. Do NOT try to install them in a Windows venv.
- Install can take 5-10 minutes on first run (JAX, diffrax, libroadrunner
  wheels are heavy).

## 3. Upstream sources (M1 ingestion path)

The `data/m1_sources/` directory is gitignored — it holds upstream Karr 2012
artifacts. Re-fetch:

```bash
git clone https://github.com/CovertLab/WholeCell   data/m1_sources/WholeCell
git clone https://github.com/CovertLab/WholeCellKB data/m1_sources/WholeCellKB
```

Pin to the commits documented in `docs/phase5/M1_sourced_inventory.md` if
you need byte-identical reproducibility:
- `WholeCell` @ `6cdee6b`
- `WholeCellKB` @ `10a9798`

## 4. Sanity-check

```bash
# All from inside the activated .venv-wsl
pytest tests/m1/ -q                  # expect: 70 passed
pytest -q                            # expect: ~578 passed, ~11 skipped, ~4 xfailed
                                     #   skipped should be exactly 5 if Thattai
                                     #   paper-cache tests are excluded
python scripts/validate_per_process_fixtures.py
                                     # expect: 89 files, 0 mismatched
```

If `pytest` reports more than ~11 skips, you're likely on a venv that's
missing `libroadrunner`. See [§Execution Environment](.github/copilot-instructions.md)
in the agent instructions for diagnostics.

## 5. Resume work

```bash
# Read the canonical state
less plan.md                              # current phase, BLOCKERs, next steps
less SESSION_CONTEXT.md                   # human-readable session log

# Inspect open todos
sqlite3 opencell_tasks.db                                                      \
    "SELECT id, title, status FROM todos WHERE status='pending' ORDER BY id"
```

Install the Copilot LLM-log pre-commit guard:

```bash
ln -sf ../../scripts/hooks/check_llm_log_on_commit.py .git/hooks/pre-commit
```

Recent agent-session checkpoints (decision history, technical context) live
**outside the repo** in `~/.copilot/session-state/<session-id>/checkpoints/`
on the original machine. On a fresh machine these are not available unless
explicitly archived. Prior decisions are summarised in `SESSION_CONTEXT.md`
and `decisions/` — those are sufficient to pick up the work, just not the
full conversational provenance.

## 6. Optional: MATLAB extraction path

Only needed if you want to **regenerate** the per-process MCOS fixtures
from scratch (e.g., to add new processes, or to validate the existing flat
extraction).

```powershell
# From Windows PowerShell
& "E:\MATLAB\bin\matlab.exe" -batch `
    "addpath('E:\opencell\scripts\matlab'); extract_per_process_fixtures"
```

Then in WSL:

```bash
python scripts/extract_per_process_fixtures.py --all --from-flat
```

See `scripts/matlab/README.md` for the full handle-cycle-cut walker design
notes (the bug class that ate two debugging sessions before naming).

---

## What is NOT recoverable from this repo alone

| Item | Where it lives | Why it matters |
|---|---|---|
| `~/.copilot/session-state/<id>/` | Machine-local `%USERPROFILE%\.copilot\` | Full agent conversation history, checkpoint summaries. Lost on a new machine unless archived. |
| PM OS files (`PREFERENCES.md`, `DECISIONS.md`, `INBOX.md`) | `$env:OneDrive\.pm-os\` | Cross-project operator state. Recovered automatically via OneDrive sign-in. |
| MATLAB R2026a license | Per-machine | Required only for fixture re-extraction (see §6). |
| `notebooks/` (local scratch) | Not tracked | Lost unless you back it up out-of-band. |

For a more complete provenance trail (and to address gap #1 from the
LLM-research practice critique), consider periodically syncing
`~/.copilot/session-state/<id>/checkpoints/` into `docs/agent_checkpoints/`
on this repo.
