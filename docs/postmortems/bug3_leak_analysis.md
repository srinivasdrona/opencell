# GPT-5.5 Independent Root-Cause Analysis (2026-05-24)

Independent cross-check on the substrate cascade. GPT-5.5 was given access to
all diagnostic artifacts but NOT told our hypothesis. Convergence with
Copilot/Claude's analysis was strong on root cause; GPT-5.5 added three keepers:

## Key additional findings beyond Copilot's analysis

### 1. Contract ambiguity (the deepest framing)

> Is `substrates` intended to be a **finite molecular pool**, a **demand
> accumulator**, or a **chemostatted external pool**? The code currently mixes
> these meanings.

This reframes the fix from a tactical patch to an explicit semantic decision.

### 2. Initial-condition bug

All substrates initialize at `1.0` (per `karr_composite.py:1424-1427`) instead
of Karr's biological counts (~10^5-10^6 molecules). Even after fixing the
bypass and the production side, anything consuming >1/tick will still go
negative on tick 1 unless initial conditions are fixed.

### 3. Secondary enrollment-coverage bug

`karr_protein_folding` consumes K, MN, NA in its update but its request
calculator requests 0 for those wids (per
`allocation_requested_vs_consumed_100t.csv:228-231`). Small magnitude, but a
real enrollment-coverage mismatch.

## Methodology validation

GPT-5.5 verified `scripts\diagnose_substrate_leak.py` actually measures what
it claims: monkey-patches every process+step, records returned
`update["substrates"]` deltas, snapshots shared store pre/post, reconciles.
Per-substrate `unattributed_delta = 0` is solid evidence there's no hidden
in-place mutation.

## Confidence summary

- High confidence on root cause (transcription + translation bypass + missing
  M1 production)
- Medium confidence on fix shape (because contract is ambiguous)

## Recommended fix shape (GPT-5.5)

1. **Decide the substrate contract explicitly.** Document in code.
2. If finite-pool: enroll M2/M3 in allocation, add request calculators,
   throttle by grants
3. Independently audit ALL enrolled consumers for negative-delta-vs-request
   mismatches (protein_folding is one; there may be others)
4. Add per-tick regression diagnostics: no substrate goes < 0 unless
   chemostatted

## Open questions (GPT-5.5)

- Should M1 static FBA publish production deltas, or is replenishment
  intentionally `dynamic_bounds=True` + `enable_pool_replenishment=True` opt-in?
- Are M2/M3 fixed rates biologically intended to be throttled, or should pools
  initialize at realistic Karr counts?
- Is `compute_baseline_demand_per_s` still numerically consistent with v3 M2/M3
  mechanisms (it uses `tx.ntp_consumption_per_s` / `tl.aa_consumption_per_s`
  rather than v3 code paths)?
