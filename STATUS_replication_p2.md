2026-06-16T18:26:43Z Started replication p2 continuation on HEAD 2018008; read SESSION_CONTEXT.md and isolated the failing initiation seed assertion in `test_karr_replication.py`.
2026-06-16T18:28:00Z Inspected `opencell/vivarium/karr_replication.py`, `opencell/state/chromosome_store.py`, and the mirrored Karr `Replication.m` / `Chromosome.m` sources to trace initiation polymerizedRegions semantics.
2026-06-16T18:30:48Z Patched `_seed_polymerized_regions()` to seed the zero-progress fork-compatible sparse triple and drop the duplicate ORI-side zero-position daughter entry introduced by naive 1-based-to-0-based normalization.
2026-06-16T18:33:10Z Patched `_resolve_chromosome_store()` to rebuild `polymerizedRegions` from `fork_position_bp` when the legacy scalar mirror is ahead of the sparse triple, preserving completion and resumed-elongation behavior.
2026-06-16T18:33:40Z Corrected non-replay elongation stoichiometry so dNTP demand consumes 2 nucleotides per bp advanced across both forks, matching the existing design and mass-balance test contract.
2026-06-16T18:35:45Z Required verification green: `bin/oc-pytest tests/vivarium/test_karr_replication.py -x -v` (7 passed) and `bin/oc-pytest tests/vivarium/test_karr_replication_l2_replay.py -x -v` (1 passed).

Final block:
Files changed: `opencell/vivarium/karr_replication.py`, `STATUS_replication_p2.md`
Test results: `tests/vivarium/test_karr_replication.py` 7 passed; `tests/vivarium/test_karr_replication_l2_replay.py` 1 passed
Blockers: none
