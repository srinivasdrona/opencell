# DEC-004: Remove Allocator Oversupply Cap (bug A1) — Match Karr evolveState Exactly

**Status:** Prepared, gate-verified, NOT landed (held pending L2.4). Branch `agent/l2-0a-uncap` @ `adf2d1a`.
**Date:** 2026-07-14
**Decision:** Remove the `np.minimum(1.0, counts_scale)` cap in `KarrAllocationStep.next_update` so OpenCell's allocator computes the uncapped proportional share `floor(req · pool / max(1, Σreq))`, bit-matching Karr `Metabolism`/`Simulation` `evolveState.m:36-37`. This resolves chassis-integration bug **A1**.

## Context

`opencell/vivarium/karr_allocation_step.py` capped each process's per-WID allocation at its request via `counts_scale = min(1.0, counts_available / total_demand)`. Karr does **not** cap: in oversupply (pool > total demand) it hands out the full proportional share, which *exceeds* the request; the surplus is returned to the pool downstream because each consumer takes only what it actually consumes.

This is catalogued as chassis bug **A1** (`plan.md`): "OC allocator caps scale at `min(1.0, counts/total_demand)`; Karr's `tmp = counts/max(1, sum_req)` can be >1 (over-allocates surplus)."

The L2.0a allocator-input gate (built 2026-07-14, `scripts/probe_l2_0a_allocator_input.py`) measured this exactly: an honest RED baseline of 111 divergences, **all** in the oversupply-cap fork (`other_fail_count == 0`), concentrated in Metabolism (69) + tRNAAminoacylation (23).

## Decision

Replace:
```python
counts_scale = np.divide(counts_available, total_demand, out=..., where=total_demand > 0.0)
counts_scale = np.minimum(1.0, counts_scale)          # A1 deviation — REMOVED
```
with the Karr-faithful:
```python
counts_scale = counts_available / np.maximum(1.0, total_demand)   # evolveState.m:36-37
```
The `max(1, total_demand)` denominator matches Karr exactly and avoids over-allocation on the fractional sub-1 total-demand edge.

## Safety Argument (audited, not assumed)

Removing the cap raises each process's per-WID allocation *ceiling*. Safety depends on how each consumer turns allocation into the substrate-consumption delta it emits to the shared `substrates` (accumulate) pool. A full read-only audit of all 24 consumers is at `docs/phase_f/A1_ALLOCATOR_UNCAP_CONSUMPTION_AUDIT.md`. Result:

- **AMOUNT class = 0** — no process emits its full allocation as consumption.
- Every consumer enforces `consumption(WID) ≤ allocation(WID)` via one of: `min(biology, allocation)`, a greedy budget loop that stops when the allocation is spent, or a fixed per-event cost gated on `allocation ≥ cost`.

Given that invariant, uncapping is pool-safe by construction:
1. Karr's proportional allocator in oversupply distributes the entire pool: `Σₚ allocationₚ(WID) = pool(WID)`.
2. Each process consumes `≤ allocation`.
3. Therefore `Σₚ consumptionₚ(WID) ≤ Σₚ allocationₚ(WID) = pool(WID)` — the pool never goes negative.
4. Uncapping only raises allocations toward Karr's value; `consume ≤ allocation` is preserved. The sole behavioral change: processes the cap was starving to `request` can now consume up to their true biology — i.e. move **toward** Karr.

This proves **safety** (no over-drain / no pool-negative). It does not by itself prove **correctness** (that OC's biology given Karr's allocation reproduces Karr's per-process consumption) — that is what the L2.1-strict + L2.2 tests verify.

## Gate Verification

- **L2.0a**: RED (111, all oversupply-cap fork) → **403/403 GREEN**, exit 0. Anti-cheat test `test_real_oracle_baseline_is_green_after_uncap` pins the green + coverage (Metabolism/tRNAAminoacylation checked > 0).
- **L2.1 strict rubric**: 28/28 (unchanged).
- **L2.2 strict rubric**: pass (unchanged).
- **Allocator unit tests** (`test_karr_allocation_step.py`, `test_allocator_guards.py`): reconciled to the Karr-faithful uncapped values, with the arithmetic cited inline (e.g. pool=100/demand=80 → scale 1.25 → 37/62, was 30/50 under the cap).

## Why NOT Landed (hold reason)

The uncap cannot land to main standalone. The v6 chassis binds transcription to the **scope-reduced v3** `KarrTranscriptionV3Process` (crude `total_nt/4·dt`, fractional, unrounded — ratified as a chassis-only reduction, `plan.md` Q5). The `min(1.0)` cap was *incidentally* integerizing every oversupplied fractional-demand consumer (because `floor(request) ≤ need` made the integer allocation the binding budget). Uncapped, `consumed = need` = fractional → the shared pool goes fractional → translation's `_coerce_integral_count` rejects it, breaking ~24 integration tests.

A 20-tick blast-radius sweep localized the fractional source to exactly **one** process (transcription v3's NTP consumption). Metabolism, once its Karr-faithful `enable_karr_substrate_writeback` (stochastic-round) path is on, emits integer deltas; all 26 other processes already do.

**This is chassis integer-count integrity, whose proper gate is L2.4 (chassis conservation) — NOT BUILT.** Integer molecule counts are an emergent property of the full stochastic simulation (L2.2+ / chassis), not of the deterministic L2.0a/L2.1 rungs. Landing A1 requires either (a) L2.4 exists to gate the chassis, and/or (b) the chassis transcription integer-count fix (deterministic round now; Karr `stochasticRound` + ACGU sequence composition as a fidelity upgrade). Both are out of scope for the deterministic A1 allocator change.

## Revisit / Land Triggers

- **L2.4 (chassis conservation) is built** — provides the gate that certifies chassis integer-count/mass-balance integrity; A1 can then land with L2.4 green.
- **Chassis transcription integer-count fix lands** (v3 NTP rounding, or chassis switched to faithful v1) — removes the fractional-pool blocker independently.
- If either the audit invariant (`consume ≤ allocation`) is ever violated by a new/changed consumer, re-audit before landing.

## Alternatives Considered and Rejected

- **Keep the cap; reframe L2.0a to measure the pool-delta (downstream) metric instead of raw allocation** — viable and aligns with the "measure in the downstream gate's metric space" principle, but leaves the allocator deviating from Karr and doesn't fix A1. Deferred as a fallback if A1 proves unlandable.
- **Enable Metabolism's stochastic-round writeback in the chassis as the fix** — necessary but insufficient (transcription v3 is the actual tick-0 fractional source, not Metabolism); also introduces stochasticity that does not belong at the L2.0a/L2.1 rungs. Reverted.
- **Relax translation's integer-count check to round** — hides the invariant violation rather than fixing the source; rejected.

## Empirical Foundation

- Root cause proven: cap-removed → 0/203 mismatches vs Karr oracle at sample (0,1); L2.0a full baseline 403/403.
- 24-consumer consumption audit (codex-delegated extraction + Copilot per-row source verification): `docs/phase_f/A1_ALLOCATOR_UNCAP_CONSUMPTION_AUDIT.md`.
- 20-tick chassis blast-radius sweep: only `karr_transcription` (v3) emits fractional substrate deltas.
- Primary source: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m:36-37` (allocation arithmetic); `+process/Metabolism.m:1200-1258` and `+process/Transcription.m:618,897` (per-process `stochasticRound` integerization).

## Related Decisions

- DEC-003 (LP degeneracy / FVA reframe) — Metabolism's L2.2 gate; independent of allocator arithmetic.
- A future decision on chassis transcription fidelity (v3 → v1, or v3 NTP integerization) will be the companion that unblocks landing this one. DEC-003 earmarked "DEC-004" for a Karr-flux-injection methodology that was never written; this record reuses the next free id (004) for the A1 uncap.

## Provenance

- Drafted in Copilot CLI session `5c51d44b-5a9f-4b23-85ff-0fddaadf2212` on 2026-07-14.
- Commits: `adf2d1a` (uncap + tests + audit), `d4f69ef` (plan/status). Branch `agent/l2-0a-uncap`, pushed to origin, not merged.
