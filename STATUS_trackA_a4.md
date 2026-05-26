# STATUS Track-A A4 (L3 request/allocation vector members)

## 1) Sites modified (file:line)
| File | Lines | Change |
|---|---:|---|
| `opencell/vivarium/karr_allocation_step.py` | 73-109, 121-124 | Added L3 vector-member map + consumer-vector normalizer; apply at step init so existing consumers get required fields. |
| `tests/vivarium/test_a4_request_vector.py` | 1-98 | Added focused A4 vivarium tests for vector hardening and non-enrollment guard. |

## 2) Vector members added
Allocator-side additions are declared in `_L3_REQUIRED_VECTOR_MEMBERS` and injected only for already-present consumers.

| Process | Field name | Type | Source |
|---|---|---|---|
| `karr_dna_supercoiling` | `H2O` (and `ATP` enforced in canonical pair) | request/allocation vector member | L3 R06 (`allocator_audit.md` hot list) |
| `karr_protein_translocation` | `GTP`, `ADP`, `GDP`, `PI`, `H2O`, `H` (with `ATP` canonicalized) | request/allocation vector member | L3 S01 (`allocator_audit.md` + consolidated protein-translocation status verdict (c)) |

Notes:
- No allocation algorithm changes were made.
- No enrollment/key-normalization edits were made.

## 3) LOC delta
Code/test delta before this STATUS file:
- `opencell/vivarium/karr_allocation_step.py`: `+44 / -0`
- `tests/vivarium/test_a4_request_vector.py`: `+79 / -0` (new)
- Total: `+123 / -0` (within 120-190 target)

## 4) Test tails (baseline + post-edit)
Command (both runs):
```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/trackA-a4-vector && timeout 600 pytest tests/integration/test_chassis_v6_biology_firing.py tests/vivarium/ tests/unit/ -q --tb=short 2>&1 | tail -60"
```

Baseline tail:
```text
ERROR tests/vivarium/test_persistent_lsoda.py
ImportError: cannot import name 'MetabolismProcess' from 'opencell.vivarium'
ERROR tests/vivarium/test_vivarium_smoke.py
ImportError: cannot import name 'GeneNetworkProcess' from 'opencell.vivarium'
2 errors in 40.82s
```

Post-edit tail:
```text
ERROR tests/vivarium/test_persistent_lsoda.py
ImportError: cannot import name 'MetabolismProcess' from 'opencell.vivarium'
ERROR tests/vivarium/test_vivarium_smoke.py
ImportError: cannot import name 'GeneNetworkProcess' from 'opencell.vivarium'
2 errors in 32.14s
```

Additional focused check:
```bash
pytest tests/vivarium/test_a4_request_vector.py -q --tb=short
```
Result: `4 passed`.

## 5) Probe diff vs baseline
After-run command:
```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/trackA-a4-vector && python scripts/_probe_full_traces.py --out-dir artifacts/probe_a4_after --ticks 200 --seed 42"
```

Baseline: `E:\opencell\artifacts\probe_full_traces_20260526_190830\entity_call_stats.csv`  
After: `E:\opencell-worktrees\trackA-a4-vector\artifacts\probe_a4_after\entity_call_stats.csv`

| Entity | Baseline (calls/nonempty/exc) | After (calls/nonempty/exc) | Delta |
|---|---|---|---|
| `karr_protein_translocation` | `200 / 0 / 0` | `200 / 0 / 0` | no change (still dead) |
| `karr_dna_supercoiling` | `200 / 200 / 0` | `200 / 200 / 0` | no change (stays alive) |

`process_updates` rows:
- `karr_protein_translocation.csv`: `0 -> 0`
- `karr_dna_supercoiling.csv`: `200 -> 200`

Alive entities (nonempty_returns > 0):
- Baseline: `32`
- After: `32`
- `NO_ALIVE_TO_DEAD_FLIPS`: confirmed

## 6) Allocator conflict log (A2/A3)
- Near-miss avoided: `karr_composite.py` consumer enrollment lists were intentionally not edited (A2 territory).
- Near-miss avoided: no default key alias/normalization logic touched (A3 territory).
- Patch confined to per-consumer vector-member declarations/normalization inside `karr_allocation_step.py`.

## 7) A2 readiness signal
`READY`: allocator now auto-augments required L3 vector members for `karr_dna_supercoiling` and `karr_protein_translocation` when those consumers are present, so A2 enrollment changes can stay focused on process registration/topology without re-solving member completeness.
