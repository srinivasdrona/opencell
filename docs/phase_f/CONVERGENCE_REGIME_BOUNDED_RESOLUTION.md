# Convergence-Greens — Design for Closing the Substrate-Regime Gap

**Status:** v0.1 (2026-06-15) — draft for operator review
**Owner:** OpenCell whole-cell-simulation project, Phase F
**Scope:** Closing the gap revealed by Day-29 substrate-stress validation for 3 "regime-bounded green" processes (tRNAAminoacylation, MacromolecularComplexation, ProteinTranslocation).

**Companion docs:**
- `L2_2_DESIGN_A_SPEC.md` — sibling per-tick gate
- `PROCESS_CATALOG.yaml` v3.3 — catalog with `closed_form_dominant: regime_bounded` for the 3 processes
- `tests/vivarium/_substrate_stress/{trnaaa,macromol,ptransloc,ppi,ppii,pfolding}_stress_v2*.py` — empirical validation harnesses

---

## 0. Correcting a framing mistake first

Earlier in this design conversation I framed the question as: **"do we need to port the inner Monte Carlo step from Karr to OC?"** That framing is wrong. Verification:

| Process | Stochastic primitives in OC port today |
|---|---|
| MacromolecularComplexation | `_per_cluster_mc` at `karr_macromolecular_complexation.py:93` (uses rng for collision-theory MC) |
| tRNAAminoacylation | `_stochastic_round` (line 384), `_histc_bin_index(rng.random(...))` (line 404), `rng.random(draws)` (line 416), `_rng.random(vals.shape)` (line 445) — multiple stochastic primitives |
| ProteinTranslocation | `_rng.permutation` (line 304) — randperm for translocation order |
| ProteinFolding | `rng.choice` (line 467) — stochastic chaperone allocation |
| ProteinProcessingI / II | `mnrnd`-style stochastic logic in `_static_update` paths |

**All 6 "convergence-green" processes already have stochastic implementations in OC.** The "OC takes the deterministic upper bound; Karr samples below it" mental model is wrong. **Both OC and Karr sample stochastically.** The Day-25 H12 narrative ("closed-form bound dominates → W1=0") was a hand-wavey explanation that fit the W1=0 observation but didn't actually map to OC's code.

What today's stress test ACTUALLY found:
- 3 processes (PFolding, PPI, PPII): OC's output is substrate-insensitive in the tested α range → matches Karr's α=1.0 oracle by virtue of being unchanged
- 3 processes (tRNAAA, Macromol, PTransloc): OC's output IS substrate-sensitive → diverges from Karr's α=1.0 oracle as substrate scales down

What today's stress test did NOT test:
- Does OC's stochastic implementation match Karr's stochastic implementation **at substrate-limited conditions**? We never had a Karr-at-α<1 oracle to compare against. We compared OC-at-α to Karr-at-α=1.

This means the "regime-bounded" label is **conservative-correct but not maximally informative**: we know OC at α<1 differs from Karr at α=1, but we DON'T know whether OC at α<1 differs from a hypothetical Karr at the same α<1.

## 1. Three possible underlying realities

Today's data is consistent with three different underlying realities for tRNAAA / Macromol / PTransloc:

### Reality R1: OC's stochastic implementation is FAITHFUL to Karr's; the test was just answering the wrong question

If true: when we generate a Karr stress oracle at α=0.05, OC at α=0.05 will match Karr at α=0.05. The processes are biology-validated; the "regime-bounded" label drops.

**How to verify:** generate Karr stress oracle (MATLAB pass at scaled substrates) and compare against OC at matched α.

**Cost:** ~50-100 hr MATLAB wall per process × 3 processes (if we extract at 5 alpha values × 50 seeds × 100 ticks) = ~300-500 hr MATLAB total, ~2-4 weeks calendar at a single-seat. Or do a smaller scope: 1 α value (α=0.05) × 50 seeds × 100 ticks per process, ~60 hr MATLAB total, ~3-4 days calendar.

**Outcome if R1 holds:** 3 more cross-regime biology greens (11 → 14 / 20 = 70%), no code change needed.

### Reality R2: OC's stochastic implementation is UNFAITHFUL to Karr's in some way, and the regime-bounded behavior is masking it

If true: when we compare OC-at-α=0.05 vs Karr-at-α=0.05, they still diverge. The OC port has a bug that ONLY manifests under substrate limitation.

**How to verify:** same as R1 (need Karr stress oracle). Then for each divergent process, code-read the MATLAB SUT vs OC port to identify what's different.

**Cost:** same MATLAB + ~1-2 weeks per process port verification + fix.

**Outcome if R2 holds:** port-fix work; eventual biology green after fix. **This is the original "port the inner MC" framing, but the actual fix is "find what's different and fix it" rather than "add the missing MC."**

### Reality R3: OC and Karr are genuinely different but in a *biologically equivalent* way

If true: the difference between OC and Karr at substrate-limited regimes is below the noise floor of any meaningful whole-cell phenotype. The "regime-bounded" label is technically accurate but biologically immaterial.

**How to verify:** run Phase E whole-cell phenotype tests. If phenotypes match Karr within tolerance even though tRNAAA/Macromol/PTransloc differ at the per-tick level, R3 is supported.

**Cost:** Phase E phenotype work happens anyway; this is reactive verification, not proactive cost.

**Outcome if R3 holds:** keep regime-bounded label; document that the regime-boundedness doesn't propagate to phenotype drift; move on.

## 2. What we actually need to design

Given the framing correction in §0 and the 3 possible realities in §1, the design problem is NOT "port the inner MC." It's: **what verification work do we want to do to determine which reality holds?**

Three design options:

### Option A: Generate Karr stress oracles, run comparison, no code work

Author a `scripts/matlab/extract_per_process_traces_stress.m` that mirrors `extract_per_process_traces_v2.m` but:
- Takes an additional `alpha` parameter (1.0, 0.5, 0.1, 0.05, 0.01)
- At each tick, before running the process's `evolveState`, scales the substrate state by α
- Persists the trace per (process, seed, α)

Run for 3 regime-bounded processes × 5 α × 50 seeds × 100 ticks = 750 MATLAB runs ≈ 150-300 hr wall (3-7 days calendar).

Then re-run today's stress harness pattern but comparing OC-at-α vs Karr-at-α (not Karr-at-α=1.0).

**Outcome:** determines R1 vs R2.

**Pros:** clean, empirical, no code changes, generalizes to L2.stress (the future damage-input gate).
**Cons:** MATLAB wall time; needs MATLAB scripting; produces a new oracle class to maintain.

### Option B: Static SUT comparison (read .m vs .py for each process)

For each of 3 processes:
1. Read the Karr `evolveState` MATLAB function end-to-end
2. Read OC's `next_update` end-to-end
3. Identify every RNG draw in each; verify they match in count + distribution
4. Identify every substrate-availability check in each; verify they match
5. Identify the "what to do when substrate is binding" branch in each; verify they match

**Outcome:** identifies R1 vs R2 mechanistically. If they look the same → R1 likely. If different → R2, with specific finding of the difference.

**Pros:** no MATLAB cost; produces a paper-grade "OC faithfully implements Karr's algorithm" claim with citations.
**Cons:** ~1-2 days operator-equivalent per process = 3-6 days; can miss subtle differences that only show up in execution.

### Option C: Defer to Phase E phenotype testing (R3 hypothesis)

Do nothing now. Document the 3 processes as `regime_bounded` in the catalog (done in commit `1a0eb6d`). When Phase E phenotypes are run, observe whether substrate-limited regimes produce divergence. If yes → escalate to Option A or B; if no → R3 confirmed; close the question.

**Pros:** $0 cost now; reactive verification.
**Cons:** if drift shows up at Phase E, diagnosis is harder (more variables in play; harder to attribute drift to a specific process); 4-6 week delay before answer.

## 3. Recommended path

**B → A → (revisit)** sequence:

1. **B first (~3-6 days):** Static SUT comparison for the 3 regime-bounded processes. Cheap; will likely resolve at least one of the three to R1 or R2 confidently. Output: per-process audit document with line-by-line citation of equivalent / divergent code.
2. **A only for the unresolved processes (~3-5 days MATLAB per process):** If Option B is inconclusive for a process, generate the Karr stress oracle and do empirical comparison.
3. **Revisit at Phase E:** If we're still at "regime-bounded" for any process after B+A, treat as R3 hypothesis and revisit when phenotype tests flag specific drift.

Total cost upper bound: **~2-3 weeks calendar** (Option B for all 3 + Option A for whichever stay unresolved). Compared to the original "port the inner MC, 3-5 weeks" estimate, this is similar effort BUT actually verifies the underlying claim rather than reflexively rewriting code.

## 4. Deliverables per option

### Option B deliverables
For each of 3 processes:
- `docs/phase_f/sut_comparisons/<process>_oc_vs_karr_audit.md` — line-by-line SUT comparison
- Verdict: R1 (faithful) | R2 (unfaithful, specific delta) | inconclusive
- If R2: linked todo for the specific fix
- Test: `tests/vivarium/test_<process>_sut_parity.py` if R1 is provable via fixture comparison

### Option A deliverables (per process that needs it)
- `scripts/matlab/extract_per_process_traces_stress.m` (shared across processes)
- New oracle class: `data/m1_sources/karr_native/per_process_traces_stress_alpha{X}_s{SEED}/<Process>_100ticks.mat`
- `tests/vivarium/_substrate_stress/<process>_stress_v3_karr_matched.py` — comparison harness against α-matched Karr oracle
- Verdict per process: R1 (matches Karr at every α) | R2 (diverges at some α, specific divergence documented)
- Catalog update: `closed_form_dominant: confirmed_biology_validated` if R1; `regime_divergence_at_alpha_X` with documented α threshold if R2

## 5. Out-of-scope follow-ups

- **PFolding / PPI / PPII** already confirmed_biology_validated; not in this design's scope.
- **L2.stress** (DNADamage radiation-input gate) is the orthogonal use case that Option A's stress oracle would also enable; mention but don't expand here.
- **pc-t7 chromosome port** is a different scope-gap entirely; this design doesn't touch it.

## 6. Open questions for operator

1. **Option B vs A first?** B is cheaper but may not resolve; A is definitive but expensive. Recommended: B first per §3, but operator may prefer A for empirical certainty.
2. **Karr stress oracle granularity?** Option A could be 5 α × 50 seeds (full) or 1 α × 50 seeds (just α=0.05 as the most-likely-divergent regime). Recommended: 1 α scope first; expand if it shows divergence.
3. **MATLAB seat constraint.** Day-28 lesson: single seat means MATLAB jobs serialize. Option A's ~60 hr wall (1 α scope) = ~3 days clock time. Acceptable?
4. **Phase E sequencing.** If we're 4-6 weeks from Phase E phenotype testing anyway, Option C might be the right call. Operator's Phase E timeline?
5. **Static SUT audit precedent.** Has a Phase-C-era SUT audit been done for any process? (If yes, the audit format exists; if no, we're inventing the deliverable shape too.) Should the audit cite specific SUT files in the Karr v0.7 source tree, or should it cite the MATLAB-class-method-level docstrings?

## 7. Acceptance criteria for this design doc

This doc is RATIFIED iff:
1. Operator picks one of Options A / B / C per §3.
2. Operator answers §6 open questions enough to scope the chosen option.
3. If Option A: pre-flight MATLAB script smoke (1 seed, 1 α) verifies the extract_stress mechanism before launching full extraction (per the Day-28 chromosome-extractor lesson — verify mechanism AND value, not just mechanism).
4. Rubber-duck review surfaces no SHOWSTOPPERs that change the chosen option.

---

*Draft v0.1. Append `## 8. Rubber-duck findings` and `## 9. GPT critique findings` if those rounds are run.*
