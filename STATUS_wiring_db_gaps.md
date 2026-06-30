# STATUS: wiring DB schema gaps fixed

## What changed
- Added `symbol` to the shared `source_anchor` schema and backfilled symbols on all anchor blocks in `data/schemas/per_process_wiring/Metabolism.yaml`.
- Expanded `provenance` to the required audited form and populated the required fields for Metabolism.
- Added `schema_date: "2026-06-29"` alongside `schema_version` in both schema files.
- Corrected Metabolism's dependency direction to a one-way `produces_inputs_for` list with `consumes_outputs_of: []`.
- Added the missing writeback exemplars for step 2 recycled internal exchange and step 3 biomass production.
- Added the simulation-level `evolveState` anchor and aligned the remaining source anchors with explicit symbols.

## Validation
- Command:
  `wsl -e bash -lc 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c "...yaml.safe_load..."'`
- Result:
  Both `data/schemas/per_process_wiring/_schema.yaml` and `data/schemas/per_process_wiring/Metabolism.yaml` parsed as `dict`.

## Open items
- None blocking.
- Source references in the row are path-based anchors; filesystem existence of each referenced source path was not re-verified in this pass.
