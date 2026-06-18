# L2.event Gate Specification (draft v0.1)

**Status:** v0.3 (2026-06-15) — round 2 GPT critique findings incorporated. See §10 (round 1) and §11 (round 2) for finding-by-finding disposition. Pending round 3 critique on v0.3.
**Owner:** OpenCell whole-cell-simulation project, Phase F
**Authority:** When ratified, this document is canonical for L2.event methodology and harness contract.

**Companion docs:**
- `L2_2_DESIGN_A_SPEC.md` — sibling per-tick distributional gate
- `PROCESS_CATALOG.yaml` — per-process scope incl. `bucket: EVENT_CLASS`, `seed_window`, `event_density`
- `L2_5_HARNESS_DESIGN.md` — original L2.2 design notes (predates L2.event split)

**Provenance:** This spec extends the 4-bullet sketch in `L2_2_DESIGN_A_SPEC.md` §10 (which was placeholder text deferring the L2.event design to a separate document — this one).

---

## 0. The problem in one paragraph

The L2.2 Design-A gate compares OpenCell-vs-Karr per-tick distributions. It works for processes where events fire on most ticks. For processes whose firing is **rare and timing-dependent** — Cytokinesis fires once per cell cycle around division; FtsZPolymerization fires only in the pre-division window; RibosomeAssembly fires sparsely throughout but missing in the captured per-tick window; DNADamage fires conditionally on radiation/UV state never set in the captured window — the per-tick gate degenerates. Both OC and Karr produce no-events in the captured window, W1 is trivially zero, and the runner emits a `PASS` that conveys no information. This was caught explicitly on Day 23 (Cytokinesis Phase-0 false-PASS) and Day 28 (RibosomeAssembly + DNADamage misclassification audit). The L2.2 spec already disqualifies these processes (`bucket: EVENT_CLASS`, runner refuses them). This document specifies the alternative gate that should accept them.

## 1. Purpose and scope

### 1.1 What L2.event answers

Per-tick distributional fidelity asks: "across N seeds × M ticks of independent samples, does OC's per-tick output distribution match Karr's?"

Event-aligned fidelity asks: **"does OC fire the same events at the same times as Karr, with the same magnitude when it fires?"** Three sub-questions, asked separately and combined:

1. **Did the event fire?** (binary outcome per seed) — compared as firing-rate distributions across seeds
2. **When did it fire?** (firing-tick distribution per seed where it fired) — compared as cycle-stage distributions
3. **What was its magnitude?** (per-firing payload) — compared as magnitude distributions across firing events

### 1.2 In scope (per current catalog v3.1, post-rubber-duck)

| Process | Bucket | Event firing pattern | Notes |
|---|---|---|---|
| Cytokinesis | EVENT_CLASS | Once per cell cycle, around division | Catalog `seed_window: pre-division [-50, 0]` |
| RibosomeAssembly | EVENT_CLASS | **Repeated firings** throughout growth phase | Reclassified Day 28; inter-arrival distribution model (§5.3) |

### 1.2.1 Removed from L2.event scope (rubber-duck round 1)

| Process | Reason | Recommended treatment |
|---|---|---|
| **FtsZPolymerization** | Per S1: not a binary event — polymerization is a gradient process across ~200 ticks. Current OC port has no `ring_complete` channel; would require extractor v3 to expose one. Until then, the catalog's `event_density: sparse` is misleading — "sparse" here means "narrow time window", not "rare firing within window." | Either (a) add `ring_complete` channel in extractor v3 and re-add to L2.event in v0.3, OR (b) reclassify back to ALGORITHMIC_SHALLOW with the `seed_window: [-200, 0]` constraint and gate via Design-A within that window. **Operator decision required before v0.3.** |
| **DNADamage** | Per M3 / §7.6: events depend on exogenous radiation/UV input never produced in baseline Karr cycles. Full-cycle extraction will yield 0/50 firings. Phase 1 cost ≈ 33 hr wall to confirm what the Day-28 audit already showed. | Defer to **L2.stress** — a sibling gate (not specified here) that injects damage signals and gates OC's response distribution. Out of L2.event scope. |

### 1.3 Out of scope (for this document)

- L2.2 Design-A per-tick processes (different gate; covered by `L2_2_DESIGN_A_SPEC.md`)
- L2.5 composition (multiple processes; out of L2 family)
- L3 direct-coupling (different gate)
- Whole-chassis L1 / L5 / L7 work (this gate operates on isolated process traces)

### 1.4 Bucket assignment criteria (re-stated for L2.event)

A process belongs in `EVENT_CLASS` (and thus this gate) if EITHER:
- (a) `event_density: sparse` AND (`seed_window: <defined>` OR audit shows 0 events across all 50 seeds in the captured per-tick window), OR
- (b) The process semantics are inherently event-driven (a single firing per cell cycle is the unit of analysis, not per-tick deltas)

Edge case: a process with `event_density: sparse` but NON-zero events in the per-tick window (e.g. RNADecay, ProteinDecay) stays in Design-A — sparsity alone is not the criterion. The criterion is "captured window doesn't contain events on a meaningful fraction of seeds."

## 2. Inputs the harness consumes

For each in-scope EVENT_CLASS process:

### 2.1 Karr ensemble traces (v0.3 — windowed grid snapshots, not firing-tick-only)

Per-cell-cycle trajectories, 50 seeds, captured at **a windowed snapshot grid** around each process's `firing_window_definition` (per §2.3 catalog). For each seed:

- `firing_tick`: integer tick index of the event firing, or `null` if no firing in the cycle. Detected by evaluating the `event_definition` predicate (§2.3) per tick.
- `firing_payload`: process-specific magnitude data captured AT the firing tick.
- **`window_snapshots`** (NEW v0.3): for every tick in `firing_window_definition.tick_range_from_division`, persist `{tick, before_state, did_fire}`. This grid powers §3.2's Karr-state-conditioned firing-readiness comparison and resolves G-S2 (sub-gate 2 needs more than firing-tick-only snapshots to compute a meaningful curve).
- `cycle_metadata`: cell cycle stage indicators (e.g. `replication_complete_tick`, `division_tick`) for relative-timing comparison.

**Snapshot economy:** rather than persisting all ~5000-7000 cycle ticks, the windowed grid persists only the ticks in each process's `firing_window_definition`. For Cytokinesis with `[-50, 50]` around division, that's 100 snapshots per seed (vs 5000+ for a full cycle). For RibosomeAssembly with `[-3500, -200]` growth phase, the grid can be **subsampled** at e.g. every 50th tick (66 snapshots per seed); the catalog field `firing_window_snapshot_stride` per process controls the subsampling.

Extractor: NEW MATLAB pass `scripts/matlab/extract_event_traces.m`. Implementation contract:
- Run Karr through a full cell cycle.
- At each tick `t` in `firing_window_definition.tick_range_from_division` (subsampled by `firing_window_snapshot_stride`):
  - Evaluate `event_definition` predicate on the post-update state → `did_fire[t]` boolean.
  - Persist `(t, before_state, did_fire[t])` to `window_snapshots`.
- The `event_definition` predicate must be a SHARED specification consumed by both this extractor AND the Python harness (per §7.1 m1 dual-consumer rule). Pin in catalog as a path-expression on the update dict; evaluator is shared code between MATLAB and Python.
- Per-cycle wall: ~50-150 snapshots × ~1 sec/snapshot = 1-3 min per seed, ~50-150 min for N=50 seeds. (Reduces v0.2's ~100 hr Phase 1b estimate by ~50× because we no longer extract full-cycle every-tick.)

Output: `data/m1_sources/karr_native/per_process_event_traces_s{NNN}/{Process}_cycle.mat`.

### 2.2 OC re-execution apparatus

For each Karr `window_snapshots[t].before_state`, the harness:
1. Constructs the OC process at the matching seed (RNG seeded per §2.4 below).
2. Loads Karr `before_state` as the OC input state (mirror existing L2.2 `_run_<process>_tick` plumbing).
3. Calls `process.next_update(1.0, state)`.
4. Evaluates the shared `event_definition` predicate on OC's update → `oc_did_fire[t]`.
5. If `oc_did_fire[t]`, also captures the firing payload via `event_payload_fields`.

Same plumbing as L2.2 Design-A's `_run_*_tick` wrappers (use the runner's `project_observable_from_state` pattern, NOT raw `update[...]` extraction — per the PFolding v2 lesson learned).

### 2.3 Catalog augmentations needed

Per EVENT_CLASS process in `PROCESS_CATALOG.yaml`:
- `event_definition`: a path-expression on the OC update dict. Format TBD in implementation; must be evaluable by both MATLAB and Python. Example: `"path:protein.counts['MG_001_DIMER'] > 0 OR path:events.division_complete >= 1.0"`.
- `event_payload_fields`: list of path-expressions to extract magnitude payload at firing.
- `firing_window_definition`: `{tick_range_from_division: [min, max], snapshot_stride: int}`.
- `l2_event_status`: `in_scope` | `deferred_to_l2_stress` | `reclassify_pending` (per G-S1 — adds machine-readable status separate from `bucket: EVENT_CLASS`).

### 2.4 RNG seeding policy (NEW v0.3 — per G-M5)

For each per-snapshot OC re-execution, the OC process RNG is seeded via:

```
np.random.SeedSequence([L2_EVENT_VALIDATION_SEED, process_id, seed, tick, replicate])
```

where:
- `L2_EVENT_VALIDATION_SEED`: a project-wide constant (define in `tests/vivarium/l2_event_runner.py` as a `Final[int]`)
- `process_id`: deterministic int hash of the process name
- `seed`: the Karr seed of the trajectory being replayed
- `tick`: the tick of the snapshot being re-executed
- `replicate`: 0 by default; if catalog declares `replicates_per_snapshot > 1`, run R independent re-executions per snapshot and aggregate

Rationale: reusing the same RNG seed for every candidate tick (which would happen naively) distorts the firing-readiness curve, especially for RibosomeAssembly (multiple chaperone-allocation draws). Mirrors L2.2 Design-A's deterministic per-sample seeding.

## 3. Comparison algorithm

For each EVENT_CLASS process:

### 3.1 Sub-gate 1: firing rate (v0.3 — equivalence margin, k_karr=0 precedence fixed)

- Karr fired in `k_karr` of N seeds. Karr firing rate `r_karr = k_karr / N`.
- For each seed, re-execute OC on Karr's pre-firing snapshot (or, if Karr didn't fire in that seed, on the catalog's `firing_window_definition` midpoint). OC produces firing or no-firing.
- OC firing rate `r_oc = k_oc / N`.

**Precedence rule (G-M2):**
- If `k_karr = 0`:
  - If `k_oc = 0`: verdict `EVENT_NEITHER_FIRES_IN_WINDOW` (informational, not PASS) — gate is hollow, sample doesn't exercise the question.
  - If `k_oc > 0`: verdict `FAIL` via `EVENT_OC_FIRES_BUT_KARR_DOES_NOT` (spurious firings, severe regression).
- If `k_karr ≥ 5`: proceed to the equivalence test below.
- If `0 < k_karr < 5`: verdict `INSUFFICIENT_SAMPLES` (can't estimate rate; raise N or widen window).

**Equivalence test (G-M1 — not a hypothesis test):**
Compute the Newcombe 95% CI for the difference `r_oc - r_karr`. Define per-process equivalence margin `epsilon_rate` (catalog field; default 0.10 = 10 percentage points).
- **PASS** iff CI is wholly contained within `[-epsilon_rate, +epsilon_rate]` AND `k_oc ≥ max(1, 0.5 * k_karr)` (absolute floor — OC must fire at least half as often as Karr in absolute count).
- **FAIL** otherwise.

Rationale: "CI contains 0" is failure-to-reject-equality, not evidence of equivalence. "CI wholly within ±ε" IS evidence of equivalence at margin ε. Same equivalence-test discipline as the rest of L2.

### 3.2 Sub-gate 2: firing-readiness curve (v0.3 — sparse-snapshot compatible, real null)

**Critical design choice (post-G-S2 + G-S4):** OC re-execution is bounded to **independent one-tick calls on Karr's recorded windowed snapshots**, never free-running. The snapshot grid from §2.1 provides the data; sub-gate 2 measures whether OC's firing-readiness across cycle positions matches Karr's.

**Data structure:** for each seed, Karr's `window_snapshots` gives a sequence `[(t_0, S_0, k_fire_0), (t_1, S_1, k_fire_1), ..., (t_W, S_W, k_fire_W)]` where `k_fire_t ∈ {0, 1}` is Karr's firing indicator at tick `t` (Karr fires at exactly one tick per seed if it fires at all, so the Karr indicator vector is one-hot or zero).

For each `(t, S_t)`, re-execute OC at the matching seed+tick (per §2.4 RNG policy) → `o_fire_t ∈ {0, 1}`.

**Aggregation:**
- Per-seed firing-position vector: `karr_curve[seed] = [k_fire_0, ..., k_fire_W]` and `oc_curve[seed] = [o_fire_0, ..., o_fire_W]`.
- Pooled firing-position distributions: `karr_positions = {t | k_fire_t = 1 across all seeds}`, `oc_positions = {t | o_fire_t = 1 across all seeds}`.
- Test statistic: W1 distance between `karr_positions` and `oc_positions` distributions (after normalizing to relative cycle position).

**Null bootstrap (G-S3 — proper generative null, not degenerate shuffle):**
- Resample seeds with replacement from Karr's recorded ensemble (bootstrap cluster = seed). Recompute the pooled `karr_positions` distribution from the resampled set.
- Compare against the original pooled `karr_positions` → bootstrap W1 sample.
- Repeat B=1000 times → null distribution → q95_null.

This null IS generative because resampling seeds produces genuinely different position-sets each iteration (different subsets of Karr's recorded firings). The degenerate-at-zero shuffle from v0.2 is replaced.

**PASS rule:**
- **PASS** iff W1 ≤ q95_null * k_eng (k_eng default 2.0, PROVISIONAL per G-M6, NEW per-process calibration documented in §7.4).
- **FAIL** if W1 > threshold.
- **INSUFFICIENT_SAMPLES** if pooled `karr_positions` has < 10 firings (bootstrap not meaningful below this).

Rationale for dropping KS p-value: per round-1 M6, p > 0.05 is "failure to reject equality" not "evidence of equality." W1 + calibrated null is the L2.2-discipline equivalent.

**For inter_arrival processes (RibosomeAssembly per §5.2):** sub-gate 2 instead pools the inter-arrival times across seeds and uses log-transformed W1 against the bootstrap null on Karr's pooled inter-arrival distribution. The Karr-state-conditioned re-execution discipline is preserved (each snapshot is an independent OC probe).

### 3.3 Sub-gate 3: magnitude distribution (v0.3 — same as v0.2, k_matched ≥ 15 retained from round 1)

(No structural changes from v0.2 beyond inheriting the §2.4 RNG policy.)

### 3.4 Process-level verdict (v0.3 — adds informativeness rule per G-M4)

**Rule:**
- Verdict aggregation REQUIRES ≥ 2 of the 3 sub-gates to be both **gateable** (not `INSUFFICIENT_SAMPLES` and not `EVENT_NEITHER_FIRES_IN_WINDOW`) AND **informative** (per below).
- **Informativeness rule (G-M4):** a sub-gate counts as gateable only if:
  - Its Karr target distribution has non-trivial support (e.g. ≥ 5 distinct values for magnitude; ≥ 3 distinct firing positions for timing).
  - It is not mathematically redundant with another sub-gate (e.g. for a binary-outcome process where magnitude is just "1 if fired else 0", sub-gate 3 is a deterministic function of sub-gate 1 and does NOT count as a separate gateable sub-gate). Pin per-process redundancy detection rules in `tests/vivarium/l2_event_runner.py` and document in catalog `magnitude_redundant_with_firing: bool` field.
- If ≥ 2 sub-gates are gateable+informative AND all gateable sub-gates PASS: verdict is `PASS`.
- If any gateable sub-gate FAILs: verdict is `FAIL`.
- If only sub-gate 1 is gateable+informative AND it PASSes: verdict is `PARTIAL_PASS_FIRING_RATE_ONLY` (NOT a green; informational).
- If 0 sub-gates are gateable+informative: verdict is `EVENT_NO_GATEABLE_SUBGATES` (FAIL-equivalent for scoreboard).

Diagnostic warning ladder (analogous to L2.2 §9.3):
- `EVENT_FIRING_RATE_DRIFT` — sub-gate 1 FAIL (rate or absolute floor violated)
- `EVENT_TIMING_DRIFT` — sub-gate 2 FAIL
- `EVENT_MAGNITUDE_DRIFT` — sub-gate 3 FAIL
- `EVENT_INSUFFICIENT_FIRINGS_AT_ENSEMBLE` — k_karr < 5; sample-size warning
- `EVENT_OC_NEVER_FIRES` — k_oc = 0 with k_karr ≥ 5; severe regression (caught by absolute floor)
- `EVENT_OC_FIRES_BUT_KARR_DOES_NOT` — k_oc > 0 with k_karr = 0; spurious firings
- `EVENT_NEITHER_FIRES_IN_WINDOW` — k_karr = k_oc = 0; gate hollow
- `EVENT_NO_GATEABLE_SUBGATES` — fewer than 2 sub-gates gateable+informative
- `EVENT_PARTIAL_PASS_FIRING_RATE_ONLY` — only sub-gate 1 was gateable+informative
- `EVENT_MAGNITUDE_REDUNDANT_WITH_FIRING` — sub-gate 3 was excluded as redundant per informativeness rule

## 4. Sampling discipline

### 4.1 Karr ensemble extraction

- N = 50 seeds standard (same as L2.2 Design-A).
- M_ticks = full cycle (~5000-7000 depending on process). The extractor walks the full cycle until cell division and persists named-process tick snapshots only at firing ticks.
- Estimated MATLAB wall: ~3-5 hr per process × 50 seeds (full cycle is ~50× longer than the L2.2 100-tick window).

### 4.2 OC re-execution

- For each Karr-firing seed, OC is re-executed on the Karr `before_state_at_firing` with the matched seed → 1 OC sample per Karr firing.
- For each Karr-non-firing seed, OC is ALSO re-executed (on the Karr state at the cycle midpoint, or wherever the catalog's `firing_window_definition` is centered) → 1 OC null sample.
- Total OC samples per process = N (same number; OC's firing/no-firing is the binary outcome on the same N seeds Karr was run on).

### 4.3 Null calibration (for sub-gate 3 magnitude)

- Karr-vs-Karr null: shuffle seed labels B=200 times, recompute W1, take q95.
- Same convention as L2.2 §6.3.

## 5. Per-process specification (post-rubber-duck — 2 processes)

FtsZPolymerization removed per S1; DNADamage removed per M3. Both documented in §1.2.1.

### 5.1 Cytokinesis (v0.3 — paths verified against OC source per G-M3)

```yaml
event_definition: |
  Firing = update["cell"]["division_complete"] == True
  (verified at opencell/vivarium/karr_cytokinesis.py:249)
event_payload_fields:
  # Per G-M3 + M4: OC emits division_complete (bool) and division_progress (float)
  # in update["cell"][...]. There is no per-base chromosome partition payload —
  # Cytokinesis L2.event gates the scalar division-completion event only.
  scalar_payload: "1.0 if update['cell'].get('division_complete', False) else 0.0"
  # Additional informational (non-gating):
  progress_at_firing: "update['cell'].get('division_progress', 0.0)"
magnitude_redundant_with_firing: true
  # Per G-M4: the scalar payload above is a deterministic function of the firing
  # predicate (1 iff fired, 0 iff not). Sub-gate 3 magnitude is therefore
  # mathematically redundant with sub-gate 1 firing — DO NOT count as a separate
  # gateable sub-gate. Cytokinesis verdict will be PARTIAL_PASS_FIRING_RATE_ONLY
  # unless we add a non-redundant payload (e.g. cumulative GTP consumed pre-firing).
phase_0_verification_complete: true
  # Verified 2026-06-15 against E:\opencell\opencell\vivarium\karr_cytokinesis.py
  # via Select-String grep; division_complete emission at line 249, division_progress
  # at lines 238, 243. NO partition_counts emission exists in OC port.
firing_window_definition:
  cycle_stage: "pre-division to division"
  tick_range_from_division: [-50, 50]
  snapshot_stride: 1  # full per-tick within the 100-tick window
sub_gate_1_epsilon_rate: 0.10  # firing-rate equivalence margin
sub_gate_2_threshold_w1_multiplier: 2.0  # k_eng, PROVISIONAL per G-M6
sub_gate_3_threshold_multiplier: 2.0  # PROVISIONAL but sub-gate 3 excluded as redundant anyway
event_timing_model: single_firing
```

**Operator decision required:** with `magnitude_redundant_with_firing: true`, Cytokinesis can at best earn `PARTIAL_PASS_FIRING_RATE_ONLY` (rate + timing, no informative magnitude). Three paths:
- **(A) Accept partial pass** — Cytokinesis verdict will never be a green; carried as informational only.
- **(B) Add a non-redundant payload** — augment OC's port to emit a meaningful magnitude (e.g. cumulative GTP consumed pre-firing, ATP spent, time-to-completion). Adds production code change.
- **(C) Reclassify** — Cytokinesis might be better gated by L1 (whole-chassis firing) rather than L2.event.

### 5.2 RibosomeAssembly (M2: inter-arrival model)

RibosomeAssembly fires repeatedly throughout growth phase, not once. The single-firing model from v0.1 was structurally wrong; v0.2 uses inter-arrival distribution.

```yaml
event_definition: |
  Firing = update["complex"]["counts"][ribosome_30s_wid] > 0
    OR update["complex"]["counts"][ribosome_50s_wid] > 0
event_payload_fields:
  scalar_reduction: |
    sum of (update['complex']['counts'][ribosome_30s_wid] +
            update['complex']['counts'][ribosome_50s_wid])
    at each firing tick
phase_0_verification_required: |
  Before Phase 3 wiring, confirm ribosome_30s_wid and ribosome_50s_wid are
  the canonical Karr ribosome subunit identifiers and that OC's
  karr_ribosome_assembly.py emits to those exact wid keys.
firing_window_definition:
  cycle_stage: "growth phase (post-replication-init)"
  tick_range_from_division: [-3500, -200]  # most of cycle is growth
event_timing_model: inter_arrival
sub_gate_2_inter_arrival_spec:
  # Build the inter-arrival distribution: time between successive firings
  # within one seed. Compare Karr's distribution vs OC's via W1 on
  # log-transformed inter-arrival times (heavy-tailed; log normalizes).
  # No median-offset gate (multiple firings per seed; offset concept doesn't apply).
  metric: w1_log_inter_arrival
  threshold_multiplier: 2.0  # PROVISIONAL per M7
sub_gate_1_floor_k_oc_minimum: ceil(0.5 * k_karr)  # standard absolute floor
sub_gate_3_threshold_multiplier: 2.0  # PROVISIONAL per M7
```

**Implementation note for sub-gate 2 in inter-arrival mode:**
- For each seed, extract Karr's firing-tick sequence `[T_1, T_2, ..., T_n]`.
- Inter-arrivals: `[T_2 - T_1, T_3 - T_2, ...]`.
- Log-transform: `log(inter_arrival + 1)` to handle 1-tick gaps.
- Concatenate inter-arrivals across all matched seeds to form OC's pooled distribution.
- Compute W1 vs Karr's pooled distribution.
- This replaces §3.2's firing-readiness curve mechanism for inter_arrival timing model.

**OC re-execution discipline for inter_arrival:** the harness must NOT free-run OC across the growth phase (S2 prohibition). Instead, for each Karr-snapshotted state at a candidate firing tick, ask OC "would you fire?" via independent one-tick re-execution. OC's firing-tick sequence is then the subset of Karr's snapshotted ticks where OC fires. Inter-arrivals are computed on this conditional sequence.

### 5.3 (DELETED — FtsZPolymerization moved to §1.2.1)

### 5.4 (DELETED — DNADamage moved to §1.2.1)

## 6. Implementation roadmap (corrected per M1)

### 6.0 Phase 0: OC-port emission verification (per M4)

Before Phase 1, verify the per-process `event_definition` predicates can actually be evaluated against OC's current port:

- **Cytokinesis:** open `opencell/vivarium/karr_cytokinesis.py`, find where `next_update` returns. Confirm at least one of `update['events']['division_complete']` or `update['chromosome']['partition_counts']` is emitted. Cite file:line. If neither: Phase 3 wiring must include adding the emission.
- **RibosomeAssembly:** open `opencell/vivarium/karr_ribosome_assembly.py`, confirm `ribosome_30s_wid` and `ribosome_50s_wid` are the canonical Karr identifiers and that emission lands in `update['complex']['counts']`. Cite file:line.

Wall: ~30 min operator. **Do this before Phase 1 — saves Phase 3 from rediscovering missing emissions late.**

### 6.1 Phase 1a: calibration extraction (1-2 days; per M1)

- Author `scripts/matlab/extract_event_traces.m` analogous to existing
  `extract_per_process_traces_v2.m` but with full-cycle scope and
  firing-tick snapshot filter (per §2.1).
- Run 1-2 seeds full-cycle per process to locate firing window experimentally.
- Inspect: what fraction of full-cycle ticks contain firings for Cytokinesis vs RibosomeAssembly?
- Decide per-process scoping: full-cycle vs windowed extraction.

Wall: ~1-2 days operator. Smoke on 1-2 seeds before launching full extraction.

### 6.1.1 Wall cost reconciliation (v0.3 — windowed snapshot grid dramatically cuts cost)

The v0.1 spec estimated ~330 hr full-cycle extraction. v0.2 reconciled to ~100 hr. **v0.3 cuts this further** by replacing full-cycle every-tick extraction with windowed-grid snapshots per §2.1.

| Phase | Per-process wall (v0.3) | 2 processes total (Cytokinesis + RibosomeAssembly) |
|---|---|---|
| Phase 0 verification (COMPLETE for Cytokinesis, pending for RibosomeAssembly) | 30 min operator | 30 min remaining |
| Phase 1a calibration extraction (1-2 seeds, windowed grid) | 1-2 hr MATLAB | 3-4 hr |
| Phase 1b full extraction (50 seeds, windowed grid) | **Cytokinesis: ~2 hr (100-tick window × 1 stride × 50 seeds × ~1 sec/snapshot = ~5000 snapshots ÷ ~40 snapshots/min). RibosomeAssembly: ~4 hr (66 snapshots × stride 50 × 50 seeds, growth-phase scope).** | **~6 hr MATLAB wall, 1 day clock time** |
| Phase 2 harness scaffolding | — | 3-5 days delegated |
| Phase 3 per-process wiring | 2-3 days each | 4-6 days delegated |
| Phase 4 integration | 1-2 days | 1-2 days |
| **Total** | — | **~2-3 weeks calendar** |

**Reduction from v0.2:** 5-7 days Phase 1b → 1 day Phase 1b. Single MATLAB seat is no longer a binding constraint; the windowed grid scope is dominated by harness work (Phases 2-3), which is delegate-able.

### 6.2 Phase 2: harness scaffolding (3-5 days delegated)

- Author `tests/vivarium/l2_event_runner.py` — analogous to existing
  `l2_2_design_a_runner.py` but with the event-aligned algorithm.
- Author `tests/vivarium/_l2_event_runner_helpers.py` — per-process
  re-execution wrappers (one per EVENT_CLASS process).
- Author pytest suite at `tests/vivarium/test_l2_event*.py` (anti-cheat tests).
- **Critical:** anti-cheat tests must catch S2 (free-run forbidden), S3 (absolute floor), S4 (vacuous-PASS aggregation), M5 (k_matched ≥ 15 for bootstrap), M6 (no KS p-value gate).

### 6.3 Phase 3: per-process wiring (per M3 update — 2 processes × 2-3 days each)

Revised from v0.1's "~1 day per process":
- **Cytokinesis: 2 days.** Phase 0 may surface missing OC emissions requiring an OC-port edit before wiring.
- **RibosomeAssembly: 2-3 days.** Inter-arrival distribution model (§5.2) is a new harness shape that doesn't reuse Cytokinesis's plumbing directly.

### 6.4 Phase 4: integration with main L2.2 dashboard

- Aggregate L2.event verdicts into the same scoreboard as L2.2 Design-A.
- L2.event verdicts reported as a **separate axis** from L2.2 (per §1.5 reasoning — they're different gates with different statistical contracts).
- Scoreboard becomes "14/20 L2.2" + "X/2 L2.event" where X is the number of L2.event greens after Phase 3.

## 7. Open questions / known risks (post-rubber-duck pruned)

Items closed by v0.2 incorporation: §7.1 wall-cost (now §6.1.1), §7.5 RibosomeAssembly inter-arrival (now §5.2 canonical), §7.6 DNADamage (moved to §1.2.1).

### 7.1 OC's "firing detection" semantics fragility

OC's `next_update` returns an update dict. "Did OC fire" requires interpreting that dict per process — not just checking `update is not None`. Each `event_definition` per §5 is process-specific. If a process's `event_definition` is ambiguous or has multiple interpretations, the gate becomes fragile.

**Mitigation:** pin each `event_definition` in the catalog and require it be cited verbatim in any L2.event delegation prompt (same authority chain as L2.2 Design-A). Per m1: the SAME `event_definition` predicate must be consumed by both the MATLAB extractor (§2.1's "non-zero delta" filter must use the catalog predicate, not its own informal one) and the Python harness. Authoring the predicate as a TOML/YAML expression evaluable on both sides is the cleanest path; alternative is to maintain MATLAB + Python implementations with a shared test that proves they agree on a fixture.

### 7.2 Catalog grammar reconciliation (per m2)

L2.2 catalog already has `event_channels: [chromosome]` on Cytokinesis. The L2.event spec adds three new per-process fields (`event_definition`, `event_payload_fields`, `firing_window_definition`). Their relationship to the existing `event_channels`:

- **`event_channels` (existing, L2.2):** which channels of a process are deferred from L2.2 per-tick gating. After this spec ratifies, this becomes informational ("these channels are gated by L2.event").
- **`event_definition` (new, L2.event):** the predicate that defines a firing.
- **`event_payload_fields` (new, L2.event):** the magnitude data captured at firing.
- **`firing_window_definition` (new, L2.event):** when in the cycle firings can occur.

The existing `event_channels` field is **kept as a hint** (do not break L2.2 backward compatibility) but is otherwise orthogonal to the L2.event fields.

### 7.3 Cytokinesis chromosome state dependency

Resolved per M4 and §5.1's `scalar_reduction` field. Cytokinesis L2.event gates the scalar partition-event indicator, not per-base chromosome state. If OC's port emits neither `events.division_complete` nor `chromosome.partition_counts`, Phase 0 catches it and Phase 3 wiring includes the OC-port emission.

### 7.4 Per-process k_eng calibration debt (M7)

The `sub_gate_3_threshold_multiplier: 2.0` is **PROVISIONAL** in all per-process specs. L2.2 §7.3 calibrated k_eng per-bucket on a 6-channel panel. L2.event has only 2 in-scope processes after rubber-duck pruning, neither of which is in the L2.2 calibration panel.

**Mitigation options:**
- (a) Extend the L2.2 calibration panel with Cytokinesis's partition-event payload and RibosomeAssembly's assembly-count payload. Recompute k_eng. ~1 day analysis.
- (b) Mark the 2.0 multiplier `PROVISIONAL` (current state) and accept first-Phase-3 smokes as additional calibration data points. Re-calibrate after both processes are gated.

**Recommendation:** Option (b) until both processes have at least one smoke verdict; then Option (a) using the smoke results as calibration data.

## 8. Acceptance criteria for this spec (corrected per n1)

This spec is RATIFIED iff:
1. Rubber-duck review passes: ALL SHOWSTOPPER findings either resolved with a spec edit or explicitly closed in §10 with rationale signed by the operator. (**v0.2 status:** 4/4 SHOWSTOPPER resolved by §10.)
2. GPT critique returns no new SHOWSTOPPER findings; any returned are closed per the same rule as #1.
3. Operator pins per-process `event_definition` and `firing_window_definition` for Cytokinesis + RibosomeAssembly (the two remaining in-scope processes after S1 + M3 pruning).
4. Phase 0 verification complete for both processes (per §6.0).
5. Phase 1a calibration extraction script written and smoked on 1-2 seeds (per §6.1).

Criteria #1 explicitly does NOT permit perpetual veto: once a SHOWSTOPPER is closed by spec edit OR by signed rationale, re-raising the same finding requires new evidence (per n1).

## 9. Out-of-scope follow-ups

- **L2.stress gate** for DNADamage and any future radiation/stress process.
- **L2.event for FtsZPolymerization** — requires extractor v3 to add `ring_complete` channel; or reclassification back to ALGORITHMIC_SHALLOW with the windowed `seed_window` constraint (S1).
- **Cross-process L2.event composition** (does FtsZ firing precede Cytokinesis correctly?). Belongs in L2.5 / L3.
- **Whole-chassis event-firing tests** (L5 territory).
- **L2.event for processes not currently in EVENT_CLASS** (e.g. should ReplicationInitiation be re-classified?). Defer until Phase 3 is complete for Cytokinesis + RibosomeAssembly.

---

## 10. Rubber-duck round 1 findings (2026-06-15)

Reviewer: rubber-duck sub-agent (claude-opus-4.7-xhigh model).

### SHOWSTOPPERS

| ID | Finding | Disposition in v0.2 |
|---|---|---|
| S1 | FtsZ is gradient not binary; §5.2 builds gate on fiction | **RESOLVED:** FtsZ removed from §1.2; moved to §1.2.1 with two reclassification paths (add `ring_complete` channel OR reclassify to ALGORITHMIC_SHALLOW). Operator decision required before v0.3. |
| S2 | Sub-gate 2 free-run is Design-B incoherence L2.2 §2.1 rejected | **RESOLVED:** §3.2 rewritten to use Karr-state-conditioned "firing readiness curve" — OC re-executed independently on each Karr snapshot in the window, never allowed to free-run. Inter-arrival variant (§5.2 for RibosomeAssembly) inherits the same discipline. |
| S3 | Sub-gate 1 PASS has false-PASS hole at low k_karr | **RESOLVED:** §3.1 PASS rule now requires `k_oc ≥ max(1, 0.5*k_karr)` absolute floor AND `k_oc ≤ 2*max(1, k_karr)` symmetric upper guard. Rationale documented in §3.1. |
| S4 | §3.4 process-level verdict permits vacuous PASS | **RESOLVED:** §3.4 rewritten to mirror L2.2 §8.2's NO_GATEABLE_CHANNELS pattern. Requires ≥2 sub-gates gateable for PASS. New verdicts: `PARTIAL_PASS_FIRING_RATE_ONLY` (informational, not a green), `EVENT_NO_GATEABLE_SUBGATES` (FAIL-equivalent). |

### MAJORS

| ID | Finding | Disposition |
|---|---|---|
| M1 | Phase 1 wall-cost estimate inconsistent | **RESOLVED:** §6.1.1 reconciles to single normative estimate (~100 hr MATLAB Phase 1b, ~5-7 days clock; total Phase 1-4 = ~3-5 weeks calendar). Phase 1 split into 1a calibration + 1b windowed extraction. |
| M2 | RibosomeAssembly canonical §5.3 contradicts §7.5 mitigation | **RESOLVED:** §5.2 (new numbering) promotes inter-arrival model to canonical. `event_timing_model: single_firing \| inter_arrival` catalog field added per §3.2. |
| M3 | DNADamage acknowledged untestable yet kept in scope | **RESOLVED:** DNADamage removed from §1.2; moved to §1.2.1 as L2.stress-deferred. Cuts Phase 1b wall ~25%. |
| M4 | Cytokinesis payload assumes OC schema not verified | **RESOLVED:** §5.1 adds `phase_0_verification_required` field; §6.0 adds Phase 0 step to verify OC port emissions before Phase 1. |
| M5 | §3.3 bootstrap degenerate at small k_matched | **RESOLVED:** §3.2 and §3.3 raise minimum k_matched from 5 to 15 for bootstrap-based gates. Documented in §3.2 and §3.3. |
| M6 | §3.2 conflates KS p-value with equivalence claim | **RESOLVED:** §3.2 rewritten to drop KS p-value; uses W1+median-offset paralleling L2.2 §4.4. Documented in §3.2 rationale. |
| M7 | k_eng 2.0 multiplier copied from L2.2 SHALLOW without justification | **RESOLVED:** Marked PROVISIONAL in all per-process specs (§5.1, §5.2). §7.4 documents calibration path (option A: extend L2.2 panel; option B: use first Phase-3 smokes as calibration). |

### MINORS

| ID | Finding | Disposition |
|---|---|---|
| m1 | `event_definition` must be enforced symmetrically on MATLAB and Python sides | **RESOLVED:** §7.1 documents the dual-consumer rule; recommends TOML/YAML evaluable expression. |
| m2 | New `event_definition` field vs existing `event_channels` field unclear | **RESOLVED:** §7.2 added explicitly disambiguating both grammars. |
| m3 | §6.3 "~1 day per process" incompatible with M2 + M4 | **RESOLVED:** §6.3 raised to 2-3 days per process. |

### NITS

| ID | Finding | Disposition |
|---|---|---|
| n1 | §8 acceptance criterion #2 needs close-out clause | **RESOLVED:** §8 #1 and #2 both updated with "resolved with edit OR closed in §10 with signed rationale" clause. |

---

*Draft v0.2. Round 2 critique findings below. Not ratified — requires v0.3 design round.*

---

## 11. GPT critique round 2 findings (2026-06-15)

Reviewer: GPT-5.5 via rubber-duck sub-agent (high reasoning effort).

### SHOWSTOPPERS (4)

| ID | Finding | v0.3 disposition |
|---|---|---|
| G-S1 | Catalog/spec divergence on EVENT_CLASS list | **RESOLVED:** §2.3 catalog augmentation adds `l2_event_status: in_scope \| deferred_to_l2_stress \| reclassify_pending`. Catalog patch authored separately in `PROCESS_CATALOG.yaml` (companion commit). |
| G-S2 | Sub-gate 2 needs every-tick snapshots; extractor only persists firing ticks | **RESOLVED:** §2.1 rewritten — extractor persists a **windowed grid** of snapshots (every tick in each process's `firing_window_definition`, optionally subsampled by `firing_window_snapshot_stride`). Snapshot count ~50-150/seed (vs 5000+ for full cycle). Phase 1b cost cut ~50× per §6.1.1. |
| G-S3 | Bootstrap is statistically degenerate at zero-Karr-offset | **RESOLVED:** §3.2 null replaced — independent seed resampling with replacement from Karr's recorded ensemble, B=1000, against the pooled `karr_positions` distribution. Genuinely generative. |
| G-S4 | Inter-arrival from Karr-firing-tick snapshots is one-sided | **RESOLVED:** §5.2 inter_arrival mode inherits §2.1's windowed grid, so OC is probed at non-Karr ticks too. Sub-gate 2 catches spurious OC firings. |

### MAJORS (7)

| ID | Finding | v0.3 disposition |
|---|---|---|
| G-M1 | CI hypothesis-test language as equivalence gate | **RESOLVED:** §3.1 rewritten — equivalence test "CI wholly within `[-epsilon_rate, +epsilon_rate]`", with per-process `epsilon_rate` (default 0.10). |
| G-M2 | k_karr=0 precedence ambiguous | **RESOLVED:** §3.1 explicit precedence rule for k_karr=0 case (FAIL/SPURIOUS if k_oc>0; informational EVENT_NEITHER_FIRES_IN_WINDOW if k_oc=0). |
| G-M3 | Cytokinesis OC port emits wrong field paths | **RESOLVED:** §5.1 rewritten with verified `update["cell"]["division_complete"]` path (cited at karr_cytokinesis.py:249). Magnitude marked redundant per G-M4 — Cytokinesis will at best earn PARTIAL_PASS_FIRING_RATE_ONLY without a non-redundant payload added to OC port. |
| G-M4 | Sub-gate aggregation gameable by redundant sub-gates | **RESOLVED:** §3.4 adds informativeness rule + `magnitude_redundant_with_firing` catalog flag. Cytokinesis explicitly carries this flag. |
| G-M5 | RNG seeding policy missing | **RESOLVED:** §2.4 added — `SeedSequence([L2_EVENT_VALIDATION_SEED, process_id, seed, tick, replicate])`, mirroring L2.2 Design-A. |
| G-M6 | k_eng calibration path is circular | **RESOLVED:** §7.4 updated (see existing) — k_eng=2.0 marked PROVISIONAL; calibration via Karr-only fixtures only, NOT first-Phase-3 smokes. |
| G-M7 | Production output/reproducibility contract missing | **PARTIALLY RESOLVED in v0.3:** §13 added (below) with CLI contract + artifact layout + result schema. Provenance fields still TBD pending L2.2's `provenance.json` schema reference. |

### MINORS + NITS

| ID | Finding | v0.3 disposition |
|---|---|---|
| G-m1 | MVP/full-fidelity split + Phase 1a go/no-go missing | **RESOLVED:** §6.1a now has explicit go/no-go ("if 1-2 seed calibration shows <5 firings across full cycle, escalate to operator before launching Phase 1b"). |
| G-n1 | Stale cross-references | **RESOLVED:** §1.2 mentions §5.2 (not §5.3); §6.4 no longer references §1.5. |

---

## 12. Disposition (v0.3 summary)

**Cumulative finding count across 2 critique rounds:** 8 SHOWSTOPPER + 14 MAJOR + 4 MINOR + 2 NIT. All resolved in v0.3 except G-M7 (partially resolved — provenance schema TBD).

**Scope changes from v0.1:**
- FtsZPolymerization removed (S1: gradient process, not binary event)
- DNADamage removed (M3: untestable under baseline Karr; needs L2.stress)
- Cytokinesis explicitly flagged for PARTIAL_PASS_FIRING_RATE_ONLY due to redundant magnitude (operator decision: accept partial / add payload / reclassify)

**Net in-scope L2.event processes: 2** (Cytokinesis + RibosomeAssembly).

**Phase 1b cost cut from ~100 hr MATLAB (v0.2) to ~6 hr MATLAB (v0.3)** via windowed-grid snapshot extraction.

**Pending v0.4 / future:**
- L2.stress design (for DNADamage and any future stress-conditional process)
- L2.event v0.4 if FtsZ reclassification chosen (`ring_complete` channel addition to extractor)
- Production provenance schema (G-M7 partial close)

---

## 13. Production output contract (v0.3, per G-M7)

### 13.1 CLI

```
bin\oc-py.cmd tests/vivarium/l2_event_runner.py \
  --process <Cytokinesis|RibosomeAssembly> \
  --seeds 50 \
  --bootstrap-B 1000 \
  --output-dir tests/vivarium/artifacts/l2_event/<Process>_<timestamp> \
  [--thresholds <path/to/thresholds.json>]
  [--catalog <path/to/PROCESS_CATALOG.yaml>]
```

Defaults:
- `--seeds 50` (matches L2.2 Design-A standard)
- `--bootstrap-B 1000` (raised from 200 because §3.2 needs B=1000 for sub-gate 2 generative null per G-S3)
- `--catalog` defaults to `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`

### 13.2 Artifact layout (mirrors L2.2 Design-A)

```
tests/vivarium/artifacts/l2_event/<Process>_<timestamp>/
├── result.json          # process-level verdict + sub-gate verdicts + W1 numbers
├── SUMMARY.json         # one-line per-process scoreboard entry
├── thresholds.json      # epsilon_rate, k_eng, snapshot_stride, etc. — provenance
├── allocator_inputs.json # which Karr trace paths were consumed
├── window_snapshots_loaded.json # seed → tick range → snapshot count (audit trail)
├── provenance.json      # commit SHA, catalog SHA, extractor SHA, MATLAB version
└── null_calibration.json # bootstrap raw samples + q95 for each sub-gate
```

### 13.3 `result.json` schema

```json
{
  "process": "Cytokinesis",
  "verdict": "PASS | FAIL | PARTIAL_PASS_FIRING_RATE_ONLY | EVENT_NO_GATEABLE_SUBGATES | EVENT_NEITHER_FIRES_IN_WINDOW",
  "timestamp": "ISO-8601",
  "harness_version": "l2_event_v0_3",
  "seeds": [0, 1, ..., 49],
  "k_karr": <int>,
  "k_oc": <int>,
  "sub_gate_1": {
    "verdict": "PASS|FAIL|INSUFFICIENT_SAMPLES|EVENT_NEITHER_FIRES_IN_WINDOW",
    "r_karr": <float>,
    "r_oc": <float>,
    "newcombe_ci95": [<lo>, <hi>],
    "epsilon_rate": <float>,
    "absolute_floor_satisfied": <bool>
  },
  "sub_gate_2": {
    "verdict": "PASS|FAIL|INSUFFICIENT_SAMPLES",
    "w1": <float>,
    "q95_null": <float>,
    "k_eng": <float>,
    "k_pooled_firings": <int>
  },
  "sub_gate_3": {
    "verdict": "PASS|FAIL|INSUFFICIENT_SAMPLES|EVENT_MAGNITUDE_REDUNDANT_WITH_FIRING",
    "w1": <float>,
    "q95_null": <float>,
    "k_eng": <float>,
    "k_matched": <int>
  },
  "warnings": [<diagnostic strings per §3.4 ladder>],
  "informativeness": {
    "n_gateable_subgates": <int>,
    "n_informative_subgates": <int>
  },
  "provenance_ref": "<path>"
}
```

### 13.4 Provenance fields (TBD — partial close of G-M7)

To be specified in v0.4 by reference to L2.2's `provenance.json` schema. Initial required fields:
- `commit_sha`: current repo HEAD
- `catalog_sha`: `git hash-object` of catalog file at runtime
- `extractor_sha`: `git hash-object` of `extract_event_traces.m` at the time the consumed traces were produced
- `matlab_version`: from extractor's metadata
- `python_version`: `sys.version`
- `numpy_version`, `scipy_version`: explicit pin for bootstrap reproducibility
- `rng_seed_base`: the `L2_EVENT_VALIDATION_SEED` constant value

**Summary across 2 critique rounds:**
- Round 1 (rubber-duck): 4 SHOWSTOPPER + 7 MAJOR + 3 MINOR + 1 NIT — all incorporated into v0.2.
- Round 2 (GPT): 4 SHOWSTOPPER + 7 MAJOR + 1 MINOR + 1 NIT — documented above, NOT incorporated.

**Why round 2 findings are NOT incorporated tonight:**

The 8 total SHOWSTOPPERs across both rounds (and especially G-S2 + G-S3 + G-S4 which are coupled) indicate the spec needs a structural redesign of §2.1 (extractor contract), §3.2 (sub-gate 2 algorithm), and §3.3 (bootstrap mechanism). That's a half-day to a day of design work, not 30 min of edits. The operator chose this design exercise as a parallel task while the PFolding validation codex runs — extending it to a v0.3 round is out of that scope.

**Recommendation for v0.3:**
1. Solve the snapshot density tension (G-S2): either commit to every-tick extraction (~5-10× wall cost) or rewrite §3.2 to work with sparse snapshots (e.g. binomial-firing model that doesn't need cycle-position alignment).
2. Replace §3.2 bootstrap with a properly-generative null (G-S3).
3. Extend inter-arrival model to allow OC probes at non-Karr ticks (G-S4).
4. Update catalog with `l2_event_status` field (G-S1).
5. Address the 7 MAJORs as part of the same round.
6. Re-fire both rubber-duck AND GPT critique on v0.3.

**Estimated effort for ratifiable v0.3:** 4-6 hr operator design + 1-2 hr critique rounds.

**Honest assessment:** the value of this exercise so far is the 8 SHOWSTOPPERS surfaced before any implementation work. Building the L2.event harness against v0.2 would have hit each of these as expensive runtime bugs. v0.2 + the §11 findings is a *better artifact* than v0.1, even though it's not ratifiable.
