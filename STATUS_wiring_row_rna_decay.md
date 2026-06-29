# STATUS: RNADecay wiring row authored

What I authored:
- `data/schemas/per_process_wiring/RNADecay.yaml`
- `data/schemas/per_process_wiring/RNADecay.yaml` validates with the repo's Python wrapper and loads as `dict 13`.

What the row captures:
- RNADecay is modeled as an allocation-mode process on `H2O` only.
- The OC port reads `substrates_allocated[self.name]` when available, so `allocator.mode.oc_current` is `allocation`.
- The process update path is in `RnaDecayLightProcess.next_update`, which covers the request emission, stochastic decay sampling, peptidyl-hydrolase gating, water gate, RNA updates, and substrate writeback.
- The row records the canonical RNAs upstream/downstream relationships, the H2O-only allocator consumer tuple, the main byproduct stoichiometry exemplars, and the global `tRNAAminoacylation < Translation` ordering constraint.

Uncertainties:
- The raw MATLAB source file `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNADecay.m` is not present in this checkout.
- Because of that, the MATLAB-side request formula is inferred from the checked-in RNADecay extract, the allocation loop extract, and the H2O-only consumer inventory rather than copied from the original `.m` body.
- The row marks `calcFluxBounds` as `not_implemented` because RNADecay is not an LP/flux process in the available source material.

Observed divergences:
- OC folds request emission into `next_update` instead of exposing a dedicated request-calculator method.
- OC adds a trace-hint short-circuit for replay harnesses.
- OC includes fallback initialization and half-life guards that are not documented in the RNADecay extract.
- No RNADecay-specific process ordering rule appeared in the available extract beyond the global `tRNAAminoacylation < Translation` constraint.

Validation:
- Command: `wsl -e bash -lc 'cd /mnt/e/opencell-worktrees/rna_decay && source /mnt/e/opencell/.venv-wsl/bin/activate && python - <<'"'"'PY'"'"' ... PY'`
- Result: `OK dict 13`
