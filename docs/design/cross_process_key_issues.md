# Cross-Process Key Issues

## CPK-001
- Severity: BLOCKER
- Leaf path: `chromosome.segregation_progress`
- Processes involved: `pc-t5` (`karr_chromosome_segregation.py`), `pc-t9` (`karr_cytokinesis.py`)
- What each says:
  - `pc-t5` declares `_updater: "accumulate"` and writes per-tick deltas.
  - `pc-t9` declared `_updater: "set"` on the same leaf while reading it as a gate input.
- Proposed fix: align `pc-t9` declaration to `_updater: "accumulate"`.
- Confidence: HIGH
- Status: FIXED in this turn.

## CPK-002
- Severity: BLOCKER-NEEDS-DESIGN
- Leaf path: `chromosome.damage_sites`
- Processes involved: `pc-t6` (`karr_dna_damage.py`), `pc-t7` (`karr_dna_repair.py`)
- What each says:
  - `pc-t6` declares `_updater: "accumulate"` and appends newly created lesions.
  - `pc-t7` declares `_updater: "set"` and writes a replacement list after removing repaired lesions.
- Proposed fix: orchestrator design call to pick one canonical representation/update protocol (recommended: map/set semantics with one updater contract), then align both processes and tests together.
- Confidence: HIGH
- Status: NOT PATCHED (requires process-logic changes, not schema-only).

## CPK-003
- Severity: BLOCKER-NEEDS-DESIGN
- Leaf path: `chromosome.fork_position_bp.*` vs `chromosome.fork_positions`
- Processes involved: `pc-t2` (`karr_replication.py`), `pc-t6` (`karr_dna_damage.py`)
- What each says:
  - `pc-t2` declares/writes `chromosome.fork_position_bp.left/right`.
  - `pc-t6` declares/reads `chromosome.fork_positions`.
- Proposed fix: choose one canonical fork-position path and apply a coordinated declaration + logic alignment in both processes.
- Confidence: HIGH
- Status: NOT PATCHED (schema-only changes are insufficient).

## CPK-004
- Severity: BLOCKER-NEEDS-DESIGN
- Leaf path: n/a (module-level gap)
- Processes involved: `pd-t1` (`opencell/vivarium/karr_host_interaction.py` expected), `docs/design/pd-t1-host-interaction.md` expected
- What each says:
  - Prompt scope expects pd-t1 landed today.
  - This worktree has no pd-t1 process module and no pd-t1 per-process design doc.
- Proposed fix: land pd-t1 artifacts first, then rerun this cross-process audit including pd-t1 keys.
- Confidence: HIGH
- Status: NOT PATCHED (artifacts absent).

## CPK-005
- Severity: INFO
- Leaf path: substrate/request key casing
- Processes involved: `pc-t1` to `pc-t10` scanned
- What each says: no mixed-case duplicates found (no `ATP` vs `atp` conflicts detected).
- Proposed fix: none.
- Confidence: HIGH

## CPK-006
- Severity: INFO
- Leaf path: `chromosome.replication_state`
- Processes involved: `pc-t1`, `pc-t2`, `pc-t3`, `pc-t4`, `pc-t5`, `pc-t6`
- What each says: declarations and in-code comparisons are consistent with string-domain usage (`idle`, `initiating`, `elongating`, `complete`).
- Proposed fix: none.
- Confidence: MED
