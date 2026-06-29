# MATLAB Extraction Inventory (Day-43 Synthesis)

Source inputs for this synthesis (no re-survey performed):
- `docs/phase_f/_inventory_tmp/consumer_callsites.txt`
- `docs/phase_f/_inventory_tmp/probe_callsites.txt`
- `docs/phase_f/_inventory_tmp/docs_mentions.txt`
- `docs/phase_f/_inventory_tmp/extract_scripts_metadata.json`
- `plan.md` Day-43 sizing/FVA reframe block and MATLAB-once intent

## 1) Executive Summary

Operator intent is explicit: renew MATLAB once, extract every dataset OpenCell can reasonably need, and avoid future license renewals. Current extraction coverage is strong for single-seed and many 100-tick multi-seed traces, but still incomplete for a "never again" MATLAB closure. The largest blockers are: (1) missing per-tick Metabolism LP oracle files (`flux`, `bounds`, `growth`) across seeds/ticks, and (2) incomplete 50-seed coverage for 9 process traces in `per_process_traces_v2_s{NNN}`. Existing assets already cover major groundwork (per-process flat fixtures, single-seed 28-process v2 traces, 50-seed ensembles for Transcription/Translation, and key metabolism snapshots). Priority order should therefore be: P0 fill direct L2.2/L2.event/L3-L5 blockers, P1 complete reference-targeted and observability-targeted extractions, then P2 full-cycle/high-volume future-proof bundles.

## 2) Existing Extractions (From `extract_scripts_metadata.json`)

| Script | Extracts | Current output coverage (seeds x ticks x processes) | Current size order |
|---|---|---|---|
| `extract_per_process_fixtures.m` | MATLAB-readable flat fixtures for process/state objects | N/A x snapshot x 44 fixtures present (`data/karr_fixtures/per_process`) | O(10 MB) total |
| `extract_per_process_traces_v2.m` | Allocator-correct before/after per-tick process traces | Single-seed: 28/28 procs at 100 ticks in `per_process_traces_v2`; multi-seed: 50 seeds but only 22/28 procs complete | O(10^1 MB) single-seed set; O(10^0 GB) seeded set |
| `extract_per_process_traces.m` | Legacy per-process traces | Single-seed: 28/28 procs at 100 ticks | O(10^1 MB) total |
| `extract_per_process_traces_fix.m` | Re-extract truncated process traces | Materialized in `per_process_traces` (single-seed fixes) | O(10^0 MB) per proc |
| `extract_per_process_traces_batch_[a-d].m` | Batch wrappers over per-process traces | Wrapper scripts; outputs represented in trace dirs above | N/A |
| `extract_transcription_ensemble.m` | 50-seed Transcription 100-tick ensemble | 50 x 100 x 1 process complete (`ensembles/transcription`) | O(10^1 MB) total |
| `extract_translation_ensemble.m` | 50-seed Translation 100-tick ensemble | 50 x 100 x 1 process complete (`ensembles/translation`) | O(10^2 MB) total |
| `extract_initial_states.m` | Process initializeState snapshots | Single-seed init states for 23 procs | O(10^2 KB) total |
| `extract_fitted_constants.m` | Per-process fitted constants | Single snapshot file present | O(10^1 KB) |
| `extract_cell_cycle_trajectory.m` | Long-run whole-cell snapshots | Single seed x 32,400 ticks target (file exists) | O(10^2 MB) |
| `extract_karr_m1_dynamics.m` | Dynamic-bound inputs and MATLAB bounds oracles | Single snapshot file present (`metabolism_dynamics.mat`) | O(10^1 KB) |
| `extract_karr_m1_flux_growth.m` | MATLAB metabolism flux + growth snapshot oracle | Single snapshot file present (`metabolism_matlab_flux_growth.mat`) | O(10^1 KB) |
| `extract_metab_flux_v3.m` | Metabolism allocated-state tick1 oracle | Seed 0 tick1 present (`metab_flux_allocated_state_s000_tick1.mat`) | O(10^1 KB) |
| `extract_metab_flux_per_tick.m` | Per-(seed,tick) metabolism LP oracle files | **Missing on disk** (`matlab_ground_truth/per_tick` absent) | Expected O(10^2 MB) at 50x100 |
| `extract_metab_flux_with_allocation.m` | Metabolism per-tick bundle (single file) | Not present | O(10^1-10^2 MB) per file |
| `extract_metab_flux_with_allocation_v2.m` | Metabolism per-tick bundle v2 | Not present | O(10^1-10^2 MB) per file |
| `extract_karr_targeted.m` | Targeted sim/KB/protein/RNA dumps | Not present (`sim_fitted_targeted.mat`, etc. missing) | Expected O(10^2 MB) |
| `extract_karr_m2v2.m` | Transcription-v2 targeted dump | Not present | O(10^0-10^1 MB) |
| `extract_karr_m3v2.m` | Translation-v2 targeted dump | Not present | O(10^0-10^1 MB) |
| `extract_karr_mats.m` | Generic flattening to `*_flat.mat` + manifest | Legacy route; no current `karr_flat` full manifest set | O(10^2 MB) depending scope |
| `extract_m3_metabolite_vocab.m` | 722-metabolite vocabulary for M3 mapping | Not present | O(10^1 KB) |
| `extract_protein_complexes.m` | Full protein-complex composition dump | Not present in `data/m1_sources/karr_flat` | O(10^0-10^1 MB) |

## 3) Consumer Audit (Grouped by fixture filename)

Fields below are "field families" observed in loader modules/callsites (including `fixture.*`, trace `states_before/states_after`, and known keys from model loaders).

### Core model fixtures

| Fixture filename | OpenCell modules loading it | Fields consumed |
|---|---|---|
| `karr_native_m1.json` + `karr_native_m1.npz` | `opencell/m1/karr_metabolism.py`, many `scripts/probe_h_*`, `probe_oc_vs_karr_lp_diff.py` | `S`, `RHS`, `lb`, `ub`, `obj`, `enz_bounds`, `catalysis`, `fluxs_stored`, reaction/substrate ID maps |
| `karr_native_m1_dynamics.json` + `.npz` | `opencell/m1/calc_flux_bounds.py`, `opencell/vivarium/karr_metabolism.py` | dynamic bounds oracles, compartment indices, external/internal exchange index sets |
| `karr_native_m1_compartmented.json` + `.npz` | `opencell/m1/compartmented.py` | compartmented stoichiometry `S(585x645x3)`, aggregate `S`, compartment maps, dry mass |
| `karr_native_m2.npz` | `opencell/vivarium/karr_observability_step.py` | RNA molecular weights and M2-linked observability arrays |
| `parameters.json` | `opencell/vivarium/karr_observability_step.py`, `opencell/vivarium/karr_request_calculators.py` | `states.Mass.dryWeightFractionDNA` and request defaults |
| `karr_archive.npz` | `opencell/vivarium/karr_translation_v3.py` | archive payload used by Translation v3 runtime |
| `karr_protein_complexes.json` | `opencell/m1/protein_complexes.py` | complex composition tables (`monomers`, `complexes`, `metabolites`, chaperones metadata) |

### Per-process fixture mats/json

| Fixture filename | OpenCell modules loading it | Fields consumed |
|---|---|---|
| `Metabolism_flat.mat` | `opencell/vivarium/karr_metabolism.py`, `opencell/m1/karr_metabolism_writeback.py`, probe stack | `substrates`, `enzymes`, `boundEnzymes`, external/internal exchange indices, ATP-hydrolysis indices, `metabolismNewProduction`, `unaccountedEnergyConsumption`, `stepSizeSec` |
| `Transcription_flat.mat` | `opencell/vivarium/karr_transcription.py` | transcription fixture struct (`counts`, enzyme/boundEnzymes families, process constants) |
| `Translation.npz` (per_process) | `opencell/vivarium/karr_composite.py` | `fixture__monomers` and translation fixture payload |
| `Chromosome_flat.mat` | `opencell/vivarium/karr_replication.py` | chromosome sparse state and replication-linked fixture fields |
| `ChromosomeCondensation_flat.mat` | `opencell/vivarium/karr_chromosome_condensation.py` | chromosome + condensation control fields |
| `ChromosomeSegregation_flat.mat` | `opencell/vivarium/karr_chromosome_segregation.py` | pole positions, segregation thresholds, chromosome state |
| `DNADamage_flat.mat` | `opencell/vivarium/karr_dna_damage.py` | damage process fixture schema + stochastic controls |
| `DNARepair_flat.mat` | `opencell/vivarium/karr_dna_repair.py` | chromosome/damage and repair kinetics fields |
| `DNASupercoiling_flat.mat` | `opencell/vivarium/karr_dna_supercoiling.py` | linking-number/supercoiling process fields |
| `Cytokinesis_flat.mat`, `FtsZRing.json`, `CellGeometry.json` | `opencell/vivarium/karr_cytokinesis.py` | cytokinesis fixture, ring and geometry dependencies |
| `FtsZPolymerization_flat.mat` | `opencell/vivarium/karr_ftsz_polymerization.py` | polymerization counts/rates |
| `HostInteraction_flat.mat` | `opencell/vivarium/karr_host_interaction.py` | host binding/attachment fields |
| `MacromolecularComplexation_flat.mat` | D2/DNA/RNA/protein pathway modules | shared complex IDs/composition used by multiple processes |
| `RibosomeAssembly_flat.mat` | ribosome + dependent process modules | ribosome assembly fixture and complex linkage |
| `ProteinActivation_flat.mat` | `opencell/vivarium/karr_protein_activation.py` | activation rules and substrate sets |
| `ProteinDecay_flat.mat` | `opencell/vivarium/karr_protein_decay_light.py`, tests | decay rates, ATP/H2O coupling, protein/complex decay reactions |
| `ProteinFolding_flat.mat` | `opencell/vivarium/karr_protein_folding.py` | chaperone indices/rates |
| `ProteinModification_flat.mat` | `opencell/vivarium/karr_protein_modification.py` | enzyme/catalysis mapping |
| `ProteinProcessingI_flat.mat` | `opencell/vivarium/karr_protein_processing_i.py` | deformylase/MAP processing fields |
| `ProteinProcessingII_flat.mat` | `opencell/vivarium/karr_protein_processing_ii.py` | peptidase/transferase processing fields |
| `ProteinTranslocation_flat.mat` | `opencell/vivarium/karr_protein_translocation.py` | translocase/SRP fixture fields |
| `Replication_flat.mat` + `ReplicationInitiation_flat.mat` | replication modules | replication complex/footprint/state fields |
| `RNAProcessing_flat.mat`, `RNAModification_flat.mat`, `Rna_flat.mat`, `tRNAAminoacylation_flat.mat` | RNA pathway modules | RNA processing/modification/catalysis state fields |
| `TranscriptionalRegulation_flat.mat` | `opencell/vivarium/karr_transcriptional_regulation.py` | regulator relations + complex linkage |
| `TerminalOrganelleAssembly_flat.mat` | `opencell/vivarium/karr_terminal_organelle_assembly.py` | localization reactions/threshold fields |

### Trace and oracle fixtures

| Fixture filename | OpenCell modules/tests/probes loading it | Fields consumed |
|---|---|---|
| `per_process_traces_v2/<Process>_100ticks.mat` | many vivarium modules/tests | `states_before`, `states_after`, `metadata` |
| `per_process_traces_v2_s{NNN}/<Process>_100ticks.mat` | L2.2 test harness + probes | seeded oracle trajectories (100 ticks) |
| `per_process_traces_v2_event_s{seed}/RibosomeAssembly_100ticks.mat` | L2 event replay test | event-window replay trace |
| `per_process_traces/<Process>_100ticks.mat` | legacy replay/probe/tests | older trace oracle format |
| `metab_flux_allocated_state_s000_tick1.mat` | metabolism probes | `flux`, `bounds`, `growth`, `pre_sub`, `post_sub`, `delta` |
| `metabolism_matlab_flux_growth.mat` | metabolism probes | snapshot MATLAB flux/growth vector |
| `Metabolism_init.mat` | probe scripts | initial substrate/enzyme state sanity checks |

## 4) Coverage Matrix

Legend: `HAVE` = materially available now, `PARTIAL` = available but incomplete for stated axis, `MISSING` = not available.

| Data type | Single-sample (single seed) | Single-sample (seeds 0-49) | Partial-trace (single seed) | Partial-trace (seeds 0-49) | 100-tick (single seed) | 100-tick (seeds 0-49) | Full-cell-cycle 50k (single seed) | Full-cell-cycle 50k (seeds 0-49) |
|---|---|---|---|---|---|---|---|---|
| Substrate state | HAVE | PARTIAL | HAVE | PARTIAL | HAVE | PARTIAL | MISSING | MISSING |
| Enzyme state / bound enzymes | HAVE | PARTIAL | HAVE | PARTIAL | HAVE | PARTIAL | MISSING | MISSING |
| FBA flux (Metabolism LP) | HAVE | PARTIAL | PARTIAL | MISSING | PARTIAL | MISSING | MISSING | MISSING |
| FBA bounds (Metabolism LP) | HAVE | PARTIAL | PARTIAL | MISSING | PARTIAL | MISSING | MISSING | MISSING |
| Allocation matrix / allocator-consistent states | HAVE | PARTIAL | HAVE | PARTIAL | HAVE | PARTIAL | MISSING | MISSING |
| RNG state / process eval order metadata | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | MISSING | MISSING |
| Chromosome sparse state | HAVE | PARTIAL | HAVE | PARTIAL | HAVE | PARTIAL | MISSING | MISSING |
| RNA state trajectories | HAVE | PARTIAL | HAVE | PARTIAL | HAVE | PARTIAL | MISSING | MISSING |
| Protein/complex state trajectories | HAVE | PARTIAL | HAVE | PARTIAL | HAVE | PARTIAL | MISSING | MISSING |
| Mass state (cell mass/biomass context) | HAVE | PARTIAL | PARTIAL | MISSING | PARTIAL | MISSING | PARTIAL (snapshot logger only) | MISSING |
| Geometry/division state | HAVE | PARTIAL | PARTIAL | MISSING | PARTIAL | MISSING | PARTIAL (snapshot logger only) | MISSING |
| Event-window traces (L2.event) | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | MISSING | MISSING |

## 5) Gap Analysis (Priority-ordered)

### P0 gaps (blockers)

#### Gap P0-1: Per-tick Metabolism LP oracle grid (flux/bounds/growth)
- Description: `data/karr_fixtures/matlab_ground_truth/per_tick/` is absent; probes currently rely on one-sample or legacy snapshots.
- Depends on: Metabolism probe suite (`probe_h_*`, `probe_oc_vs_karr_*`), L2.2 metabolism diagnostics, L3/L4 boundary-injection workflows.
- Recommended extraction scope: seeds `0..49` x ticks `1..100` x process `Metabolism` (minimum); add `1..500` as optional extension.
- Approx MATLAB compute + size: ~3-8 hours for 50x100 grid; ~0.2-0.6 GB output.

#### Gap P0-2: Incomplete 50-seed 100-tick v2 trace coverage
- Description: in `per_process_traces_v2_s{NNN}` only 22/28 processes have full 50-seed coverage; missing or near-missing are `FtsZPolymerization`, `HostInteraction`, `ProteinActivation`, `TerminalOrganelleAssembly`, `Transcription`, `TranscriptionalRegulation`, plus `Translation`/chromosome pair under-covered.
- Depends on: L2.2 ensemble fidelity, L2.event planning, cross-process replay tests.
- Recommended extraction scope: seeds `0..49` x ticks `1..100` x missing process set above.
- Approx MATLAB compute + size: ~6-16 hours; ~0.17 GB additional (based on current per-file sizes, excluding retries/failures).

#### Gap P0-3: Event-window traces (non-vacuous L2.event)
- Description: docs explicitly flag existing 100-tick windows as event-inactive for key event classes.
- Depends on: `L2_EVENT_GATE_SPEC_v4.md` acceptance path, event-class adapters/replay.
- Recommended extraction scope: seeds `0..49` x process-specific windows around real firing windows (not fixed mid-cycle 100 ticks).
- Approx MATLAB compute + size: ~4-12 hours (window dependent); ~0.2-2 GB.

### P1 gaps (current-quarter)

#### Gap P1-1: Targeted knowledge extracts not currently materialized (`karr_flat`)
- Description: `sim_fitted_targeted.mat`, `transcription_v2_targeted.mat`, `translation_v2_targeted.mat`, `protein_complexes.mat`, `m3_metabolite_vocab.mat` absent.
- Depends on: mechanism-level diagnostics, future direct-comparison probes, richer observability tooling.
- Recommended extraction scope: one-shot global extraction (no seed loop), full process/state metadata targets.
- Approx MATLAB compute + size: ~1-3 hours; ~0.2-1 GB.

#### Gap P1-2: Multi-seed chromosome-heavy process saturation
- Description: `ChromosomeCondensation` and `ChromosomeSegregation` currently 1-seed in seeded v2 dirs.
- Depends on: chromosome-primary L2.2/L2.5/L3 pairing studies.
- Recommended extraction scope: seeds `0..49` x ticks `1..100` for both processes.
- Approx MATLAB compute + size: ~2-6 hours; ~25 MB additional.

#### Gap P1-3: Metabolism deeper tick horizons
- Description: today’s trace norms and many probes center on 100 ticks; no broad 500+ tick seeded LP oracle set.
- Depends on: trajectory drift studies, robust L3/L4 confidence for longer horizons.
- Recommended extraction scope: seeds `0..49` x ticks `1..500` for Metabolism LP oracle files.
- Approx MATLAB compute + size: ~15-40 hours; ~1-3 GB.

### P2 gaps (future-proofing)

#### Gap P2-1: Full-cell-cycle process-level traces (dense, replay-grade)
- Description: current `cell_cycle_trajectory.mat` is logger snapshots, not full replay-grade per-process state tapes.
- Depends on: L4/L5 high-fidelity phenotype and long-horizon coupling audits.
- Recommended extraction scope: single seed first, ticks `1..50,000`, all 28 processes, selected state families (`substrates`, `enzymes`, `chromosome`, mass/geometry).
- Approx MATLAB compute + size: ~12-36 hours (single seed); ~10-80 GB.

#### Gap P2-2: Full-cell-cycle multi-seed archives
- Description: no 50-seed full-cycle trace archive exists.
- Depends on: L5 ensemble-level chassis phenotype claims.
- Recommended extraction scope: seeds `0..49` x ticks `1..50,000` x selected high-value processes (start with metabolism+chromosome+division).
- Approx MATLAB compute + size: multi-day/weekend runs; ~0.5-2.0 TB depending process/state breadth.

#### Gap P2-3: Explicit RNG/state-transition provenance capture
- Description: RNG seeds are often present, but explicit per-tick RNG stream state/process-order logs are not standardized outputs.
- Depends on: deterministic replay debugging and attribution in hard stochastic divergences.
- Recommended extraction scope: augment all multi-seed trace outputs with tick-level RNG/order metadata sidecars.
- Approx MATLAB compute + size: negligible compute overhead; ~1-5% storage overhead.

## 6) Forward-looking Needs (L3/L4/L5)

- Full-cycle (>=50k) extraction for at least one seed with replay-grade process/state detail.
- 50-seed full-cycle for a reduced high-value process subset (Metabolism + chromosome cluster + cytokinesis).
- Event-window specialized traces for EVENT_CLASS processes with non-vacuous windows.
- Long-horizon metabolism LP oracle archive (beyond 100 ticks) for drift studies and boundary-injection confidence.
- Standardized RNG/order provenance sidecars for every seeded trace set.
- "One-shot canonical archive" manifest that records extractor version, WholeCell source hash, MATLAB release, toolbox inventory, and per-file SHA256.

## 7) Extraction Priority Order (Tiers)

1. **P0**: Metabolism per-tick LP oracle grid (`seeds 0..49`, `ticks 1..100`) + explicit bounds/flux/growth files.
2. **P0**: Complete 50-seed 100-tick v2 traces for currently missing/undercovered processes.
3. **P0**: Event-window trace extraction for L2.event designated processes/windows.
4. **P1**: Materialize missing targeted `karr_flat` extraction outputs (`m2v2`, `m3v2`, targeted sim/KB/protein/RNA, protein complexes, m3 vocab).
5. **P1**: Extend chromosome-heavy seeded coverage and fill Translation seeded gaps in v2 traces.
6. **P1**: Extend Metabolism LP oracle horizon to 500 ticks for seeded runs.
7. **P2**: Generate replay-grade single-seed full-cycle 50k extraction bundle.
8. **P2**: Generate selective multi-seed full-cycle archives for L5 readiness.
9. **P2**: Add RNG/order provenance sidecars and canonical final extraction manifest.

