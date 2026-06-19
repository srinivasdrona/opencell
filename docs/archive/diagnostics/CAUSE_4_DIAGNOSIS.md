# CAUSE_4 Diagnosis: PPI compat-overlay dict-merge clobbers unprocessed deltas

**Date:** 2026-06-05  
**Test:** `tests/vivarium/test_l2_5_ppi_ppii_v2.py` (committed `79536fb`)  
**Symptom:** PPI→PPII pair test diverges from oracle at monomer master-WID index 174, diff = 38.0 (positive), early tick.

## Root cause (single-line summary)

In `KarrProteinProcessingIProcess.next_update` (file `opencell/vivarium/karr_protein_processing_i.py`), lines 288–308 build a `protein.counts` compat-overlay by **dict-merging** `unprocessed_updates` (negative deltas) and `processed_updates` (positive deltas) over the **same WID set**. Python's `{**a, **b}` keeps `b`'s value when keys collide, so the negative half is silently dropped. PPII then reads inflated `protein.counts[wid]` as its unprocessed-monomer input pool and over-processes.

## Empirical evidence

`scripts/check_ppi_wid_overlap.py` (Windows-python OK):

```
PPI unprocessed n=482, processed n=482, positionally identical: True, set-overlap: 482
PPII unprocessed n=482
PPI.unproc ∩ PPII.unproc = 482   (every PPI input WID is also a PPII input WID)
PPI.proc   ∩ PPII.unproc = 482   (every PPI output WID is also a PPII input WID)
First 3 of each: ['MG_001_MONOMER', 'MG_002_MONOMER', 'MG_003_MONOMER']
```

PPI fixture: `unprocessedMonomerWholeCellModelIDs == processedMonomerWholeCellModelIDs` for all 482 entries. "Processed" is a stage attribute, not a name change. So `unprocessed_updates` and `processed_updates` ALWAYS have identical keys for every monomer PPI touches that tick.

## The offending code block

`karr_protein_processing_i.py:288-308`

```python
unprocessed_updates = {
    wid: -float(processed_events[i])
    for i, wid in enumerate(self.unprocessed_monomer_wids)
    if processed_events[i] > 0
}
processed_updates = {
    wid: float(processed_events[i])
    for i, wid in enumerate(self.processed_monomer_wids)
    if processed_events[i] > 0
}
if unprocessed_updates or processed_updates:
    update["protein"] = {
        "unprocessed_counts": unprocessed_updates,    # correct: negative
        "processed_counts": processed_updates,        # correct: positive
    }
    if use_protein_counts_compat:
        compat_counts_updates = {
            **unprocessed_updates,                    # OVERWRITTEN by next line
            **processed_updates,                      # only positive deltas survive
        }
        update["protein"]["counts"] = compat_counts_updates
```

## Activation condition

`use_protein_counts_compat = True` is set at line 206 when:
- `protein.unprocessed_counts` is empty / sums to 0, AND
- `protein.counts` has nonzero data for these WIDs.

L2.5 pair harness `test_l2_5_ppi_ppii_v2.py` bootstraps PPI with monomer pools in `protein.counts` only (matching the legacy single-pool convention used upstream by translation), so the compat path is hot. This is also why **isolated_replay_result: matches_oracle** held — the L2.1 isolated runner supplies `protein.unprocessed_counts` directly, never hitting the compat branch.

## Expected vs actual net delta on `protein.counts[wid]`

| | unprocessed write | processed write | net delta |
|---|---|---|---|
| **Intended** (mass conservation; monomer just changes stage) | `-events` | `+events` | `0` |
| **Actual** (dict-merge clobber) | dropped | `+events` | `+events` (phantom gain) |

At master-WID index 174, `events ≈ 38` → diff +38.0. Matches observed.

## Proposed fix (minimal)

Replace the dict-merge with an additive merge so colliding keys sum:

```python
if use_protein_counts_compat:
    compat_counts_updates: dict[str, float] = {}
    for wid, delta in unprocessed_updates.items():
        compat_counts_updates[wid] = compat_counts_updates.get(wid, 0.0) + delta
    for wid, delta in processed_updates.items():
        compat_counts_updates[wid] = compat_counts_updates.get(wid, 0.0) + delta
    if compat_counts_updates:
        update["protein"]["counts"] = compat_counts_updates
```

Net result for the always-colliding 482 monomer WIDs becomes `0` (mass-conserving), matching the intent of the compat path. The separate `unprocessed_counts` / `processed_counts` writes remain unchanged and stay correct.

## Why this didn't show up before

- L2.1 PPI isolated replay seeds `protein.unprocessed_counts` → compat path not triggered.
- L2.1 PPII isolated replay was never run in composition with a live PPI step before (only with oracle-trace inputs).
- Pre-L2.5 chassis runs probably had downstream consumers that also did dict-merge clobbers on the same WIDs, masking the phantom gain through symmetric error cancellation.

## Verification plan (post-fix)

1. Re-run `tests/vivarium/test_l2_5_ppi_ppii_v2.py` — expect `pair_replay_result: matches_oracle`.
2. Run L2.1 PPI replay (`tests/vivarium/test_l2_1_pp_i.py` or equiv) to confirm no regression on the isolated path.
3. Run L2.1 PPII replay — same.
4. Optional: add a unit test that exercises the compat branch directly with PPI alone (states have only `protein.counts`, no `protein.unprocessed_counts`).

## Risk

Very low. The fix is local to one code block, additive merge is strictly more general than dict overwrite, and the intended behavior (stage-change mass-conservation) is what the fix produces. Only risk is downstream consumers that were *relying* on the phantom gain — none expected (the L2.1 isolated paths don't hit this branch at all, and the chassis composite uses `protein.unprocessed_counts` natively).

## Citation back to GPT-5.5 critique

The critique flagged `karr_protein_processing_i.py:399-413` (`multivariate_hypergeometric` sampling) as the drift site. That call site is **upstream** of the bug — it produces `processed_events` correctly (the sampling math is fine). The bug is the **dict-merge two screens down** that loses half the deltas when writing them out via the compat overlay. The critique was directionally right about the file but off by ~100 lines on the actual line.

---

## ⚠️ UPDATE 2026-06-05 — applied fix did NOT close the test. Probe revealed actual mechanism is different.

Applied the additive-merge fix above, ran L2.5 pair test: still RED with identical diff=38 at master-idx 174. L2.1 PPI/PPII isolated tests stayed GREEN (no regression). Fix is dormant in this test path, then reverted.

### Probe results

`scripts/probe_cause_4_l25.py` (monkey-patches PPI+PPII `next_update` to log state shape) shows on call 1:

```
[PPI call 1] protein.unprocessed_counts sum=0.0 (n_keys=482), protein.counts sum=38.0 (n_keys=3)
             MG_174_MONOMER:  NOT PRESENT in protein.counts (sentinel -999)
[PPII call 1] sees protein.counts['MG_174_MONOMER'] = NOT PRESENT
[PPII call 2] sees protein.counts['MG_174_MONOMER'] = 0.0
```

### What this tells us

1. **Compat path IS hit** (consistent with the original hypothesis about which branch activates).
2. **The 38-count bootstrap is concentrated in 3 specific monomers; none of them is MG_174_MONOMER.** The dict-merge collision would only have affected those 3 keys, not master-idx 174.
3. **Master-idx 174 ≠ MG_174_MONOMER.** The harness's master-WID ordering interleaves MG_473/MG_474/MG_476/MG_477/MG_478 etc. into the MG_001..MG_482 sequence, so positional index 174 in the master list refers to some other WID (one of the 3 bootstrapped monomers, very likely).
4. **PPI does not write any delta for the WID at master-idx 174 in this test** — it's not in its compat input.

### Actual mechanism (revised hypothesis, NOT yet verified)

The diff at master-idx 174 likely arises from one of:
- **(H1)** PPII processes one of the 3 bootstrap monomers and writes +38 to `protein.processed_counts[that_wid]` (or `processedMonomers[that_wid]`), where oracle expects 0 because oracle has the upstream Translation feeding nascent monomers differently.
- **(H2)** The harness's bootstrap state is wrong — it seeds 38 monomers into `protein.counts` for 3 WIDs that the oracle never has nonzero at this point, so any PPI/PPII output on them is "extra".
- **(H3)** The harness's observable extraction maps `processedMonomers` to PPII's `protein.processed_counts` (which PPII writes), but oracle's `processedMonomers` is what MATLAB's MR.protein.processedCounts emits at a different ontology level.

(H1) is most likely. Verification would require: (a) print the 3 bootstrap WIDs by name and find their master indices; (b) print PPII's emit values for those WIDs each tick; (c) cross-reference against oracle's per-tick deltas for those master indices.

### Investment so far / remaining

- Investment: ~45 min (read PPI, read PPII, write probe, run probe, interpret).
- Remaining for full closure: 30-90 min focused work (verify which hypothesis is correct, design correct fix, run regression).
- Speculative additive-merge fix: REVERTED. Will keep the diagnosis + probe checked in as session artifacts so future work can pick this up cleanly.

### Disposition

CAUSE_4 is bigger than a 7-line in-session fix. Re-classify as a real workstream (sub-task of L2.5 PPI+PPII sweep, or stand-alone bug-fix branch) rather than an opportunistic in-flight patch on `feature/l2-2-apm-x2`. The probe script and the corrected diagnosis here are the handoff package.
Resolved by commit 04e9d93; mechanism: harness bootstrap seeded only first-process schema (missing downstream allocator keys) and mixed shared observable stores, causing CAUSE_4 pollution in PPI+PPII replay.
