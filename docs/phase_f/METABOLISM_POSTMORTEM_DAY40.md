# Post-mortem: L2.2 Metabolism gap — root causes of the divergence

**Date:** Day-40 (2026-06-26)
**Scope:** Why OpenCell's M1 (Karr metabolism) port produced 17 WIDs of substrate-writeback divergence (W1=161 vs threshold=102) despite passing the original per-reaction oracle 6 months ago.
**Author:** Day-40 session, after building the gap map.

## TL;DR

The gap wasn't caused by a single bug. It was caused by a **chain of design and validation choices** made during the Phase-5 port that each individually looked reasonable but collectively assumed the FBA solve was the deterministic part of metabolism. It isn't. The LP is highly degenerate (cond = 6.7e+12), the writeback algorithm is the actual deterministic part, and we built the port assuming the opposite. By the time we wrote the L2.2 trace-replay test (Day-37), the assumptions were so baked in that ~80% of the divergence appeared as "expected solver noise" rather than as a portability bug.

**The deepest root cause: we ported the LP solve but not Karr's FBA discipline around the LP solve.** Karr's MATLAB does seven specific things before/after `glpkcc(...)` — solver options, scaling, bound clipping, post-clip enforcement, parsimony coefs, internal-exchange handling. Our initial port did ONE of them (the LP call itself) and the rest emerged as gap-driven patches over the months that followed.

## Timeline of the chain

### Decision 1 (Apr 25, commit `ef32f87`): "Pivot to Karr-native FBA"

**What happened:** Replaced an iPS189 (Suthers 2009) model with a Karr-native one. Loaded Karr's S, RHS, lb, ub, obj from the fitted MATLAB snapshot. Built `solve_fba()` using `scipy.optimize.linprog(method="highs")`.

**Choices that locked in problems:**

1. **HiGHS over GLPK** — chosen because scipy ships with it (no extra dep). The commit message doesn't mention "checked that this matches Karr's solver family". This single choice produces ~80% of the current W1 gap (HiGHS picks a different vertex than Karr's GLPK 4.x on the degenerate LP).
2. **`DEFAULT_BIG = 1e3`** instead of Karr's 1e6 (realmax) — chosen because "conversion fluxes typically ≤ 1e3". But Karr's stored fluxes span ±1e6 (LIPASE cycles). The 1e3 choice meant our initial LP didn't even include the cycle behavior; we silently truncated the problem.
3. **Dropped `fbaEnzymeBounds`** — stated reason: "proven inconsistent with stored fluxs (34/504 cols violate by up to 100×)". This was a real observation — but the right response was to investigate why Karr's MATLAB tolerates the inconsistency (post-step values, applied differently), not to drop them entirely. Karr applies them BEFORE the FBA solve as a pre-clip on bounds; we skipped this step.

**Why these passed review at the time:** The per-reaction oracle had threshold `median |log2(predicted/karr_stored)| < 1.0` — i.e., a **2× per-reaction margin** was accepted as PASS. With that loose threshold, all three choices looked harmless: the per-reaction comparison gave 0.96 (just under 1.0) and was called done.

### Decision 2 (subsequent commits, "Bug 4 through Bug 6c"): patches without revisiting

Between the initial port and Day-37, we shipped:
- Bug 4: "karr_metabolism emits substrate production deltas"
- Bug 4 followup: "avoid double-counting M1 writeback"
- Bug 6a Stage 1: "LP writeback to shared substrates (demand keys, positive only)"
- Bug 6a Stage 2: "full LP writeback to mapped cytosol substrates (signed)"
- Bug 6b: "stoichiometric demand-pool headroom caps in M1 LP bounds"
- Bug 6c: "lazy _prev_shared init in KarrMetabolismProcess"

**Pattern:** each "Bug X" was a downstream symptom (substrate counts wrong somewhere). We patched the symptom (add stage to writeback, add headroom cap, etc.) rather than asking "are we porting Karr's algorithm completely?" The patches built up a `S @ v` writeback that was structurally different from Karr's 4-step `evolveState` writeback.

**Why this happened:** we trusted the "per-reaction oracle PASSED" verdict from the initial port. With that prior, downstream divergences looked like "small bugs to patch" not "the writeback algorithm is missing".

### Decision 3 (Day-37, commit `3b4eb0e`): the smoking-gun discovery

When the L2.2 strict rubric ran and produced W1=171.39 for substrates, a diag dive (`diag(metabolism): root-cause L2.2 W1=171.39 — Karr substrate writeback never implemented`) discovered that **Karr's 4-step `evolveState` substrate writeback was never ported at all**. The Bug 4–6c patches had built an entirely different writeback (single-step S @ v).

**This is the structural miss:** Karr's `Metabolism.m:1200-1258` has a specific 4-step + clip algorithm. We never read it during the original port. We inferred a writeback from "what would naturally fall out of the LP" rather than transliterating Karr's algorithm.

### Decision 4 (Day-38): writeback implemented, gap moved sideways

After the Day-37 discovery, we implemented Karr's 4-step writeback. Expected W1 to drop from 171.39 → "much smaller". Actually got 168.39 (1.7% reduction). The writeback algorithm port was correct (verified Day-39: floor = 40 / 148K when fed Karr's flux), but the LP was still feeding it bad flux because we hadn't matched Karr's solver.

### Decision 5 (Day-40, today): the LP solver miss

Today's investigation found:
- The LP cond = 6.7e+12 (numerically degenerate)
- 8 reactions have lb=-inf, ub=+inf (unbounded thermodynamically-infeasible cycles)
- 27 LIPASE-family reactions form a cyclical "free" subnet
- 7 Pyk variants, 5 PfkA variants, 3 Adk variants, 4 Gmk variants are kinetically-equivalent isoforms
- Karr's GLPK 4.x basis happens to favor specific variants; HiGHS/GLPK 5.0 don't

Swapping HiGHS → GLPK 5.0 + presolve=OFF closed 82% of writeback L1 (124,551 → 22,412 per sample). The remaining 22K is structural LP-degeneracy between GLPK 4.x and GLPK 5.0 + alternative pathway choice.

## Root causes (ranked by leverage)

### RC1 — We ported the LP call but not Karr's FBA discipline (highest leverage)

Karr's `Metabolism.m` and `ComputationUtil.linearProgramming` together do these things, in this order:
1. Construct bounds via `calcFluxBounds` (rules 1-5, sometimes 6)
2. Apply `max(lb, -realmax)`, `min(ub, +realmax)`
3. Call `glpkcc(...)` with options `{lpsolver:1, presol:1, scale:1, msglev:0, tolbnd:10e-7}`
4. Check `errFlag` from GLPK status code (specific status interpretation)
5. Apply `max(min(flux, ub), lb)` post-clip
6. Apply 4-step `evolveState` substrate writeback (`Metabolism.m:1200-1258`):
   - Step 1: net stoichiometric production (`S @ v * timestep`)
   - Step 2: stochastic-round to integer counts (uses Karr's MCG16807 RNG)
   - Step 3: compartment distribution (cytosolic vs extracellular split)
   - Step 4: water/proton consolidation
   - Step 5: clip metabolite-row post-state to non-negative

Our initial port did **step 3 (the LP call) only**. Everything else either wasn't ported, was ported with different semantics, or was added later as a patch. The patches were never re-audited against Karr's source.

**Why this is the deepest cause:** treating the LP call as "the FBA" is a category error. The LP call returns one of many degenerate optima; what makes the simulation deterministic is the discipline around the call (solver options + post-clip + writeback algorithm).

### RC2 — Validation threshold was set loose enough to mask the misses

`median |log2(predicted/karr_stored)| < 1.0` is a per-reaction 2× tolerance. With this threshold, you can have:
- A solver picking different vertices: hidden (median is fine because mass conservation holds)
- BIG=1e3 vs 1e6: hidden (the 4 reactions that need 1e6 are outliers, don't move the median)
- Missing writeback steps: hidden (per-reaction comparison doesn't test substrate counts)

A validation threshold that doesn't FAIL on real differences is worse than no validation: it gives false confidence. The initial PASSED verdict was treated as "M1 metabolism ported" through all the subsequent Bug-4 to Bug-6c patches.

**The lesson:** validation thresholds for porting should be set at "bit-match within float-precision" for deterministic parts, and "distribution-match within bootstrap noise" for stochastic parts. **Default to bit-match unless proven otherwise.**

### RC3 — We didn't audit the LP's degeneracy structure before designing the L2.2 trace-replay test

L2.2's design assumes Karr's recorded substrate distributions are canonical "ground truth". For a non-degenerate LP, that's fine. For an LP with cond=6.7e+12 and 8 unbounded cycle dimensions, Karr's "ground truth" is actually "one of many degenerate optima that GLPK 4.x happened to pick on Karr's specific machine".

An LP-degeneracy audit (one probe run) would have shown:
- cond(S) = 6.7e+12
- 8 reactions have lb=-∞, ub=+∞
- Null-space dimension = 128 (504 - 376)
- 6 enzyme variant families (Pyk×7, Adk×3, PfkA×5, Gmk×4, ...)

Any one of those signals would have prompted "wait, is trace-replay the right L2.2 metric?" Instead, we designed the test as if the LP solution was unique, then ran it on Day-37 and started debugging the FAIL verdict.

**The lesson:** before designing a test against a mathematical object, audit the object. For LPs, this means cond, null-space, and bound-finiteness.

### RC4 — Symptom-driven patches without architectural revisit

Bug 4 → Bug 4 followup → Bug 6a Stage 1 → Bug 6a Stage 2 → Bug 6b → Bug 6c is a pattern: each patch was correct for the symptom it addressed, but none asked "are we now diverging from Karr's algorithm overall?"

The Day-37 discovery (writeback never implemented) would have been caught earlier if anyone had compared the call-graph of our `KarrMetabolismProcess._dynamic_update` against Karr's `Metabolism.m::evolveState`. Instead the code path grew organically.

**The lesson:** every time you ship 3+ patches in the same module, do a brief architectural re-audit against the upstream source. Compare call-graphs, not line-by-line.

### RC5 — We didn't know about LP solver-family non-equivalence as a porting risk

This is partially excusable: it's domain knowledge that whole-cell modellers have but software engineers porting code don't necessarily. Karr 2012 itself acknowledges LP degeneracy in the paper but doesn't dwell on it (it wasn't HIS test problem; he had his GLPK 4.x and his trace).

But once we'd picked HiGHS for `scipy.linprog`, we should have run a **single sanity probe**: "solve Karr's published LP, compare to Karr's published flux." That probe would have shown 5.5e+7 flux L1 difference at the initial port. Instead we relied on the median-log2 oracle, which masked it.

**The lesson:** when porting any solver-dependent code, the FIRST test should be exact-input/exact-output replay against the upstream's recorded answer. Not summary statistics; the actual answer.

## What we'd do differently if we restarted the port today

1. **Read Karr's `Metabolism.m` line-by-line first**, before writing any Python. Build a structured call-graph of `evolveState`.
2. **Set up a "Karr's exact answer" smoke test** as the first validation gate: solve Karr's published LP with Karr's exact bounds + objective, compare flux vector element-by-element. PASS only at floating-point tolerance.
3. **Audit LP properties** (cond, null-space, bound-finiteness) and document degeneracy structure before designing any downstream test.
4. **Match Karr's solver family** — GLPK via swiglpk — as the default. Pin solver version in setup.py.
5. **Port Karr's full FBA discipline**: solver options (`presolve=OFF, scale=AUTO, tolbnd=1e-6`), post-clip, 4-step writeback. All seven steps, named and tested individually.
6. **Design L2.2 around invariants**, not trace-replay. Test: "biomass within X%, mass conservation, KS distance <Y for each substrate distribution". Trace-replay can be a SEPARATE regression test, not the primary acceptance gate.

## Process improvements (for other module ports)

Generalizing from this post-mortem to the other 27 Karr processes:

1. **Mandatory upstream-source read-through** before any port. Document the algorithm steps as a call-graph in the design doc. Reviewer must verify call-graph matches upstream.
2. **Mandatory "exact answer" smoke test** as Gate 0 of any port. Bit-match within FP tolerance against published reference. No looser thresholds at this gate.
3. **Mandatory pre-test object audit** for any test built against a mathematical object. For LPs: cond, null-space, bound-finiteness. For ODEs: stiffness, conservation laws. For Markov chains: ergodicity, transition-matrix structure.
4. **Architectural re-audit after every 3rd patch** in the same module. Compare current call-graph to upstream call-graph.
5. **Default validation threshold = bit-match.** Looser tolerances only with documented justification and explicit operator sign-off.
6. **Solver/library pinning** for any module that depends on numerical algorithms. Don't accept "any LP solver" or "any random.seed implementation" — pin exact versions.

## What's still ahead for L2.2 Metabolism

Now that we understand the root causes:
- **Current state**: writeback L1 = 22,412 per sample (vs 124,551 with HiGHS). 82% improvement landed by switching to GLPK + presolve=OFF + Karr's options.
- **Remaining**: 22K is structurally split into 4 clusters (aromatic AA + dipeptides, lipid family, byproducts, carbon backbone) of which we have a per-WID map in `METABOLISM_GAP_MAP.md`.
- **Each cluster** is a separate variant-family or unbounded-cycle problem. Each can be fixed independently with documented intervention.
- **L2.2 metric itself**: even after closing all variant-family gaps, W1 may not reach below threshold if Karr's recorded trace embeds GLPK 4.x-specific basis noise. That's a separate methodological question (RC3 above).
