# L2.0a Allocator Input Gate — Design

**Status:** DESIGN (drafted 2026-07-08, Day-48). Gate NOT yet built.
**Ladder position:** L2.0a — runtime, 1 tick × 28 processes, oracle at the
allocation boundary (pool-in + requirements-in → allocation-out). Runs WITHOUT a
Karr oracle at *process outputs* (plan.md L-ladder line 43). Sits after L2.0
(static schema) and before L2.1 (per-process bit-identity replay).
**Format:** follows the landed L1b gate design doc
(`docs/phase_f/L1B_WIRING_CONFORMANT_GATE.md`) — DAP Intent + Spec-Authority
quote + Design Contract + Inventory + Decision Ledger + Self-Audit.

---

## DAP Intent (Slot 1)

**Beat 1 — Contract.** Given Karr's pre-tick global metabolite pool and Karr's
per-process metabolic requirements, does OC's `KarrAllocationStep` produce the
same per-process allocated substrate counts as Karr's `Simulation.evolveState`
allocation step? Done = a deterministic per-(process, WID) verdict over all 28
processes at a fixed tick, comparing OC allocation output to the Karr
`allocations` oracle, with exit-code gate semantics.

**Beat 2 — Surface.**
- Read: `opencell/vivarium/karr_allocation_step.py` (OC allocator under test);
  `opencell/vivarium/karr_request_calculators.py` (OC request path);
  `data/karr_fixtures/per_process/*.mat` (`states_before` pool snapshots);
  the Karr allocation oracle in
  `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m:24-37`;
  `tests/vivarium/l2_replay_common.py` (fixture/replay helpers).
- Write: `scripts/l2_0a_verify_allocator.py` (or `tests/vivarium/test_l2_0a_*`),
  a report artifact, this doc.
- Suspect patterns: (a) the OC allocator's default enrolls only **3** consumer
  processes (`_default_consumer_processes`, karr_allocation_step.py) — the gate
  must enroll all 28; (b) OC caps scale at `min(1, ·)` while Karr does not
  (evolveState.m:36) — a known arithmetic fork, see D4.

**Beat 3 — Expected outcome.** Distinguishing command:
`bin\oc-py scripts/l2_0a_verify_allocator.py --format plain`. Expected: per-WID,
per-process integer-equality verdicts; PASS only when every checked
(process, WID) allocation equals the Karr oracle; exit 0 iff all pass. Smallest
reachable state: load one Karr `states_before` pool snapshot + Karr requirements
for one tick; feed to `KarrAllocationStep.next_update`; compare to Karr
`allocations` at that tick.

**Beat 4 — Invert (pre-mortem).**
- **Tautology false-pass:** if the gate feeds *OC's own* request-calculator
  output as the "requirements" input, it tests the allocator against numbers OC
  itself generated — the request-calc bug (if any) is invisible and the
  allocation just re-derives its own inputs. Guard (D5): the requirements input
  MUST be Karr's `requirements` oracle (evolveState.m:31-35), not OC requests.
  Request-calculator correctness is a *separate* gate concern (A2 / L2.1), not
  L2.0a.
- **Aggregation false-pass:** comparing pool-level *total* allocated per WID
  (summed over processes) instead of per-(process, WID) hides a
  compensating misallocation between two processes. Guard (D2): compare the full
  (process × WID) matrix, not column sums.

**Beat 5 — Act, then verify.** Build the gate + a synthetic-fixture self-test
that plants a known misallocation and asserts the gate FAILs it; then run
against real fixtures and record the honest first-run verdict (which may be RED
on the D4 fork — that is informative, not a gate defect).

**PM sanity-check.** This design assumes the Karr `allocations` matrix
(evolveState.m:37) is either already captured in the per-process fixtures or can
be extracted by extending the existing MATLAB extraction; if the oracle is NOT
recoverable per-process at a fixed tick, D1 must be reopened (verification is the
first build step and needs WSL/MATLAB).

---

## Spec Authority Quote Block

Karr's allocation arithmetic — the authoritative oracle
(`@Simulation/evolveState.m:24-37`, verbatim):

```matlab
%% estimate metabolic requirements of processes
requirements = zeros([numel(mets.counts) nProcesses]);
for i = 1:nProcesses
    r = mod.calcResourceRequirements_Current();
    requirements(mod.substrateMetaboliteGlobalCompartmentIndexs, i) = ...
        reshape(r(mod.substrateMetaboliteLocalIndexs, :), [], 1);
end
requirements = max(0, requirements);
tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));
```

Karr then feeds each process its allocation and returns unused counts to the pool
(`evolveState.m:63-73`): `allocation` is set as the process's substrates, the
process runs, and `mets.counts = counts + (substrates_after - allocation)`.

---

## 1) Design Contract

- **Required behavior:** a runtime gate that isolates and validates the
  *allocator arithmetic* — the per-process proportional fair-share division of a
  shared metabolite pool — against Karr's `allocations` oracle, decoupled from
  request-calculator correctness (upstream) and process biology (downstream).
- **Why this matters:** every metabolite-consuming process at L2.1+ receives its
  inputs through `KarrAllocationStep`. If the allocator mis-divides the pool,
  every downstream per-process replay inherits a corrupted input and L2.1
  verdicts become unattributable. L2.0a proves the allocation boundary before
  L2.1 depends on it (diagnostic-dependency ordering, plan.md line 41).
- **Done = property:** for a fixed tick, feeding Karr's pool + Karr's
  requirements to OC's allocator reproduces Karr's per-(process, WID) allocation
  exactly (integer equality), for all 28 processes, with no oracle read at
  process outputs.

---

## 2) Inventory of Existing Artifacts

- [A01] `opencell/vivarium/karr_allocation_step.py` | code | OC allocator under
  test. `next_update` computes `scale = min(1, available/total_demand)`,
  `allocated = floor(requested*scale)`. Default enrolls 3 consumers only.
- [A02] `opencell/vivarium/karr_request_calculators.py` | code | OC request
  path; NOT the L2.0a input (see D5) — its correctness is A2/L2.1 scope.
- [A03] `@Simulation/evolveState.m:24-37` | oracle | Karr requirements +
  allocation arithmetic (`fix`, uncapped scale). THE authoritative spec.
- [A04] `@Simulation/evolveState.m:63-73` | oracle | allocation-consumption +
  unused-return semantics (context for why over-allocation is benign in Karr).
- [A05] `data/karr_fixtures/per_process/*.mat` | fixture | `states_before`
  per-channel snapshots (`cell_vector(handle,"states_before",field,tick)`,
  l2_replay_common.py:310). Pool = substrates `states_before` at the tick.
- [A06] `tests/vivarium/l2_replay_common.py` | code | fixture resolution,
  `states_before` loading, WID projection helpers — reuse, do not reinvent.
- [A07] `data/schemas/per_process/*.toml` `[state_groups].substrates` | schema |
  per-process substrate WID sets (which WIDs each process requests).

Inventory Beat-4 inversion: the allocation oracle (`allocations` matrix) may not
be captured in the current per-process fixtures (they carry `states_before`, not
necessarily `substrates_allocated`). Risk reduction: D1 makes "verify/extend the
oracle extraction" the explicit first build step.

---

## 5) Decision Ledger

**D1 — Oracle source for the allocation output.**
- Options: (1) recompute the oracle in Python from Karr's requirements + pool
  using evolveState.m:36-37 arithmetic; (2) read a captured `allocations`/
  `substrates_allocated` matrix from the fixtures; (3) extend the MATLAB
  extraction to emit per-tick `allocations`.
- Chosen: **(2) if present, else (3); NEVER (1) alone.** Recomputing the oracle
  in Python re-implements the very arithmetic under test (tautology). The gate
  must compare OC's `KarrAllocationStep` output to a Karr-*produced* number.
- Falsifier: if neither the fixture nor a feasible extraction yields per-process
  Karr allocations at a fixed tick, L2.0a cannot be an oracle gate — reopen.
- Build-step-0 (needs WSL/MATLAB): inspect a fixture for an allocation field;
  if absent, extend `scripts/matlab/extract_per_process_traces_v2.m`.

**D2 — Comparison metric.**
- Options: (1) integer equality per (process, WID); (2) tolerance-based;
  (3) pool-level column-sum equality.
- Chosen: **(1) exact integer equality per (process, WID).** Karr allocations
  are `fix(...)` integer counts; OC uses `np.floor(...)`. For non-negative
  operands `fix == floor`, so exact equality is the correct, tolerance-free
  metric (this is a σ=0 boundary, like L2.1). (3) is rejected — it is the
  Beat-4 aggregation false-pass.
- Falsifier: any legitimate source of non-integer or seed-dependent allocation
  would break exact equality — none exists at this boundary (allocation is
  deterministic given pool + requirements).

**D3 — Scope.**
- Chosen: the **substrates (metabolite) channel only**, the 585-WID universe
  (`_default_substrate_wids`, karr_allocation_step.py), all 28 processes, at a
  single fixed tick (tick 0 of each per-process fixture). Non-metabolite ports
  are out of scope (the allocator only divides substrates).
- The gate MUST enroll all 28 processes as consumers, overriding the 3-consumer
  default (`_default_consumer_processes`) — otherwise 25 processes are silently
  unchecked (a Beat-4 coverage hole).

**D4 — The scale-cap arithmetic fork (the first expected finding).**
- Observation (grounded): OC caps `scale = min(1, available/total_demand)`
  (karr_allocation_step.py); Karr uses `available / max(1, total_demand)` with
  **no `min(1,·)` cap** (evolveState.m:36). In the *over-supplied* regime
  (available > total_demand) they diverge: Karr distributes the whole pool
  proportionally (each process gets ≥ its request); OC gives each exactly its
  request (excess stays in pool). In the *under-supplied* regime they agree.
- Decision: **the gate compares OC to the Karr oracle and reports the
  divergence honestly.** Resolution is deferred to the gate's first verdict:
  if real and material, either (a) change OC to match Karr (drop the `min(1,·)`
  cap) or (b) record a justified deviation with evidence that Karr's
  unused-return semantics (evolveState.m:72-73) makes the two observationally
  equivalent at process outputs. Do NOT pre-decide by editing OC before the
  gate measures it (empirical-probe-before-design-iteration).
- Falsifier: if first-run shows exact parity on real fixtures, the over-supply
  regime never occurs for these WIDs at tick 0 and D4 is moot (still record it).

**D5 — Requirements input (isolate the allocator).**
- Chosen: feed **Karr's `requirements` oracle** (evolveState.m:31-35) as the
  per-process demand, NOT OC's request-calculator output. This isolates the
  allocator arithmetic (L2.0a) from request-calculator correctness (A2 / L2.1).
  A second, optional mode may feed OC requests to measure the *combined*
  request+allocate path, but the primary L2.0a verdict uses Karr requirements.
- Falsifier: if Karr per-process requirements are not recoverable at a tick, the
  isolation is impossible and L2.0a collapses into a combined gate — reopen D5.

**D6 — No oracle at process outputs.**
- Chosen: L2.0a's oracle is strictly at the allocation boundary
  (pool + requirements → allocation). It does NOT run process `evolveState` nor
  compare process outputs (that is L2.1). Consistent with plan.md line 43.

---

## 10) Self-Audit (slot-3 mapping)

| Beat-4 failure mode | Guard | Where enforced |
|---|---|---|
| Tautology: OC requests used as oracle requirements | D5: Karr `requirements` oracle is the input | gate input loader |
| Aggregation: column-sum hides per-process misallocation | D2: full (process×WID) integer-equality | comparison metric |
| Coverage: only 3 default consumers checked | D3: enroll all 28 processes | consumer enrollment |
| Oracle-recompute tautology (Python re-derives allocation) | D1: oracle must be Karr-produced, not recomputed | oracle source |
| Pre-deciding the D4 fork by editing OC first | D4: gate measures before any OC change | build sequencing |

**Open items (build-time, need WSL/MATLAB — currently BLOCKED, WSL down):**
1. D1/Build-step-0: confirm the per-process fixtures carry a Karr `allocations`
   field at a fixed tick, or extend the MATLAB extraction to emit it.
2. D5: confirm Karr per-process `requirements` at a tick are recoverable from the
   same fixture (or the trace).
3. D4 first-run: measure the over-supply divergence on real fixtures.

## Build sequence (once WSL restored)
1. Build-step-0 (D1/D5): fixture-field audit; extend extraction if needed.
2. Implement `scripts/l2_0a_verify_allocator.py`: load pool + Karr requirements
   for tick 0 of each process; run `KarrAllocationStep.next_update`; compare to
   Karr `allocations`; per-(process, WID) integer verdicts + aggregate.
3. Synthetic self-test: plant a misallocation → assert FAIL; parity → PASS.
4. First real-fixture run: record honest verdict; adjudicate D4.
5. CI: add as a blocking job alongside `l1b-gates` once green (HB6 pattern).
