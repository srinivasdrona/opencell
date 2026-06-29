# STATUS — Metab FBA Paradox investigation

## Hypothesis
H10-refined: NaN-vs-`+-inf` semantics differ between OC's `np.fmax`/`np.fmin` and Karr's MATLAB `max`/`min`.

## Progress log
- 2026-06-24T13:29:38Z Initialized investigation under the 3-file read-set and loaded `SESSION_CONTEXT.md` plus the deliberate-action prefix.
- 2026-06-24T13:29:38Z Completed mandated reads of `opencell/m1/calc_flux_bounds.py`, `Metabolism.m:1318-1402`, and `scripts/probe_metab_rule_isolation.py`.
- 2026-06-24T13:35:08Z Committed the standalone probe artifact at `scripts/probe_metab_fba_paradox_codex.py` before execution.
- 2026-06-24T13:35:08Z Ran `bin/oc-py scripts/probe_metab_fba_paradox_codex.py`; raw transcript written to `tmp/metab_fba_paradox_codex.log`.

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
- Are OC and Karr-faithful bound arrays element-wise identical? No.
- Diff count: 293 lower-bound reactions differ, 293 upper-bound reactions differ, 293 unique reactions differ (586 bound cells total).
- Dominant pattern: every diff is `Karr=NaN` versus a concrete OC value; the single largest bucket is `lb (OC=finite, Karr=NaN)` with 136 cells, followed by `ub (OC=+inf, Karr=NaN)` with 133 cells.
- First diff examples: `rxn[0]`, `rxn[1]`, `rxn[2]`, `rxn[9]`, `rxn[11]` all show `lb (OC=0, Karr=NaN)` and `ub (OC=+inf, Karr=NaN)`.
- Karr-faithful growth: `2.119269255200e-05` vs OC baseline `5.581449765541e-06` vs OC Rule-3-off `2.119269255200e-05`.
- Verdict: H10 confirmed. A faithful MATLAB-semantic bound calculation reproduces the Rule-3-off LP behavior exactly, so the paradox comes from OC erasing NaNs into concrete bounds before solve time.
- Exact fix note: the first concrete line to change is `opencell/m1/calc_flux_bounds.py:152`, replacing `np.fmax` with `np.maximum`, but the faithful fix is not actually one-line; the same `fmax/fmin` -> `maximum/minimum` semantic correction is also required at lines 153, 171, and 172 (and likely the other `fmax/fmin` sites) to avoid papering over the broader MATLAB-vs-NumPy mismatch.
- Beat 4 inversion checks:
  - The diff helper did not drop NaNs: every reported class explicitly includes `Karr=NaN`, and the raw log shows the per-reaction NaN-bearing values.
  - The Karr-faithful path did not call back into OC `compute_bounds`: it is a separate function in the probe that re-implements lines 1318-1402 directly with `np.maximum` / `np.minimum`.
  - The LP result is not a sanitization artifact: Karr-faithful growth matches OC Rule-3-off exactly (`2.119269255200e-05`), which is the predicted H10 signature rather than an arbitrary shifted value.

## Commits
- `649351c`: seed `STATUS_metab_fba_paradox.md` with Beats 1-4
- `ee9e730`: add `scripts/probe_metab_fba_paradox_codex.py`
- Pending final STATUS result commit.
