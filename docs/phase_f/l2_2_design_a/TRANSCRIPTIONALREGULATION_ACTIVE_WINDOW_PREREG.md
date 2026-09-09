# TranscriptionalRegulation L2.2 Distributional Gate — Preregistration

## 2026-09-08 SECOND REWRITE (Opus re-review of the first rewrite, addressed here) — CURRENT AUTHORITATIVE DESIGN

**The "2026-09-08 REWRITE" section directly below this one was itself found
insufficient on re-review** (kept beneath, unmodified, for the historical
record -- its diagnosis of the ORIGINAL rejected design's circularity is
still correct and still the reason a "test OC against OC" design can never
work; only its OWN pilot implementation had further gaps, closed here).
Five further gaps, now closed, with a real tested implementation
(`scripts/l22_evidence/txreg_pit_gate.py`,
`tests/scripts/test_l22_evidence_txreg_pit_gate.py`, 17 unit + 1 real-trace
integration test):

1. **Karr's REAL trace winner, not OC's ledger-restored SIMULATED one.**
   The first rewrite's pilot script (`tmp/pit_pilot_ledger_winners.py`,
   kept as historical evidence, not deleted) derived "Karr's real winner"
   by re-running OC's own `next_update` under the L2.1 chromosome-RNG
   ledger and reading OFF OC's OWN resulting state -- correct only by
   relying on the *separately established* L2.1 GENUINE bit-identity
   proof, and still, mechanically, an OC-simulation-derived value, not a
   directly-observed one. `txreg_pit_gate.py::extract_competition_events`
   instead reads Karr's real winner DIRECTLY from the trace's own
   `states_after` `tfBoundPromoters`/`boundTFs` deltas -- zero OC
   simulation, zero RNG replay, zero ledger reads anywhere in this
   module's winner-determination path. The candidate SET/weights (which
   sites even competed, and their affinities) still legitimately come
   from OC's own `candidate_sites_for_tf` applied to the trace's real
   `states_before` -- that is testing OC's LAW, which is the entire point
   of an L2.2 gate; only the WINNER identification changed.
2. **Post-mask renormalized weights.** `compute_pit_values` restricts
   every event's weight vector to the `accessible_mask`-passing subset
   before computing the categorical/Plackett-Luce law, renormalizing to
   sum to 1 over that subset only -- never the raw, full coarse-candidate
   weights. A winner found outside the accessible subset raises
   (`AssertionError`), rather than being silently dropped or scored
   against the wrong denominator.
3. **Randomized PIT with a separately-seeded analysis RNG; mid-P
   descriptive only.** `compute_pit_values` draws the continuous
   randomization uniform from a dedicated `numpy.random.default_rng`
   instance (an explicit `analysis_rng_seed` argument, e.g. `12345` in
   the pilot run below) -- never `TxRegMcgRandStream`/`_chromosome_rng`/
   `_rng`. The gate statistic (KS test) is computed ONLY on the
   randomized values; the deterministic mid-P values are also reported
   (`PitResult.mid_p_pit_values`) but explicitly labeled descriptive-only,
   never fed into the KS test.
4. **Canonical, hash-bound evidence bundle.** `write_evidence_bundle`
   writes `result.json`/`input_manifest.json`/`provenance.json` (matching
   `scripts/l22_evidence/schema.py`'s existing file-naming convention) to
   `docs/phase_f/l2_2_design_a/evidence_bundle/TranscriptionalRegulation/latest_event/`,
   binding: the genuine trace's own sha256, its L2.1-ledger sidecar's
   sha256 (present for completeness; never read by this gate's own
   analysis), this generator module's own source sha256, and
   `karr_transcriptional_regulation.py`'s source sha256. See "Known scope
   boundary" in the module's own docstring for what this does NOT yet do
   (wire into `scripts/l22_evidence/generator.py`'s/`verdict.py`'s
   existing `design_a_per_tick`/`event_class` harness dispatch, nor edit
   `PROCESS_CATALOG.yaml` -- both explicitly deferred, unchanged from
   every prior version of this document).
5. **Positive-control power demonstration -- honestly reported, not
   cherry-picked.** Three perturbations were run against the SAME 45
   genuine events / 48 pooled values (existing seed-0 trace only, no new
   extraction):
   - `occlusion_disabled` (real historical bug class, ticks 221/684):
     KS=0.159, **p=0.160** -- does NOT reach significance (occlusion is
     rare: only 2 of 4000 ticks).
   - `uniform_weights` (ignore real site affinities): KS=0.093,
     **p=0.765** -- does NOT reach significance (this dataset's real
     winners do not appear to depend on weight-magnitude strongly enough
     for a flat law to look implausible at N=45).
   - `shuffled_weights` (each event's weights independently,
     deterministically permuted across its own candidates): KS=0.212,
     **p=0.023** -- REACHES significance. This is the demonstrated
     positive control: the gate genuinely CAN reject a wrong
     weight-to-candidate law at this pilot's sample size.
   The two non-significant perturbations are reported as genuine findings
   about this pilot's CURRENT power profile (adequate to detect
   weight/candidate-identity mismatches; not yet adequate, at N=1 seed, to
   detect rare/narrow defects like occlusion, or a purely-magnitude-blind
   defect) -- not suppressed because they were inconvenient. This is
   exactly the power gap the deferred N=10 cohort exists to close.

### Deferred (unchanged from every prior version of this document)

- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` / `evidence_index.json`
  — still not edited.
- The 9-additional-seed extraction (`N_seeds=10` target) — still NOT run.
  No MATLAB cohort launch of any kind was performed for this rewrite
  either; `extract_competition_events` re-analyzes ONLY the
  already-extracted, already-accepted seed-0 trace via pure-Python replay
  (no MATLAB invocation, no new host-wide MATLAB session).
- No cohort-wide KS/AD gate execution or verdict -- the numbers above are
  a PILOT (`result.json`'s own `verdict` field is literally
  `"PILOT_ONLY_NOT_A_GATE_VERDICT"`), not a gate pass/fail.
- Wiring into `scripts/l22_evidence/generator.py`/`verdict.py`'s existing
  harness dispatch (see module docstring "Known scope boundary").

On approval: (1) run the 9 additional seed extractions via
`run_matlab_slot.ps1` (subject to the shared MATLAB-slot capacity
constraint), (2) re-run `extract_competition_events`/`compute_pit_values`
across all 10 seeds' pooled events, (3) re-run all three positive controls
at the larger N to check whether `occlusion_disabled`/`uniform_weights`
also reach significance with more power, (4) apply the catalog delta
below, and (5) decide the actual gate verdict.

---

## 2026-09-08 FIRST REWRITE (superseded by the SECOND REWRITE above; kept for the historical record of the circularity diagnosis)

**The original design below (everything from "## Scope" onward, kept
verbatim beneath this section for the historical record) was REJECTED.**
Root defect: its gate statistic pooled PIT values computed from **OC's OWN,
independently-(fresh-)seeded `TxRegMcgRandStream` realization** -- a
simulation seeded and run forward with no relationship to Karr's real
recorded RNG input state -- and tested those PIT values against **the exact
same closed-form weighted-categorical / Plackett-Luce law that stream
implements by mathematical construction**. Any correctly-implemented RNG
necessarily produces draws whose PIT values are Uniform(0,1) under the law
it implements -- this is a tautology, not a test. The design never touched
a single outcome from the genuine Karr trace; it was, in effect, a unit
test of the RNG library re-validating itself, with zero statistical power
to detect ANY Karr-fidelity defect (a bug in candidate-set construction,
occlusion, damage, or footprint logic would pass this gate exactly as
easily as no bug at all, since the gate never compares to Karr).

**The fix:** replace "OC's own fresh-seeded realization" with **Karr's real,
independently-verified winners**, obtained via the L2.1 chromosome-RNG-
ledger-restored replay (`chromosome_rand_stream_ledger`,
`decisions/dec-006-shared-chromosome-randstream-input-oracle.md`) that the
dedicated L2.1 test (`tests/vivarium/
test_karr_transcriptional_regulation_l2_replay.py`) independently proves
produces OUTPUT bit-identical to Karr's real trace at all 4000/4000 ticks,
all 5 observable surfaces. Under that independently-established proof, the
site OC selects at every competition event during a ledger-restored replay
**is** Karr's real winner (not an arbitrary simulated one) -- so testing
whether THAT winner's PIT value under the closed-form law is Uniform(0,1)
is a genuine, non-circular test of whether the closed-form law actually
describes Karr's real empirical selection behavior. This is "test Karr
winners under OC's law" (the closed-form Plackett-Luce/categorical law OC's
`TxRegMcgRandStream.randsample` implements) using a **Karr-derived
null-generating mechanism** (the ledger-restored replay, not an
independently-fresh-seeded one) -- not "test OC's own simulation against
itself."

### Pilot result (existing seed-0 trace only -- NO new extraction, NO cohort launch)

To confirm the corrected design actually runs and to report real numbers
(not just a hypothetical design) before committing to a cohort,
`tmp/pit_pilot_ledger_winners.py` (uncommitted, disposable analysis script)
replayed the ONE accepted genuine seed-0 4000-tick trace through the
ledger-restored mechanism, capturing every `_sample_accessible_sites_batched`
call with `n_candidates > 1` (a genuine competition event) and computing the
mid-P PIT of the REAL (ledger-restored, proven-Karr-identical) winner(s)
under the closed-form law, using a fixed weight-descending ranking
convention (deterministic mid-P; no auxiliary randomization uniform -- a
disclosed simplification appropriate for a pilot, see "Known simplifications"
below):

```
n genuine (n_candidates>1) competition events: 45
n pooled PIT values (one event can contribute >1 for a k>1 batched pick): 48
KS statistic = 0.1372, p = 0.2988 (two-sided, vs Uniform(0,1))
mean = 0.5397 (expected ~0.5), std = 0.2753 (expected ~0.2887)
```

This is **NOT a gate verdict** -- N=48 pooled values from one seed is
underpowered (see the original design's own power analysis below, which
correctly estimated needing ~60-100 pooled events for adequate power
against a moderate effect size; this pilot's 45 events is close to but
below that floor, consistent with the original design's linear
extrapolation from a single seed). It is reported as evidence that (a) the
corrected mechanism runs end-to-end against real evidence without error,
(b) the corrected mechanism produces a plausible (non-degenerate, not
trivially 0 or 1) p-value, unlike the rejected design's guaranteed-uniform
tautology, and (c) the observed event count (45, vs. the original design's
41 tally from an earlier, less-complete instrumentation pass) is consistent
enough with the original design's feasibility estimate that its N_seeds=10
extraction plan (still NOT executed by this document) remains a reasonable
target for a properly-powered gate.

### Known simplifications in the pilot (to be resolved before a real gate run, not before this design review)

1. **Deterministic mid-P, no randomization uniform.** A textbook exact PIT
   for a discrete/categorical law uses an auxiliary independent
   `Uniform(0,1)` draw to place `u` continuously within
   `[F(rank-1), F(rank)]`; this pilot instead uses the fixed midpoint. This
   is a common, defensible approximation (used elsewhere in calibration
   literature for coarse categorical PIT checks) but is not textbook-exact;
   the production gate implementation should draw the auxiliary uniform
   from a SEPARATE, clearly-labeled analysis-only RNG stream (never
   `TxRegMcgRandStream`/`_chromosome_rng`/`_rng`, to avoid any appearance of
   reintroducing circularity) and report both conventions if they disagree.
2. **Batched-rejection candidate pool not modeled.** Real
   `sampleAccessibleRegions` permanently zeros a drawn-but-rejected
   candidate's weight for the REST of that call (even across multiple
   inner while-loop batches), not just within one batch; this pilot's
   Plackett-Luce conditional-removal step only removes ACTUALLY-CHOSEN
   winners from the remaining pool between successive picks of a `k>1`
   batched bind, not transiently-drawn-but-rejected ones. This matters only
   when a competition event ALSO has an `is_accessible=False` candidate
   AND `k>1`, a narrow intersection; unaffected `k==1` events (the
   documented dominant case) are exact under this simplification.

### Deferred (still not executed by this rewrite, matching the original mandate)

- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` / `evidence_index.json`
  — still not edited.
- The 9-additional-seed extraction (`N_seeds=10` target) — still NOT run.
  No MATLAB cohort launch of any kind was performed for this rewrite; the
  pilot above re-analyzes ONLY the already-extracted, already-accepted
  seed-0 trace via pure-Python replay (no MATLAB invocation).
- No cohort-wide KS/AD gate execution or verdict.

On approval, the next task should: (1) apply the catalog delta below
(unchanged from the original design), (2) run the 9 additional seed
extractions via `run_matlab_slot.ps1` (subject to the shared MATLAB-slot
capacity constraint), (3) promote the pilot script above into a proper,
tested, committed module (resolving the two simplifications above), and
(4) run the pooled KS/AD gate on all 10 seeds and report the verdict.

---

## Original design (2026-09-05, REJECTED 2026-09-08 -- kept verbatim below for the historical record; do not re-approve without the rewrite above)

## Scope

This document freezes a proposed L2.2 distributional-gate design for
`TranscriptionalRegulation`'s site-level TF-promoter binding surface
(`tfBoundPromoters` / `boundTFs`) **without editing the shared catalog or
evidence index** (`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`,
`evidence_index.json`) and **without running a cohort**. It is submitted for
review before either happens.

## Why this exists (catalog is stale)

```yaml
- name: TranscriptionalRegulation
    oc_module: opencell/vivarium/karr_transcriptional_regulation.py
    bucket: DETERMINISTIC
    in_scope_L2_2: false
    rationale_M: "no RNG"
    notes: "L2.1 sufficient."
```
(`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:524-534`)

This is factually wrong as of the 2026-09-03/04/05 L2.1 fix
(`STATUS_L21_TXREG_ACTIVE_FIX.md`): the process genuinely ports Karr's
`RandStream('mcg16807')`-driven weighted-without-replacement TF-site
competition (`TranscriptionalRegulation.m::bindTranscriptionFactors` ->
`ChromosomeProcessAspect.bindProteinToChromosome` ->
`Chromosome.m::sampleAccessibleRegions`). `rationale_M: "no RNG"` and
`bucket: DETERMINISTIC` no longer describe the source process, regardless of
whether L2.1 has reached full bit-identity. **Reclassification is a scoping
decision for the maintainers** (this document proposes `bucket: TRIVIAL_RNG`,
`in_scope_L2_2: true`, see "Recommended catalog delta" below) — not made here.

## Update (2026-09-05): L2.1 has since closed to GENUINE

The section below ("Why L2.1's residual gap does not block L2.2") was written
while L2.1 was still CODE_GAP at tick 11. L2.1 has since closed to **GENUINE**
(full 4000/4000-tick bit-identity, see `STATUS_L21_TXREG_ACTIVE_FIX.md`'s
"2026-09-05 chromosome-RNG-ledger closure" and
`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`). This *strengthens*, not
weakens, the case below: the process's own `mcg16807`-driven weighted-sampling
mechanism is now proven bit-exact against Karr's real shared-chromosome-stream
draws for every tick of the existing trace, not merely "independently verified
for the algorithm in isolation" as it was when this section was first written.
The distributional-gate design and its analytical null are unaffected by this
update (the PIT-vs-Uniform null is derived from the closed-form selection law,
independent of L2.1 status either way) — this note exists only to keep this
document's framing current, not to change the design.

## Why L2.1's residual gap does not block L2.2

L2.1 (bit-exact per-tick replay) currently has an open, mechanism-confirmed gap
at tick 11 of the one existing genuine trace: Karr's real weighted site draw
is made by `Chromosome.m::sampleAccessibleRegions` using **the chromosome
state's own shared `randStream`**, not any single process's — a stream
consumed every tick by every Karr process that calls
`bindProteinToChromosome` (DNA repair, replication, ribosome assembly, etc.),
in a per-tick randomized process order (see STATUS section "2026-09-04/05
continuation" for the full mechanism and live-MATLAB evidence). This makes
**per-realization** bit-identity intractable without modeling ~28 processes'
shared-stream draws.

L2.2 does not require per-realization identity. It asks a strictly weaker
question: does OC's *own*, independently-seeded `TxRegMcgRandStream`-driven
site-selection mechanism draw from the theoretically correct probability
law, in the aggregate, across many independent realizations? OC's own
`mcg16807` port is separately, directly verified bit-exact against live
MATLAB (`scripts/matlab/probe_txreg_mcg_randsample.m`,
`probe_txreg_real_sample_accessible_regions.m`) for the actual weighted
selection *algorithm* (Park-Miller mcg16807 core, MathWorks
`randsample(s,n,k,replacement,w)` semantics, `Chromosome.m`'s batched
`sampleAccessibleRegions` padding). What is NOT verified end-to-end is
whether OC's stream POSITION at any given tick matches Karr's real,
cross-process-entangled stream position — an L2.1, not L2.2, question. This
is the standard L2.1/L2.2 split already established for other stochastic
processes in this catalog (e.g. `EVENT_CLASS`/`TRIVIAL_RNG` buckets whose
L2.2 gate is explicitly a distributional test, not a per-tick replay).

## Existing-trace inventory (performed before any extraction plan, per mandate)

- `data/m1_sources/karr_native/per_process_traces_v2/TranscriptionalRegulation_100ticks.mat`
  — canonical 100-tick, seed 0. Zero `boundTFs`/`tfBoundPromoters` deltas in
  this window (already noted in `STATUS_L21_TXREG_ACTIVE_FIX.md`): useless
  for this gate, too short to reach any TF-competition event.
- `data/m1_sources/karr_native/per_process_traces_v2_event_s000/TranscriptionalRegulation_4000ticks.mat`
  — 4000-tick, seed 0 (the only genuine active-window trace for this
  process). **Already tallied for this prereg** (see below) — no new
  extraction needed to validate the design's feasibility.
- `docs/phase_f/l2_2_design_a/evidence_index.json`: zero references to
  `TranscriptionalRegulation` (grep-confirmed).
- `docs/phase_f/l2_2_design_a/evidence_bundle/`: no `TranscriptionalRegulation`
  subdirectory (only an unrelated `Transcription` directory exists).
- **Conclusion: exactly one genuine multi-hundred-tick trace exists (seed 0,
  4000 ticks); zero L2.2 evidence exists anywhere.** A real extraction of
  additional seeds is required to reach adequate power (see below).

## Empirical tally from the existing seed-0 trace (feasibility check)

Instrumented replay of `TranscriptionalRegulation_4000ticks.mat` (seed 0)
through OC's `_sample_accessible_sites_batched`, counting every call to the
weighted-sampling primitive and its candidate-set size:

| candidate-set size (`n`) | call count |
|---|---|
| 1 (trivial/forced, no information) | 67 |
| 2 | 11 |
| 3 | 5 |
| 4 | 2 |
| 5 | 6 |
| 6 | 4 |
| 7 | 10 |
| 8 | 2 |
| 9 | 1 |
| **total genuine (`n>1`) competitions** | **41** |

(108 total sampling attempts; 41 are genuine multi-candidate competitions
carrying an RNG signal, spread across 41 distinct active ticks out of 4000.)
This confirms the design is feasible: a single seed already yields a usable
number of competition events, and extrapolating linearly, a modest number of
additional seeds reaches a well-powered pooled sample (see below).

## Proposed metric: probability-integral-transform (PIT) against an exact analytical null

For **every** genuine competition event (`n_candidates > 1`, i.e. every one
of the 41+ tallied above, pooled across seeds), Karr's own algorithm
(`Chromosome.m::sampleAccessibleRegions` -> `RandStream.randsample`, verified
in `TxRegMcgRandStream.randsample`) defines an **exact, closed-form
selection law** given only the (deterministically known, not itself
stochastic) candidate set and affinity weights at that tick — no Karr-side
empirical bootstrap is needed:

- **`k == 1` (dominant case; the vast majority of the 41 events above, since
  most active ticks bind exactly one TF copy):** the winning candidate
  follows a plain weighted-categorical (multinomial) law,
  `P(win = i) = w_i / sum(w)`.
- **`k > 1` (rare; batched without-replacement draws):** the *sequence* of
  accepted picks follows the **Plackett-Luce** model (the well-known exact
  law generated by MathWorks' real with-replacement-then-reject algorithm,
  i.e. `RandStream.m`'s `randsample(n,k,false,w)` branch):
  `P(i_1, i_2, ..., i_k) = prod_{j=1}^{k} w_{i_j} / (sum(w) - sum_{l<j} w_{i_l})`.
  This is exact, not approximate — it is the textbook closed form for
  weighted sampling without replacement.

For each genuine competition event, compute the **PIT value** of the
realized winner under this exact law: rank all candidates by weight, and let
`u = F(winner)` where `F` is the CDF of the (exact, closed-form) categorical
law evaluated just below/at the winner's rank (standard mid-P or
randomized-PIT convention to keep `u` continuous for discrete laws). Under
`H0` (OC's realized draws are governed by the correct law), the pooled set
of `u` values across all competition events (across all ticks, across all
seeds) is **Uniform(0, 1)**, independent of candidate-set size or weight
values — a single, dimension-free, exact analytical null. No Karr-side
simulation, bootstrap, or empirical resampling is required to construct it.

**Gate statistic:** two-sided Kolmogorov-Smirnov (or Anderson-Darling, more
sensitive in the tails) test of the pooled `u` values against `Uniform(0,1)`.
`PASS` if `p >= 0.05` (two-sided, no multiple-comparison correction needed —
this is a single pooled test, not per-channel/per-tick). Report the observed
KS statistic and `p`-value; do not thresholds-shop after seeing the result
(this document freezes the test and its rejection rule before any additional
extraction).

**Secondary, informational-only check:** active-tick event rate (fraction of
ticks per seed with `n_candidates > 1`) compared between OC and the genuine
Karr trace via a simple two-sample proportion test — informational because
this is fundamentally an L2.1 (deterministic-input) property, not a
stochastic-law property, and is already covered by the ongoing L2.1 effort.

## Required N (seeds) / M (ticks) and power

- **M_ticks = 4000** per seed (matches the one existing accepted trace
  family exactly — no protocol change, same extraction recipe).
- Seed 0 alone yields 41 genuine competition events. Extrapolating linearly
  (no reason to expect strong seed-to-seed variation in the *rate* of
  competition events, since it is driven by chromosome accessibility
  dynamics that are structurally similar across seeds), **N_seeds = 10**
  (seeds 0-9; seed 0 already extracted) is expected to yield on the order of
  **300-500 pooled competition events**.
- **Power justification:** a KS test against a fully-specified uniform null
  reaches conventional power (β ≈ 0.8, α = 0.05) to detect a
  Kolmogorov distance of ~0.15-0.2 (a *moderate* miscalibration, e.g. a
  systematic ~15-20 percentile-point bias in winner selection) at n ≈ 60-100
  pooled samples, and much smaller effect sizes (D ≈ 0.08-0.10) at n ≈
  300-500 (standard KS power tables / asymptotic `D_crit ≈ 1.36/sqrt(n)` for
  α=0.05). N_seeds=10 (≈400 pooled events, extrapolated) comfortably clears
  the higher bar and gives headroom against the extrapolation being
  optimistic by 2x.
- **If seed-to-seed extraction shows the 41-events/4000-ticks rate does not
  hold** (e.g. materially fewer competitions in later seeds), the frozen
  fallback is to raise `N_seeds` in increments of 10 until the pooled event
  count exceeds 100 (minimum) / 300 (target), never to change the metric or
  null after seeing partial data.

## Extraction plan (not executed by this document)

For each seed `s` in `[1, 9]` (seed 0 already exists):

```
bin\oc-py.cmd -m scripts.matlab... (via run_matlab_slot.ps1, slot-safe)
  extract_per_process_traces_v2({'TranscriptionalRegulation'}, ...
    'per_process_traces_v2_event_s%03d' % s, 4000, s)
```

i.e. the exact same recipe already used for seed 0
(`data/m1_sources/karr_native/per_process_traces_v2_event_s000/`), with
`seed=s` and output subdir `per_process_traces_v2_event_s%03d`. No
`tick_offset`/`window_contract` change from the accepted seed-0 recipe (no
burn-in, no anchor-window discovery — the existing recipe already produces
usable competition events from tick 1).

Each extraction is an independent ~4000-tick full-scheduler MATLAB run
(compute cost comparable to the existing seed-0 extraction); must go through
`scripts/tools/run_matlab_slot.ps1` (slot-safe, shared MATLAB license) like
all other MATLAB work in this repo.

## Recommended catalog delta (not applied by this document)

```yaml
- name: TranscriptionalRegulation
    oc_module: opencell/vivarium/karr_transcriptional_regulation.py
    bucket: TRIVIAL_RNG            # was: DETERMINISTIC
    in_scope_L2_2: true            # was: false
    M_ticks: 4000
    N_seeds: 10
    event_density: "sparse (~1-2% of ticks; ~41 genuine multi-candidate competitions per 4000 ticks, seed 0)"
    input_channels: ["enzymes (protein/complex TF counts)", "chromosome (polymerizedRegions/monomerBoundSites/complexBoundSites)"]
    output_channels: ["tfBoundPromoters", "boundTFs"]
    primary_channel: "tfBoundPromoters"
    karr_artifact: "per_process_traces_v2_event"
    rationale_M: "genuine RandStream('mcg16807')-driven weighted-without-replacement TF-site competition (Chromosome.m::sampleAccessibleRegions); 'no RNG' rationale is stale as of the 2026-09-03/04/05 L2.1 site-level rewrite."
    notes: "L2.2 gate is a PIT-vs-Uniform(0,1) distributional test over genuine (n_candidates>1) competition events, not per-tick W1 -- see TRANSCRIPTIONALREGULATION_ACTIVE_WINDOW_PREREG.md."
```

## Explicitly NOT done by this document

- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` — not edited.
- `docs/phase_f/l2_2_design_a/evidence_index.json` — not edited.
- No additional-seed extraction run.
- No cohort/sweep/gate execution.

This document is a design freeze for operator/Opus review. On approval, the
next task should: (1) apply the catalog delta above, (2) run the 9 additional
seed extractions via `run_matlab_slot.ps1`, (3) implement the PIT-vs-Uniform
metric (new, small, standalone module — reusing
`TxRegMcgRandStream.randsample`'s exact algorithm to compute the closed-form
`F` for each event, not a re-derivation), and (4) run the pooled KS/AD gate
and report the verdict.
