# STATUS: ProteinProcessingII wiring row

Authored `data/schemas/per_process_wiring/ProteinProcessingII.yaml` for the `ProteinProcessingII` Karr process.

What the row captures:
- Process identity for the MATLAB class and OC port.
- Method correspondence for `initializeConstants`, state I/O, allocator requests, the current-tick evolve path, lifecycle resource accounting, and the absent `calcFluxBounds` hook.
- Allocator mode as `allocation` on both Karr and current OC, with the OC port reading from `substrates_allocated[self.name]`.
- Count-space stoichiometry for `H2O`, `PG160`, `SNGLYP`, and `H`, plus the nominal-but-unemitted `diacylglycerolCys` routing mismatch.
- Count-space unit conversion, dependency notes, ordering notes, source anchors, and provenance.

Uncertainties:
- I left `produces_inputs_for` empty because I did not find a direct downstream process-specific consumer for PP2 outputs in the source/OC wire-up that I could anchor cleanly.
- The provenance `kb_version` is recorded as `karr_native_m1__v2` by fixture family convention; the PP2 loader itself only exposes the flat MAT fixture path.

Observed divergences:
- OC request calculation is availability-based via `_request_from_available`, not the exact MATLAB `min(ceil(rate * dt), available monomers)` formula.
- OC reads `substrates_allocated[self.name]` with a strict-zero allocator contract instead of falling back to the global substrate pool.
- The MATLAB chemistry comment names `diacylglycerolCys`, but neither implementation materializes it as a real emitted product.
- `calcFluxBounds` has no OC analogue for this process.

Validation:
- `wsl -e bash -lc 'source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/protein_processing_ii && python -c "import yaml; d=yaml.safe_load(open(\"data/schemas/per_process_wiring/ProteinProcessingII.yaml\")); print(\"OK\", type(d).__name__, len(d))"'`
- Result: `OK dict 13`
