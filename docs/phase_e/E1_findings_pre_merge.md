# E.1 trajectory findings — pre-merge analysis

**Status**: drafted 2026-05-23 17:30 IST while E.1 Codex session (PID 73788) was completing its full-suite verify. The fixture pickle at `data/phase_e/v6_trajectory_32400s.pkl` was already committed at `fdea8a2` on `agent/pe-1-real-match` when this analysis ran.

**Purpose**: capture the quantitative failure modes E.1 exposed so (a) the allocation-consumer Codex turn launches with the right regression target, and (b) Phase E.2 can predict which KPs will fail before it runs.

## Headline

chassis_v6 ran the full 32400 ticks (9 simulated hours) **without crashing**. Framework correctness ✓. Biology is **broken in three diagnosed ways**, all traceable to a single root cause: the deliberate v6-turn deferral of allocation-consumer enrollment for `karr_rna_decay` and `karr_host_interaction`.

## Quantitative trajectory summary

| Tick | Time (s) | ATP | GTP | dNTP total | Cell mass (g) | Repl. state | Fork pos | mRNA | Protein |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 1.0 | 1.0 | 4.0 | 8.2e-16 | 0 | 0.0 | 339 | 16,272 |
| 100 | 100 | **-43,750** | -43,749 | **0** | 8.2e-16 | 0 | 0.0 | ~400 | ~17,000 |
| 1,100 | 1,100 | -347k | -347k | 0 | **-9e-17** | 0 | 0.0 | ~600 | ~25,000 |
| 8,100 | 8,100 | -2.55M | -2.55M | 0 | (neg) | 0 | 0.0 | 1,154 | 45,155 |
| 16,200 | 16,200 | -5.75M | -5.75M | 0 | -1.8e-14 | 0 | 0.0 | 1,146 | 61,545 |
| 32,400 | 32,400 | **-10.21M** | -10.21M | 0 | **-3.4e-14** | **0** | **0.0** | 1,261 | 91,127 |

Wall time: 2330 s (~39 min) for the full run. 325 snapshots at 100-tick stride.

## Failure modes

### F1 — Substrate pools go negative (BLOCK-RELEASE class)

- `atp_pool` crosses zero at **tick 100** and falls linearly at ~315 units/tick for the entire remaining run
- `gtp_pool` mirrors ATP (same drain mechanism)
- `dntp_pool_total` is depleted by tick 100 and never recovers (no nucleotide salvage / repolymerization wired back into the pool)
- `cell_dry_mass_g` goes negative at tick 1100 and stays negative (mass-balance is physically impossible from this point on)

**Root cause hypothesis**: `karr_rna_decay` and `karr_host_interaction` are wired in the topology and emit accumulate-deltas on substrate stores, but are NOT in `KARR_ALLOCATION_CONSUMERS`. Result: they consume ATP/dNTP without going through the request/grant cycle. Other consumers (Replication, Translation, Metabolism) respect the cycle; these two bypass it. Over 32400 ticks the unbookmarked drain compounds to ~10M units.

**Confidence**: high. The known-gap was deliberately documented in the chassis_v6 STATUS report. Quantitative trajectory matches the predicted failure mode precisely.

### F2 — Replication never initiated (CASCADE from F1)

- `replication_state_code` stuck at 0 (idle) for all 325 snapshots
- `fork_position_norm` stuck at 0.0
- No `division_event_timestamp_s` recorded
- `division_detected: False` at end of run

**Root cause hypothesis**: ReplicationInitiation's DnaA-ATP polymer formation requires ATP availability and dNTP precursors. With ATP underwater from tick 100 and dNTP empty from tick 100, the firing threshold can never be met. This is a CASCADE failure from F1 — not an independent bug in ReplicationInitiation.

**Validation step**: after fixing F1, re-check whether replication initiates. If it still doesn't, there's a second independent issue in `karr_replication_initiation.py` thresholding (currently believed unlikely; pc-t1 tests were thorough).

### F3 — Transcription/translation grow unbounded (CASCADE from F1)

- mRNA grows 339 → 1261 (3.7×) over 9 simulated hours
- Protein grows 16272 → 91127 (5.6×) over the same window

**These ratios are biologically plausible** for a cell that should have doubled (M. genitalium cycle is ~9 h). The production machinery is largely correct. The problem is that production is *not bounded by ATP availability* because the allocation cycle is consuming ghost ATP that the bookkeeping says exists but is actually negative. After F1 fixes, expect growth ratios to drop somewhat as Translation gets correctly throttled.

**Confidence**: medium. mRNA plateaus around tick 8100 (1154) and barely grows from there (to 1261 at end), suggesting RNAProcessing/RNADecay are reaching steady state internally even if the substrate accounting is broken. Protein keeps climbing because protein-decay rates are much lower than synthesis at these substrate levels.

## What E.1 establishes

**Framework correctness**: ✓
- 32400 ticks complete without crash, error, or numerical blowup
- Snapshot stride consistent at 100 ticks
- Schema v1 pickle structure valid
- E.1 comparator script (per design `docs/design/phase_e1_trajectory_match.md`) ran cleanly

**Biological fidelity**: ✗ (as expected)
- E.1 explicitly states fidelity is NOT its acceptance gate (that's E.2/E.3 territory)
- ≥1 observable passes the sanity floor — mRNA growth shape is plausible, so that satisfies the E.1 framework gate

**Net E.1 verdict**: PASS on its own terms. The "1 observable passes" sanity floor is met (mRNA growth pattern is in-range for a 9-hour Karr-equivalent run). Everything else is for E.2 to score.

## Implications for downstream work

### Allocation-consumer enrollment promoted to v1.0 BLOCK-RELEASE
- Was: v1.x cleanup item
- Now: must ship before v1.0 release
- `PROMPT_allocation_consumer.md` has been revised post-E.1 with the trajectory evidence as the regression target (must show ATP ≥0, dNTP non-empty, mass ≥0, replication advancing)

### Phase E.2 KP predictions (advance work, not gospel)

Given the trajectory state, here are the **predicted dispositions** for the 28-KP E.2 scorecard. E.2 will publish the real numbers; these are my pre-E.2 expectations:

| KP class | Count | Predicted result | Why |
|---|---|---|---|
| Substrate conservation (ATP, GTP, dNTP, AAs, H2O) | ~5 | **FAIL** (BLOCK-RELEASE bucket) | Direct F1 manifestation |
| Cell mass / total dry mass | ~2 | **FAIL** (BLOCK-RELEASE bucket) | Direct F1 manifestation |
| Replication completion / fork progression / division timing | ~4 | **FAIL** (cascade from F1) | F2 |
| DNA-related KPs (chromosome state, supercoiling, segregation) | ~3 | **FAIL** or **BLOCKED** | Downstream of replication never starting |
| Transcription rate / mRNA steady-state count | ~3 | **PASS** or near-PASS | F3 evidence shows plausible ratios |
| Translation rate / protein count | ~3 | **PASS** with high count drift | F3 — production correct but unbounded |
| Aminoacylation, processing, modification, folding KPs | ~5 | **PASS** likely | Phase B closure was tight; these run on protein machinery |
| Beyond-Karr / qualitative | ~3 | **N/A** or qualitative | Bucket convention |

**Expected E.2 verdict**: roughly **8-12 of 28 PASS**, **~12 FAIL (cascade)**, **~3 BLOCKED**, **~3 N/A**. After allocation-consumer fix lands, predicted **18-22 of 28 PASS** which would clear E.2's ≥10/28 acceptance gate.

This is **not a fatal trajectory**. It's the exact diagnostic E.2 was designed to produce, and the root cause is a single, scoped, already-queued fix.

### Phase E.2 launch timing

E.2 should still launch on the **current** chassis_v6 (NOT wait for allocation-consumer fix), because:
1. The cascade analysis above needs E.2's quantitative scorecard to validate
2. E.3 needs the BEFORE-fix discrepancy log to classify
3. After allocation-consumer lands, we can re-run E.2 in <1 hour using the cached infrastructure (fixture regeneration + extractor re-run)

Sequencing: `E.1 merge → E.2 launch (current chassis) → E.3 launch → allocation-consumer launch → E.2 re-run → E.3 re-classify → release-gate`.

## Open questions

1. After the allocation-consumer fix, does replication initiate within 9 simulated hours? Karr's published replication start time is ~30 min into the cycle (~1800 ticks). If the fix lands but replication still doesn't start, there's a separate threshold-tuning issue in pc-t1.
2. Why does mRNA plateau at ~1145-1261 (close to steady state) while protein keeps climbing linearly? Is this real Karr biology (proteins are stable, mRNA turns over) or an artifact of `karr_rna_decay` running without allocation budget? Will resolve itself when allocation lands.
3. Should we add a `protein_decay_rate_observed` KP to E.2's scorecard to catch potential over-translation independently of mass conservation? Currently the scorecard relies on cell mass to catch this; that's circular if mass itself is broken.

## Provenance

- Fixture: `E:\opencell-worktrees\pe-1-real-match\data\phase_e\v6_trajectory_32400s.pkl` (commit `fdea8a2`)
- Schema version: 1
- Chassis: v6 (commit `51aac1e` on main, 28 processes wired)
- Inspector run: 2026-05-23 17:30 IST, session `5c51d44b-5a9f-4b23-85ff-0fddaadf2212`
- This document is **advance analysis**, not a substitute for the formal E.1 report. The Codex session will produce `docs/phase_e/E1_match_report.md` with the canonical verdict.
