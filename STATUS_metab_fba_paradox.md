# STATUS — Metab FBA Paradox investigation

## Hypothesis
H10-refined: NaN-vs-`+-inf` semantics differ between OC's `np.fmax`/`np.fmin` and Karr's MATLAB `max`/`min`.

## Progress log
- 2026-06-24T13:29:38Z Initialized investigation under the 3-file read-set and loaded `SESSION_CONTEXT.md` plus the deliberate-action prefix.
- 2026-06-24T13:29:38Z Completed mandated reads of `opencell/m1/calc_flux_bounds.py`, `Metabolism.m:1318-1402`, and `scripts/probe_metab_rule_isolation.py`.

## Beat 1: Contract
The contract is to determine whether H10-refined explains the Rule 3 paradox by comparing OC `cfb.compute_bounds(...)` against a faithful MATLAB-semantic port of `Metabolism.calcFluxBounds()` for the same tick-0 inputs.
Investigation succeeds if the standalone probe can distinguish, with quantitative evidence, between "NaN handling changes the bound arrays and restores growth toward `~2e-5`" and "the bound arrays do not differ in a way that explains the LP gap."

## Beat 2: Read-set
- `opencell/m1/calc_flux_bounds.py:1-200`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m:1318-1402`
- `scripts/probe_metab_rule_isolation.py:1-101`

Suspect patterns in `compute_bounds`:
- Rule 1 uses `np.fmax` / `np.fmin` at lines 152-153 with an inline comment that NaNs are "benign," which is exactly the semantic claim under test.
- Rule 3 uses `np.fmax` / `np.fmin` at lines 171-172, so any NaN produced earlier is silently replaced by the static bounds instead of propagating.
- Rules 4 and 5 also use `np.fmax` / `np.fmin`, which means the OC implementation consistently normalizes NaNs away after initialization.

## Beat 3: Falsifiable prediction
If H10 is true, the probe will print that OC and Karr-faithful bounds differ at one or more columns, that the dominant diff class is NaN-vs-`-inf` or NaN-vs-`0`, and that solving the OC LP with Karr-faithful bounds raises growth toward `~2e-5` (closer to OC Rule-3-off at `2.12e-5` than to OC baseline at `5.58e-6`).
If H10 is false, the probe will print either that the bound arrays are element-wise identical across all 504 columns or that any differences do not move growth materially away from `5.58e-6`, which rejects NaN-handling as the causal bug.

## Beat 4: Inversion
The probe could falsely confirm H10 if its comparison helper treats NaNs as equal-to-missing and drops them before classification, causing the report to miss the actual divergence pattern.
The probe could also falsely confirm H10 if the supposed Karr-faithful path accidentally reuses OC `compute_bounds` or copies its `np.fmax` / `np.fmin` semantics, producing an answer that only looks independent.
Another false confirmation mode is mapping NaN bounds to large finite numbers differently from the path used by `solve_fba`, which would make any growth delta an artifact of the probe instead of evidence about Rule 3 semantics.

## Beat 5: Result
- Pending probe implementation and execution.

## Commits
- Pending.
