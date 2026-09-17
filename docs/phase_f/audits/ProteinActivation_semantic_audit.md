# ProteinActivation Semantic Audit

Process: `ProteinActivation`
Authority: primary `ProteinActivation.m`, current
`karr_protein_activation.py`, and chassis topology.
Scope: exhaustive six-protein documentation.

## Current implementation status

The active/inactive transfer formula is implemented for all six regulated
proteins. Three implementation deviations remain: OC reads raw flat signals,
whereas MATLAB converts non-stimulus signals to concentration using cell volume;
MATLAB evaluates/writes per compartment, whereas OC uses one scalar per WID;
and production topology omits/misseeds the active/inactive state surface.

## Claim table

| Claim ID | Category | Documented claim and evidence | Verdict |
|---|---|---|---|
| PA-S1-01 | S1 | The row now exhaustively lists all six regulated proteins (`MG_085`, `MG_101`, `MG_127`, `MG_205`, `MG_236`, `MG_409`) on the consume side; OC enforces the same six-WID fixture set (`karr_protein_activation.py:20-27,168-176`). | VERIFIED |
| PA-S2-01 | S2 | Every listed protein has an executable consume path: active count is consumed when its rule is false, inactive count when true (`ProteinActivation.m:359-366`; OC `:237-264`). | VERIFIED |
| PA-S3-01 | S3 | The produce side is also exhaustive for the same six proteins. | VERIFIED |
| PA-S4-01 | S4 | Both implementations transfer the whole active/inactive count according to an all-or-nothing rule result. | VERIFIED |
| PA-S4-02 | S4 | MATLAB converts non-stimulus signals by `(nAvogadro/1000) * geometry.volume`, leaving true stimulus signals raw (`ProteinActivation.m:369-375`). OC reads raw flat `substrates`/`stimuli` values (`karr_protein_activation.py:226-235`). | CODE_DEVIATES |
| PA-S5-01 | S5 | MATLAB evaluates and updates every `(protein, compartment)` tuple (`ProteinActivation.m:378-394`). OC projects each protein to one flat `activation_substrates` WID (`karr_protein_activation.py:195-204`; `karr_composite.py:2126-2129`). | CODE_DEVIATES |
| PA-S5-02 | S5 | Production topology maps `substrates`, `stimuli`, and `protein` only, omitting `inactivatedSubstrates` (`karr_composite.py:2126-2130`). It initializes `activation_substrates` from the metabolite `initial_substrates` map rather than Karr active/inactive protein state (`:2277-2283`). | CODE_DEVIATES |
| PA-S6-01 | S6 | MATLAB has a zero-return resource hook; OC omits it. The row now records allocator-sequenced zero demand versus bypass as a benign resource-equivalent shape difference. | VERIFIED |
| PA-S6-02 | S6 | The row now anchors the real MATLAB `calcResourceRequirements_Current` method rather than claiming it is absent. | VERIFIED |
| PA-S6-03 | S6 | No ProteinActivation-specific scheduler edge or `calcFluxBounds` path exists. | VERIFIED |

## Aggregate counts

- VERIFIED: 7
- ROW_WRONG: 0
- CODE_DEVIATES: 3
- MISSING: 0

## Open implementation deviations

- Non-stimulus rule inputs: MATLAB concentration conversion versus OC raw
  values.
- Per-compartment MATLAB rule evaluation/writeback versus OC flat per-WID
  projection.
- Missing production `inactivatedSubstrates` topology and metabolite-derived
  `activation_substrates` initialization.

## Documentation corrections completed

- Replaced exemplar-only lists with exhaustive six-protein transfer entries.
- Replaced derived-extract anchors with the primary MATLAB source.
- Correctly documented the zero-return MATLAB request hook.
- Reclassified the signal-scaling and compartment differences as code
  deviations rather than row omissions.
- Added the production topology/initial-state defect.
