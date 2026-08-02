# H12 Evidence Report: 5 `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` rows

Worktree `E:\opencell-worktrees\l22-h12`, branch `agent/l22-h12`, rebased
onto `main` (result-schema/evaluator base `fdefdb5`). This is a **repair**
of a prior H12 delivery (frozen baseline `0e6ddaf`) per an Opus5 review
that identified real defects in the original methodology (see "What was
wrong with v1" below). It accompanies commits touching
`scripts/l22_evidence/h12.py` (formula version bumped 1.0.0 → 2.0.0),
`scripts/l22_evidence/verdict.py` (`EVALUATOR_SCHEMA_VERSION` bumped 3 → 4),
vendored Karr `.m` source under `data/karr_vendored_source/`, the 5
regenerated H12 evidence artifacts, the `h12_evidence_index.json`
side-index, and new/updated tests. See
`docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md` §13.16 for the
technical schema writeup this report summarizes.

## Task

Five catalog rows (`MacromolecularComplexation`, `ProteinFolding`,
`ProteinProcessingI`, `ProteinProcessingII`, `tRNAAminoacylation`) carry a
hand-set `closed_form_dominant=confirmed_biology_validated` flag with no
machine-checked producer. The evidence gate correctly demotes their
`PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` warning to non-green without
one. This task's job: produce that producer honestly, or report failure —
and, this round, to repair specific defects an independent review found
in the first attempt.

## What was wrong with v1 (why this repair exists)

1. **MacromolecularComplexation's `compare_predictions` was full-width,
   not scoped per unit.** Two networks active in the same tick both write
   into the shared `substrates`/`complexs` arrays; a unit's `predicted_delta`
   was zero-padded outside its own network's indices, but the *actual*
   delta at another unit's indices is real, nonzero activity from the
   OTHER network. A full-width compare treated this as a mismatch. This
   was masked in v1 because the buggy compare happened to still read as
   "814/814 100%" — the 814 "matches" were an artifact of how mismatches
   were being (mis)classified, not evidence the fix was already correct.
   Fixed by adding `UnitPrediction.index_mask` and scoping every diff to
   the unit's own claimed indices (`h12.py::compare_predictions`).
2. **ProteinFolding's chaperone/enzyme guard was omitted entirely.** v1's
   docstring asserted chaperones are "unconditionally non-limiting" without
   deriving that from source. The real MATLAB (`ProteinFolding.m` line
   ~535) computes `species = max(0, [substrates; enzymes*Inf; ...]')`: a
   chaperone at **exactly zero count** gives `0*Inf == NaN`, and MATLAB's
   `max(0, NaN)` returns `0` (not `Inf`/non-limiting) — a **per-species**
   exclusion from folding that tick, not a whole-tick guard failure. v1's
   predictor could not have distinguished a present-chaperone tick from a
   provably-impossible zero-chaperone tick because it never modeled the
   chaperone axis at all. Fixed by loading `proteinChaperoneMatrix` and
   gating `eligible_flux` per species (`h12.py::predict_protein_folding`);
   covered by two new synthetic zero-chaperone unit tests
   (`test_h12_formulas.py`) since real oracle data essentially never hits
   count-zero chaperones.
3. **No structural distinction between "confirmed on every regime the
   process can exhibit" and "confirmed on every regime observed in this
   dataset".** For MacromolecularComplexation, network-size-≥2 with a
   genuinely-nonzero sampling bound is Monte-Carlo by construction — no
   closed-form prediction is or can be claimed there, at any N/M. For
   ProteinProcessingII, the diacylglyceryl-transferase branch never fires
   in the real Karr population (all real lipoprotein monomers observed
   take the passthrough/signal-peptidase path). v1 had no mechanism to
   flag "some of this process's own defined branches were never even
   exercised, let alone confirmed" — so a 100%-match artifact for either
   process looked indistinguishable from one where every branch had been
   genuinely exercised. Fixed by adding a `REQUIRED_BRANCHES` registry, a
   `branch_tags`/`branches_confirmed`/`branches_observed` machinery in
   every predictor and `compare_predictions`, and a new **non-gating**
   `H12_OBSERVED_REGIME` verdict: 100% exact match, zero tolerance, but
   missing required branch coverage. `validate_h12_support()` accepts only
   `H12_CONFIRMED`, never `H12_OBSERVED_REGIME`.
4. **Freshness hashing was raw-byte, not LF-normalized, and
   `predictor_source_path` was not pinned to a specific expected module.**
   A byte-identical predictor re-saved with different line endings (e.g.
   Windows checkout) would spuriously read as stale; a wrong or dangling
   path was previously soft-trusted as an attestation string with no
   requirement it equal the real module. Fixed: `_sha256_lf_normalized()`
   for the predictor module and vendored Karr source (raw-byte
   `_sha256_file()` retained only for the binary fixture `.mat` files);
   `EXPECTED_PREDICTOR_SOURCE_PATH = "scripts/l22_evidence/h12.py"` is now
   hard-pinned and hard-fails on any deviation.
5. **The Karr `.m` source was never actually vendored/tracked** — v1's
   artifacts referenced absolute local paths under
   `data/m1_sources/WholeCell/...`, which do not exist in a fresh clone and
   whose hashes were therefore unverifiable outside the author's machine.
   Fixed by vendoring the 5 relevant `.m` files (plus the upstream MIT
   license) under the tracked `data/karr_vendored_source/` directory, with
   `karr_source_citation()` hard-failing (no soft-trust) if the vendored
   file is missing, and `validate_h12_support()` re-verifying its
   LF-normalized hash against the artifact's recorded value.
6. **`ANY` trivial mismatch was not distinguished from a nontrivial one.**
   v1 tracked only a single mismatch-count/rate over nontrivial samples;
   a predictor that wrongly claimed "nothing happens" on a trivial sample
   (a harder failure mode — the guard logic itself is wrong) was not
   specially flagged. Fixed: `trivial_checked_count`/
   `trivial_mismatch_count` are now tracked separately and ANY nonzero
   `trivial_mismatch_count` is an unconditional `H12_FAIL`, regardless of
   the nontrivial match rate.

## Method summary (anti-laundering, unchanged in spirit from v1)

For each process, the closed-form prediction is transcribed directly from
the Karr MATLAB source (now vendored at `data/karr_vendored_source/*.m`,
upstream `CovertLab/WholeCell` commit `6cdee6b355aa0f5ff2953b1ab356eea049108e07`,
MIT license) plus static fixture parameters
(`data/karr_fixtures/per_process/*_flat.mat`) plus `states_before` only —
never from the OC vivarium port, the runner, `states_after`, or any
`result.json`/oracle output. Predictions are frozen in memory (and in the
artifact's `raw_prediction_hash`) before `after` is touched at all; a
separate `compare_predictions()` function is the sole reader of
`states_after`, invoked only in a distinct comparison phase. This is
enforced by a static AST guard (`tests/scripts/test_h12_anticheat.py`, 15
tests) over every predictor function's source — not just a convention.

## Results — 3 `H12_CONFIRMED`, 2 `H12_OBSERVED_REGIME` (non-gating)

Run against real oracle `.mat` trace data at each process's actual catalog
`N_seeds`/`M_ticks`, in the task's mandated highest-risk-first order:

| Process | seeds × ticks | total samples | nontrivial | exact matches | match rate | trivial mismatches | required branches confirmed | verdict |
|---|---|---|---|---|---|---|---|---|
| tRNAAminoacylation | 50 × 50 | 2500 | 2500 | 2500 | 100% | 0 | 1/1 | **H12_CONFIRMED** |
| ProteinProcessingII | 50 × 20 | 1000 | 560 | 560 | 100% | 0 | 2/3 (missing `transferase_fires`) | **H12_OBSERVED_REGIME** |
| ProteinFolding | 50 × 100 | 5000 | 2639 | 2639 | 100% | 0 | 2/2 | **H12_CONFIRMED** |
| MacromolecularComplexation | 50 × 100 | 10000 | 814 | 814 | 100% | 0 | 1/2 (missing `network_ge2_fires`) | **H12_OBSERVED_REGIME** |
| ProteinProcessingI | 50 × 20 | 1000 | 635 | 635 | 100% | 0 | 2/2 | **H12_CONFIRMED** |

Every process achieves a genuine 100% exact-match rate on every nontrivial
sample it produced, with zero trivial mismatches — the predictor logic
itself is not shown wrong anywhere. The 2 `H12_OBSERVED_REGIME` verdicts
reflect a **structural** limitation, not a correctness gap:

- **MacromolecularComplexation**: network-size-≥2 complexes only ever land
  in the `regime_valid=True` (all-bounds-zero, trivially deterministic)
  case in the real 50-seed dataset — the genuinely-competitive,
  Monte-Carlo-excluded case (`regime_valid=False`) is, by construction,
  mutually exclusive with ever appearing in `branches_confirmed`. No
  amount of additional real oracle sampling can change this: it is a
  property of the closed-form argument itself (a nonzero sampling bound
  under network≥2 competition is never closed-form), not of the sample.
- **ProteinProcessingII**: the diacylglyceryl-transferase branch never
  fires across all 50 seeds × 20 ticks — every observed lipoprotein
  monomer takes the passthrough/signal-peptidase path in this population.
  Unlike MacromolecularComplexation's case, this IS potentially a sampling
  artifact (a different/larger population could in principle exercise the
  transferase path) rather than a structural impossibility, but no such
  data currently exists, so it remains honestly unconfirmed.

Per the mandate, `H12_OBSERVED_REGIME` **never clears the evidence gate**
(`h12.validate_h12_support` and `verdict.h12_support_reason` both hard-
require `verdict == "H12_CONFIRMED"`); see
`tests/scripts/test_l22_evidence_verdict.py::test_process_h12_observed_regime_never_clears_gate`.

"Nontrivial" samples are those where the closed-form regime's guard
conditions hold (i.e., where the catalog's determinism claim actually
applies at that tick/seed); "trivial" samples (guard fails, e.g. no
substrate available, or every eligible species is chaperone-blocked) are
still predicted and still compared — they simply fall outside the regime
the catalog claims is closed-form, but a wrong trivial prediction is
tracked separately and is an unconditional hard fail. No tolerance was
applied anywhere — even a single mismatch out of hundreds is a hard
`H12_FAIL` (verified:
`test_h12_artifact.py::test_compare_predictions_single_mismatch_out_of_100_fails_no_tolerance`).
None of the 5 processes' MATLAB source defines a pre-registered
integer/float tolerance, so none was assumed.

## Evidence-index tally (mechanically derived, not hardcoded)

Regenerating `docs/phase_f/l2_2_design_a/evidence_index.json` from the
unchanged tracked `evidence_bundle` + the current catalog + the 5 fresh
H12 artifacts (`bin\oc-py scripts/l22_evidence/generator.py generate`)
yields, across all 22 in-scope catalog rows:

```
PASS:             14
FAIL:              4
MISSING_EVIDENCE:  4
```

The 3 newly-`H12_CONFIRMED` rows (`tRNAAminoacylation`, `ProteinFolding`,
`ProteinProcessingI`) are now `PASS`/green; the 2
`H12_OBSERVED_REGIME` rows (`MacromolecularComplexation`,
`ProteinProcessingII`) correctly remain `FAIL`/non-green. The other 2
FAIL rows (`Replication`, `DNASupercoiling`) are pre-existing, unrelated
evaluator-guard findings untouched by this task (see
`tests/scripts/test_l22_evidence_generator.py`); `ProteinDecay` is not a
FAIL row at all -- it is, and remains, `PASS`/green, uninvolved in H12
entirely (it carries no `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE`
sentinel and was never one of the 5 target processes). `bin\oc-py
scripts/l22_evidence/generator.py audit` confirms `integrity: OK`.

## Catalog demotion recommendation

- **tRNAAminoacylation, ProteinFolding, ProteinProcessingI**: no
  `closed_form_dominant` demotion warranted — genuine, machine-checked
  H12_CONFIRMED evidence now backs the existing catalog flag.
- **ProteinProcessingII**: **demotion recommended for reviewer/maintainer
  consideration.** The transferase branch has never been observed to fire
  in any available real oracle data; the catalog's
  `confirmed_biology_validated` claim implicitly covers a branch that has
  zero empirical support. This is a non-binding observation only — no
  catalog file was edited in this work, per the task's explicit
  instruction that any demotion decision is left to the reviewer/
  maintainer.
- **MacromolecularComplexation**: **demotion recommended for reviewer/
  maintainer consideration**, for a different (structural, not sampling)
  reason: network-size-≥2 complexes can never be H12_CONFIRMED under ANY
  amount of additional real-population sampling, because a nonzero
  competitive sampling bound is Monte-Carlo by mathematical construction,
  not a rare event a bigger dataset would eventually catch. The catalog's
  `confirmed_biology_validated` flag, if intended to cover network≥2, is
  claiming determinism for a regime that is provably never deterministic.

## Methodology caveats

1. **ProteinFolding's zero-chaperone/prosthetic-scarcity guard is now
   source-faithful, but exercised only synthetically.** Real oracle data
   essentially never has a chaperone at exactly zero count (they are
   constitutively-expressed enzymes), so the corrected per-species
   exclusion logic is exercised by 2 new hand-constructed unit tests
   (`test_h12_formulas.py::test_protein_folding_zero_count_chaperone_blocks_only_the_dependent_species`,
   `::test_protein_folding_all_chaperones_zero_yields_trivial_no_op_not_a_guard_failure`)
   rather than by real-data branch coverage. This is intentional — the
   mandate explicitly notes "scarcity perturbation remains recommended"
   as a future improvement, not a blocker for the current CONFIRMED
   verdict, since the full N/M real-data run does independently achieve
   100% branch coverage on both `monomer_folding_fires` and
   `complex_folding_fires`.
2. **Pre-existing, unrelated bug (not introduced, not fixed):**
   `tRNAAminoacylation`'s row independently has a `primary_channel`
   casing mismatch (`rnas` vs. `RNAs`) noted by the prior v1 report;
   this is now resolved as a non-issue for this row's H12 support (the
   row is green in the current tally above), but any residual channel-
   naming inconsistency elsewhere in the catalog remains out of this
   task's scope (catalog edit).
3. **No OC sweep was re-run.** All 5 artifacts and the evidence-index
   regeneration above used only the existing, tracked `evidence_bundle`
   and real oracle `.mat` trace files already present on disk — no
   process/runner/biology/threshold code was executed or modified, per
   the "no process sweep" / "no expensive OC sweeps" instructions.

## What was NOT done (explicitly out of scope)

- No `PROCESS_CATALOG.yaml`, runner, biology, or threshold edits (the two
  demotion recommendations above are reviewer/maintainer decisions only).
- No OC sweep re-run.
- No `git push` (worktree-local commits only, per task instruction).

## Verification performed

- All 5 processes re-run against real oracle data end-to-end at full
  catalog N/M — see the 5 tracked JSON artifacts and the tally table
  above.
- `tests/scripts/test_h12_anticheat.py` (15), `test_h12_formulas.py` (17,
  13 original + 4 new: 2 ProteinFolding zero-chaperone synthetic tests
  updated fixtures, 2 net-new), `test_h12_artifact.py` (9, 4 new: index-
  mask scoping regression test, branch-coverage-gated verdict tests),
  `test_h12_evidence_wiring.py` (11, rewritten to use real on-disk hashes)
  — all passing.
- `tests/scripts/test_l22_evidence_verdict.py` (rewritten H12 section:
  16 tests using real process hashes/branch registries instead of fake
  tmp-path files, including new trivial-mismatch/branch-coverage/
  observed-regime/wrong-pinned-path/missing-fixture cases) — all passing.
- `tests/scripts/test_l22_evidence_anticheat.py` (56, including 1 fixed
  H12 fixture using the new real-hash payload shape) — all passing (full
  run takes ~16 minutes due to heavy per-test real-repo hashing;
  confirmed genuinely progressing, not hung).
- `bin\oc-py scripts/l22_evidence/generator.py generate` + `audit`:
  22-row index regenerated fresh, `integrity: OK`,
  `PASS: 14 / FAIL: 4 / MISSING_EVIDENCE: 4`.
- AST sanity (`ast.parse`) on both `h12.py` and `verdict.py` after all
  edits.

## Addendum: MacromolecularComplexation network_ge2_fires closure evidence

A follow-on task (worktree
`E:\opencell-worktrees\l22-macromol-network2-evidence-v2`, branch
`agent/l22-macromol-network2-evidence-v2`) closed out the
"demotion recommended for reviewer/maintainer consideration" note above
for `MacromolecularComplexation` with a committed, machine-checkable,
**non-gating** evidence package (no catalog/verdict/gate change on that
branch either):

- `docs/phase_f/l2_2_design_a/h12/
  MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md` — investigates
  why `MG_429_MONOMER` (PTS system E1), network 2's limiting substrate, is
  fixture-constant zero across all 5000 accepted natural (seed, tick)
  samples, and whether `ub>0` is structurally reachable without changing
  stoichiometry/constants.
- `docs/phase_f/l2_2_design_a/h12/condition_gated/
  MacromolecularComplexation_h12_condition_gated.json` (generator:
  `scripts/l22_evidence/h12_condition_gated.py`, tests:
  `tests/scripts/test_h12_condition_gated.py`) — mechanically binds this
  report's accepted `H12_OBSERVED_REGIME` artifact, an independently
  re-derived natural-population census (same hash-identical 50-seed
  population; `ub==[0,0]` on all 5000 samples), and the existing accepted
  `H12_PERTURBATION_OBSERVED_STOCHASTIC` artifact (network 2 fires for
  real once only E1 is conditioned), proposing classification
  `CONDITION_GATED_CANDIDATE`.
- `docs/phase_f/l2_2_design_a/h12/CONDITION_GATED_TAXONOMY_PROPOSAL.md` —
  a narrowly-scoped proposal for a future `H12_CONDITION_GATED` verdict
  value, explicitly not enacted by that branch.

The condition-gated artifact's `classification` field is pinned to the
literal `CONDITION_GATED_CANDIDATE` string (never an enacted
`CONDITION_GATED` value), its `lifecycle_reachability_status` field is
pinned to the literal `UNRESOLVED` string (whether E1 could ever become
nonzero at a later lifecycle stage is recorded as genuinely unknown, not
resolved false), and its `unblocks_current_row`/`unblocks_l2_5`/
`maintainer_decision_made` fields are all pinned `false` — this candidate
does not, by itself, change this report's verdict or unblock the row.

This report's own verdict, tally, and demotion recommendation above are
UNCHANGED by this addendum; the addendum only records where the
follow-on evidence lives for a future reviewer decision.
