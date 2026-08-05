# MacromolecularComplexation network 2: E1 (`MG_429_MONOMER`) provenance

Worktree `E:\opencell-worktrees\l22-macromol-network2-evidence-v2`, branch
`agent/l22-macromol-network2-evidence-v2`. This document answers the
question required before any `CONDITION_GATED` classification can be
proposed honestly: **why does network 2's upper bound (`ub`) sit at
`[0, 0]` on every one of the 5000 accepted natural samples, and is `ub>0`
structurally reachable without changing any constant or stoichiometry?**

## 1. What network 2 is (source-faithful)

From the tracked fixture (`data/karr_fixtures/per_process/
MacromolecularComplexation_flat.mat`, SHA256
`658e25f30acd8ea84f7bf4b1b2536bf994ad389d9cb575dfeefbf628fe151f01`) and
`data/karr_vendored_source/MacromolecularComplexation.m`:

- Network 2 (`complexs2complexNetworks == 2`) is the **only** disconnected
  component with more than one complex (145 of the 147 total complexes are
  singleton networks routed through the deterministic `network==1`
  branch — `evolveState`, `MacromolecularComplexation.m:294`).
- Network 2's 4 substrates (0-based fixture indices `[23, 37, 42, 192]`)
  are monomer species `MG_041_MONOMER` ("PTS system, HPr"),
  `MG_062_MONOMER` ("PTS system, fructose-specific IIABC component"),
  `MG_069_MONOMER` ("PTS system, glucose-specific IIABC component"), and
  `MG_429_MONOMER` ("PTS system, E1") — the phosphotransferase-system
  sugar-uptake machinery.
- Its 2 complexes (0-based indices `[22, 23]`) are `MG_041_062_429_PENTAMER`
  and `MG_041_069_429_PENTAMER` — the fructose-specific and
  glucose-specific PTS permease pentamers, respectively.
- Stoichiometry block (`complexComposition` restricted to these
  rows/columns): `[[1,1],[2,0],[0,2],[2,2]]`, i.e. both pentamers require
  **2 copies of E1** (`MG_429_MONOMER`) in addition to 1 HPr and 2 copies
  of their respective sugar-specific IIABC component.
- Upper bound formula (`buildProteinComplexs_bounds`, lines 390-392):
  `ub = floor(min(pool ./ stoich, [], 1))`. Since both complexes require
  E1 at stoichiometry 2, `ub[c] = floor(min(..., pool[E1]/2, ...))` — E1
  alone is sufficient to zero out both complexes whenever
  `pool[E1] < 2`.

## 2. The natural population: E1 is fixture-constant zero, not merely scarce

Re-derived directly from the real, hash-verified 50-seed × 100-tick oracle
trace population already accepted for this process's H12 evidence (the
same `oracle_seed_file_sha256` map recorded in the accepted
`docs/phase_f/l2_2_design_a/h12/MacromolecularComplexation_h12.json`; see
`scripts/l22_evidence/h12_condition_gated.py::compute_natural_network2_census`,
which performs this computation mechanically and is covered by
`tests/scripts/test_h12_condition_gated.py`):

| substrate (0-based idx) | min | max | mean | fraction of ticks == 0 |
|---|---|---|---|---|
| `MG_041_MONOMER` (23, HPr) | 50.0 | 53.0 | 51.006 | 0.0 |
| `MG_062_MONOMER` (37, fructose IIABC) | 34.0 | 34.0 | 34.0 | 0.0 |
| `MG_069_MONOMER` (42, glucose IIABC) | 31.0 | 31.0 | 31.0 | 0.0 |
| `MG_429_MONOMER` (192, E1) | **0.0** | **0.0** | **0.0** | **1.0** |

Across all 5,000 (seed × tick) samples, `MG_429_MONOMER`'s pre-tick count
is exactly `0` — not merely small or occasionally zero. It is the argmin
(binding/limiting substrate) for **both** complexes in all 10,000
(complex × sample) evaluations. This reproduces, independently, the same
structural fact `docs/phase_f/l2_2_design_a/h12/perturbation/
PERTURBATION_SPEC.json`'s `macromolecular_complexation_network2_competition`
scenario derivation already asserted by hand
(`"substrate[192]": "40 -- PERTURBED. Real fixture-constant 0 at every
seed/tick in the natural trace..."`) — this document is the first place
that claim is mechanically re-derived from the real oracle population
rather than asserted.

## 3. Is this a real biological ceiling, or an extraction-window artifact?

This is the open question, and the honest answer is: **we cannot
distinguish the two from data already in this worktree** with the
evidence at hand. Two facts, both grounded in local primary source, point
in different directions:

**Evidence for "genuinely near-zero E1 expression in this population":**
Mycoplasma genitalium's fructose PTS operon (`MG_041`/`MG_069`/`MG_429`
region) is a small, low-copy system; nothing in the fixture or the
process source asserts E1 must ever be nonzero at any particular tick —
`MacromolecularComplexation.m`'s docstring (lines 15-16) documents 149
complexes formed by this process with means/ranges that vary hugely by
complex, and doesn't promise every subunit species reaches a
complex-forming count within an arbitrary observation window.

**Evidence that the sampled window itself may be the limiting factor:**
`scripts/matlab/extract_per_process_traces_v2.m` (the actual extractor
that produced every accepted per-process trace, including this one) is a
**full whole-cell `Simulation` replay** — `karr_bootstrap()` builds the
real fitted `Simulation` object graph and every process's `evolveState()`
runs in the real scheduler order each tick (`evolve_state_with_tap`,
lines ~140-200) — this is not a synthetic/isolated per-process fixture.
The extractor's own module docstring (lines 11-16) explicitly documents
and provides for exactly this class of problem:

> `tick_offset` ... Use this to capture an "event window" for processes
> that are quiescent at cell birth (t=0) but active later -- e.g.
> RibosomeAssembly's first assembly event is ~tick 238, so
> `tick_offset=200` with `n_ticks=100` snapshots ticks 200..299 and
> captures the firing window.

The accepted MacromolecularComplexation trace was extracted at
`tick_offset=0` (ticks 0-99 from cell birth) — the same default window
that, for a different process (`RibosomeAssembly`), is already known in
this codebase to be too early to observe an event that Karr's own model
places at tick ~238. Since `MG_429_MONOMER`'s appearance as a free
substrate for `MacromolecularComplexation` (a mature monomer, per the
class's own "Initialization" docstring: "Macromolecular complexes are
initialized up to the amounts of RNA and protein subunits initialized by
other processes") is downstream of transcription, translation, and
protein processing/folding for that gene, a translation event occurring
after tick 99 would be indistinguishable, in this window, from E1 never
being expressed at all.

**No local artifact in this worktree resolves this.** No per-gene
expression-onset timing table for `MG_429` exists in
`data/karr_input_spec/`, `data/karr_fixtures/`, or `data/karr_archive/`
(checked by grep; only substrate-membership lists, not timing, are
present — e.g. `data/schemas/per_process/macromolecular_complexation.toml:12`
lists `MG_429_MONOMER` as a substrate with no expression-rate field). A
`tick_offset>0` re-extraction (the same mechanism already used for
`RibosomeAssembly`) is the only way to test the "late but real" hypothesis
directly, and that is explicitly **out of scope for this change** (no new
extraction authorized).

## 4. Conclusion

- E1 (`MG_429_MONOMER`) is not a synthetic zero — it is the real,
  hash-verified count from the accepted full-`Simulation` extraction, and
  it is provably the sole limiting substrate for network 2 in 100% of the
  accepted population.
- `ub[network 2] > 0` **is** reachable without changing any constant or
  stoichiometry — the existing, accepted, non-gating perturbation
  artifact (`docs/phase_f/l2_2_design_a/h12/perturbation/
  MacromolecularComplexation_h12_perturbation.json`) already demonstrates
  this by conditioning `MG_429_MONOMER`'s pool value alone (0 → 40) and
  observing `ub = [17, 15]`, with the genuine Monte Carlo competition loop
  (`buildProteinComplexs_montecarlokinetic`) executing for real across 50
  independent seeds.
- Whether that conditioned value is itself a state the real Karr model
  ever reaches naturally (at a later tick, per §3) is **unresolved** and
  is explicitly flagged, not asserted either way, in the `CONDITION_GATED`
  evidence artifact this document accompanies
  (`docs/phase_f/l2_2_design_a/h12/condition_gated/
  MacromolecularComplexation_h12_condition_gated.json`,
  `lifecycle_reachability_status: "UNRESOLVED"` (pinned, never a
  resolved `true`/`false`), `lifecycle_reachability_note` field; "unobserved
  in the sampled window" alone is explicitly recorded as insufficient for a
  terminal disposition — see `unobserved_in_window_alone_is_insufficient`).
- Independent of that open question, network 2's competitive branch is
  **Monte Carlo by construction**
  (`buildProteinComplexs_montecarlokinetic`, `MacromolecularComplexation.m`
  lines 334-357, draws `randStream.rand()` at line 349 each iteration) —
  no closed form exists for the selected-complex sequence. This means
  `H12_CONFIRMED` is inapplicable to this unit regardless of how the §3
  question resolves; more natural-population sampling, or a future
  `tick_offset` extraction, could at most move this row from
  "unreachable in the sampled window" to "reachable but still
  irreducibly stochastic" — never to a closed-form match.

## 5. Addendum (2026-08-05): §3's question answered by a real full-cycle probe

Worktree `E:\opencell-worktrees\l22-macromol-closure-20260805`, branch
`agent/l22-macromol-closure-20260805`. §3 above left the "genuine
ceiling vs. sampling-window artifact" question explicitly unresolved and
declared a `tick_offset>0` re-extraction out of scope for that change.
This addendum reports the result of exercising that exact alternative
via a full-natural-lifecycle probe, which **is** in scope for this
change: `scripts/matlab/full_cycle_event_scan_macromol.m` +
`scripts/l22_evidence/h12_lifecycle_reachability.py`.

**Mechanism.** The probe runs the real Karr per-tick scheduler (resource
allocation via `calcResourceRequirements_Current` + `evolveState()` in
`randperm` process order — the identical mechanism as the already-accepted
`full_cycle_event_scan_v2.m`, the precedent used to justify
RibosomeAssembly's `tick_offset=200` re-extraction) for a single seed
(seed=0), starting at cell birth, with **no conditioning of any pool or
constant**. It tracks E1's local substrate pool (`MG_429_MONOMER`) and
network-2 complex deltas every tick, logging to CSV, and stops on
`Geometry.pinched` (natural cell division) or a 33,000-tick ceiling.

**Result.** The run was deliberately stopped by the operator at real,
simulated tick 24,300 (of the 33,000-tick ceiling; natural division was
not reached) once the accumulated evidence was already decisive and
strictly increasing with no sign of plateauing:

| quantity | value |
|---|---|
| E1 pool remains exactly 0 | ticks 1 – 5,891 |
| first tick E1 pool > 0 | tick 5,892 |
| tick E1 pool first reaches 2 (the exact 2-copies-per-pentamer stoichiometric requirement) | ~tick 8,100 |
| first real network≥2 complex-formation event | tick 8,166 |
| total real network≥2 events observed (tick 1 – 24,300) | **27**, growing steadily/non-monotonic-but-net-increasing throughout, not a one-off burst |
| max E1 pool observed | 2 |

Each of the 27 events was independently verified (via the raw CSV) to
co-occur with `e1_pool == 2` and `net2_complex_delta_sum == 1` at that
tick — the exact stoichiometric signature network 2 requires, arising
from the real scheduler with no synthetic pool injection, no fixture
edits, and no conditioning of any kind.

**Conclusion for §3's question.** This directly falsifies the "E1 always
zero / genuine biological ceiling for this population" hypothesis and
confirms the "M=100/`tick_offset=0` sampling-window artifact" hypothesis
— the same class of effect already established in this codebase for
`RibosomeAssembly` (tick~238 activation), just manifesting far later
(~tick 5,892) for this process's free E1 pool. Across the natural
50-seed × 100-tick population, E1 is fixture-constant zero not because
network 2 can never fire, but because the accepted window (ticks 0-99)
ends roughly 58x before E1 first becomes nonzero in this seed's real
trajectory.

**Scope, explicitly disclosed and not overstated.**

- This is **one seed** (seed=0), not N=50. It does not claim every seed's
  E1-onset timing is identical, nor that all 50 seeds would show
  network≥2 firing by the same tick (or at all) — the accepted 50-seed
  natural census and condition-gated candidate remain the only N=50
  evidence, and are unchanged by this addendum.
- This run did **not** reach natural cell division (`Geometry.pinched`);
  it covers ticks 1-24,300 of an estimated ~32,400-tick natural cycle
  (~75%). It is real, but partial, coverage of one lifecycle.
- This addendum does **not** flip
  `condition_gated/MacromolecularComplexation_h12_condition_gated.json`'s
  own `lifecycle_reachability_status` field, which remains, correctly and
  intentionally, pinned to the literal string `"UNRESOLVED"`
  (`tests/scripts/test_h12_condition_gated.py`) — that field is scoped
  narrowly to "would a `tick_offset>0` RE-EXTRACTION of the accepted
  100-tick trace resolve this", a different (and narrower) question than
  the one this full-scheduler probe answers. This addendum instead
  records its own finding in a new, separate, NON-GATING artifact:
  `docs/phase_f/l2_2_design_a/h12/lifecycle_reachability/
  MacromolecularComplexation_h12_lifecycle_reachability.json`
  (`scripts/l22_evidence/h12_lifecycle_reachability.py`), which is not
  consumed by `verdict.py`, `generator.py`, `PROCESS_CATALOG.yaml`, or
  `evidence_index.json`, and never claims `H12_CONFIRMED`,
  `H12_OBSERVED_REGIME`, `PASS`, or an enacted `CONDITION_GATED` value.
- §4's independent, unaffected conclusion still holds: network 2's
  competitive branch is Monte Carlo by construction
  (`buildProteinComplexs_montecarlokinetic` draws `randStream.rand()`
  each iteration), so `H12_CONFIRMED` remains structurally inapplicable
  to this unit regardless of how the reachability question resolves.

