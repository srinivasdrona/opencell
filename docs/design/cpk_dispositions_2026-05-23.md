# CPK Findings — Orchestrator Dispositions (2026-05-23)

Resolves CPK-002 and CPK-003 from `docs/design/cross_process_key_issues.md`.
CPK-001 already fixed in audit turn. CPK-004 already fixed via re-merge (`8dd146d`).
CPK-005, CPK-006 are INFO-only — no action.

## CPK-002 — `chromosome.damage_sites` updater conflict

### The conflict
- `karr_dna_damage.py` (DamageProcess): writes appended damage events with `_updater: "accumulate"`
- `karr_dna_repair.py` (RepairProcess): writes a replacement list (post-repair) with `_updater: "set"`

These are two legitimate but incompatible mental models on one leaf.

### Disposition: split into two owned leaves

```
chromosome.damage_events_cumulative  : accumulate, owned by DamageProcess only
chromosome.repair_events_cumulative  : accumulate, owned by RepairProcess only
chromosome.damage_sites              : DERIVED VIEW, computed lazily by a thin "chromosome aggregator" process or by reader-side helper
```

Rationale:
- Each writer owns one leaf with one updater (matches `fix-set-accumulate-warnings` rule)
- Both event streams are preserved (matches Karr semantics: damage AND repair are observable phenotypes; we shouldn't lose either)
- Readers (e.g. trajectory comparator, E.2 KP14/KP15) compute the current damage set as `damage_events - repair_events`
- Storage cost is small (events are sparse, indexed by genome position + tick)

### Out-of-the-box alternative (rejected)
Option B (single `damage_sites` leaf as `set` semantics, with a small "damage manager" coordinator process driving both add/remove): rejected because it adds a fourth small process and tangles ownership. Splitting is simpler.

### Implementation sketch (for future Codex turn `agent/cpk-002-damage-split`)

1. In `karr_dna_damage.py`:
   - Rename schema leaf `chromosome.damage_sites` → `chromosome.damage_events_cumulative`
   - Keep `_updater: "accumulate"`
2. In `karr_dna_repair.py`:
   - Rename schema leaf `chromosome.damage_sites` → `chromosome.repair_events_cumulative`
   - Change `_updater: "set"` → `_updater: "accumulate"`
   - Repair process emits `repair_events_cumulative += <newly repaired lesions>` instead of writing back the post-repair list
3. Add helper `opencell.vivarium.chromosome_views.current_damage_sites(state)`:
   ```python
   def current_damage_sites(state):
       d = state["chromosome"]["damage_events_cumulative"]
       r = state["chromosome"]["repair_events_cumulative"]
       return [lesion for lesion in d if lesion["id"] not in {x["id"] for x in r}]
   ```
4. Update any reader (tests, E.2 KP15 extractor) to use the helper.
5. Migration: update existing tests that asserted `chromosome.damage_sites` directly to use the helper.

Estimated effort: ~30 min Codex turn, 60k token budget, one branch.

### Priority
**P1** — blocks any clean E.1 trajectory comparison of damage observables; should ship before E.2 fixture build.

## CPK-003 — fork position path collision

### The conflict
- `karr_replication.py`: writes `chromosome.fork_position_bp.left` and `chromosome.fork_position_bp.right` (dict with `left`/`right` keys, each `int` bp)
- `karr_dna_damage.py`: reads `chromosome.fork_positions` (path doesn't exist in writer schemas)

Result: `dna_damage` always reads a default/empty value for fork positions → no collision-induced damage logic runs. Silent semantic gap.

### Disposition: align `dna_damage` reader to canonical writer path

Pick `chromosome.fork_position_bp.*` as canonical (more informative, semantically explicit about left/right fork orientation, already the writer's API).

### Implementation sketch (`agent/cpk-003-fork-position-path`)

1. In `karr_dna_damage.py`:
   - Change reader schema: replace `chromosome.fork_positions` with explicit `chromosome.fork_position_bp.left` and `.right`
   - Update read code: `fork_left = state["chromosome"]["fork_position_bp"]["left"]; fork_right = ...`
   - Collision detection logic uses both
2. Optionally add `chromosome.fork_positions` as a DERIVED view (a list `[left_bp, right_bp]`) in `chromosome_views.py` for legacy callers, but only if needed by ≥2 readers. Single-reader case = just align directly.
3. Add test asserting `dna_damage` actually reads non-default fork positions during replication (regression for the silent gap).

Estimated effort: ~20 min Codex turn, 40k tokens, one branch.

### Priority
**P1** — quietly degrades replication-coupled damage modeling; affects E.1 fork-progress + E.2 KP11/KP12/KP14.

## Combined dispatch plan

After naming-drift ships and chassis_v6 wiring lands, dispatch CPK-002 + CPK-003 fixes in parallel (independent branches, different files). Total wall-time: ~30 min in parallel.

Alternative: bundle into chassis_v6 prompt as "before final wiring, also resolve CPK-002 and CPK-003 per disposition doc." Costs more tokens in the v6 turn but saves a dispatch cycle. **Recommendation: bundle** — v6 turn touches the chromosome.* topology anyway, so fixing the schemas in the same turn is cheaper context-wise.

## Tracking todos

After this doc lands, add to opencell_tasks.db:
- `cpk-002-damage-split` (P1, owner: chassis_v6 turn)
- `cpk-003-fork-position-path` (P1, owner: chassis_v6 turn)
