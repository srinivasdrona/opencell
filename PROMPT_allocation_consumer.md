# PROMPT — v6 allocation-consumer enrollment

## Scope (one Codex turn)

chassis_v6 wired RnaDecay and HostInteraction into the topology but did NOT enroll them as `KarrAllocationStep` consumers (deliberately deferred during the v6 turn to avoid emitting new UserWarnings against restricted modules). This turn enrolls them properly and confirms full mass-balance accounting across all allocation consumers.

**Token budget**: 60k. **Checkpoints**: 4. **Worktree**: `E:\opencell-worktrees\allocation-consumer` (branch `agent/allocation-consumer-enrollment`).

**DO NOT START** until both pre-conditions hold:
1. E.1 has merged to main (so the v6 trajectory fixture is banked and won't be invalidated by this turn).
2. skip-drift audit has merged (so test count baseline is stable).

## Pre-reading (in this order)
1. `SESSION_CONTEXT.md` — all 11 hard rules
2. `opencell/vivarium/karr_allocation_step.py` — request/allocate contract + `_default_consumer_processes()`
3. `opencell/vivarium/karr_protein_decay_light.py` — minimal consumer pattern
4. `opencell/vivarium/karr_rna_decay.py` — current state (substrate writes happen, NO request/alloc cycle)
5. `opencell/vivarium/karr_host_interaction.py` — current state
6. `opencell/vivarium/karr_composite.py` — `build_karr_chassis_v6` + `CHASSIS_V6_EXPECTED_PROCESS_KEYS`
7. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNADecay.m` — Karr's substrate consumption pattern (H2O for hydrolysis)
8. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/HostInteraction.m` — Karr's substrate-touch list

## Tasks

### Checkpoint 1 — Inventory substrate consumption (read-only)
- For RnaDecay: enumerate which substrate WIDs are consumed/produced per decay event. Karr's `.m` source lists the hydrolysis stoichiometry; document inline in the next checkpoint's diff.
- For HostInteraction: enumerate substrate touches (Karr's HostInteraction.m is small — mostly inhibition/binding bookkeeping; may have zero substrate consumers, in which case skip its enrollment and document why in STATUS.md).
- Write findings to `docs/design/allocation_consumer_enrollment.md`.
- Commit: `docs: allocation-consumer enrollment inventory`.

### Checkpoint 2 — Wire RnaDecay as allocation consumer
- Update `karr_rna_decay.py` to emit `requests.rna_decay.<wid>` for the substrates it consumes (typically H2O).
- Read `substrates_allocated.rna_decay.<wid>` and bound decay rate by allocated amount.
- Update `_default_consumer_processes()` in `karr_allocation_step.py` to include `("rna_decay", [<wids>])`.
- Narrow tests: `pytest -x tests/vivarium/test_karr_rna_decay.py tests/vivarium/test_karr_allocation_step.py -W error::UserWarning`.
- Commit: `karr_rna_decay: enroll as allocation consumer`.

### Checkpoint 3 — Wire HostInteraction (or document deferral)
- If HostInteraction has substrate consumption: same pattern as Checkpoint 2.
- If it doesn't: document in `docs/design/allocation_consumer_enrollment.md` why no enrollment is needed (e.g., "Karr's HostInteraction only writes to host/cell-fate flags, no shared-substrate consumption").
- Narrow tests for whatever changed.
- Commit: either `karr_host_interaction: enroll as allocation consumer` OR `docs: host_interaction allocation enrollment N/A`.

### Checkpoint 4 — Full chassis_v6 regression + commit
- Update `build_karr_chassis_v6` consumer list in `karr_composite.py` if changed.
- Run `tests/vivarium/test_chassis_v6_*.py` (full v6 smoke suite).
- Run full suite: `pytest -x -q` — MUST end in same pass count as pre-turn baseline (no regressions, no new xfails, no new UserWarnings).
- Update `docs/design/allocation_consumer_enrollment.md` with final mass-balance summary.
- Commit: `chassis_v6: rna_decay + host_interaction allocation enrollment complete`.

## Acceptance criteria
1. `KARR_ALLOCATION_CONSUMERS` registry includes rna_decay (and host_interaction if applicable).
2. No new UserWarnings introduced.
3. Full suite pass count unchanged from pre-turn baseline (currently 877 + whatever skip-drift recovered).
4. `docs/design/allocation_consumer_enrollment.md` documents the Karr-source citation for every consumed WID per process.
5. STATUS.md final block: files changed, test results, mass-balance check (substrate deltas sum to ~0 over a 1000-tick run of chassis_v6).

## Out of scope (DO NOT do)
- Do not modify allocation algorithm (Karr proportional fair-share is locked).
- Do not touch karr_replication, karr_d2 (macromolecular_complexation), karr_metabolism wiring.
- Do not refactor karr_composite.py beyond updating the consumer list.
- Do not run the full v6 32400-tick trajectory (E.1 owns that).
