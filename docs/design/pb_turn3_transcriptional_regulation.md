# Phase B Turn 3 — TranscriptionalRegulation

**Status**: design ready · **Estimated wall**: 35 min · **Karr process**: `Process_TranscriptionalRegulation`

## Why this is Phase B Turn 3

After tRNAAminoacylation (Phase B T1) and RibosomeAssembly (Phase B T2) close the protein-synthesis input side, TranscriptionalRegulation is the first process that **modifies the kinetic rates of an already-running process** (M2v3 transcription). It introduces:

- TF-promoter binding state (a new persistent state variable)
- TF-mediated fold-change modulation of M2v3's per-gene transcription rates
- The cleanest test of "can our chassis carry kinetic-parameter feedback between processes"

Small scale (per Karr docstring): **5 transcription factors, 29 regulated transcription units, 31 TF-TU relationships**. Manageable but algorithmically distinct from anything Phase A built.

## Algorithm (per docstring §Simulation, lines 101-106)

```
For each TF species:
  - Identify free copies of this TF (not yet bound to any promoter)
  - Identify promoters for this TF that aren't already bound by this TF species
  - Randomly bind free TFs to available promoters, weighted by per-promoter affinity
  - At most 1 copy of this TF binds each promoter (rule #4)

After binding update:
  - For each TU, compute fold_change_total = ∏ over bound TFs of (TF.fold_change_for_this_TU)
  - M2v3's transcription rate for that TU is multiplied by fold_change_total
```

This couples bidirectionally to M2v3:
- TranscriptionalRegulation READS `protein.counts.<TF_wid>` (TF copies available)
- TranscriptionalRegulation WRITES `tf_binding.<TF>.<TU>` (a new store) and `tx_rate_fold_change.<TU>` (multiplier)
- M2v3 READS `tx_rate_fold_change.<TU>` and multiplies its per-TU baseline rate

## Critical: M2v3 modification required

This is the FIRST turn that requires modifying an existing v3 process — M2v3 must read the new fold-change store and apply it. Options:

**Option A**: Modify `karr_m2_v3.py` in place to read the new store (with a default of 1.0 if not wired).

**Option B**: Build `karr_m2_v4.py` with the regulation wiring; keep v3 untouched.

**Recommendation**: **Option A with default=1.0**. The store is optional; if `tx_rate_fold_change.<TU>` is absent, M2v3 uses 1.0 (no regulation). Backwards-compatible. Keeps complexity bounded.

## Empirical fixture findings

Inspect `data/karr_fixtures/per_process/TranscriptionalRegulation_flat.mat`. Expected fields:
- `transcriptionFactorWholeCellModelIDs` (5 strings)
- `transcriptionUnitWholeCellModelIDs` (29 strings)
- `tfPromoterAffinityMatrix` (5 × 29 — affinity weights)
- `tfTuFoldChangeMatrix` (5 × 29 — fold-change effects)
- `promoterBindingSiteCounts` (per TU, often 1)

If field names differ, inspect at implementation time using the standard pattern.

## ports_schema

```python
{
    "protein": {
        "counts": {
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
            for wid in self.tf_wids  # 5 TF copies (read-only)
        }
    },
    "tf_binding": {
        # New store — one entry per (TF, TU) pair indicating bound count (0 or 1)
        tf_wid: {
            tu_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
            for tu_wid in self.tu_wids
        }
        for tf_wid in self.tf_wids
    },
    "tx_rate_fold_change": {
        # M2v3 reads this
        tu_wid: {"_default": 1.0, "_updater": "set", "_emit": True}
        for tu_wid in self.tu_wids
    },
}
```

**Note on `_updater: "set"` for `tx_rate_fold_change`**: single-writer store (only TranscriptionalRegulation writes it), so set is safe and semantically correct (full overwrite each tick).

## Scope

**Net new files**:
1. `opencell/vivarium/karr_transcriptional_regulation.py` (~200 LOC)
2. `tests/vivarium/test_karr_transcriptional_regulation.py` (~180 LOC)

**Modified files**:
3. `opencell/vivarium/karr_m2_v3.py` — add optional read of `tx_rate_fold_change.<TU>` store, multiply baseline rate. Default 1.0 when store absent (backwards-compatible).

## Test plan

1. **test_fixture_loads**: 5 TFs, 29 TUs, 31 relationships
2. **test_no_free_tfs_no_binding_change**: zero free TF copies → no binding update
3. **test_high_affinity_tf_binds_first**: with 1 TF copy and 2 promoters of different affinity, TF binds higher-affinity promoter (stochastic but biased)
4. **test_one_copy_per_tf_per_promoter**: 10 free copies of same TF + 1 promoter → exactly 1 binds
5. **test_fold_change_multiplicative**: 2 TFs bound to same TU, each with fold_change 2.0 → tx_rate_fold_change = 4.0
6. **test_m2v3_reads_fold_change** (integration): chassis with M2v3 + TranscriptionalRegulation; verify M2v3 emits delta proportional to fold_change × baseline_rate
7. **test_unbinding_recovers_baseline**: when TF unbinds (TF.counts → 0 next tick), tx_rate_fold_change returns to 1.0
8. **test_steady_state_binding_fraction**: from snapshot state, after 100 ticks, ~50% of TFs are bound (Karr's "high affinity, stable binding" suggests >50%; pin at >40% as acceptance)
9. **test_no_regression_m2v3_without_regulation** (regression): M2v3 alone (no TR wired) behaves bit-identical to pre-modification

## M2v3 modification spec (minimal)

```python
# In KarrTranscriptionV3Process.next_update, after computing synth_per_s baseline:
fold_changes = states.get("tx_rate_fold_change", {})
if fold_changes:
    multipliers = np.array(
        [float(fold_changes.get(tu_wid, 1.0)) for tu_wid in self.tu_wids],
        dtype=float,
    )
    synth_per_s = synth_per_s * multipliers
# ... rest unchanged
```

Add `"tx_rate_fold_change"` as an optional port in `ports_schema` (with `_default: 1.0`, `_updater: "set"`, only-read). If TR isn't wired, the store gets default 1.0 for all TUs.

## Acceptance criteria

- All 9 tests pass
- No regressions in A3.3 tests (32 tests), Phase B T1 (9 tests), Phase B T2 tests (9 tests)
- Commit: `pb-t3: TranscriptionalRegulation + M2v3 fold-change wiring`

## Out of scope

- Modeling transcription factor synthesis dynamics (TFs are just proteins; M3v3 handles their synthesis)
- Wiring into chassis_v4 builder (separate turn)
- Modeling promoter occupancy at fine resolution (binary bound/unbound is sufficient per Karr)
- Modeling co-binding sterics beyond multiplicative fold-change

## Phase B remaining turns

| Turn | Process | New mechanism |
|---|---|---|
| pb-t4 | RNAProcessing | Pre-rRNA + pre-tRNA cleavage from precursor RNAs |
| pb-t5 | RNAModification | Methylation, pseudouridylation of t/rRNAs |
| pb-t6 | ProteinProcessingI | N-terminal Met cleavage, signal peptide cleavage |
| pb-t7 | ProteinProcessingII | Diacylation, isoprenylation |
| pb-t8 | ProteinModification | Phosphorylation, acetylation |
| pb-t9 | ProteinFolding | Chaperone-mediated folding (groEL, dnaK) |
| pb-t10 | ProteinTranslocation | Sec-system membrane insertion |
| pb-t11 | ProteinActivation | Activation reactions for selected enzymes |
| pb-final | build_karr_chassis_v4 | Full Phase B integration + extended ratchet validation |
