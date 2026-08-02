# ProteinProcessingII H12 Scenario B (scarcity matrix) -- terminal-status proposal

**Status: PROPOSAL / NOT ENACTED.** This document recommends a course of action
for the central H12 verdict taxonomy. It does not itself change any verdict,
catalog entry, or evidence-index row. As of this commit:

- `scripts/l22_evidence/h12.py` (predictor, `decide_verdict`, lines ~1130-1162)
  is unmodified. The only two verdict strings it can emit remain
  `H12_CONFIRMED` and `H12_OBSERVED_REGIME`.
- `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_h12.json` is unmodified.
  Its stored `verdict` remains `H12_OBSERVED_REGIME` with
  `missing_required_branches: ["transferase_fires"]`.
- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` and
  `scripts/l22_evidence/verdict.py` (central evidence-index aggregation) are
  unmodified.
- `docs/phase_f/l2_2_design_a/h12/perturbation/ProteinProcessingII_h12_perturbation.json`
  (Scenario A) remains `NON_GATING` and unchanged.

Any change to the four items above requires a separate, serialized commit,
explicitly authorized by GPT-5.6 Sol after Opus 5 review of this proposal and
of the Scenario B code/spec landed in this same commit.

## 1. Why the natural regime alone cannot close H12 for this process

`ProteinProcessingII.evolveState` (Karr MATLAB,
`data/karr_vendored_source/ProteinProcessingII.m:348-446`) has three mutually
exclusive branches selected by `unprocessedMonomers`/enzyme-capacity/water/
PG160 availability at entry:

1. `passthrough_fires` -- nothing to process this tick.
2. `peptidase_fires` -- peptidase capacity is the binding constraint; lipoprotein
   signal peptide cleavage proceeds via `mnrnd`-style Monte Carlo allocation
   bounded by peptidase count.
3. `transferase_fires` -- transferase capacity (or water, or PG160) is the
   binding constraint on lipoprotein anchoring; this is the dormant branch.

Under the 50-seed x 20-tick standard Karr trace used to produce
`ProteinProcessingII_h12.json`, `transferase_fires` is never observed: 0/1000
(seed, tick, unit) samples have `transferase_demand > 0` triggering that guard
path. `branches_confirmed = ["passthrough_fires", "peptidase_fires"]`,
`missing_required_branches = ["transferase_fires"]`. This is a fact about the
biological operating point of the standard Karr trace, not a predictor defect:
under normal cellular resource abundance, transferase/PG160/water never bind.
No amount of additional *standard* seeds/ticks changes this, because the
regime is deterministic given initial abundance, not seed-sensitive at the
branch-selection level.

## 2. What Scenario B adds (code/spec, this commit; no execution yet)

Scenario B is a pre-registered, source-faithful **conditioned pre-state
matrix**: 5 distinct initial states, each derived algebraically from Karr
fixture quantities and Karr formulas (never from a desired/fitted outcome),
each constructed so that a specific scarcity guard (or, in one case, two
simultaneously) binds and the dormant `transferase_fires` branch actually
executes in real Octave, drawing real `mnrnd`/`stochasticRound` randomness.

States (full derivations, guard-failure labels, and hand-traced mechanics are
recorded in `PERTURBATION_SPEC.json ->
scenarios.protein_processing_ii_scenario_b_scarcity_matrix.states`):

| state | binding guard(s) | source-valid derivation basis |
|---|---|---|
| `peptidase_capacity_scarce` | peptidase count | fixture `enzymes.copyNumber` reduced to Karr-formula-derived minimum below demand |
| `water_scarce` | water pool | fixture stoichiometry-derived minimum water below hydrolysis demand |
| `transferase_capacity_scarce` | transferase count | fixture `enzymes.copyNumber` reduced below anchoring demand |
| `pg160_scarce` | PG160 substrate pool | fixture pool reduced below per-unit consumption requirement |
| `simultaneous_transferase_and_pg160_scarce` | transferase count AND PG160 pool | both of the above jointly, to test the guard's dual-cause label path |

Every numeric value in each state is either taken directly from the Karr
fixture (`ProteinProcessingII_flat.mat`) or computed from a documented Karr
formula (e.g. `demand - 1` at the exact integer boundary the guard checks),
never chosen to force a particular downstream outcome distribution. This
matches the existing Scenario A convention of deriving constants from Karr
data only.

## 3. Evidence contract (unchanged from Turn 2a decisions, restated for the record)

- **Exact, zero-tolerance claims** (verified per-seed, per-state, from raw
  Octave CSV output): mass conservation, non-negativity, per-species
  allocation cap, and pool cap (peptidase/transferase/water/PG160, as
  applicable to that state's binding guard). These are integer-valued counts
  in float64 and are checked with exact equality/inequality, matching
  `h12.compare_predictions`'s existing no-epsilon convention.
- **Distributional-only claim**: the specific per-species stochastic
  allocation (`mnrnd` output) must show real cross-seed variation -- i.e.
  `mnrnd` cannot be a structural no-op in the constructed regime, unlike
  Scenario A's provably-RNG-invariant construction. This is checked as
  "variation observed" (at least 2 distinct raw allocation vectors across the
  seed set for a state), not against any specific numeric target.
- No epsilon/statistical-distance threshold is invented for the exact bounds;
  they are checked at machine-exact equality because the quantities are
  integers. No null/statistical model is required for the distributional
  claim because "at least 2 distinct realizations across N>=5 independent
  seeds" is a existence check, not a distribution-shape claim.

## 4. Independent predictor / anti-laundering boundary

`guard_diagnostics_ppii()` and `predict_ppii_scarcity_bounds()`
(`scripts/l22_evidence/h12_perturbation.py`) are new, freeze-before-execution
predictor code, independent of (but cross-checked once, in this session, via
disposable scratch scripts now deleted, against) `h12.predict_protein_processing_ii`.
They:

- read only `states_before` + static fixture/spec constants;
- never import the OC SUT or read `states_after`/runner/oracle output during
  prediction;
- `ingest_ppii_scenario_b()` is the only function that reads Octave CSV
  output, and it runs strictly after prediction is frozen (COMPARE phase),
  exactly mirroring the existing Scenario A PREDICT/COMPARE separation.

## 5. Exact files this commit touches (code/spec/tests/docs only)

Modified:
- `docs/phase_f/l2_2_design_a/h12/perturbation/PERTURBATION_SPEC.json`
- `scripts/l22_evidence/h12_perturbation.py`
- `scripts/octave_h12_perturbation/README.md`
- `tests/scripts/test_h12_perturbation.py`

Created:
- `scripts/octave_h12_perturbation/run_ppii_scenario_b.m`
- this file.

Explicitly NOT touched (deferred to a future, separately authorized commit):
- `scripts/l22_evidence/h12.py`
- `scripts/l22_evidence/verdict.py`
- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`
- `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_h12.json`
- `docs/phase_f/l2_2_design_a/h12/perturbation/ProteinProcessingII_h12_perturbation.json`
- `docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json`

## 6. Canary / full run plan (NOT executed this commit)

1. **Canary**: 1 state (`transferase_capacity_scarce`, the simplest
   single-cause state) x 5 seeds. Expected runtime: seconds (single Octave
   process, 5 short evolveState calls). Purpose: confirm the harness invokes
   the real dormant branch at all (nonzero `transferase_fires` count) and that
   raw CSV schema matches `ingest_ppii_scenario_b`'s expectations, before
   spending time on the full matrix.
2. **Full**: all 5 states x 50 seeds each (250 total draws). Expected runtime:
   low tens of seconds to a few minutes depending on Octave startup overhead
   per invocation; each state's evolveState call is O(tens of species), no
   heavy linear algebra.

Both are gated behind explicit CLI subcommands
(`run-octave-scenario-b-canary` / `run-octave-scenario-b-full` in
`h12_perturbation.py`) and behind `PERTURBATION_SPEC.json
scenario_b_execution_status: "NOT_YET_EXECUTED"`. Neither has been invoked in
this session.

## 7. Predicted verification outcomes

- Canary: expect `transferase_fires`-branch activation in all 5 seeds (guard
  is constructed to bind unconditionally on demand > 0, independent of RNG),
  with cross-seed variation in *which* lipoprotein units are anchored this
  tick (the stochastic allocation), while aggregate bounds (mass conservation,
  per-species cap, pool cap) hold exactly in all 5.
- Full matrix: expect all 4 single-cause states to show >=2 distinct
  allocation realizations across 50 seeds with 0 bound violations; the
  simultaneous-binding state additionally exercises the guard's dual-cause
  label without a contradiction (both causes present, no bound violated).
- If any state instead shows a structural `mnrnd` no-op (e.g. because
  `demand` rounds to a value the guard's capacity exactly matches, making
  every seed identical), the terminal outcome would be `NO_VARIATION` for
  that state, not `OBSERVED_STOCHASTIC` -- this is a real possible outcome the
  code is built to detect and report honestly, not to hide.

## 8. Recommended terminal status if Scenario B executes cleanly

**Recommendation (not enacted by this commit):** if the canary and full run
both produce `OBSERVED_STOCHASTIC` verdicts with 0 invariant violations across
all 5 states, the honest terminal status for ProteinProcessingII is a new
**`H12_CONDITION_GATED`** taxonomy value (distinct from both `H12_CONFIRMED`
and `H12_OBSERVED_REGIME`), meaning: *the dormant branch has been
independently confirmed to execute correctly and exactly under a real,
source-faithful, off-nominal condition, but the process's real branch coverage
under its own standard/natural Karr trace remains incomplete.*
`H12_CONDITION_GATED` would NOT be equivalent to `H12_CONFIRMED` for the
purpose of any sentinel currently gated on `H12_CONFIRMED`
(`scripts/l22_evidence/h12.py:1358-1359` -- `verify_process_specific_h12` only
accepts literal `"H12_CONFIRMED"`); it would be a new, explicitly
lower-trust bucket requiring its own review before any future gate change
considers accepting it.

If Scenario B instead cannot be made to fire the branch source-faithfully (all
inversion tests below pass but the real branch stays dormant even under
genuine scarcity), the correct terminal status remains `H12_OBSERVED_REGIME`
unchanged, and this proposal would be withdrawn rather than forced through.

## 9. Inversion tests this design must survive (implemented as unit tests in `tests/scripts/test_h12_perturbation.py`)

- Branch remains inactive under a state that was supposed to trigger it ->
  caught by the `regime_valid`/guard-failure-label spec-consistency test
  (parametrized over all 5 states).
- Only one conditioned state used instead of the matrix -> the spec/CLI
  requires iterating `PPII_SCENARIO_B_STATE_NAMES`; `ingest_ppii_scenario_b`
  returns a dict keyed by all 5 names, tested directly.
- Global RNG mutation between states -> `run_ppii_scenario_b.m` seeds
  per-draw explicitly (documented in the driver and README); no global
  `rand("seed", ...)` call outside the per-draw loop.
- Reused seeds across states -> seed schedule is pre-registered in
  `PERTURBATION_SPEC.json` per state, not derived from a shared counter.
- Predictor reads `states_after`/SUT -> `guard_diagnostics_ppii`/
  `predict_ppii_scarcity_bounds` take only `states_before`-shaped inputs;
  `ingest_ppii_scenario_b` is a separate, later-called function, and no
  import of the OC SUT exists anywhere in this module.
- Scarcity never binds -> `evaluate_ppii_scarcity_invariants`'s no-variation
  and mass-conservation-violation synthetic tests exist specifically to prove
  the harness would report `NO_VARIATION`/`INVARIANT_VIOLATION` rather than a
  false `OBSERVED_STOCHASTIC`, if this were to happen.
- `mnrnd` replaced by deterministic allocation -> the no-variation synthetic
  test directly simulates this failure mode (identical allocation vector
  across seeds) and asserts the verdict is `NO_VARIATION`, not
  `OBSERVED_STOCHASTIC`.
- Stale standard traces mislabeled as a new condition -> Scenario B never
  reads the existing 50-seed standard traces; it generates its own inputs
  from `PPII_SCENARIO_B_STATES` via `_write_ppii_scenario_b_octave_states`,
  independently of any prior extraction.
- Stored verdict trusted -> this proposal explicitly does not read or rely on
  the stored `ProteinProcessingII_h12.json` verdict for its own pass/fail
  logic; it is a self-contained, from-raw-CSV recomputation.

## 10. Non-goals (restated)

No production biology/threshold/catalog relaxation is proposed or enacted.
No repeat standard-trace extraction occurs or is proposed. No PASS/CONFIRMED
claim is made from Python-only perturbation (Scenario B requires real Octave
execution with real `mnrnd`, not yet performed). This document proposes a
distinct, new, explicitly-lower-trust taxonomy value gated by a review it
does not itself grant.
