# Open Questions — Decision Sheet (2026-05-23)

Pre-answers for the 9 open questions raised by the v5 and v6 design docs.
Recorded here so the orchestrator can unblock integration sessions instantly
if any of them STATUS-out asking, and so the answers are durable.

## chassis_v5 (pc-final-chassis-v5)

### v5-OQ1 — Confirm final module filenames / class names for pc-t2..pc-t10

**Decision: use the names that already landed today (factual lookup, not a choice).**

| Turn | Module file | Class name (from STATUS.md) |
|---|---|---|
| pc-t2 | `opencell/vivarium/karr_replication.py` | `KarrReplicationProcess` |
| pc-t3 | `opencell/vivarium/karr_dna_supercoiling.py` | `KarrDNASupercoilingProcess` (assumed) |
| pc-t4 | `opencell/vivarium/karr_chromosome_condensation.py` | `KarrChromosomeCondensationProcess` (assumed) |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `KarrChromosomeSegregationProcess` (assumed) |
| pc-t6 | `opencell/vivarium/karr_dna_damage.py` | `KarrDNADamageProcess` (assumed) |
| pc-t7 | `opencell/vivarium/karr_dna_repair.py` | `KarrDNARepairProcess` (assumed) |
| pc-t8 | `opencell/vivarium/karr_ftsz_polymerization.py` | `KarrFtsZPolymerizationProcess` (assumed) |
| pc-t9 | `opencell/vivarium/karr_cytokinesis.py` | `KarrCytokinesisProcess` |
| pc-t10 | `opencell/vivarium/karr_terminal_organelle_assembly.py` | `KarrTerminalOrganelleAssemblyProcess` |
| pd-t1 | `opencell/vivarium/karr_host_interaction.py` | `KarrHostInteractionProcess` (assumed) |

Audit session (`agent/audit-cross-process-keys`) will produce the authoritative
matrix. Integration session pc-final should `grep -rn "class Karr" opencell/vivarium/karr_*.py`
to confirm exact class names — no orchestrator call needed.

### v5-OQ2 — Phase C requests: direct process writes vs new request-calculator step?

**Decision: direct process writes, matching the pc-t1 pattern already shipped.**

Rationale: pc-t1 ReplicationInitiation writes `requests.<proc>.<sub>` directly in
its `next_update`; the 10 new processes all followed that pattern (their per-turn
STATUS.md confirms `requests`/`substrates_allocated` contract per-process). A
new request-calculator step would be over-engineering Karr-light v1. Revisit
only if Phase E.1 trajectory drift traces to allocation-timing artifacts.

### v5-OQ3 — Chromosome coordinate schema (left/right nt scalar vs region-index)?

**Decision: keep left/right nt scalar for v5. Region-index deferred to v2.**

Rationale: pc-t2 already implemented fork tracking as `left/right` bp scalars
per its design doc. Region-index representation is needed only when DNA-binding
occupancy processes (KP15) need per-region accounting; that's a Phase E.2
phenotype-match concern, not a v5 integration blocker. Karr's reference
trajectory exposes scalar fork position, so this is even faithfully comparable.

### v5-OQ4 — Target tick windows for replication completion + division

**Decision: extract from `data/m1_sources/karr_native/cell_cycle_trajectory.mat`
via the pe-1 loader. Initial tolerance bands per A6 semantics contract.**

Concrete extraction recipe (pe-1 already shipped `opencell/validation/karr_trajectory.py`):
```python
from opencell.validation.karr_trajectory import load_karr_trajectory
t = load_karr_trajectory()
# replication completion = first tick where chromosome.polymerized_regions == full
# division = first tick where cell.division_event fires
```

Tolerance: ±30% (medium bucket per v6's per-bucket-tolerance table). Tighten
later when phenotype-match (Phase E.2) lands.

### v5-OQ5 — CellCycleCoordinator location: inside karr_composite.py or dedicated module?

**Decision: dedicated module `opencell/vivarium/karr_cell_cycle_coordinator.py`.**

Already specified this in the pc-final prompt. Rationale: it's a Step (not a
Process) and has its own state-machine logic worth ~150-300 LOC; embedding it
in karr_composite.py would push that file past 1500 LOC and conflate wiring
with control logic.

## chassis_v6 (pd-final-chassis-v6)

### v6-OQ1 — TerminalOrganelle vs HostInteraction extract numbering (27/28 mismatch)

**Decision: extract numbering follows Karr's original SimulationFixture process
order (27=TerminalOrganelle, 28=HostInteraction). Vivarium process ordering is
independent — set by topological/dependency order, not Karr index.**

Action: rename docs if needed for clarity, but the integration code MUST NOT
depend on extract-file numbering for execution order. Use Vivarium's
topological order from explicit before/after declarations.

### v6-OQ2 — Host adhesion gating policy for v1

**Decision: ACCEPT the v6 design's recommended default — non-gating in v1.**

HostInteraction emits observables only. CellCycleCoordinator does NOT block
replication/cytokinesis/growth on adhesion. The `host_adhesion_gates_division`
feature flag stays defined but defaults `False`. Karr's published model has no
gating mechanism documented; adding one would be biology-beyond-Karr in v1.

### v6-OQ3 — KP01..KP28 stable labels for scorecard

**Decision: ADOPT the KP01-KP28 table in pd_final_chassis_v6.md (lines 144-173) as canonical.**

Action: pe-1 trajectory_compare.py and any pd-final scorecard test must
import a single shared registry (recommend
`opencell/validation/phenotype_registry.py`) that maps KP id → store path →
extractor function. If that registry doesn't exist post-pd-final-integration,
file a Phase E.2 prep todo.

### v6-OQ4 — Process key names for Phase C + RNADecay before pc-final implementation

**Decision: same as v5-OQ1. pc-final session should grep the actual class names; no
orchestrator call needed. The pd-final session was told to do the same via its prompt.**

## Cross-cutting performance budget reality check

v6 design assumes ~62 ticks/s from chassis_v4 baseline. Adding 10+1 processes
will likely halve that to ~30 ticks/s. 32400 ticks @ 30 ticks/s ≈ 18 min ≈
CI-borderline. The v6 design's `xfail("perf-budget v2")` escape hatch is the
right answer — don't try to optimize today. Phase E.2 / E.3 can profile.

## Risks I'm NOT pre-deciding (need orchestrator + design pass)

These are genuine future design calls, not factual lookups:

- **Cross-process state-key BLOCKERS** if the audit session (agent/audit-cross-process-keys)
  finds severity-BLOCKER-NEEDS-DESIGN issues. Examples that would matter:
  - pc-t9 cytokinesis expects `cell.ftsz_ring_complete` (bool); pc-t8 ftsz writes a different name/type
  - pc-t5 segregation expects `chromosome.replication_state == "complete"` but pc-t2 uses a different enum
  - Multiple processes claim ownership of `chromosome.replication_state` updater
- **CellCycleCoordinator transition ambiguity**: e.g., what if replication
  completes BEFORE FtsZ ring assembly? Karr's published trajectory should answer this empirically — pe-1 can extract the actual ordering.
- **Phase E.1 trajectory drift > 50%** — could mean Karr-light scope is too
  light. Mitigation: document, don't fix in v1. Bucket as
  `karr-known-incomplete` and revisit in Phase E calibration.
