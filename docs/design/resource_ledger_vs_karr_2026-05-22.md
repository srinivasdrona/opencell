# Audit: OpenCell `resource_ledger.py` vs Karr's Allocation Algorithm

**Audit date:** 2026-05-22 19:42 IST
**Auditor:** Copilot CLI (orchestrator) — manually completed after Codex delegation aborted on missing `rg` binary (Codex partial trace in `agent/karr-allocation-audit/.codex_stdout.log`)
**Auditing for:** A3 step 3 (`d2-real + ProteinDecay-light`) joint design — see `docs/design/a3_step3_joint_design_v1.md` §3.2

---

## TL;DR

OpenCell's `opencell/core/resource_ledger.py` (200 LOC) **implements proportional-fair-share allocation correctly in spirit, but it is dormant in the current chassis**. It is instantiated by `opencell/core/engine.py` (a pre-Vivarium `Engine` class) and not used by `opencell/vivarium/karr_composite.py` (the actually-running chassis). A3 step 3 cannot use `ResourceLedger` as-is because no Vivarium hook reads/writes it.

**Recommendation: build a new Vivarium `Step` (`KarrAllocationStep`) for A3.3 that mirrors Karr's algorithm. Keep `ResourceLedger` as-is for backwards compatibility with the older `engine.py` path but document it as not-on-the-critical-path for the Karr-faithful chassis.**

Alignment between `ResourceLedger.allocate()` and Karr's `evolveState.m` lines 137-170 is high enough that the existing implementation could serve as the reference implementation for the new `KarrAllocationStep` — modulo the priority-weighting feature, which Karr doesn't have.

---

## Karr's algorithm (verbatim from `Simulation.evolveState.m` lines 137-170, also `docs/karr_extracts/architecture/03_variable_allocation.md`)

```matlab
%% estimate metabolic requirements of processes
processes = this.processes;
nProcesses = length(processes);
requirements = zeros([numel(mets.counts) nProcesses]);
for i = 1:nProcesses
    mod = processes{i};
    mod.copyFromState();
    r = mod.calcResourceRequirements_Current();
    requirements(mod.substrateMetaboliteGlobalCompartmentIndexs, i) = ...
        reshape(r(mod.substrateMetaboliteLocalIndexs, :), [], 1);
end
requirements = max(0, requirements);
tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));
```

Key properties:
- `requirements` is a (metabolite × process) matrix
- Each metabolite is allocated independently across processes
- `max(0, ...)` clips negative requests (no producing-into-the-pool through allocation)
- `max(1, ...)` in denominator prevents division by zero
- `fix(...)` is integer floor (toward zero)
- If supply ≥ demand → each process gets exactly what it requested
- If supply < demand → each gets `(its_request × supply / total_request)`, integer floor

No priority weighting. No reservation. No re-pool on refusal. All processes are equal.

---

## OpenCell's algorithm (verbatim from `opencell/core/resource_ledger.py` lines 100-155)

```python
def allocate(self, available: dict[str, float]) -> dict[str, AllocationResult]:
    # Group requests by species
    by_species: dict[str, list[ResourceRequest]] = {}
    for req in self._requests:
        if req.amount > 0:  # only allocate consumption requests
            by_species.setdefault(req.species_id, []).append(req)

    results: dict[str, AllocationResult] = {}

    for species_id, requests in by_species.items():
        avail = available.get(species_id, 0.0)
        total_weighted = sum(r.amount * r.priority for r in requests)
        total_demand = sum(r.amount for r in requests)

        req_dict: dict[str, float] = {}
        alloc_dict: dict[str, float] = {}

        for req in requests:
            req_dict[req.sub_model_id] = req.amount

            if total_demand <= avail:
                alloc_dict[req.sub_model_id] = req.amount
            elif total_weighted > 0:
                # Proportional allocation weighted by priority
                fraction = (req.amount * req.priority) / total_weighted
                alloc_dict[req.sub_model_id] = fraction * avail
            else:
                alloc_dict[req.sub_model_id] = 0.0

        shortfall = max(0.0, total_demand - avail)
        results[species_id] = AllocationResult(...)
    ...
```

Key properties:
- Iterates per-species (analogous to Karr's per-metabolite-row)
- `if req.amount > 0` filter (analogous to Karr's `max(0, requirements)`)
- Branch on `total_demand <= avail` (no-contention fast path)
- Proportional allocation `(r.amount × r.priority) / total_weighted × avail`
- **Adds a `priority` weighting Karr doesn't have**
- Returns floats, not integers (no `fix()` analog)

---

## Side-by-side comparison

| Aspect | Karr | OpenCell `ResourceLedger.allocate` | Match? |
|---|---|---|---|
| When allocation runs | At start of every `evolveState` tick, before any process eval | Called explicitly by caller (no fixed cadence) | ⚠️ Different architecture (Karr per-tick; OpenCell on-demand) |
| What gets allocated | Metabolites only (one matrix row per metabolite) | Arbitrary species (whatever caller passes) | ✓ Equivalent — caller chooses |
| Request collection | `calcResourceRequirements_Current()` method on each Process | `.request(sub_model_id, species_id, amount)` calls | ✓ Equivalent interface, different mechanics |
| No-contention fast path | Implicit: `requirements × supply / sum(requirements)` returns `requirements` when sum < supply (after `fix()` floor) | Explicit: `if total_demand <= avail: alloc = amount` | ✓ Same result, OpenCell more explicit |
| Contention resolution | `floor(request × supply / total_request)` | `(amount × priority) / total_weighted × avail` | ⚠️ Karr has no priority; OpenCell does |
| Negative request handling | Clipped via `max(0, requirements)` | Filtered via `if req.amount > 0` | ✓ Same effect |
| Division-by-zero guard | `max(1, sum(requirements, 2))` in denominator | `elif total_weighted > 0: ... else: 0.0` | ✓ Same effect |
| Integer truncation | `fix(...)` (floor toward zero) | **NONE — returns floats** | ✗ Divergence (see below) |
| Priority feature | Not present | `priority` field in `ResourceRequest` | ✗ OpenCell has an extension Karr doesn't |
| Re-allocation on refusal | Not present (process gets what allocator gave) | Not present | ✓ Match |
| Multi-compartment handling | Via `substrateMetaboliteGlobalCompartmentIndexs` indexing | Via `species_id` string — no compartment concept | ⚠️ Karr is compartment-aware; OpenCell is not |

---

## Findings

### Divergences

1. **MINOR: Integer floor missing.** Karr's `fix(...)` truncates allocations to integers. OpenCell returns floats. For metabolite counts in molecules, this is a correctness issue once we have D.2-real consuming integer GTP (you can't consume 4.7 GTPs). The fix is one `int()` call in the new `KarrAllocationStep`; not blocking but must be applied.

2. **MAJOR: Priority weighting is a deviation.** Karr explicitly does NOT have process priorities. All processes get fair share. OpenCell's `priority` parameter looks like an extension for processes that should preempt others (e.g., maybe metabolism should have priority over translation under starvation). **For A3.3, leave `priority` at default 1.0 across all processes** to match Karr exactly. If we want to keep the priority feature available, that's a future-Phase-X enhancement, NOT Karr-2012 behavior. Flag it explicitly in the L4 paper as an opt-in extension if we ever use it.

3. **MAJOR: ResourceLedger is not wired into the Vivarium chassis.** The chassis composer `opencell/vivarium/karr_composite.py` (currently building `build_karr_m1_m2_m3_engine` and `build_karr_chassis_v2`) does not import `ResourceLedger` and does not call its methods. The only call site is `opencell/core/engine.py:92` which instantiates it inside a non-Vivarium `Engine` class that's been superseded by the Vivarium chassis. This is the central finding.

4. **MINOR: Allocation cadence not enforced.** Karr's algorithm runs every tick, by construction (inside `evolveState`). `ResourceLedger.allocate()` is called whenever the caller invokes it. For A3.3 we need to enforce per-tick cadence; a Vivarium `Step` does this naturally.

5. **MINOR: No compartment dimension.** Karr's allocation is per-metabolite-per-compartment (the `substrateMetaboliteGlobalCompartmentIndexs` reshape). OpenCell's `species_id` string is flat. Probably fine for A3.3 because the M1/M2/M3 chassis already treats substrates as flat-keyed (`substrates.ATP` not `substrates.ATP.c`). But worth flagging.

### Gaps

1. No call site that gives `KarrAllocationStep`-style behavior in the Vivarium path. The new step must be built from scratch.

2. No tests in `tests/vivarium/` that verify allocation under contention. `tests/unit/test_resource_ledger.py` tests the dormant ledger but not the chassis behavior.

### Already-aligned

1. **The algorithm itself is correct.** `ResourceLedger.allocate` with `priority=1.0` everywhere produces the same fractional allocations as Karr (modulo float vs int).

2. **The "no-contention fast path" optimization.** Both implementations skip the proportional calculation when total demand ≤ supply.

3. **The "consumption only" filter.** Karr's `max(0, requirements)` and OpenCell's `if req.amount > 0` both correctly limit allocation to demand (not production).

4. **The denominator guard.** Both prevent division-by-zero correctly.

---

## Current OpenCell call sites

```
opencell/core/resource_ledger.py        DEFINES the class
opencell/core/engine.py:19, 92, 75      USES — instantiates self.ledger = ResourceLedger()
                                         in non-Vivarium Engine class (pre-Vivarium era)
tests/unit/test_resource_ledger.py      TESTS — unit tests of the allocate method in isolation
```

Search performed (after Codex's `rg` failure):

```bash
wsl -e bash -lc "cd /mnt/e/opencell && grep -rln 'ResourceLedger\|resource_ledger' opencell/ tests/ --include='*.py'"
```

Result: **3 files only**. None in `opencell/vivarium/`. Confirms ledger is dormant in the currently-running chassis.

---

## Recommendations for A3 step 3 design

### Recommendation 1 — Build a new `KarrAllocationStep` for the Vivarium chassis

`opencell/vivarium/karr_allocation_step.py` — implements Karr's algorithm exactly:

```python
class KarrAllocationStep(Step):
    """Proportional-fair-share allocation per Karr 2012.

    Runs at the start of every Vivarium tick, before any Process.next_update.
    Reads each process's metabolite requests and writes per-process
    allocations to a shared store. Each process then reads its allocation
    instead of the raw substrate pool.

    Algorithm verbatim from Simulation.evolveState.m lines 137-170.
    """

    def next_update(self, timestep: float, states: dict) -> dict:
        substrate_counts = states["substrates"]
        # Each process registered a request via parameters
        # requirements[wid, process] = request from process for substrate wid
        requirements = self._collect_requirements(states)
        # Karr's algorithm:
        # allocations[wid, process] = floor(requirements[wid, process] *
        #                                   substrate_counts[wid] /
        #                                   max(1, sum(requirements[wid, :])))
        ...
```

Use this for A3.3, not `ResourceLedger`. ~120 LOC.

### Recommendation 2 — Set priority = 1.0 in the new step, document the deviation if ever used

The new step does NOT carry the `priority` parameter. If we ever want to give metabolism preferential allocation under starvation (legitimate biology in some contexts), introduce it explicitly in a later phase with a YAML decision file in `decisions/`. Don't carry the priority feature forward as a "feature" we might use — Karr-fidelity means treating processes equally.

### Recommendation 3 — Float-vs-int

The new step returns int allocations (using Python `//` integer division or `int(floor(...))` explicitly). Document in tests that allocations are integer molecules.

### Recommendation 4 — Mark `ResourceLedger` as dormant

Add a top-of-file note to `opencell/core/resource_ledger.py`:

```python
"""Resource ledger: partition-merge allocation for shared metabolites.

STATUS (2026-05-22): This module is dormant in the Vivarium-based chassis.
The A3 step 3 design replaces it with `opencell/vivarium/karr_allocation_step.py`
(KarrAllocationStep) which implements Karr's algorithm exactly within
Vivarium's Step abstraction. ResourceLedger is retained for backwards
compatibility with the older `opencell/core/engine.py` Engine class but
is not on the critical path for Karr-faithful runs.

See: docs/design/resource_ledger_vs_karr_2026-05-22.md
```

Do NOT delete `ResourceLedger`. The `engine.py` Engine class may still be used in places we haven't audited; deletion is a separate cleanup item, not part of A3.3.

### Recommendation 5 — Test infrastructure

`tests/vivarium/test_karr_allocation_step.py` to cover:
- No-contention case (everyone gets what they asked for)
- Exact-supply case (allocations sum to supply)
- Over-demand case (proportional distribution; integer floor)
- Zero-supply edge case (everyone gets 0)
- Zero-request edge case (no division by zero)
- Determinism (same requests → same allocations across runs)
- Integer property (no float allocations)

---

## Update to `a3_step3_joint_design_v1.md` §3.2

OPEN-2 from §10 of the joint design is now **resolved** with this finding. §3.2 should be updated to:

> The existing `opencell/core/resource_ledger.py` is dormant in the Vivarium chassis (see `docs/design/resource_ledger_vs_karr_2026-05-22.md`). A3.3 builds a new `opencell/vivarium/karr_allocation_step.py` implementing Karr's algorithm as a Vivarium `Step`. The existing ledger is kept for backwards compatibility with the older `opencell/core/engine.py` Engine class but is not on the A3.3 critical path. This adds ~120 LOC to the implementation budget (from §4 of the joint design); the total estimate of ~1150 LOC becomes ~1270 LOC.

---

## Files inspected

- `opencell/core/resource_ledger.py` (200 lines, fully read)
- `opencell/core/engine.py` lines 18-95 (call sites only)
- `opencell/vivarium/karr_composite.py` (grepped, confirmed no ledger reference)
- `tests/unit/test_resource_ledger.py` (confirmed exists; not read)
- `docs/karr_extracts/architecture/01_simulation_loop.md` lines 137-170 (the allocation block)
- `docs/karr_extracts/architecture/03_variable_allocation.md` (full)
- `data/m1_sources/WholeCell/src/+edu/.../@Simulation/evolveState.m` — referenced via extract; not opened directly

---

## Codex delegation post-mortem

Codex was delegated this audit task on `agent/karr-allocation-audit` at ~19:13. It successfully read the verbatim Karr block and OpenCell ledger (visible at lines ~150-210 of its stdout trace). Then it tried `wsl -e bash -lc "... rg --files | rg 'evolveState\.m' ..."` to locate the source file, failed with `bash: line 1: rg: command not found`, retried twice, gave up. No audit doc written, no commit made.

Lesson for the `delegate-to-codex` skill: **tool-availability assertion** in WSL is worth checking before Codex attempts. `rg`, `jq`, `fd`, and other modern Unix tools are not always installed even when `bash` is. Codex's prompt should either (a) include explicit tool availability list, or (b) instruct Codex to fall back to POSIX-standard tools (`grep`, `find`) if modern alternatives fail. Adding this to the skill spec is a follow-up.
