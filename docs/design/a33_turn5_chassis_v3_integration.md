# A3.3 Turn 5 — build_karr_chassis_v3 + ratchet-closure integration

**Status**: design ready · **Codex worktree**: `agent/a33-integration` (to be created after T1-T4 merge) · **Estimated wall**: 30 min · **Depends on**: T1 + T2 + T3 + T4 merged to main.

## Why this module exists

The v3 chassis is the headline deliverable of A3 step 3: a Vivarium composite that runs M1 + M2v3 + M3v3 + KarrAllocationStep + KarrD2Real + ProteinDecayLight together for 1000+ ticks and demonstrates **steady-state complex counts** (the closed ratchet loop).

If this composite shows complex counts growing unboundedly or oscillating wildly, the joint design is wrong. If it shows a clean steady state, A3 step 3 ships.

## Scope (this turn)

**Modified files**:
1. `opencell/vivarium/karr_composite.py` (+~80 LOC)
   - Add `build_karr_chassis_v3(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=10.0, condition=None) -> Engine`
   - Keep `build_karr_chassis_v2` and earlier builders untouched

**Net new files**:
2. `tests/integration/test_karr_chassis_v3.py` (~300 LOC)
   - The ratchet-closure integration test (1000 ticks, steady state verification)
   - + ancillary unit tests on the v3 wiring itself

## Composite topology (the wiring)

```
Vivarium Engine: build_karr_chassis_v3

Steps (run in topology-determined order before Processes):
  ┌─ RequestCalculator-D2 (writes requests.karr_d2_real.<wid>)
  ├─ RequestCalculator-PD (writes requests.karr_protein_decay_light.{ATP,H2O})
  └─ KarrAllocationStep (reads requests.*, substrates.*; writes substrates_allocated.*)

Processes (parallel snapshot, all using accumulate updater):
  ├─ KarrMetabolismProcess (M1, existing — already uses accumulate on substrates)
  ├─ KarrTranscriptionV3Process (M2v3 — accumulate on rna.counts; delta-emit)
  ├─ KarrTranslationV3Process (M3v3 — accumulate on protein.counts; delta-emit)
  ├─ KarrD2RealProcess (accumulate on complex.counts, substrates)
  ├─ ProteinDecayLightProcess (accumulate on complex.counts, protein.counts, rna.counts, substrates)
  └─ KarrTotalsEmitter (existing housekeeping)

Stores:
  ├─ substrates.<wid>           (accumulate, 585 WIDs)
  ├─ rna.counts.<wid>           (accumulate, ~530 WIDs)
  ├─ protein.counts.<wid>       (accumulate, ~482 WIDs)
  ├─ complex.counts.<wid>       (accumulate, 147 WIDs)
  ├─ requests.<proc>.<wid>      (set, written by RequestCalculators)
  └─ substrates_allocated.<proc>.<wid> (set, written by KarrAllocationStep)
```

## Pseudocode for `build_karr_chassis_v3`

```python
def build_karr_chassis_v3(
    m1_model: KarrM1Model,
    m2_model: KarrM2Model,
    m3_model: KarrM3Model,
    time_step_s: float = 1.0,
    emit_step_s: float = 10.0,
    condition: str | None = None,
) -> Engine:
    """v3 chassis: M1 + M2v3 + M3v3 + D2-real + ProteinDecay-light + KarrAllocationStep.

    Differs from v2:
      - M2/M3 use delta-emit (accumulate) instead of set
      - D2-stub replaced by D2-real
      - ProteinDecay-light added (closes ratchet)
      - KarrAllocationStep + RequestCalculators added (proper Karr allocation)
    """
    # Load fixtures (D.2-real and ProteinDecay-light load their own)
    
    # Build processes
    m1 = KarrMetabolismProcess({...})  # unchanged from v2
    m2_v3 = KarrTranscriptionV3Process({"kinetics_model": m2_model, "time_step": time_step_s})
    m3_v3 = KarrTranslationV3Process({"kinetics_model": m3_model, "time_step": time_step_s})
    d2_real = KarrD2RealProcess({"time_step": time_step_s})
    decay_light = ProteinDecayLightProcess({"time_step": time_step_s})
    
    # Build allocation Step with full consumer list
    allocation = KarrAllocationStep({
        "consumer_processes": [
            ("karr_d2_real", d2_real.substrate_wids),
            ("karr_protein_decay_light", ["ATP", "H2O"]),
        ],
        "substrate_wids": m1.substrate_wids,
    })
    
    # Build request calculators (one per consumer)
    req_d2 = RequestCalculatorD2({"d2_real_proc": d2_real})  # closure over consumer
    req_pd = RequestCalculatorPD({"pd_light_proc": decay_light})
    
    # Topology: declare port wiring
    topology = {
        "karr_m1":                  {...},
        "karr_transcription_v3":    {...},
        "karr_translation_v3":      {...},
        "karr_d2_real":             {...},
        "karr_protein_decay_light": {...},
        "karr_allocation_step":     {"substrates": ("substrates",), "requests": ("requests",), "substrates_allocated": ("substrates_allocated",)},
        "request_calculator_d2":    {...},
        "request_calculator_pd":    {...},
    }
    
    composite = {
        "processes": {
            "karr_m1": m1,
            "karr_transcription_v3": m2_v3,
            "karr_translation_v3": m3_v3,
            "karr_d2_real": d2_real,
            "karr_protein_decay_light": decay_light,
        },
        "steps": {
            "karr_allocation_step": allocation,
            "request_calculator_d2": req_d2,
            "request_calculator_pd": req_pd,
        },
        "topology": topology,
    }
    
    return Engine(composite=composite, emit_step=emit_step_s)
```

### RequestCalculator pattern

```python
class RequestCalculatorD2(Step):
    """Computes D.2-real's per-tick metabolite request from current state.
    
    For D.2-real specifically: this is ALWAYS zero (per Opus critique;
    calcResourceRequirements_Current returns zeros in MacromolecularComplexation.m).
    Wired for architectural consistency but emits no requests.
    """
    defaults = {"d2_real_proc": None}
    
    def ports_schema(self):
        wids = self.parameters["d2_real_proc"].substrate_wids
        return {"requests": {"karr_d2_real": {
            wid: {"_default": 0.0, "_updater": "set", "_emit": False} for wid in wids
        }}}
    
    def next_update(self, timestep, states):
        # MC requests zero metabolites per Karr's actual algorithm
        return {"requests": {"karr_d2_real": {}}}


class RequestCalculatorPD(Step):
    """Computes ProteinDecay-light's per-tick ATP+H2O request from current complex counts.
    
    expected_atp = sum over c of (decay_rate * complex_count[c] * dt * atp_per_decay[c])
    expected_h2o = ... similar
    """
    defaults = {"pd_light_proc": None}
    
    def ports_schema(self):
        return {
            "complex": {"counts": {...}},  # read all D.2 complex counts
            "requests": {"karr_protein_decay_light": {
                "ATP": {"_default": 0.0, "_updater": "set", "_emit": False},
                "H2O": {"_default": 0.0, "_updater": "set", "_emit": False},
            }},
        }
    
    def next_update(self, timestep, states):
        # Calculate expected decay events, multiply by per-decay stoichiometry
        pd = self.parameters["pd_light_proc"]
        complex_counts = np.array(
            [float(states["complex"]["counts"][wid]) for wid in pd.complex_wids]
        )
        rates = pd._decay_rates_per_complex()  # helper on the process
        expected_decays = rates * complex_counts * timestep
        # Per-decay ATP/H2O from complex_decay_reactions matrix
        atp_idx = pd.atp_substrate_idx
        h2o_idx = pd.h2o_substrate_idx
        atp_req = abs(pd.complex_decay_reactions[atp_idx, :] @ expected_decays)
        h2o_req = abs(pd.complex_decay_reactions[h2o_idx, :] @ expected_decays)
        return {"requests": {"karr_protein_decay_light": {
            "ATP": float(atp_req),
            "H2O": float(h2o_req),
        }}}
```

## Test plan

### Test 1: chassis builds without errors
```python
def test_chassis_v3_builds():
    engine = build_karr_chassis_v3(m1_model, m2_model, m3_model)
    assert engine is not None
```

### Test 2: 10-tick smoke run
```python
def test_chassis_v3_10_ticks():
    """Run 10 ticks. No exceptions, no negative counts, mass roughly conserved."""
    engine = build_karr_chassis_v3(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=1.0)
    engine.update(10.0)
    state = engine.state.get_value()
    # Check no negative counts
    for wid, cnt in state.get("complex", {}).get("counts", {}).items():
        assert cnt >= 0, f"Negative complex count for {wid}: {cnt}"
```

### Test 3: ratchet closure (THE headline test, 1000 ticks)
```python
def test_chassis_v3_ratchet_closure_steady_state():
    """The closed loop: D.2-real assembles, ProteinDecay-light degrades.
    
    After 1000 ticks at Δt=1s (≈17 min biological time):
      - Total complex count should be bounded (not growing unbounded)
      - Complex counts in last 100 ticks should be within 20% of mean over ticks 500-1000
        (i.e., reached a steady state)
    """
    engine = build_karr_chassis_v3(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=10.0)
    
    # Capture complex count trajectories
    complex_trajectories = {wid: [] for wid in d2_real.complex_wids}
    for tick in range(1000):
        engine.update(1.0)
        state = engine.state.get_value()
        for wid in complex_trajectories:
            complex_trajectories[wid].append(state["complex"]["counts"].get(wid, 0))
    
    # Check steady state for the 10 most-abundant complexes
    top10 = sorted(complex_trajectories.items(),
                    key=lambda x: x[1][-1], reverse=True)[:10]
    for wid, traj in top10:
        late_mean = np.mean(traj[500:])
        early_mean = np.mean(traj[200:500])
        # Should not be growing > 20% between early-mid and late
        assert abs(late_mean - early_mean) / max(1, early_mean) < 0.2, \
            f"Complex {wid} not at steady state: early={early_mean}, late={late_mean}"
```

### Test 4: no v2 regressions
```python
def test_v2_chassis_still_works():
    """Confirm build_karr_chassis_v2 produces identical results post-merge."""
    # Run 10-tick determinism test against pre-merge baseline (compare to known good output)
```

### Test 5: probe-4-style topology audit
```python
def test_chassis_v3_all_writers_accumulate():
    """All same-leaf-writers in v3 chassis use accumulate updater."""
    # Inspect topology and process schemas
    # For every leaf written by multiple processes/steps, assert all writers use accumulate
```

### Test 6: allocation step actually constrains under scarcity
```python
def test_allocation_step_constrains_under_scarcity():
    """Force a state where total ATP demand exceeds supply.
    Verify substrates_allocated.* sums to supply (proportional fair share)."""
```

### Test 7: D.2-real produces, ProteinDecay-light degrades
```python
def test_d2_and_decay_both_active():
    """In a 100-tick run, verify both D.2 (positive deltas) and ProteinDecay
    (negative deltas) operate on complex.counts."""
```

### Test 8: emit-step instrumentation
```python
def test_emit_step_records_complex_trajectories():
    """Confirm Vivarium emit captures complex.counts at every emit_step."""
```

## Acceptance criteria

- All 8 tests pass
- All 168+ existing tests still pass (v2 unaffected)
- The ratchet-closure test (Test 3) is the headline acceptance — if it passes, A3.3 ships
- Commit: `a33-t5: build_karr_chassis_v3 + ratchet-closure integration`
- STATUS reports: chassis tick-rate (ticks/s), peak memory, ratchet test outcome

## Out of scope (Turn 5 / A3.3 entirely)

- Δt sensitivity sweep — Phase B prerequisite
- Multi-run determinism check (run with rng_seed=0,1,2 and confirm deterministic) — useful but Phase B
- Performance profiling — Phase B
- Beyond M3/D.2-real: Translation initiation/termination details, transcription regulation — Phase B
- Karr fidelity validation against published whole-cell trajectories — Phase E

## Reference for Codex executor

Read these files first:
- `docs/design/a33_turn1_m2m3_v3_delta_emit.md` (what M2v3, M3v3 expose)
- `docs/design/a33_turn2_allocation_step.md` (the allocation Step contract)
- `docs/design/a33_turn3_d2_real.md` (D.2-real port schema, substrate/complex WID lists)
- `docs/design/a33_turn4_protein_decay_light.md` (ProteinDecay-light port schema)
- Existing `opencell/vivarium/karr_composite.py::build_karr_chassis_v2` as the template

The 4 turn outputs MUST be merged to main first. Verify by:
```
git log --oneline -10
```
should show commits with prefix `a33-t1:`, `a33-t2:`, `a33-t3:`, `a33-t4:`.

Time-box: 30 min for the integration code; 1000-tick test may take 10-30 min wall to run. Don't time-box the run.
