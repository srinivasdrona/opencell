# STATUS — L2.5 Pair Matrix

- 2026-06-18T11:54:04Z Started task; read SESSION_CONTEXT and Phase F inputs, confirmed 28 per-process TOMLs.
- 2026-06-18T11:54:04Z Noted catalog has no explicit validation_status field; script uses deterministic fallback and records filter mode.
- 2026-06-18T11:55:19Z Beat 1: added scripts/derive_l25_pair_matrix.py with TOML loading, pair overlap/tier classification, deterministic emit, and --check-only.
- 2026-06-18T11:55:56Z Beat 2: generated docs/phase_f/L2_5_PAIR_MATRIX.md (28x28 matrix and tier lists).
- 2026-06-18T11:56:08Z Beat 3: generated data/schemas/l25_pair_list.toml with sorted [[pairs]] entries and shared WID lists.
- 2026-06-18T11:57:27Z Beat 4: updated docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md to reference the generated artifacts as authoritative, with concrete counts and regenerate/check commands.
- 2026-06-18T11:57:27Z Verification: `bin\oc-py.cmd scripts/derive_l25_pair_matrix.py --check-only` reports up-to-date artifacts.

## Tier definitions

- Tier 1 (must pass for L2.5 green): substrate overlap >= 3 OR enzyme overlap >= 3.
- Tier 2 (should pass): substrate/enzyme overlap is 1-2.
- Tier 3 (informational): overlap exists only in RNAs/monomers/complexs.
- Disjoint: zero overlap across all canonical state groups.

## Actual counts from current 28 TOMLs

- total_processes = 28
- total_pairs_computed = 378
- shared_pool_pairs = 256
- disjoint_pairs = 122
- tier_1_pairs = 183
- tier_2_pairs = 72
- tier_3_pairs = 1
- l25_honest_required_pairs = 154
- consistency check: 256 + 122 = 378
