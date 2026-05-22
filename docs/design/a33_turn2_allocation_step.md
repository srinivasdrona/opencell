# A3.3 Turn 2 — KarrAllocationStep

**Status**: design ready · **Codex worktree**: `agent/a33-allocation` (to be created) · **Estimated wall**: 30 min

## Why this module exists

Karr's `evolveState.m` (lines 148–161) computes proportional fair-share metabolite allocation BEFORE any process runs:

```matlab
requirements = zeros([numel(mets.counts) nProcesses]);
for i = 1:nProcesses
    requirements(:, i) = process_i.calcResourceRequirements_Current();
end
requirements = max(0, requirements);
tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));
```

**Algorithm**: For each metabolite `m`, given the sum of all processes' requested amounts `Σᵢ requirements[m,i]`:
- If supply ≥ demand: each process gets what it requested
- If supply < demand: each process gets `floor(supply × (request_i / total_demand))` — proportional fair share with integer floor

The OPEN-2 audit (`docs/design/resource_ledger_vs_karr_2026-05-22.md`) confirmed the existing `opencell/core/resource_ledger.py` implements this algorithm correctly BUT is dormant in the Vivarium chassis (only used by pre-Vivarium `engine.py`). A3.3 needs a Vivarium-native `Step` that wires the same algorithm into the chassis.

## Architecture: Vivarium `Step` semantics

A Vivarium `Step` runs once per tick BEFORE any `Process.next_update`. It reads from stores and writes to stores like a Process, but has no schedule (it's update-driven). For metabolite allocation, we want:

```
Per tick:
  1. Each Process writes its current-state requests to `requests.<process_name>.<wid>`
     (this happens at the END of the prior tick's next_update, OR via a separate
     request-calculator Step — see "request mechanism" below)
  2. KarrAllocationStep fires:
     a. Reads `substrates.<wid>` (current supply)
     b. Reads `requests.<process_name>.<wid>` for every registered consumer process
     c. Computes proportional fair share
     d. Writes `substrates_allocated.<process_name>.<wid>` for each consumer
  3. Each consuming Process reads `substrates_allocated.<self.name>.<wid>` in its
     next_update and uses that as the upper bound on consumption
```

## The request mechanism — closing GPT-5.5's critique

GPT-5.5 critique: "allocation requests must be state-derived, not static parameters."

**Resolution**: The allocation Step does NOT call methods on Processes (Vivarium Processes don't expose callable methods to each other). Instead, **each consumer Process writes its current-tick request to a shared `requests` store at the END of every `next_update`**, where it gets read by the allocation Step on the NEXT tick.

This introduces a 1-tick lag for request propagation. To eliminate the lag, we use a separate `RequestCalculatorStep` per process (also a Vivarium Step), which runs BEFORE the allocation Step:

```
Tick N:
  Step phase (in this order):
    1. RequestCalculator-D2 reads complex.counts + protein.counts -> writes requests.d2_real.<wid>
    2. RequestCalculator-PD reads complex.counts -> writes requests.protein_decay_light.<wid>
    3. KarrAllocationStep reads requests.* + substrates.* -> writes substrates_allocated.*
  Process phase (parallel snapshot):
    4. M2v3, M3v3, D.2-real, ProteinDecay-light all evaluate from start-of-tick + allocations
```

Vivarium runs all Steps to fixed-point BEFORE Processes fire (`engine.py:_apply_step_until_stable`). Step ordering within the same tick is by topology: each RequestCalculator writes to `requests.<name>` (a store the allocation Step reads), so Vivarium's update-propagation ensures RequestCalculators fire before KarrAllocationStep.

**Verification spike**: this turn includes a small probe (`test_step_chain_propagation`) confirming Vivarium fires Steps in the topology-determined order, with allocation Step seeing all RequestCalculator outputs.

## Algorithm pseudocode

```python
class KarrAllocationStep(Step):
    name = "karr_allocation_step"
    defaults = {
        "consumer_processes": [],  # list of (process_name, [wid_1, wid_2, ...]) tuples
        "substrate_wids": [],      # all WIDs in the substrate universe (585 for M1)
    }
    
    def ports_schema(self):
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.parameters["substrate_wids"]
            },
            "requests": {
                proc_name: {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in wids
                }
                for proc_name, wids in self.parameters["consumer_processes"]
            },
            "substrates_allocated": {
                proc_name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in wids
                }
                for proc_name, wids in self.parameters["consumer_processes"]
            },
        }
    
    def next_update(self, timestep, states):
        substrates = states["substrates"]
        requests = states["requests"]
        update_alloc = {}
        
        # For every WID that any consumer requested, compute fair share
        all_requested_wids = set()
        for proc_name in requests:
            all_requested_wids.update(requests[proc_name].keys())
        
        for wid in all_requested_wids:
            supply = max(0.0, float(substrates.get(wid, 0.0)))
            total_demand = sum(
                max(0.0, float(requests[p].get(wid, 0.0))) for p in requests
            )
            if total_demand <= 0.0:
                continue  # nobody asked, allocate nothing
            
            scale = min(1.0, supply / total_demand)  # 1.0 if supply >= demand
            for proc_name in requests:
                req = max(0.0, float(requests[proc_name].get(wid, 0.0)))
                allocated = math.floor(req * scale)  # integer floor, per Karr's `fix()`
                update_alloc.setdefault(proc_name, {})[wid] = float(allocated)
        
        return {"substrates_allocated": update_alloc}
```

**Note on `_updater: "set"` for `substrates_allocated`**: Only the allocation Step writes to this store. Per the all-accumulate decision, `set` is forbidden only when MULTIPLE writers might collide. The allocation Step is the SOLE writer for `substrates_allocated.*` so `set` is safe and semantically correct (each tick fully replaces the prior tick's allocation). Document this exception inline.

**Note on `_updater: "accumulate"` for `requests`**: Multiple RequestCalculator Steps may write to overlapping WIDs within the same process's request bucket (e.g., if RequestCalculator-D2 and RequestCalculator-RibAsm both want GTP). Use accumulate to sum them, then the allocation step reads the sum.

Actually — simpler: each Process owns its own request bucket (`requests.d2_real`, `requests.protein_decay_light`), and only one RequestCalculator writes per bucket per tick. So **`requests.<process>.<wid>` can also be `set`**. Multiple RequestCalculators target DIFFERENT process buckets, never the same. Simpler and correct.

**Revised schema**: both `requests.<proc>.<wid>` and `substrates_allocated.<proc>.<wid>` use `_updater: "set"` because each is single-writer.

## Scope (this turn)

**Net new files**:
1. `opencell/vivarium/karr_allocation_step.py` (~140 LOC)
2. `tests/vivarium/test_karr_allocation_step.py` (~150 LOC)

**Modified files**: NONE.

## Test plan

### Test 1: under-demand (everyone gets full request)
- 2 consumers, 1 metabolite, supply=100, requests {A: 30, B: 50}
- Expected: `substrates_allocated.A.X == 30`, `substrates_allocated.B.X == 50`

### Test 2: over-demand (proportional with floor)
- 2 consumers, 1 metabolite, supply=10, requests {A: 30, B: 20}
- Total demand = 50, scale = 10/50 = 0.2
- A: floor(30 × 0.2) = 6, B: floor(20 × 0.2) = 4
- Expected: A → 6, B → 4. Supply not fully consumed (10−6−4 = 0 remainder).

### Test 3: exact-supply
- supply=50, requests {A: 30, B: 20}, total = 50
- Expected: A → 30, B → 20 (full)

### Test 4: zero-request consumer
- supply=100, requests {A: 0, B: 50}
- Expected: A → 0, B → 50

### Test 5: zero-supply
- supply=0, requests {A: 30, B: 20}
- Expected: A → 0, B → 0

### Test 6: integer floor edge case
- supply=10, requests {A: 7, B: 5}, total = 12, scale = 10/12 ≈ 0.833
- A: floor(7 × 0.833) = floor(5.833) = 5
- B: floor(5 × 0.833) = floor(4.166) = 4
- Expected: A → 5, B → 4. Karr's `fix()` rounds toward zero == math.floor for non-negative.

### Test 7: step-chain propagation (the architectural probe)
- Tiny composite: 2 toy RequestCalculator Steps + 1 KarrAllocationStep + 1 consumer Process
- Confirm that within one tick, RequestCalculators write requests, allocation reads them, consumer sees allocation
- Assert final state of `substrates_allocated.<consumer>.<wid>` matches expected fair share

### Test 8: multi-WID over-demand
- 2 consumers requesting 2 metabolites, mixed under-/over-demand per metabolite
- Verifies per-WID allocation is independent (each metabolite scaled separately)

## Acceptance criteria

- All 8 tests pass
- `pytest tests/ -x --ignore=tests/probes -q` — all existing tests still green
- Commit message: `a33-t2: KarrAllocationStep (Karr proportional fair-share)`
- STATUS reports: file count, test counts, full pytest output

## Out of scope (Turn 2)

- Hooking the allocation step into `build_karr_chassis_v3` — Turn 5
- RequestCalculator Steps for D.2-real and ProteinDecay-light — Turn 3 and Turn 4 respectively (each turn delivers its own RequestCalculator alongside the consumer Process)
- Integration with `resource_ledger.py` — explicitly NOT integrated; the ledger remains dormant. The audit doc explains why.

## Open question (deferred to Turn 3, not blocking)

- Does the integer-floor strategy match Karr's `fix()` exactly for negative values? Karr's `max(0, fix(...))` guards against this; we use `math.floor` after a `max(0, ...)` clamp on requests. **Equivalent for non-negative inputs.** Negative requests are nonsensical (a process can't request −5 metabolites) so this is fine.
