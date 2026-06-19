# Phase E.1 Real-Match — chassis_v6 Full Trajectory vs Karr

You are a Codex session. Read `SESSION_CONTEXT.md` first (8 hard rules).

## Token budget
**~130k**. Bulk of cost = one 32400-tick simulation (the cached fixture). Comparator + reporting is light. Commit at each of 5 checkpoints. Hard stop at 110k → STATUS PARTIAL.

## Mission

Upgrade the existing E.1 scaffold (currently runs chassis_v4 for 1000 s vs Karr) to a **full cell-cycle comparison**: chassis_v6 simulated for the full Karr trajectory length (32400 s nominal, or until division event), all 9 scaffold observables compared against Karr's full timeseries. Produce the canonical opencell-v6 trajectory pickle that E.2 will consume.

This unblocks E.2 (phenotype scorecard).

## Prerequisites
- `agent/naming-drift-rename` merged to main (canonical module names)
- `agent/phase-e-designs` merged to main (E.2/E.3/E-final docs available for reference)
- `pd-final-chassis-v6` shipped: `build_karr_chassis_v6()` importable, returns 28-process composite, all 5 v6 smoke tests pass on main
- `data/m1_sources/karr_native/cell_cycle_trajectory.mat` present
- Existing scaffold modules in place: `opencell/validation/karr_trajectory.py`, `opencell/validation/trajectory_compare.py`, `scripts/phase_e1_dry_run.py`

Verify all six; STOP and STATUS.md if any missing.

## Design sources (READ FIRST)
1. `docs/design/pe-1-trajectory-scaffold.md` — v1 scaffold spec (loader/comparator contract — DO NOT change)
2. `docs/design/phase_e_master.md` — overall Phase E narrative
3. `docs/design/phase_e2_phenotype_scorecard.md` — the downstream consumer (its `load_v6_trajectory_fixture()` helper must accept the pickle this turn produces)
4. `opencell/validation/karr_trajectory.py` and `trajectory_compare.py` — existing scaffold to reuse
5. `scripts/phase_e1_dry_run.py` — the v4-against-1000s baseline (your starting point for the new script)

## What to build

### 1. Long-run simulation script: `scripts/phase_e1_real_match.py`

Runs chassis_v6 for 32400 ticks, sampling every 100 ticks (matching Karr snapshot cadence). Persists state every snapshot to an in-memory list, then pickles to disk.

```python
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from vivarium.core.engine import Engine
import pickle, time, pathlib

OUT = pathlib.Path("data/phase_e/v6_trajectory_32400s.pkl")
SNAPSHOT_STRIDE_TICKS = 100
MAX_TICKS = 32400

def run_v6_trajectory():
    composite = build_karr_chassis_v6()
    engine = Engine(composite=composite, ...)
    snapshots = []
    t0 = time.time()
    for tick in range(0, MAX_TICKS + 1, SNAPSHOT_STRIDE_TICKS):
        engine.update(SNAPSHOT_STRIDE_TICKS if tick > 0 else 0.0)
        state = engine.state.get_value()
        snapshots.append({
            "tick": tick,
            "time_s": float(tick),
            "state": _extract_observables(state),
        })
        if _division_detected(state):
            break
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("wb") as f:
        pickle.dump({
            "snapshots": snapshots,
            "wall_time_s": time.time() - t0,
            "ticks_completed": snapshots[-1]["tick"],
            "division_detected": _division_detected(state),
            "chassis": "v6",
            "schema_version": 1,
        }, f)
    return snapshots
```

`_extract_observables(state)` returns the same 9 observables defined in scaffold (cell_dry_mass_g, replication_state_code, fork_position_norm, mrna_total_count_estimate, protein_total_count_estimate, atp_pool, gtp_pool, dntp_pool_total, division_event_timestamp_s) — reuse scaffold helpers where possible.

### 2. Comparator extension: `opencell/validation/trajectory_compare.py`

Add `compare_full_trajectory(opencell_trajectory, karr_trajectory, alignment="snapshot_index")` that:
- Aligns by snapshot index (both sampled every 100 s in same window)
- For each observable, computes per-snapshot abs+rel error
- Returns `{observable: {L_inf_abs, L_inf_rel, L2_abs, L2_rel, mean_abs, n_snapshots_compared, status}}`
- `status` ∈ {`PASS`, `FAIL`, `MISSING_KARR`, `MISSING_OPENCELL`}
- Uses same A6 tolerances as v1 (metabolite 0.05, count 0.5, signal 0.10)
- DO NOT break v1 `compare_trajectories` signature — additive only

### 3. Report generator: `scripts/phase_e1_real_match_report.py`

Reads both pickles (v6 + Karr), runs comparator, emits `docs/phase_e/E1_real_match.md`:
- Header: chassis version, wall-time, ticks completed, division detected
- Per-observable summary table (observable, L_inf_rel, L2_rel, n_snapshots, status)
- Top 10 worst-snapshot rows per observable (for diagnostic)
- A "passing observables" count (out of 9)

### 4. Tests: `tests/validation/test_e1_real_match.py`

```python
@pytest.mark.slow
def test_e1_real_match_fixture_exists():
    """The v6 trajectory pickle was produced and loadable."""
    p = pathlib.Path("data/phase_e/v6_trajectory_32400s.pkl")
    assert p.exists()
    with p.open("rb") as f:
        d = pickle.load(f)
    assert d["chassis"] == "v6"
    assert d["schema_version"] == 1
    assert d["ticks_completed"] >= 30000  # near-full run

def test_e1_comparator_runs():
    """Comparator processes the fixture without crashing on any observable."""
    v6 = _load_v6_fixture()
    karr = load_karr_trajectory()
    result = compare_full_trajectory(v6, karr)
    for obs in EXPECTED_OBSERVABLES:
        assert obs in result
        assert result[obs]["status"] in {"PASS", "FAIL", "MISSING_KARR", "MISSING_OPENCELL"}

def test_e1_at_least_one_observable_passes():
    """Sanity floor: framework is wired correctly (NOT a fidelity claim)."""
    v6 = _load_v6_fixture()
    karr = load_karr_trajectory()
    result = compare_full_trajectory(v6, karr)
    passing = [obs for obs, r in result.items() if r["status"] == "PASS"]
    assert len(passing) >= 1, f"No observable passed; framework likely broken. Detail: {result}"
```

### 5. Caching note for E.2

`phase_e2_phenotype_scorecard.md` references a session-scoped fixture loader. Verify (and patch if needed) that `load_v6_trajectory_fixture()` consumes `data/phase_e/v6_trajectory_32400s.pkl` with the schema documented above. If the fixture API in the E.2 design doc doesn't match what we produce, update the E.2 design doc (small inline patch acceptable).

## Acceptance criteria

- `scripts/phase_e1_real_match.py` runs end-to-end producing `data/phase_e/v6_trajectory_32400s.pkl`
- Wall-time logged (expect ~30-90 min on 9P bridge; not a fail criterion, just observed)
- `docs/phase_e/E1_real_match.md` written with per-observable table
- ≥1 observable in PASS bucket (sanity floor; this is NOT a fidelity gate — E.2 owns that)
- All 3 new tests pass
- Full suite still green (post-merge baseline + 3 new tests)

**Explicit non-goals**:
- Fidelity to Karr per-KP. That's E.2.
- Tightening tolerances. That's `per-kp-tolerance-calibration` (post-E.2 todo).
- Investigating why specific observables miss. That's E.3.

E.1 is a framework-correctness milestone, not a fidelity milestone.

## Commit checkpoints (5 expected)

1. Comparator extension (`compare_full_trajectory` + tests for it standalone, mocked snapshots) → "e1-real: comparator extension"
2. Long-run script `scripts/phase_e1_real_match.py` + dry validation on 1000 s (early-exit override for safety) → "e1-real: long-run script (smoke)"
3. Full 32400-tick run produces pickle → "e1-real: v6 trajectory fixture generated"
4. Report generator + `docs/phase_e/E1_real_match.md` → "e1-real: comparison report"
5. Test suite + final verification → "e1-real: tests pass"

If you hit token pressure between 3 and 4, the fixture pickle is the critical deliverable — STATUS PARTIAL is acceptable post-checkpoint-3.

## Hard rules
- DO NOT modify chassis_v6 or any karr_*.py process. If you spot a bug, write it to STATUS.md as a finding; let a follow-up turn fix it.
- DO NOT change scaffold v1 API (`compare_trajectories`, `load_karr_trajectory`). Additive only.
- Narrow pytest in inner loop: `pytest -x tests/validation/test_e1_real_match.py`
- Full suite only after checkpoint 5
- Persist the pickle even if comparator finds high error — the fixture itself is the deliverable

## STATUS.md
Per-checkpoint milestones, current token usage, snapshot count, wall-time tally, any anomalies (e.g. NaN observables, premature division, schema errors).

Begin by verifying prerequisites, then reading the 5 design sources.
