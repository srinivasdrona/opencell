# Phase D Turn 1 — HostInteraction

**Status**: design ready · **Estimated wall**: 45 min · **Karr process**: `Process_HostInteraction`

## Why this is Phase D Turn 1

`HostInteraction` is the only remaining biological process after Phase C in the
project plan. It models adhesion and host-interface state transitions for
*M. genitalium* once terminal organelle machinery is available.

For this turn we implement a Karr-light process that captures adhesion dynamics
as aggregate stochastic binding/unbinding events while preserving Vivarium
allocation/mass-balance contracts.

## Primary sources

- Karr extract: `docs/karr_extracts/process/27_HostInteraction.md`
  - Note: task text references `28_HostInteraction.md`, but this repo contains
    `27_HostInteraction.md` and `28_TerminalOrganelleAssembly.md`.
- Karr fixture: `data/karr_fixtures/per_process/HostInteraction_flat.mat`
- Karr native trace target (if present locally):  
  `data/m1_sources/karr_native/per_process_traces/HostInteraction_100ticks.mat`

## Algorithm (Karr-light v1)

Karr docstring logic is qualitative/boolean and centers on adhesion requiring a
properly formed terminal organelle and adhesin expression. This turn maps that
to a stochastic aggregate-adhesion model:

1. Read terminal-organelle and adhesin readiness from:
   - `cell.terminal_organelle_count`
   - mature protein counts for HostInteraction fixture proteins
2. Compute an adhesion-capability scalar in `[0, 1]`.
3. Simulate per-tick stochastic events:
   - bind events ~ Poisson(`k_bind * capability * free_sites * dt`)
   - unbind events ~ Poisson(`k_unbind * bound_sites * dt`)
4. Bound bind events by allocated ATP (`KarrAllocationStep` contract).
5. Emit:
   - `cell.host_adhesion_strength` as an accumulate delta (`[0, 1]` bounded)
   - `cell.host_attached` as set bool (`True` if strength >= threshold)
   - `substrates.ATP` negative accumulate delta for ATP consumption
   - next-tick ATP request in `requests.karr_host_interaction.ATP`

## Vivarium ports / new state

New `cell` state leaves:

- `cell.host_adhesion_strength` (float; accumulate; emitted)
- `cell.host_attached` (bool; set; emitted; sole-writer state machine)
- `cell.terminal_organelle_count` (float/int input; accumulate schema for shared store compatibility)

Other ports:

- `protein.counts` for required host-interaction proteins
- `substrates.ATP` (accumulate consumption)
- `requests.karr_host_interaction.ATP` (set)
- `substrates_allocated.karr_host_interaction.ATP` (accumulate/read)

## Substrate consumption

Karr-light v1 models small ATP cost per successful adhesion bond event:

- `ATP consumed = atp_per_binding_event * n_bind_applied`
- no additional hydrolysis products emitted in v1 (documented deferment)

## Scope

### In scope (v1)

- New process: `opencell/vivarium/karr_host_interaction.py`
- Aggregate stochastic adhesion/unbinding
- ATP allocation contract integration
- Standalone operation when Phase C `terminal_organelle_count` producer is absent

### Deferred to v2

- Full host boolean cascade (`isTLRActivated`, `isNFkBActivated`, inflammatory response)
- Per-receptor/per-protein docking states
- Explicit ATP hydrolysis coproduct bookkeeping (`ADP`, `Pi`, `H+`, `H2O`)
- Strict calibration against native trace internals beyond attach/detach rates

## Test plan

1. Process instantiates and exposes expected stores/fixture mappings.
2. One-tick positive-capability state yields non-negative adhesion delta and ATP demand.
3. Allocation contract: ATP-limited allocation caps bind events and ATP consumption.
4. 100-tick run approaches bounded steady-state adhesion within expected envelope.
5. Deterministic replay with same seed produces identical updates.
6. No NaN / no negative adhesion strength regressions over long runs.

## Open questions

1. Native `HostInteraction_100ticks.mat` is gitignored/missing in this worktree;
   v1 should auto-load rates when available and otherwise use documented defaults.
2. Whether `cell.host_attached` should use hysteresis (attach threshold != detach threshold)
   is deferred unless trace evidence requires it.
