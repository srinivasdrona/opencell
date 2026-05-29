# STATUS — Fix ProteinProcessingI

- Date: 2026-05-29
- Branch/worktree: `agent/fix-protein-processing-i` / `E:\opencell-worktrees\fix-protein-processing-i`
- Scope state: **PARTIAL ([wip])**

## 1. Canonical MATLAB rule (file:line)
- File: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingI.m`
- Event-count / transformation rule: `evolveState` builds `transformations`, scales by enzyme limits, then stochastic-rounds (`lines 247-253`), with water repartition when constrained (`lines 256-275`).
- Metabolite accounting rule: deformylation emits `[-H2O, +FOR, +H] * sum(transformations)` (`lines 286-288`) and cleavage adds `[-H2O, +MET] * sum(transformations(cleavageMask))` (`lines 290-292`).

## 2. OC simplification replaced
- Replaced strict reliance on `protein.unprocessed_counts`/`protein.enzyme_counts` with a replay-compat fallback path that can ingest L2 inputs from `protein.counts` when dedicated stores are empty.
- Added replay-compat monomer-enzyme fallback to fixture baseline when `protein.counts` overlay collisions zero out monomer enzyme values.
- Added missing hydrogen byproduct accounting (`H += total_processed`) to match MATLAB stoichiometry.

## 3. Diff (line count + concept)
- `opencell/vivarium/karr_protein_processing_i.py`: **67 lines changed** (`52 insertions`, `15 deletions`).
- Concepts:
  - replay-compat input normalization for monomer/enzyme reads,
  - compat mirror into `protein.counts`,
  - missing hydrogen stoichiometry fix.

## 4. Final test result
- Target replay:
  - Command: `pytest tests/vivarium/test_karr_protein_processing_i_l2_replay.py --tb=line -rs` (WSL venv)
  - Result: **FAIL (progress from initial H2O mismatch)**
  - New first-fail: `tick=1, observable=processedMonomers, index=147, oc_val=2.0, karr_val=1.0, diff=+1.0`
- Focused unit tests:
  - `pytest tests/vivarium/test_karr_protein_processing_i.py -q`
  - Result: `8 passed`

## 5. Commit hash
- Pending commit in this status update; hash will be filled after commit.

## 6. Wall-time
- Approx. **~75 minutes**.

## Notes / blocker
- The remaining mismatch is tied to L2 projection shape: `processedMonomers` and `unprocessedMonomers` are both projected from `protein.counts` with identical WIDs, so exact simultaneous representation conflicts once both are compared from a single post-update state.
