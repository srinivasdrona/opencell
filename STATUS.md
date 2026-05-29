1. WID for enzymes[2]
- `MG_196_MONOMER` (Translation fixture `enzymeWholeCellModelIDs[2]`).

2. MATLAB file:line for the missing mutation
- `Translation.m:629-632` (`new_ribosome30SIF3 = min(ribosome30S, IF3)`, then decrement free IF3 / 30S, increment `ribosome30SIF3`).
- Companion initiation turnover: `Translation.m:748-752` (initiation consumes `ribosome30SIF3` and returns IF3 to free pool for initiated ribosomes).

3. Root-cause hypothesis (<=4 lines)
- OC v3 wrapper did not model the IF3 <-> 30S/30S_IF3 initiation-state mutation at all.
- Replay therefore retained free IF3 at tick 0 while Karr moved 13 copies from free IF3 into 30S_IF3-associated initiation flow.
- Missing `enzyme_wids` mapping also hid real enzyme IDs from replay projection.

4. Patch diff size (+/-)
- `opencell/vivarium/karr_translation_v3.py`: `+19 / -1` (20 lines total change; within <=25-line cap).

5. L2.1 replay result
- **first-fail moved (productive)**
- Command run (mandatory):
  - `python -m pytest tests/vivarium/test_karr_translation_l2_replay.py --tb=line -rs -q`
- New first-fail: `tick=0, observable=enzymes, index=3, oc_val=65, karr_val=77, diff=-12`.
- Baseline before patch: `tick=0, observable=enzymes, index=2, diff=+13`.

6. L1 chassis result
- Requested path `tests/vivarium/test_karr_translation.py` is not present in this worktree (pytest path error).
- Closest chassis smoke test run: `tests/vivarium/test_karr_translation_chassis.py`
  - `test_process_builds`: PASS
  - `test_engine_runs_without_drift_at_ss`: FAIL (`ARG delta -23.0 vs expected -27.6837`, rel error ~0.169 > 0.05).

7. Commit hash
- `<pending>`

8. Wall-time
- ~55 minutes.
