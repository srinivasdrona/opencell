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
executes in real MATLAB, drawing real `mnrnd`/`stochasticRound` randomness
from Karr's own `edu.stanford.covert.util.RandStream` class (see §2a below --
**not** Octave, per Opus5 turn-3 correction 1).

States (full derivations, guard-failure labels, and hand-traced mechanics are
recorded in `PERTURBATION_SPEC.json ->
scenarios.protein_processing_ii_scenario_b_scarcity_matrix.states`):

| state | binding guard(s) | margin vs. limit | source-valid derivation basis |
|---|---|---|---|
| `transferase_capacity_scarce` (**DESIGNATED CANARY**) | transferase count only | `enzymes_diacylglycerylTransferase` reduced to 152.0, below the lipoprotein-anchoring demand computed from a nonzero `lipoprotein_first3` allocation; `transferase_demand > 0` in every one of its 50 pre-registered seeds | fixture `enzymes.copyNumber` reduced below the Karr-formula transferase-capacity limit |
| `pg160_scarce` | PG160 substrate pool only | `substrates_PG160` reduced to 3.0, below the transferase-branch's per-unit PG160 consumption requirement | fixture pool reduced below per-unit consumption requirement |
| `peptidase_capacity_scarce` | peptidase count only | `enzymes_signalPeptidase` reduced to 1.0, below the secreted-cleavage demand | fixture `enzymes.copyNumber` reduced below the Karr-formula peptidase-capacity limit |
| `water_scarce` | water pool only | `substrates_water` reduced to 30.0, below the hydrolysis demand from the secreted pathway (this state has `transferase_demand == 0` -- it exercises only the peptidase/water side of the guard, which is WHY it cannot serve as canary evidence for the transferase branch, per Opus5 turn-3 correction 3) | fixture stoichiometry-derived minimum water below hydrolysis demand |
| `simultaneous_peptidase_capacity_and_water_scarce` | peptidase count AND water pool | `enzymes_signalPeptidase` reduced to 2.0 AND `substrates_water` reduced to 10.0, jointly below demand | both of the above jointly, to test the guard's dual-cause label path |

Every numeric value in each state is either taken directly from the Karr
fixture (`ProteinProcessingII_flat.mat`) or computed from a documented Karr
formula (e.g. capacity set strictly below the exact demand the guard checks),
never chosen to force a particular downstream outcome distribution. This
matches the existing Scenario A convention of deriving constants from Karr
data only.

### 2a. Genuine-MATLAB execution engine (replaces the rejected Octave-stub design)

Opus5 rejected Turn 2a's design because its `run_ppii_scenario_b.m` Octave
driver drew its stochastic samples from this repo's own
`mnrndStub.m`/`stochasticRoundStub.m` scaffolding (used elsewhere for
Octave-only structural evidence), which is **not** Karr's real stochastic
implementation and cannot serve as evidence of genuine `mnrnd`/
`stochasticRound` behavior. Turn 3 replaces this entirely:

- `scripts/matlab_h12_perturbation/run_ppii_scenario_b_matlab.m` is a genuine
  local **MATLAB** driver (not Octave). It requires the Statistics Toolbox
  and constructs a real `edu.stanford.covert.util.RandStream('mcg16807',
  'Seed', k)` instance per seed -- the identical class WholeCell/Karr itself
  uses. If MATLAB, the Statistics Toolbox, or `RandStream` construction is
  unavailable, the driver **aborts with no fallback**; it never silently
  substitutes a stub.
- `data/karr_vendored_source/RandStream.m` is a byte-identical vendored copy
  of the real Karr `RandStream` class (hash-pinned; see that directory's
  README for provenance/hashes), vendored for audit even though the future
  driver loads the canonical WholeCell package path (`edu.stanford.covert.
  util.RandStream`) at runtime.
- `scripts/matlab_h12_perturbation/evolveState_ppii_matlab.m` is a true
  verbatim (zero-substitution) transcription of `ProteinProcessingII.m`
  evolveState lines 349-445 -- disclosed here as **transcribed**, not
  vendored byte-for-byte, because MATLAB `.m` files cannot `import` a method
  body from another class file the way the RandStream *class* can be
  referenced; its fidelity is instead verified by
  `tests/scripts/test_h12_perturbation_source_binding.py::
  test_matlab_harness_matches_vendored_source_exactly` (a normalized
  line-by-line diff against the vendored Karr source).
- This tier is explicitly isolated, source-faithful, MATLAB-only stochastic-
  branch evidence -- it remains `NON_GATING`/conditioned, and it is **not**
  `H12_CONFIRMED`. See §8 for the honest scope of what it can and cannot
  close.

## 3. Evidence contract (corrected per Opus5 turn-3 review)

- **Exact, zero-tolerance claims** (verified per-seed, per-state, from raw
  MATLAB CSV output, via `evaluate_ppii_scarcity_invariants`):
  - `mass_conservation`: `unprocessed_after.sum() + processed_after.sum() ==
    unprocessed_before.sum()`, exactly. There is **no third "passthrough
    pool" term** in this invariant -- `signalSequenceMonomers` is a
    side-channel bookkeeping array (which units received a signal sequence),
    not a third mass pool, and is never summed into the conservation check.
  - `non_negativity`: every after-state array entry (unprocessed, processed,
    signal, substrates) is `>= 0`.
  - `per_species_cap`: no species' `processed_after` may exceed its own
    `unprocessed_before` count.
  - `pool_cap_peptidase` / `pool_cap_transferase`: the aggregate peptidase-
    processed count may never exceed `water_before`, and the aggregate
    transferase-processed count may never exceed `pg160_before` (the two
    metabolite pools the guard formula itself checks).
  These are integer-valued counts in float64 and are checked with exact
  equality/inequality, matching `h12.compare_predictions`'s existing
  no-epsilon convention.
- **Distributional-only claim**: the specific per-species stochastic
  allocation (`mnrnd`/`stochasticRound` output) must show real cross-seed
  variation -- i.e. it cannot be a structural no-op in the constructed
  regime, unlike Scenario A's provably-RNG-invariant construction. This is
  checked as "variation observed" (at least 2 distinct raw allocation
  vectors across the seed set for a state), not against any specific numeric
  target.
- No epsilon/statistical-distance threshold is invented for the exact
  bounds; they are checked at machine-exact equality because the quantities
  are integers. No null/statistical model is required for the distributional
  claim because "at least 2 distinct realizations across N independent
  seeds" is an existence check, not a distribution-shape claim.

## 4. Independent predictor / anti-laundering boundary

`guard_diagnostics_ppii()` and `predict_ppii_scarcity_bounds()`
(`scripts/l22_evidence/h12_perturbation.py`) are freeze-before-execution
predictor code, independent of but cross-checked against
`h12.predict_protein_processing_ii` by a committed, parametrized boundary-
grid test
(`tests/scripts/test_h12_perturbation.py::
test_guard_diagnostics_ppii_boundary_grid_matches_accepted_h12_predictor`),
which exercises each of the four guards independently at its exact numeric
boundary plus one simultaneous-failure combination. They:

- read only `states_before` + static fixture/spec constants;
- never import the OC SUT or read `states_after`/runner/oracle output during
  prediction;
- `freeze_ppii_scenario_b_predictions()` persists this frozen prediction to
  disk, hash-bound to the exact state file it was derived from, strictly
  BEFORE any MATLAB process is invoked;
- `ingest_ppii_scenario_b()` is the only function that reads MATLAB CSV
  output; it **loads** the frozen prediction JSON and never recomputes it,
  and it independently validates the MATLAB run-manifest (mode, exact seed
  list, three-way state-file hash, harness hash, and an explicit
  `randstream_class_confirmed` flag) before trusting any CSV row.

## 5. Exact files this commit touches (code/spec/tests/docs only)

Created:
- `data/karr_vendored_source/RandStream.m`
- `scripts/matlab_h12_perturbation/evolveState_ppii_matlab.m`
- `scripts/matlab_h12_perturbation/run_ppii_scenario_b_matlab.m`
- `scripts/matlab_h12_perturbation/probe_matlab_environment.m`
- `scripts/matlab_h12_perturbation/README.md`
- this file (rewritten from its Turn 2a version).

Modified:
- `data/karr_vendored_source/README.md`
- `docs/phase_f/l2_2_design_a/h12/perturbation/PERTURBATION_SPEC.json`
- `scripts/l22_evidence/h12_perturbation.py`
- `scripts/octave_h12_perturbation/README.md`
- `tests/scripts/test_h12_perturbation.py`
- `tests/scripts/test_h12_perturbation_source_binding.py`

Deleted (superseded, per Opus5 turn-3 correction 1 -- no stub-based Scenario
B evidence is retained):
- `scripts/octave_h12_perturbation/run_ppii_scenario_b.m`

Explicitly NOT touched (deferred to a future, separately authorized commit):
- `scripts/l22_evidence/h12.py`
- `scripts/l22_evidence/verdict.py`
- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`
- `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_h12.json`
- `docs/phase_f/l2_2_design_a/h12/perturbation/ProteinProcessingII_h12_perturbation.json`
- `docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json`

## 6. Canary / full run plan (NOT executed this commit)

1. **Canary**: 1 state (`transferase_capacity_scarce`) x its own block's
   first 5 seeds (1000-1004, an explicit prefix/subset of that state's own
   50-seed block, never a separate seed range). Expected runtime: tens of
   seconds to low minutes (genuine MATLAB startup/license-checkout overhead
   is real, unlike Octave's near-instant startup; 5 short evolveState
   calls). Purpose: confirm the genuine-MATLAB harness invokes the real
   dormant branch at all (nonzero `transferase_fires` count, real
   `RandStream`-backed variation across seeds) and that raw CSV schema
   matches `ingest_ppii_scenario_b`'s expectations, before spending time on
   the full matrix.
2. **Full**: all 5 states x their own 50-seed blocks each (250 total draws,
   seeds 1000-1249, disjoint per state and disjoint from Scenario A/
   macromol's 0-49 range). Expected runtime: low minutes (MATLAB process
   startup dominates; each state's evolveState call itself is O(tens of
   species), no heavy linear algebra).

Both are gated behind explicit CLI subcommands
(`run-matlab-scenario-b-canary` / `run-matlab-scenario-b-full` in
`h12_perturbation.py`) and behind `PERTURBATION_SPEC.json
scenario_b_execution_status: "NOT_YET_EXECUTED"`. Neither has been invoked in
this session; `probe_matlab_environment()`/`probe-matlab-environment` (a
standalone, unexecuted preflight license/toolbox/class-availability check)
is also not yet invoked.

## 7. Predicted verification outcomes

- Canary: expect `transferase_fires`-branch activation in all 5 seeds (the
  canary state's guard is constructed to bind unconditionally on
  `transferase_demand > 0`, independent of RNG), with cross-seed variation
  in *which* lipoprotein units are anchored this tick (the stochastic
  allocation), while aggregate bounds (mass conservation, per-species cap,
  pool cap) hold exactly in all 5. The run-manifest must record
  `randstream_class_confirmed: true` and `mode: "canary"` with exactly the 5
  pre-registered seed ids.
- Full matrix: expect all 4 single-cause states to show >=2 distinct
  allocation realizations across their 50 seeds each with 0 bound
  violations; the simultaneous-binding state additionally exercises the
  guard's dual-cause label without a contradiction (both causes present, no
  bound violated).
- If any state instead shows a structural `mnrnd`/`stochasticRound` no-op
  (e.g. because `demand` rounds to a value the guard's capacity exactly
  matches, making every seed identical), the terminal outcome would be
  `H12_PERTURBATION_SCARCITY_NO_VARIATION` for that state, not
  `H12_PERTURBATION_SCARCITY_OBSERVED_STOCHASTIC` -- this is a real possible
  outcome the code is built to detect and report honestly, not to hide.
- If genuine MATLAB, the Statistics Toolbox, or `RandStream` construction is
  unavailable in the execution environment, the canary aborts outright (no
  evidence artifact, no fallback engine) -- this is an expected, not a
  surprising, outcome and would simply mean this evidence tier cannot be
  produced in that environment.

## 8. Recommended terminal status if Scenario B executes cleanly (restated honestly)

**Goal restatement (Opus5 turn-3 correction 4):** the sole purpose of this
evidence tier is to exercise the conditioned scarcity/`mnrnd` paths under
genuine, source-faithful MATLAB execution and to support a possible later
`H12_CONDITION_GATED` proposal. It **cannot** and does not attempt to close
or remove the natural regime's `missing_required_branches:
["transferase_fires"]` finding, cannot change `H12_OBSERVED_REGIME`, and
cannot unblock L2.5. Those three facts remain true regardless of this
evidence tier's outcome.

**Recommendation (not enacted by this commit):** if the canary and full run
both produce `H12_PERTURBATION_SCARCITY_OBSERVED_STOCHASTIC` verdicts with 0
invariant violations across all 5 states, the honest terminal status for
ProteinProcessingII is a new **`H12_CONDITION_GATED`** taxonomy value
(distinct from both `H12_CONFIRMED` and `H12_OBSERVED_REGIME`), meaning: *the
dormant branch has been independently confirmed to execute correctly and
exactly under a real, source-faithful, off-nominal condition (genuine MATLAB
RandStream, not a stub), but the process's real branch coverage under its
own standard/natural Karr trace remains incomplete.* `H12_CONDITION_GATED`
would NOT be equivalent to `H12_CONFIRMED` for the purpose of any sentinel
currently gated on `H12_CONFIRMED` (`scripts/l22_evidence/h12.py:1358-1359`
-- `verify_process_specific_h12` only accepts literal `"H12_CONFIRMED"`); it
would be a new, explicitly lower-trust bucket requiring its own review before
any future gate change considers accepting it.

If Scenario B instead cannot be made to fire the branch source-faithfully
(all inversion tests below pass but the real branch stays dormant even under
genuine scarcity), or if genuine MATLAB/RandStream is simply unavailable to
run it at all, the correct terminal status remains `H12_OBSERVED_REGIME`
unchanged, and this proposal would be withdrawn rather than forced through.

## 9. Inversion tests this design must survive (implemented as unit tests in `tests/scripts/test_h12_perturbation.py`)

- Branch remains inactive under a state that was supposed to trigger it ->
  caught by `test_scenario_b_states_have_expected_regime_invalid_reason`
  (parametrized over all 5 states) plus
  `test_scenario_b_canary_state_has_nonzero_transferase_demand`.
- Only one conditioned state used instead of the matrix -> `mode="full"`
  ingest requires all 5 `PPII_SCENARIO_B_STATE_NAMES`;
  `test_ingest_ppii_scenario_b_canary_mode_processes_only_canary_state`
  proves canary-mode's single-state scope is intentional and explicit, not
  an accidental omission of the other 4.
- Global RNG mutation / non-independent streams -> each seed is an
  independently-constructed real `RandStream('mcg16807', 'Seed', k)`
  instance in the MATLAB driver (documented in
  `run_ppii_scenario_b_matlab.m` and its README), never an ambient/shared
  stream; a degenerate/no-op result from such a mutation would be caught by
  the no-variation synthetic tests
  (`test_evaluate_ppii_scarcity_invariants_no_variation_flagged`,
  `test_build_ppii_scarcity_perturbation_artifact_no_variation_when_a_state_never_varies`).
- Reused seeds across states ->
  `test_scenario_b_seed_blocks_are_pairwise_disjoint_and_avoid_scenario_a_macromol_ids`
  mechanically asserts every state's seed block is pairwise disjoint and
  disjoint from Scenario A/macromol's 0-49 range;
  `test_ingest_ppii_scenario_b_rejects_reused_or_substituted_seed_list`
  proves ingest itself rejects a manifest that substitutes an out-of-block
  seed list.
- Predictor reads `states_after`/SUT -> `guard_diagnostics_ppii`/
  `predict_ppii_scarcity_bounds`/`freeze_ppii_scenario_b_predictions` take
  only `states_before`-shaped inputs and are asserted (by
  `test_predict_phase_functions_never_touch_after_data`, an AST scan) to
  never reference after/loadtxt tokens; `ingest_ppii_scenario_b` is a
  separate, later-called function, and no import of the OC SUT exists
  anywhere in this module (`test_no_forbidden_module_imports_anywhere`).
- Scarcity never binds -> `evaluate_ppii_scarcity_invariants`'s no-variation
  and mass-conservation-violation synthetic tests exist specifically to
  prove the harness would report `NO_VARIATION`/`INVARIANT_VIOLATION`
  rather than a false `OBSERVED_STOCHASTIC`, if this were to happen.
- `mnrnd` replaced by deterministic allocation -> the no-variation synthetic
  test directly simulates this failure mode (identical allocation vector
  across seeds) and asserts the verdict is `NO_VARIATION`, not
  `OBSERVED_STOCHASTIC`; the driver's no-stub-fallback abort and
  `randstream_class_confirmed` manifest field give an additional, earlier
  catch, enforced by
  `test_ingest_ppii_scenario_b_rejects_missing_randstream_confirmation`.
- Stale standard traces mislabeled as a new condition -> Scenario B never
  reads the existing 50-seed standard traces; it generates its own inputs
  from `PPII_SCENARIO_B_STATES` via `_write_ppii_scenario_b_state_files`,
  independently of any prior extraction. A related staleness failure mode
  (a state file or harness drifting after its prediction was frozen) is
  caught by
  `test_ingest_ppii_scenario_b_rejects_stale_state_file_hash` and
  `test_ingest_ppii_scenario_b_rejects_stale_harness_hash`.
- Stored verdict trusted -> this proposal explicitly does not read or rely
  on the stored `ProteinProcessingII_h12.json` verdict for its own
  pass/fail logic; it is a self-contained, from-raw-CSV recomputation, and
  `test_ingest_ppii_scenario_b_never_recomputes_prediction_stored_verdict_is_trusted`
  proves ingest loads the FROZEN prediction rather than recomputing it
  (predict_ppii_scarcity_bounds is monkeypatched to raise, and ingest still
  succeeds).
- Mixed canary/full or wrong-cardinality evidence trusted -> a manifest mode
  mismatch, wrong row count, or seed-id-column mismatch are each rejected by
  dedicated tests
  (`test_ingest_ppii_scenario_b_rejects_manifest_mode_mismatch`,
  `test_ingest_ppii_scenario_b_rejects_mixed_canary_full_row_count`,
  `test_ingest_ppii_scenario_b_rejects_seed_id_column_mismatch`).

## 10. Non-goals (restated)

No production biology/threshold/catalog relaxation is proposed or enacted.
No repeat standard-trace extraction occurs or is proposed. No PASS/CONFIRMED
claim is made from Python-only perturbation or from Octave stub randomness
(Scenario B requires real genuine-MATLAB execution with Karr's real
`edu.stanford.covert.util.RandStream`-backed `mnrnd`/`stochasticRound`, not
yet performed). This document proposes a
distinct, new, explicitly-lower-trust taxonomy value gated by a review it
does not itself grant.
