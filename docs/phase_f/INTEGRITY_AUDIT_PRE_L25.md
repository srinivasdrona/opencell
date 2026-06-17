# Integrity Audit Status Log

- UTC 2026-06-17 20:55:45: Started full-scope static integrity audit for 38 process/composite files + 6 test infrastructure files. Read `SESSION_CONTEXT.md` and verified file existence.
- UTC 2026-06-17 20:55:45: Completed global scans. Found 14 process modules with `trace_hint` reads in `next_update`/callees; no process-side direct `states['trace_hint']` indexing, but widespread `states.get('trace_hint')` replay paths.

## Executive summary
- Total findings: **31**
- **HIGH:** 20
- **MEDIUM:** 9
- **LOW:** 2
- Coverage: **All 38 process/composite files audited** and **all 6 test infrastructure files audited** (static read-only).

## Findings table (HIGH → LOW)

| # | Process | Category | File:Line | Pattern/Value | Risk | L2.5 impact | Notes |
|---|---|---|---|---|---|---|---|
| 1 | karr_replication | trace_hint oracle | opencell/vivarium/karr_replication.py:890 | `next_update` branches to `_next_update_from_trace_hint` | HIGH | replication can read expected next state instead of computing | Uses `enzymes_next` / `boundEnzymes_next` / `chromosome_next` deltas from hint |
| 2 | karr_replication_initiation | trace_hint oracle | opencell/vivarium/karr_replication_initiation.py:289 | hint-gated replay branch | HIGH | DnaA/free-bound transitions can be oracle-driven | `_next_update_from_trace_hint` computes deltas directly from hint |
| 3 | karr_transcription | trace_hint oracle | opencell/vivarium/karr_transcription.py:300 | substrates/enzymes/bound from `trace_hint` | HIGH | NTP usage + RNAP pools can track oracle, not free-run biology | Multiple helper paths consumed in `next_update` |
| 4 | karr_translation | trace_hint oracle | opencell/vivarium/karr_translation.py:357 | guarded replay mode from hint | HIGH | protein production can be replay-scheduled, not emergent | Guard installs `_l21_trace_hint_active` and scheduled outputs |
| 5 | karr_translation_v3 | trace_hint oracle | opencell/vivarium/karr_translation_v3.py:209 | enzyme/bound deltas + active ribosome count from hint | HIGH | translation state can be partly oracle-fed | `boundEnzymes_next` used as active ribosome truth source |
| 6 | karr_metabolism | trace_hint oracle | opencell/vivarium/karr_metabolism.py:341 | early return `{"substrates": hint_delta}` | HIGH | ATP/metabolite flux no longer constrained by LP dynamics under hint | bypasses normal `_dynamic_update`/`_static_update` path |
| 7 | karr_rna_decay | trace_hint oracle | opencell/vivarium/karr_rna_decay.py:262 | replay short-circuit from `substrates_next` | HIGH | decay substrate byproducts can be copied from oracle | `next_update` returns hint deltas when present |
| 8 | karr_protein_decay_light | trace_hint oracle | opencell/vivarium/karr_protein_decay_light.py:450 | replay short-circuit from substrates/monomers/complexs hints | HIGH | decay outputs can be derived from expected-after channel | direct per-store hint-delta replay |
| 9 | karr_protein_modification | trace_hint oracle | opencell/vivarium/karr_protein_modification.py:255 | protein fluxes from `unmodifiedMonomers_next` | HIGH | modification flux can be oracle-derived | `_protein_fluxes_from_trace_hint` overrides sampled flux path |
|10| karr_dna_supercoiling | trace_hint oracle | opencell/vivarium/karr_dna_supercoiling.py:404 | replay_mode from bound/chromosome hints | HIGH | supercoiling/linking numbers can be steered by hint | also applies `substrates_next` hint deltas |
|11| karr_chromosome_condensation | trace_hint oracle | opencell/vivarium/karr_chromosome_condensation.py:255 | `boundEnzymes_next` drives bound update | HIGH | SMC occupancy/energy coupling can mirror oracle | comment explicitly says replay reads sigma-gated binding from hint |
|12| karr_ftsz_polymerization | trace_hint oracle | opencell/vivarium/karr_ftsz_polymerization.py:228 | `enzymes_next` chooses next counts | HIGH | FtsZ polymerization can follow answer sheet | skips ODE path when hint exists |
|13| karr_terminal_organelle_assembly | trace_hint oracle | opencell/vivarium/karr_terminal_organelle_assembly.py:334 | substrate deltas from `substrates_next` | HIGH | substrate transfer can become oracle-fed | hint path preferred over computed transfer path |
|14| karr_transcriptional_regulation | trace_hint oracle | opencell/vivarium/karr_transcriptional_regulation.py:427 | enzyme/bound deltas from hint | HIGH | TF enzyme channels can be replayed from expected-after | appended to computed regulatory update |
|15| l2_replay_common | test infra injection | tests/vivarium/l2_replay_common.py:522 | `overlay_trace_after_hint` writes `states_after` into state | HIGH | harness preloads expected outputs into SUT input surface | explicit docstring says process source may read populated hint |
|16| l2_2_replay_common | test infra injection | tests/vivarium/l2_2_replay_common.py:185 | `states_after` projected then `overlay_trace_after_hint` before `next_update` | HIGH | replay can validate against values already injected | occurs in single-step and composition loop |
|17| l2_2_replay_common_v2 | test infra injection | tests/vivarium/l2_2_replay_common_v2.py:251 | same after-hint overlay-before-step pattern | HIGH | same oracle-laundering risk in v2 harness | includes composition path at line 729 |
|18| _l2_2_design_a_runner_helpers | test infra injection | tests/vivarium/_l2_2_design_a_runner_helpers.py:1396 | transcription/translation helpers inject `oracle_after_*` via hint | HIGH | process-under-test can consume expected-after directly | explicit per-tick helper wiring for hints |
|19| l2_2_design_a_runner | test infra injection | tests/vivarium/l2_2_design_a_runner.py:797 | `sample_state` carries `oracle_after_*` and `oracle_after_by_channel` into runner | HIGH | broadened oracle surface passed to tick runner | increases accidental oracle-read blast radius |
|20| l2_replay_common | allocator oracle surrogate | tests/vivarium/l2_replay_common.py:761 | `refresh_allocator_views` sets requests/allocations to current substrate pool | HIGH | removes allocator contention dynamics; grants can become idealized | not using competitive demand model |
|21| karr_translation | hardcoded replay schedule | opencell/vivarium/karr_translation.py:31 | `_L21_REPLAY_TERMINATION_SCHEDULE` giant literal | MEDIUM | baked per-tick event script can lock behavior to one trace regime | no fixture/line provenance embedded in constant |
|22| karr_replication | hardcoded replay schedule | opencell/vivarium/karr_replication.py:51 | `_REPLAY_DNTP_COUNTS` / `_REPLAY_ATP_EVENTS` / `_REPLAY_LIGATION_EVENTS` | MEDIUM | free-running replication can be biased by static schedule assumptions | schedule literals are extensive and fixed |
|23| karr_request_calculators | hardcoded numeric | opencell/vivarium/karr_request_calculators.py:280 | `requests["ATP"] = avail * 25.0` | MEDIUM | ATP demand scaling may be overfit to replay and brittle in shared pool | comment says parity but no explicit provenance ref |
|24| karr_transcription_v2 | hardcoded numeric | opencell/vivarium/karr_transcription_v2.py:130 | `per_ntp = total_nt / 4.0` | MEDIUM | fixed equal split can misallocate NTP demand if composition is skewed | stoich simplification not fixture-derived per-channel |
|25| karr_transcription_v3 | hardcoded numeric | opencell/vivarium/karr_transcription_v3.py:217 | `total_nt / 4.0` | MEDIUM | same equal-split risk for allocator demand | same simplification as v2 path |
|26| karr_request_calculators | hardcoded numeric | opencell/vivarium/karr_request_calculators.py:600 | `per_ntp_need = total_nt / 4.0 * dt` | MEDIUM | request layer may propagate same stoich simplification into shared allocator | duplicates v2/v3 split logic |
|27| karr_protein_processing_i | hardcoded stoich literal | opencell/vivarium/karr_protein_processing_i.py:237 | `water_remaining // 2` and `-= 2 * cleavage_count` | MEDIUM | if stoich differs from source process, water gating drifts under contention | not linked inline to fixture field or Karr line |
|28| karr_metabolism | non-neutral ports default | opencell/vivarium/karr_metabolism.py:267 | `substrates[*]._default = 1.0` | MEDIUM | missing state overlay can be masked by nonzero substrate seed | violates neutral-default expectation for replay-sensitive stores |
|29| karr_chromosome_condensation | non-neutral ports default | opencell/vivarium/karr_chromosome_condensation.py:207 | defaults from `trace_anchor_bound` / `default_condensation_level` | MEDIUM | missing chromosome overlay can silently inherit trace-anchored state | initialization is data-bearing, not neutral |
|30| karr_macromolecular_complexation_stub | pass-through/no-op | opencell/vivarium/karr_macromolecular_complexation_stub.py:115 | `next_update` returns `{}` always | LOW | if stub is accidentally wired for L2.5+, process is inert | intended stub, but integration misuse risk |
|31| l2_2_replay_common + v2 | pass-through channels excluded | tests/vivarium/l2_2_replay_common.py:92 | `pass_through={"boundEnzymes","enzymes"}` | LOW | enzyme/bound no-op paths can hide behind ownership exclusions | similar pattern in v2 at `tests/vivarium/l2_2_replay_common_v2.py:125` |

## Per-category summary
- **Category 1 (Oracle leakage):**
  - **14/38** process/composite files read `trace_hint` in runtime paths (`next_update` or directly-called helpers).
  - Primary impacted modules: replication family, transcription/translation family, metabolism, RNA/protein decay, DNA topology/cell-cycle auxiliaries.
- **Category 2 (Hardcoded numerics):**
  - **6 process files** with medium-risk literals in runtime/request logic (`25.0`, repeated `/4.0` splits, replay schedules, stoich literals).
- **Category 3 (Provenance gaps / non-neutral defaults):**
  - **2 process files** flagged as medium-risk for non-neutral defaults likely to mask absent overlay (`karr_metabolism`, `karr_chromosome_condensation`).
- **Category 4 (Pass-through / echo-back):**
  - **1 process stub + 2 harness specs** with explicit no-op/pass-through behavior.
- **Category 5 (Test infrastructure concerns):**
  - **5/6 test infra files** contain high-risk oracle injection surfaces (`l2_replay_common`, `l2_2_replay_common`, `l2_2_replay_common_v2`, `l2_2_design_a_runner`, `_l2_2_design_a_runner_helpers`).
  - `_l2_2_design_a_projections.py` inspected; no direct pre-step oracle injection pattern found.

## Recommendation

### MUST fix before L2.5
1. Remove or hard-disable all `trace_hint`-driven runtime branches from production process paths (Findings #1–#14), or gate them behind an explicit **test-only flag defaulting off** in composite/chassis runs.
2. Remove pre-step `states_after` injection in replay/design harnesses (Findings #15–#19), replacing with strict post-step comparison-only usage.
3. Replace `refresh_allocator_views` idealized grant mirroring with contention-faithful allocator simulation (Finding #20), otherwise shared-pool behavior is not exercised.

### Can defer (but track)
1. Replay schedule and scalar-literal cleanup (#21–#27): move constants into fixture-backed config with explicit provenance tags.
2. Non-neutral default hygiene (#28–#29): neutralize defaults where possible, or document why non-neutral defaults are required and safe.
3. Stub/pass-through guardrails (#30–#31): ensure CI/composer assertions prevent accidental stub wiring or excluded-channel blind spots.

## Confidence note
- **No claim of zero HIGH findings.** High-risk findings are present and concentrated around oracle surfaces in both runtime process code and replay/design harness infrastructure.

## Coverage checklist (audited)
- Process/composite scope: all requested 38 files under `opencell/vivarium/`.
- Test infrastructure scope: all requested 6 files under `tests/vivarium/`.
- Method: static code reading + pattern scans only; no test execution.

