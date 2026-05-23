# OpenCell — Shared Codex Session Context (2026-05-23)

## Project at a glance
Python whole-cell simulation of *Mycoplasma genitalium* — a port of Karr 2012's
MATLAB whole-cell model onto `vivarium-core`. Repo: `E:\opencell` (main).

## Today's mission (2026-05-23)
**Ship Phase C (10 Karr processes covering DNA replication + cell cycle), then
start Phase D (HostInteraction → chassis_v6 = all 28 processes integrated).**
Phases A3.3 + B already shipped yesterday (17 of 28 processes). pc-t1
ReplicationInitiation already shipped on main at `karr_replication_initiation.py`.

## Hard rules (non-negotiable)

### 1. Karr-fidelity is the prime directive
Every algorithm choice must trace to:
- Karr 2012 MATLAB source at `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/<Process>.m`
- Karr extract at `docs/karr_extracts/process/<NN>_<Process>.md` (verbatim docstring + mapping notes — trust the verbatim section, spot-check the mapping notes)
- Per-process bit-identical trace at `data/m1_sources/karr_native/per_process_traces/<Process>_100ticks.mat` (gold-standard validation data)
Do NOT invent biology. If a docstring is silent, document the gap, don't guess.

### 2. WSL venv ONLY for Python
The repo uses an editable install in `.venv-wsl`. All Python commands MUST be:
```
wsl -e bash -lc "/mnt/e/opencell/.venv-wsl/bin/python ..."
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest ..."
```
Windows-side `py -3.12` or `python` will fail with ModuleNotFoundError on the
project's own package. Do NOT try to "fix" this — switch interpreters.

### 3. Vivarium accumulate-only rule
Every per-tick writer in OpenCell chassis MUST use `_updater: "accumulate"` and
emit DELTAS (not absolute values). Mixed `set`+`accumulate` on the same leaf is
broken (order-sensitive — last-declared updater wins, probe-tested 2026-05-22).
Decision logged as `vivarium-all-accumulate-no-set`.
Exception: long-lived discrete state machines (e.g., `replication_state` = "idle"/"elongating"/"complete") may use `_updater: "set"` because no other writer
touches them. When in doubt, prefer accumulate.

### 4. KarrAllocationStep contract
If your process consumes shared substrates (ATP, GTP, NTPs, AAs, etc.):
- Write a `requests.<process_name>.<substrate_id>` value at tick start
- Read your `substrates_allocated.<process_name>.<substrate_id>` allocation
- Apply your action bounded by what was allocated
- Emit your accumulate-delta on `substrates.<substrate_id>` (negative for consumption)
See `opencell/vivarium/karr_allocation_step.py` + `karr_protein_decay_light.py`
for the pattern. The pc-t1 file `karr_replication_initiation.py` shows the full
shape for a Phase C process.

### 5. Commit-or-STATUS on every exit
NEVER exit without writing STATUS.md. If you got stuck — say so, with the
specific error and what you tried. A partial STATUS is always better than none.

### 6. No regressions
Before commit, run the FULL test suite via WSL pytest. Phase A+B+C-T1 must
remain green (~720 tests currently pass; 0 fail; 11 skip; 4 xfail).

## Reference files to read FIRST (every session)
1. `opencell/vivarium/karr_replication_initiation.py` — Phase C v1 pattern (DNA state, allocation, accumulate)
2. `opencell/vivarium/karr_allocation_step.py` — request/allocate protocol
3. `opencell/vivarium/karr_composite.py` — chassis_v4 wiring (search for `build_karr_chassis_v4`)
4. `opencell/vivarium/karr_protein_decay_light.py` — minimal scope, allocation consumer
5. `.github/copilot-instructions.md` — Primary-Source Discipline rule
6. `docs/design/pc_turn1_replication_initiation.md` — Phase C T1 design (your template)
7. `docs/design/phase_c_overview.md` — Phase C scope + new stores plan

## What "Karr-light" means
For Phase C processes too complex to port fully in one Codex turn, scope to:
- Per-tick rates (counts, deltas) matching Karr's per-process trace data
- Bulk state changes (e.g., fork advancement counter) NOT per-nucleotide mechanics
- Document the deferred mechanism explicitly as "v2 scope" in the file docstring
The chassis must still close mass balance — light scope ≠ fictional biology.

## Files NOT to modify
- Any file under `data/karr_archive/`, `data/m1_sources/`, `docs/karr_extracts/`
- `plan.md` (orchestrator owns it)
- `opencell_tasks.db` (orchestrator owns it)

## Branch policy
You are working in a dedicated worktree on branch `agent/<task-name>`. Commit
your work locally to that branch; the orchestrator will merge to `main` after review.

## Definition of done (per turn)
1. New file(s) created per the prompt
2. Tests pass via WSL pytest (`pytest tests/vivarium/test_karr_<process>.py -v`)
3. Full suite still green: `pytest -x -q` (must end in 0 failures, no new xfails)
4. One commit with message `pc-tN: <Process> (one-line scope summary)`
5. STATUS.md final block: files changed, test results, any blockers
