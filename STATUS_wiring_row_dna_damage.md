# STATUS: DNADamage wiring row

Authored `data/schemas/per_process_wiring/DNADamage.yaml` for the `DNADamage` Karr process.

What I captured:
- Process identity for `DNADamage` and the current OC port `KarrDNADamageProcess`.
- Method correspondence for `calcResourceRequirements_Current`, `evolveState`, and `calcFluxBounds`.
- Allocator mode as bypass on both sides, with no request surface in the current OC port.
- Canonical consume / produce stoichiometry examples grounded in the DNADamage fixture reaction matrix.
- Compartment routing, unit conversion, dependencies, ordering constraints, source anchors, provenance, and explicit deviations.

Main uncertainties:
- The canonical MATLAB `.m` file is not present in this worktree, so MATLAB-side anchors use `docs/karr_extracts/process/04_DNADamage.md` as the local verbatim proxy.
- `kb_version` is inferred from the cataloged trace path family (`karr_native_per_process_traces_v2_s000`) rather than read from a dedicated DNADamage KB string.
- `calcResourceRequirements_Current` and `calcFluxBounds` are marked `not_implemented` because the current OC port does not expose allocator or flux-bound wiring.

Observed divergences:
- The current OC process is lesion-creation only; it does not implement the reaction stoichiometry updates described in the extract.
- The OC port reads `states["substrates"]` directly and never uses `substrates_allocated`.
- Repair chemistry and lesion-specific chromosome-array parity are deferred.

Validation:
- `wsl -e bash -lc 'cd /mnt/e/opencell-worktrees/dna_damage && source /mnt/e/opencell/.venv-wsl/bin/activate && python -c "import yaml; ..."'`
- Result: `OK dict 13`

Notes:
- The exact validation command from the task failed in this worktree because `/mnt/e/opencell` did not contain the authored file; the equivalent command against `/mnt/e/opencell-worktrees/dna_damage` passed.
