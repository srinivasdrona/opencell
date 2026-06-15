# L2.event Gate Specification (draft v0.1)

**Status:** v0.2 (2026-06-15) — round 1 (rubber-duck) findings incorporated. Round 2 (GPT) produced 4 new SHOWSTOPPER + 7 MAJOR findings; see §11. **Not ratified — requires v0.3 design round before implementation.**
**Owner:** OpenCell whole-cell-simulation project, Phase F
**Authority:** When ratified, this document is canonical for L2.event methodology and harness contract.

**Companion docs:**
- `L2_2_DESIGN_A_SPEC.md` — sibling per-tick distributional gate
- `PROCESS_CATALOG.yaml` — per-process scope incl. `bucket: EVENT_CLASS`, `seed_window`, `event_density`
- `L2_2_HARNESS_DESIGN.md` — original L2.2 design notes (predates L2.event split)

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

### 2.1 Karr ensemble traces

Per-cell-cycle trajectories (full cycle, NOT per-tick windows), 50 seeds, captured at ~tick resolution. For each seed:
- `firing_tick`: integer tick index of the event firing, or `null` if no firing in the cycle
- `firing_payload`: process-specific magnitude data captured AT the firing tick (e.g. for Cytokinesis: chromosome partition counts; for RibosomeAssembly: number of new ribosomes formed)
- `before_state_at_firing`: full process state snapshot at the firing tick (substrates, enzymes, boundEnzymes, etc.) — needed for OC re-execution
- `cycle_metadata`: cell cycle stage indicators (e.g. `replication_complete_tick`, `division_tick`) to enable relative timing comparison

These need a NEW MATLAB extractor pass — `extract_event_traces.m` — distinct from the existing `extract_per_process_traces_v2.m` (which captures per-tick windows). The new extractor:
- Runs Karr through a full cell cycle (~5000-7000 ticks depending on doubling time)
- Snapshots the named process at every tick BUT only persists ticks where `proc.next_update` returned a non-zero delta
- Persists the full cycle metadata once per seed

Output: `data/m1_sources/karr_native/per_process_event_traces_s{NNN}/{Process}_cycle.mat`.

### 2.2 OC re-execution apparatus

For each captured Karr `before_state_at_firing`, the harness:
1. Constructs the OC process at the matching seed
2. Loads the Karr `before_state` as the OC input state
3. Calls `process.next_update(1.0, state)`
4. Records whether OC produced an event firing and what magnitude

Same plumbing as L2.2 Design-A's `_run_*_tick` wrappers, just invoked at the specific firing-tick rather than across a per-tick window.

### 2.3 Catalog augmentations needed

Per EVENT_CLASS process in `PROCESS_CATALOG.yaml`:
- `event_definition`: structured description of what counts as a "firing" (e.g. for Cytokinesis: `update["chromosome"]["partition_counts"]` is non-empty; for RibosomeAssembly: `update["complex"]["counts"][ribosome_wid] > 0`)
- `event_payload_fields`: which fields of the `next_update` return value form the magnitude payload
- `firing_window_definition`: which cycle stages can plausibly contain the firing (used to bound the search; defaults to the full cycle)

## 3. Comparison algorithm

For each EVENT_CLASS process:

### 3.1 Sub-gate 1: firing rate

- Karr fired in `k_karr` of N seeds (typically N=50). Karr firing rate `r_karr = k_karr / N`.
- For each Karr-firing seed, replay OC at the firing tick (per §2.2). OC produces firing or no-firing.
- OC firing rate `r_oc = k_oc / N` where k_oc counts OC firings across the SAME N seeds.
- Compare via two-sample binomial test (or Wilson CI on the difference).
- **PASS** iff ALL of:
  - `|r_oc - r_karr|` within the 95% Wilson CI for the difference, AND
  - `r_karr > 0` (Karr actually fires in the captured cycles), AND
  - **`k_oc ≥ max(1, 0.5 * k_karr)`** (S3 absolute floor — OC must fire at least half as often as Karr in absolute count, with a minimum of 1), AND
  - **`k_oc ≤ 2 * max(1, k_karr)`** (S3 symmetric upper guard — OC must not fire spuriously more than 2× Karr's rate; prevents false-PASS where the difference-CI is wide enough to contain a large absolute drift)
- **FAIL** if any of the above conditions violated.
- **INSUFFICIENT_SAMPLES** if `k_karr < 5` (cannot estimate rate meaningfully).

Rationale for absolute floor: at low k_karr (e.g. 5/50), the Wilson 95% CI for a difference is wide enough to contain 0 even when `k_oc = 0`. Without the absolute floor, OC literally never firing where Karr fires 5× would PASS sub-gate 1, contradicting the EVENT_OC_NEVER_FIRES diagnostic. Per rubber-duck S3.

### 3.2 Sub-gate 2: firing-timing distribution (Karr-state-conditioned)

**Critical design choice (post-rubber-duck S2):** OC must NOT be allowed to free-run for K ticks from a single Karr snapshot. Free-running OC enters states Karr never visits within ~5-10 ticks, making the measured firing-tick distribution a measure of OC's isolated drift rather than its firing law under Karr-like inputs. This is the Design-B incoherence L2.2 §2.1 explicitly rejected.

Instead, sub-gate 2 measures **"at what fraction of Karr-visited cycle positions in a window around the firing event would OC have fired, given Karr's state at that position?"**

For each seed where Karr fired at tick `T_karr`:
- Define a window `[T_karr - W, T_karr + W]` (W per-process, see §5).
- For each tick `t` in the window: load Karr's snapshot at tick `t`, call OC's `next_update`, record whether OC would have fired (per §2.3 `event_definition`).
- Build OC's empirical "firing readiness curve" across the window — a vector of binary outcomes per tick offset.
- Compare to Karr's curve (Karr fires exactly once at offset 0; offsets elsewhere are 0).

**Aggregated metric:** for each seed, compute the offset `T_oc_first` = first tick offset in the window where OC fires (or +W+1 if OC never fires within the window). The distribution of `T_oc_first - T_karr` across the matched seeds is the firing-tick-offset distribution.

- Compute the median of `T_oc_first - T_karr` across matched seeds: `med_offset_oc`.
- Compute W1 distance between OC's firing-tick-offset distribution and a degenerate-at-zero distribution (Karr always fires at offset 0 by construction).
- Compute null bootstrap on W1: shuffle Karr-Karr seeds B=200 times, take q95 (with the M5 caveat about small-sample bootstrap — apply only when k_matched ≥ 15).
- **PASS** iff `|med_offset_oc| ≤ sub_gate_2_threshold` (per-process, see §5) AND W1 ≤ q95_null * k_eng.
- **FAIL** if either violated.
- **INSUFFICIENT_SAMPLES** if `k_matched < 15` (M5 — raised from 5 to avoid degenerate bootstrap).

Rationale for dropping KS p-value gate: per M6, p > 0.05 is "failure to reject equality", not "evidence of equality." At small k_matched, KS will essentially never reject regardless of true divergence → automatic PASS. At large k_matched it rejects minor shifts → false FAIL. L2.2 made the same choice for the same reason (§4.4); L2.event must not regress.

### 3.3 Sub-gate 3: magnitude distribution

For seeds where both Karr and OC fired AT corresponding cycle stages:
- Karr `firing_payload_karr[i]`
- OC `firing_payload_oc[i]`
- Compute W1 distance between the two payload distributions across matched seeds (payload is process-specific; see §5).
- Compute null bootstrap: shuffle Karr-Karr seed labels B=200 times, take q95.
- **PASS** iff W1 ≤ q95_null * k_eng, where k_eng is `sub_gate_3_threshold_multiplier` per process — **PROVISIONAL at 2.0** pending L2.2-style calibration on a panel of L2.event payloads (M7).
- **FAIL** if W1 > q95_null * k_eng.
- **INSUFFICIENT_SAMPLES** if matched seeds < 15 (M5 raised from 5).

### 3.4 Process-level verdict (corrected per S4)

**Rule (S4 — mirrors L2.2 §8.2 `NO_GATEABLE_CHANNELS`):**
- Verdict aggregation REQUIRES ≥ 2 of the 3 sub-gates to be actually gateable (i.e., not `INSUFFICIENT_SAMPLES`).
- If only sub-gate 1 is gateable AND it PASSes: verdict is `PARTIAL_PASS_FIRING_RATE_ONLY` (NOT a green; reported as informational, blocks the process from contributing to "L2.event greens" count).
- If 0 sub-gates are gateable: verdict is `EVENT_NO_GATEABLE_SUBGATES` (FAIL-equivalent for scoreboard purposes; sample size too small to test anything).
- If ≥ 2 sub-gates are gateable AND all gateable sub-gates PASS: verdict is `PASS`.
- If any gateable sub-gate FAILs: verdict is `FAIL`.

Diagnostic warning ladder (analogous to L2.2 §9.3):
- `EVENT_FIRING_RATE_DRIFT` — sub-gate 1 FAIL
- `EVENT_TIMING_DRIFT` — sub-gate 2 FAIL
- `EVENT_MAGNITUDE_DRIFT` — sub-gate 3 FAIL
- `EVENT_INSUFFICIENT_FIRINGS_AT_ENSEMBLE` — k_karr < 5; sample-size warning
- `EVENT_OC_NEVER_FIRES` — k_oc = 0 with k_karr ≥ 5; severe regression (caught by absolute floor)
- `EVENT_OC_FIRES_BUT_KARR_DOES_NOT` — k_oc > 0 with k_karr = 0; spurious firings (caught by upper guard)
- `EVENT_NO_GATEABLE_SUBGATES` — fewer than 2 sub-gates are gateable; sample size too small
- `EVENT_PARTIAL_PASS_FIRING_RATE_ONLY` — only sub-gate 1 was gateable and passed; not a green

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

### 5.1 Cytokinesis

```yaml
event_definition: |
  Firing = update["chromosome"]["partition_counts"] is non-empty
    OR update["events"]["division_complete"] >= 1.0
event_payload_fields:
  # Per M4: Cytokinesis L2.event gates the SCALAR partition payload (count of
  # chromosomes partitioned), NOT the per-base chromosome state. The scalar
  # reduction f(OC update) → scalar is:
  scalar_reduction: "sum of update['events']['division_complete'] across the firing tick"
  # OR if that field doesn't exist in OC's port:
  scalar_reduction_fallback: "1.0 if update['chromosome']['partition_counts'] is non-empty else 0.0"
phase_0_verification_required: |
  Before Phase 3 wiring, verify OC's karr_cytokinesis.py emits at least ONE of:
    (a) update['events']['division_complete']
    (b) update['chromosome']['partition_counts']
  Cite file:line in OC port. If neither exists, the gate is dead on arrival
  and the Phase 3 wiring must include adding the emission to the OC port.
firing_window_definition:
  cycle_stage: "pre-division to division"
  tick_range_from_division: [-50, 50]
  W_for_sub_gate_2: 25  # window half-width for §3.2 firing-readiness curve
sub_gate_1_floor_k_oc_minimum: 1  # implied by §3.1 absolute floor
sub_gate_2_threshold_median_offset_ticks: 25
sub_gate_3_threshold_multiplier: 2.0  # PROVISIONAL per M7
event_timing_model: single_firing
```

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

### 6.1.1 Wall cost reconciliation (per M1)

The v0.1 spec had inconsistent estimates ("1-2 days" vs "330 hr"). Reconciled normative estimate for v0.2:

| Phase | Per-process wall | 2 processes total wall |
|---|---|---|
| Phase 0 verification | 30 min operator | 1 hr |
| Phase 1a calibration extraction (1-2 seeds full-cycle) | 4-6 hr MATLAB | 8-12 hr |
| Phase 1b windowed extraction (48-49 seeds at the calibrated window) | ~50 hr per process (full-cycle Karr is ~50× slower than 100-tick) | **~100 hr MATLAB wall, ~5-7 days clock time accounting for single MATLAB seat** |
| Phase 2 harness scaffolding | — | 3-5 days delegated |
| Phase 3 per-process wiring | 2-3 days each (M3 update) | 4-6 days delegated |
| Phase 4 integration | 1-2 days | 1-2 days |
| **Total** | — | **~3-5 weeks calendar** |

Even after dropping FtsZ and DNADamage (S1 + M3), Phase 1b dominates at ~100 hr MATLAB wall. The MATLAB single-seat constraint (from Day-28 lesson) means this cannot be parallelized without securing additional MATLAB seats. **Operator decision required:** accept 5-7 day Phase 1b clock time, OR secure additional MATLAB seats.

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

### SHOWSTOPPERS (4 — each requires v0.3 spec edit before ratification)

| ID | Finding | Severity assessment |
|---|---|---|
| G-S1 | `PROCESS_CATALOG.yaml` still marks FtsZ + DNADamage as EVENT_CLASS; v0.2 prose removed them from §1.2 but didn't update the machine-readable catalog. Spec and catalog disagree. | **Real:** runner consumes catalog; will include processes the spec excludes. Easy fix in catalog: add `l2_event_status: in_scope \| deferred_to_l2_stress \| reclassify_pending` field. |
| G-S2 | v0.2 §3.2's Karr-state-conditioned readiness curve requires Karr snapshots at every tick in window `[T-W, T+W]`. But §2.1 extractor contract persists ONLY firing-tick snapshots. **Internal contradiction introduced by the S2 fix.** | **Real and structural:** the S2 incorporation is incompatible with the §2.1 storage model. Either extract every-tick (cost explodes — see §6.1.1 — back from ~100 hr to ~500+ hr) or rewrite §3.2 to work with sparse snapshots. |
| G-S3 | v0.2 §3.2 bootstrap is statistically degenerate. Karr's firing-tick-offset distribution is degenerate-at-zero by construction, so Karr-vs-Karr shuffling produces zero variance → q95_null = 0 → no nonzero W1 can PASS. **Statistical bug in the new §3.2.** | **Real:** the null distribution needs a real generative process (independent resampling with replacement from a non-degenerate Karr-only cohort), not a degenerate shuffle. v0.3 must redesign the §3.2 null. |
| G-S4 | RibosomeAssembly inter-arrival from Karr-firing-tick snapshots ONLY misses (a) OC firings BETWEEN Karr firings (spurious early/late) and (b) OC firings AFTER Karr's last firing. Sub-gate 2 for inter_arrival mode is therefore one-sided. | **Real:** inter_arrival model needs a point-process / risk-set treatment with snapshots at non-firing ticks too. Couples to G-S2 (same root cause: sparse snapshots can't support distributional comparison). |

### MAJORS (7)

| ID | Finding | Disposition path |
|---|---|---|
| G-M1 | §3.1 still uses CI hypothesis-test language as equivalence gate. CI containing 0 ≠ equivalence. | v0.3 should specify an equivalence margin `epsilon_rate` and require the CI to lie wholly inside `[-epsilon, +epsilon]`. |
| G-M2 | `k_karr = 0` precedence ambiguous. Upper guard `k_oc ≤ 2*max(1, k_karr)` allows k_oc=2 when k_karr=0. | v0.3: explicit "k_karr=0 ⇒ k_oc must be 0 OR verdict is FAIL/SPURIOUS". |
| G-M3 | Cytokinesis OC port emits `update["cell"]["division_complete"]`, NOT `update["events"]["division_complete"]`. §5.1 specs wrong field path. **M4 only partially closed.** | v0.3: fix §5.1 to cite verified field path; require Phase 0 to verify or update OC port. |
| G-M4 | §3.4 "≥2 gateable sub-gates" counts any non-INSUFFICIENT sub-gate, including ones derived from firing predicate (sub-gate 3 magnitude derived from same indicator as sub-gate 1 firing). Vacuous-PASS resurfaces as "rate + trivial magnitude = PASS." | v0.3: add informativeness rule — sub-gate counts only if Karr target has nontrivial support and is not mathematically redundant with another sub-gate. |
| G-M5 | RNG seeding policy missing. §2.2 + §3.2 invoke OC's `next_update` repeatedly per `(seed, tick)` but don't specify how OC RNG is seeded for each call. Reusing seeds distorts readiness curves. | v0.3: import L2.2 deterministic per-sample seeding: `SeedSequence([L2_EVENT_VALIDATION_SEED, process_id, seed, tick, replicate])`. |
| G-M6 | §7.4 option (b) "calibrate k_eng from first Phase-3 smokes" is circular — those smokes are the OC outputs being judged. | v0.3: keep k_eng=2.0 as experimental until calibrated on Karr-only fixtures with biological tolerances; do not tune thresholds on unvalidated target outcomes. |
| G-M7 | Production output/reproducibility contract missing — no CLI spec, no artifact layout, no result.json schema, no provenance fields. Sibling L2.2 has all of these. | v0.3: add sections mirroring L2.2 §11-13 (CLI contract, artifact layout, result/provenance JSON schema). |

### MINORS (1)

| ID | Finding | Disposition |
|---|---|---|
| G-m1 | Spec needs explicit MVP/full-fidelity split and Phase 1a go/no-go checkpoint to avoid spending full framework cost before confirming signal. | v0.3: add §6.0.5 Phase 1a checkpoint with explicit go/no-go criteria. |

### NITS (1)

| ID | Finding | Disposition |
|---|---|---|
| G-n1 | Stale references: §1.2 mentions §5.3 (now §5.2 after FtsZ removal); §6.4 references §1.5 (doesn't exist). | v0.3: clean up cross-references. |

---

## 12. Disposition

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
