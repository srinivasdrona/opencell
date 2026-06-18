# STATUS: L25 ProcessSpec Wiring

## Scope
Wire all 20 missing `_ProcessSpec` entries in `tests/vivarium/l2_2_replay_common_v2.py`, verify 28 total entries, and run the 43 deterministic-stochastic (DS) pair tests.

## Constraints Check
- Python invocations use `bin\oc-py.cmd` / `bin\oc-pytest.cmd` only.
- Modified files limited to:
  - `tests/vivarium/l2_2_replay_common_v2.py`
  - `docs/phase_f/STATUS_l25_processspec_wiring.md`

## Beat Tracker
| Beat | Description | Status | Notes |
|---|---|---|---|
| 1 | Wire all 20 missing `_ProcessSpec` entries | COMPLETE | Imports + specs added; `_COMPOSITION_ORDER_V2` expanded to 28 names |
| 2 | Verify 28 entries + collect-only run | PENDING | Waiting on verification commands |
| 3 | Run all 43 DS pair tests + summarize | PENDING | Waiting on full run |
| 4 | (Conditional) Document new failure modes | PENDING | Will complete only if new modes appear |

## Wiring Notes
- Added all 20 requested process specs and expanded `_COMPOSITION_ORDER_V2` to include all 28 process names.
- Used per-process L2 replay test constants for process class, observables, WID attribute mapping, pass-through, and hint surfaces.
- Applied projection literals where trace vector cardinality differs from runtime observable cardinality (e.g. Metabolism substrates, Transcription substrates, ProteinActivation substrates, ProteinTranslocation monomers).

## Progress Log
- [2026-06-18 16:28:00 UTC] Loaded `SESSION_CONTEXT.md` and confirmed Hard Rule 17 naming discipline.
- [2026-06-18 16:28:00 UTC] Audited DS pair harness/test/status artifacts and identified unsupported-process gap as primary blocker.
- [2026-06-18 16:28:00 UTC] Wired 20 missing process specs and added required imports/order coverage in `l2_2_replay_common_v2.py`.
