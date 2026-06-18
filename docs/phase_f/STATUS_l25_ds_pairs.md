# STATUS: L2.5 Deterministic-Stochastic Pair Sweep

## Scope
Scaffold and run L2.5 honest-mode deterministic-stochastic pair tests using a
single parametrized test file and seed_0 only.

## Constraints Check
- Python invocations use `bin\oc-py.cmd` / `bin\oc-pytest.cmd` only.
- Harness/process/schema/catalog files are not modified.
- Pair source is `data/schemas/l25_pair_list.toml`.

## Beat Tracker
| Beat | Description | Status | Notes |
|---|---|---|---|
| 1 | Scaffold helper that generates DS pair tests programmatically | COMPLETE | Loader reads TOML and filters DS honest-required pairs |
| 2 | Generate all 43 DS pair test cases | COMPLETE | `pytest --collect-only` confirms 43 case IDs |
| 3 | Run all 43 and commit result table | PENDING | Not started |
| 4 | Conditional failure investigation documentation | PENDING | Execute only if failures occur |

## Progress Log
- [2026-06-18 14:21:55 UTC] Loaded SESSION_CONTEXT Hard Rule 17 and L2.5 reference docs.
- [2026-06-18 14:21:55 UTC] Parsed `l25_pair_list.toml`; verified DS honest-required pair count is 43.
- [2026-06-18 14:21:55 UTC] Added new test module scaffold at `tests/vivarium/test_l25_deterministic_stochastic_pairs.py`.
- [2026-06-18 14:25:21 UTC] Updated case IDs to explicit `ProcessA+ProcessB` labels.
- [2026-06-18 14:25:21 UTC] Ran collection for DS test file; `43 tests collected`.
