# STATUS: fix-adapter-keys-5way

## Per-process results

### ProteinDecay
- Before: `SKIP` - `Replay execution failed: 'complex'`
- Root cause: Replay state can omit the `complex` port, but adapter indexed `states["complex"]["counts"]` directly.
- Fix: Added a safe empty-map fallback for missing/non-dict `complex` port in `ProteinDecayLightProcess.next_update`.
- After: `SKIP` - `Structural mismatch: no comparable properties.`

### ProteinFolding
- Before: `SKIP` - `Replay execution failed: 'unfolded_counts'`
- Root cause: Fixture exposes `unfoldedMonomers`, adapter expected `protein.unfolded_counts`.
- Fix: Added legacy vector-to-WID fallback from `unfoldedMonomers` when nested `protein.unfolded_counts` is absent.
- After: `PASS`

### ProteinModification
- Before: `SKIP` - `Replay execution failed: 'unmodified_counts'`
- Root cause: Fixture exposes `unmodifiedMonomers`, adapter expected `protein.unmodified_counts`.
- Fix: Added legacy vector-to-WID fallback from `unmodifiedMonomers` when nested `protein.unmodified_counts` is absent.
- After: `PASS`

### RNAModification
- Before: `SKIP` - `Replay execution failed: 'rna'`
- Root cause: Fixture exposes `unmodifiedRNAs` / `modifiedRNAs`, adapter expected nested `rna.counts` / `rna.modified_counts`.
- Fix: Added legacy vector-to-WID fallbacks from `unmodifiedRNAs` and `modifiedRNAs` when nested `rna` stores are absent.
- After: `PASS`

### tRNAAminoacylation
- Before: `SKIP` - `Replay execution failed: 'rna'`
- Root cause: Fixture exposes `freeRNAs` / `aminoacylatedRNAs`, adapter expected nested `rna.counts` / `rna.aminoacylated_counts`.
- Fix: Added legacy vector-to-WID fallbacks from `freeRNAs` and `aminoacylatedRNAs` when nested `rna` stores are absent.
- After: `PASS`

## Scorecard tally

- Baseline committed scorecard: `15 PASS / 1 PARTIAL / 0 FAIL / 12 SKIP`.
- After refresh in this branch: `19 PASS / 1 PARTIAL / 0 FAIL / 17 SKIP`.

Notes:
- Four of five target SKIPs moved to `PASS`.
- `ProteinDecay` no longer fails with `KeyError('complex')`, but remains `SKIP` because the current replay artifact has no comparable input/output properties for scoring.
- Current script output includes additional `_from_flat` / `_from_trajectory` fixture stems, which increases total SKIP count versus the earlier 28-row scorecard snapshot.

## Processes not moved from SKIP -> PASS/PARTIAL

- `ProteinDecay` stayed `SKIP`.
- Reason: The key bug is fixed (no more `Replay execution failed: 'complex'`), but fixture comparables are absent, so the row is now a structural-mismatch SKIP.

## Files changed

- `artifacts/karr_fidelity_scorecard.json`
- `docs/phase_e/karr_fidelity_scorecard.md`
- `opencell/vivarium/karr_protein_decay_light.py`
- `opencell/vivarium/karr_protein_folding.py`
- `opencell/vivarium/karr_protein_modification.py`
- `opencell/vivarium/karr_rna_modification.py`
- `opencell/vivarium/karr_trna_aminoacylation.py`
- `tests/unit/test_karr_protein_folding_strict_zero.py`
- `tests/unit/test_karr_protein_modification_strict_zero.py`
- `tests/unit/test_karr_rna_modification_strict_zero.py`
- `tests/unit/test_karr_trna_aminoacylation_strict_zero.py`
- `tests/vivarium/test_karr_protein_decay_light.py`

## Commits

1. `50821fa` - fix(scorecard): ProteinDecay replay adapter key alignment
2. `c10bb56` - fix(scorecard): ProteinFolding replay adapter key alignment
3. `99e6717` - fix(scorecard): ProteinModification replay adapter key alignment
4. `2bd9b1d` - fix(scorecard): RNAModification replay adapter key alignment
5. `212aba6` - fix(scorecard): tRNAAminoacylation replay adapter key alignment
6. `0e235ba` - docs(scorecard): refresh after 5 adapter key alignment fixes
7. `HEAD` - STATUS_fix_adapter_keys_5way.md (this commit)