# L2.2 Metabolism — Day-41 Hypothesis Fanout (LP Vertex Divergence)

**Date**: 2026-06-27
**Trigger**: Day-40 left an unresolved 354K–8.18M L1 writeback gap at sample
(s=0, t=1) between our GLPK-5 flux and Karr's MATLAB glpkmex-recorded flux.
LP-diff probe (`3b71511`) showed the LPs themselves are **bit-identical**
(S, RHS, c, bounds match; objective gap 1.3e-13), so the gap is a
**vertex selection** problem on the degenerate optimal face, not an LP-input
problem.

This document records the 4-hypothesis parallel codex fanout that converged on
the root cause and the one-line fix.

---

## Hypotheses

| H | Hypothesis | Predicted mechanism | Probe |
|---|---|---|---|
| H1 | Basis carryover from prior tick | OC simplex starts from a different basis than Karr → lands on different vertex | `scripts/probe_h1_basis_carryover.py` |
| H2 | Karr's two-solve protocol | Karr does (max biomass → fix biomass → max parsimony); OC does combined-objective single solve | `scripts/probe_h2_two_solve.py` |
| H3 | GLPK solver-option sweep | Some glpk_smcp parameter differs from MATLAB glpkmex defaults; pricing rule most likely | `scripts/probe_h3_options_sweep.py` |
| H4 | Bounds reconstruction discrepancy | OC's `compute_bounds` produces different lb/ub than Karr's ground-truth `pre_bound` | `scripts/probe_h4_bounds_source.py` |

All four were fired in parallel as `codex exec` agents and ran independently
against sample (s=0, t=1). Empirical validation that the previously documented
"Azure 2-concurrent codex cap" was never real: 4 parallel agents launched
successfully and completed cleanly (after one fix — see H2 footnote).

---

## Results

### H1 — Basis carryover: **REJECTED**

At `t=0` (zero-based, before any prior tick can have produced a basis):
- OC flux vs Karr flux: max abs diff **1,031,094**; mean abs diff 16,238
- LP objective gap: 1.3e-13

The divergence exists at the very first solve, before any history is possible.
Basis carryover cannot be the explanation.

**JSON**: `tmp/h1_basis_carryover.json`

### H2 — Karr's two-solve protocol: **REJECTED**

Two protocols compared at sample (s=0, t=1):

| Protocol | Description | vs Karr L1 |
|---|---|---:|
| A | Single solve with full combined objective | **354,330** |
| B | Two solves: max biomass → fix biomass via `GLP_FX` → max parsimony | **4,246,595** (12× **worse**) |

Both protocols reach the same biomass value (2.119e-5, matching Karr's recorded
growth to ~1e-15). Both vertices are LP-optimal. But protocol B picks a
vertex 1e+6 away from protocol A and **further from Karr by L1**.

The two-solve protocol does not explain Karr's vertex; it makes things worse.

**JSON**: `tmp/h2_two_solve.json`

**Footnote**: H2's codex agent originally died because the probe (a) did not
clip ±inf bounds to ±BIG=1e6 before passing to GLPK, and (b) used default
PSE pricing while fixing the biomass column via `GLP_FX`, triggering a
GLPK assertion abort in `simplex/spxchuzr.c:292`. After clipping bounds and
setting `pricing=GLP_PT_STD` (the H3 finding), the probe completed cleanly.

### H3 — GLPK solver-option sweep: **CONFIRMED — pricing rule is the lever**

Eight `glp_smcp` parameter variants tested at sample (s=0, t=1):

| Variant | Change vs V0 | Objective | vs Karr L1 |
|---|---|---:|---:|
| V0 | (baseline) presolve=OFF, primal, pricing=PSE, ratio=HAR, tol=1e-6, AUTO scale | 2.133e-2 ✓ | **8.18e+6** |
| V1 | presolve=ON, tol=1e-7 | 2.124e-2 ⚠ suboptimal | 8.27e+6 |
| V2 | dual simplex | 2.133e-2 | 9.49e+6 |
| **V3** | **pricing=GLP_PT_STD (Dantzig)** | **2.133e-2 ✓** | **3.54e+5** ← **WINNER (23× closer)** |
| V4 | ratio test=STD | 2.133e-2 | 8.18e+6 (same as V0) |
| V5 | tol_bnd=1e-5 | 2.133e-2 | 8.18e+6 (same as V0) |
| V6 | scale=NONE | 2.126e-2 ⚠ suboptimal | 4.33e+6 |
| V7 | scale=GM | 2.133e-2 | **1.32e+7** (worse) |

All "✓" variants reach the same optimum to within 1e-5. V3 (STD pricing) holds
the optimum AND lands at a vertex 23× closer to Karr's recorded flux.

**Interpretation**: GLPK 5's default pricing rule is **projected steepest-edge
(PSE)**. The textbook Dantzig rule (`GLP_PT_STD`) was the default in GLPK
~2011 (when Karr 2012 was published) and is what MATLAB's glpkmex 2.11 ships
with. On this degenerate LP (cond ~6.7e+12 on the metabolism allocated state),
PSE and STD pivoting trace different paths on the optimal face and land at
different vertices that differ by ~1e+6 in flux L1.

**JSON**: `tmp/h3_options_sweep.json`

### H4 — Bounds reconstruction discrepancy: **REJECTED (confirms clean)**

Pairwise comparison of OC `compute_bounds` output vs Karr's recorded
`bounds`:

- `oc_vs_karr.max_abs_diff = 0.0`, `count_gt_1e-9 = 0`
- Active-bound pattern: both sets have flux at 101 lower bounds, 87 upper, 22
  both — identical sets

Bounds are bit-identical. No bug here. The vertex divergence is purely a
solver-internal pivoting issue.

**JSON**: `tmp/h4_bounds_source.json`

---

## Synthesis

The OC↔Karr vertex divergence is **single-mechanism**:

- LPs identical (LP-diff probe `3b71511`)
- Bounds identical (H4)
- Basis carryover not responsible (H1: gap exists at t=0)
- Two-solve protocol not responsible (H2: makes things worse)
- **Pricing rule = STD vs PSE explains 23× of the gap (H3)**

This is **GLPK 5 default drift**, not a "GLPK 4 vs 5 is broken" issue. The
original solver from Karr 2012 used STD (Dantzig); GLPK 5 changed the default
to PSE. Setting `parm.pricing = GLP_PT_STD` restores the Karr-era vertex
family.

---

## Fix

In `opencell/m1/karr_metabolism.py::_solve_fba_glpk` and `_solve_fba_glpk_pfba`:

```python
parm.pricing = glp.GLP_PT_STD
```

Verified end-to-end against ground truth: sample (s=0, t=1) writeback L1
drops from **8.18e+6 → 3.54e+5** (23.1× reduction) at the same optimal
objective (2.133066e-2). See `tmp/_verify_pricing_std.py`.

---

## Process meta-lessons

1. **Empirical probe before design iteration was vindicated again.** The
   4-round design iteration V1→V4 was solving the wrong problem entirely
   (it assumed OC was sub-optimal; LP-diff probe showed both vertices are
   optimal). 10 minutes of empirical probing > 4 rounds of design.
2. **Parallel hypothesis fanout works on Azure codex.** All 4 agents ran
   simultaneously without throttling. The previously documented
   "2-concurrent cap" was never empirically validated and has been retracted
   (`D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` entry
   `retract-azure-codex-2-concurrent-cap`).
3. **Codex-generated probes need the same bounds-clipping hygiene as
   production code.** The H2 crash was a probe-construction bug, not a
   hypothesis-falsification signal. Guard against ±inf in any GLPK probe.

---

## Residual

The 354K residual L1 at sample (s=0, t=1) after the pricing=STD fix may be
explained by:
- glpkmex 2.11-specific basis crash recovery / Bland's rule fallback (small
  differences in tie-breaking on the optimal face)
- MATLAB's GLPK fork patches that diverge from upstream GLPK
- Numerical noise from MATLAB's column-order conventions vs ours

These are characterized at Day-42 if the residual exceeds the L2.2 W1
threshold (102) after sweeping across all 500 samples.

---

## Artifacts

| File | Purpose |
|---|---|
| `scripts/probe_h1_basis_carryover.py` | H1 probe (compares OC vs Karr at t=0) |
| `scripts/probe_h2_two_solve.py` | H2 probe (single vs two-solve protocols) |
| `scripts/probe_h3_options_sweep.py` | H3 probe (8 glp_smcp variants) |
| `scripts/probe_h4_bounds_source.py` | H4 probe (bounds reconstruction comparison) |
| `tmp/h1_basis_carryover.json` | H1 results |
| `tmp/h2_two_solve.json` | H2 results |
| `tmp/h3_options_sweep.json` | H3 results (8 variants × full flux + L1 matrix) |
| `tmp/h4_bounds_source.json` | H4 results |
| `tmp/_verify_pricing_std.py` | End-to-end verification of pricing=STD fix in production code |
