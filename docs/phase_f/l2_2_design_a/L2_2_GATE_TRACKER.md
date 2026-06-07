# L2.2 Design-A Gate Tracker

**Living document.** Updated as each process's L2.2 Design-A gate progresses from missing-data → ready → RED → GREEN. Maintain until all in-scope processes are GREEN (= L2.2 complete = L2.5 unblocked).

| Metadata | |
|---|---|
| **Owner** | Copilot session 5c51d44b (orchestrator) |
| **Started** | 2026-06-06 |
| **Last updated** | 2026-06-06T15:30+05:30 |
| **Companion catalog** | [`PROCESS_CATALOG.yaml`](./PROCESS_CATALOG.yaml) |
| **Companion audit** | [`../L2_2_STOCHASTIC_AUDIT.md`](../L2_2_STOCHASTIC_AUDIT.md) |
| **Design rationale** | [`./L2_2_DESIGN_A_SPEC.md`](./L2_2_DESIGN_A_SPEC.md) (v1.3, frozen for implementation) |

## Legend

| Symbol | Status | Meaning |
|---|---|---|
| ⬛ | OUT-OF-SCOPE | DETERMINISTIC (no RNG) → L2.1 sufficient, no Design-A test needed |
| 🟦 | OPTIONAL | TRIVIAL-RNG → L2.1 lambda-integral is primary; Design-A is a cross-check only |
| ⬜ | MISSING-DATA | In-scope, but Karr fixtures (per_process_traces_v2) not extracted for the required seed set |
| 🟧 | MISSING-EXTRACTOR | In-scope, but the MATLAB extractor doesn't emit this process's fields yet |
| 🟨 | READY | Karr fixtures + OC module available; awaiting Design-A harness implementation or first gate run |
| 🟥 | RED | Gate ran under Design-A; W1 threshold breached. Has open investigation. |
| 🟩 | GREEN | Gate passes under Design-A. Process is L2.5-eligible. |
| ⏸️ | BLOCKED | Has an explicit prerequisite (e.g., L2.1 trace fix) before gate can run |

## Top-line status

| Bucket | Total | OUT-OF-SCOPE | MISSING-DATA | MISSING-EXTRACTOR | READY | RED | GREEN | BLOCKED |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ALGORITHMIC_DEEP | 4 | — | 4 | 0 | 0 | 0 | 0 | 0 |
| ALGORITHMIC_SHALLOW | 14 | — | 12 | 0 | 0 | 0 | 0 | 2 |
| TRIVIAL_RNG | 4 | — | 4 | 0 | 0 | 0 | 0 | 0 |
| DETERMINISTIC | 6 | 6 | — | — | — | — | — | — |
| **Totals** | **28** | **6** | **20** | **0** | **0** | **0** | **0** | **2** |

(BLOCKED count includes RNAModification and RibosomeAssembly: both need the L2.1 trace fixed from no-op state before any Design-A run is meaningful.)
(In-scope total: 22 processes. SB-5 resolved 2026-06-06: TRIVIAL-RNG kept as confirmation tier. Bucket tally corrected 2026-06-06 via spec critique: 4+14+4=22, not 4+13+5.)
(Event-channel deferral, 2026-06-06: ReplicationInitiation.chromosome and Cytokinesis.chromosome are flagged `event_channels` in catalog. The *other* output channels on those two processes gate normally; only the listed event channel is deferred to L2.event. FtsZPolymerization was considered for the same treatment but rejected — its polymerization is gradual, not a single firing event with a distinct channel.)

## Shared blockers (resolve once, unblocks many)

| ID | Blocker | Affects | Owner | Status | Notes |
|---|---|---|---|---|---|
| **SB-1** | Design-A harness rewrite: per-tick state reset in `_l2_2_ensemble_runner.py` + per-tick `load_fitted_init_from_mat` in `l2_replay_common.py` | ALL 17 in-scope processes | Copilot → Codex | NOT STARTED | Hard prerequisite for any gate. Spec → `./L2_2_DESIGN_A_SPEC.md`. |
| **SB-2** | Invoke `extract_per_process_traces_v2.m` with the full 17-process list (or empty for all 28). Script is **already general** — F5.1b just happened to pass `{'Translation'}` explicitly. **Per-seed cost = ~30s × 17 processes ≈ 8-10 min/seed** (sequential within one seed; bootstraps sim once per process). | All in-scope | Codex (MATLAB) | NOT STARTED | No script changes needed for the loop itself. |
| **SB-2a** | **CONFIRMED PARTIAL_BUG** (codex audit 2026-06-06, `STATUS_sb2a_audit.md`). Case-sensitivity for `RNAs` is real: 4 in-scope processes (Transcription, RNADecay, ProteinDecay, RibosomeAssembly) declare capital `RNAs` and silently get dropped. **Plus** 14 additional state-bearing property omissions across 11 unique names across 7 processes (Translation drops 6 of 10 state props — `mRNAs`, `freeTRNAs`, `freeTMRNA`, `aminoacylatedTRNAs`, `aminoacylatedTMRNA`, `boundTMRNA`; RNAProcessing drops `intergenicRNAs`; ProteinFolding drops `unfoldedComplexs`/`foldedComplexs`; ProteinProcessingII drops `signalSequenceMonomers`). 11 of 22 processes are clean. | 11 of 22 processes affected (severity varies: Translation worst) | Codex (MATLAB) | **AUDIT DONE; FIX PENDING** | Recommended FIX_DIFF in STATUS lines 1217-1238: extend allowlist with the 11 missing names + capital `RNAs`. One-spot edit. Verify post-fix: re-extract seed 0 for all 22 in-scope; confirm `metadata.snapshot_properties` non-empty per process. |
| **SB-3** | Seeds 11..49 not extracted for any non-Translation process (Translation has 0..10). | ALL in-scope processes | Codex (MATLAB) | NOT STARTED | After SB-2 + SB-2a land: 50 seeds × 17 processes × 30s ≈ 7 hours sequential, ~2 hours if fanned out 4-way across MATLAB licenses. Embarrassingly parallel. |
| **SB-4** | W1 threshold recalibration: existing thresholds were tuned against Design-B coupled trajectories. Under Design-A, noise floor is much lower; need empirical recalibration on a known-good channel (e.g., DETERMINISTIC pseudo-run or TRIVIAL-RNG Metabolism) before any RED verdict is interpreted. | All gates | Copilot | DEFERRED | First-pass: 3-5× empirical noise floor. Revisit after first 2-3 gates land. |
| **SB-5** | TRIVIAL-RNG: skip, keep as optional, or run all? | 5 processes | Operator | **RESOLVED 2026-06-06: KEEP ALL 5** | Metabolism additionally serves as SB-4 noise-floor anchor (run first). |
| **SB-6** | L2.1 trace fix for `RNAModification` and `RibosomeAssembly` (currently no-op traces). | 2 processes | Codex | NOT STARTED | Track in main L2.2 plan, not this tracker. Mention for visibility. |

## Per-process status

### 🔴 ALGORITHMIC_DEEP (4 processes — full Design-A ensemble required)

| Process | Status | M | N | Karr seeds available | Karr seeds needed | Missing | Open RED cause | Owner | Updated |
|---|---|---:|---:|---|---|---|---|---|---|
| **Translation** | ⬜ MISSING-DATA | 100 | 50 | 0..10 (11) | 0..49 (50) | 39 more seeds | n/a (no Design-A run yet; Design-B last run: W1max=38,775 substrates RED, but Design-B is wrong harness) | Codex (SB-2,SB-3) | 2026-06-06 |
| **Transcription** | ⬜ MISSING-DATA | 100 | 50 | 0..10 (11) for Translation only — Transcription NOT extracted | 0..49 (50) | 50 seeds × extractor extension for Transcription fields | Codex (SB-2,SB-3) | n/a | Codex | 2026-06-06 |
| **ReplicationInitiation** | ⬜ MISSING-DATA | 200 | 50 | 0 | 0..49 (50) | 50 seeds × extractor extension | Codex (SB-2,SB-3) | n/a | Codex | 2026-06-06 |
| **DNARepair** | ⬜ MISSING-DATA | 200 | 50 | 0 | 0..49 (50) | 50 seeds × extractor extension | Codex (SB-2,SB-3) | n/a | Codex | 2026-06-06 |

### 🟠 ALGORITHMIC_SHALLOW (13 processes — Design-A ensemble, lighter)

| Process | Status | M | N | Karr seeds available | Karr seeds needed | Missing | Notes | Owner | Updated |
|---|---|---:|---:|---|---|---|---|---|---|
| **Replication** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension | | Codex | 2026-06-06 |
| **DNASupercoiling** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension | | Codex | 2026-06-06 |
| **RNAProcessing** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension | | Codex | 2026-06-06 |
| **RNAModification** | ⏸️ BLOCKED | 100 | 50 | 0 | 0..49 | L2.1 trace fix (SB-6) + 50 seeds | Trace currently no-op | Codex (SB-6 first) | 2026-06-06 |
| **RNADecay** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension | Day-18 lift done; Design-A pending | Codex | 2026-06-06 |
| **tRNAAminoacylation** | ⬜ MISSING-DATA | 50 | 50 | 0 | 0..49 | 50 seeds × extractor extension | Boundary TRIVIAL/SHALLOW; defaulted SHALLOW | Codex | 2026-06-06 |
| **ProteinModification** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension | | Codex | 2026-06-06 |
| **ProteinFolding** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension | | Codex | 2026-06-06 |
| **ProteinDecay** | ⬜ MISSING-DATA | 200 | 50 | 0 | 0..49 | 50 seeds × extractor extension | Day-19 trace-hint GREEN masks complexity; Design-A is real test | Codex | 2026-06-06 |
| **ProteinTranslocation** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension | | Codex | 2026-06-06 |
| **MacromolecularComplexation** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension | | Codex | 2026-06-06 |
| **RibosomeAssembly** | ⏸️ BLOCKED | 200 | 50 | 0 | 0..49 | L2.1 trace fix (SB-6) + 50 seeds | Trace currently no-op | Codex (SB-6 first) | 2026-06-06 |
| **FtsZPolymerization** | ⬜ MISSING-DATA | 200 | 50 | 0 | 0..49 | 50 seeds × extractor extension + seed bias toward pre-division window | Sparse outside division | Codex | 2026-06-06 |
| **Cytokinesis** | ⬜ MISSING-DATA | 100 | 50 | 0 | 0..49 | 50 seeds × extractor extension + seed bias toward division window | Sparse outside division | Codex | 2026-06-06 |

### 🟦 TRIVIAL_RNG (4 processes — Design-A confirmation tier; in-scope per SB-5 2026-06-06; tRNAAminoacylation listed under SHALLOW)

| Process | Status | M | N | Karr seeds available | Karr seeds needed | Missing | Notes | Owner | Updated |
|---|---|---:|---:|---|---|---|---|---|---|
| **Metabolism** | ⬜ MISSING-DATA | 20 | 50 | 0 | 0..49 | 50 seeds (via SB-2/SB-3) | **PRIORITY**: also serves as SB-4 noise-floor anchor. Run FIRST under Design-A. | Codex | 2026-06-06 |
| **DNADamage** | ⬜ MISSING-DATA | 20 | 50 | 0 | 0..49 | 50 seeds | Rare-event; may yield INSUFFICIENT_SAMPLES at M=20 (acceptable). | Codex | 2026-06-06 |
| **ProteinProcessingI** | ⬜ MISSING-DATA | 20 | 50 | 0 | 0..49 | 50 seeds | Cross-process consistency for monomer counts. | Codex | 2026-06-06 |
| **ProteinProcessingII** | ⬜ MISSING-DATA | 20 | 50 | 0 | 0..49 | 50 seeds | Cross-process consistency for monomer counts. | Codex | 2026-06-06 |
| **(tRNAAminoacylation)** | (held in SHALLOW per audit Q3 — see SHALLOW table) | | | | | | | | |

### ⬛ DETERMINISTIC (6 processes — no Design-A test)

| Process | Notes |
|---|---|
| ChromosomeCondensation | No RNG in MATLAB source. L2.1 sufficient. |
| ChromosomeSegregation | No RNG. L2.1 sufficient. |
| HostInteraction | No RNG. L2.1 sufficient. |
| ProteinActivation | No RNG. L2.1 sufficient. |
| TerminalOrganelleAssembly | No RNG. L2.1 sufficient. |
| TranscriptionalRegulation | No RNG. L2.1 sufficient. |

## Workstream plan (proposed parallel codex fanout)

Once `L2_2_DESIGN_A_SPEC.md` is written and success/failure criteria are defined, fire these in parallel worktrees:

| Codex | Workstream | Scope | Deps | ETA |
|---|---|---|---|---|
| **C1: Harness rewrite** | SB-1 | Per-tick reset in `_l2_2_ensemble_runner.py` + per-tick `load_fitted_init_from_mat`. Update `test_l2_2_translation.py` to point at `per_process_traces_v2` (Design-A source). | none | ~45 min |
| **C2: Extractor fix + first pass** | SB-2a + SB-2 (seed 0) | (a) Audit + fix `pick_snapshot_properties` allowlist for case sensitivity (add `RNAs`, `Monomers`, `Complexs`, etc.). (b) Re-extract seed 0 for all 17 in-scope processes; verify each .mat has non-empty `metadata.snapshot_properties`. | none | ~30 min |
| **C3: Seed regeneration (deep, fanout)** | SB-3 | Run fixed extractor for seeds 1..49 × the 4 DEEP processes. Output: `per_process_traces_v2_s{001..049}/{Translation,Transcription,ReplicationInitiation,DNARepair}_100ticks.mat`. Translation seeds 1..10 already exist; skip-on-exists is built into the script (line 59-62). | C2 done | ~60 min if fanned 4-way |
| **C4: Seed regeneration (shallow, fanout)** | SB-3 | Same as C3 for 11 in-scope SHALLOW processes (excluding the 2 BLOCKED). | C2 done | ~3 hours if fanned 4-way, parallel with C3 if MATLAB licenses permit |
| **C5: First Design-A gate run** | gate-1 | Run Design-A Translation gate (requires C1 + C2 + C3 done) and report W1max per channel. | C1+C2+C3 | ~10 min |
| **C6: Threshold recalibration (SB-4)** | calibration | Run pseudo-deterministic baseline; compute noise floor; propose new thresholds. | C5 result | ~30 min |

## Update protocol

When any cell in this tracker changes:

1. Update the cell + bump `Updated` column to today's date.
2. Update top-line status table tallies if a status moved buckets.
3. If a process flips to GREEN, log to `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` via the `log-decision` skill (slug: `l2-2-design-a-<process>-green`).
4. When all in-scope processes are GREEN, archive this tracker (rename `L2_2_GATE_TRACKER_FINAL.md`) and unblock L2.5.

## History

| Date | Event |
|---|---|
| 2026-06-06 | Tracker created. All 22 in-scope processes MISSING-DATA. Harness rewrite (SB-1) is the universal gate for all Design-A runs. |
| 2026-06-06 | SB-2 fact-checked: extractor is already general (accepts process_names list or auto-grabs all 28). SB-2a added: case-sensitivity bug in `pick_snapshot_properties` allowlist must be fixed before fan-out. |
| 2026-06-06 | SB-2a codex audit complete (`STATUS_sb2a_audit.md`, verdict PARTIAL_BUG). Case-sensitivity for `RNAs` confirmed (4 processes); also 14 additional state-bearing omissions across 11 unique property names across 7 processes. Translation worst (drops 6 of 10 state-bearing props). 11 of 22 processes clean. Recommended FIX_DIFF in STATUS lines 1217-1238. |
| 2026-06-06 | SB-5 resolved: KEEP all 5 TRIVIAL-RNG in scope. Metabolism prioritized as SB-4 noise-floor anchor. In-scope count 17 → 22. |
| 2026-06-06 | `L2_2_DESIGN_A_SPEC.md` v1 drafted (15 sections). Codex GPT-5 critique returned NEEDS_REVISION (4 HIGH + 4 MED). Spec rewritten as v1.1: channel-level (not process-level) event-deferral; Karr-only null bootstrap replaces flawed half-split max; OC-side bootstrap CI added; allocator-diff approximation cut (extractor v2 cannot support it); 5-channel calibration panel replaces single-Metabolism anchor; INSUFFICIENT_SAMPLES verdict added; `worst_samples` fake-pairing diagnostic removed; F1-F9 root-cause taxonomy with multi-label allowed; 16 reproducibility pins via `provenance.json`. Catalog tally fixed: 4+14+4=22 (was 4+13+5). Event channels declared on ReplicationInitiation.chromosome and Cytokinesis.chromosome only. |
| 2026-06-06 | Spec v1.2: codex critique-v2 returned narrower NEEDS_REVISION (4 HIGH + 3 MED + 1 LOW). All 8 deltas applied: §1.4 explicit supersession of audit-addendum bucket counts; §3.2 channel-schema with `aggregation` rules; §3.3 sample-size justification; §4.1 `SeedSequence([L2_2_VALIDATION_SEED, s, t])` replaces `hash()`; §4.4(b) two-sample cluster bootstrap CI; §5.2 reframed allocator artifact as input-snapshot; §6.0 narrowed marginal claim; §6.4 joint Spearman-correlation diagnostic for `joint_check: true` (non-gating); §7.2 adaptive `absolute_floor`; §7.3 per-bucket `k_eng` + DEEP rep on panel; §7.4 `thresholds.json` schema; §8.2 `NO_GATEABLE_CHANNELS` verdict + primary≠event invariant; §9.3 4-group taxonomy A/B/C/D with F10 latent-state class added and F8 demoted to non-L2.2-inferable; §11 closed-form analytical check promoted MAY→SHOULD; §12 `--seeds` int-or-CSV; §13 `input_manifest.json` / `null_calibration.json` / `analytical_check.json`; §14 (OS, BLAS) caveat + input-artifact SHA-256. Catalog: `joint_check: true` on MacromolecularComplexation; Cytokinesis `primary_channel` chromosome→substrates. v3 critique fired. |
| 2026-06-06 | **Spec v1.3 frozen.** Codex critique-v3 returned SHIP_WITH_MINOR_FIXES (2 HIGH + 3 MED + 1 LOW, all lockstep / no design changes). All 6 deltas applied in-session: header DRAFT v1.1→v1.3; §2.2 stale `hash((s,t))` replaced with `SeedSequence` reference; §3.3 `0.05 × σ_Karr` quantitative claim softened; §4.2 `requirements.txt`→`pyproject.toml`; §7.3 panel aligned to real catalog channel IDs (dropped phantom `Metabolism\|enzymes`; added `MacromolecularComplexation\|complexs` SHALLOW rep; PROVISIONAL note on DEEP `k_eng` until 2nd DEEP rep added); §9.1/§9.2 JSON examples re-keyed to actual Translation channels (`monomers`, `substrates`, `boundEnzymes`) and a `joint_check` block example added; §13 `SUMMARY.json` schema upgraded — `NO_GATEABLE_CHANNELS` first-class in tally, per-process `joint_verdict`/`n_joint_fail_pairs`/`warnings` fields; harness_version `design_a_v1_3` throughout; §14 item 8 dependency authority moved to `pyproject.toml` + optional lockfile; `thresholds.json` schema version 1.2→1.3. Catalog: `seed_window:` entries added to FtsZPolymerization ([-200,0]) and Cytokinesis ([-50,0]) per spec §10 MUST. Tracker: spec-link bumped v1.1→v1.3; TRIVIAL_RNG header corrected to 4 processes. **No further critique rounds planned before C1/C2 harness fanout begins.** |
