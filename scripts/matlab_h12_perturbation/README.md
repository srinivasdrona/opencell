# `scripts/matlab_h12_perturbation/`

Genuine-**MATLAB** (not Octave) harness for ProteinProcessingII H12
Scenario B scarcity-matrix evidence generation. This directory exists
separately from `scripts/octave_h12_perturbation/` so the two execution
engines are never confused by file location:

| Directory | Engine | Scope | RNG |
|---|---|---|---|
| `scripts/octave_h12_perturbation/` | GNU Octave | Scenario A (deterministic replay), macromolecular-complexation invariants | `stochasticRoundStub.m`/`mnrndStub.m` scaffolds (provably RNG-invariant contexts only) |
| `scripts/matlab_h12_perturbation/` (this dir) | Real MATLAB + Statistics Toolbox | Scenario B scarcity-matrix (dormant transferase/scarcity branch) | Real `edu.stanford.covert.util.RandStream` (`mnrnd`/`stochasticRound`) |

## Why real MATLAB is required here

Opus5's Turn 3 review rejected an earlier Octave-stub-based Scenario B
design: Octave's `mnrndStub.m`/`stochasticRoundStub.m` scaffolds are
explicitly **not** Karr's real stochastic behavior, and using them to
"prove" the dormant transferase/scarcity branch fires with genuine
Karr-style randomness would not be valid evidence for that branch (Octave
lacks a `RandStream` class of this shape and has no `mnrnd`/`binornd`
Statistics-Toolbox equivalents at all). Scenario A remains valid Octave/stub
evidence because it only exercises code paths that are provably RNG-invariant
(see `test_h12_perturbation_source_binding.py` and `PERTURBATION_SPEC.json`
Scenario A's rationale). Scenario B specifically targets the stochastic
`mnrnd`/`stochasticRound` scarcity-allocation branch, so it requires the
real generator.

## Files

- `evolveState_ppii_matlab.m` -- TRUE VERBATIM transcription of
  `ProteinProcessingII.m` evolveState (vendored lines 349-445), with
  **zero** substitutions: `this.randStream.stochasticRound(...)` and
  `this.randStream.mnrnd(...)` are literal method calls on a real
  `this.randStream` object, unlike `scripts/octave_h12_perturbation/
  evolveState_ppii.m` which substitutes free-function stubs. Checked
  byte-for-byte (modulo comment/whitespace normalization only) against
  the vendored source by
  `tests/scripts/test_h12_perturbation_source_binding.py`
  (`MATLAB_BINDINGS`).
- `run_ppii_scenario_b_matlab.m` -- driver. Aborts (no stub fallback) if
  not running under genuine MATLAB, if the Statistics Toolbox is
  unlicensed/uninstalled, or if `edu.stanford.covert.util.RandStream`
  cannot be found/constructed. Reads each state's frozen
  `ppii_scenario_b_<name>_prediction.json` (written by
  `scripts/l22_evidence/h12_perturbation.py generate-inputs-scenario-b`)
  for its pre-registered seed list -- seed ranges are never hardcoded
  twice in both Python and MATLAB. Writes a per-state CSV (leading column
  = actual seed id) plus a per-state JSON run-manifest recording mode,
  actual seeds used, MATLAB version, toolbox license status, RandStream
  confirmation, and harness/state file hashes.
- `probe_matlab_environment.m` -- standalone, read-only preflight
  diagnostic (MATLAB/Octave, license, toolbox, RandStream construction).
  Not invoked by the driver or by anything in this commit; this is the
  "parse/license/toolbox probe" step authorized separately from (and
  before) the canary run.

## Execution status

**Nothing in this directory is invoked by this commit.** Per the
multi-turn authorization protocol for this evidence-closure task:

1. This code/spec commit is reviewed (Opus5).
2. `probe_matlab_environment.m` is run manually to confirm the target
   MATLAB environment is usable (GPT-5.6 Sol authorization).
3. `run_ppii_scenario_b_matlab.m` is run in `canary` mode
   (`PPII_SCENARIO_B_MODE=canary`) -- `transferase_capacity_scarce` only,
   its pre-registered 5-seed canary prefix.
4. After canary review, `run_ppii_scenario_b_matlab.m` is run in `full`
   mode (`PPII_SCENARIO_B_MODE=full`) -- all 5 states, 50 seeds each.

See `docs/phase_f/l2_2_design_a/h12/perturbation/PERTURBATION_SPEC.json`
(`scenario_b_execution_status`) and
`docs/phase_f/l2_2_design_a/h12/perturbation/PROTEINPROCESSINGII_SCENARIO_B_PROPOSAL.md`
for the full pre-registration.

## What this evidence can and cannot close

Even after full execution, this evidence tier is **isolated MATLAB
source-faithful stochastic-branch evidence** -- it supports a possible
future `CONDITION_GATED` classification for the scarcity/transferase
branch. It does **not** and cannot:

- Close or remove natural regime finding `missing_required_branches=['transferase_fires']`.
- Change ProteinProcessingII H12's verdict from `H12_OBSERVED_REGIME`.
- Unblock L2.5.
- Constitute an `H12_CONFIRMED` verdict on its own.
