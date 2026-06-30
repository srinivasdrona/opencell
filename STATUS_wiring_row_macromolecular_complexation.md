# STATUS: MacromolecularComplexation wiring row

## What I authored

- `data/schemas/per_process_wiring/MacromolecularComplexation.yaml`
- `STATUS_wiring_row_macromolecular_complexation.md`

## What the row captures

- Class identity for Karr `MacromolecularComplexation` and the OC port `MacromolecularComplexationProcess`.
- Allocator wiring showing Karr uses an allocation path, while current OC also reads from `substrates_allocated[self.name]`.
- The zero-request allocator formula for this process.
- Canonical consume/produce stoichiometry examples, compartment routing, unit conversion, dependencies, ordering constraints, source anchors, provenance, and known deviations.

## Uncertainties

- The prompt-specified MATLAB source file is not present in this checkout, so the MATLAB anchors are grounded in the preserved verbatim design extracts under `docs/design/` rather than a directly readable `.m` file.
- `kb_version` is still `unknown`; I did not find a reliable version string in the OC init path or fixture metadata.
- I did not invent a fake `.m` provenance entry. `matlab_files_referenced` is empty because no `.m` file was actually readable here.

## Divergences noted

- OC’s competitive helper can form multiple complexes per iteration because it samples a Poisson multiplicity.
- OC includes a cluster-1 fallback into the Monte Carlo helper if the closed-form bound would overconsume.

## Validation

- `bin\\oc-py.cmd tmp/validate_macromol_row.py` -> `OK dict 13`
