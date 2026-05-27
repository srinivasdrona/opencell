# STATUS: Track-F / Track-A (Per-process Karr fidelity scorecard)

Date: 2026-05-27
Branch: `trackF/karr-fidelity-trackA`

## Outcome summary

- Replay loader now strips replay prefixes in `.npz` fixtures so `state_before__X` / `states_after__X` channels map to port-shaped keys (`X`) before `next_update`.
- Cytokinesis replay smoke remains `xfail(strict=True)` with a documented known gap.
- Scorecard emitted for all 28 replay fixtures:
  - PASS: 15
  - PARTIAL: 1
  - FAIL: 0
  - SKIP: 12
- Required adapters with rich data are PASS/PARTIAL:
  - ChromosomeCondensation: PASS
  - Cytokinesis: PASS
  - FtsZPolymerization: PARTIAL
  - ProteinTranslocation: PASS
  - Metabolism: PASS

## Files changed

- `opencell/validation/replay.py`
- `tests/unit/test_replay_loader.py`
- `tests/integration/test_replay_fixture_loaded.py`
- `tests/integration/test_replay_smoke.py`
- `docs/phase_e/karr_fidelity_known_gaps.md`
- `scripts/karr_fidelity_scorecard.py`
- `docs/phase_e/karr_fidelity_scorecard.md`
- `artifacts/karr_fidelity_scorecard.json`
- `tests/integration/test_karr_fidelity_scorecard.py`
- `STATUS_karr_fidelity_trackA.md`

## Irreducible gaps / v1.x follow-ups

- Cytokinesis smoke mismatch:
  - Fixtures provide state snapshots (`boundEnzymes`, `enzymes`, `substrates`), while the process emits request deltas; no direct output-key overlap for a strict one-tick replay assertion.
  - Documented in `docs/phase_e/karr_fidelity_known_gaps.md`.
- Track-B replay fixture quality:
  - `Transcription`, `Translation`, `RNADecay`, `Replication`, `ReplicationInitiation` are marked SKIP with:
    `1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract.`
- Adapter coverage:
  - `TerminalOrganelleAssembly`, `HostInteraction` are SKIP (no Track-A Vivarium replay adapter wiring in this scorecard pass).
