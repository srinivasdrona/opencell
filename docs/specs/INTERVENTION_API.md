# Intervention API Specification (forward-looking, no implementation)

**Status:** SPEC ONLY (Day 32, 2026-06-18) — implementation deferred to Post-L5.
**Purpose:** Define a domain-agnostic perturbation API now so the implementation
when it lands is a fulfillment of this contract, not a fresh design exercise.
The spec also acts as a **tripwire**: any biology-touching code change that
cannot be expressed as an `Intervention` is a candidate biology-leak.

## Design intent (DAP Beat 1)

Contract:
- Required behavior: any perturbation of any simulation state — knockouts,
  parameter throttles, nutrient shifts, RNG re-seeding, freeze/thaw of
  sub-systems — must be expressible as an `Intervention` instance applied
  to the running engine.
- Done = (property statement): given an `Intervention` and a running
  simulator, the engine applies the operation at the declared time window
  with the declared repeat policy, with no biology-specific knowledge in
  the engine itself.

Falsifiable expectation (Beat 3):
- If this spec is correct, an RL agent doing gene knockouts and a chemical
  reactor simulator throttling reactant flow use the **same API**, with
  only the `target_path` and `value` types differing.

Inversion (Beat 4):
- Failure mode: spec gets retrofitted to fit existing biology-specific
  perturbation code post-L5, baking biology back in. Mitigation: write
  the spec NOW, before any perturbation code exists; future code must
  conform to spec, not vice versa.

## The class

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any

class Operation(Enum):
    SET = "set"          # assign value directly: state[path] = value
    SCALE = "scale"      # multiply: state[path] *= value
    DELTA = "delta"      # add: state[path] += value
    FREEZE = "freeze"    # prevent any process from modifying state[path]
    UNFREEZE = "unfreeze"  # release a prior freeze

class RepeatPolicy(Enum):
    ONE_SHOT = "one_shot"        # apply once at start of time_window
    EVERY_TICK = "every_tick"    # apply on every tick within time_window
    AT_INTERVAL = "at_interval"  # apply at intervals (see interval_s)

@dataclass(frozen=True)
class Intervention:
    target_path: tuple[str, ...]
    """Path into the simulator's state tree.
    Examples:
      - Biology: ("protein", "counts", "MG_001_MONOMER")
      - Chemistry: ("reactor", "concentrations", "glucose")
      - Traffic: ("intersection", "5", "signal_phase")
      - Economics: ("agent", "42", "wealth")
    """

    operation: Operation
    value: Any
    time_window: tuple[float, float]
    repeat: RepeatPolicy = RepeatPolicy.ONE_SHOT
    interval_s: float | None = None
    metadata: dict[str, Any] | None = None
```

## Application semantics (per tick)

1. Pre-tick: apply FREEZE/UNFREEZE operations
2. Each process runs `next_update` (frozen paths are read-only)
3. Post-tick: apply SET/SCALE/DELTA operations
4. Trace metadata flags ticks with active interventions

## Conflict resolution

- SET vs SET → last-write-wins (warning emitted)
- SET vs DELTA → SET first, then DELTA on new value
- SCALE vs DELTA → SCALE first, then DELTA
- FREEZE vs mutation → mutation rejected, warning emitted

## Examples

### Biology: knockout a gene at t=1000s
```python
Intervention(
    target_path=("protein", "counts", "MG_001_MONOMER"),
    operation=Operation.SET, value=0,
    time_window=(1000.0, math.inf),
    repeat=RepeatPolicy.EVERY_TICK,
)
```

### Generic: throttle process rate during [100, 200]s
```python
Intervention(
    target_path=("processes", "transcription", "rate_scale"),
    operation=Operation.SET, value=0.5,
    time_window=(100.0, 200.0),
    repeat=RepeatPolicy.EVERY_TICK,
)
```

## Tripwire usage (the discipline)

When reviewing new code that perturbs simulation state, ask:

1. **Can the perturbation be expressed as an `Intervention`?**
   - YES → good (generic surface used)
   - NO → biology-leak suspected; investigate

2. **Is the target_path schema-driven (from TOML state_groups) or hardcoded?**
   - Schema-driven → good
   - Hardcoded → refactor to schema lookup

## Out of scope (now)

- `InterventionEngine` implementation
- Wiring into `KarrComposite`
- UI/CLI for declaring interventions
- Persistence/replay of intervention sequences

## Post-L5 implementation plan

1. Create `core/intervention.py` with the dataclasses above
2. Add `InterventionEngine` wrapping Vivarium's engine
3. Modify `KarrComposite.run` to accept `interventions: list[Intervention]`
4. Add per-tick pre/post hooks for FREEZE / SET / SCALE / DELTA
5. Emit intervention metadata per `data_emit_schema.yaml`
6. Add `MGenInterventionPresets` module for biology-specific presets:
   gene_knockout, nutrient_shift, etc.
