# Karr Fidelity Known Gaps

## Cytokinesis replay-smoke mismatch

- Date: 2026-05-27
- Affected test: `tests/integration/test_replay_smoke.py::test_replay_smoke_cytokinesis_one_tick`
- Current disposition: `xfail(strict=True)`

### Why this is currently irreducible

The replay fixture for `Cytokinesis` provides tick-series state snapshots for:

- `boundEnzymes`
- `enzymes`
- `substrates`

The Vivarium process `KarrCytokinesisProcess.next_update(...)` does not emit those
state channels directly on each tick. Its observed update payload is request-driven
(for example `requests/karr_cytokinesis/GTP`) and therefore has no key overlap with
the fixture's `states_after__*` snapshot keys.

With no shared output channel names, a direct one-tick numeric comparison is not
possible in this smoke test without introducing process-specific projection logic.

### Follow-up (v1.x)

Define process-specific replay adapters that project each process update into the
same semantic channel space as Track-B `states_after` fixtures (or regenerate
fixtures aligned to emitted Vivarium update channels).
