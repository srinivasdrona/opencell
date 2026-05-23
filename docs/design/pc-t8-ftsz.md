# Phase C Turn 8 - FtsZPolymerization

**Status**: design ready  
**Task slug**: `pc-t8-ftsz`  
**Karr process**: `Process_FtsZPolymerization`

## Primary-source basis

- Karr extract: `docs/karr_extracts/process/25_FtsZPolymerization.md`
- Karr fixture: `data/karr_fixtures/per_process/FtsZPolymerization_flat.mat`
- Karr trace: `/mnt/e/opencell/data/m1_sources/karr_native/per_process_traces/FtsZPolymerization_100ticks.mat`
  - Trace decode notes (h5 v7.3): `states_before/enzymes` and `states_after/enzymes` are 100x11 object vectors into `#refs#`.
  - Ring-subunit proxy used for validation: `sum_{k=2..9}(count_k * k)` from species `MG_224_[k]MER_GTP`.
  - Tail steady-state (ticks 81-100) mean is ~`392.25` (before) / `392.35` (after).

## Scope (Karr-LIGHT v1)

Implement a light stochastic FtsZ polymerization process that:

- tracks a compact 11-species FtsZ state (GDP/GTP monomer + 2-9mers),
- consumes allocated GTP for GDP->GTP activation,
- emits cell-cycle coupling state:
  - `cell.ftsz_ring_count` (accumulate-delta integer)
  - `cell.ftsz_ring_complete` (set bool, true when count >= threshold),
- matches 100-tick ring steady-state to Karr trace within 10%.

### Deferred to v2

- Full ODE solve/discretize flow used by MATLAB process.
- Explicit annealing/cyclization (already simplified out in Karr header modifications, but additional detailed transitions remain deferred).
- Geometry-coupled ring edges and bent/straight filament states (`FtsZRing` state internals).
- Direct coupling to cytokinesis polygon-edge occupancy dynamics.

## State ports and stores

New/used ports:

- `cell`
  - `ftsz_ring_count` (`_updater: "accumulate"`, emits integer deltas)
  - `ftsz_ring_complete` (`_updater: "set"`, sole-writer boolean gate)
- `substrates`
  - all fixture substrate WIDs (`GDP`, `GTP`, `PI`, `H2O`, `H`) with accumulate deltas
- `requests`
  - `requests.karr_ftsz_polymerization.GTP` (`set`)
- `substrates_allocated`
  - `substrates_allocated.karr_ftsz_polymerization.GTP` (`accumulate`)

## Substrate-consumption and allocation contract

- At tick start, request GTP based on activatable GDP-monomer demand.
- Read allocated GTP from `substrates_allocated.karr_ftsz_polymerization.GTP` (fallback to substrate pool when allocation not present).
- Bound activation events by allocated GTP.
- Emit accumulate substrate deltas (negative for GTP consumption, positive for GDP/PI/H byproducts where applicable in light stoichiometry).

## Algorithm sketch

Per tick:

1. Sync internal 11-state vector from initialization (first tick) or carry-forward.
2. Compute stochastic reaction candidates:
   - GDP->GTP activation (allocation bounded)
   - GTP monomer nucleation to dimer
   - elongation from k-mer to (k+1)-mer up to max length
   - reverse/dissociation steps to maintain bounded steady-state
3. Apply non-negativity clamps and integer event bounds.
4. Compute ring count as subunits in polymers (2-9mers weighted by length).
5. Emit deltas:
   - `cell.ftsz_ring_count` accumulate delta
   - `cell.ftsz_ring_complete = (ring_count >= threshold)`
   - `substrates` deltas
   - next-tick `requests.GTP`

## Parameters/defaults

- fixture path: `data/karr_fixtures/per_process/FtsZPolymerization_flat.mat`
- RNG seed
- timestep
- rate scales for light stochastic transitions
- `ring_complete_threshold`: default `392` (trace-informed)

## Chassis wiring (v4)

- Add process `karr_ftsz_polymerization` to `build_karr_chassis_v4`.
- Add `("karr_ftsz_polymerization", ["GTP"])` to allocation consumers.
- Ensure `GTP` included in allocation substrate WID universe.
- Add topology for `cell`, `substrates`, `requests`, `substrates_allocated`.
- Seed initial state:
  - `cell.ftsz_ring_count` from fixture initial enzyme vector weighted 2-9mer sum.
  - `cell.ftsz_ring_complete` from threshold check.

## Test plan

1. Process and fixture load with expected species and substrate IDs.
2. Chassis v4 default build includes `karr_ftsz_polymerization`.
3. One-tick update under abundant GTP produces valid sign behavior (ring non-decrease in growth-biased setup; requests non-negative).
4. Allocation contract: with zero allocated GTP, process consumes no GTP.
5. 100-tick run reaches ring steady-state within 10% of trace tail mean (~392.3).
6. 100-tick safety: no NaN, no negative internal species, no negative reported ring count.

## Open questions

- `TASK-SPECIFIC SCOPE` referenced `docs/karr_extracts/process/09_FtsZPolymerization.md`; repo canonical file is `25_FtsZPolymerization.md`.
- Worktree does not include `data/m1_sources/karr_native/per_process_traces`; trace is read from `/mnt/e/opencell/...`.
