# L2.4 Chassis Autonomous Conservation Gate — Design

**Status:** DESIGN (drafted 2026-07-08, Day-48; **revised same day after gpt-5.4
design review** — scope corrected, see review log). Gate NOT yet built.
**Scope (review-corrected):** **v1 catches A1** (allocator-bypass / unaccounted
substrate leaks) via flat-per-WID integer-exact conservation with a fail-closed
write-surface audit. **A4 (compartment merge) and A2 (process-order/randperm)
are OUT of v1 scope** — the current OC runtime is flat-per-WID (no compartment
ledger) and fixed-order (no `randperm`), so neither is observable without new
instrumentation; both are named v2 prerequisites (D4, D5). The first draft
overclaimed "catches A1-A4"; that is corrected here.
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
tick: for every substrate WID (flat, v1 — see D4), the measured change in the
shared pool equals the net of what all processes wrote —
`Δpool == Σ_p (produced − consumed)`. Done = a deterministic per-WID
conservation verdict with zero unattributed delta (excluding the documented
open-boundary exchange WIDs, D2), aggregated to a PASS/FAIL gate, over a seed
sweep.

**Beat 2 — Surface.**
- Read: `opencell/vivarium/karr_composite.py` (`build_karr_chassis_v6`, the
  28-process engine); `scripts/run_chassis_v6_32400t.py` (existing conservation
  PROTOTYPE — `per_tick_process_sums`, before/after snapshots,
  `max_abs_unattributed_delta`, lines ~349-353, 603-668, 774-776);
  `opencell/core/resource_ledger.py` (PARTITION-EVOLVE-MERGE mass-conservation
  rationale); `tests/vivarium/test_mass_balance_invariants.py`.
- Write: `scripts/l2_4_verify_conservation.py`, a report artifact, this doc.
- Suspect patterns: (a) `project_to_flat_per_wid` merges compartments (A4) — the
  runtime is already flat-per-WID, so v1 CANNOT see A4 (D4, scoped out);
  (b) `enable_pool_replenishment` (build_karr_chassis_v6 param) injects external
  inflow — masks leaks as supply (D2).

**Beat 3 — Expected outcome.** Distinguishing command:
`bin\oc-py scripts/l2_4_verify_conservation.py --ticks 100 --seeds 0,1,2,3`.
Expected: per-tick, per-WID `unattributed_delta` values (flat; exchange WIDs
excluded); PASS only when every value is exactly 0 across all ticks and seeds;
exit 0 iff so. Smallest reachable state: fresh chassis → Vivarium `Engine` →
step 100 ticks → per-tick flat-WID conservation accounting. (Note: seed varies
stochastic internals only; `build_karr_chassis_v6` has no seed-order param — D5.)

**Beat 4 — Invert (pre-mortem). [scope corrected post-review]**
- **Replenishment false-pass (A1) — v1 GUARDS this:** if
  `enable_pool_replenishment=True`, a process that writes via a bypass path the
  accounting doesn't see (A1) is masked because external inflow refills the pool.
  Guard (D2): closed system, replenishment OFF, + exclude the 124 exchange WIDs.
- **Uncounted write-path false-pass (A1) — v1 GUARDS this:** a substrate effect
  through a store path the ledger doesn't count is silently missed. Guard (D6):
  FAIL-CLOSED write-surface audit hard-fails any write outside the inventory.
- **Tolerance false-pass — v1 GUARDS this:** a float tolerance hides 1-molecule
  integer leaks. Guard (D3): integer-exact, tolerance 0.
- **Compartment-merge (A4) — v1 CANNOT guard (documented blind spot):** a
  molecule moved cytosol→membrane nets to zero. The OC runtime is already
  flat-per-WID (M1 `sum(axis=1)`, karr_metabolism_writeback.py:164-174), so v1
  physically cannot observe compartments. A4 needs a compartment ledger (D4, v2).
- **Order-divergence (A2) — v1 CANNOT guard (documented blind spot):** Karr's
  `randperm` order (evolveState.m:48-57) vs OC's fixed order. OC has no
  seed-varied ordering, so v1 cannot exercise A2 (D5, v2).

**Beat 5 — Act, then verify.** Build the gate + a synthetic self-test that plants
a known flat-WID leak (a process that writes a substrate without the accounting
seeing it) and asserts the gate FAILs it, plus a fail-closed-audit test (a
substrate write on an unlisted store path FAILs, proving D6); then run the real
chassis and record the honest verdict (which may be RED on A1 — that is the gate
doing its job, not a defect). (A compartment-move self-test belongs to the v2
compartment-ledger work, D4, not v1.)

**PM sanity-check.** This design assumes the chassis can run 28 processes × 100
ticks autonomously (no Karr injection) and that the existing
`run_chassis_v6_32400t.py` conservation accounting is correct enough to lift into
a flat-WID gate; if the 100-tick autonomous run is not stable (e.g. a process
explodes before tick 100), the gate scope must drop to the max stable tick and
that becomes a separate stability finding.

---

## Spec Authority Quote Block

The conservation identity (the physics L2.4 enforces): for a closed system, the
shared metabolite pool changes ONLY by what processes produce/consume. Per tick,
per WID (flat, v1 — the runtime is flat-per-WID; a per-compartment form is v2):

```
Δpool[wid]  ==  Σ_processes ( produced − consumed )[wid]     (wid ∉ exchange set)
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

- **Required behavior (v1):** an autonomous, oracle-free runtime gate that proves
  the 28-process chassis conserves mass at flat-per-WID granularity — every
  non-exchange substrate the pool loses/gains is exactly attributable to process
  production/consumption, every tick, across a stochastic-seed sweep.
- **Why this matters:** L2.1/L2.2 validate each process against Karr *in
  isolation* (single-process replay). They are structurally blind to
  *integration* bugs — a process that bypasses the allocator (A1), a scheduler
  order divergence (A2), or a compartment-merging projection (A4) only manifests
  when all 28 run together on the shared pool. L2.4 is the first gate that
  exercises the integrated wiring, and it needs no Karr output oracle because
  mass conservation is a physics law, not a Karr-specific number. **v1 catches
  A1** (bypass/unaccounted leaks); **A2 and A4 require v2 instrumentation** (OC
  randperm ordering; a compartment ledger) and are explicitly out of v1 scope.
- **Done = property (v1):** for all 28 processes, all ≤100 ticks, all swept
  seeds, every non-exchange WID has `unattributed_delta == 0` (integer-exact,
  flat-per-WID), with the fail-closed write-surface audit passing.

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

**D2 — Closed system + explicit Metabolism boundary (design-review corrected).**
- Chosen: `enable_pool_replenishment=False` (closed to *replenishment* refills),
  BUT the conserved system boundary must be defined explicitly — a bare closed
  system FALSE-FAILS on Metabolism's legitimate exchange flux.
- **The boundary problem (review finding 6, highest risk):** Metabolism
  genuinely exchanges metabolites with the environment (uptake/secretion). M1
  applies external-exchange changes on a private compartmented state and then
  flattens them into the shared `substrates` store
  (`karr_metabolism_writeback.py:127-160`). There is currently NO boundary-flux
  port or emitted boundary ledger. So "explicit boundary term" was hand-wave in
  the first draft. Two admissible resolutions, pick at build time:
  - **(2a) Exclude the exchange set from the closed invariant.** Treat the
    124-WID external-exchange metabolite set (from
    `Metabolism_flat.mat substrateIndexs_externalExchangedMetabolites`, the same
    set L2.5/HB5 use) as OPEN boundary: do NOT assert conservation on those WIDs.
    Assert closed conservation only on the internal (non-exchange) WIDs.
    Simplest; ships v1.
  - **(2b) Observe/emit the boundary.** Add a named Metabolism exchange-flux
    observable and include it in the invariant:
    `Δpool == Σ_p net_write + exchange_flux`. Stronger; requires a new emit port.
- Chosen for v1: **(2a)** — exclude the 124 exchange WIDs, assert conservation on
  the internal set, and record the exchange WIDs as a documented open-boundary
  exclusion (not a silent skip). (2b) is a v2 hardening.
- Falsifier: if a WID outside the 124-exchange set shows a persistent
  unattributed delta, that is a real A1 leak, not a boundary artifact.

**D3 — Tolerance = 0 (integer-exact).**
- Chosen: counts are integers; conservation is exact. No float tolerance. A
  1-molecule unattributed delta is a FAIL (it is exactly the S3-class
  1-molecule bug that L2.1 flagged).

**D4 — Compartment resolution (design-review corrected — flat-WID v1).**
- The intent (per-compartment, to catch A4) is right, BUT the review confirmed
  the existing prototype and the OC runtime are FLAT-per-WID: M1 flattens the
  `(585, 3)` compartmented delta with `sum(axis=1)`
  (`karr_metabolism_writeback.py:164-174`), the shared `substrates` store is flat
  per WID, and `run_chassis_v6_32400t.py` snapshots/attributes by WID only. So
  L2.4 CANNOT catch A4 by "lifting the prototype" — that claim was wrong.
- Chosen: **v1 asserts flat-WID conservation only** (integer-exact per WID,
  honestly scoped). **A4 (compartment merge) is explicitly OUT of v1 scope** and
  named as a prerequisite for a v2: catching A4 requires a compartment-resolved
  ledger (observe M1's internal `(585,3)` state before it is flattened, and key
  attribution on `(process, wid, compartment, tick)`). Do NOT claim A4 coverage
  until that ledger exists.
- Falsifier: a compartment-move bug that nets to zero flat-per-WID will pass v1;
  that is a known, documented v1 blind spot, not a hidden false-pass.

**D5 — Seed sweep (design-review corrected — does NOT catch A2 in v1).**
- The review confirmed `build_karr_chassis_v6` has NO `seed` parameter and OC has
  NO `randperm`-equivalent scheduler — it uses a FIXED process/step order
  (`karr_composite.py`). Varying a seed changes stochastic process *internals*,
  NOT process *order*. So a seed sweep CANNOT catch the A2 "fixed-order vs
  randperm-order" divergence. The first-draft A2-coverage claim was wrong.
- Chosen: **v1 runs a multi-seed sweep for robustness of the flat-WID
  conservation check against stochastic internals, but does NOT claim A2
  coverage.** **A2 is explicitly OUT of v1 scope** and named as a prerequisite:
  catching A2 requires OC to implement Karr's randomized process ordering
  (`randperm` with the tRNAAminoacylation-before-Translation constraint,
  evolveState.m:48-57) and then sweeping *orders* — a separate build.
- Falsifier: if all processes are order-independent at the pool level, A2 is a
  non-issue; the design does not assume that, it just scopes A2 out of v1.

**D6 — Attribution + FAIL-CLOSED write-surface audit (review-strengthened).**
- Chosen: on failure, attribute the unattributed delta to the offending
  (process, WID, tick) and classify A1 (bypass write not accounted). **The
  write-surface guard is FAIL-CLOSED, not a soft cross-check:** derive the
  allowed substrate-write path inventory from the chassis topology
  (`karr_composite.py`) + the L1b wiring rows' declared produce/consume WIDs, and
  **hard-FAIL if any substrate-affecting update at runtime lands on a store path
  outside that inventory.** The prototype counts only writes where
  `store_path[0] == "substrates"` (`run_chassis_v6_32400t.py:352`); a substrate
  effect through any other path would otherwise be silently uncounted — the
  fail-closed audit converts that blind spot into an explicit failure.

**D7 — No output oracle.**
- Chosen: L2.4 reads NO Karr process-output trace. Its only oracle is the
  conservation identity (physics). This is what lets it run at 28×100 without the
  per-process Karr fixtures and what makes it the integration gate L2.1 cannot be.

---

## 10) Self-Audit (slot-3 mapping)

| Beat-4 failure mode | Guard | Where enforced |
|---|---|---|
| A1 bypass leak masked by inflow | D2: replenishment OFF + explicit exchange-WID exclusion | chassis config + invariant scope |
| Substrate write outside the counted surface | D6: FAIL-CLOSED topology audit (hard-fail) | accounting audit |
| 1-molecule leak under float tolerance | D3: integer-exact, tol 0 | comparison |
| "Looks conserved overall" aggregate-only | D1: per-cell fail, not just max-abs | verdict granularity |
| False-fail on Metabolism exchange flux | D2: exclude 124 external-exchange WIDs (documented open boundary) | invariant scope |
| (v1 blind spot, documented) A4 compartment-merge nets to zero flat-per-WID | D4: A4 OUT of v1; needs compartment ledger (v2) | scope boundary |
| (v1 blind spot, documented) A2 order divergence not exercised | D5: A2 OUT of v1; needs OC randperm ordering (v2) | scope boundary |

**Open items (build-time, need WSL — currently BLOCKED, WSL down):**
1. Confirm the chassis runs 28 procs × 100 ticks autonomously with
   replenishment OFF (stability); if not, set scope = max stable tick.
2. Lift `run_chassis_v6_32400t.py` conservation accounting into a gate at
   flat-WID granularity (NOT per-compartment — the prototype is flat-only) and
   build the fail-closed write-surface audit (D6).
3. Resolve the Metabolism boundary (D2): default v1 = exclude the 124
   external-exchange WIDs; record them as a documented open boundary.
4. (v2 prerequisites, not v1) compartment ledger for A4 (D4); OC randperm
   ordering for A2 (D5).

## Build sequence (once WSL restored)
1. Stability probe: `build_karr_chassis_v6(enable_pool_replenishment=False)`,
   step 100 ticks, seed 0 — does it complete? Record max stable tick.
2. Implement `scripts/l2_4_verify_conservation.py`: per-tick, **flat-per-WID**
   integer-exact accounting lifted from the prototype; exclude the 124
   exchange WIDs (D2); fail-closed write-surface audit (D6); multi-seed sweep.
3. Synthetic self-tests: planted flat-WID leak → FAIL; a substrate write on an
   unlisted store path → fail-closed audit FAILs (prove D6).
4. First real run: record honest verdict; attribute flat-WID failures to A1.
5. (v2) compartment ledger → A4; OC randperm order → A2; then A4/A3b fixes
   (plan.md line 134).
6. CI: add as a blocking job (HB6 pattern) once green.

## Design review log
- **2026-07-08 (gpt-5.4 rubber-duck):** conservation-prototype existence
  CONFIRMED (`run_chassis_v6_32400t.py` per_tick_process_sums /
  max_abs_unattributed_delta). Found blocking overclaims, all corrected: (D4) the
  prototype + OC runtime are flat-per-WID (M1 flattens `(585,3)` via
  `sum(axis=1)`, karr_metabolism_writeback.py:164-174) so A4 is NOT catchable by
  lifting the prototype → A4 scoped out of v1; (D5) `build_karr_chassis_v6` has
  no seed param and OC has no `randperm` → seed sweep cannot catch A2 → A2 scoped
  out of v1; (D2) the "explicit boundary term" was hand-wave → v1 excludes the
  124 external-exchange WIDs as documented open boundary; (D6) write-surface
  guard strengthened to fail-closed. v1 honestly catches **A1** only.
