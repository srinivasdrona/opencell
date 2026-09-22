# ProteinActivation Semantic Audit

Process: `ProteinActivation`
Authority: primary `ProteinActivation.m`, current
`karr_protein_activation.py`, and chassis topology.
Scope: exhaustive six-protein documentation.

## Current implementation status

The source-faithful active/inactive transfer is implemented for all six
regulated proteins and all six compartments. Production uses canonical
ProteinMonomer/ProteinComplex active and inactive state, live geometry volume,
raw true stimuli, and Karr count-to-mM conversion for all other signals.

## Claim table

| Claim ID | Category | Documented claim and evidence | Verdict |
|---|---|---|---|
| PA-S1-01 | S1 | The row now exhaustively lists all six regulated proteins (`MG_085`, `MG_101`, `MG_127`, `MG_205`, `MG_236`, `MG_409`) on the consume side; OC enforces the same six-WID fixture set (`karr_protein_activation.py:20-27,168-176`). | VERIFIED |
| PA-S2-01 | S2 | Every listed protein has an executable consume path: active count is consumed when its rule is false, inactive count when true (`ProteinActivation.m:359-366`; OC `:237-264`). | VERIFIED |
| PA-S3-01 | S3 | The produce side is also exhaustive for the same six proteins. | VERIFIED |
| PA-S4-01 | S4 | Both implementations transfer the whole active/inactive count according to an all-or-nothing rule result. | VERIFIED |
| PA-S4-02 | S4 | OC leaves true stimulus indices raw and converts every other signal with `count / (nAvogadro/1000) / geometry.volume`, matching MATLAB (`karr_protein_activation.py:677-694`). | VERIFIED |
| PA-S5-01 | S5 | OC stores and updates every active/inactive `(protein, compartment)` tuple in shared protein/complex roots; compartment 0 retains the existing canonical count leaf and compartments 1-5 have explicit branches. | VERIFIED |
| PA-S5-02 | S5 | Production topology maps protein, complex, stimuli, and live geometry and seeds canonical active/inactive state from ProteinMonomer/ProteinComplex fixtures (`karr_composite.py:_seed_protein_activation_shared_state`). | VERIFIED |
| PA-S6-01 | S6 | MATLAB has a zero-return resource hook; OC omits it. The row now records allocator-sequenced zero demand versus bypass as a benign resource-equivalent shape difference. | VERIFIED |
| PA-S6-02 | S6 | The row now anchors the real MATLAB `calcResourceRequirements_Current` method rather than claiming it is absent. | VERIFIED |
| PA-S6-03 | S6 | No ProteinActivation-specific scheduler edge or `calcFluxBounds` path exists. | VERIFIED |

## Aggregate counts

- VERIFIED: 10
- ROW_WRONG: 0
- CODE_DEVIATES: 0
- MISSING: 0

## Implementation fidelity result

- No known ProteinActivation implementation deviation remains on the audited
  signal conversion, compartment state, initialization, transfer, topology,
  and conservation surfaces.

## Documentation corrections completed

- Replaced exemplar-only lists with exhaustive six-protein transfer entries.
- Replaced derived-extract anchors with the primary MATLAB source.
- Correctly documented the zero-return MATLAB request hook.
- Closed signal scaling, compartment state, and production initialization
  through canonical shared stores.
