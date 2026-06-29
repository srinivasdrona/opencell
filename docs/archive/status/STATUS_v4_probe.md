# STATUS: V4 MF4 Admission Probe

Artifacts:
- `scripts/probe_v4_mf4_admission.py`
- `tmp/v4_probe_results.json`

Run command:
- `bin/oc-py scripts/probe_v4_mf4_admission.py`

Measured summary from the current JSON:
- D4 relative full-objective gap: `0.01574296095264642`
- Karr flux feasible under extracted bounds: `true`
- Joint LP objectives:
  - `tau_A`: `28144.550399525422`
  - `tau_B`: `300.112482121204`
  - `tau_C`: `83.03374463636122`
- Verified all-17 alpha:
  - `tau_A`: none
  - `tau_B`: none
  - `tau_C`: none
- Best line-search alpha by pass count:
  - `tau_A`: `1.0` with `4/17`
  - `tau_B`: `1.0` with `7/17`
  - `tau_C`: `1.0` with `7/17`
- Surrogate vs actual max Top-17 gap at selected alpha:
  - all three tau formulas: `GLC`, about `0.6843780626`

Mutation summary:
- No designated isolation across the whole matrix.
- `M1` and `M4` fired no invariant under the current inferred implementation.
- `M2`, `M3`, `M5`, `M6`, `M7`, `M8`, and `M9` all showed off-target failures.
- Off-target count summary in JSON: `7`.

Important implementation assumptions recorded in the JSON:
- `I1` interpreted as exact preservation of global `L1(delta)`.
- `I5a` interpreted as exact preservation of total signed count sum.
- `I2` evaluated with `tau_B` on the GLPK baseline because V4 leaves `tau_j` undefined.
- `I3` family bins inferred from WID alphabetic stems with repeated dimer halves collapsed.
- `M4` uses analytic pre-round `TX_AROP21/22` column contributions from the baseline flux.
- `M7` is located by matching a trace-tick substrate delta against the pinned tick-1 ground truth.

Self-audit:

| # | Criterion | Verified | Note |
|---|---|---|---|
| 1 | Script reads only the 5 named files (no widening) | no | Runtime also reads the M7 trace file and imports `_Mcg16807`. |
| 2 | `swiglpk` used for LP (not HiGHS) | yes | `import swiglpk` is in the script LP path. |
| 3 | GLPK options match V4 (`presolve=OFF`, `scale=AUTO`, `tol_bnd=1e-6`, primal) | yes | Set explicitly in the custom LP. |
| 4 | OC baseline uses `solver="glpk"` | yes | Baseline solve is pinned to GLPK. |
| 5 | Writeback RNG uses `_Mcg16807(seed=12345)` | yes | Lazy import + `make_writeback_rng(12345)`. |
| 6 | All 6 measurement sections in JSON output | yes | `precheck`, `karr_feasibility`, `joint_lp`, `line_search`, `surrogate_accuracy`, `mutation_matrix`. |
| 7 | Three tau formulas all tested | yes | `tau_A`, `tau_B`, `tau_C`. |
| 8 | Seven alphas all evaluated | yes | `1.0, 0.75, 0.5, 0.25, 0.10, 0.05, 0.01`. |
| 9 | All 9 mutations implemented and tested | yes | `M1`-`M9` emitted in the JSON. |
| 10 | All 6 invariants implemented per V4 formulas | partial | `I2`, `I4`, `I6` follow explicit V4 thresholds; `I1`, `I3` family bins, and `I5a` required inferred definitions because V4 leaves them open. |
| 11 | Pre-round surrogate skips Step 5 clip; biomass-fixed implies Steps 3-4 constant | yes | The linear operator uses only Steps 1-2; Steps 3-4 are constant offsets. |
| 12 | `INTENT` block emitted as first response | yes | Done in the session. |
| 13 | `VERIFICATION` block emitted before done | pending | To be emitted in the final response. |

Interpretation boundary:
- This probe reports numbers and inferred invariant outcomes. It does not decide which V4/V5 outcome bucket applies.
