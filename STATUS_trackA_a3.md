# STATUS_trackA_a3

## 1) Sites modified (file:line)

| File | Lines | Change |
|---|---:|---|
| `opencell/vivarium/karr_allocation_step.py` | 18-22 | Added `KEY_ALIASES` for legacy key normalization (`d2_real`, `protein_decay_light`). |
| `opencell/vivarium/karr_allocation_step.py` | 79-111 | Added `_canonical_process_key`, `_normalize_consumer_processes`, `_normalize_requests`. |
| `opencell/vivarium/karr_allocation_step.py` | 123-129 | `ports_schema()` now normalizes configured consumer keys/wids. |
| `opencell/vivarium/karr_allocation_step.py` | 170 | `next_update()` now canonicalizes/merges request keys before allocation. |
| `opencell/vivarium/karr_protein_decay_light.py` | 223-241 | Added guard: when ATP/H2O demand is zero, suppress negative substrate deltas (no consume-with-zero-demand writeback). |
| `tests/vivarium/test_a3_key_drift.py` | 1-89 | Added focused A3 regression tests (alias normalization behavior + PD zero-demand negative-delta guard; environment-safe skip for non-worktree import path). |

## 2) Key alias / default key changes (before/after)

Before (`karr_allocation_step.py`):
```python
def _default_consumer_processes():
    return [
        ("karr_macromolecular_complexation", ["ATP", "GTP", "H2O"]),
        ("karr_protein_decay_light", ["ATP", "H2O"]),
        ("karr_rna_decay", ["H2O"]),
    ]

# no alias map / no request-key canonicalization
requests = states.get("requests", {})
```

After (`karr_allocation_step.py`):
```python
KEY_ALIASES = {
    "d2_real": "karr_macromolecular_complexation",
    "protein_decay_light": "karr_protein_decay_light",
}

requests = _normalize_requests(states.get("requests", {}))
```

Notes:
- Default keys were already canonical in this branch; this patch adds alias safety for legacy keys and canonical merge behavior.
- This addresses L4 drift risk without changing A2 enrollment/A4 vector-member territories.

## 3) Zero-demand-while-consuming diagnosis (allocator vs fixture)

- **ProteinDecayLight**: fixture-driven issue confirmed for ATP/H2O demand extraction.
  - Runtime check at this HEAD: `ATP nonzero cols = 0`, `H2O nonzero cols = 0` across the 147 filtered columns in `complex_decay_reactions`.
  - Conclusion: ATP/H2O request collapse is primarily **fixture extraction/data** (not allocator key dispatch).
  - A3 fix applied here: if computed ATP/H2O request is zero, suppress negative substrate writebacks to avoid consume-with-zero-demand behavior.
- **MacromolecularComplexation**: allocator/request seam remains known (hard-zero request calculator), but process already strict-gated by allocated budget in this branch. No new allocator enrollment/topology changes made (A2 boundary respected).

## 4) LOC delta

- `opencell/vivarium/karr_allocation_step.py`: `+48 / -2`
- `opencell/vivarium/karr_protein_decay_light.py`: `+15 / -5`
- `tests/vivarium/test_a3_key_drift.py`: `+71 / -0` (new file)
- **Total**: `+134 / -7` (net `+127`) — within 120-200 target.

## 5) Test tails (baseline + post-edit)

Baseline tail:
```text
==================================== ERRORS ====================================
___________ ERROR collecting tests/vivarium/test_persistent_lsoda.py ___________
ImportError while importing test module '/mnt/e/opencell-worktrees/trackA-a3-keys/tests/vivarium/test_persistent_lsoda.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/vivarium/test_persistent_lsoda.py:35: in <module>
    from opencell.vivarium import MetabolismProcess, PersistentMetabolismProcess
E   ImportError: cannot import name 'MetabolismProcess' from 'opencell.vivarium' (unknown location)
____________ ERROR collecting tests/vivarium/test_vivarium_smoke.py ____________
ImportError while importing test module '/mnt/e/opencell-worktrees/trackA-a3-keys/tests/vivarium/test_vivarium_smoke.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/vivarium/test_vivarium_smoke.py:15: in <module>
    from opencell.vivarium import (
E   ImportError: cannot import name 'GeneNetworkProcess' from 'opencell.vivarium' (unknown location)
=========================== short test summary info ============================
ERROR tests/vivarium/test_persistent_lsoda.py
ERROR tests/vivarium/test_vivarium_smoke.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 50.72s
```

Post-edit tail:
```text
==================================== ERRORS ====================================
___________ ERROR collecting tests/vivarium/test_persistent_lsoda.py ___________
ImportError while importing test module '/mnt/e/opencell-worktrees/trackA-a3-keys/tests/vivarium/test_persistent_lsoda.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/vivarium/test_persistent_lsoda.py:35: in <module>
    from opencell.vivarium import MetabolismProcess, PersistentMetabolismProcess
E   ImportError: cannot import name 'MetabolismProcess' from 'opencell.vivarium' (unknown location)
____________ ERROR collecting tests/vivarium/test_vivarium_smoke.py ____________
ImportError while importing test module '/mnt/e/opencell-worktrees/trackA-a3-keys/tests/vivarium/test_vivarium_smoke.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/vivarium/test_vivarium_smoke.py:15: in <module>
    from opencell.vivarium import (
E   ImportError: cannot import name 'GeneNetworkProcess' from 'opencell.vivarium' (unknown location)
=========================== short test summary info ============================
ERROR tests/vivarium/test_persistent_lsoda.py
ERROR tests/vivarium/test_vivarium_smoke.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 43.81s
```

Result: tails are identical modulo runtime duration.

## 6) Probe diff table (`entity_call_stats.csv`)

Baseline: `E:\opencell\artifacts\probe_full_traces_20260526_190830\entity_call_stats.csv`  
After: `artifacts/probe_a3_after/entity_call_stats.csv`

| Entity | Baseline (calls/nonempty/exc) | After (calls/nonempty/exc) | Delta |
|---|---|---|---|
| `karr_macromolecular_complexation` | `200 / 200 / 0` | `200 / 200 / 0` | none |
| `karr_protein_decay_light` | `200 / 200 / 0` | `200 / 200 / 0` | none |

Global probe diff:
- Changed rows: `0`
- `NO_ALIVE_TO_DEAD_FLIPS`: **PASS** (`0`)
- Alive entities baseline: `32 / 40`; after: `32 / 40` (no regressions across the 32 alive entities).
- Process-update CSV sizes unchanged for both targets (`21` bytes baseline and after), consistent with fixture/topology follow-up being outside this PR.

## 7) Allocator conflict log (A2/A4 protocol)

- **Touched only claimed section**: allocator key normalization/default-key dispatch in `karr_allocation_step.py`.
- **Did not touch A4 territory**: no request vector-member definition changes.
- **Did not touch A2 territory**: no enrollment/direct-writer registration or topology rewiring in `karr_composite.py`.
- Near-miss intentionally avoided: adding/requesting topology rewires for internal request/allocated stores was identified as A2-owned and not edited.

## 8) A2 readiness signal

- A3 patch is additive and key-normalization scoped.
- No enrollment or direct-writer topology edits were made; A2 can proceed/rebase without conflict from this PR's touched regions.
