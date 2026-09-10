# Preregistration: DNASupercoiling two-sided sparse-support gate

Status: **frozen at commit time below, before the N=200 evaluation run in
STATUS_L22_DNAS_SEPT2.md.**

## Why this preregistration exists

`scripts/l22_dnas_rare_event/sparse_gate.py` (shared Design-A catalog helper;
NOT modified by this preregistration) implements a one-sided sparse-support
gate for the DNASupercoiling `linkingNumbers.delta_nnz` component. Its
`exact_underactivity_pvalue` calls
`scipy.stats.binomtest(k=oc_count, n=oc_count+karr_count, p=0.5,
alternative="less")` on three support axes (`pooled_nonzero_ticks`,
`active_seeds`, `clustered_seeds`). That test can only ever reject OC being
*less* active than Karr. It cannot reject, at any magnitude, OC being *more*
active than Karr.

`STATUS_L22_DNAS_FOLLOWUP8.md` ran the frozen `N=200` gate with that rule and
recorded verdict `PASS`, sparse gate `PASS`, while also recording the support
counts:

- OC pooled/active/clustered `delta_nnz`: `1486 / 200 / 200`
- Karr pooled/active/clustered `delta_nnz`: `65 / 58 / 7`

OC produced nonzero linking-number activity in *every one* of the 200
seed x tick cells that were checked for "active"/"clustered" status, versus
Karr's 58/200 and 7/200 respectively, and ~23x the pooled nonzero-tick count.
The one-sided rule cannot flag this as a failure by construction. That PASS
is explicitly rejected here as not statistically credible and is **not
reused**.

## The new rule

Implemented in `scripts/l22_dnas_rare_event/two_sided_sparse_gate.py` (new
file; does not edit `sparse_gate.py`, `_l2_2_design_a_projections.py`, or any
process/index/catalog file).

**Per axis** (`pooled_nonzero_ticks`, `active_seeds`, `clustered_seeds`,
identical definitions to the shared `support_counts` helper, reused
read-only):

- H0: a pooled support "hit" on this axis is equally likely to be OC's or
  Karr's (`p = 0.5`).
- H1 (two-sided): OC's share differs from `0.5` in either direction.
- Test: exact binomial test,
  `binomtest(k=oc_count, n=oc_count + karr_count, p=0.5,
  alternative="two-sided")`.
- A rejected axis is labeled `OVERACTIVE` if `oc_count > karr_count`,
  `UNDERACTIVE` if `oc_count < karr_count`.

**Multiplicity correction:** Holm-Bonferroni across the 3 axes (same
procedure, same `alpha_family = 0.05`, as the one-sided rule -- only the
per-axis test statistic and resulting labels differ), reusing the shared
`holm_adjust` helper read-only.

**Component verdict** (`linkingNumbers.delta_nnz`):

- `PRIMARY_INSUFFICIENT_SAMPLES` if the pooled total (`oc_count + karr_count`)
  is zero on every axis (no information to test).
- `PRIMARY_OVERACTIVE` if any axis rejects in the `OVERACTIVE` direction (and
  none reject `UNDERACTIVE`).
- `PRIMARY_UNDERACTIVE` if any axis rejects `UNDERACTIVE` (and none reject
  `OVERACTIVE`).
- `PRIMARY_MIXED_UNDER_AND_OVERACTIVE` if axes reject in both directions.
- `FAIL` if all axes pass but the underlying scaled-W1 magnitude metric
  (`per_component_scaled_distance`, shared, unchanged, symmetric) fails.
- `PASS` only if all axes pass Holm-corrected two-sided testing AND the
  magnitude metric passes.

**Process verdict** (`DNASupercoiling`): `FAIL` if the dense
`linkingNumbers.delta_value_sum` magnitude metric fails; otherwise the sparse
component verdict above.

Unlike the one-sided rule, there is **no minimum Karr-support floor**. The
one-sided rule's floor (`min_karr_pooled_nonzero_ticks=31`, etc.) exists only
to keep an underactivity-only claim meaningful when Karr itself has little
support to compare against. A two-sided test needs no such floor to detect
overactivity: Karr support of zero against large OC support is itself the
single clearest possible overactivity signal, and the exact two-sided
binomial test already accounts for its own power at any pooled total > 0.

## Frozen worked examples (computed before the N=200 rerun)

From `scripts.l22_dnas_rare_event.two_sided_sparse_gate.preregistration_examples()`,
applied directly to the FOLLOWUP8 frozen counts above:

- pooled `1486` (OC) vs `65` (Karr): two-sided p-value well below
  `alpha_family / 3 = 0.016667` -> rejects, direction `OVERACTIVE`.
- active `200` (OC) vs `58` (Karr): rejects, direction `OVERACTIVE`.
- clustered `200` (OC) vs `7` (Karr): rejects, direction `OVERACTIVE`.

All three axes reject in the `OVERACTIVE` direction on the FOLLOWUP8 counts,
so this rule would have returned `PRIMARY_OVERACTIVE` (not `PASS`) had it been
applied at that time. This is a preregistered demonstration that the new rule
is capable of catching the specific failure mode the one-sided rule missed;
it is not itself the N=200 evaluation for this task (that evaluation is run
once, after this document and the rule module are committed, against the
current worktree's DNASupercoiling code -- see STATUS_L22_DNAS_SEPT2.md for
the actual result).

## Commit discipline

This document and `scripts/l22_dnas_rare_event/two_sided_sparse_gate.py` plus
its test suite (`tests/scripts/test_l22_dnas_two_sided_sparse_gate.py`) are
committed together, BEFORE the single N=200 evaluation run required by
`PROMPT_SEPT2.md`. The evaluation script and its output are added in a
separate, later commit so the rule definition's git history predates the one
(and only) run of the frozen tensors through it.
