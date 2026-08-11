# STATUS_L22_RIBOSOME_BRIDGE

## Scope

Bridge the existing hash-bound `docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/`
N=50 PASS into an L2.2-authority `latest_event/` bundle so
`scripts/l22_evidence/generator.py` can mechanically classify
`RibosomeAssembly` as `PASS` without:

- trusting stored verdict strings
- weakening the L2.2 mandatory-file contract
- routing the row through the Design-A runner/helper path
- editing the shared tracked `docs/phase_f/l2_2_design_a/evidence_index.json`

Authoritative contract used:

```yaml
name: RibosomeAssembly
harness_type: event_class
M_ticks: 200
N_seeds: 50
primary_channel: complexs
karr_artifact: per_process_traces_v2
```

## What Changed

- Added `scripts/l22_evidence/event_bridge.py`.
  It reads the existing L2.event RibosomeAssembly bundle, maps source event
  channel `count` onto the catalog primary channel `complexs`, converts raw
  event metrics into L2.2 mechanical fields, writes the full
  `latest_event/` authority set, and emits `sweep_provenance.json`.
- Split event-class staleness binding away from Design-A-only runner files.
  `event_class` rows now hash the event bridge/L2.event shared surfaces, plus
  RibosomeAssembly's event adapter/driver modules, instead of `runner`,
  `helpers`, `projections`, or `l2_replay_common.py`.
- Generated
  `docs/phase_f/l2_2_design_a/evidence_bundle/RibosomeAssembly/latest_event/`
  with:
  `result.json`, `input_manifest.json`, `provenance.json`, `thresholds.json`,
  `null_calibration.json`, `SUMMARY.json`, `analytical_check.json`,
  `sweep_provenance.json`.
- Added focused bridge tests that prove:
  raw metrics, not stored PASS strings, control the verdict;
  upstream event-bundle drift stales the row; and event-bridge source drift
  stales the row.

## Verification

Command:

```text
.\bin\oc-py.cmd scripts/l22_evidence/event_bridge.py
```

Actual:

- wrote bridged `latest_event` bundle at
  `docs/phase_f/l2_2_design_a/evidence_bundle/RibosomeAssembly/latest_event`

Command:

```text
.\bin\oc-pytest.cmd tests/scripts/test_l22_event_bridge.py -v
```

Actual:

- `4 passed`

Command:

```text
.\bin\oc-pytest.cmd tests/scripts/test_l22_evidence_generator.py -v
```

Actual:

- `7 passed`

Focused anti-staleness spot checks:

```text
.\bin\oc-pytest.cmd tests/scripts/test_l22_evidence_anticheat.py::test_l2_replay_common_change_stales_every_design_a_process_but_not_event_class -v
.\bin\oc-pytest.cmd tests/scripts/test_l22_evidence_anticheat.py::test_clean_baseline_evidence_is_green -v
.\bin\oc-pytest.cmd tests/scripts/test_l22_evidence_anticheat.py::test_projection_distance_primary_channel_is_missing_evaluator -v
```

Actual:

- all `3` targeted anticheat tests passed

Fresh branch-local generator run:

```text
.\bin\oc-py.cmd scripts/l22_evidence/generator.py generate --out tmpl22_ribosome_bridge_index.json
```

Actual tally:

```json
{
  "FAIL": 4,
  "MISSING_EVIDENCE": 3,
  "PASS": 15
}
```

This is the expected bridge effect:
`RibosomeAssembly` moves from `MISSING_EVIDENCE` to `PASS`, while
`Cytokinesis`, `DNADamage`, and `FtsZPolymerization` remain the three honest
`MISSING_EVIDENCE` rows.

## Proposed L2.2 Row

Generated from the fresh branch-local run above:

```json
{
  "process": "RibosomeAssembly",
  "bucket": "EVENT_CLASS",
  "harness_type": "event_class",
  "evidence_dir": "docs/phase_f/l2_2_design_a/evidence_bundle/RibosomeAssembly/latest_event",
  "mechanical_verdict": "PASS",
  "green": true,
  "channel_verdicts": {
    "complexs": "SEED_NOISE",
    "payload": "SEED_NOISE",
    "timing": "SEED_NOISE"
  },
  "catalog_soft_flags": {
    "M_ticks": 200,
    "N_seeds": 50,
    "closed_form_dominant": "false",
    "harness_type": "event_class",
    "in_scope_L2_2": true,
    "primary_channel": "complexs",
    "primary_distance": "per_tick_vector_w1_mean"
  },
  "reasons": [],
  "warnings": []
}
```

## Notes

- The bridge intentionally leaves the shared tracked
  `docs/phase_f/l2_2_design_a/evidence_index.json` unchanged. The
  coordinator still owns the final regeneration commit.
- The bridged row records `ticks = 200` from the authoritative L2.2
  contract. The upstream event-window MATs remain `100` ticks wide at
  `tick_offset = 200`; that source-window detail is preserved in the bridged
  `input_manifest.json` and `result.json` metadata.
- I did not run the full strict-rubric integrity audit against the committed
  tracked index, because this branch intentionally does not regenerate that
  coordinator-owned file.
