# L2.4 Chassis Autonomous Conservation Gate — Design

**Status:** DESIGN (drafted 2026-07-08, Day-48). Gate NOT yet built.
**Ladder position:** L2.4 — runtime, 28 processes × ≤100 ticks, **NO Karr oracle
at process outputs** (plan.md L-ladder line 43). Sits after L2.1/L2.2
(per-process) and before L2.5 (shared-pool composition), because L2.5
misattributes composition failures unless the chassis wiring is conservation-
proven first (plan.md line 41; was named "L1c" before the 2026-07-02 relocation).
**Format:** follows the landed L1b gate design doc
(`docs/phase_f/L1B_WIRING_CONFORMANT_GATE.md`).

---

## DAP Intent (Slot 1)

**Beat 1 — Contract.** Run the full 28-process chassis autonomously (no Karr
trace injection) for ≤100 ticks and assert mass conservation at each accounted
tick: for every (substrate WID, compartment), the measured change in the shared
pool equals the net of what all processes wrote — `Δpool == Σ_p (produced − consumed)`.
Done = a deterministic per-(WID, compartment) conservation verdict with zero
unattributed delta, aggregated to a PASS/FAIL gate, over a seed sweep.

**Beat 2 — Surface.**
- Read: `opencell/vivarium/karr_composite.py` (`build_karr_chassis_v6`, the
  28-process engine); `scripts/run_chassis_v6_32400t.py` (existing conservation
  PROTOTYPE — `per_tick_process_sums`, before/after snapshots,
  `max_abs_unattributed_delta`, lines ~349-353, 603-668, 774-776);
  `opencell/core/resource_ledger.py` (PARTITION-EVOLVE-MERGE mass-conservation
  rationale); `tests/vivarium/test_mass_balance_invariants.py`.
- Write: `scripts/l2_4_verify_conservation.py`, a report artifact, this doc.
- Suspect patterns: (a) `project_to_flat_per_wid` merges compartments (A4) —
  a compartment-summed check would hide it; (b) `enable_pool_replenishment`
  (build_karr_chassis_v6 param) injects external inflow — masks leaks as supply.

**Beat 3 — Expected outcome.** Distinguishing command:
`bin\oc-py scripts/l2_4_verify_conservation.py --ticks 100 --seeds 0,1,2,3`.
Expected: per-tick, per-(WID, compartment) `unattributed_delta` values; PASS only
when every value is exactly 0 across all ticks and seeds; exit 0 iff so. Smallest
reachable state: `build_karr_chassis_v6(seed=…)` fresh chassis → Vivarium
`Engine` → step 100 ticks → per-tick conservation accounting.

**Beat 4 — Invert (pre-mortem).**
- **Compartment-merge false-pass (A4):** summing pool deltas over compartments
  makes a molecule moved cytosol→membrane net to zero, hiding a real
  compartment-conservation break. Guard (D4): the invariant is per
  (WID, *compartment*), never compartment-summed.
- **Single-seed false-pass (A2):** Karr picks a *random* process order each tick
  (`randperm`, evolveState.m:48-57); OC uses a fixed order (karr_composite.py).
  An order-dependent double-spend can conserve under one order and leak under
  another. Guard (D5): sweep ≥4 seeds; a conservation break under ANY seed FAILs.
- **Replenishment false-pass (A1):** if `enable_pool_replenishment=True`, a
  process that writes via a bypass path the accounting doesn't see (A1) is
  masked because external inflow refills the pool. Guard (D2): closed system,
  replenishment OFF.
- **Tolerance false-pass:** a float tolerance hides 1-molecule integer leaks.
  Guard (D3): integer-exact, tolerance 0.

**Beat 5 — Act, then verify.** Build the gate + a synthetic self-test that plants
a known leak (a process that writes a substrate without the accounting seeing it)
and asserts the gate FAILs it, and a compartment-move test that asserts the
per-compartment check catches it while a compartment-sum would not; then run the
real chassis and record the honest verdict (which may be RED on A1/A2/A4 — that
is the gate doing its job, not a defect).

**PM sanity-check.** This design assumes the chassis can run 28 processes × 100
ticks autonomously (no Karr injection) and that the existing
`run_chassis_v6_32400t.py` conservation accounting is correct enough to lift into
a gate; if the 100-tick autonomous run is not stable (e.g. a process explodes
before tick 100), the gate scope must drop to the max stable tick and that
becomes a separate stability finding.

---

## Spec Authority Quote Block

The conservation identity (the physics L2.4 enforces): for a closed system, the
shared metabolite pool changes ONLY by what processes produce/consume. Per tick,
per (WID, compartment):

```
Δpool[wid, compartment]  ==  Σ_processes ( produced − consumed )[wid, compartment]
⇔  unattributed_delta  ==  0
```

Prototype already in the tree (`scripts/run_chassis_v6_32400t.py`): it snapshots
substrates `before`/`after` at `conservation_stride`, accumulates
`per_tick_process_sums[wid] += delta` over substrate writes (lines 349-353), and
reports `max_abs_unattributed_delta` (lines 774-776). L2.4 formalizes this into a
per-(WID, compartment), integer-exact, seed-swept, blocking gate.

The A1-A4 wiring bugs L2.4 is built to catch (grounded in the per-process
semantic audits, `docs/phase_f/audits/*_semantic_audit.md`):
- **A1** — allocator-participation mismatch: a process consumes/produces via a
  *bypass* path outside the allocator accounting (e.g. DNARepair AMET/AHCYS/H
  bypass; Metabolism request-formula vs allocation). Shows as unattributed delta.
- **A2** — ordering/scheduler mismatch: Karr randomizes process order each tick
  (`randperm`, constraint tRNAAminoacylation-before-Translation,
  evolveState.m:48-57); OC uses fixed order. Order-dependent double-spend shows
  as seed-dependent conservation breaks.
- **A3/A3b** — formula/source + consumption-clipping mismatch (LP bounds source,
  byproduct emission, clipping).
- **A4** — projection/compartment-merge mismatch: `project_to_flat_per_wid`
  merges compartments; a per-compartment conservation check exposes it.

---

## 1) Design Contract

- **Required behavior:** an autonomous, oracle-free runtime gate that proves the
  28-process chassis conserves mass — every substrate the pool loses/gains is
  exactly attributable to process production/consumption, per compartment, every
  tick, under multiple process orderings (seeds).
- **Why this matters:** L2.1/L2.2 validate each process against Karr *in
  isolation* (single-process replay). They are structurally blind to
  *integration* bugs — a process that bypasses the allocator (A1), a scheduler
  order divergence (A2), or a compartment-merging projection (A4) only manifests
  when all 28 run together on the shared pool. L2.4 is the first gate that
  exercises the integrated wiring, and it needs no Karr output oracle because
  mass conservation is a physics law, not a Karr-specific number.
- **Done = property:** for all 28 processes, all ≤100 ticks, all swept seeds,
  every (WID, compartment) has `unattributed_delta == 0` (integer-exact).

---

## 2) Inventory of Existing Artifacts

- [A01] `opencell/vivarium/karr_composite.py` `build_karr_chassis_v6` | code |
  the 28-process Vivarium engine builder; `enable_pool_replenishment` param
  (must be False, D2); fixed process/step order (the A2 surface).
- [A02] `scripts/run_chassis_v6_32400t.py` | code | conservation PROTOTYPE to
  lift: `per_tick_process_sums` (attributed writes), before/after substrate
  snapshots, `max_abs_unattributed_delta`. Reuse its accounting; scope to 100
  ticks + per-compartment + seed sweep + gate semantics.
- [A03] `opencell/core/resource_ledger.py` | code | documents the
  PARTITION-EVOLVE-MERGE conservation model ("ensures mass conservation and
  prevents double-counting") — the conceptual contract.
- [A04] `tests/vivarium/test_mass_balance_invariants.py` | test | existing
  mass-balance test style to extend.
- [A05] `docs/phase_f/audits/*_semantic_audit.md` | doc | authoritative A1-A4
  per-process definitions (DNARepair, Metabolism, Translation, ProteinFolding).
- [A06] `opencell/vivarium/karr_allocation_step.py` | code | the allocator whose
  per-tick division must net-conserve (L2.0a proves its arithmetic; L2.4 proves
  it conserves in the integrated run).

Inventory Beat-4 inversion: the prototype accounts only substrate writes whose
`store_path[0] == "substrates"` (run_chassis_v6_32400t.py:352); a process that
writes substrates through a different store path would be invisible. Risk
reduction: D6 enumerates all substrate-affecting store paths and asserts the
accounting covers every process's write surface (cross-check against the L1b
wiring rows' produce/consume WIDs).

---

## 5) Decision Ledger

**D1 — The invariant.**
- Chosen: per-tick, per-(WID, compartment) **integer-exact** conservation:
  `Δpool == Σ_p net_write`, i.e. `unattributed_delta == 0`. Rejected: aggregate
  "max_abs over the run" as the only signal (hides which WID/tick/process; keep
  it as a summary but fail per-cell).
- Falsifier: any legitimate non-conserving source (a true external exchange
  reaction) would break exactness — those belong to Metabolism's exchange flux
  and must be modeled as explicit pool boundary terms, not silent leaks (D2).

**D2 — Closed system (no replenishment).**
- Chosen: `enable_pool_replenishment=False`. Conservation is only checkable in a
  closed system; external inflow masks leaks (Beat-4 A1 false-pass). If
  Metabolism's exchange fluxes are genuinely open-boundary, they are accounted as
  an explicit, enumerated boundary term — NOT folded into "unattributed".
- Falsifier: if the chassis cannot run ≤100 ticks with replenishment off (pool
  depletes and a process errors), reopen with a documented minimal boundary set.

**D3 — Tolerance = 0 (integer-exact).**
- Chosen: counts are integers; conservation is exact. No float tolerance. A
  1-molecule unattributed delta is a FAIL (it is exactly the S3-class
  1-molecule bug that L2.1 flagged).

**D4 — Compartment-resolved (never merged).**
- Chosen: the invariant key is (WID, *compartment*). A compartment-summed check
  is FORBIDDEN — it is the A4 false-pass (a molecule moved between compartments
  nets to zero in the sum). This directly targets `project_to_flat_per_wid`.
- Falsifier: if compartments are genuinely indistinguishable for a WID at
  runtime, document why; otherwise per-compartment stands.

**D5 — Seed sweep (expose A2).**
- Chosen: run ≥4 seeds; the process-order/scheduler divergence (A2) is
  seed/order-dependent, so a single seed can conserve while another leaks. A
  conservation break under ANY seed FAILs the gate. (Note: OC uses fixed order;
  the seed sweep varies stochastic process internals, and — if/when OC adopts
  Karr's `randperm` order — the order too. Document which is varied.)
- Falsifier: if all processes are order-independent at the pool level, the sweep
  is redundant (still cheap insurance).

**D6 — Attribution + write-surface coverage.**
- Chosen: on failure, attribute the unattributed delta to the offending
  (process, WID, compartment, tick) and classify A1 (bypass write not accounted)
  / A2 (seed-variance) / A4 (compartment). Cross-check the accounting's covered
  write surface against the L1b wiring rows' declared produce/consume WIDs so no
  process's substrate writes are silently outside the ledger.

**D7 — No output oracle.**
- Chosen: L2.4 reads NO Karr process-output trace. Its only oracle is the
  conservation identity (physics). This is what lets it run at 28×100 without the
  per-process Karr fixtures and what makes it the integration gate L2.1 cannot be.

---

## 10) Self-Audit (slot-3 mapping)

| Beat-4 failure mode | Guard | Where enforced |
|---|---|---|
| A4 compartment-merge hidden by summing | D4: per-(WID, compartment) key | invariant key |
| A2 order double-spend hidden by 1 seed | D5: ≥4-seed sweep, any-fail | run matrix |
| A1 bypass leak masked by inflow | D2: replenishment OFF (closed) | chassis config |
| 1-molecule leak under float tolerance | D3: integer-exact, tol 0 | comparison |
| Process writes outside the ledger surface | D6: write-surface coverage vs L1b rows | accounting audit |
| "Looks conserved overall" aggregate-only | D1: per-cell fail, not just max-abs | verdict granularity |

**Open items (build-time, need WSL — currently BLOCKED, WSL down):**
1. Confirm the chassis runs 28 procs × 100 ticks autonomously with
   replenishment OFF (stability); if not, set scope = max stable tick.
2. Lift + generalize `run_chassis_v6_32400t.py` conservation accounting to
   per-compartment and confirm the covered write surface is complete (D6).
3. Decide the explicit open-boundary term set for Metabolism exchange (D2).

## Build sequence (once WSL restored)
1. Stability probe: `build_karr_chassis_v6(enable_pool_replenishment=False)`,
   step 100 ticks, seed 0 — does it complete? Record max stable tick.
2. Implement `scripts/l2_4_verify_conservation.py`: per-tick, per-(WID,
   compartment) accounting lifted from the prototype; integer-exact; seed sweep.
3. Synthetic self-tests: planted leak → FAIL; compartment-move → per-compartment
   FAILs, compartment-sum would not (prove D4).
4. First real run: record honest verdict; attribute failures to A1/A2/A4.
5. A4 + A3b localized fixes once L2.4 instruments them (plan.md line 134).
6. CI: add as a blocking job (HB6 pattern) once green.
