# L2.5 Pair Tracker — actual pass/fail status per shared-pool pair

**Generated:** 2026-06-19 (Day 33 EOD)
**Source of truth for L2.5 status. PROCESS_STATUS_ALL_29.md L2.5 column points here.**
**Machine-loadable companion:** [`data/schemas/l25_pair_list.toml`](../../data/schemas/l25_pair_list.toml) (pair derivation, no status field)
**Catalog reference:** [`l2_2_design_a/PROCESS_CATALOG.yaml`](./l2_2_design_a/PROCESS_CATALOG.yaml) `l2_5_gate:` section

---

## Scope (from `l25_pair_list.toml`, schema_version 1.0)

| Bucket | Count | Notes |
|---|---:|---|
| **Total pairs computed** (28 choose 2) | **378** | |
| Disjoint (no shared WIDs, OUT OF L2.5 SCOPE) | 122 | No allocator contention possible; not tested |
| **L2.5 honest-required (shared-pool)** | **256** | Per-side oracle: bit-identity (det) or distributional (stoch) |
| ↳ Stochastic ↔ Stochastic (SS) | 211 | Both sides distributional |
| ↳ Deterministic ↔ Stochastic (DS) | 43 | Det side bit-identity, stoch side distributional |
| ↳ Deterministic ↔ Deterministic (DD) | 2 | Both sides bit-identity (strictest) |

## Scoreboard (Day-33 EOD)

| Status | Count | Source |
|---|---:|---|
| 🟢 **PASS** | **18** | 1 SS + 15 DS + 2 DD (was 10 at Day-32 EOD; H9 harness fix unlocked +8) |
| 🔴 FAIL | 20 | 20 DS (failure-class breakdown below) |
| ⚪ SKIPPED | 8 | 8 DS (no-op trace / sparse-event; need event-window) |
| ⬜ UNTESTED | 210 | 210 SS (only Translation+RNAProcessing wired) |
| ➖ OUT OF SCOPE | 122 | Disjoint (no shared WIDs) |
| — | — | — |
| **TOTAL** | **378** | |

---

## 🟢 PASS — 18 pairs

### SS (1)

| Pair | Test file | Notes |
|---|---|---|
| Translation + RNAProcessing | `test_l2_2_translation_plus_rna_processing_v2.py::test_l25_no_hints` | First SS green; gated by Translation evolveState port (`02e354a`) |

### DS (15) — from `test_l25_deterministic_stochastic_pairs.py`

| Pair | Day landed |
|---|---|
| ChromosomeCondensation + DNARepair | Day-32 |
| ChromosomeCondensation + Replication | Day-32 |
| ChromosomeCondensation + Translation | Day-32 |
| ChromosomeCondensation + ProteinFolding | Day-33 (H9 unlock) |
| ChromosomeCondensation + RNAProcessing | Day-33 (H9 unlock) |
| ChromosomeCondensation + tRNAAminoacylation | Day-33 (H9 unlock) |
| ChromosomeCondensation + ProteinProcessingI | Day-33 (H9 unlock) |
| ChromosomeCondensation + ProteinProcessingII | Day-33 (H9 unlock) |
| ChromosomeSegregation + DNARepair | Day-32 |
| ChromosomeSegregation + ProteinFolding | Day-32 |
| ChromosomeSegregation + Translation | Day-32 |
| ChromosomeSegregation + tRNAAminoacylation | Day-32 |
| ChromosomeSegregation + RNAProcessing | Day-33 (H9 unlock) |
| ChromosomeSegregation + ProteinProcessingI | Day-33 (H9 unlock) |
| ChromosomeSegregation + ProteinProcessingII | Day-33 (H9 unlock) |

### DD (2) — from dedicated test files

| Pair | Test file | Notes |
|---|---|---|
| ChromosomeCondensation + ChromosomeSegregation | `test_l25_chromosome_condensation_plus_segregation.py` | Originally FAILED with CAUSE_4 (predicted); now PASS after H5+H6 harness fixes |
| HostInteraction + TerminalOrganelleAssembly | `test_l25_host_interaction_plus_terminal_organelle.py` | First-try PASS |

---

## 🔴 FAIL — 20 DS pairs (Day-33 EOD)

| Stochastic process | Failing pairs | Root cause class | Next-step |
|---|---:|---|---|
| Metabolism | 3 (Cond+M, Seg+M, HostInt+M) | Karr 4-partition port required | ~150 LOC port + KB extraction |
| DNASupercoiling | 2 (Cond+DS, Seg+DS) | **H10 allocator-budget squeeze under composition** (NEW Day-33) | Diagnose H10, fix harness allocator path |
| FtsZPolymerization | 2 | "no-hints branch lacks binding/release compute" (same class as DNAS canary) | Canary-style biology port (~30-50 LOC) |
| ProteinDecay | 2 | same | same |
| ProteinModification | 2 | same | same |
| ProteinTranslocation | 2 | same | same |
| Replication | 1 (Seg+R) | same (Cond+R passed already) | same |
| ReplicationInitiation | 2 | same | same |
| Transcription | 2 | same | same |
| RNADecay | 2 | same | same |

Total: 20 (5 unique stochastic processes need biology ports + DNAS H10 harness + Metab Karr port + Replication overflow).

---

## ⚪ SKIPPED — 8 DS pairs (no-op trace / sparse-event)

Skipped because one or both processes produces a no-op trace at seed 0 in the 100-tick window. Need event-window MATLAB re-extraction (same approach as RibosomeAssembly at L2.2).

| Pair | Reason |
|---|---|
| ChromosomeCondensation + Cytokinesis | Cytokinesis no-op (post GTP fix) |
| ChromosomeSegregation + Cytokinesis | Cytokinesis no-op |
| ChromosomeCondensation + DNADamage | DNADamage radiation-gated quiescent |
| ChromosomeSegregation + DNADamage | DNADamage quiescent |
| ChromosomeCondensation + RNAModification | RNAModification no-op in window |
| ChromosomeSegregation + RNAModification | RNAModification no-op |
| ChromosomeCondensation + RibosomeAssembly | RibosomeAssembly no-op (legacy) |
| ChromosomeSegregation + RibosomeAssembly | RibosomeAssembly no-op |

---

## ⬜ UNTESTED — 210 SS pairs

Only 1 of 211 SS pairs has a test (Translation+RNAProcessing). The other 210 are listed in `l25_pair_list.toml` with `pair_oracle_complexity = "stochastic_stochastic"`.

**Plan (per-day):** scaffold the 210 SS pairs into a parametrized test file (mirror of `test_l25_deterministic_stochastic_pairs.py`) once the DS/DD failure modes have been resolved enough to give signal-not-noise.

---

## ➖ OUT OF SCOPE — 122 disjoint pairs

No shared WIDs → no allocator contention possible → no L2.5 test required. Enumerated in `l25_pair_list.toml` where `l25_honest_required = false`.

---

## Refresh discipline

Update this tracker:

- After every L2.5 pair test sweep that changes the green/red count.
- Whenever a new pair test is wired or a class of failures is reclassified.
- At end of day if any L2.5-relevant commit landed.

The tracker is human-edited (not autogenerated); the pair derivation in `l25_pair_list.toml` IS autogenerated. If the pair list changes (process added/removed, schema bumped), this tracker needs to be reconciled by hand.
