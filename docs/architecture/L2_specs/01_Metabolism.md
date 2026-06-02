# L2 Spec — Metabolism (01)

**Status**: DRAFT v2 (post-critique), awaiting operator review.
**Last updated**: 2026-05-27.
**Authors**: Copilot (session `5c51d44b`).
**Verified against**:
- Karr source: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m`
- Python process: `opencell/vivarium/karr_metabolism.py` @ `trackA/wave2-base`
- Karr-native core: `opencell/m1/karr_metabolism.py`
- Oracle: `data/karr_fixtures/per_process_replay/Metabolism.{json,npz}` (probed 2026-05-27)

**Change log from v1**:
- **v2 fixes 6 CRITICAL + 4 SIGNIFICANT findings from the v1 adversarial critique.** See §10 for the diff.
- Major reframe: replay is now **substrate-delta** only (oracle has no flux records); per-reaction flux comparison is **out of scope** for L2 unless we re-extract the `.mat`.
- Major reframe: static mode is a setup-bug gate only. **All meaningful replay and all perturbation tests require `dynamic_bounds=True`.**
- RNG framing corrected: Karr Metabolism IS stochastic (4× `stochasticRound` per tick).

---

## 1. Purpose

Defines what "Metabolism is L2-green" means **before** we write any test. The contract has three parts:

- **(A) Replay fidelity**: feed Karr's recorded `state_before[t]`, compare our emitted Δsubstrate to Karr's `states_after[t] − state_before[t]`.
- **(B) Responsiveness**: deliberately perturb inputs beyond Karr's recorded window and check the LP responds in the biologically correct direction.
- **(C) Hard-code audit**: every numeric literal in the Python wrapper is either (a) sourced from `parameters.json` / `data/karr_fixtures/karr_native_m1.{json,npz}`, or (b) a justified algorithmic constant.

L2 verdict = (A) ∧ (B) ∧ (C).

This spec is the contract. Test code that diverges is wrong. Code changes that require this spec to change require a doc-change PR first.

---

## 2. What Metabolism does

Metabolism is the **FBA engine**. Once per tick, given enzyme counts, substrate counts, cell dry mass, and external nutrient availability, it solves a linear program that maximizes biomass production subject to:

- enzyme-kinetic upper bounds (when `dynamic_bounds=True`),
- exchange-flux limits from media composition,
- stoichiometric mass balance `S·v = 0`.

The LP returns a flux vector `v` over **645 WCM reaction IDs** (504 FBA columns once degenerate/identical reactions are collapsed; **641** is the Karr-KB count and refers to the published reactions before the WCM ID system was extended — see §2.1). Per-tick substrate deltas are `S · v · timestep`, then **stochastically rounded to integer counts** (see §2.2).

**Source-of-truth counts** (single place):

| Quantity | Count | Source |
|---|---|---|
| WCM reaction IDs (output flux vector length) | **645** | `karr_native_m1.json:reaction_wcm_ids` |
| FBA matrix columns | **504** | `karr_native_m1.npz:S` shape (376 × 504) |
| Substrate WCM IDs | **585** | `karr_native_m1.json:substrate_wcm_ids` |
| Enzyme WCM IDs | **104** | `karr_native_m1.json:enzyme_wcm_ids` |
| Substrate compartments in oracle | **3** | `Metabolism.npz:state_before__substrates` shape |
| Karr published reaction count | 641 | Karr 2012 supplement (legacy, informational only) |
| Karr published enzyme count | 100 | `Metabolism.m:38` docstring (legacy; +4 from WCM-ID extension, open question O2) |

### 2.1 Per-reaction vs per-substrate semantics
**L2 replay does not compare per-reaction fluxes**, because the oracle JSON declares `snapshot_properties = [boundEnzymes, enzymes, substrates]` — no `metabolicReaction` snapshot. Per-reaction comparison is tracked as **open question O1** (requires MATLAB re-extraction).

### 2.2 Stochasticity (corrects v1 §2 "no RNG" claim)
**Karr Metabolism IS stochastic at the substrate-update level.** `Metabolism.m` lines 1215, 1220, 1225, 1230 each call `this.randStream.stochasticRound(...)` on the continuous substrate update before writing back. The stochastic rounding rule per the MATLAB source is **independent Bernoulli draws**: for value `x` with fractional part `f`, output `ceil(x)` with probability `f`, else `floor(x)`. **No residual / carry-forward.** The oracle's `rng_seed: 0` exists specifically because of this — a given seed produces a deterministic realization, not a continuous reference.

**Implication**: bit-exact integer-count comparison to the oracle requires porting Karr's `stochasticRound` semantics with the matching seed. Otherwise we compare expected values with a sqrt(n) tolerance band. **Recommendation**: port the rounding (cheap, ~30 lines) so replay is bit-exact under matching seed.

---

## 3. Replay fidelity (Part A)

### 3.1 Oracle schema (empirically verified)

`np.load("data/karr_fixtures/per_process_replay/Metabolism.npz")` contains exactly six arrays:

| Array | Shape | Dtype | Meaning |
|---|---|---|---|
| `state_before__substrates` | `(100, 3, 585)` | float64 | Substrate counts at tick start, per compartment |
| `states_after__substrates` | `(100, 3, 585)` | float64 | Substrate counts at tick end |
| `state_before__enzymes` | `(100, 1, 104)` | float64 | Free enzyme counts at tick start |
| `states_after__enzymes` | `(100, 1, 104)` | float64 | Free enzyme counts at tick end |
| `state_before__boundEnzymes` | `(100, 1, 104)` | float64 | Bound enzyme counts at tick start |
| `states_after__boundEnzymes` | `(100, 1, 104)` | float64 | Bound enzyme counts at tick end |

**Substrate compartment index**: Karr's MATLAB convention is `cytosol = 1` (1-indexed); Python is `cytosol = 0` (0-indexed). The other two indices are extracellular and membrane — to be confirmed by inspecting nonzero patterns. See open question O5.

### 3.2 Mode requirement

Per critique finding C3, `_static_update()` in `karr_metabolism.py` does not read its `states` argument. Static mode therefore returns identical flux for every tick. **Static-mode replay against per-tick recorded data is structurally impossible.**

**Decision**: L2 replay runs in `dynamic_bounds=True` mode only. Static mode gets one trivial test ("output is invariant across feed values") solely to gate setup bugs.

### 3.3 Replay procedure (substrate delta)

For tick `t ∈ [0, 99]`:

1. Construct process input state from `state_before__{substrates, enzymes, boundEnzymes}[t]`. Map 3 compartments → Python compartment indices per §3.1.
2. Run `next_update(timestep=1.0, states=input_state)` with `dynamic_bounds=True`.
3. Extract emitted Δsubstrate from update dict.
4. Compute oracle Δ = `states_after__substrates[t] − state_before__substrates[t]`.
5. Compare per (substrate, compartment) cell:
   - **Stochastic-bit-exact path** (preferred): if our `stochasticRound` matches Karr's with the same seed sequence, integer counts must equal exactly.
   - **Expected-value path** (fallback): mean over all 100 ticks of (predicted − oracle) per (substrate, compartment) must lie within `±2 σ_round`, where `σ_round ≤ 0.5` per Bernoulli draw.

### 3.4 Enzyme delta

**Expected**: `state_before__enzymes == states_after__enzymes` for all 100 ticks (Metabolism does not modify free enzyme counts in `next_update`; that's `MacromolecularComplexation`'s job). Same for `boundEnzymes`.

**Test**: assert `(state_after - state_before) == 0` across all 100 × 104 cells, both enzymes and boundEnzymes.

### 3.5 Tolerance posture

- **Continuous flux comparison** (if a per-tick flux trace becomes available via O1): `rtol=1e-6` matches Karr's `glpk` `tolbnd=1e-6` (verified `Metabolism.m:176`). Our HiGHS solver default is ~1e-7, well inside.
- **Discrete substrate count**: see §3.3. Bit-exact under matching seed, otherwise `|cumulative_error| / sqrt(n_ticks) ≤ 1` per substrate.

**v1 stated `rtol=1e-9`. That's unreachable at the solver layer. Corrected to 1e-6.**

---

## 4. Responsiveness (Part B) — Perturbations

**All perturbations require `dynamic_bounds=True`.** Per critique finding C4, substrate-injection perturbations are no-ops in static mode.

| ID | Perturbation | Expected response | Pass criterion |
|---|---|---|---|
| **P1** | Halve external glucose (and other carbon sources to zero) | Biomass flux drops monotonically | μ_perturbed < 0.6 × μ_baseline |
| **P2** | Zero ATP | LP infeasible OR biomass = 0 OR all ATP-coupled fluxes = 0 | One of those three; warn if HiGHS returns nonzero biomass |
| **P3** | 10× one essential enzyme | Biomass increases or saturates (Vmax-cap regime) | μ_perturbed ≥ μ_baseline (within 1e-6) |
| **P4** | Halve external glucose only | Biomass drops; alternative carbon uptake increases if available | μ_perturbed < μ_baseline AND |Δμ| ≥ 1e-6 |
| **P5** | Open all reaction bounds (`lb=-BIG, ub=+BIG`) but keep `S·v=0` | LP remains feasible; μ ≥ baseline | μ_perturbed ≥ μ_baseline − 1e-6 |
| **P6** | Inject ATP demand spike (set ATP `lb` ≥ baseline×1.5 on biomass column) | Either biomass drops to accommodate or LP becomes infeasible | μ_perturbed < μ_baseline OR LP infeasible |

**Optional (P7-P9)**: solver-degeneracy probes, alternative objective weights, mass-balance violation injection. Track post-L2-green.

### 4.1 Baseline for perturbation comparisons

Run the same process in dynamic mode with **Karr's recorded `state_before[0]` (the tick-0 starting state from the oracle)** and use the resulting μ_baseline. Do **not** use a separately-fitted snapshot.

---

## 5. State-before reconstruction

To feed `next_update`, we need:

1. **Substrate counts**: directly from `state_before__substrates[t]`. Shape `(3, 585)` per tick.
2. **Enzyme counts**: directly from `state_before__enzymes[t]`. Shape `(1, 104)`.
3. **Bound enzymes**: directly from `state_before__boundEnzymes[t]`. Shape `(1, 104)`.
4. **Cell dry mass**: NOT in the oracle. Use `karr_native_m1.json:fitted.cell_dry_mass` (single scalar from the fitted snapshot). Open question O3 — should this be derived from substrate counts × MW per tick instead?
5. **Compartment volumes**: NOT in the oracle. Use fitted values from `karr_native_m1.json`. Open question O4.

### 5.1 ID mapping

Substrate IDs from `karr_native_m1.json:substrate_wcm_ids` (length 585) must match the oracle's last axis. **Verify before running**: assert lengths match and a known anchor (e.g., `ATP`) sits at the expected index.

---

## 6. Hard-code audit (Part C)

**Procedure**: grep `karr_metabolism.py` (vivarium adapter + m1 core) for numeric literals. For each, classify:

| Class | Meaning | Action |
|---|---|---|
| **OK-algorithmic** | `0`, `1`, `1e-6`, array shapes | No action |
| **OK-sourced** | Constant pulled from `parameters.json` or `karr_native_m1.{json,npz}` | Record source in code comment |
| **HARDCODE-BUG** | Biological constant inline; should come from a fixture | File fix-up PR before L2-green |

### 6.1 Known HARDCODE-BUG: `_KARR_DEMAND_KEYS`

`karr_metabolism.py:65-90` defines `_KARR_DEMAND_KEYS` as a **literal tuple of 35 WCM IDs**. The inline comment at lines 63-64 reads "Pulled from the Karr 585-ID space at runtime so we never hard-code the set" — this is **factually false**. The list IS the hard-code.

**Required fix** (must land before L2-green, can land in spec-v2 commit):
1. Remove the literal tuple.
2. Derive `_KARR_DEMAND_KEYS` at module init from `karr_native_m1.json` (the parsimony penalty terms are recoverable from the objective vector — the 35 nonzero entries past the biomass column).
3. Correct the inline comment to describe what the code actually does.

### 6.2 Audit checklist for the rest of the file

Grep for `[0-9]+\.[0-9]` and `= [0-9]{2,}` patterns. Cross-reference each hit against the fixture. Document outcome in `docs/architecture/L2_specs/01_Metabolism_hardcode_audit.md` (separate file, generated by audit run).

---

## 7. Test runner contract

A separate codex session builds `tests/L2/test_metabolism.py` (and shared `tests/L2/_runner.py`) implementing this spec. The runner must:

1. Load oracle (`np.load`, `json.load`) and verify shapes/keys match §3.1 (fail loudly if not).
2. Instantiate `KarrMetabolismProcess` with `dynamic_bounds=True`.
3. Run replay loop per §3.3.
4. Run perturbation suite per §4.
5. Run hard-code audit per §6.
6. Emit verdict JSON: `{replay: pass|fail, perturbations: {P1..P6: pass|fail}, hardcodes: {n_bugs: int, ids: [...]}, overall: pass|fail}`.

**This runner pattern becomes the template for the other 27 processes.**

---

## 8. Out of scope for L2

- **Per-reaction flux trace comparison**: oracle doesn't have it. Tracked as O1.
- **Multi-tick integration with feedback** (substrate counts updated by metabolism affect next-tick FBA): that's L3 territory.
- **Cross-process coupling**: any test that requires `MacromolecularComplexation` outputs is L3+.
- **Cell-cycle phenotypes**: doubling time, growth rate, etc. are L4+.
- **Glpk vs HiGHS bit-exact matching**: different solvers, different vertices on degenerate LPs. Out of scope; we accept any LP-optimal solution.

---

## 9. Open questions (require operator decision)

| ID | Question | Default if not resolved |
|---|---|---|
| **O1** | Re-extract `Metabolism_100ticks.mat` with `metabolicReaction.fluxs` per tick to enable per-reaction comparison? | No; L2 ships with substrate-delta only. |
| **O2** | Reconcile 104 (Python) vs 100 (Karr docstring) enzyme count. Are the extra 4 placeholder slots, or 4 real enzymes added in WCM ID extension? | Document discrepancy; do not block L2. |
| **O3** | Cell dry mass: scalar from fitted snapshot, or derive per-tick from substrate counts? | Scalar (matches Karr's snapshot FBA). |
| **O4** | Compartment volumes: fitted snapshot or per-tick from cell-mass model? | Fitted snapshot. |
| **O5** | Compartment-index mapping (oracle's axis-1 indices 0/1/2 to extracellular/cytosol/membrane). | Verify empirically from nonzero patterns; document in spec-v3. |
| **O6** | Bit-exact stochastic rounding port vs expected-value tolerance band — which does L2-green require? | Expected-value band (cheaper, still meaningful). |

---

## 10. Diff from v1 (audit trail)

| Critique ID | Severity | Resolution in v2 |
|---|---|---|
| C1 | CRITICAL | §2.1, §3.1, §3.3 — replay is substrate-delta only; per-reaction flux is O1. |
| C2 | CRITICAL | §2.2 — "no RNG" claim removed; Karr stochasticity documented. |
| C3 | CRITICAL | §3.2 — L2 runs in `dynamic_bounds=True`; static mode is setup-gate only. |
| C4 | CRITICAL | §4 header — all perturbations gated to dynamic mode. |
| C5 | CRITICAL | §2.2 — corrected to "independent Bernoulli draws, no carry-forward". |
| C6 | CRITICAL | §3.1 — oracle schema documented from empirical `np.load`. |
| S1 | SIGNIFICANT | §2 counts table + O2 — 104 vs 100 enzyme discrepancy flagged. |
| S2 | SIGNIFICANT | §2 counts table — 641 / 645 / 504 reconciled with provenance per number. |
| S3 | SIGNIFICANT | §6.1 — `_KARR_DEMAND_KEYS` reclassified as HARDCODE-BUG with required-fix gate. |
| S4 | SIGNIFICANT | §3.5 — tolerance corrected 1e-9 → 1e-6 with solver-side justification. |
| M1 | MINOR | §3.5 — arithmetic error from v1 §3.5 removed. |
| M2 | MINOR | §3.3 — `timestep=1.0` explicit; deviation = undefined behavior (will be tested with `assert timestep == 1.0` in process). |
| M3 | MINOR | §3.3 — α/β oracle-format choice resolved: §3.3 IS the format ADR for all 28 processes. Codex fanout inherits substrate-delta-replay as the default template. |
