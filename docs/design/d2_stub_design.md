# D.2 Stub Design Proposal (Turn 1 + Turn 2 Resolutions)

## Scope and Intent

This proposal covers only the transient A3 step-1 `d2-stub`: seed
`complex.counts` defaults at `t=0` from snapshot data, then emit no updates.

Out of scope: real assembly/degradation logic, D.2-real port design, or
test-infra expansion.

## 1. Vivarium Class Choice

Choice: **`Process`** (not `Step`, `Deriver`, or composer-only loader).

Why:
- Matches existing chassis pattern (`opencell/vivarium/karr_m1.py`,
  `karr_m2.py`, `karr_m3.py`): same explicit `ports_schema()` and
  `next_update()`.
- `ports_schema` is the cleanest place to register 149 leaves with
  `_default`, `_updater`, `_emit`.
- Stub behavior is naturally represented as `next_update(...) -> {}`.
- Keeps D.2 wiring symmetric with other chassis processes inside
  `karr_composite.py`.

## 2. WID Enumeration Source (Data Path + Filter)

### Primary derivation path for D.2-owned complex IDs

Read these fixture fields:
- `data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat`
  - `data.fixture.complexWholeCellModelIDs`
- `data/karr_fixtures/per_process/RibosomeAssembly_flat.mat`
  - `data.fixture.complexWholeCellModelIDs`

Filter:
1. Start from `MacromolecularComplexation.fixture.complexWholeCellModelIDs`.
2. Union in `RibosomeAssembly.fixture.complexWholeCellModelIDs`.
3. Sort deterministically for stable schema/test ordering.

Expected size from current fixtures: **149** unique WIDs.

### Provenance cross-check (ownership histogram)

To validate the “882 form-entries” ownership ground fact, cross-check:
- `data/karr_fixtures/per_process/ProteinComplex_flat.mat`
  - `data.fixture.formationProcesses`
- `data/karr_fixtures/per_process/Metabolite_flat.mat`
  - `data.fixture.processWholeCellModelIDs` (1-based process-ID name table)

This confirms `Process_MacromolecularComplexation` owns 882/1206 form rows.

## 3. Snapshot Value Source (Mature Counts)

Use `ProteinComplex_flat.mat` as the count source:
- `data.fixture.wholeCellModelIDs` (1206 form rows; repeated by form-state)
- `data.fixture.matureIndexs` (201 mature row indices, 1-based)
- `data.fixture.compartments` (primary compartment index per form row, 1-based)
- `data.fixture.counts` (`[1206, 6]`, per-form by-compartment snapshot counts)

Design snippet (illustrative only):

```python
from scipy.io import loadmat
import numpy as np

pc = loadmat(
    "data/karr_fixtures/per_process/ProteinComplex_flat.mat",
    squeeze_me=True,
    struct_as_record=False,
)["data"].fixture

form_wids = np.asarray(pc.wholeCellModelIDs, dtype=object).ravel().astype(str)
mature_rows = np.asarray(pc.matureIndexs, dtype=np.int64).ravel() - 1
comp_cols = np.asarray(pc.compartments, dtype=np.int64).ravel() - 1
counts = np.asarray(pc.counts, dtype=np.float64)

mature_count_by_wid = {
    form_wids[row]: float(counts[row, comp_cols[row]])
    for row in mature_rows
}
```

Then seed only the D.2-owned WID subset from `mature_count_by_wid`.

## 4. Compartment Handling

Decision: **do not carry compartment as an explicit port dimension in the
stub**.

Reasoning:
- Existing chassis convention is flat keyed stores (`rna.counts.<wid>`,
  `protein.counts.<wid>`, `substrates.<wid>`), not `(wid, compartment)` tuples.
- A3 requires alignment with flat topology patterns.
- Stub projects the snapshot’s compartmented matrix to one scalar per WID using
  the mature row’s primary compartment (`compartments[row]`).

Resulting store shape:
- `complex.counts.<wid>` as flat leaves (no nested compartment keys).

## 5. Port Schema Sketch

`ports_schema(self)` shape:

```python
{
    "complex": {
        "counts": {
            "<WID_1>": {
                "_default": <snapshot_count_float>,
                "_updater": "accumulate",
                "_emit": True,
            },
            # ... one leaf per D.2-owned WID (149 total)
        }
    }
}
```

`next_update(self, timestep, states)` returns `{}` always.

## 6. karr_composite Wiring Plan

Integrate in:
- `opencell/vivarium/karr_composite.py`
  - function: `build_karr_m1_m2_m3_engine(...)`

Wiring changes:
1. Instantiate `d2_stub_proc` alongside M1/M2/M3 process objects.
2. Add process entry, e.g. `"d2_stub": d2_stub_proc`.
3. Add topology entry:
   - `"d2_stub": {"complex": ("complex",)}`
4. Keep existing M1/M2/M3 topology and state wiring unchanged.

No changes needed in `build_karr_m1_m2_engine(...)` for this stub.

Implementation module path:
- `opencell/vivarium/karr_d2_stub.py`

## 7. Test Plan (Single Smoke Test)

New test file:
- `tests/d2/test_d2_stub.py`

Single test flow:
1. Build chassis engine via `build_karr_m1_m2_m3_engine(...)` with stub wired.
2. At `t=0`, read `engine.state.get_value()["complex"]["counts"]`.
3. Independently load expected snapshot map from fixture fields (same source
   paths as section 3) for every D.2-owned WID (149).
4. Assert equality for all WIDs.
5. Run one tick (`engine.update(1.0)`).
6. Assert `complex.counts.<wid>` unchanged for every WID.

No additional test harness/util packages.

## 8. Resolved Questions

1. Resolved: **149 is correct**; the A3 brief's "~147" was an approximation.
2. Resolved: **pure fixture derivation**, no canonical whitelist artifact.
3. Resolved: **`opencell/vivarium/karr_d2_stub.py`** per existing chassis
   convention.

