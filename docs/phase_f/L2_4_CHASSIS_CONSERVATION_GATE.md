# L2.4 Chassis Autonomous Conservation Gate — Design

**Status:** DESIGN (drafted 2026-07-08, Day-48; **revised 2026-07-08 after gpt-5.4
design review** — scope corrected; **revised again 2026-07-19, Day-53, after
gpt-5.5 review + the Day-53 conservation probe** — two-part gate (D8), full-horizon
requirement (D9), integer-validity (D3-rev), exchange shadow-audit (D2-rev),
mechanical write-surface audit (D6-rev), coverage matrix, empirical anchor; see
review log). Gate NOT yet built.
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
a flat-WID gate. **Full-horizon completion is a PASS precondition (D9), not a
soft assumption:** if any seed crashes before the requested tick count the gate
returns STABILITY_FAIL (nonzero exit), NOT a reduced-scope "max stable tick"
pass — a conservation verdict over a truncated run is vacuous and must never
unblock A1.

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
flat-per-WID (v1; per-compartment is v2, D4), integer-exact, seed-swept, blocking
gate.

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
- Chosen: per-tick, per-WID (flat, v1 — per-compartment is v2, D4) **integer-exact**
  conservation:
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
- Chosen for v1 (**gpt-5.5-revised, SS#3**): (2a) ALONE is TOO BROAD — excluding
  a whole WID treats every delta on it as boundary flux, but the fixture shows
  the external-exchange set overlaps **12 internal-exchange rows, 3 ATP-hydrolysis
  rows, and 27 nonzero biomass-production rows**, so an A3/A3b metabolism bug on
  those WIDs would hide behind the "exchange" label. v1 therefore does (2a) PLUS
  a mandatory **SHADOW AUDIT: FAIL whenever a skipped exchange WID also receives a
  non-boundary internal / biomass / ATP-hydrolysis delta in the same tick.** Full
  (2b) — a named, emitted Metabolism boundary-flux term in the invariant
  (`Δpool == Σ_p net_write + exchange_flux`) — remains the v2 target and is
  preferred if the emit port is cheap.
- Falsifier: if a WID outside the 124-exchange set shows a persistent
  unattributed delta, that is a real A1 leak, not a boundary artifact.

**D3 — Integer-exact, and integer-VALIDITY asserted BEFORE the residual (gpt-5.5, MAJOR-5).**
- Chosen: counts are integers; conservation is exact, tolerance 0. A 1-molecule
  unattributed delta is a FAIL (the S3-class 1-molecule bug L2.1 flagged).
- **Revised (gpt-5.5):** a zero residual is NOT the same as integer integrity — a
  fractional delta applied to the store can yield `unattributed_delta == 0`
  EXACTLY while still violating molecule-count integrity (this is precisely the
  uncapped v3-transcription fractional-NTP failure mode; see Empirical Anchor).
  So BEFORE the residual comparison, assert every substrate delta AND every
  post-tick pool count is finite and integer-valued (`x == round(x)`); any
  fractional value is a Part-B FAIL (D8). Then compare INTEGER residuals, not
  floats-with-tolerance.

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
- **Revised (gpt-5.5, MAJOR-6):** deriving allowed paths from topology + L1b rows
  alone only catches paths already known to the inventory; it can miss in-place
  state mutation, command-style updates, or nested nonstandard stores later
  projected to substrates. So the audit MUST be mechanical, not inventory-derived
  only: snapshot ALL substrate-like numeric leaves before/after each tick and FAIL
  on any changed WID/path not in the declared allowed-update set, INCLUDING
  in-place changes.

**D7 — No output oracle.**
- Chosen: L2.4 reads NO Karr process-output trace. Its only oracle is the
  conservation identity (physics). This is what lets it run at 28×100 without the
  per-process Karr fixtures and what makes it the integration gate L2.1 cannot be.

**D8 — Two-part gate + verdict on the UNCAPPED target branch (gpt-5.5, SS#1).**
- The conservation residual (`Δpool == Σ process net_write`) sums the SAME
  substrate deltas Vivarium then applies to the store. For ordinary substrate
  ports it passes BY CONSTRUCTION even if the biology is wrong, the allocator
  over/under-allocates, a process consumes beyond its request, or the uncap
  produces fractional counts. So flat-conservation ALONE validates store
  attribution, not chassis integrity — and a green on the CAPPED baseline
  certifies a DIFFERENT chassis than the uncapped one the A1 decision ships.
  (Empirically confirmed — see Empirical Anchor: capped conserves to 2.27e-12,
  uncapped crashes on fractional NTP.)
- Chosen: L2.4 is **TWO-PART**, both required to PASS:
  - **Part A — store-attribution conservation:** no unaccounted substrate store
    change (the flat-per-WID `unattributed_delta == 0`, D1/D3).
  - **Part B — chassis integer/allocation integrity:** every substrate delta and
    post-tick pool count is finite and integer-valued (D3-revised); nonnegative
    where applicable; on a declared write surface (D6); and every consumer
    enforces `consumption ≤ allocation` (the L2.0a allocator contract, re-checked
    in the integrated run).
- **Verdict target:** the blocking L2.4 verdict MUST be taken on the exact
  UNCAPPED target branch (the branch that lands the A1 uncap). The capped
  baseline is a HARNESS SMOKE TEST only and MUST NOT be used to unblock A1.
- Falsifier: if Part A is green but Part B fails (e.g. a fractional NTP delta
  that nets to a 0 residual), the gate FAILs — that is the A1-uncap fractional
  failure mode, caught.

**D9 — Full-horizon completion is part of the gate; no truncated PASS (gpt-5.5, SS#2).**
- The first draft's "if a process explodes before tick 100, drop scope to the max
  stable tick" is UNSAFE: a conservation verdict over 0 completed ticks has no
  conservation meaning, and a truncated green could unblock A1 vacuously. The
  Day-53 probe already found tick-1 crashes on all seeds.
- Chosen: the requested horizon (default 100 ticks, all swept seeds) MUST
  complete. If any seed crashes before the requested tick count, L2.4 exits
  nonzero as **STABILITY_FAIL** — NOT PASS-with-shorter-scope. A
  `--max-stable-tick` mode may exist ONLY as exploratory diagnostics and MUST NOT
  unblock A1.
- Falsifier: a chassis that cannot survive the horizon is not conservation-proven;
  STABILITY_FAIL is the correct, non-vacuous verdict.

---

## Coverage Matrix (what v1 does / does NOT catch — gpt-5.5, MAJOR-4)

| Bug class | v1 verdict | How / why |
|---|---|---|
| **A1** — unaccounted FLAT substrate write (non-exchange, on a visible path) | **CATCHES** | Part A residual + D6 fail-closed mechanical audit |
| **A1** — allocator oversupply / cap mismatch | **CATCHES via Part B only** | the integer + `consumption ≤ allocation` checks (D8 Part B); NOT via the Part A residual alone |
| **A2** — process-order / `randperm` divergence | **NO** | OC is fixed-order; needs a v2 randperm order sweep (D5) |
| **A3/A3b** — metabolism LP-bounds / clipping / byproduct fidelity | **MOSTLY NO** | flat conservation is blind to LP-internal fidelity; the D2 shadow audit only catches exchange-WID mislabeling |
| **A4** — compartment merge (nets to zero flat-per-WID) | **NO** | needs a v2 compartment ledger (D4) |

**Verdict language (gpt-5.5, MINOR-8):** every L2.4 PASS report MUST state:
"L2.4 PASS means no unaccounted flat substrate store change AND integer/allocation
integrity under this run **on the uncapped chassis**; it is NOT an output-fidelity
or Karr-parity certificate."

## Empirical Anchor (Day-53 probe, 2026-07-18/19)

The L2.4 stability + conservation probe (`run_chassis_v6_32400t.py`) plus the
gpt-5.5 review produced converging evidence that drove D8/D9/D3-rev:
- **RNG-mismatch crash (FIXED):** the chassis reseeds every process `_rng` to a
  `Generator`; 4 processes called `RandomState`-only APIs
  (`random_sample`/`.rand`/`randperm`) → tick-1 `AttributeError` on all seeds.
  Fixed (commit `04d15e1`); the capped chassis then ran 100/100 ticks.
- **Capped conserves to machine epsilon:** on the CAPPED baseline,
  `max_abs_unattributed_delta = 2.27e-12` (top WID `H`, tick 32). Empirical proof
  of D8/SS#1 — flat conservation is GREEN on the capped chassis, which is NOT the
  uncapped chassis the A1 decision ships.
- **Uncapped crashes on fractional NTP:** the uncapped chassis emits fractional
  NTP from v3 mean-field transcription (`karr_transcription_v3.py:160,217`, no
  stochastic rounding) → `non-integral enzyme count`. This is the exact Part-B /
  D3-revised failure mode (a fractional delta a Part-A residual would NOT catch).
  Fix in flight: port translation-v3's `_stochastic_round_*` into transcription-v3
  (the lone continuous process missing store-boundary discretization; metabolism
  and translation-v3 already round).

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
| Fractional delta nets to 0 residual (capped-green false-pass) | D3-rev + D8 Part B: integer-validity asserted BEFORE the residual | integer check |
| Truncated / vacuous PASS on a crash | D9: full horizon required, else STABILITY_FAIL (nonzero) | verdict / exit |
| Exchange-WID exclusion hides a metabolism bug | D2-rev: shadow audit FAILs a non-boundary delta on a skipped WID | invariant scope |
| Verdict taken on the capped, not uncapped, chassis | D8: verdict target = uncapped branch; capped = smoke only | verdict target |
| In-place / off-path substrate mutation | D6-rev: mechanical before/after snapshot of ALL substrate leaves | accounting audit |

**Open items (build-time):**
1. Confirm the chassis runs 28 procs × 100 ticks autonomously with replenishment
   OFF **on the UNCAPPED branch** (D8 verdict target); if any seed crashes before
   the horizon, that is **STABILITY_FAIL** (D9) — NOT a reduced-scope pass.
   (Probe status: capped runs 100/100 ticks; uncapped pending the transcription-v3
   stochastic-round fix — the lone remaining fractional source.)
2. Lift `run_chassis_v6_32400t.py` conservation accounting into a gate at
   flat-WID granularity (NOT per-compartment — the prototype is flat-only), and
   add the **Part-B integer/allocation-integrity checks** (D8): finite+integer
   deltas & pools (D3-rev), `consumption ≤ allocation`, and the **mechanical**
   before/after write-surface snapshot audit (D6-rev).
3. Resolve the Metabolism boundary (D2): v1 = exclude the 124 external-exchange
   WIDs **plus** the shadow audit (fail on a non-boundary delta to a skipped WID);
   full boundary-flux emit (2b) is v2.
4. (v2 prerequisites, not v1) compartment ledger for A4 (D4); OC randperm
   ordering for A2 (D5).

## Build sequence
1. Stability probe (**DONE 2026-07-18**): capped runs 100/100 ticks
   (`max_abs_unattributed_delta = 2.27e-12`); uncapped pending the
   transcription-v3 stochastic-round fix. **Full-horizon completion on the
   UNCAPPED branch is a PASS precondition (D9); a crash before the horizon is
   STABILITY_FAIL, not a reduced scope.**
2. Implement `scripts/l2_4_verify_conservation.py`: per-tick, **flat-per-WID**
   integer-exact **Part-A** accounting lifted from the prototype (exclude the 124
   exchange WIDs + shadow audit, D2-rev), PLUS **Part-B** integer/allocation
   integrity (D8): finite+integer deltas & pools (D3-rev), `consumption ≤
   allocation`, mechanical write-surface snapshot audit (D6-rev); multi-seed
   sweep (labelled stochastic-smoke, D5 — NOT A2 coverage).
3. Synthetic self-tests: planted flat-WID leak → FAIL; a substrate write on an
   unlisted store path → mechanical audit FAILs (prove D6); a planted fractional
   delta that nets to a 0 residual → Part-B FAILs (prove D3-rev/D8).
4. First real run **on the uncapped branch**: record honest verdict; attribute
   flat-WID failures to A1; a pre-horizon crash is STABILITY_FAIL (D9).
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
- **2026-07-19 (gpt-5.5 rubber-duck + Day-53 probe):** 3 SHOWSTOPPERs + 6 majors/
  minors, all incorporated. **SS#1 → D8** (two-part gate: Part A store-attribution
  + Part B integer/allocation integrity; verdict on the UNCAPPED branch, capped =
  smoke only) — empirically confirmed (capped conserves to 2.27e-12 while the
  uncapped chassis crashes on fractional NTP). **SS#2 → D9** (full-horizon
  required; crash = STABILITY_FAIL, not a truncated PASS; removed the unsafe
  "drop to max stable tick" language from the PM sanity-check / open items /
  build sequence). **SS#3 → D2-revised** (whole-WID exclusion too broad — fixture
  overlaps 12 internal-exchange / 3 ATP-hydrolysis / 27 biomass rows; added a
  mandatory shadow audit; full boundary-flux emit = v2). **MAJOR-5 → D3-revised**
  (assert integer-VALIDITY of deltas+pools BEFORE the residual — the fractional-
  NTP failure mode). **MAJOR-6 → D6-revised** (mechanical before/after snapshot,
  not inventory-derived alone). **MAJOR-4 → Coverage Matrix** added. **MINOR-8**
  → verdict language sharpened; **MINOR-9** → stale per-compartment wording fixed
  (D1, Spec Authority now say flat-per-WID v1). The probe also fixed an RNG-
  mismatch crash (commit `04d15e1`) and localized the uncapped fractional source
  to transcription-v3 (the lone continuous process missing store-boundary
  stochastic rounding; metabolism + translation-v3 already round).
