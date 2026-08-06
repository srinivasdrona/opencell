# DEC-004: MacromolecularComplexation `closed_form_dominant` withdrawn from `confirmed_biology_validated`

**Status:** Active
**Date:** 2026-08-05
**Decision:** `PROCESS_CATALOG.yaml`'s `MacromolecularComplexation` entry's `closed_form_dominant` field is withdrawn from `confirmed_biology_validated` and set to `candidate`. The `evidence_index.json` `SENTINEL_FAIL` this catalog value was propping up (via `verdict.py`'s `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` demotion path) should fall through, on the next coordinator sweep re-run, to an ordinary non-green disposition based on this process's actual `channel_verdicts` — see "Regeneration inputs for `evidence_index.json`" below.

## Context

The catalog's prior value (set 2026-06-16, at merge `3deae19`) read:

> `closed_form_dominant: confirmed_biology_validated  # 2026-06-16 REVALIDATED. L2 replay PASS + stress α=1.0 exact match (97/97, W1=0). One-copy-per-iteration fix at 3deae19. Stress α<1 divergence is input-mismatch (OC-at-α vs Karr-at-α=1), not algorithm — same pattern as tRNAAA.`

That value drove `scripts/l22_evidence/verdict.py`'s `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` demotion attempt, which requires a machine-checked `h12_evidence_ref` at verdict `H12_CONFIRMED` to succeed; this process's actual H12 artifact verdict is `H12_OBSERVED_REGIME` (network 2's competitive branch is Monte Carlo by construction — `buildProteinComplexs_montecarlokinetic` draws `randStream.rand()` every iteration, `MacromolecularComplexation.m` lines 334-357), so the demotion has been rejected and the row has surfaced as `SENTINEL_FAIL` in `evidence_index.json` rather than either a genuine PASS or an honest ordinary FAIL.

Two rounds of investigation this branch (`agent/l22-macromol-closure-20260805`, base `3ad6a21`) confirm the catalog value itself, not just its evidence wiring, is unsound:

1. **Network 2 is stochastic, not closed-form, by construction** (§4 of `docs/phase_f/l2_2_design_a/h12/MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md`; static-source fact, independent of any Monte Carlo trial outcome).
2. **The natural 50-seed × 100-tick population never exercises network 2's competitive branch at all** — E1 (`MG_429_MONOMER`) is fixture-constant zero across all 5,000 accepted (seed × tick) samples in that window (§2 of the same doc), so the `closed_form_dominant` claim's own supporting evidence (`stress α=1.0 exact match 97/97`) never actually walks the Monte Carlo competition path for network 2; it is evidence about network 1's deterministic branch only, mislabeled as covering the process as a whole.
3. **A corrected full-natural-lifecycle probe (this branch) empirically confirms network 2 IS naturally reachable later in the cycle** (real, unmodified `sim.evolveState()` scheduler, seed 0, no conditioning) — see §5 of the same doc for exact tick/event numbers. This directly falsifies any reading of `confirmed_biology_validated` that would imply network 2's Monte Carlo branch is inert/inapplicable in practice for this process's natural population; it is very much active once the natural cycle runs long enough, and it is exactly the stochastic branch that `closed_form_dominant` claims is not dominant.

`closed_form_dominant: confirmed_biology_validated` is therefore not merely awkwardly wired into the verdict machinery — its underlying claim (that a closed form dominates this process's primary-channel behavior) does not hold for the naturally-reachable, actually-exercised network≥2 competitive branch. The correct catalog value for a process with a real, naturally-reachable, irreducibly-stochastic branch feeding its primary channel (`complexs`) is `candidate` (unresolved / not evidenced as dominant), not `confirmed_biology_validated`.

## Decision

Change `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`'s `MacromolecularComplexation` entry:

```yaml
closed_form_dominant: candidate  # 2026-08-05 WITHDRAWN from confirmed_biology_validated; see dec-004.
```

The inline `notes` field is updated to record this withdrawal alongside the prior revalidation history (append-only, not deleted) so the field's full history remains auditable in-place.

## Arguments For

1. **Matches the actual evidence.** Network 2's competitive branch is Monte Carlo by construction (static source fact) AND naturally reachable later in the cell cycle (this branch's corrected full-lifecycle probe) AND never exercised in the accepted N=50 short-window population (prior finding). None of these three facts support "closed form dominant, confirmed."
2. **Removes a broken evidence-gate wiring without touching `verdict.py` or `evidence_index.json`.** The catalog is the correct, coordinator-owned-adjacent place to fix this: it is the actual source of the false claim that a re-run sweep would otherwise keep trying (and keep failing) to use for a `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` demotion.
3. **Honest non-green beats an unresolved `SENTINEL_FAIL`.** `SENTINEL_FAIL` is a distinct, load-bearing signal that a *demotion attempt failed its own evidence check* — it is not itself an honest description of this process's real disposition. Removing the unsound catalog claim should let a re-run sweep fall through to this process's real `channel_verdicts` (all three recorded as `SEED_NOISE` in the current `evidence_index.json` entry), landing on an ordinary non-green status, not a special-cased sentinel.
4. **No waiver.** This is not a `DEFERRED`/known-gap waiver — it is a correction of a specific, now-falsified factual claim (`confirmed_biology_validated`), backed by new, hash-bound, machine-checked evidence (`docs/phase_f/l2_2_design_a/h12/lifecycle_reachability/MacromolecularComplexation_h12_lifecycle_reachability.json`).

## Arguments Against (and rejected reasons)

1. **"The 2026-06-16 stress-test evidence (97/97 exact match) is real and shouldn't be discarded"** — Counter: it is not discarded; it remains true evidence about network 1's deterministic branch (145 of 147 complexes, the `network==1` closed-form path). The correction here is narrower: that evidence does not extend to network 2's Monte Carlo branch, and `closed_form_dominant` is a whole-process-primary-channel claim, not a network-1-only claim. The notes field is updated to make this scope explicit, not to delete the prior finding.
2. **"This regresses a previously-green row to non-green"** — Counter: the row was already `SENTINEL_FAIL`, not green, before this change (confirmed via `evidence_index.json`, `docs/phase_f/l2_2_design_a/h12/`). This decision does not create a regression; it replaces an unresolved sentinel with an honest disposition once the coordinator sweep is re-run.

## Revisit Triggers

- A future `tick_offset>0` re-extraction of the accepted N=50 natural population (not yet authorized/performed) that shows network 2 firing within a revised M-tick window for a majority of seeds, changing the "never exercised in N=50" premise.
- A structural change to `buildProteinComplexs_montecarlokinetic` that removes its `randStream.rand()` dependency (would need independent re-verification, not assumed here).
- The coordinator's re-run sweep produces a disposition other than the predicted ordinary non-green fallthrough — the prediction in "Regeneration inputs" below is reasoned, not verified against live coordinator tooling, and must be corrected here if the real sweep output differs.

## Alternatives Considered and Rejected

- **Route through `DEFERRED`/a known-gap waiver** — explicitly forbidden by the user for this task; also would not correct the underlying false catalog claim, just hide it.
- **Edit `evidence_index.json` directly** — forbidden (coordinator-owned, externally regenerated; no local script in this repo produces its warning/verdict text, confirmed by exhaustive grep of `scripts/l22_evidence/`).
- **Leave `closed_form_dominant` unchanged and instead patch `verdict.py`'s demotion logic to special-case this process** — would hide the same false claim behind a code-level carve-out instead of correcting it at the source; rejected as evidence-laundering.

## Empirical Foundation

- `docs/phase_f/l2_2_design_a/h12/MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md` §2-§5 (fixture-constant-zero natural population; Monte Carlo static-source argument; corrected full-lifecycle probe results).
- `docs/phase_f/l2_2_design_a/h12/lifecycle_reachability/MacromolecularComplexation_h12_lifecycle_reachability.json` (machine-checked, hash-bound; NON-GATING).
- `docs/phase_f/l2_2_design_a/h12/MacromolecularComplexation_h12.json` (accepted N=50 natural census; verdict `H12_OBSERVED_REGIME`, not `H12_CONFIRMED`).
- `scripts/l22_evidence/verdict.py` (`PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` / `DETERMINISTIC_CONVERGENCE_PREFIX` demotion-rejection logic that currently surfaces as `SENTINEL_FAIL`).

## Implementation

- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`: `MacromolecularComplexation.closed_form_dominant` changed `confirmed_biology_validated` → `candidate`; notes appended, not replaced.
- This decision file + `decisions/_decision_index.yaml` entry.

## Regeneration inputs for `evidence_index.json` (coordinator-facing; NOT executed here)

`docs/phase_f/l2_2_design_a/evidence_index.json` is externally, coordinator-owned-regenerated; no script in this worktree produces its per-row warning/verdict text, so this decision does not and cannot edit it directly. For the coordinator's next sweep re-run over this catalog:

- **Input changed:** `PROCESS_CATALOG.yaml`'s `MacromolecularComplexation.closed_form_dominant` is now `candidate`, not `confirmed_biology_validated`.
- **Predicted effect (reasoned, not verified against live coordinator tooling):** the `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` demotion path in `verdict.py` should no longer be attempted for this row (its trigger condition is the catalog's `closed_form_dominant` reading as a `confirmed*` value), so the `SENTINEL_FAIL` reason currently stored for this process should not recur. The row should instead resolve via its ordinary `channel_verdicts` (`SEED_NOISE` on all three channels per the current `evidence_index.json` entry), landing on `verdict.py`'s ordinary `STATUS_FAIL` disposition (`schema.py::STATUS_FAIL = "FAIL"`) rather than a sentinel-classified row.
- **This prediction is explicitly flagged as a well-reasoned regeneration input for the coordinator, not a verified fact** — the actual coordinator sweep/runner that produces `evidence_index.json` is not present in this worktree and was not run as part of this decision.

## External Review Context

- Opus review (BLOCKING) on this branch's first pass identified that the prior `closed_form_dominant: confirmed_biology_validated` value was never actually falsified at source when the first-pass artifact was built, and required this withdrawal to be routed through a structured decision (this file), not a `DEFERRED` waiver.

## Related Decisions

- None prior specific to this process; this is the first catalog-field-level decision for `MacromolecularComplexation`.

## Provenance

- Drafted in Copilot CLI session on 2026-08-05, worktree `E:\opencell-worktrees\l22-macromol-closure-20260805`, branch `agent/l22-macromol-closure-20260805`.
- Corrected full-natural-lifecycle MATLAB probe (`scripts/matlab/full_cycle_event_scan_macromol.m`) run for real (seed 0, real `sim.evolveState()` scheduler) to produce the evidence cited above.
