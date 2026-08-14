# Task: Port Karr Translation.evolveState — biology-faithful enzyme accounting (L2.5 unblocker)

Read `./SESSION_CONTEXT.md` for project rules.
Pay special attention to Hard Rule 17 (naming discipline, added today).

## ⚠️ Python interpreter — MANDATORY
Use `bin\oc-pytest.cmd` and `bin\oc-py.cmd` for all Python/pytest. Do NOT run python directly.
The WSL venv at `/mnt/e/opencell/.venv-wsl` is the only correct interpreter.

## STATUS file
Write `docs/phase_f/status/STATUS_translation_evolvestate_port.md` as you go.
Final assistant message: "done, see STATUS".
Do NOT write STATUS at the repo root — repo .gitignore drops STATUS_*.md there.

## Commit cadence
Commit each beat with prefix `port(translation):`. Beats:
1. Audit existing v3 wrapper + identify what needs adding (no code changes)
2. Add Karr-faithful enzyme transition logic (initiation: 30S+IF3→30S_IF3)
3. Add ribosome assembly: 30S_IF3+50S→70S, and recycling 70S→30S+50S
4. Add elongation factor recycling (bound→free transitions)
5. Validate: both L2.2 single-process AND L2.5 composition tests pass

## The biology to port (from Karr Translation.m:599-850)

### Read-set anchor lines in `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Translation.m`:

- Lines 599-700: `evolveState` opening — variable setup, **30S+IF3 formation** (line 629-632)
- Lines 678-682: **elongation factor recycling** (bound EF-G/EF-Ts/EF-Tu/EF-P → free, all on tick start)
- Lines 684-705: elongation loop (per-ribosome, deducts factors per AA)
- Lines 740-754: **70S complex initiation** (30S_IF3 + 50S → 70S bound)
- Lines 798-860: **termination/release** (70S → 30S + 50S free, releases RF, etc.)
- Lines 870-895: tmRNA rescue path (lower priority, can be Karr-light)

### The 4 critical enzyme transitions OC currently MISSES without trace_hint:

| Transition | Karr line | OC line affected | Effect on enzyme vector |
|---|---|---|---|
| **30S + IF3 → 30S_IF3** | 629-632 | Translation enzymes[2]=MG_196_MONOMER, [9]=RIBOSOME_30S, [10]=RIBOSOME_30S_IF3 | -IF3, -30S, +30S_IF3 |
| **30S_IF3 + 50S → 70S (bound)** | 740-754 | enzymes[10]=30S_IF3, [11]=50S; boundEnzymes[12]=70S | -30S_IF3, -50S, +bound70S |
| **70S termination → 30S + 50S** | 798-860 | boundEnzymes[12]=70S, enzymes[9]=30S, [11]=50S | -bound70S, +30S, +50S |
| **Elongation factor recycling** | 678-682 | enzymes[3,4,5,6]=MG_089/026/451/433; their bound mirrors | +12 to each free, -12 to each bound (per tick) |

The 13-unit diff observed in L2.5 first-pair canary is **exactly tick 0's
elongation factor recycling + IF3 binding**. This is biology that OC is missing.

## The forensic baseline (from STATUS_translation_l25_divergence.md)

OC's current `next_update` at tick 0:
- Emits `update["protein"]` (correct — monomer counts updated via M3 mechanism)
- Emits `update["enzymes"]` = {} when no trace_hint
- Emits `update["boundEnzymes"]` = {} when no trace_hint

Karr at tick 0 (from oracle trace):
- `enzymes[MG_196_MONOMER]` (IF3): -13
- `enzymes[RIBOSOME_30S]`: -23
- `enzymes[RIBOSOME_30S_IF3]`: +13
- `enzymes[RIBOSOME_50S]`: -10
- `boundEnzymes[RIBOSOME_70S]`: +10
- `enzymes[MG_089/026/451/433]`: each +12 (elongation factors freed)
- `boundEnzymes[MG_089/026/451/433]`: each -12 (elongation factors released)

Pattern: 10 ribosomes terminate (70S→30S+50S), 13 initiate (30S+IF3→30S_IF3),
and all elongation factors recycle.

## Implementation approach

### Add a new method `_compute_enzyme_transitions_from_biology`

In `opencell/vivarium/karr_translation_v3.py`, add a method that computes
enzyme deltas from current state + Karr's algorithm, WITHOUT reading from
trace_hint:

```python
def _compute_enzyme_transitions_from_biology(
    self,
    states: dict[str, Any],
    timestep: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Compute (enzymes_delta, bound_enzymes_delta) from biology.
    
    Implements the four Karr Translation.evolveState transitions:
    1. 30S + IF3 -> 30S_IF3 (initiation, line 629-632)
    2. Elongation factor recycling (line 678-682)
    3. 30S_IF3 + 50S -> 70S (line 740-754)
    4. 70S termination -> 30S + 50S (line 798-860)
    
    Returns (enzymes_delta, bound_enzymes_delta), both keyed by WID.
    """
    # ... implementation ...
```

### Modify `next_update` to use biology path when hint absent

Current flow:
```python
update["enzymes"] = self._enzyme_channel_deltas_from_trace_hint(states, channel="enzymes")
```

New flow:
```python
hint = states.get("trace_hint", {})
if hint and "enzymes_next" in hint:
    # L2.2 mode: use hint as authoritative
    update["enzymes"] = self._enzyme_channel_deltas_from_trace_hint(states, channel="enzymes")
    update["boundEnzymes"] = self._enzyme_channel_deltas_from_trace_hint(states, channel="boundEnzymes")
else:
    # L2.5+ mode: compute from biology
    enz_delta, bound_delta = self._compute_enzyme_transitions_from_biology(states, timestep)
    if enz_delta:
        update["enzymes"] = enz_delta
    if bound_delta:
        update["boundEnzymes"] = bound_delta
```

This preserves L2.2 backward compatibility (hint path unchanged) while
adding L2.5 honest biology path.

## Algorithm pseudocode (from Karr Translation.m)

```python
def _compute_enzyme_transitions_from_biology(self, states, timestep):
    # Read current enzyme counts
    enz = states.get("enzymes", {})
    bound = states.get("boundEnzymes", {})
    
    n_30S = int(enz.get("RIBOSOME_30S", 0))
    n_30S_IF3 = int(enz.get("RIBOSOME_30S_IF3", 0))
    n_50S = int(enz.get("RIBOSOME_50S", 0))
    n_70S_bound = int(bound.get("RIBOSOME_70S", 0))
    n_IF3 = int(enz.get("MG_196_MONOMER", 0))  # initiation factor 3
    
    # Elongation factor WIDs (4 factors)
    elng_factor_wids = ["MG_089_DIMER", "MG_026_MONOMER", "MG_451_DIMER", "MG_433_DIMER"]
    # (Verify by reading process.enzymeIndexs_elongationFactors from fixture)
    
    enz_delta = {}
    bound_delta = {}
    
    # Transition 1: 30S + IF3 -> 30S_IF3 (line 629-632)
    new_30S_IF3 = min(n_30S, n_IF3)
    if new_30S_IF3 > 0:
        enz_delta["RIBOSOME_30S"] = enz_delta.get("RIBOSOME_30S", 0) - new_30S_IF3
        enz_delta["RIBOSOME_30S_IF3"] = enz_delta.get("RIBOSOME_30S_IF3", 0) + new_30S_IF3
        enz_delta["MG_196_MONOMER"] = enz_delta.get("MG_196_MONOMER", 0) - new_30S_IF3
    
    # Transition 2: elongation factor recycling (line 678-682)
    # All bound EFs become free at tick start
    for wid in elng_factor_wids:
        bound_count = int(bound.get(wid, 0))
        if bound_count > 0:
            enz_delta[wid] = enz_delta.get(wid, 0) + bound_count
            bound_delta[wid] = bound_delta.get(wid, 0) - bound_count
    
    # Transition 3: 30S_IF3 + 50S -> 70S bound (line 740-754)
    # Karr's logic: this happens for active mRNA binding; simplified here
    # Count of new initiations = min(30S_IF3 after step 1, 50S, available mRNAs, allocated GTP)
    n_active_mRNAs = ...  # count of mRNAs with translation initiation factors bound
    # ...
    
    # Transition 4: 70S termination -> 30S + 50S free (line 798-860)
    # Count of terminating ribosomes = sum of ribosomes whose nascent peptide
    # reached the end of their mRNA this tick
    # Simplified: use elongation_rate to estimate
    # ...
    
    return enz_delta, bound_delta
```

The Transition 3 and 4 are more complex because they require ribosome state
tracking (which mRNAs are bound, what positions). Read Karr's code lines
740-860 carefully. If implementing the full ribosome state machine is too
much, **use trace-based heuristics** (count of active ribosomes from M3
mechanism) for transitions 3-4 but make transitions 1 + 2 fully faithful.

## Acceptance criteria

1. **L2.2 single-process test still passes:**
   `bin\oc-pytest.cmd tests/vivarium/test_karr_translation_l2_replay.py -v`
   (this uses trace_hint, so should pass unchanged)

2. **L2.5 composition test (without hints) passes for first few ticks at least:**
   `bin\oc-pytest.cmd tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py::test_l25_translation_plus_rna_processing_no_hints -v`
   If full 100-tick pass is too ambitious, getting tick 0 to pass with
   only ±2 enzyme tolerance is acceptable as a milestone.

3. **No regressions in other Translation tests:**
   `bin\oc-pytest.cmd tests/vivarium/test_karr_translation*.py -v`

4. **At least 3 commits with `port(translation):` prefix**

5. **STATUS written with:**
   - Which transitions are fully faithful
   - Which transitions use heuristics (and why)
   - Tick-by-tick diff after fix (what's improved, what's still divergent)
   - Recommended next steps if not all tests pass

## Files you may read (read-set)

- `opencell/vivarium/karr_translation_v3.py` (PRIMARY — the file to modify)
- `opencell/vivarium/karr_translation.py` (v1 — has _l21_release_guard reference)
- `opencell/m3/translation.py` and `translation_v2.py` (M3 mechanism backing v3)
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Translation.m` (KARR SOURCE)
- `data/karr_fixtures/per_process/Translation_flat.mat` (for enzymeIndexs_* arrays)
- `data/m1_sources/karr_native/per_process_traces_v2_s000/Translation_100ticks.mat` (oracle)
- `tests/vivarium/test_karr_translation_l2_replay.py`
- `tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py`
- `tests/vivarium/l2_2_replay_common_v2.py` (composition harness)
- `docs/phase_f/status/STATUS_translation_l25_divergence.md` (the forensic analysis from this morning)
- `data/schemas/per_process/translation.toml` (v2.1 schema — has enzyme WIDs, observables)

## Files you may write (write-set)

- `opencell/vivarium/karr_translation_v3.py` (PRIMARY)
- `tests/vivarium/test_karr_translation_evolvestate.py` (NEW — unit tests for transitions)
- `docs/phase_f/status/STATUS_translation_evolvestate_port.md` (status doc)

DO NOT modify:
- `karr_translation.py` (v1 — leave alone)
- `karr_ribosome_assembly.py` (separate process, separate concerns)
- Any other process file
- Test infrastructure (`l2_*_replay_common*.py`)
- TOML schemas

## Hard rules

- If you exceed 130k tokens without committing Beat 3, stop and write STATUS
- Preserve the existing trace_hint path (do NOT remove it; add biology path alongside)
- Name new methods with biology-neutral verbs where possible (`_compute_*`,
  `_recycle_*`, `_initiate_*`) — these are organism-agnostic operations
- The new code path must NOT read from `trace_hint`. That's the whole point.
- If transitions 3+4 require ribosome state tracking that doesn't exist in
  v3, document the gap and propose a separate task for it. Do NOT invent
  state tracking.
- Run the full Translation test suite after each major change, not just at
  the end — catches regressions early
