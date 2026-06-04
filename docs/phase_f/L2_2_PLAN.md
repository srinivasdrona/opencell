# L2.2 Distributional Fidelity Plan (DEEP-Only)

## §0 Status and scope

- Status: DRAFT (2026-06-04).
- This document defines the L2.2 execution plan for the 7 ALGORITHMIC-DEEP processes only.
- This scope is locked by the stochastic audit and the critique addendum.
- This plan is intentionally distributional.
- This plan is intentionally per-process.
- This plan is intentionally pre-L2.5.

### In-scope process set (7 DEEP)

1. ReplicationInitiation
2. Replication
3. DNARepair
4. Transcription
5. Translation
6. MacromolecularComplexation
7. Cytokinesis

### Explicit out-of-scope sets

- 13 ALGORITHMIC-SHALLOW processes.
- 5 TRIVIAL-RNG processes.
- 6 DETERMINISTIC processes.
- L2.5 composition harness design details beyond sequencing dependencies already documented in `docs/phase_f/L2_5_PLAN.md`.
- L3 and above.

### Provenance and gating references

- Scope source: `docs/phase_f/L2_2_STOCHASTIC_AUDIT.md`.
- Load-bearing rationale: CRITIQUE ADDENDUM in the same file.
- Critique outcome changed DEEP count from 4 to 7.
- L2.5 dependency contract source: `docs/phase_f/L2_5_PLAN.md`.
- L2.1 baseline source: `docs/phase_e/PROCESS_STATUS_ALL_29.md` (44/46 strict, 2 SKIP).

### Scope discipline statement

- This plan does not reopen bucket assignments.
- This plan does not reinterpret the critique addendum.
- This plan does not redesign SHALLOW harnesses.
- This plan does not redesign TRIVIAL no-hint checks.
- This plan does not alter L2.5 pair priority policy except sequencing implications from DEEP completion.

## §1 Methodology overview

### 1.1 What L2.2 means in this workstream

- For each DEEP process, run an ensemble of Karr MATLAB trajectories over N seeds.
- For the same process, run an ensemble of OpenCell Python trajectories over N seeds.
- At each tick, compare empirical distributions of selected observables.
- The comparison target is distributional agreement.
- The comparison target is not same-seed trajectory identity.
- The comparison target is not pointwise bit identity.
- The comparison target is not composition behavior.

### 1.2 Comparison unit definition

- Unit A: per observable, per WID, per tick, compare Karr vs OpenCell sample distributions.
- Unit B: per process, top-variance 3-WID joint check per tick.
- Unit C: process-level pass if all required Unit A and Unit B checks pass.

### 1.3 Primary statistical test choice

- Primary recommendation: per-WID two-sample KS test with Bonferroni-corrected alpha.
- Secondary guardrail: joint Wasserstein distance over top-3 most-variable WIDs.
- Rationale sentence 1: KS is simple, robust, and easy to diagnose at individual WID granularity.
- Rationale sentence 2: KS gives a clear per-WID rejection signal useful for regression localization.
- Rationale sentence 3: KS alone misses cross-WID coupling, which DEEP processes can depend on.
- Rationale sentence 4: a small joint Wasserstein check closes the coupling blind spot without full high-dimensional density estimation.
- Rationale sentence 5: top-3 variable WIDs keep compute bounded while targeting the most informative correlated surfaces.

### 1.4 Correction policy

- Global alpha per process: 0.01.
- Family size for KS correction per process: number of (tick, observable, WID) hypotheses tested in that process.
- Correction method: Bonferroni (strict, simple, operator-auditable).
- Optional reporting method (non-gating): Holm-adjusted p-values for interpretability.

### 1.5 Ensemble size policy

- Baseline N for Karr: 40 seeds per process.
- Baseline N for Python: 40 seeds per process.
- Escalation N: 80 per side when a process has borderline KS rejections concentrated near corrected alpha.
- Power intuition: for small practical effects, KS may need near-100 samples.
- Power tradeoff: for medium effects we care about in DEEP state machines, N in [20, 50] is usually informative.
- Cost-aware compromise: N=40 baseline, N=80 only for disputed boundaries.

### 1.6 Seed policy

- Seed set per process is fixed and shared conceptually, but not expected to align trajectory-by-trajectory across MATLAB and NumPy RNGs.
- Karr seed list proposal: integer seeds 0..39.
- Python seed list proposal: integer seeds 0..39.
- If N escalates, extend to 0..79.
- Do not infer equivalence from same numeric seed between engines.

### 1.7 Pass/fail thresholds

- KS gate: all required hypotheses must pass at Bonferroni-corrected alpha.
- KS effect-size reporting: include max D per observable and 95th percentile D per process.
- Wasserstein gate: for each tick, W1(OC, Karr) on top-3 WID vector must be <= calibrated threshold.
- Wasserstein threshold calibration: threshold defined as 95th percentile of Karr-vs-Karr split-ensemble baseline distance times 1.10 safety factor.
- Fail fast policy: stop process run at first hard fail for CI speed, but write full diagnostic artifacts when run in audit mode.

### 1.8 Honest limitations

- MATLAB `randStream` and NumPy `default_rng` are different RNG engines.
- Same seed does not imply same draw sequence.
- Distributional matching does not prove mechanistic identity.
- Passing marginal KS does not prove all high-order dependencies.
- Top-3 Wasserstein is a targeted, not exhaustive, multivariate guard.
- Large discrete mass-at-zero surfaces can inflate tie behavior in KS.
- For heavy zero-inflation, additional descriptive diagnostics are needed in failure reports.

### 1.9 Relationship to L2.1 and L2.5

- L2.1 remains a single-trace seam and per-tick delta-integral check.
- L2.2 (this doc) adds per-process distributional fidelity for DEEP processes.
- L2.5 composition remains paused until L2.2 green for stochastic processes participating in pairs.
- Immediate unblock value is highest for transcription and translation because of downstream pairing value.

## §2 Per-process design

## §2.1 ReplicationInitiation

### §2.1.1 RNG fingerprint (verified MATLAB line refs)

- `randomlySelectNRows` used in DnaA box sampling at `ReplicationInitiation.m:293-296`.
- Weighted `randsample` in DnaA polymer dissociation at `ReplicationInitiation.m:572`.
- Repeated `stochasticRound` in binding/polymerization limits at `ReplicationInitiation.m:602`, `622`, `633`, `658`, `678`, `689`.
- Weighted `randsample` without replacement in polymerization placement at `ReplicationInitiation.m:720` and `745`.
- Bernoulli vector branch `rand < kd1ATP/3600` at `ReplicationInitiation.m:828`.
- Iterated max-binding logic uses stochastic limit recomputation between bind/polymerize steps in `bindAndPolymerize*` flow (`ReplicationInitiation.m:584-761`).

### §2.1.2 Output state vectors to compare

- `substrates` vector for ATP/ADP/water/phosphate/hydrogen deltas from activation/inactivation/reactivation (`ReplicationInitiation.m:547-548`, `577-580`, `882-883`).
- `enzymes` vector for DnaA pools and polymer states (`ReplicationInitiation.m:549`, `581`, `733-735`, `759-761`, `849`, `880-881`).
- `boundEnzymes` effective occupancy through chromosome binding/release operations (`bindProteinToChromosome`, `releaseProteinFromSites`, `modifyProteinOnChromosome` at `ReplicationInitiation.m:772-787`, `838`, `844`).
- Chromosome DnaA occupancy summary at oriC boxes (derived from `chromosome.complexBoundSites` restricted to `dnaABoxStartPositions`).
- Aggregated oriC assembly indicators for R1-R5 occupancy state from helper-calculated status (`calculateDnaABoxStatus` path at `ReplicationInitiation.m:1133+`).

### §2.1.3 Ensemble extraction

- Extend `scripts/matlab/extract_per_process_traces_v2.m` to accept `seed_list` argument.
- Current script seeds only `uint32(0)` (`seed_simulation(sim, uint32(0))`).
- Add outer loop over seeds.
- For each seed, call `seed_simulation(sim, uint32(seed))`.
- Write per-seed output under `data/karr_ensemble/ReplicationInitiation/seed_<seed>/ReplicationInitiation_100ticks.mat`.
- Add snapshot extractor support for chromosome occupancy summary (custom serialized arrays, not raw object placeholder).
- Preserve existing `states_before` and `states_after` group names for harness compatibility.
- Add metadata fields: `rng_seed`, `seed_index`, `n_seeds_total`, `process_name`, `n_ticks`, `snapshot_schema_version`.
- Rough disk estimate: 0.3 MB per seed current schema; 1-2 MB per seed with added chromosome occupancy summaries; 40 seeds => 40-80 MB.

### §2.1.4 Python ensemble run

- Python class: `opencell.vivarium.karr_replication_initiation.KarrReplicationInitiationProcess`.
- Instantiate one process instance per seed with `{"rng_seed": seed}`.
- Use shared replay helper API (defined in §3) to run 100 ticks and emit per-seed observed vectors.
- Output path: `artifacts/l2_2_ensemble/python/ReplicationInitiation/seed_<seed>.npz`.
- Persist both raw per-tick vectors and computed diagnostics (KS stats inputs, Wasserstein inputs).
- Preserve observable naming aligned to Karr export keys.

### §2.1.5 Comparison test file

- Proposed file: `tests/vivarium/test_l2_2_replication_initiation_distributional.py`.
- Assertions:
- Assert all expected Karr seed files exist for configured N.
- Assert schema compatibility for each seed file.
- Run per-tick per-WID KS with Bonferroni correction.
- Run top-3-WID joint Wasserstein per tick.
- Fail with structured mismatch artifact including tick, WID, KS D, p-value, corrected alpha, Wasserstein value, and owning seed subsets.
- Pass criterion: no hard failures.

### §2.1.6 Effort estimate

- Total: 0.9 eng-days.
- MATLAB ensemble extraction changes: 0.25 d.
- Python ensemble runner integration: 0.20 d.
- Process-specific observable mapping and comparison test: 0.25 d.
- Debugging and diagnostics polish: 0.20 d.

### §2.1.7 Known risks

- DnaA occupancy is partially represented through chromosome object mutation, not simple vectors.
- If chromosome occupancy extraction is omitted, false-green risk rises.
- Weighted `randsample` with changing weights can amplify sensitivity to tiny indexing mismatches.
- Release/protect logic around R1-R5 boxes can produce bimodal occupancy behavior that needs robust diagnostics.

## §2.2 Replication

### §2.2.1 RNG fingerprint (verified MATLAB line refs)

- Okazaki fragment length sampling uses Poisson draw with rejection while-loop at `Replication.m:415-418`.
- Process subfunction order randomized with `randperm` at `Replication.m:606`.
- Binary limit branch uses `ceil(2 * rand())` at `Replication.m:828`.
- RNA polymerase collision stall mask uses Poisson random draw at `Replication.m:861`.
- Ligase reaction count uses `stochasticRound` at `Replication.m:1230`.
- Persistent replication state is read and updated across helper calls within single tick and across ticks (`Replication.m:692-1274`, dependent getters at `Replication.m:1301+`).

### §2.2.2 Output state vectors to compare

- `substrates` vector changes for ATP/water/ADP/phosphate/hydrogen, dNTP/diphosphate, NAD/NMN/AMP (`Replication.m:667-671`, `909-913`, `945-946`, `1085-1089`, `1244-1247`).
- `enzymes` vector changes for replisome, primase/core/beta-clamp/SSB pools (`Replication.m:675-676`, `735-746`, `951-965`, `1021-1022`, `1081-1082`, `1182-1212`, `1272-1273`).
- `boundEnzymes` occupancy projections from chromosome binding and release of helicase/pol/beta-clamp/SSB (`Replication.m:645`, `660-683`, `748-753`, `785`, `1077`, `1181`, `1187`, `1191`, `1265-1269`).
- Chromosome unwound-region and break-state summaries from `setRegionUnwound` and `strandBreaks` updates (`Replication.m:658-659`, `1146-1149`, `1172-1175`, `1242`, `1262`).
- Optional derived metrics for comparison stability:
- Active fork count.
- Mean lagging-fragment progress.
- Number of ligation events.

### §2.2.3 Ensemble extraction

- Same shared seed-loop changes as §2.1.
- Add process-specific snapshot extraction for replication structural summaries:
- `strandBreaks` sparse count and selected loci around terC and recent Okazaki boundaries.
- Bound replisome complex counts by class.
- Keep full vectors for `substrates`, `enzymes`, `boundEnzymes`.
- Output path: `data/karr_ensemble/Replication/seed_<seed>/Replication_100ticks.mat`.
- Rough disk estimate: 0.3 MB per seed current schema; 2-4 MB per seed with structural summaries; 40 seeds => 80-160 MB.

### §2.2.4 Python ensemble run

- Python class: `opencell.vivarium.karr_replication.KarrReplicationProcess`.
- Run via shared helper with fixed tick count and per-seed process re-init.
- Emit per-seed vectors and derived replication summaries mirroring Karr exporter.
- Output path: `artifacts/l2_2_ensemble/python/Replication/seed_<seed>.npz`.

### §2.2.5 Comparison test file

- Proposed file: `tests/vivarium/test_l2_2_replication_distributional.py`.
- Assertions include strict schema match for structural summary channels.
- KS per WID per tick over `substrates`, `enzymes`, and selected replication summary dimensions.
- Joint Wasserstein over top-3 variable dimensions (expected to include fork progression/break counts in non-trivial runs).
- Pass criterion: all corrected KS and Wasserstein checks pass.

### §2.2.6 Effort estimate

- Total: 1.1 eng-days.
- MATLAB extraction + structural summaries: 0.35 d.
- Python runner mapping + derived metrics: 0.25 d.
- Statistical test implementation and diagnostics: 0.30 d.
- Debugging: 0.20 d.

### §2.2.7 Known risks

- This process was promoted from SHALLOW to DEEP explicitly because of the rejection loop.
- Persistent state and helper ordering create path dependence that can look like RNG mismatch.
- Over-aggregating replication structure can hide true divergence.
- Under-aggregating can explode hypothesis count and over-penalize with Bonferroni.

## §2.3 DNARepair

### §2.3.1 RNG fingerprint (verified MATLAB line refs)

- Binary branch between Modification and Restriction order at `DNARepair.m:897-903`.
- Randomized subfunction schedule with `randperm` at `DNARepair.m:916-919`.
- Multiple `randperm` calls inside BER and pathway internals (`DNARepair.m:936`, `986`, `1299`, `1392`).
- Extensive `stochasticRound` for pathway reaction capacities (`DNARepair.m:960`, `997`, `1037`, `1064`, `1153`, `1241`, `1330`, `1468`, `1516`, `1549`).
- Multi-pathway state machine with BER, NER, HR, polymerize, ligate, modification, restriction, DisA (`DNARepair.m:906-915`).

### §2.3.2 Output state vectors to compare

- `substrates` vector including dNMP pools, water/hydrogen, lesion substrate channels, and pathway-specific consumption/production (`DNARepair.m:970`, `1023`, `1051`, `1078`, `1179`, `1189-1204`, `1270`, `1351`, `1439`, `1482`, `1529`, `1562`).
- Chromosome damage-state arrays:
- `damagedBases` (`DNARepair.m:972`, `1217`, `1527`).
- `abasicSites` (`DNARepair.m:973`, `1216`, `1262`, `1445`).
- `gapSites` (`DNARepair.m:1049`, `1076`, `1215`, `1260-1261`, `1444`).
- `strandBreaks` (`DNARepair.m:1009`, `1019`, `1048`, `1075`, `1214`, `1355`, `1446-1447`, `1480`, `1560`).
- `intrastrandCrossLinks` (`DNARepair.m:1218`, and related pruning at `1385`).
- `hollidayJunctions` (`DNARepair.m:1264-1265`, `1354`).
- `enzymes` and `boundEnzymes` aggregate vectors as carried by process-level stores.

### §2.3.3 Ensemble extraction

- Add dedicated DNARepair snapshot adapter in MATLAB extractor.
- Adapter emits compact encoded chromosome-damage vectors (sparse coordinate form preferred).
- Keep per-tick `substrates`, `enzymes`, `boundEnzymes` arrays.
- For chromosome channels, write deterministic field order and integer dtype normalization.
- Output path: `data/karr_ensemble/DNARepair/seed_<seed>/DNARepair_100ticks.mat`.
- Rough disk estimate: 0.7 MB per seed current schema; 5-12 MB per seed with chromosome damage channels; 40 seeds => 200-480 MB.

### §2.3.4 Python ensemble run

- Python class: `opencell.vivarium.karr_dna_repair.KarrDNARepairProcess`.
- Shared helper executes process per seed and gathers equivalent encoded chromosome-damage channels.
- Output path: `artifacts/l2_2_ensemble/python/DNARepair/seed_<seed>.npz`.
- Use shared serializer to keep channel naming and sparse encoding identical to Karr side.

### §2.3.5 Comparison test file

- Proposed file: `tests/vivarium/test_l2_2_dna_repair_distributional.py`.
- Assertions:
- Validate chromosome channel schema and encoding invariants.
- Run KS per scalar dimension in encoded channels.
- Run Wasserstein on top-3 variable encoded dimensions per tick.
- Emit targeted failure artifacts with pathway marker tags (BER/NER/HR/etc) when mappable.
- Pass criterion: all corrected checks pass.

### §2.3.6 Effort estimate

- Total: 1.3 eng-days.
- MATLAB chromosome-channel extraction work: 0.45 d.
- Python mirror encoding and runner wiring: 0.30 d.
- Statistical test and diagnostics: 0.30 d.
- Debugging and validation: 0.25 d.

### §2.3.7 Known risks

- DNARepair has the highest branching complexity of the seven.
- Small encoding mistakes in sparse chromosome channels can look like biology divergence.
- Zero-heavy lesion channels may require tie-aware interpretation for KS outputs.
- Repair pathways can be near-inactive in some seeds; must differentiate no-op from mismatch.

## §2.4 Transcription

### §2.4.1 RNG fingerprint (verified MATLAB line refs)

- RNAP state transition sampling via weighted `randsample` at `Transcription.m:494`.
- Iterated rejection-like loops in binding selection at `Transcription.m:502-503` and `535-536`.
- Polymerase queue randomization via `randperm` at `Transcription.m:672-673`.
- Multiple stochastic rounds for transition counts at `Transcription.m:686`, `709`, `731`, `803`.
- Termination down-selection order randomized at `Transcription.m:927`.
- Additional rejection loop over mature RNA weight in initialization routine at `Transcription.m:597-598`.

### §2.4.2 Output state vectors to compare

- `substrates` vector for NTP use and byproducts:
- NTP consumption through polymerize call (`Transcription.m:895-897`).
- Water/hydrogen terminal effects (`Transcription.m:950-951`).
- Diphosphate production (`Transcription.m:962-964`).
- `enzymes` / `boundEnzymes` for transcription factors and RNAP pools (`Transcription.m:967-972`).
- Nascent RNA output vector `RNAs` (TU-indexed) via updates at `Transcription.m:934-938` and state transfer in `copyToState` at `Transcription.m:360-364`.
- RNAP internal state summaries (counts by state class from `rnaPolymerases.states`, bound TU/progress summaries from `transcripts.*` at `Transcription.m:667-910`, `953-957`).

### §2.4.3 Ensemble extraction

- Extend MATLAB extractor `pick_snapshot_properties` to include `RNAs` explicitly.
- Add custom scalar summary channels for RNAP state counts and transcript progress distributions.
- Current generic property list omits several transcription-specific internal structures.
- Keep existing per-tick tap semantics (`before` after copyFrom+allocation, `after` after evolveState).
- Output path: `data/karr_ensemble/Transcription/seed_<seed>/Transcription_100ticks.mat`.
- Rough disk estimate: 0.3 MB per seed current schema; 2-5 MB per seed with RNAP state summaries and RNA vectors; 40 seeds => 80-200 MB.

### §2.4.4 Python ensemble run

- Python class baseline: `opencell.vivarium.karr_transcription.KarrTranscriptionProcess`.
- If the operator elects v3 parity target, allow class override to `KarrTranscriptionV3Process` with same helper API.
- Seed plumbing through process config `{"rng_seed": seed}`.
- Output path: `artifacts/l2_2_ensemble/python/Transcription/seed_<seed>.npz`.

### §2.4.5 Comparison test file

- Proposed file: `tests/vivarium/test_l2_2_transcription_distributional.py`.
- Assertions:
- KS over substrate, enzyme, and RNA output dimensions.
- KS over RNAP state-summary dimensions.
- Top-3 Wasserstein over highest-variance dimensions, expected to include RNA output and RNAP-state channels.
- Report includes process-class identifier to prevent silent version drift.
- Pass criterion: all corrected checks pass.

### §2.4.6 Effort estimate

- Total: 1.0 eng-days.
- MATLAB extractor augmentation: 0.30 d.
- Python runner + class-target pinning: 0.20 d.
- Statistical test implementation: 0.30 d.
- Debugging: 0.20 d.

### §2.4.7 Known risks

- Existing L2.1 harness for transcription already needed projection/hint overrides.
- Distributional tests without RNAP internal summaries could miss core state-machine drift.
- Overly granular RNAP per-polymerase dimensions can create noisy multiplicity explosion.
- Recommended mitigation: compare state-count summaries, not raw per-index identities.

## §2.5 Translation

### §2.5.1 RNG fingerprint (verified MATLAB line refs)

- Weighted mRNA binding via `randsample` at `Translation.m:760`.
- Elongation and termination queue randomization via `randperm` at `Translation.m:691` and `814`.
- tmRNA branch Bernoulli at `Translation.m:866`.
- Random nascent length initialization in setup path at `Translation.m:512`.
- Additional weighted sampling in initialization and maintenance routines (`Translation.m:492`, `544`).

### §2.5.2 Output state vectors to compare

- `substrates` vector for GTP/GDP/water/phosphate/hydrogen (`Translation.m:907-911`).
- `enzymes` and `boundEnzymes` vectors for translation factors and ribosome pools (`Translation.m:889-900`).
- `monomers` output vector incremented on successful termination (`Translation.m:836`).
- tRNA/tmRNA state vectors (`freeTRNAs`, `aminoacylatedTRNAs`, `freeTMRNA`, `boundTMRNA`, `aminoacylatedTMRNA`) from updates at `Translation.m:896`, `899-900`, `904`.
- Ribosome state summaries from `rib.states`, `rib.boundMRNAs`, `rib.mRNAPositions`, `rib.tmRNAPositions` sync at `Translation.m:883-886`.
- Aborted polypeptide event counts via `pol.abortedPolypeptides` append path at `Translation.m:839-841`.

### §2.5.3 Ensemble extraction

- Extend MATLAB extractor to include translation-specific properties beyond generic list:
- `freeTRNAs`.
- `aminoacylatedTRNAs`.
- `freeTMRNA`.
- `boundTMRNA`.
- `aminoacylatedTMRNA`.
- Add ribosome/polypeptide summary channels as compact aggregates.
- Output path: `data/karr_ensemble/Translation/seed_<seed>/Translation_100ticks.mat`.
- Rough disk estimate: 1.2 MB per seed current schema; 4-8 MB per seed with tRNA/ribosome summaries; 40 seeds => 160-320 MB.

### §2.5.4 Python ensemble run

- Python class: `opencell.vivarium.karr_translation_v3.KarrTranslationV3Process`.
- Seed plumbing through process config as in existing L2.1 tests.
- Output path: `artifacts/l2_2_ensemble/python/Translation/seed_<seed>.npz`.
- Use shared helper to extract identical summary channels as MATLAB side.

### §2.5.5 Comparison test file

- Proposed file: `tests/vivarium/test_l2_2_translation_distributional.py`.
- Assertions:
- KS over core vectors (`substrates`, `enzymes`, `boundEnzymes`, `monomers`).
- KS over tRNA/tmRNA summary channels.
- KS over ribosome-state summary channels.
- Top-3 Wasserstein over most variable dimensions per tick.
- Emit targeted diagnostics for tmRNA-branch related channels when divergence clusters there.
- Pass criterion: all corrected checks pass.

### §2.5.6 Effort estimate

- Total: 1.1 eng-days.
- MATLAB extraction expansion: 0.35 d.
- Python summary extraction and mapping: 0.25 d.
- Statistical test wiring and reporting: 0.30 d.
- Debugging: 0.20 d.

### §2.5.7 Known risks

- Translation has large state dimensionality; naive per-ribosome per-position checks are not tractable.
- Existing substrate projection mismatch history (26 Karr vs 20 OC) must be made explicit and stable.
- tmRNA branch probability can create rare-event drift requiring enough seeds.
- Aggregation choice is critical: too coarse hides mismatch, too fine destabilizes multiplicity.

## §2.6 MacromolecularComplexation

### §2.6.1 RNG fingerprint (verified MATLAB line refs)

- Monte Carlo assembly loop starts at `MacromolecularComplexation.m:340`.
- Cumulative probabilities recomputed each loop at `MacromolecularComplexation.m:342-343`.
- Complex selection by inverse-CDF random draw at `MacromolecularComplexation.m:349`.
- Sequential resource depletion after each draw at `MacromolecularComplexation.m:355-356`.
- This dynamic reweighting is the DEEP promotion trigger from critique addendum.

### §2.6.2 Output state vectors to compare

- `complexs` vector update from new complex formation (`MacromolecularComplexation.m:312`).
- `substrates` vector depletion by complex composition (`MacromolecularComplexation.m:313`).
- `enzymes` and `boundEnzymes` remain pass-through in current L2.1 pattern, but still exported for consistency.
- Derived competition-network summaries:
- Per-network number of complexes formed.
- Residual substrate mass per network.

### §2.6.3 Ensemble extraction

- Current extractor already captures `complexs` and `substrates` when present in properties.
- Add network-summary channel computed from `complexNetworks` partition index arrays.
- Add seed-loop and per-seed directory outputs.
- Output path: `data/karr_ensemble/MacromolecularComplexation/seed_<seed>/MacromolecularComplexation_100ticks.mat`.
- Rough disk estimate: 0.9 MB per seed current schema; 1-2 MB per seed with network summaries; 40 seeds => 40-80 MB.

### §2.6.4 Python ensemble run

- Python class: `opencell.vivarium.karr_macromolecular_complexation.MacromolecularComplexationProcess`.
- Seed plumbing through `{"rng_seed": seed}`.
- Output path: `artifacts/l2_2_ensemble/python/MacromolecularComplexation/seed_<seed>.npz`.

### §2.6.5 Comparison test file

- Proposed file: `tests/vivarium/test_l2_2_macromolecular_complexation_distributional.py`.
- Assertions:
- KS over `complexs` and `substrates` dimensions.
- KS over network-summary channels.
- Wasserstein over top-3 high-variance complex/network dimensions.
- Pass criterion: all corrected checks pass.

### §2.6.6 Effort estimate

- Total: 0.7 eng-days.
- MATLAB seed-loop + network summary channels: 0.20 d.
- Python runner mapping: 0.15 d.
- Test and diagnostics: 0.20 d.
- Debugging: 0.15 d.

### §2.6.7 Known risks

- Sequential depletion makes this process sensitive to tiny ordering differences.
- Competition networks can have sparse events; low-activity seeds need careful handling.
- If only aggregate totals are compared, false-green risk is high.

## §2.7 Cytokinesis

### §2.7.1 RNG fingerprint (verified MATLAB line refs)

- Membrane-binding Bernoulli checks at `Cytokinesis.m:184` and `193`.
- Dissociation Bernoulli checks at `Cytokinesis.m:206` and `246`.
- Hydrolysis Bernoulli check at `Cytokinesis.m:224`.
- Sequential state-dependent updates over ring substates across `Cytokinesis.m:184-248`.
- This is a Markov-chain style transition process with state-updated rates/eligibility.

### §2.7.2 Output state vectors to compare

- `substrates` vector for water/phosphate/hydrogen updates (`Cytokinesis.m:229-231`).
- `enzymes` / `boundEnzymes` for FtsZ pools (`Cytokinesis.m:186-187`, `195-196`, `210-214`, `234-235`, `251-254`).
- Ring structural state summaries:
- `numEdgesOneStraight` (`Cytokinesis.m:188`, `197`).
- `numEdgesTwoStraight` (`Cytokinesis.m:198`, `225`).
- `numEdgesTwoBent` (`Cytokinesis.m:226`, `247`).
- `numResidualBent` (`Cytokinesis.m:207`, `248`).
- Geometry state summary:
- `geometry.pinchedDiameter` update at `Cytokinesis.m:239`.

### §2.7.3 Ensemble extraction

- Add Cytokinesis-specific summary extraction from `ftsZRing` and `geometry` state objects.
- Keep `substrates`, `enzymes`, `boundEnzymes` vectors.
- Export per-tick scalar ring-state channels alongside core vectors.
- Output path: `data/karr_ensemble/Cytokinesis/seed_<seed>/Cytokinesis_100ticks.mat`.
- Rough disk estimate: 0.25 MB per seed current schema; 0.5-1 MB per seed with ring/geometry summaries; 40 seeds => 20-40 MB.

### §2.7.4 Python ensemble run

- Python class: `opencell.vivarium.karr_cytokinesis.KarrCytokinesisProcess`.
- Seed plumbing through process config.
- Output path: `artifacts/l2_2_ensemble/python/Cytokinesis/seed_<seed>.npz`.
- Ensure canonical WID mapping for cytokinesis substrate/enzyme channels is explicitly pinned, following current L2.1 pattern.

### §2.7.5 Comparison test file

- Proposed file: `tests/vivarium/test_l2_2_cytokinesis_distributional.py`.
- Assertions:
- KS over substrate/enzyme channels.
- KS over ring structural summaries and pinched diameter channel.
- Wasserstein over top-3 varying ring/chemistry channels.
- Pass criterion: all corrected checks pass.

### §2.7.6 Effort estimate

- Total: 0.7 eng-days.
- MATLAB ring-summary extraction: 0.20 d.
- Python mirror extraction: 0.15 d.
- Test implementation: 0.20 d.
- Debugging: 0.15 d.

### §2.7.7 Known risks

- Cytokinesis often appears near-no-op under gated upstream states in some runs.
- No-op seeds must be treated as valid samples, not silently dropped.
- Small count channels can produce high-variance empirical CDFs for low N.
- Risk of overfitting to canonical WID overrides if not cross-checked against source state mapping.

### §2 effort rollup (DEEP-only)

- ReplicationInitiation: 0.9 d.
- Replication: 1.1 d.
- DNARepair: 1.3 d.
- Transcription: 1.0 d.
- Translation: 1.1 d.
- MacromolecularComplexation: 0.7 d.
- Cytokinesis: 0.7 d.
- Total: 6.8 eng-days.

## §3 Cross-cutting infrastructure

### 3.1 MATLAB ensemble extraction script changes

- Base script to extend: `scripts/matlab/extract_per_process_traces_v2.m`.
- Current constraints observed:
- Only single seed (`uint32(0)`) is used.
- Output path is single-process flat file under `data/m1_sources/karr_native/<output_subdir>/`.
- Snapshot property picker is generic and limited.
- Object values sanitize to string placeholders and lose state detail.

### 3.1.1 Required script/interface changes

- Add args:
- `seed_list` (vector of integer seeds).
- `output_root` (optional, default `data/karr_ensemble`).
- `n_ticks` (keep existing default 100).
- `process_names` (existing behavior retained).
- Optional `snapshot_profile` argument keyed by process name.

### 3.1.2 Required runtime behavior changes

- For each process:
- For each seed in `seed_list`:
- Bootstrap fresh simulation.
- Seed via `seed_simulation(sim, uint32(seed))`.
- Run tap loop for `n_ticks`.
- Save per-seed output file.
- Directory layout:
- `data/karr_ensemble/<Process>/seed_<seed>/<Process>_<n_ticks>ticks.mat`.

### 3.1.3 Required metadata changes

- Keep `process_name`.
- Keep `n_ticks`.
- Keep `rng_seed`.
- Add `seed_index`.
- Add `n_seeds_total`.
- Add `snapshot_profile_name`.
- Add `schema_version`.
- Add `export_git_sha` if available.

### 3.1.4 Snapshot schema guidance

- Preserve `states_before` and `states_after` naming for compatibility.
- For vector observables, keep one MATLAB cell entry per tick.
- For custom summary channels, use deterministic field names.
- For sparse chromosome structures, use integer index/value arrays per tick.
- Avoid storing raw MATLAB objects.

### 3.2 Python ensemble runner helper

- New helper file proposed: `tests/vivarium/l2_2_distributional_common.py`.
- Purpose: shared engine for loading per-seed Karr files, running per-seed Python process trajectories, and computing distributional tests.

### 3.2.1 Suggested API sketch

```python
@dataclass
class DistributionalConfig:
    process_name: str
    process_cls: type
    observables: tuple[str, ...]
    summary_extractors: dict[str, Callable]
    seed_list: list[int]
    n_ticks: int = 100
    alpha: float = 0.01
    wasserstein_topk: int = 3


def run_distributional_replay(config: DistributionalConfig) -> DistributionalResult:
    ...


def ks_with_bonferroni(samples_a: np.ndarray, samples_b: np.ndarray, alpha: float, family_size: int) -> KSResult:
    ...


def joint_wasserstein_topk(samples_a: np.ndarray, samples_b: np.ndarray, topk_indices: np.ndarray) -> WassersteinResult:
    ...
```

### 3.2.2 Expected helper responsibilities

- Load all Karr seed files for one process.
- Validate schema and seed coverage.
- Run Python process for same seed list.
- Build per-tick sample matrices by observable/WID.
- Compute KS statistics and corrected p-values.
- Compute Wasserstein top-3 checks.
- Emit structured artifacts for CI and human debug.

### 3.3 Karr seed handling contract

- MATLAB side:
- Use process simulation seed via existing `seed_simulation` plumbing.
- Confirm each export file records seed in metadata.
- Python side:
- Pass explicit seed through process config.
- Recreate process instance per seed.
- Do not reuse RNG state across seeds.

### 3.3.1 Current extractor seed status

- `extract_per_process_traces_v2.m` currently hardcodes `uint32(0)`.
- It requires a new seed-list parameter.
- It requires output path expansion to avoid overwrite/skip collisions.

### 3.4 Output schema contract

- One file per `(process, seed)`.
- Same field names across processes for shared channels.
- Optional process-specific summary channels under namespaced keys.
- Tick axis always length `n_ticks`.
- Vector axis dimensions must be stable across seeds within process.

### 3.4.1 Readability requirements

- Files must be readable from Python with `h5py` without ad-hoc transforms.
- Schema version recorded in metadata.
- Integer count channels should round-trip as numeric vectors without float-noise ambiguity where possible.

### 3.5 Diagnostic artifact requirements

- For each failed process run, write:
- `failure_summary.json`.
- `ks_failures.csv`.
- `wasserstein_failures.csv`.
- Optionally sampled per-tick histograms for top failing channels.

## §4 Execution sequencing

### 4.1 Recommended process order

1. Translation.
2. Transcription.
3. DNARepair.
4. Replication.
5. ReplicationInitiation.
6. MacromolecularComplexation.
7. Cytokinesis.

### 4.1.1 Rationale

- Translation and Transcription have highest L2.5 unblock value.
- Both are already high-visibility in current L2.5 pair discussions.
- DNARepair is complex and benefits from early infrastructure hardening but is less immediate for pair unblock.
- Replication and ReplicationInitiation share chromosome extraction infrastructure; doing them back-to-back reduces context switching.
- MacromolecularComplexation is deep but narrower state surface.
- Cytokinesis has lower immediate pairing urgency per current L2.5 sequencing notes.

### 4.2 Milestone slicing

- M1: cross-cutting infra and one reference process (Translation).
- M2: second high-value process (Transcription) to validate reuse.
- M3: branch-heavy DNARepair.
- M4: replication pair (Replication + ReplicationInitiation).
- M5: MacromolecularComplexation + Cytokinesis.
- M6: full DEEP closure sweep and docs/status update.

### 4.3 Parallelism opportunity

- Yes, all 7 process tracks can be split across worktrees.
- Shared risk: MATLAB ensemble extraction I/O contention if all seeds regenerate simultaneously.
- Shared risk: schema drift if each track edits extraction schema independently.
- Recommended parallel pattern:
- One owner track for extraction schema and shared helper.
- Process tracks consume frozen schema and implement process-specific summaries/tests.

### 4.4 Worktree and resource tradeoffs

- Pros:
- Calendar compression.
- Independent debugging loops.
- Reduced context switching per contributor.
- Cons:
- Merge coordination overhead.
- Duplicate MATLAB regeneration costs.
- Higher chance of inconsistent per-process summary encodings if contracts are not locked early.

### 4.5 Calendar estimate

- Optimistic: 4.5 calendar days (strong parallelism, few schema regressions).
- Realistic: 6-7 calendar days (moderate parallelism, one to two rework loops).
- Pessimistic: 9-10 calendar days (schema churn + borderline statistical disputes requiring N escalation).

## §5 Pass/fail gates for L2.2 closure

### 5.1 Process-level gate

- For each DEEP process:
- All configured observables and summary channels are present and schema-valid.
- KS tests pass at all ticks for all WIDs under Bonferroni-corrected alpha.
- Wasserstein top-3 checks pass at all ticks.
- All configured seeds completed with no missing files.

### 5.2 Aggregate DEEP gate

- All 7 DEEP processes pass process-level gate.
- No unresolved schema exceptions.
- No unresolved diagnostic classed as harness bug.
- Result state: `L2.2 ALL GREEN (DEEP scope)`.

### 5.3 L2.5 unblock contract

- Any L2.5 pair containing one of the 7 DEEP processes is unblocked only after that process is L2.2 green.
- Full DEEP-green means no DEEP-based L2.5 blockers remain.

### 5.4 Failure policy

- Single hard fail in any DEEP process keeps that process red.
- Borderline statistical cases trigger N escalation to 80 before final verdict.
- If still failing at N=80, file remains red and requires mechanistic debug.

## §6 Out-of-scope (explicit)

- The 5 TRIVIAL no-hint tests.
- The 13 SHALLOW Python-only ensemble harness workstream.
- The 6 DETERMINISTIC processes.
- L2.5 composition harness implementation details (covered in `L2_5_PLAN.md`).
- L3 and higher ladder rungs.

## §7 Open questions

### 7.1 Carry-over from audit Q1-Q4

#### Q1 (carry-over): wrong-lambda-right-shape acceptance for TRIVIAL/SHALLOW

- Does not block this DEEP-only plan drafting.
- Does affect broader L2.2 closure narrative.
- Recommendation: accept critique addendum direction and handle TRIVIAL via separate no-hint tests, SHALLOW via separate harness.
- Owner input needed: yes (policy-level).

#### Q2 (carry-over): handling L2.1-SKIPPED processes in L2.2

- RibosomeAssembly and RNAModification are SHALLOW, not DEEP.
- Recommendation: defer from this DEEP plan and track in SHALLOW workstream.
- Owner input needed: yes, because sequencing preference impacts downstream reporting.

#### Q3 (carry-over): tRNAAminoacylation boundary classification

- Not part of DEEP scope here.
- Recommendation: leave classification as in critique-governed bucket table; do not reopen in this doc.
- Owner input needed: no for this plan.

#### Q4 (carry-over): parallel vs sequential execution for DEEP

- Recommendation: parallel after M1 infra lock.
- Owner input needed: yes (resource allocation and integration preference).

### 7.2 New DEEP-plan-specific questions

#### Q5: Which transcription class is canonical for L2.2 distributional gate (`karr_transcription` vs `karr_transcription_v3`)?

- Recommendation: default to `karr_transcription` for continuity with current L2.1 replay gate, report class in artifacts, and optionally shadow-run v3 non-gating.
- Owner input needed: yes.
- **Decision (2026-06-05, operator-confirmed):** Use **v1 = `KarrTranscriptionProcess`** (`opencell/vivarium/karr_transcription.py`) imported directly in the L2.2 ensemble runner. No v3 shadow.
  - Rationale: v1 is the trace-trust Karr-port (`_substrate_deltas_from_hint`, `_bound_enzyme_deltas_from_hint`, fixture-backed; 695 LOC, fresh June-4 commits `7473bd0` / `edaa781` closing L2-replay alignment). v3 is a scope-reduced mechanism approximation built on `opencell.m2.transcription_v2` (223 LOC, last meaningful commit `5638f69` "declare scope reduction") and was never aiming for L2-replay parity — it bypasses the trace and predicts from analytic curves. The two processes answer different questions (replay-faithful port vs runnable mechanism for whole-cell chassis); conflating them in L2.2 would smear the gate's signal.
  - Composite note: `karr_composite.py:210` aliases `karr_transcription → KarrTranscriptionV3Process` for whole-cell runs. This is a chassis runtime decision (no trace-data mid-simulation) and is **not** a statement that v3 is the L2 target. L2.2 instantiates v1 directly, matching the existing L2.1 replay-test pattern (each test imports its target process, no composite indirection).
  - No code change required for this decision — codex's L2.2 §2.6 already assumes v1.

#### Q6: For Replication and DNARepair, should gate include raw chromosome sparse channels or only derived summaries?

- Recommendation: include both minimal raw sparse channels and compact summaries.
- Owner input needed: no (implementation authority within this workstream).

#### Q7: Should Wasserstein threshold be absolute or bootstrap-calibrated per process?

- Recommendation: bootstrap-calibrated from Karr split-ensemble baseline with 1.10 margin.
- Owner input needed: no.

#### Q8: Should Bonferroni family be per-process global or per-observable?

- Recommendation: per-process global for strictness and audit simplicity.
- Owner input needed: no.

#### Q9: Should no-op seeds be retained in sample distributions?

- Recommendation: yes, retain no-op seeds; they are valid stochastic outcomes under gated state.
- Owner input needed: no.

### 7.3 Explicit question requested in prompt

- Question: should the two L2.1-SKIPPED SHALLOW processes (RibosomeAssembly, RNAModification) be deferred or included now in L2.2 despite L2.1 skip?
- Recommendation: defer from DEEP plan and execute in SHALLOW workstream after trace extension or alternate non-no-op initialization policy is ratified.
- Owner input needed: yes.

### 7.4 Open-question count summary

- Total open questions listed: 9.
- Questions requiring operator input: 5.
- Questions within implementation authority: 4.

## §8 Change log

- Entry 1: Created 2026-06-04, scoped to 7 DEEP processes per audit `da9a4b3` + critique addendum `bb5716c`.
