# Phase E.2 Scorecard Emitter Gaps

This document captures Phase E.2 KPs that cannot be extracted from the current wave-2 artifact schema without emitter changes.

## KP15 - DNA-binding occupancy dynamics

- Status: `NEEDS_EMITTER`
- Why extractor cannot run: `trajectory.pkl` snapshots expose only scalar state observables and do not include chromosome occupancy structures. No sibling CSV currently emits occupancy traces.
- Required emitter field(s): `snapshots[*].state.chromosome.complex_bound_sites`
- Minimum expected schema:

```json
{
  "tick": 1200,
  "time_s": 1200.0,
  "state": {
    "chromosome": {
      "complex_bound_sites": {
        "RNAP-0001": [12345, 12346],
        "DnaA-oriC": [391245]
      }
    }
  }
}
```

- Disposition TODO: `E2-V1_1-KP15-DNA-OCCUPANCY`
