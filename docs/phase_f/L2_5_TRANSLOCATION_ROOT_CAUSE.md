# L2.5 EOD update — Day-35 Translocation root cause (REVISED)

**Status:** Day-35 EOD investigation IDENTIFIED the composition-time enzyme-port
contamination but **the speculative single-port-read fix did NOT move the
scoreboard**. The actual bug is more subtle and needs Day-36 focused work.

## What was confirmed

Instrumented diagnostic at tick 21 for ProteinFolding+ProteinTranslocation
(via `L25_DIAG_PAIR=Folding+Translocation` env-gated prints in the harness):

- `protein.enzyme_counts` in composition has 3 nonzero from Folding's overlay:
  `{MG_238_MONOMER: 46, MG_305_MONOMER: 32, MG_297_MONOMER: 16}`
- `MG_297_MONOMER` IS Translocation's `srp_receptor_wid`
- `top-level state.enzymes` has ALL 4 Translocation Sec/SRP wids non-zero:
  `MG_0001_048: 29 (srp), MG_297_MONOMER: 16 (srp_recv),
  MG_072_DIMER: 13 (translocase_atpase), MG_055_..._20MER: 13 (translocase_pore)`
- `substrates_allocated[Translocation]` post-allocator-refresh:
  `{ATP: 215, H2O: 1941651}` — plenty of budget

These three together explain why Translocation in composition produces 14
ATP hydrolyses (4 proteins × ~3.5 ATP avg = 14).

## What was attempted and why it didn't work

**Speculative fix**: change `_enzyme_remaining` in Translocation to read from
`state["enzymes"]` (canonical port) instead of `protein.enzyme_counts`.

**Result**: SS scoreboard unchanged (7 PASS / 15 FAIL / 34 SKIP). The fix was
**reverted**.

**Why it doesn't help**: in composition mode, `state["enzymes"]` is ALSO
populated with non-zero values (Folding's overlay + Translocation's overlay).
Reading from a different port that contains the same contaminated values
gives the same result.

## What's actually happening

L2.1 passes for Translocation despite my fix because some OTHER guard in
`next_update` returns early in L2.1. Three candidates:

1. **ATP/H2O guard** (line 355): `if atp_remaining <= 0 or h2o_remaining <= 0: return {}`.
   If L2.1's allocator gives Translocation 0 ATP (allocator behavior depends on the
   state-overlay history), this trips.
2. **Cytoplasmic queue empty** (line 338): `if not cytoplasmic_counts: return {}`.
   Depends on whether L2.1 has `protein.unprocessed_counts` populated.
3. **Total copies zero** (line 349): same family.

The composition harness, by overlaying upstream Folding's deltas + the H6
upstream-mutation-preservation logic, may be presenting a more-populated state
to Translocation than L2.1 ever does. This makes Translocation's biology fire
events that simply never had the inputs in L2.1.

The "fix" is not in Translocation's code — it's in understanding why
**Karr's MATLAB Translocation at tick 21 produces 0 events** with the same
input state. Either:
- Karr's MATLAB allocator gave Translocation 0 ATP at tick 21 (allocator
  contention with other processes Karr ran in parallel)
- Karr's MATLAB Translocation has additional state we're not modeling
- The OC port doesn't match Karr's algorithm for the rate-limiting step

## Real diagnostic next step (Day-36)

Instrument BOTH L2.1 AND composition at tick 21 with the same diagnostic
prints. Compare:
- `state["substrates"]` content (ATP, H2O, ...)
- `state["enzymes"]` content (all Sec/SRP wids)
- `state["substrates_allocated"]["karr_protein_translocation"]` post-refresh
- `cytoplasmic_counts` after the location/queue filtering
- The first exit point in `next_update` (line 339 vs 350 vs 356)

If L2.1 exits at line 356 (`atp_remaining <= 0`) and composition exits at
the end (does work), the bug is **allocator-driven**: composition gives
Translocation a larger ATP budget than Karr did at tick 21.

If L2.1 exits at line 339 (empty queue) and composition has non-empty queue,
the bug is **queue-population**: upstream Folding's overlay contaminates
`protein.unprocessed_counts` or `protein.location`.

This 30-min focused probe will give the answer and the next fix direction.

## Honest scoreboard

**Unchanged from Day-35 morning** post-Day-35-fix-1 (hidden_read_surface):
- 15 PASS / 46 FAIL / 41 SKIP across 102 wired (of 256 in-scope)
- 7 PASS / 15 FAIL / 34 SKIP across 56 SS clean × clean

The hidden_read_surface fix is correct and lands in plan. The Translocation
speculative fix was reverted. No regression introduced today.

## Findings updated

- ✅ Finding 1 (FIXED): hidden_read_surface contract gap — committed `02bb267`
- 🔬 Finding 2 (PARTIALLY CHARACTERIZED): ProteinTranslocation composition
  drift — confirmed contamination is in enzyme-port reads, but single-port
  fix doesn't help because state.enzymes is also contaminated. Need
  allocator-vs-queue binary search at tick 21 (Day-36 ~30 min probe).
- 🔬 Finding 3 (UNCHANGED): DNARepair 1-event drift plausibly stochastic
  variance — needs ensemble or rubric review.
- 🆕 Finding 4 (NEW): The "L2.1 passes by coincidence" pattern is real and
  may generalize. Translocation's L2.1 expects 0 events at tick 21, and OC
  trivially produces 0 (some early-return guard trips). Composition exposes
  that the early-return condition is fragile.

## Methodology lesson

The rubber-duck critique (Sonnet 4.6) correctly identified:
- B1: my standalone probe was missing H6 logic. Switched to harness-direct
  instrumentation (correct call).
- B2: substrate contamination hypothesis (partial; correct shape, wrong
  port — it's enzyme contamination, not substrate H6).
- B3: counterfactual coincidence is structural. The PASS audit
  (`scripts/probe_pass_audit.py`) showed 8 of 14 testable PASSes are
  GENUINE (both sides active), 6 are SINGLE-SIDE (Seg inactive, partner
  active), 0 are COINCIDENTAL. So current 15 PASSes ARE real validations.

The critique was right on direction (substrate contamination is structurally
the bug) but the specific port being contaminated is enzyme, not substrate.
