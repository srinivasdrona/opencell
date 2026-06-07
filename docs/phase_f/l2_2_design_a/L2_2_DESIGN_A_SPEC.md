# L2.2 Design-A Gate Specification

**Status:** v1.3 (2026-06-06) — frozen for implementation; codex critique-v3 returned SHIP_WITH_MINOR_FIXES and all 6 deltas have been applied.
**Owner:** OpenCell whole-cell-simulation project, Phase F
**Companion docs:**
- `PROCESS_CATALOG.yaml` — per-process bucket / scope / M / N / channels
- `L2_2_GATE_TRACKER.md` — live per-process status
- `STATUS_sb2a_audit.md` — extractor allowlist audit (codex, 2026-06-06)
- `../L2_2_STOCHASTIC_AUDIT.md` — original 4-bucket classification (2026-06-04)

This document defines the harness contract, sampling discipline,
comparison metric, threshold policy, and acceptance rule for the L2.2
("is the math right?") gate, in its **Design-A** reformulation. It is
the canonical reference for all in-scope process gates and is intended
to be published alongside the project.

**Authority chain:** when this spec, the catalog, the tracker, or the
audit disagree, this spec is authoritative for *methodology and
scope under Design-A semantics*; the catalog is authoritative for
*per-process M/N, channel definitions, and event flags*; the audit
is authoritative for the *original bucket classification* but is
explicitly superseded by this spec for *bucket assignment under
Design-A* (see §1.4). Conflicts are to be resolved by editing in
lockstep, not by silent override.

---

## 1. Purpose and scope

### 1.1 What L2.2 answers

L2.1 ("is the recipe wired right?") gives a deterministic, byte-equality
single-trace comparison: same seed, same inputs, same outputs, tick by
tick. It catches wiring bugs (missing import, swapped index, dropped
update).

L2.2 ("is the math right?") gives a **distributional** comparison:
across many independent (seed, tick) samples, does the OpenCell
implementation of process *P* produce outputs whose *distribution*
matches the Karr reference? It catches rate-constant bugs,
wrong-shape distributions, and subtle ordering / allocator differences
that pass L2.1 by coincidence on a single trace.

### 1.2 In scope

| Bucket | Process count in scope | Notes |
|---|---:|---|
| ALGORITHMIC_DEEP | 4 | state-machine or rejection-loop sampling |
| ALGORITHMIC_SHALLOW | 14 | order-dependent allocation or single coin-flip branch |
| TRIVIAL_RNG | 4 | closed-form draws written direct to state |
| **Total in-scope L2.2** | **22** | matches `PROCESS_CATALOG.yaml` tallies |

For three of these 22 processes, *one channel* per process is a
singular firing event that fires at most once per simulation lifetime
(`ReplicationInitiation`, `Cytokinesis`; analogous treatment was
considered but not adopted for `FtsZPolymerization`, see §10).
**These specific channels** are deferred to a separate L2.event gate
(§10); the *other* channels on these processes remain in scope and
are gated normally under Design A. Per-channel scope is declared in
`PROCESS_CATALOG.yaml` via the `event_channels` list field.

`RNAModification` and `RibosomeAssembly` are in-scope but **BLOCKED**
until their L2.1 traces stop being no-ops (shared blocker SB-6 in the
tracker).

### 1.3 Out of scope (for this document)

- L2.1 trace fixes (own backlog)
- L3 integration / multi-process composition (separate gate)
- Allocator correctness (logged here as an input record, see §5; the
  allocator itself is gated at L3, not here)
- Cell-level emergent metrics (mass doubling, division time) — these are L3+

### 1.4 Bucket reassignment under Design-A (supersedes audit addendum)

The 2026-06-04 audit addendum to `../L2_2_STOCHASTIC_AUDIT.md`
promoted `Replication`, `MacromolecularComplexation`, and
`Cytokinesis` from SHALLOW to DEEP on the grounds that each contains
iterated rejection/while-loop sampling or a within-tick Markov
chain. Under Design-A semantics this spec resolves that
re-classification as follows:

- `Replication` and `Cytokinesis` are kept in SHALLOW. Their
  iterated-loop / Markov-chain dynamics execute **within a single
  one-tick invocation**; the resulting per-tick channel deltas are
  exactly what Design-A samples and compares via W1. The addendum's
  promotion would only be material if we were validating across-tick
  state-machine evolution, which Design-A intentionally is not.
- `MacromolecularComplexation` is also kept in SHALLOW for the
  marginal-W1 portion of the gate, BUT the audit's concern about
  cross-complex correlations is genuine for the joint distribution.
  This is handled by the **DEEP/coupled joint-check requirement**
  in §6.2 (cross-channel rank-correlation diagnostic), which
  `MacromolecularComplexation` opts into via the catalog's
  `joint_check: true` flag.
- The TRIVIAL_RNG count (5 in the addendum, 4 in the current
  catalog) reflects a single process moved out of L2.2 scope
  entirely between the two documents; the catalog is the live
  source of truth.

Result: the addendum's revised counts (7 DEEP / 10 SHALLOW / 5
TRIVIAL = 22) are explicitly **NOT** the Design-A scope. The
Design-A scope is 4 / 14 / 4 = 22 as declared in §1.2 and in the
catalog tally. The audit's bucket *concerns* are preserved via the
joint-check flag, not via re-bucketing.

---

## 2. Design-A semantics (and why it replaces Design B)

### 2.1 The structural problem with Design B

The pre-existing harness (Design B) initialised process *P* once from
Karr's `states_before[0]` ("tick-0 fitted init"), then free-ran *P*
alone for 100 ticks, then compared the trajectory against Karr's
full-simulation trajectory.

This is **structurally incoherent** because Karr's trajectory is the
product of all 28 processes interacting through the allocator and
shared substrate pool. In isolation, *P* has no replenishment, no
removal, no allocator competition. By tick 5–10, the isolated *P* run
has drifted into a state Karr never visits, and the comparison
measures the drift, not the algorithm.

### 2.2 Design A: per-tick reset, pooled distributional comparison

For each (seed `s`, tick `t`) sample:

1. Load Karr's `before` snapshot for process *P* at tick *t*, seed *s*.
   This snapshot is **post-allocator, pre-process**: the resources the
   Karr scheduler had just handed to *P* (see §5).
2. Seed OC's RNG using `numpy.random.SeedSequence([L2_2_VALIDATION_SEED, s, t])` (§4.1 is the normative RNG contract; this step is a high-level summary).
3. Invoke OC's implementation of *P* for **exactly one tick**.
4. Capture OC's `after` snapshot.
5. Compute `delta_OC(s, t, c) = after[c] − before[c]` for each channel *c*
   in *P*'s declared channel list.
6. Compute `delta_Karr(s, t, c) = after_Karr[c] − before_Karr[c]` from
   the corresponding Karr extraction.

Across `N=50` seeds × `M` ticks (M per-process, see catalog), we
obtain `N × M` delta observations per channel for both OC and Karr.
We then compare the two empirical distributions (§6).

What this gate validates: **does OC reproduce Karr's one-tick
transition law on the set of pre-process states Karr's simulation
actually generates?** It does NOT validate (i) the allocator, (ii)
long-range autonomous dynamics, or (iii) any latent state the
extractor failed to capture. The §8 verdict should be read as a
correctness claim on the transition kernel, conditional on the input
distribution Karr produces.

---

## 3. Sample definition

- **Unit of comparison:** one scalar delta value per (seed, tick, channel).
- **Number of observations per channel per process:** `N × M`
  (e.g. Translation: 50 × 100 = 5000; ProteinDecay: 50 × 200 = 10 000).
- **Channels:** scalar observables derived from Karr state-bearing
  properties, declared per-process in `PROCESS_CATALOG.yaml` under
  `output_channels`. Catalog also declares `primary_channel` (string)
  and `event_channels` (list of strings) per process. The mapping
  from a channel name to a scalar is fixed by §3.2.
- **Aggregation across seeds and ticks:** flat pool of `N × M`
  *observations* — **not** `N × M` independent biological replicates.
  Per-tick samples within a seed share reset state but use different
  pre-process snapshots; per-seed samples are independent. The
  resampling unit for variability estimation is therefore the **seed**
  (§4.4), even though W1/KS are computed on the flat pool.

### 3.1 Why delta not absolute

Absolute `after[c]` is dominated by the initial-condition magnitude of
`before[c]`, which itself is a function of when in the cell cycle the
snapshot was taken. The delta isolates the **one-tick algorithmic
contribution** of process *P*, which is the only thing this gate can
actually validate.

### 3.2 Channel schema (scalar observable from a state property)

The Karr state surface is array-valued: a property like `substrates`
is indexed by `(metabolite, compartment)`; `monomers` by `(proteinID,
compartment)`; `rnas` by `(rnaID, compartment)`. A scalar channel
observation is derived from these arrays by a fixed aggregation rule.

For channel `c` of process *P* at sample (s, t):

```
delta_scalar(s, t, c) = aggregate(after[c]) − aggregate(before[c])
```

The catalog's `output_channels` field is now a list of *channel
specs*, each of the form:

```yaml
output_channels:
  - name: substrates                   # the scalar channel ID used in result.json
    source_property: substrates        # MATLAB property name in the .mat (case-sensitive)
    aggregation: signed_sum_all        # sum over all (row, col) elements; preserves sign
    sign_convention: production_positive    # negative = consumption, positive = production
    units: molecules_per_tick
```

Permitted aggregation rules (canonical, ordered by specificity):

| `aggregation` | Definition | When used |
|---|---|---|
| `signed_sum_all` | `sum(after) - sum(before)` over all indices, signed | Default for substrate/resource pool channels. |
| `signed_sum_per_compartment` | Returns a *vector* of one delta per compartment column. Each compartment becomes its own scalar channel `<name>__c<k>`. | When per-compartment behaviour differs materially (e.g. ProteinTranslocation). |
| `count_nonzero_changes` | `sum(after != before)` — count of indices whose value changed | Event-density channels (rare modifications). |
| `signed_sum_row_indices` | Like `signed_sum_all` but restricted to a specified row-index list | When only a sub-population of WIDs is biologically relevant. |
| `boolean_fire` | `1` if any element changed, else `0`. Renders the channel Bernoulli. | Event-channel candidates (see §10). |

The default for an `output_channels` entry written as a bare string
(e.g. `output_channels: [substrates, monomers, chromosome]`) is
`aggregation: signed_sum_all` with `source_property` equal to the
name. Channel specs are otherwise expanded forms of the same.

The `result.json` channel keys are the channel `name` field. The
calibration panel (§7.3), thresholds file (§7.4), and triage
taxonomy (§9.3) all reference these same names.

**Catalog migration commitment:** the current catalog uses the
shorthand form; the C1 harness workstream is responsible for
expanding to the full spec form for any channel whose default
`signed_sum_all` is biologically inappropriate. The default is
sound for ~80% of channels.

### 3.3 Sample-size justification

Per-channel `N × M` ranges from 1000 (TRIVIAL processes with M=20)
to 10 000 (Translation, ProteinDecay with M=100 / 200). This is
adequate to detect moderate-to-large distributional shifts at the
`k_eng × q95_null` thresholds used; we make no formal statistical
power claim. As an empirical rule of thumb, panel runs (§7.3) show
the gate is sensitive to W1 shifts comparable to a small fraction
of `σ_Karr` at `N × M = 5000`, but the exact detection threshold is
channel- and distribution-shape dependent and is reported per
channel in `result.json` rather than asserted globally. For sparse
channels with mostly-zero deltas, the §8.3
`min_nonzero_events ≥ 30` guard activates `INSUFFICIENT_SAMPLES`
before the gate emits a misleading PASS/FAIL. These choices are
pragmatic engineering, not a power-calibrated test; future M
increases for under-supported processes are tracked per-channel via
the tracker.

---

## 4. RNG policy, null calibration, and uncertainty

### 4.1 Per-sample RNG seeding

For sample (s, t), OC seeds its RNG to a stable arithmetic mixer
of (s, t) before invoking process *P*. The mixer is fixed by spec
to remove the CPython `hash` dependency:

```python
import numpy as np
ss = np.random.SeedSequence([L2_2_VALIDATION_SEED, s, t])
rng_for_sample = np.random.default_rng(ss)
```

with `L2_2_VALIDATION_SEED = 0xCA11B` (the same constant used by
the bootstrap RNG; see §4.5). `numpy.random.SeedSequence` is a
defined, documented, reproducible mixer; results are identical
across Python interpreters and `PYTHONHASHSEED` settings. The RNG
is **not** carried over from tick `t-1`.

### 4.2 Why this is sound

The gate compares **distributions**, not paired (s, t) values. So
matching Karr's per-sample RNG state would be both impossible and
unnecessary. What matters is that OC's empirical distribution
converges to the same distribution Karr's samples are drawn from at
the same input-state mix.

### 4.3 The seed-vs-biology validation problem

A natural worry: if OC and Karr disagree on some channel, is the
disagreement "real" (the underlying biology/algorithm differs) or
just sampling noise that would shrink with more samples?

We need a **null distribution**: how much would Karr disagree with
itself given the same sample budget?

### 4.4 Noise floor estimation (MANDATORY)

For each process P and each channel c, before reporting OC-vs-Karr W1,
we estimate two quantities:

**(a) Karr-only null** — the sampling distribution of W1 between two
draws of the *same* underlying distribution (Karr-vs-Karr at the
actual gate sample size), via seed-level bootstrap matched to N=50:

  1. Sample 50 seed-indices from Karr's 50 seeds **with replacement**.
     Call this subset A. Sample another 50 the same way; call it B.
  2. Pool all M-tick samples from each subset (A has 50×M observations;
     B has 50×M).
  3. Compute `W1_null_b = wasserstein_distance(samples_A, samples_B)`.
  4. Repeat `B = 1000` times, recording the empirical distribution
     `D_null_Karr(c)`. The 95th percentile is `q95_null(c)`.

This Karr-only design has three properties the prior half-split
procedure did not have:

- Sample sizes (50 seeds × M vs 50 seeds × M) match the actual
  OC-vs-Karr comparison size; the half-split estimated the null at
  25-vs-25, which inflates W1 systematically.
- A buggy OC implementation can no longer raise its own acceptance
  threshold by having inflated internal seed variability.
- `B = 1000` estimates the 95th percentile reliably; the Monte Carlo
  standard error on q95 is dominated by the underlying distribution
  rather than bootstrap sampling error at this B.

**(b) Two-sample cluster bootstrap CI** — the sampling uncertainty
of the W1 point estimate, treating *both* sides as cluster-resampled
at the seed level. Used for diagnostic reporting (not for the gate):

  1. Sample 50 seed-indices from OC's 50 seeds with replacement
     (`OC_bs`); pool the M-tick samples.
  2. Independently sample 50 seed-indices from Karr's 50 seeds
     with replacement (`Karr_bs`); pool the M-tick samples.
  3. Compute `W1_b = wasserstein_distance(OC_bs samples, Karr_bs samples)`.
  4. Repeat B = 1000 times. The 2.5% / 97.5% empirical percentiles are
     the 95% CI on `W1_OC_vs_Karr`.

This two-sample form (resampling both sides, not OC against a fixed
Karr) gives the correct sampling-variance estimate for a
two-sample statistic; the prior single-sample form understated it.

The diagnostic JSON always reports: `w1_oc_vs_karr` (point estimate),
`w1_oc_vs_karr_ci95` (CI from (b)), `q95_null` (from (a)), `n_seeds_oc`,
`n_seeds_karr`, `bootstrap_B`, and the channel classification (§8).

### 4.5 Bootstrap RNG reproducibility

The bootstrap resampling RNG is seeded from a fixed constant
(`L2_2_VALIDATION_SEED = 0xCA11B`) so re-runs produce identical
resamples and identical `q95_null` / CI values.

---

## 5. Allocator policy and input logging

### 5.1 Policy

We use Karr's `before` snapshot as-is. We do **not** re-run OC's
allocator on the loaded state before invoking process *P*. This
isolates *P*'s algorithm correctness from allocator correctness.

A consequence to acknowledge plainly: a process can pass this gate
while OC's allocator is still wrong in a way that would change *P*'s
inputs in a real composed run. That failure mode is gated at L3, not
here.

### 5.2 Allocator inputs logged (always emitted) — input-snapshot only

For each sample (s, t), the runner records the resources the Karr
scheduler had handed to *P* immediately before *P* executed:
substrate / enzyme / cofactor counts as captured in the `before`
snapshot's resource-bearing properties. This logged record is the
input Karr's process actually saw, byte-for-byte.

This file lives at:
`artifacts/l2_2_gates/<process>/<timestamp>/allocator_inputs.json`

It is always emitted. **It is an input-snapshot record, not an
allocator-comparison diagnostic.** Calling it
`allocator_inputs.json` reflects the upstream source of these
values (Karr's allocator); it does NOT mean L2.2 has visibility
into OC's allocator behaviour on the same global state — that
requires OC to be run, which Design-A intentionally does not do.

It is consumed by:

- humans, when investigating a channel that fails despite the
  algorithm appearing correct (rules out "wrong inputs to a correct
  algorithm")
- the future L3 allocator gate, as the post-allocator regression
  baseline

**Explicit limitation:** allocator divergence between OC and Karr
cannot be inferred from this artifact alone. The diagnostic
taxonomy in §9.3 marks the corresponding triage family as
"out-of-scope from L2.2 artifacts; flag for L3" rather than as a
directly inferable cause.

An earlier draft of this spec proposed an "approximate allocator-diff
via per-process slice reconstruction." That was rejected during spec
review: the reconstruction is incomplete, can produce misleading
signals, and would encourage debugging effort in the wrong direction.

---

## 6. Comparison metric

### 6.0 Scope of the comparison claim

L2.2 Design-A compares **selected one-dimensional output marginals**
of the one-tick transition kernel, conditional on Karr-generated
pre-process input states. It does **not**, by itself, validate the
full joint conditional transition kernel (joint distribution over all
output channels). For processes whose biology has tight cross-channel
coupling that a marginal-only check cannot see, §6.4 adds a joint
rank-correlation diagnostic; opt-in via the catalog's `joint_check:
true` flag (currently set on `MacromolecularComplexation`; others may
be added as evidence accrues).

### 6.1 Primary: Wasserstein-1 (W1)

W1 measures the average mass-transport distance between two 1-D
empirical CDFs. It has the same units as the underlying random
variable (counts/tick), so thresholds are interpretable.

**Implementation (public, fixed):**

```python
from scipy.stats import wasserstein_distance  # scipy >= 1.11.0
w1 = wasserstein_distance(samples_OC, samples_Karr)
```

`scipy.stats.wasserstein_distance` computes the exact 1-D W1 via the
empirical CDF integral; no binning. Pinned in `pyproject.toml`
(`scipy>=1.11,<2.0`).

### 6.2 Secondary: Kolmogorov–Smirnov (KS)

KS measures the maximum vertical gap between two empirical CDFs. It
is sensitive to shape/tail differences that W1 can mask when the
distributions have similar means.

**Implementation:**

```python
from scipy.stats import ks_2samp
ks_stat, ks_pvalue = ks_2samp(samples_OC, samples_Karr)
```

KS is **diagnostic only**: reported in the JSON but not gated on,
because at N × M = 5000 a tiny shape difference becomes
"significant" and would dominate the gate over real signal.

### 6.3 Why not paired metrics (e.g. per-(s,t) absolute error)

Exact sample pairing across OC and Karr at the RNG-state level is
unavailable: we cannot reconstruct Karr's exact pre-process RNG
state from extractor v2 artifacts. Distributional metrics are
therefore the primary choice. W1 + KS together cover location/scale
+ shape.

A future extractor that logs Karr's pre-process RNG state or the
first few uniforms consumed per tick would enable partially paired
diagnostics (seed-level paired summaries, tick-conditioned
comparisons); this design leaves room for that without depending on
it.

### 6.4 Joint check for coupled processes (DEEP / `joint_check: true`)

For processes flagged `joint_check: true` in the catalog (currently
`MacromolecularComplexation`; future additions tracked via the
tracker), the runner additionally computes pairwise Spearman rank
correlation across all pairs of non-event output channels, on both
the OC sample pool and the Karr sample pool. For each channel pair
`(c1, c2)`:

```
delta_corr(c1, c2) = | spearmanr(samples_OC[c1], samples_OC[c2]).statistic
                    - spearmanr(samples_Karr[c1], samples_Karr[c2]).statistic |
```

The joint-check verdict for the process is:

- `JOINT_PASS` — every `delta_corr` ≤ `joint_corr_tol` (default 0.15;
  overridable per-process in `thresholds.json`).
- `JOINT_FAIL` — at least one `delta_corr` > `joint_corr_tol`.
- `JOINT_INSUFFICIENT` — fewer than 2 gateable non-event channels;
  joint check not meaningful.

In v1.2 the joint check is **diagnostic only** (does not contribute
to the per-process pass verdict in §8.2). It IS reported in
`result.json` under the top-level `joint_check` block, and a
JOINT_FAIL on a JOINT_PASS-flagged process triggers a tracker note.
Promotion of the joint check to gating status is contingent on (i)
establishing a noise-floor null for `delta_corr` analogous to §4.4,
and (ii) accumulating cross-process evidence on what tolerance is
operationally tight without being noisy. Both are tracked as
"DEEP joint gate v2" follow-on work in the tracker.

---

## 7. Threshold policy

### 7.1 Per-channel thresholds

Per-channel because channels have wildly different scales
(Translation synthesises ~1 monomer/tick on average; Metabolism
consumes ~10⁴ substrate-molecules/tick).

### 7.2 Threshold formula

For channel *c* of process *P*:

```
threshold(P, c) = max(
    absolute_floor(c),               # never gate below this scale
    k_eng × q95_null(P, c)           # engineering tolerance over Karr-only null
)
```

Where:

- `q95_null(P, c)` = §4.4 procedure (a) result. Estimates the noise
  floor under the null hypothesis "OC and Karr draw from the same
  distribution". Computed from Karr-only resampling, so it does NOT
  depend on OC's behaviour; a buggy OC cannot raise its own
  threshold.
- `k_eng` = engineering tolerance multiplier; default 2.0. Calibrated
  via §7.3 panel. Allows for unavoidable implementation differences
  (RNG state, floating-point order, etc.) that are real but not
  algorithmic bugs.
- `absolute_floor(c)` = a per-channel floor on the W1 value below
  which a pass is automatic regardless of `q95_null`. **No global
  default 0.5 is set;** that value was too lenient for sparse
  Bernoulli-like channels (where a 0.10-vs-0.50 event-rate
  difference would slip through under a 0.5 floor). Instead, each
  channel's floor is specified in `thresholds.json` per §7.4. If a
  channel is missing from `thresholds.json`, the runner falls back
  to the **adaptive floor**:

      absolute_floor(c) = max(0.05,
                              0.10 × max(|mean(delta_Karr_c)|, stddev(delta_Karr_c)))

  This adaptive floor scales with the natural magnitude of the
  channel's Karr-observed delta distribution, so neither a sparse
  Bernoulli channel (small mean, small stddev → tight floor) nor a
  dense large-count channel (large mean → looser floor) gets
  systematically under- or over-protected. The constant `0.05` is
  the absolute minimum to avoid floating-point noise from registering
  as a fail. Both the fallback formula and any per-channel override
  in `thresholds.json` are reported in `result.json` for
  transparency.

**Honest framing:** this is an engineering tolerance gate, not a
calibrated hypothesis test. `q95_null` calibrates the null at
per-channel level; `k_eng` is an explicit slack parameter; the
all-channels-pass aggregation in §8.2 is a conservative QA rule, not
a family-wise 5% test.

### 7.3 Calibration of `k_eng` (SB-4)

`k_eng` is calibrated on a **panel** of channels chosen for known-good
behaviour spanning the distributional regimes AND the buckets, not a
single process. The initial panel uses canonical catalog channel IDs
(per §3.2 schema):

| Process | Bucket | Channel ID (catalog name) | Regime |
|---|---|---|---|
| Metabolism | TRIVIAL_RNG | substrates | dense, large counts |
| ProteinProcessingI | TRIVIAL_RNG | monomers | dense, mid counts |
| RNADecay | SHALLOW | rnas | sparse, small counts |
| ProteinFolding | SHALLOW | monomers | sparse, zero-inflated |
| MacromolecularComplexation | SHALLOW | complexs | dense, coupled (also `joint_check: true`) |
| Transcription | **DEEP** | rnas | DEEP representative (provisional — see note) |

**Provisional DEEP calibration note.** Only one DEEP process
(`Transcription | rnas`) appears in the initial panel. The resulting
`k_eng[ALGORITHMIC_DEEP]` is therefore marked PROVISIONAL in
`thresholds.json` until at least a second DEEP representative
(target: `Translation | monomers`) is added to the panel and the
per-bucket calibration is re-run. The runner emits a warning when a
DEEP-bucket process is gated against a provisional `k_eng[DEEP]`.

Procedure (per-bucket calibration; supersedes global single-`k_eng`):

1. Run Design-A gates on the panel processes with `k_eng = 1.0` and
   record per-channel `w1_oc_vs_karr / q95_null` ratios.
2. Compute, **per bucket**, the max observed ratio across that
   bucket's panel channels. Call these `r_TRIVIAL`, `r_SHALLOW`,
   `r_DEEP`.
3. Set `k_eng[bucket] = max(2.0, ceil(r_bucket × 1.2))` for each
   bucket. The runner consults `k_eng[bucket]` based on the gated
   process's bucket.
4. Record final per-bucket `k_eng` values, the panel data, and
   per-channel `absolute_floor` overrides in `thresholds.json`
   (committed; SHA-256 of file recorded in each run's
   `provenance.json`).

If any panel channel produces `w1_oc_vs_karr / q95_null > 5.0`, do
**not** proceed with calibration — that ratio indicates a real
algorithm bug, not a calibration question. Fix the panel channel
first.

The runner consumes `thresholds.json`; no thresholds are hard-coded.

### 7.4 `thresholds.json` schema (public contract)

`thresholds.json` is a committed, hashed configuration file. The
runner refuses to start if its SHA-256 does not match the value
recorded in the producing `provenance.json` of any artifact under
comparison.

```json
{
  "version": "1.3",
  "k_eng": {
    "TRIVIAL_RNG": 2.0,
    "ALGORITHMIC_SHALLOW": 2.0,
    "ALGORITHMIC_DEEP": 3.0
  },
  "absolute_floor_default_formula": "max(0.05, 0.10 * max(|mean(delta_Karr)|, stddev(delta_Karr)))",
  "min_nonzero_events_default": 30,
  "joint_corr_tol_default": 0.15,
  "per_channel_overrides": {
    "Translation.monomers": {
      "absolute_floor": 0.20,
      "min_nonzero_events": 50,
      "notes": "tightened after F5.1c investigation"
    }
  },
  "per_process_overrides": {
    "MacromolecularComplexation": {
      "joint_corr_tol": 0.10
    }
  },
  "calibration_record": {
    "calibrated_at": "2026-06-08T10:00:00+05:30",
    "panel_runs": ["artifacts/l2_2_gates/Metabolism/2026-06-08T09:30:00+05:30/", "..."],
    "per_bucket_panel_max_ratio": {
      "TRIVIAL_RNG": 1.4,
      "ALGORITHMIC_SHALLOW": 1.8,
      "ALGORITHMIC_DEEP": 2.6
    }
  }
}
```

Authoring discipline:
- All keys are required (except `per_channel_overrides`,
  `per_process_overrides`, which may be `{}`).
- Per-channel overrides use the dotted `Process.channelID` key
  format; both sides must match the catalog exactly (case-sensitive).
- `version` is bumped whenever the schema changes; runner pins the
  major version it supports.
- Edits are made via PR; the calibration record block is regenerated
  by the calibration workflow, not hand-edited.

---

## 8. Gate pass rule

### 8.1 Per-channel verdict

Each channel *c* is one of:

- `SEED_NOISE` — `w1_oc_vs_karr ≤ q95_null(P, c)`: divergence is
  within Karr-only sampling noise at this sample budget.
- `PASS` — `q95_null < w1_oc_vs_karr ≤ threshold(P, c)`: above null
  noise but within engineering tolerance.
- `FAIL` — `w1_oc_vs_karr > threshold(P, c)`: exceeds tolerance;
  pursue per §9.3 taxonomy.
- `INSUFFICIENT_SAMPLES` — too few nonzero events to compute reliable
  W1; see §8.3.
- `EVENT_CHANNEL_DEFERRED` — channel listed under the process's
  `event_channels:` field in catalog; see §10.

### 8.2 Per-process verdict

A process passes the L2.2 gate iff **both**:

1. At least one channel is gateable (i.e. not
   `EVENT_CHANNEL_DEFERRED` and not `INSUFFICIENT_SAMPLES`); AND
2. Every gateable channel is `SEED_NOISE` or `PASS`.

Otherwise:

- If condition (1) fails (no gateable channels remain), the process
  verdict is `NO_GATEABLE_CHANNELS` — distinct from `PASS` and from
  `FAIL`. This blocks a vacuous PASS where every channel is
  deferred or unsupported, and forces an explicit follow-up action
  (raise M, expand `output_channels`, or escalate to L2.event).
- A single `FAIL` on any gateable channel produces a process-level
  `FAIL` verdict.

Additional rule: the catalog's `primary_channel` for a process
**MUST NOT** be listed in that process's `event_channels`. The
runner refuses to start on a catalog whose primary is deferred —
that configuration would always make the process semantics
event-driven, which means the process should be treated under
L2.event end-to-end, not partially here. This caught
`Cytokinesis` in v1.1 (primary was `chromosome`, also the event
channel); the catalog was updated to make `substrates` the primary.

`EVENT_CHANNEL_DEFERRED` and `INSUFFICIENT_SAMPLES` channels do NOT
contribute to the pass/fail aggregation; they are reported but not
gated.

Rationale: if the algorithm is correct, all (gateable) channels
should be within the engineering envelope; per-channel failures are
not redundant because they pinpoint which sub-mechanism diverged
(see §9.3 taxonomy).

### 8.3 INSUFFICIENT_SAMPLES verdict

W1 and KS need a minimum nonzero-event count to be meaningful. For
sparse channels where the rare-event count is too low, the empirical
distribution is dominated by zeros and the metrics are unreliable.

A channel produces verdict `INSUFFICIENT_SAMPLES` if, in EITHER
OC's N×M observations OR Karr's N×M observations, the count of
nonzero events is below `min_nonzero_events` (default 30;
overridable per-channel in `thresholds.json`).

INSUFFICIENT_SAMPLES channels:

- Are excluded from the per-process aggregation (§8.2)
- Are reported in `result.json` with full sample statistics (nonzero
  count, max value, full sample list) so the cause can be inspected
- Trigger a tracker note recommending either (i) increase M for this
  process to gain support, or (ii) declare this channel structurally
  not-distributional and remove from `output_channels` in catalog,
  or (iii) move to event-channel treatment (§10)

This verdict prevents the gate from making confident-looking
pass/fail calls on data that cannot statistically support them.

### 8.4 BLOCKED and SKIPPED states

- `BLOCKED`: prerequisite missing (e.g. L2.1 trace is a no-op);
  process is excluded from this gate's tally until prerequisite
  lands.
- `SKIPPED`: process is `in_scope_L2_2: false` in the catalog
  (DETERMINISTIC bucket).

---

## 9. Diagnostic output

### 9.1 Always emitted (pass or fail)

`artifacts/l2_2_gates/<process>/<timestamp>/result.json`:

```json
{
  "process": "Translation",
  "verdict": "PASS",
  "timestamp": "2026-06-06T14:00:00+05:30",
  "harness_version": "design_a_v1_3",
  "seeds": [0, 1, "...", 49],
  "ticks": 100,
  "n_observations_per_channel": 5000,
  "bootstrap_B": 1000,
  "k_eng": {"TRIVIAL_RNG": 2.0, "ALGORITHMIC_SHALLOW": 2.0, "ALGORITHMIC_DEEP": 3.0},
  "channels": {
    "monomers": {
      "verdict": "PASS",
      "w1_oc_vs_karr": 0.12,
      "w1_oc_vs_karr_ci95": [0.09, 0.15],
      "q95_null": 0.41,
      "threshold": 0.82,
      "absolute_floor": 0.5,
      "ks_stat": 0.018,
      "ks_pvalue": 0.34,
      "n_nonzero_oc": 4127,
      "n_nonzero_karr": 4156,
      "samples_oc": {"mean": 1.02, "stddev": 1.31, "skew": 0.12, "kurtosis": -0.04, "min": 0, "max": 7},
      "samples_karr": {"mean": 1.04, "stddev": 1.29, "skew": 0.11, "kurtosis": -0.05, "min": 0, "max": 7},
      "is_primary": true,
      "is_event_channel": false
    },
    "substrates": {"verdict": "...", "...": "..."},
    "boundEnzymes": {"verdict": "...", "...": "..."}
  },
  "joint_check": null,
  "allocator_inputs_ref": "artifacts/l2_2_gates/Translation/2026-06-06T14:00:00+05:30/allocator_inputs.json",
  "provenance_ref": "artifacts/l2_2_gates/Translation/2026-06-06T14:00:00+05:30/provenance.json"
}
```

For processes flagged `joint_check: true` in the catalog (e.g.
`MacromolecularComplexation`), the `joint_check` top-level field in
`result.json` carries a non-null block:

```json
"joint_check": {
  "verdict": "JOINT_PASS",
  "max_abs_delta_corr": 0.08,
  "joint_corr_tol": 0.15,
  "n_pairs": 28,
  "n_pairs_over_tol": 0,
  "is_gating": false,
  "worst_pair": {"channel_a": "complexs[ribosome_50S]", "channel_b": "complexs[ribosome_30S]", "delta_corr": 0.08}
}
```

`joint_check.verdict` is one of `JOINT_PASS`, `JOINT_FAIL`,
`JOINT_INSUFFICIENT`. `is_gating: false` reflects v1.2 / v1.3
treatment of the joint check as diagnostic-only; the process verdict
is still computed from per-channel marginals. The §13 `SUMMARY.json`
schema surfaces `joint_verdict` so a green marginal PASS coupled to
a JOINT_FAIL is visible to dashboards.

### 9.2 On FAIL: additional artifacts

`failure_diagnostics.json`:

```json
{
  "failed_channels": ["substrates", "boundEnzymes"],
  "histogram_overlay_png": "artifacts/.../hist_substrates.png",
  "per_seed_w1_distribution_png": "artifacts/.../seed_w1_substrates.png",
  "seed_level_w1_summary": {
    "substrates": {"mean": 2.3, "stddev": 0.4, "worst_seed": 17, "worst_seed_w1": 3.1}
  },
  "divergence_class_labels": ["C1", "D1"],
  "notes": "human triage notes here"
}
```

Note: `worst_samples` (per-(s,t) absolute-error claims) is intentionally
NOT included. Per §6.3 we cannot pair samples across OC and Karr at
the RNG-state level, so "worst sample" framing is fake-pairing and
would mislead debugging. Per-seed W1 (across all M ticks of that
seed) is the smallest honest unit of failure attribution.

### 9.3 Divergence triage taxonomy (for FAIL diagnosis)

After L2.1 passes, a channel can still fail L2.2 due to one or more
of these families. **This is a triage checklist, not a set of
directly inferable root causes**: the runner does not auto-classify;
a human (or future agent) uses the always-emitted diagnostics
(per-channel statistics, `allocator_inputs.json`, histograms,
`provenance.json`) to assign labels. Multi-label is allowed.

Families are grouped into four categories by where the cause lives.

#### A. Observed-data adequacy (NOT a root cause; rule out first)

Before assigning any other family, confirm the failure is not just a
data-adequacy artifact:

- **A1: Sample-support insufficiency.** Channel has <
  `min_nonzero_events` in either pool. Verdict should have been
  `INSUFFICIENT_SAMPLES`, not `FAIL`. *Action: confirm §8.3 path
  was not bypassed; if it was, fix the runner; if support is
  genuinely adequate, move on.*

#### B. Harness / extractor / provenance (within the L2.2 control surface)

- **B1: Extractor / schema mismatch.** Channel exists in OC but is
  empty / zeros in Karr extraction or vice versa; the `.mat` is
  missing the property. *Look at* `pick_snapshot_properties`
  allowlist (SB-2a precedent); MATLAB property-name case sensitivity.
- **B2: Latent-state / reset incompleteness.** OC's per-tick reset
  fails to restore some latent state (transient buffers, partial
  ribosome positions, residual filament-bound counts) that Karr's
  snapshot captures only implicitly. Symptom: failure appears only
  after the first tick within a seed, or correlates with how far
  the snapshot is from a "clean" cell-cycle phase. *Look at* the
  reset code path in `_l2_2_ensemble_runner.py` and at any state
  Karr keeps that extractor v2 does not enumerate.
- **B3: Provenance / config mismatch.** Failure reproduces across
  reruns; SHAs or `thresholds.json` reveal OC was run against a
  different parameter file or commit than the Karr extraction.
  *Look at* `provenance.json`, OC commit, WholeCell extraction
  commit, `thresholds.json` SHA.

#### C. Within-process algorithm (the L2.2 question proper)

- **C1: RNG draw-order / draw-count drift.** Means roughly match
  but distribution shape differs; OC and Karr make different
  numbers of random draws per tick (or in different order). *Look
  at* per-tick draw-count instrumentation in OC vs an instrumented
  Karr trace.
- **C2: Sub-step ordering within tick.** Mean matches; shape
  differs; a sub-step (e.g. decay before synthesis vs after)
  executes in different order. *Look at* documented sub-step order
  in Karr source; reorder OC to match.
- **C3: Stoichiometry / rate constant.** Means differ by a clean
  ratio (2×, 0.5×); shapes identical up to that scale. *Look at*
  rate-constant file vs Karr's `fitConstants.mat`; check unit
  conversions. F5.1c-style.
- **C4: Boundary / edge condition.** Distribution body matches;
  tails or rare large-delta samples mismatch. *Look at* per-seed
  FAIL outliers; check guards on empty pools, capacity limits,
  integer overflow.
- **C5: Deterministic subsolver mismatch.** A TRIVIAL_RNG channel
  fails despite "trivial" stochastics; usually an upstream
  deterministic computation (FBA LP, ODE step) produces slightly
  different values. *Look at* numerical backend versions (LP
  solver, BLAS); pin and re-run.

#### D. Out-of-scope from L2.2 artifacts alone (flag and escalate)

- **D1: Allocator-input mismatch (NOT L2.2-inferable).** Failure may
  be caused by OC's allocator handing *P* different inputs than
  Karr's allocator did, on the same global state. **This cannot be
  inferred from L2.2 artifacts alone** because OC's allocator is
  never exercised by Design-A. `allocator_inputs.json` records only
  what Karr's allocator did. *Action: flag for L3 allocator gate
  investigation; do not pretend to diagnose from here.*

- **UNKNOWN.** None of the above fit; pattern is novel. *Action:*
  document the symptom, propose a new family letter, update this
  table.

The runner does NOT auto-classify; it provides the diagnostics and
a human (or future agent armed with this taxonomy) populates
`failure_diagnostics.json["divergence_class_labels"]`. Labels use
the dotted form (`"B2"`, `"C3"`, `"D1"`).

---

## 10. Event channels (out of L2.2 scope)

Some processes have one or more *channels* whose value changes
exactly once in the simulation lifetime: a firing tick at which an
irreversible state transition occurs. Examples:

- `ReplicationInitiation` — firing tick of replication start
  (channel: `chromosome`)
- `Cytokinesis` — firing tick of cell division
  (channel: `chromosome`)

`FtsZPolymerization` was considered for the same treatment, but its
ring-assembly proceeds via continuous monomer accumulation across a
window of ticks; only the final ring-closure moment is event-like,
and that closure is not exposed as a separate channel in extractor
v2. Until/unless a `ring_complete` channel is added, FtsZ's output
channels gate normally under §8.

For these specific channels, Design A's per-tick distributional
reset is not the right comparison: across N×M (s, t) observations
the firing event happens at most ~50 times (once per seed). The
problem is not that the data become Bernoulli per se (W1 is well
defined for Bernoulli); it is that the *biological question* about
firing channels is "did OC fire at the right time / right rate
conditional on input state?", not "do the per-tick deltas match in
distribution?" W1 over per-tick deltas is the wrong summary for the
right question.

**Treatment:** these specific channels are listed under the
`event_channels:` field for their process in `PROCESS_CATALOG.yaml`.
The runner skips them with verdict `EVENT_CHANNEL_DEFERRED` and they
do not contribute to the per-process pass/fail aggregation (§8.2).
The **other** channels on the same process run normally and DO
contribute to the verdict. The catalog's `primary_channel` for a
process MUST NOT be one of its `event_channels` (§8.2 invariant).

**Seed-bias documentation for sparse process windows.** Some
non-event channels on these processes (e.g. `Cytokinesis.substrates`,
`FtsZPolymerization` outputs) are only biologically active during
narrow cell-cycle windows. To make public reproduction possible
without operator judgement, the seed selection rule for any sparse
process MUST be specified explicitly in
`PROCESS_CATALOG.yaml` per-process under `seed_window:`, e.g.

```yaml
seed_window:
  tick_range_from_division: [-50, 0]   # only ticks within 50 ticks before division
  rationale: "Cytokinesis is biologically active only in late cell cycle"
```

If `seed_window:` is unset, the runner uses all M ticks per seed.

**Sketch of L2.event gate** (out of scope for this document; to be
specified in `L2_EVENT_GATE_SPEC.md`):

1. Across Karr's 50 seeds, find the empirical distribution of the
   firing tick.
2. For each Karr tick *t* where some seeds fired and others didn't,
   load the `before` snapshot and call OC's event-check.
3. OC passes iff its firing rate at each such tick is within a
   binomial CI of Karr's firing rate.
4. When OC fails to fire and Karr did, the diagnostic locates which
   input precondition (substrate count, regulator state, …) was
   already wrong — pushing the debugging effort upstream rather
   than into the event-firing code itself.

---

## 11. TRIVIAL_RNG processes

All 4 in-scope TRIVIAL_RNG processes (`Metabolism`, `DNADamage`,
`ProteinProcessingI`, `ProteinProcessingII`) use **the same harness**
as DEEP and SHALLOW. Their TRIVIAL classification means we *expect*
tight passes with small `k_eng[TRIVIAL_RNG]`; it does not justify a
separate code path, and it avoids code-path skew between buckets.

Where a TRIVIAL_RNG channel has a known closed-form distribution
(e.g. Poisson with rate λ, multinomial with parameters from
upstream FBA), the runner **SHOULD** emit a non-gating
analytical-check side artifact comparing OC's empirical moments to
the closed-form expectation. (Promoted from MAY to SHOULD per
critique v2: only 4 processes, cost is small, value is high — it
separates "random-draw mechanics wrong" from "inputs upstream
wrong" cheaply.) The check is non-gating because closed-form
inputs themselves depend on upstream computations that may diverge
between OC and Karr.

`Metabolism` is the largest contributor to the §7.3 calibration
panel.

---

## 12. Harness CLI

```
python -m tests.vivarium.l2_2_design_a_runner \
    --process <Process>                            # e.g. Translation
    --seeds <int|csv>                              # int = count (0..N-1); CSV = explicit list e.g. "0,3,7,11"
    --ticks <M>                                    # from catalog
    --karr-source <path>                           # per_process_traces_v2[_s###]
    --thresholds <path-to-thresholds.json>         # from catalog dir
    --catalog <path-to-PROCESS_CATALOG.yaml>       # for channels, event flags
    --bootstrap-B <int>                            # default 1000
    --out <result-dir>                             # artifacts/l2_2_gates/<process>/<timestamp>/
    [--null-only]                                  # compute q95_null only, skip OC run; writes null_calibration.json
```

The `--seeds` flag accepts either an integer (interpreted as "use
seeds 0..N-1") or a comma-separated list of explicit seed indices
(interpreted as exactly that list). The `result.json` always
records the resolved seed list under `seeds`, never an opaque count.

Exit codes:

- `0`: PASS (at least one gateable channel exists AND every gateable channel is SEED_NOISE or PASS)
- `1`: FAIL (at least one gateable channel is FAIL)
- `2`: BLOCKED (missing prerequisite listed in stderr)
- `3`: HARNESS_ERROR (bug in the runner itself)
- `4`: NO_GATEABLE_CHANNELS (all channels deferred or insufficient; non-vacuous treatment per §8.2)

Stdout: one-line summary; stderr: detail.

---

## 13. Artifact layout

```
artifacts/l2_2_gates/
├── SUMMARY.json                            # roll-up across all processes
├── <Process>/
│   ├── <ISO-timestamp>/
│   │   ├── result.json                     # §9.1
│   │   ├── allocator_inputs.json           # §5.2 (input-snapshot only)
│   │   ├── failure_diagnostics.json        # §9.2 (only if FAIL)
│   │   ├── histograms/                     # PNG overlays per channel
│   │   ├── thresholds_applied.json         # snapshot of thresholds at run time
│   │   ├── input_manifest.json             # §14: consumed input paths + SHA-256
│   │   ├── null_calibration.json           # §4.4(a): q95_null per channel + B used
│   │   ├── analytical_check.json           # §11 (TRIVIAL_RNG only): non-gating moments vs closed form
│   │   └── provenance.json                 # §14
│   └── latest -> <ISO-timestamp>           # symlink (Windows: junction)
```

`SUMMARY.json` schema:

```json
{
  "generated_at": "...",
  "harness_version": "design_a_v1_3",
  "k_eng": {"TRIVIAL_RNG": 2.0, "ALGORITHMIC_SHALLOW": 2.0, "ALGORITHMIC_DEEP": 3.0},
  "processes": {
    "Translation": {"verdict": "PASS", "latest_run": "...", "n_channels_gated": 3, "n_event_deferred": 0, "n_insufficient": 0, "joint_verdict": null, "warnings": []},
    "Transcription": {"verdict": "FAIL", "latest_run": "...", "failed_channels": ["rnas"], "n_event_deferred": 0, "joint_verdict": null, "warnings": ["k_eng[ALGORITHMIC_DEEP] is provisional (only 1 DEEP panel rep)"]},
    "MacromolecularComplexation": {"verdict": "PASS", "latest_run": "...", "n_channels_gated": 3, "joint_verdict": "JOINT_FAIL", "n_joint_fail_pairs": 4, "warnings": ["marginal PASS coupled with JOINT_FAIL; cross-complex correlation diagnostic flagged"]},
    "Cytokinesis": {"verdict": "NO_GATEABLE_CHANNELS", "latest_run": "...", "reason": "only gateable channel (substrates) had n_nonzero < min_nonzero_events; chromosome is event-deferred"}
  },
  "tally": {"PASS": 17, "FAIL": 1, "BLOCKED": 2, "SKIPPED": 6, "NO_GATEABLE_CHANNELS": 2}
}
```

The tracker (`L2_2_GATE_TRACKER.md`) reads `SUMMARY.json` to
populate per-process status.

---

## 14. Reproducibility

A public re-run requires the following pins. The runner emits a
`provenance.json` in each result directory capturing all of these.

**Python side:**

1. Python: `python==3.12.*`
2. NumPy: `numpy>=1.26,<2.0`
3. SciPy: `scipy>=1.11,<2.0` (required for `wasserstein_distance`
   semantics this spec depends on)
4. OS / BLAS: byte-identical numerical results require pinned
   numpy/scipy AND a matching BLAS backend. Recommended:
   OpenBLAS 0.3.x (single-thread for reproducibility:
   `OPENBLAS_NUM_THREADS=1`). MKL and Apple Accelerate produce
   *equivalent statistical* verdicts but not byte-identical
   `result.json` numerics. The determinism contract below applies
   per (OS, BLAS) combination.
5. OC commit SHA: `provenance.json["oc_commit"]`
6. `thresholds.json` content hash (SHA-256):
   `provenance.json["thresholds_sha256"]`
7. `PROCESS_CATALOG.yaml` content hash:
   `provenance.json["catalog_sha256"]`
8. `pyproject.toml` content hash recorded as the dependency
   authority; if the repo also commits a lockfile (e.g.
   `uv.lock`, `poetry.lock`, `pdm.lock`), record its SHA-256 too.
   The runner refuses to start if `pyproject.toml` SHA-256 disagrees
   with the value recorded in `provenance.json`.
9. Input artifacts SHA-256 (mirror of `input_manifest.json`):
   each Karr `.mat` consumed for the run, recorded under
   `provenance.json["inputs"]` as `{path, sha256, size_bytes}`.

**MATLAB side (Karr extraction):**

10. MATLAB release: `provenance.json["matlab_release"]` (extractor v2
    verified on R2023b; results on other releases should be
    re-validated).
11. WholeCell source revision: SHA at `data/m1_sources/WholeCell/.git`
    recorded.
12. Extractor script commit SHA:
    `scripts/matlab/extract_per_process_traces_v2.m` recorded.
13. MATLAB toolbox set: extractor uses Statistics; record full `ver`
    output.

**Seeding behaviour (pinned-as-code, not just-as-versions):**

14. Per-sample seed mixer is exactly
    `numpy.random.default_rng(numpy.random.SeedSequence([L2_2_VALIDATION_SEED, s, t]))`
    (see §4.1). `PYTHONHASHSEED=0` is still set defensively by the
    runner entrypoint even though no `hash()` call remains, in case
    a third-party dependency reintroduces hash-ordering nondeterminism.
15. Bootstrap RNG: `numpy.random.default_rng(L2_2_VALIDATION_SEED)`
    with `L2_2_VALIDATION_SEED = 0xCA11B`.
16. Bootstrap iterations: `B = 1000`.
17. All randomness in the runner uses `default_rng`, never the
    global `numpy.random` state.

**Determinism contract:**

Given identical pins (1–17) AND identical (OS, BLAS) backend AND
identical input artifacts, the runner MUST produce byte-identical
`result.json` numerical content. Across different (OS, BLAS)
backends, the verdict (PASS / SEED_NOISE / FAIL /
INSUFFICIENT_SAMPLES / EVENT_CHANNEL_DEFERRED) MUST agree; the
numeric W1 / bootstrap-CI values MAY differ in the last few decimal
places. A regression test enforces byte-identical reproduction on
the CI reference platform (Linux x86_64, OpenBLAS 0.3.x,
single-thread).

---

## 15. Provenance and changelog

| Date | Event |
|---|---|
| 2026-06-06 | v1 drafted. Resolves Q1–Q10 design discussion. |
| 2026-06-06 | v1.1: codex GPT-5 critique applied (`STATUS_design_a_spec_critique.md`). Major changes: §1.2 scope reconciliation (channel-level event-deferral, not process-level); §3 honest framing of N×M as observations not independent replicates; §4.4 Karr-only null + OC-side CI (replaces flawed half-split max procedure); §5.2 cut approximate allocator-diff (extractor v2 cannot support it); §7.3 calibration panel replaces single-Metabolism anchor; §8.1 5-verdict system; §8.3 INSUFFICIENT_SAMPLES; §9.2 dropped fake "worst_samples" pairing; §9.3 F1–F9 root-cause families with multi-label; §14 tightened pins. |
| 2026-06-06 | v1.2: codex GPT-5 critique-v2 applied. §1.4 explicit supersession of audit-addendum bucket counts (per-tick reset collapses iterated-loop concern for Replication/Cytokinesis); §3.2 channel schema with `aggregation` rules; §3.3 sample-size justification; §4.1 stable `SeedSequence([L2_2_VALIDATION_SEED, s, t])` mixer replaces `hash()`; §4.4(b) two-sample cluster bootstrap CI; §5.2 reframed `allocator_inputs.json` as input-snapshot only (not allocator diagnostic); §6.0 narrowed claim to "selected one-dimensional marginals"; §6.4 joint Spearman-correlation diagnostic for `joint_check: true` processes (non-gating in v1.2); §7.2 adaptive `absolute_floor` formula `max(0.05, 0.10·max(|mean|, stddev))` per channel; §7.3 per-bucket `k_eng` placeholder `{TRIVIAL_RNG: 2.0, SHALLOW: 2.0, DEEP: 3.0}`, Transcription/rnas added as DEEP panel rep; §7.4 published `thresholds.json` schema; §8.2 `NO_GATEABLE_CHANNELS` verdict + invariant that `primary_channel` MUST NOT be in `event_channels`; §9.3 taxonomy restructured into four groups A/B/C/D (data-adequacy / harness / within-process / out-of-scope-upstream), F10 latent-state class added under B, F8 demoted to D as non-L2.2-inferable; §10 seed-window doc rule for sparse processes; §11 closed-form analytical check promoted MAY→SHOULD for TRIVIAL_RNG; §12 `--seeds` accepts int-count or CSV-list explicitly; §13 added `input_manifest.json`, `null_calibration.json`, `analytical_check.json`; §14 (OS, BLAS) byte-identical caveat, input-artifact SHA-256 pins. Catalog: `joint_check: true` on MacromolecularComplexation; Cytokinesis `primary_channel` chromosome→substrates. |
| 2026-06-06 | v1.3: codex GPT-5 critique-v3 returned SHIP_WITH_MINOR_FIXES; all 6 lockstep deltas applied (no design changes). Header bumped DRAFT v1.1→v1.3; §2.2 step 2 stale `hash((s,t))` replaced with `SeedSequence(...)` reference; §3.3 `0.05 × σ_Karr` quantitative claim softened to empirical-rule-of-thumb; §4.2 `requirements.txt` → `pyproject.toml`; §7.3 panel aligned to real catalog channel IDs (dropped phantom `Metabolism\|enzymes`; added `MacromolecularComplexation\|complexs` SHALLOW rep; explicit PROVISIONAL note on DEEP `k_eng` until second DEEP rep added); §9.1 / §9.2 JSON examples re-keyed to actual Translation output channels (`monomers`, `substrates`, `boundEnzymes`) and a `joint_check` block example added at top level; §13 `SUMMARY.json` schema upgraded — `NO_GATEABLE_CHANNELS` first-class in tally; per-process `joint_verdict`, `n_joint_fail_pairs`, `warnings` fields added; harness_version bumped v1_2→v1_3 in all examples; §14 item 8 replaced `requirements.txt` with `pyproject.toml` + optional lockfile authority; `thresholds.json` schema version bumped 1.2→1.3. Spec frozen for implementation; no further critique rounds planned before harness build begins. |

References:

- Karr et al. (2012), Cell 150(2):389–401 — Mycoplasma genitalium
  whole-cell model.
- `docs/phase_f/L2_2_STOCHASTIC_AUDIT.md` (2026-06-04) — 4-bucket
  classification.
- `STATUS_sb2a_audit.md` (2026-06-06) — extractor allowlist audit.
- `STATUS_design_a_spec_critique.md` (2026-06-06) — GPT-5 critique
  driving v1.1 revisions.
