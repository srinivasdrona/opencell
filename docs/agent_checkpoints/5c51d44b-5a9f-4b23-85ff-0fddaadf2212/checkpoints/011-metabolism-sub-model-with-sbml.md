<overview>
Building OpenCell, an open-source whole-cell simulation in Python/JAX. This session segment built the first sub-model anchored on real biology: `opencell/models/sbml_model.py` (generic SBML→ODE engine via libsbml + sympy.lambdify) and `opencell/models/metabolism.py` (Chassagnole 2002 / BIOMD0000000051 wrapper). Validated to ~1e-8 relative agreement vs libroadrunner over 5 minutes simulated time, with comparison artifacts (PNGs + JSON) committed. Currently debugging an unexpectedly large (~12%) discrepancy in a glucose-spike perturbation experiment.
</overview>

<history>
1. User: "1. which is better accepted? 2. go with your instinct" (re: libsbml vs ElementTree, manifest vs direct SBML)
   - Chose libsbml (universal in SBML ecosystem: COPASI, PySCeS, Tellurium, COBRApy)
   - Chose direct SBML for `MetabolismModel` with manifest reference recorded in provenance
   - Verified libsbml installs cleanly + extracts clean infix formulas via `libsbml.formulaToString(kl.getMath())`
   - Built `opencell/models/sbml_model.py` (~340 lines): SbmlOdeModel.from_file, _compile_formula via sympy.lambdify, RHS with assignment-rule cofactors, compartment volume scaling, loud failure on events/funcdefs/rateRules
   - Built `opencell/models/metabolism.py`: thin wrapper pinning BIOMD0000000051 + DOI 10.1002/bit.10288 + PMID 17590932
   - PySCeS oracle blocked by an internal PySCeS bug (`'NewCore' object has no attribute 'time'` on csymbol-time assignment rules). Pivoted to libroadrunner — installed cleanly, gave clean ~1e-6 agreement on first try.
   - Built tests/unit/test_sbml_model.py (17 tests) + tests/integration/test_metabolism_chassagnole.py (4 tests). Initially 3 failures: sympy singleton collision (S/E/I/Q/etc), funcdef test had wrong XML element ordering, RR API exclusivity (times vs start/end/points). All fixed.
   - 357 → 378 tests passing, no regressions, 4m16s. Committed `4f6ccf5`.

2. User: "did you really run the complete simulation? I do not see the output PNG files. Did you generate them for both the runs? I want to compare how close them are."
   - Built `scripts/compare_chassagnole.py`: runs both simulators, produces 3 PNGs (opencell, roadrunner, overlay+residual log panel) + residuals JSON
   - Worst-case error across all 18 species, 601 time points: 2.48e-8 relative
   - Overlay PNG: dashed (OC) lines visually invisible under thick (RR) lines
   - Committed `8ef06e8`. Cleaned up stale `.git-commit-msg.tmp` in `8c3fab8`.

3. User: "let's run it for 5 minute duration and compare the results, annotate the artifact file names as 5 minute simulation or 300 seconds, some such"
   - Parameterized script with --seconds, suffixed all artifact filenames with `_{secs}s`
   - Re-ran for both 60s and 300s, removed legacy unsuffixed names
   - 300s results: worst 3.3e-8, median 6.8e-9 (5× longer integration → only 33% more error)
   - Committed `7b3ade7`.

4. User: "why did both 60s and 300s take the same wall time? did the 300s one actually run for that long?"
   - Ran benchmark across horizons 10s/60s/300s/600s/1800s
   - Showed actual integration is 0.14s → 0.54s (sub-linear due to LSODA adaptive stepping in smooth post-transient regime)
   - Showed ~13s wall is overhead: roadrunner C-extension import (~8s) + matplotlib (~2s) + RR model compile + 6 PNG writes
   - Showed biology proof: cglcex drops 1.32 → 0.061 → 0.046 → 0.044 mM across t=60/300/600/1800s
   - No code changes, just diagnostic.

5. User: "great, can we rerun for 300 second, but with a glucose spike at 180 seconds, double the initial starting value?"
   - Built `scripts/spike_chassagnole.py`: two-phase integration (0→180, set cglcex=4.0, 180→300). For RR uses `rr["[cglcex]"] = 4.0` between two `simulate()` calls.
   - First run: spike worked (cglcex pre=0.29, post=3.98) but worst-case rel error blew up to 12% on cpep, ~10% on cg6p/cf6p/cfdp
   - Suspected time-grid misalignment between OC's t_eval and RR's `simulate(start, end, npoints)` second call. Fixed by asking RR for N+1 points and dropping the duplicate spike-time row, plus added an explicit grid-alignment assertion.
   - Re-ran: **identical errors**, grid assertion did NOT trip → grid alignment was not the bug.
   - Started diagnostic to inspect whether RR's `simulate()` silently resets state at start of each call (a known RR foot-gun). PowerShell choked on the inline Python because of `f"... {rr['[cglcex]']:.4f} ..."` — quote-escaping inside a heredoc inside `wsl -- bash -c '...'` triggered a PowerShell parse error.
   - **This is where the segment was paused for compaction.**
</history>

<work_done>
Files created:
- `opencell/models/sbml_model.py` (~340 lines): generic SBML→ODE engine
- `opencell/models/metabolism.py` (~140 lines): Chassagnole wrapper with provenance
- `scripts/run_chassagnole.py` (~100 lines): single-run demo + provenance JSON
- `scripts/compare_chassagnole.py` (~210 lines): OC vs RR comparison with 3 PNGs + JSON, --seconds parameterized
- `scripts/spike_chassagnole.py` (~205 lines): two-phase glucose spike comparison
- `tests/unit/test_sbml_model.py`: 17 tests (formula compile incl. singleton-shadow guard, Chassagnole load, unsupported-feature loud failures)
- `tests/integration/test_metabolism_chassagnole.py`: 4 tests (libroadrunner oracle agreement)
- `artifacts/chassagnole_opencell_60s.png`, `_300s.png`
- `artifacts/chassagnole_roadrunner_60s.png`, `_300s.png`
- `artifacts/chassagnole_overlay_60s.png`, `_300s.png`
- `artifacts/chassagnole_residuals_60s.json`, `_300s.json`
- `artifacts/chassagnole_spike_overlay_300s.png`, `chassagnole_spike_residuals_300s.json` (these have the 12% bug — must be regenerated after fix)

Files modified:
- `pyproject.toml`: added `sympy>=1.13` to runtime deps; `libroadrunner>=2.7` to oracle extras
- `.gitignore`: added `.git-commit-msg.tmp`

Commits:
- `4f6ccf5`: metabolism + sbml_model + tests
- `8ef06e8`: compare_chassagnole.py + initial 60s artifacts
- `8c3fab8`: cleanup stale temp file
- `7b3ade7`: parameterize --seconds; 60s + 300s suffixed artifacts
- (spike_chassagnole.py + buggy spike artifacts NOT committed yet — must be fixed first)

Tests: 378 passing (was 357 at session start, +21 new). Full suite ~4m16s.

End-to-end working:
- ✅ SBML→ODE engine on Chassagnole BIOMD0000000051 (18 species, 48 reactions, 7 assignment rules)
- ✅ Smooth-trajectory agreement with libroadrunner ~1e-8 relative across 18 species, 5 min sim time
- ❌ **Glucose-spike perturbation**: ~12% rel error on cpep — cause not yet identified
</work_done>

<technical_details>

### SBML→ODE engine architecture
- libsbml parses SBML L2/L3; for each `<kineticLaw>` and `<assignmentRule>`, `libsbml.formulaToString(getMath())` returns infix string
- `_compile_formula`: regex-extract identifiers, build `local_dict={name: sympy.Symbol(name)}` to **prevent singleton shadowing** (S→sympy.S, E→exp(1), I→sqrt(-1), N→Naturals, O→BigO, Q→Rationals), then `sympy.lambdify(symbols, expr, modules='numpy')`
- `_SBML_RESERVED` frozenset of MathML/SBML built-ins (pow, exp, log, ln, sqrt, sin, cos, pow, ceiling, piecewise, gt/lt/geq, pi, exponentiale, true/false) — not pre-bound
- RHS: build env (boundary species + global params + compartment volumes + t/time + dynamic species from y), apply assignment rules in document order, compute fluxes by evaluating compiled kinetic laws against env+local_params, then `dydt = stoich @ fluxes / volume`
- Loud failure: `<event>`, `<functionDefinition>`, `<rateRule>`, `<algebraicRule>`, `<initialAssignment>`, `hasOnlySubstanceUnits=true`

### Chassagnole BIOMD0000000051 specifics
- SBML L2 V1
- 18 dynamic species (all concentrations, in cytosol or extracellular, both compartments size 1.0)
- 7 cofactors (catp, cadp, camp, cnadp, cnadph, cnad, cnadh) — declared as **non-constant global parameters** driven by 7 `<assignmentRule>` elements. Empirical fits to measured cofactor data over the original glucose-pulse experiment (functions of `t` only).
- 48 reactions, each with 4–6 local parameters in `<kineticLaw>`
- No events, no function defs, no rate rules
- SBML SHA-256: `28deec2bf55de027f116b46a8b1a75a820b05bdc9c5cd72dcf260bfacba75302`

### Validation: libroadrunner is the right oracle
- PySCeS hits `'NewCore' object has no attribute 'time'` on csymbol-time assignment rules — internal bug, not our problem
- libroadrunner (2.9.2) installs cleanly via pip, runs Chassagnole out of the box
- Smooth-trajectory agreement: worst 3.3e-8 rel err over 5 min, ~5 orders below test threshold of 1e-3

### Solver scaling (LSODA on Chassagnole)
- 10s→0.145s wall, 2,525 RHS evals
- 60s→0.34s wall, 6,355 evals
- 300s→0.44s wall, 7,959 evals  (**5× more sim time, only 25% more evals** — adaptive stepping in smooth regime)
- 600s→0.54s wall, 9,131 evals
- 1800s→0.51s wall, 8,675 evals (system at steady state, large steps)

### Time-grid alignment quirk in spike script
- `rr.simulate(start, end, N)` returns N rows including BOTH endpoints, so dt = (end-start)/(N-1). If you want to match a uniform t_eval grid spanning the second phase (e.g., 180.1, 180.2, ..., 300.0 = 1200 pts at dt=0.1), you must call `rr.simulate(180, 300, 1201)` and drop the first row (the spike-time duplicate).
- Added explicit grid alignment assertion in `run_roadrunner_with_spike` — it does NOT trip, so the 12% spike error is NOT a grid issue.

### **Open mystery: 12% error in glucose-spike experiment**
Smooth case: ~1e-8 rel err. Spike case at t=180s with cglcex 2.0→4.0:
- cpep max_rel = 1.18e-1
- cpyr max_rel = 9.93e-2
- cg6p, cf6p, cfdp ~7-8%
- cglcex itself: 1.5e-3 (only ~10× worse than smooth case)
Hypotheses:
1. **(MOST LIKELY)** `rr.simulate(start, end, N)` silently resets state to model initial conditions at the start of each call — known RR foot-gun. The spike write `rr['[cglcex]'] = 4.0` would be discarded. Need to verify by inspecting `res2[0, cglcex_col]` — should be 4.0 if spike persisted, 2.0 if RR reset.
2. RR may treat `simulate(180, 300, ...)` as a fresh integration starting from t=180 with initial conditions (no spike applied), but with assignment rules evaluated at t=180+ (so cofactors are correct), giving glucose-pulse-from-fresh-state dynamics — different from OC's continuation-from-spiked-state.
3. RR may need `useResetSeed=False` or `setSimulateOptions(reset=False)` to preserve state across simulate() calls.

### PowerShell + WSL + Python heredoc gotcha
Inline Python with f-strings containing `{rr['[cglcex]']:.4f}` inside `wsl -- bash -c "python -c \"...\"` triggers PowerShell parse error: `Array index expression is missing or not valid` because PS interprets `[cglcex]` as an array index in the unquoted-by-PS portion.
Workarounds:
- Write Python to a `.py` file or `/tmp/foo.py` first, then run via `python /tmp/foo.py`
- Use `${'$'}` escaping
- Avoid bracketed strings like `[cglcex]` in inline scripts
- Use `rr.getValue('[cglcex]')` instead of `rr['[cglcex]']` (no brackets in subscript)

### libsbml + sympy install in WSL venv
`/mnt/e/opencell/.venv-wsl/` — pre-existing. `python-libsbml==5.21.1` already installed; `libroadrunner==2.9.2` installed in this session.

### File-system sync delay quirk (Windows ↔ WSL)
After `create` writes a file via Windows path, the file may not be visible from WSL for 1–5 seconds. Workaround: `sleep 2 && ...` before running the new script. Recurred multiple times; trivial but wastes a tool call each time.

### Git commit messages over WSL
`git commit -m "long multi-line message"` over `wsl.exe` pipe HANGS. Workaround: write message to `/tmp/foo.msg` via heredoc inside the same bash invocation, then `git commit -F /tmp/foo.msg`. Works reliably. Documented in earlier session checkpoint.
</technical_details>

<important_files>

- **`E:\opencell\opencell\models\sbml_model.py`** (NEW)
  - Generic SBML→ODE engine. Heart of the new capability.
  - `_compile_formula` (lines ~95-125): the singleton-safe sympy parser
  - `SbmlOdeModel.from_file` (lines ~155-280): loads + compiles entire model
  - `rhs` (lines ~310-330): the ODE RHS suitable for solve_ivp/LSODA
  - `provenance` (lines ~335-355): SHA-256 + topology audit record

- **`E:\opencell\opencell\models\metabolism.py`** (NEW)
  - `MetabolismModel.load()` pins BIOMD0000000051 + paper-pairing identifiers
  - `provenance()` extends sbml_model.provenance with biomodels_id + paper_doi + paper_pubmed_id

- **`E:\opencell\scripts\spike_chassagnole.py`** (NEW, **HAS THE BUG**)
  - Lines 56-92: `run_opencell_with_spike` — two-phase integration with `y_after_spike[cglcex_idx] = spike_value`
  - Lines 95-130: `run_roadrunner_with_spike` — uses `rr["[cglcex]"] = 4.0` between two simulate() calls. **Must investigate whether RR resets state.**
  - Grid alignment fix at lines 113-126 confirmed not to be the bug

- **`E:\opencell\scripts\compare_chassagnole.py`** (NEW, working)
  - Reference for clean OC-vs-RR comparison pattern (smooth case, ~1e-8 agreement)
  - Use this as template when fixing spike script

- **`E:\opencell\tests\unit\test_sbml_model.py`** (NEW)
  - 17 tests including `test_sympy_singleton_names_not_shadowed` (regression guard for the S/E/I/Q bug)

- **`E:\opencell\tests\integration\test_metabolism_chassagnole.py`** (NEW)
  - libroadrunner oracle test, rtol=1e-3 atol=1e-6, all 18 species, 7 sample times

- **`E:\opencell\artifacts\chassagnole_overlay_300s.png`** (committed, smooth case)
  - Shows visually perfect OC-vs-RR agreement; the standard for what spike comparison should look like once fixed

- **`E:\opencell\artifacts\chassagnole_spike_overlay_300s.png`** (NOT committed, has 12% errors)
  - Currently shows visible deviation post-spike; will need regeneration after bug fix

- **`E:\opencell\pyproject.toml`** (MODIFIED)
  - Added `sympy>=1.13` to dependencies (line ~29)
  - Added `libroadrunner>=2.7` to `[oracle]` extras

- **`C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`** (UPDATED)
  - Top sections now reflect 378 tests, metabolism sub-model COMPLETE, libroadrunner oracle agreement, updated Honest Status (8 blockers → 7 with metabolism done), revised next-steps focusing on adding more sub-models + coupling

- **`E:\opencell\manifests\chassagnole2002.draft.yaml`** (UNCHANGED this segment)
  - Has the eutils-verified paper-pairing block; metabolism.py references it as audit sidecar

- **`E:\opencell\data\biomodels_reference\BIOMD0000000051_chassagnole2002.xml`** (UNCHANGED, committed previously)
  - The 137KB SBML the engine consumes; SHA-256 `28deec2bf55de027f116b46a8b1a75a820b05bdc9c5cd72dcf260bfacba75302`
</important_files>

<next_steps>

**Immediate (where compaction interrupted):** Diagnose and fix the 12% rel error in `scripts/spike_chassagnole.py`.

**Step 1 — Confirm the hypothesis** (RR resets state at start of `simulate()`):
Write a Python file (NOT inline `python -c` — avoid the `[cglcex]` PowerShell parse error) to `/tmp/diag_spike.py` containing:
```python
import roadrunner
rr = roadrunner.RoadRunner("data/biomodels_reference/BIOMD0000000051_chassagnole2002.xml")
rr.integrator.relative_tolerance = 1e-10
rr.integrator.absolute_tolerance = 1e-12
res1 = rr.simulate(0, 180, 1801)
print("after sim1 live cglcex:", rr.getValue("[cglcex]"))
print("res1 last cglcex:", res1[-1, list(res1.colnames).index("[cglcex]")])
rr.setValue("[cglcex]", 4.0)
print("after spike live cglcex:", rr.getValue("[cglcex]"))
res2 = rr.simulate(180, 300, 1201)
print("res2 first cglcex:", res2[0, list(res2.colnames).index("[cglcex]")])
print("after sim2 live cglcex:", rr.getValue("[cglcex]"))
```
Then run with `wsl -- bash -c 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && python /tmp/diag_spike.py'`.

If `res2[0, cglcex]` is 4.0, spike persisted → look elsewhere (maybe assignment rules?).
If `res2[0, cglcex]` is 2.0 (or the natural decayed value at t=180), spike was discarded → need to set `rr.SimulateOptions.reset=False` or use `rr.oneStep` / `rr.integrator.integrate()` directly.

**Step 2 — Fix in `scripts/spike_chassagnole.py`**:
Likely fix is one of:
- `rr.getSimulateOptions().reset_at_start = False` (or similar property name; check API)
- Use `rr.oneStep(t, dt)` in a loop after the spike rather than `rr.simulate()`
- Pass `reset=False` keyword to second `simulate()` call

**Step 3 — Re-run spike script, verify rel error drops back to ~1e-7 range**, regenerate `chassagnole_spike_overlay_300s.png`, commit.

**After spike is debugged:**
1. Build a second sub-model (transcription) on a curated BioModels entry — same SBML→ODE pattern. Candidate: a simple constitutive transcription model from BioModels (search needed).
2. Wire metabolism + transcription via the resource ledger so they share at least ATP. First multi-module coupled integration.
3. Build `solvers/hybrid.py` for ODE+SSA operator splitting.
4. Replan Phase 2 around the "stitched curated BioModels entries" architecture instead of "designed toy genes."

**Open assumptions to validate:**
- The 12% error is solely a state-reset issue in RR — could partially be assignment-rule timing or solver-restart accuracy. Address the obvious cause first; verify; only then chase residual error.
- Once the spike experiment is correct, this is a strong candidate for a new test in `tests/integration/test_metabolism_chassagnole.py` covering perturbation scenarios.
</next_steps>