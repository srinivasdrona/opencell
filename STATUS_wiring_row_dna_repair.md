# DNARepair Wiring Row Status

Authored `data/schemas/per_process_wiring/DNARepair.yaml` and this status note.

What is covered:

- Process identity for `DNARepair`
- Allocator-mode wiring and request surface
- Canonical consume / produce stoichiometry for the tracked ATP / dNTP / RM-side-effect set
- Compartment routing for the tracked WIDs
- Unit-conversion summary from repair events to molecule counts
- Dependencies, ordering notes, source anchors, provenance, and deviations

What is intentionally approximate:

- The raw MATLAB `DNARepair.m` file was not present in this checkout, so MATLAB-side anchors use `docs/karr_extracts/process/05_DNARepair.md` and `docs/karr_extracts/architecture/01_simulation_loop.md` instead of direct `.m` line spans.
- `calcFluxBounds` was marked `not_implemented` because I did not find a DNARepair-specific flux-bound body in the available material.
- The current OC port is an aggregated repair model, so the row calls out the omitted Karr-only ligation / polymerization products instead of pretending the port is one-to-one.

Observed divergences called out in the row:

- OC folds request generation into `KarrDNARepairProcess.next_update`.
- OC only models the simplified ATP/dNTP demand plus the conditional AMET -> AHCYS + H side effect.
- The full Karr repair chemistry remains broader than the current OC port.

If you want the next pass to be stricter, the main follow-up is to recover the raw MATLAB source file or a line-accurate extract so the MATLAB anchors can point at the exact `.m` implementation rather than the closest derived documentation.
