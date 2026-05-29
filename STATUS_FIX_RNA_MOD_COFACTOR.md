# STATUS: FIX_RNA_MOD_COFACTOR

1. **Path chosen (X or Y) + why**
- **Path X**. Reverted `9acdb32` first as directed to remove stochastic-round ambiguity and re-check replay behavior.
- Replay oracle did not produce a fail fingerprint; it is currently an L2.1 no-op trace (all mutated observables unchanged across 100 ticks).

2. **Root cause hypothesis**
- Residual cofactor drift is consistent with substrate accounting being tied to completed-RNA transitions instead of per-reaction flux multiplicity.
- In OC, partial reaction chemistry was dropped from substrate updates; this can bias cofactor rows (including AMP/AHCYS families).

3. **Patch diff size**
- `opencell/vivarium/karr_rna_modification.py`: **8 lines changed** (7 insertions, 1 deletion).
- Surface area in target file is <=20 lines.

4. **Final test result + first-fail fingerprint**
- `pytest tests/vivarium/test_karr_rna_modification_l2_replay.py --tb=line -rs` => **SKIPPED**
- Fingerprint: `L2.1 N/A: no-op trace` with mutated observable nonzero-delta counts `{'substrates': 0, 'modifiedRNAs': 0, 'unmodifiedRNAs': 0}`.
- Additional verification: `pytest tests/vivarium/test_karr_rna_modification.py --tb=line -rs` => **10 passed**.

5. **Commit hash(es)**
- `9b3ae46` — revert of ambiguous stochastic-round commit `9acdb32`.
- `<pending>` — this patch commit (created below as `[wip]`).

6. **Wall-time**
- ~30 minutes.
