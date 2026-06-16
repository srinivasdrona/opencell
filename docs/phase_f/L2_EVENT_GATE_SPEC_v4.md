# L2.event Gate Specification v4

**Status:** draft v4 (2026-06-16) - fresh DESIGN_TEMPLATE rewrite intended to supersede `docs/phase_f/L2_EVENT_GATE_SPEC.md` once ratified.
**Owner:** OpenCell whole-cell-simulation project, Phase F
**Authority:** when ratified, this document is the canonical design for the L2.event gate for `Cytokinesis` and `RibosomeAssembly`.

## DAP Intent

Contract (Beat 1):
- Required behavior: when L2.event PASSes for an in-scope process, the OC port must match Karr on event-aligned behavior over the declared cycle window, using Karr-state-conditioned one-tick probes rather than free-running replay.
- Surface inventory intent: evidence comes from the superseded v0.3 spec, the L2.2 sibling spec/catalog, the OC process ports and tests, the per-process schema/extract docs, and the PFolding v2 one-tick stress harness pattern.

Falsifiable expectation (Beat 3):
- If this design is correct, implementation will require a per-tick event-window extractor, a process-specific normalized event adapter, and a two-sample Karr-only null; an implementation that uses firing-tick-only snapshots, sparse inter-arrival grids, or bootstrap-against-fixed-Karr will fail this spec.

Inversion (Beat 4):
- Most plausible "looks right, is wrong" failure mode: the doc preserves v0.3's vocabulary but quietly reintroduces vacuous PASS by omitting explicit count floors, allowing sparse grids that miss OC-only firings, or defining event predicates against the wrong OC fields.

PM/operator sanity-check sentence:
- This design assumes the native Karr `.m` sources are canonical but not locally available in this checkout, so verified facts are restricted to local schemas/extract docs plus OC code unless Phase 0 repopulates the source tree.

## 1) Design contract

Contract:
- Required behavior: L2.event shall determine whether the OC implementation of an EVENT_CLASS process reproduces Karr's event behavior on Karr-generated pre-process states within a declared cell-cycle window.
- Why this matters: L2.2 Design-A correctly rejects these processes because tick-aligned no-event windows can produce zero-W1 fake PASS verdicts with no signal about biological correctness.
- Done = (property statement, not command success): for each in-scope process, a PASS means OC matches Karr on the process-specific informative event properties for that window: cycle-level count or incidence, event timing or hazard, and any non-redundant event payload, with explicit protection against vacuous support and spurious OC-only firings.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: the implementation compares only Karr firing ticks, so OC firings between Karr firings are invisible and the gate passes a mis-timed or over-active process.
- What would falsify this contract statement: any implementation that can return PASS when Karr has zero usable event support, when OC fires outside the fully enumerated window, or when Cytokinesis passes using only a redundant magnitude channel violates this contract.

## 2) Inventory of existing artifacts

- [A01] path=data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Cytokinesis.m | kind=code | role=canonical Karr Cytokinesis SUT path referenced by local schemas/docs; absent in this checkout and therefore a Phase 0 dependency rather than a locally verified source file.
- [A02] path=data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RibosomeAssembly.m | kind=code | role=canonical Karr RibosomeAssembly SUT path referenced by local schemas/docs; absent in this checkout and therefore a Phase 0 dependency rather than a locally verified source file.
- [A03] path=data/schemas/per_process/cytokinesis.toml | kind=schema | role=machine-checkable local schema that records Cytokinesis MATLAB source path, trace path, channel inventory, and extractor diagnostics.
- [A04] path=data/schemas/per_process/ribosome_assembly.toml | kind=schema | role=machine-checkable local schema that records RibosomeAssembly MATLAB source path, trace path, channel inventory, and extractor diagnostics.
- [A05] path=docs/karr_extracts/process/26_Cytokinesis.md | kind=doc | role=local extract of the Cytokinesis MATLAB docstring and canonical source path; evidence for single-firing division semantics.
- [A06] path=docs/karr_extracts/process/24_RibosomeAssembly.md | kind=doc | role=local extract of the RibosomeAssembly MATLAB docstring and canonical source path; evidence for repeated all-or-nothing particle formation and GTPase-driven cost.
- [A07] path=opencell/vivarium/karr_cytokinesis.py | kind=code | role=verified OC Cytokinesis port; authoritative local source for actual input stores, emitted fields, and completion predicate.
- [A08] path=opencell/vivarium/karr_ribosome_assembly.py | kind=code | role=verified OC RibosomeAssembly port; authoritative local source for actual input stores, emitted fields, and randomized 30S/50S formation behavior.
- [A09] path=tests/vivarium/test_karr_cytokinesis.py | kind=code | role=local verification surface for Cytokinesis state shape and emitted `cell.division_complete` semantics.
- [A10] path=tests/vivarium/test_karr_ribosome_assembly.py | kind=code | role=local verification surface for RibosomeAssembly complex payloads, hydrolysis byproducts, and randomized ordering.
- [A11] path=tests/vivarium/_l2_2_design_a_runner_helpers.py | kind=code | role=existing one-tick replay helper layer containing `build_state_template`, overlay/projection helpers, Karr-seed loaders, and anti-oracle guards that L2.event should reuse.
- [A12] path=docs/phase_f/l2_2_design_a/L2_2_DESIGN_A_SPEC.md | kind=doc | role=sibling authoritative spec for one-tick Karr-state-conditioned replay semantics, separate scoreboard axis, and production artifact patterns.
- [A13] path=docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml | kind=schema | role=current machine-loadable EVENT_CLASS scope source and the place where v4-driven `l2_event` fields will eventually live in a separate patch.
- [A14] path=docs/phase_f/L2_EVENT_GATE_SPEC.md | kind=doc | role=superseded v0.3 attempt whose unresolved contradictions and critique history motivate this rewrite.
- [A15] path=tests/vivarium/_substrate_stress/pfolding_stress_v2.py | kind=code | role=reference harness pattern for Karr-backed one-tick OC probes without OC-vs-OC laundering.
- [A16] path=STATUS_pfolding_convergence_v2.md | kind=status | role=prior status artifact demonstrating how a false reference design was corrected by keeping Karr as the only oracle.
- [A17] path=data/m1_sources/karr_native/README.md | kind=doc | role=local evidence that native MATLAB extractions are large, gitignored assets and that `data/m1_sources/WholeCell/` is the intended source root when populated.
- [A18] path=data/m1_sources/karr_native/V2_TRACE_MANIFEST.json | kind=schema | role=machine-checkable trace manifest showing current native-trace availability; useful as evidence that target per-seed event traces are not yet present for the two in-scope processes.

Beat-4 inversion for inventory:
- What critical artifact could still be missing from this list? The strongest missing artifact is the actual populated `data/m1_sources/WholeCell/` tree plus any existing full-cycle/event-window extractor script for these processes.
- What check did you run to reduce that risk? The repo was searched for the native `.m` paths, local `.m` files, target process traces, OC port files, catalog/spec files, and PFolding reference harness; only the schema/extract references and the local OC-side artifacts were present.

## 3) Interaction-surface map

| Surface ID | Producer | Consumer | Contract unit | Failure if mismatched | Evidence anchor |
|---|---|---|---|---|---|
| S1 | EVENT_CLASS catalog entry | MATLAB extractor | `l2_event_status`, `event_adapter_id`, window definition, input-channel list, payload definition | extractor saves the wrong ticks or wrong channels, producing non-replayable traces | [A13], this spec §5 D1/D7 |
| S2 | MATLAB extractor | event-trace artifact | per-tick channel-projected snapshot grid with cycle metadata and Karr normalized event record | firing-tick-only or sparse snapshots make hazard/timing claims untestable | [A14], [A17], this spec §5 D1/D2 |
| S3 | event-trace artifact | Python harness | schema version, per-seed tick order, declared window anchor, per-tick Karr event record | harness silently reorders or drops ticks and can miss OC-only firings | this spec §5 D1/D4, §6 C1 |
| S4 | Python replay helper layer | `opencell/vivarium/karr_cytokinesis.py` | runtime state must include `cell`, `chromosome`, `substrates`, `requests`, and `substrates_allocated` with the exact keys the port reads | harness replays a state Karr never produced or omits gating fields, causing false misses or false fires | [A07], [A09], [A11] |
| S5 | Python replay helper layer | `opencell/vivarium/karr_ribosome_assembly.py` | runtime state must include `substrates`, `rna.counts`, `protein.counts`, `complex.counts`, `requests`, and `substrates_allocated` | harness replays the wrong store shape or confuses `complexs` with emitted `complex.counts` | [A08], [A10], [A11] |
| S6 | native Karr step output | normalized event adapter | adapter-specific conversion from native Karr state delta into `{fire_count, fired, timing_tick, payload}` | MATLAB and Python classify different biological moments as the event | [A05], [A06], this spec §5 D7 |
| S7 | OC `next_update` result plus replayed state | normalized event adapter | adapter-specific conversion from OC update/runtime state into the same normalized event record schema | wrong OC field path yields false PASS/FAIL, especially on Cytokinesis and RibosomeAssembly payloads | [A07], [A08], this spec §5 D7 |
| S8 | Python harness | `result.json`, `SUMMARY.json`, `input_manifest.json`, `null_calibration.json`, `provenance.json` | stable result schema, exit-code contract, and consumed-input manifest including `--karr-source` provenance | production runs are non-reproducible or unverifiable even if the math is right | [A12], [A14], this spec §9 |
| S9 | L2.event runner | Phase F scoreboard/dashboard | separate `l2_event` axis from `l2_2_design_a`; no EVENT_CLASS process may silently fall back to the per-tick runner | fake green progress from routing event processes through the wrong harness | [A12], [A13], [A14] |
| S10 | PFolding v2 stress pattern | L2.event harness implementation | one-tick state overlay, anti-oracle file-I/O guard, and Karr-backed reference discipline | OC-vs-OC laundering or raw-update scraping reappears under a different name | [A15], [A16], [A11] |

Beat-4 inversion:
- Which cross-surface assumption is most likely false? The riskiest assumption is that channel-projected snapshots can carry every state bit the OC ports need without a hidden dependency on unprojected native state.
- What observation would expose that quickly? A phase-0 smoke where replaying a known Karr fire/no-fire tick from the saved snapshot cannot reproduce the expected OC input surface or requires an extra store not declared in the snapshot schema should fail immediately.

## 4) Baseline facts and constraints

1. `opencell/vivarium/karr_cytokinesis.py` reads `cell.ftsz_ring_complete`, `cell.division_progress`, `cell.division_complete`, `chromosome.segregation_progress`, and `substrates_allocated[karr_cytokinesis][GTP]` inside `next_update()`.
2. The same Cytokinesis port emits `cell.division_progress`, optional `cell.division_complete`, and substrate consumption on `substrates[GTP]`; it does not emit `update["events"][...]` or any `chromosome.partition_counts` payload.
3. `tests/vivarium/test_karr_cytokinesis.py` verifies that Cytokinesis completion is represented by `cell.division_complete is True` when `division_progress` reaches one, confirming the local OC event surface.
4. `opencell/vivarium/karr_ribosome_assembly.py` reads `substrates_allocated[karr_ribosome_assembly][GTP,H2O]`, `rna.counts`, and `protein.counts`, and it randomizes particle ordering with `_rng.permutation(len(self.complex_wids))`.
5. The RibosomeAssembly port emits positive counts on `complex.counts` and hydrolysis byproducts on `substrates`; it has no dedicated `events` store.
6. The RibosomeAssembly `ports_schema()` exposes both `complexs` and emitted `complex.counts`, but `next_update()` writes `complex`, so any event predicate keyed only to `complexs` would be wrong for update-time detection.
7. Local flat fixtures exist for both target processes: `data/karr_fixtures/per_process/Cytokinesis_flat.mat` and `data/karr_fixtures/per_process/RibosomeAssembly_flat.mat`.
8. Local per-seed native traces for `Cytokinesis` and `RibosomeAssembly` do not exist in this checkout under `data/m1_sources/karr_native/per_process_traces_v2_s000/...`; event-trace extraction is therefore a prerequisite, not an implementation detail.
9. The canonical Karr MATLAB source paths are recorded in `data/schemas/per_process/*.toml` and `docs/karr_extracts/process/*.md`, but the `data/m1_sources/WholeCell/...` tree is not populated locally in this worktree.
10. The Cytokinesis Karr extract describes a multi-stage bind/bend/dissociate cycle concluding when constriction completes; the RibosomeAssembly Karr extract describes repeated all-or-nothing 30S/50S formation within a single time step, not a single once-per-cycle event.
11. The existing L2.2 helper layer already contains the reusable one-tick replay primitives (`build_state_template`, `overlay_observable_into_state`, `refresh_allocator_views`, `project_observable_from_state`, `forbid_sut_oracle_file_io`).
12. PFolding stress v2 is a local cautionary baseline: a harness can report a clean green while comparing OC to itself unless Karr remains the only reference surface.
13. The operator context constrains MATLAB use to a single seat and this task prohibits MATLAB execution, production-code edits, test edits, and catalog edits.

Beat-4 inversion:
- Which baseline "fact" is inferred rather than proven? The least-proven baseline is the exact native Karr event window and event-count semantics for both processes, because the canonical `.m` files are not present locally.
- What would invalidate it? Populating the native source tree or running a phase-0 extractor pilot could show that the assumed window anchors or per-tick event counting need to change.

## 5) Decision ledger

Decision D1
- Question: what snapshot density and payload should the extractor save for event-class replay?
- Options considered:
  1) Sparse snapshot grid with stride greater than one.
  2) Full per-tick grid with raw whole-state snapshots.
  3) Full per-tick grid with channel-projected snapshots only.
- Chosen option: 3.
- Rationale: sparse grids reintroduce `G-S4` and `R3-S1` by letting OC-only firings hide between sampled ticks; full raw-state dumps are heavier than needed and blur the replay contract. Channel-projected per-tick snapshots preserve every replay-relevant input while keeping the artifact focused on the one-tick transition law.
- Tradeoffs accepted: extractor and schema work move forward in exchange for larger trace artifacts than v0.3 imagined.
- Beat-4 inversion (how chosen option could be wrong): the projected snapshot omits a hidden input store that one OC port reads indirectly, so replay correctness is only apparent.
- Falsifier (what evidence would force reopening D1): a phase-0 replay smoke cannot reconstruct a known Karr fire/no-fire tick using only the saved snapshot fields.
- Operator escalation needed? yes - QO1 (window bounds and anchor verification).

Decision D2
- Question: how should repeated-firing RibosomeAssembly timing be modeled?
- Options considered:
  1) Inter-arrival distribution as the primary timing statistic.
  2) Per-cycle event count only.
  3) Per-tick hazard or intensity over the fully enumerated window, with event count handled separately.
- Chosen option: 3.
- Rationale: RibosomeAssembly is repeated-firing and all-or-nothing per tick, so hazard or intensity is the directly observable quantity from a stride-1 grid. Inter-arrival depends on censoring and sparse-grid assumptions; count-only misses timing drift. The same infrastructure collapses cleanly to a near-singular position distribution for Cytokinesis.
- Tradeoffs accepted: more OC one-tick probes and a process-specific timing statistic split (`position W1` for Cytokinesis, hazard-distance for RibosomeAssembly).
- Beat-4 inversion (how chosen option could be wrong): hazard alignment could pass while the OC port forms the wrong particle mix at the right ticks.
- Falsifier (what evidence would force reopening D2): hazard passes but magnitude payload on `[RIBOSOME_30S, RIBOSOME_50S]` fails consistently on the same cohort.
- Operator escalation needed? no.

Decision D3
- Question: what cycle-level count or incidence rule prevents low-support false PASS?
- Options considered:
  1) Non-significant difference or "CI contains zero" logic.
  2) Distributional distance on per-seed event counts only.
  3) Distributional distance on per-seed event counts plus explicit `k_karr=0` precedence, absolute floor, and symmetric upper guard.
- Chosen option: 3.
- Rationale: `S3`, `G-M1`, and `G-M2` show that low-support events need an explicit support discipline. v4 therefore compares per-seed event-count distributions but also requires `T_oc` to stay within `[max(1, floor(0.5 * T_karr)), ceil(2.0 * T_karr)]`, where `T_*` is total fires in the cohort. If `T_karr = 0`, then `T_oc = 0` yields `NO_KARR_SUPPORT` and `T_oc > 0` is a hard FAIL.
- Tradeoffs accepted: the ratio guards are pragmatic engineering bounds rather than a biologically derived theorem.
- Beat-4 inversion (how chosen option could be wrong): count guards can pass a process that fires the right amount but in the wrong region of the cycle.
- Falsifier (what evidence would force reopening D3): the timing gate repeatedly fails on cohorts where the count gate passes, showing the count rule is too permissive on its own.
- Operator escalation needed? no.

Decision D4
- Question: what null or bootstrap design should define timing, count, and magnitude thresholds?
- Options considered:
  1) Shuffle or resample inside a single fixed Karr cohort.
  2) Bootstrap OC against a fixed Karr reference.
  3) Two-sample Karr-only cluster bootstrap matched to the exact gate statistic.
- Chosen option: 3.
- Rationale: `G-S3` and `R3-S2` require a real two-sample null. v4 treats seed as the cluster unit and resamples two independent Karr cohorts for each statistic (`count W1`, `position W1`, `hazard distance`, payload-component W1). That gives the acceptance threshold the same variance structure as the live OC-vs-Karr comparison.
- Tradeoffs accepted: more computation and more artifact detail in `null_calibration.json`.
- Beat-4 inversion (how chosen option could be wrong): even a two-sample null can be wrong if the resampling unit should be cycle fragments rather than whole seeds.
- Falsifier (what evidence would force reopening D4): Karr-vs-Karr calibration smokes exceed the nominal false-fail budget by a material margin.
- Operator escalation needed? no.

Decision D5
- Question: how should RNG be seeded across independent event-window probes?
- Options considered:
  1) Keep a persistent process RNG across the saved grid.
  2) Seed once per Karr seed and reuse it for every tick in that seed.
  3) Seed independently per `(process, seed, tick, replicate)` using `SeedSequence`.
- Chosen option: 3.
- Rationale: L2.event validates conditional one-tick behavior, not an OC free-run. Reusing a persistent RNG creates path dependence that Karr-state-conditioned replay is explicitly designed to avoid. The normative seed is `SeedSequence([L2_EVENT_VALIDATION_SEED, process_id, seed, tick, replicate])` with default `replicate = 0`.
- Tradeoffs accepted: OC's internal random stream is reproducible but not intended to mimic Karr's exact RNG order.
- Beat-4 inversion (how chosen option could be wrong): one replicate per snapshot may under-sample conditional variability for a highly stochastic state.
- Falsifier (what evidence would force reopening D5): a sensitivity pilot with `replicates_per_snapshot = 3` changes verdicts relative to the default single-replicate run.
- Operator escalation needed? yes - QO4 (replicate policy).

Decision D6
- Question: how should Cytokinesis receive a meaningful verdict when magnitude is redundant with fire/no-fire?
- Options considered:
  1) Require three informative gates and keep Cytokinesis permanently non-green.
  2) Block Cytokinesis until the OC port grows a non-redundant payload.
  3) Make the process-specific minimum informative gate set explicit: Cytokinesis passes on count plus timing, while magnitude remains non-gating until a future payload exists.
- Chosen option: 3.
- Rationale: the verified local OC port exposes `division_complete` and `division_progress`, but no non-redundant magnitude payload. Count and timing are still distinct event properties, so the gate can make a truthful, narrower claim today without pretending a third independent claim exists.
- Tradeoffs accepted: a Cytokinesis PASS in v4 is a two-claim PASS, not a magnitude-certified PASS.
- Beat-4 inversion (how chosen option could be wrong): readers may over-interpret PASS as certifying a non-existent payload surface.
- Falsifier (what evidence would force reopening D6): the result schema or final wording cannot clearly mark Cytokinesis magnitude as `not_gateable_redundant`.
- Operator escalation needed? yes - QO2 (payload augmentation policy).

Decision D7
- Question: how should event definitions be shared across MATLAB extraction and Python replay without ambiguous free-form predicates?
- Options considered:
  1) Free-form Python or MATLAB expressions stored in the catalog.
  2) YAML or JSON path expressions over each native surface.
  3) Catalog-declared adapter IDs that produce a normalized event record with a shared schema.
- Chosen option: 3.
- Rationale: the Karr native surface and the OC Vivarium surface do not share a raw path grammar. v4 therefore standardizes the cross-language contract at the normalized-record layer: each process declares `event_adapter_id`, and both MATLAB and Python implementations must emit the same record shape `{fire_count, fired, timing_tick, payload}` from native inputs.
- Tradeoffs accepted: adapter code and fixture tests become a first-class implementation task.
- Beat-4 inversion (how chosen option could be wrong): the adapter layer can drift into a silent mini-spec that nobody reviews carefully.
- Falsifier (what evidence would force reopening D7): adapter fixture tests disagree across languages, or a target process cannot be expressed with the normalized record without ad-hoc exceptions.
- Operator escalation needed? yes - QO3 (adapter ownership and location).

Finding coverage map:

| Finding IDs | v4 disposition |
|---|---|
| `S1`, `M3` | moved out of scope in §8: `FtsZPolymerization` remains deferred as a gradient process and `DNADamage` remains deferred to `L2.stress`. |
| `S2`, `G-S2`, `G-S4`, `R3-S3` | resolved by D1 plus surfaces `S1-S5`: only Karr-state-conditioned one-tick probes against a stride-1 windowed grid are allowed. |
| `S3`, `G-M1`, `G-M2` | resolved by D3: explicit `T_karr = 0` precedence, absolute floor, symmetric upper guard, and no equality-via-non-significance logic. |
| `S4`, `G-M4`, `R3-M2` | resolved by D6 and §6: PASS requires the process-specific informative gate set, and redundant magnitude cannot count for Cytokinesis. |
| `M1`, `R3-S4` | handled in §9 and §10: v4 stops claiming verified implementation or wall-clock certainty before extraction pilots and calibration smokes exist. |
| `M2`, `R3-S1` | resolved by D2: RibosomeAssembly timing is hazard-based, not inter-arrival-on-sparse-grid and not single-fire logic. |
| `M4`, `G-M3` | resolved by §4 and D7: OC field paths are verified from source, and cross-language event detection uses adapters rather than guessed paths. |
| `M5`, `M6`, `G-S3`, `R3-S2` | resolved by D3 and D4: low-support rules are explicit and all acceptance thresholds come from matched two-sample Karr-only nulls. |
| `M7`, `G-M6` | left explicit in §7/QO5 and §10/R5: calibration source must be Karr-only and is not silently inherited from v0.3. |
| `G-S1`, `G-M7`, `R3-M6` | resolved by surfaces `S1`, `S8`, §9 migration, and the required separate catalog patch plus result/provenance contract. |
| `G-M5` | resolved by D5. |
| `R3-M1` | resolved by D2, D6, and §6/C5: magnitude is specified per process and not left as an underspecified universal rule. |
| `R3-M3`, `R3-M4`, `R3-M5` | resolved by D7, §9 result contract requirements, and the removal of premature ratification claims from the design. |

## 6) Expected outcomes and verification claims

Claim C1:
- If design is correct, we should observe: every saved event-trace artifact contains a stride-1 tick grid for the declared window and no missing ticks inside that window.
- Measurement method / command / assertion: inspect per-seed metadata in `input_manifest.json` or extractor metadata for `tick_start`, `tick_end`, `stride`, and `n_ticks_saved`; assert `stride == 1` and `n_ticks_saved == tick_end - tick_start + 1`.
- Threshold or exact value: exact equality.
- Why this distinguishes from alternatives: sparse or firing-tick-only extraction violates D1 even before any statistical comparison runs.

Claim C2:
- If design is correct, we should observe: phase-0 Cytokinesis support smokes show Karr firing support in the chosen division-aligned window on the vast majority of sampled cycles.
- Measurement method / command / assertion: count `fire_count > 0` across the initial 50-cycle Cytokinesis cohort in the extracted event records.
- Threshold or exact value: at least 45 of 50 cycles must contain one Cytokinesis fire in-window; otherwise the window or adapter is wrong and QO1 must be reopened.
- Why this distinguishes from alternatives: a singular once-per-cycle process that fails this support check is not being sampled in the right regime, so any green verdict would be vacuous.

Claim C3:
- If design is correct, we should observe: the RibosomeAssembly timing statistic is non-degenerate under Karr-only calibration.
- Measurement method / command / assertion: compute the Karr-vs-Karr two-sample hazard-distance null on the first 50-seed RibosomeAssembly cohort and inspect `q95_null`.
- Threshold or exact value: `q95_null > 0` and total Karr fire ticks across the cohort is at least 50.
- Why this distinguishes from alternatives: a zero-width or ultra-sparse timing null is the signature of the degenerate bootstrap designs rejected in v0.3.

Claim C4:
- If design is correct, we should observe: Karr-vs-Karr smoke runs using the live acceptance logic fail rarely rather than systematically.
- Measurement method / command / assertion: run repeated Karr-vs-Karr smokes with independently resampled seed cohorts and compute the observed false-fail rate for each gate statistic.
- Threshold or exact value: observed false-fail rate no greater than 10 percent over 100 smoke comparisons for each statistic.
- Why this distinguishes from alternatives: a design can appear mathematically neat while being miscalibrated enough to reject Karr against itself.

Claim C5:
- If design is correct, we should observe: Cytokinesis result artifacts report magnitude as non-gateable redundancy but still permit a full process verdict from count plus timing.
- Measurement method / command / assertion: validate `result.json` for Cytokinesis against the v4 schema and inspect the per-gate verdict block.
- Threshold or exact value: `magnitude.verdict == "NOT_GATEABLE_REDUNDANT"` and process verdict is allowed to be `PASS` only when `count` and `timing` both pass.
- Why this distinguishes from alternatives: v0.3's `PARTIAL_PASS_FIRING_RATE_ONLY` language did not produce a meaningful green path for the verified OC surface.

Claim C6:
- If design is correct, we should observe: OC-only firings are measurable, stored, and capable of failing the run rather than being lost between Karr firing ticks.
- Measurement method / command / assertion: inspect the timing artifact or `result.json` diagnostics for `oc_only_fire_ticks` or equivalent off-Karr-fire accounting.
- Threshold or exact value: field present and non-null whenever OC fires on a tick where Karr does not.
- Why this distinguishes from alternatives: a firing-tick-only design can pass all basic tests while still never observing the most important false-positive mode.

Beat-4 inversion:
- How could these claims pass while design is still wrong? The likeliest hole is that the extractor and adapter agree with each other on the wrong event semantics because both inherited the same mistaken interpretation from secondary sources.
- Additional guardrail to close that hole: phase-0 must include a manual source-verification checkpoint against the repopulated native `.m` files before the first green verdict can be treated as authoritative.

## 7) Open questions for operator

QO1. What exact division-relative and growth-phase windows should v4 freeze for `Cytokinesis` and `RibosomeAssembly` once the native Karr sources are repopulated?
- Why unresolved: the canonical `.m` files are referenced locally but absent from this checkout, so exact bounds cannot be re-verified from primary source today.
- Options:
  1) Freeze the current catalog-inspired windows and only adjust if phase-0 support smokes fail.
  2) Treat window bounds as blocked until the native source tree is present and manually reviewed.
- Recommended default (if no response): 1, with QO1 automatically reopened if C2 or C3 fails.
- Risk if wrong: the gate can become vacuous or over-broad before any statistics are computed.

QO2. Should Cytokinesis be allowed to ship a green verdict on count plus timing only, or should non-redundant payload augmentation be a prerequisite?
- Why unresolved: the verified local OC port lacks a non-redundant event payload today.
- Options:
  1) Allow v4 green on the narrower two-claim contract and defer payload augmentation.
  2) Hold Cytokinesis at `BLOCKED` until an additional payload is implemented.
- Recommended default (if no response): 1.
- Risk if wrong: either the project overclaims Cytokinesis fidelity or delays a truthful but narrower gate unnecessarily.

QO3. Where should the normalized event adapters live, and who owns their cross-language fixture tests?
- Why unresolved: the design introduces adapter IDs, but the correct implementation home is a project-policy choice.
- Options:
  1) Keep adapters near the runner (`tests/vivarium/l2_event_*`) with mirrored MATLAB helper functions.
  2) Put adapters in a shared library location used by both the runner and future catalog tooling.
- Recommended default (if no response): 1 for first implementation, then revisit once more than two processes use the pattern.
- Risk if wrong: adapter drift becomes harder to detect or refactor.

QO4. Should the first implementation freeze `replicates_per_snapshot` at one, or expose higher replicate counts from day one?
- Why unresolved: D5 chooses deterministic per-snapshot seeding but leaves replicate count as a policy knob.
- Options:
  1) Freeze at one for v1 and only add higher replicate counts if sensitivity tests demand it.
  2) Expose `replicates_per_snapshot` immediately in the catalog and runner CLI.
- Recommended default (if no response): 1.
- Risk if wrong: the first implementation either hides an important sensitivity or overcomplicates calibration before it is needed.

QO5. Which Karr-only source should own `k_eng` and threshold calibration for count, timing, and payload gates?
- Why unresolved: v4 refuses circular calibration from judged OC outputs, but the repo does not yet have an established L2.event calibration panel.
- Options:
  1) Calibrate from dedicated Karr-vs-Karr event fixtures generated by the new extractor.
  2) Borrow provisional multipliers from L2.2 until event fixtures exist.
- Recommended default (if no response): 1, with provisional values clearly labeled and non-ratifying until the Karr-only panel exists.
- Risk if wrong: thresholds look precise while being statistically unjustified.

QO6. How should MATLAB extraction be scheduled under the single-seat constraint once code work begins?
- Why unresolved: this task is doc-only and current event traces are absent.
- Options:
  1) Extract Cytokinesis first, validate the schema, then queue RibosomeAssembly.
  2) Extract both processes in one longer MATLAB campaign before Python implementation starts.
- Recommended default (if no response): 1.
- Risk if wrong: the seat is tied up generating traces against a schema that still needs revision.

QO7. In the later catalog patch, should RibosomeAssembly keep `primary_channel: complexs` for backward compatibility, or should the event adapter contract explicitly migrate readers to emitted `complex.counts` terminology?
- Why unresolved: the local OC port exposes both names, and this task may not patch the catalog.
- Options:
  1) Preserve `complexs` in legacy per-tick fields but define event payloads on normalized adapter output only.
  2) Use the separate catalog patch to normalize the terminology around emitted `complex.counts`.
- Recommended default (if no response): 2.
- Risk if wrong: event predicates or payload extraction can silently target the wrong OC surface.

## 8) Scope boundary

In scope:
1. A new L2.event design for exactly two processes: `Cytokinesis` and `RibosomeAssembly`.
2. A stride-1, Karr-state-conditioned, one-tick event-window replay model.
3. A process-specific informative gate set covering count or incidence, timing or hazard, and non-redundant payload where available.
4. A normalized event-adapter contract shared by MATLAB extraction and Python replay.
5. A production-facing runner contract that includes result schema, exit codes, input manifest, null-calibration artifact, and provenance requirements.

Out of scope:
1. `FtsZPolymerization`; v0.3 already deferred it because it is a gradient process rather than a binary event candidate.
2. `DNADamage`; v0.3 already deferred it to a future `L2.stress` gate because baseline Karr cycles do not spontaneously exercise the process.
3. Any production-code edits under `opencell/**`.
4. Any existing test edits.
5. Any catalog patch; this spec can require future catalog fields but may not apply that patch itself.
6. MATLAB execution during this task.
7. Routing EVENT_CLASS processes through the L2.2 per-tick runner as a temporary fallback.

Deferred follow-ups:
1. Separate catalog patch adding `l2_event_status`, window fields, adapter IDs, and informative-gate metadata.
2. MATLAB extractor implementation and event-fixture generation.
3. Python runner and adapter implementation.
4. Optional Cytokinesis payload augmentation beyond count plus timing.
5. `L2.stress` design for `DNADamage`.

Beat-4 inversion:
- Most likely scope-creep vector: trying to solve catalog cleanup, OC port augmentation, and MATLAB extraction in the same task because the design names them.
- How this doc prevents it: every such item is explicitly deferred or listed as a migration phase owned by a later implementation task.

## 9) Migration and rollout path

Strategy:
1. Parallel-v2 design replacement. Keep `docs/phase_f/L2_EVENT_GATE_SPEC.md` untouched as historical context and add this file as the candidate authority.
2. No in-place fallback. EVENT_CLASS processes remain refused by the per-tick L2.2 runner until the v4 implementation phases complete.

What changes from v0.3:
1. Extractor contract changes from ambiguous or contradictory firing-tick language to a stride-1 event-window grid with channel-projected snapshots.
2. RibosomeAssembly timing changes from inter-arrival thinking to a hazard or intensity design on the full grid.
3. Count support becomes explicit and guarded by `T_karr = 0` precedence plus absolute lower and upper bounds.
4. Null calibration changes from degenerate or variance-mismatched bootstrap ideas to statistic-matched two-sample Karr-only calibration.
5. Cytokinesis verdict logic changes from "partial pass unless payload appears" to a process-specific informative gate set.
6. Event-definition sharing changes from underspecified path-expression ideas to normalized adapter IDs.
7. Production contract becomes mandatory: `--karr-source`, exit codes, `input_manifest.json`, `null_calibration.json`, and provenance hashes are required, not optional.

What stays from v0.3:
1. The core problem statement: L2.2 per-tick distributional gating is categorically wrong for these sparse event processes.
2. The in-scope process set: `Cytokinesis` and `RibosomeAssembly` only.
3. The Design-A coherence rule: OC may only be judged on independent one-tick probes from Karr-generated states.
4. Separate scoreboard treatment from L2.2 rather than silently folding EVENT_CLASS results into the per-tick tally.

Sequence of steps:
1. Ratify v4 and, in a later doc-only housekeeping change, mark `docs/phase_f/L2_EVENT_GATE_SPEC.md` as superseded by this file without editing its historical content.
2. Phase 0: repopulate or verify access to `data/m1_sources/WholeCell/...`, confirm final process windows, and add the separate catalog patch.
3. Phase 1a: implement the MATLAB extractor plus adapter skeleton for Cytokinesis only and run the C2 support smoke.
4. Phase 1b: extend the same extractor pattern to RibosomeAssembly and run the C3 non-degenerate timing smoke.
5. Phase 2: build the Python runner on top of the existing L2.2 helper layer and PFolding anti-oracle pattern.
6. Phase 3: run Karr-vs-Karr calibration smokes for every gate statistic and freeze provisional thresholds only after the false-fail budget is acceptable.
7. Phase 4: run OC-vs-Karr verdicts, emit the required artifacts, and wire the scoreboard to a separate `l2_event` axis.

Backout trigger and backout method:
1. Trigger: phase-0 or phase-1 smokes cannot produce non-vacuous Karr support for a process, or replay from the saved snapshot cannot reconstruct the required OC input surface.
2. Method: keep EVENT_CLASS processes in refused or blocked status, do not route them into a green scoreboard path, and reopen D1 or D7 rather than weakening the gate.

Compatibility period:
1. During implementation, two documents coexist: historical v0.3 and candidate v4.
2. The catalog continues to advertise `harness_type: event_class`, but the live runner remains unavailable until the separate implementation task lands.
3. No mixed routing is allowed; either a process is blocked for missing v4 prerequisites or it is judged by the completed L2.event runner.

Beat-4 inversion:
- How migration could strand partially-updated code: the catalog patch, extractor, and runner could land out of order, leaving EVENT_CLASS processes tagged as runnable while their artifacts or adapters do not yet exist.
- Checkpoint or guard to detect that state: the first implementation PR must require a phase checklist in CI or review that verifies catalog fields, extractor outputs, runner schema, and scoreboard routing together before any process can leave `BLOCKED`.

## 10) Risks and residual unknowns

R1. Native Karr sources remain absent when implementation begins.
- Likelihood: medium
- Impact: high
- Detection: phase-0 cannot verify window bounds or adapter semantics against the primary source tree.
- Mitigation: treat repopulating `data/m1_sources/WholeCell/` as an explicit prerequisite and do not ratify green verdicts without it.
- Owner: operator

R2. Channel-projected snapshots omit a hidden OC dependency.
- Likelihood: medium
- Impact: high
- Detection: one-tick replay from saved snapshots fails to reproduce a known Karr fire/no-fire case.
- Mitigation: phase-0 replay smoke on both target processes before large extraction campaigns.
- Owner: implementation author

R3. Cytokinesis PASS is interpreted too broadly.
- Likelihood: medium
- Impact: medium
- Detection: reviewers read PASS as certifying a magnitude surface that does not exist.
- Mitigation: keep the contract, result schema, and scoreboard wording explicit that Cytokinesis v4 certifies count plus timing only.
- Owner: spec author and operator

R4. RibosomeAssembly stride-1 windows are more expensive than expected.
- Likelihood: medium
- Impact: medium
- Detection: pilot extraction time or artifact size is materially larger than the plan can absorb.
- Mitigation: keep the saved payload channel-projected, extract Cytokinesis first, and measure before scaling.
- Owner: implementation author

R5. Threshold calibration drifts into circularity or cargo-culted L2.2 constants.
- Likelihood: medium
- Impact: high
- Detection: threshold rationale cites judged OC outputs or inherited constants without a Karr-only panel.
- Mitigation: require a dedicated event-fixture calibration artifact and keep provisional values explicitly non-ratifying.
- Owner: operator

R6. Adapter implementations diverge across MATLAB and Python.
- Likelihood: medium
- Impact: high
- Detection: cross-language fixture tests disagree on `fire_count`, `fired`, `timing_tick`, or payload.
- Mitigation: make adapter fixtures part of phase-1 acceptance, not a later cleanup.
- Owner: implementation author

R7. Catalog and spec drift again.
- Likelihood: medium
- Impact: medium
- Detection: EVENT_CLASS entries lack the v4-required fields or still encode superseded semantics.
- Mitigation: later catalog patch must quote this spec directly and land in lockstep with the first runner implementation.
- Owner: operator

## 11) Operator review checklist

1. Did the inventory list concrete artifacts and explicitly distinguish canonical-but-absent Karr sources from locally verified OC-side evidence?
2. Are the cross-surfaces explicit enough that an implementer can name the extractor artifact, adapter boundary, replay state shape, and result contract without guessing?
3. Does each major decision include options, chosen option, rationale, inversion, and falsifier?
4. Are operator choices separated from implementer work, especially on window bounds, Cytokinesis payload policy, adapter ownership, replicate count, and threshold calibration?
5. Is scope tight enough to prevent this doc from quietly turning into a catalog patch, MATLAB run, or OC-port change request?

## Acceptance bar checklist

1. [x] Design contract is stated as a system property (not "test passes").

   Section 1 defines PASS as a property of OC event-aligned fidelity on Karr-generated states and explicitly names the informative claims a green verdict is allowed to make. It does not define success as a command, a unit test, or a bootstrap script returning zero.

2. [x] Inventory manifest is present, machine-checkable, and has at least `N_inventory` entries (`N_inventory >= 8` by default).

   Section 2 lists 18 concrete artifacts in the required `path=... | kind=... | role=...` format. The list includes the superseded v0.3 attempt, primary-source proxies for the absent Karr SUT files, OC ports, tests, sibling spec, catalog, and the PFolding v2 reference harness.

3. [x] Interaction-surface map explicitly names cross-component/process/schema/store boundaries.

   Section 3 names ten boundaries spanning catalog-to-extractor, extractor-to-artifact, artifact-to-runner, replay-helper-to-port, adapter normalization, result schema, and scoreboard routing. The failure mode for each boundary is spelled out rather than left implicit.

4. [x] Every major decision has options considered, chosen option, rationale, and Beat-4 inversion.

   Section 5 contains seven decision cards, each with options, chosen option, rationale, accepted tradeoffs, inversion, falsifier, and escalation status. The decisions cover the architectural forks called out in the task prompt plus the missing count-support rule.

5. [x] Falsifiable expected outcomes are stated for the chosen design before implementation.

   Section 6 states six explicit claims with measurement methods and thresholds. Several can fail even if a harness "runs," including missing stride-1 grids, degenerate Karr-only nulls, Cytokinesis support failure, and absence of OC-only firing diagnostics.

6. [x] Open questions for operator section has at least `N_questions` entries (`N_questions = 5` default).

   Section 7 contains seven operator questions, each with why unresolved, options, recommended default, and risk if wrong. The questions isolate genuine policy forks rather than implementation chores.

7. [x] Scope boundary section clearly states in-scope and out-of-scope.

   Section 8 separates the two in-scope processes and the design surfaces they require from out-of-scope work such as `FtsZPolymerization`, `DNADamage`, catalog edits, MATLAB execution, tests, and production-code changes. Deferred follow-ups are listed separately.

8. [x] Migration/backout path is documented for existing code/artifacts.

   Section 9 defines a parallel-v2 migration strategy, names what changes and what stays from v0.3, sequences the implementation phases, and includes explicit backout triggers plus the rule that EVENT_CLASS processes remain blocked until prerequisites exist.

9. [x] Risks and residual unknowns are explicit (no silent assumptions).

   Section 10 records seven concrete risks, including absent native Karr sources, hidden snapshot dependencies, Cytokinesis overclaim risk, extractor cost, calibration circularity, adapter drift, and catalog/spec drift. The main silent assumptions from v0.3 are now surfaced as either risks or operator questions.
