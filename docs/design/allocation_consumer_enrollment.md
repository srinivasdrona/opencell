# Allocation Consumer Enrollment Inventory (v6)

## Scope and provenance
- Branch: `agent/allocation-consumer-enrollment`
- Prompt target: v6 allocation-consumer enrollment BLOCK-RELEASE
- Karr primary-source paths requested by prompt:
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNADecay.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/HostInteraction.m`
- Note: those raw `.m` files are not present in this checkout; inventory below is grounded in:
  - verbatim Karr extracts: `docs/karr_extracts/process/13_RNADecay.md`, `docs/karr_extracts/process/27_HostInteraction.md`
  - process fixtures: `data/karr_fixtures/per_process/RnaDecay_flat.mat`, `data/karr_fixtures/per_process/HostInteraction_flat.mat`

## RNADecay substrate inventory
Karr source statement (verbatim extract): RNADecay algorithm step 2 says metabolite reactant limits are ignored "since the only reactant is water".

Fixture evidence from `RnaDecay_flat.mat` (`fixture.decayReactions` over `fixture.substrateWholeCellModelIDs`):
- Consumed WIDs (negative stoichiometry):
  - `H2O`
- Produced WIDs (positive stoichiometry across one or more RNA decay reactions):
  - `ALA`, `AMP`, `ARG`, `ASN`, `ASP`, `CMP`, `CYS`, `FMET`, `GLN`, `GLU`, `GLY`, `GMP`, `GmMP`, `H`, `HIS`, `ILE`, `LEU`, `LYS`, `MET`, `PHE`, `PRO`, `PSIURIMP`, `SER`, `THR`, `TRP`, `TYR`, `UMP`, `UmMP`, `VAL`, `cmnm5s2UMP`, `k2CMP`, `m1GMP`, `m2GMP`, `m62AMP`, `m7GMP`, `s4UMP`

Enrollment decision:
- `karr_rna_decay` must be registered as an allocation consumer for `H2O`.
- Byproducts remain emitted through the process stoichiometry on `substrates`.

## HostInteraction substrate inventory
Karr source evidence (verbatim extract `27_HostInteraction.md`):
- Simulation is described as qualitative Boolean rules over adherence and host signaling flags.
- No metabolite substrate consumption is described in Representation/Simulation sections.

Fixture evidence from `HostInteraction_flat.mat`:
- `substrateWholeCellModelIDs` is empty.
- `substrates` vector is empty.
- metabolite-linked substrate/enzyme index arrays are empty.

Enrollment decision:
- Karr HostInteraction has no shared-substrate consumer list to enroll.
- OpenCell `karr_host_interaction` was updated in this turn to remove its prior ATP proxy request/consumption path and now writes only host/cell-state deltas.
- Therefore `karr_host_interaction` is **N/A for KarrAllocationStep consumer enrollment** in v6.

## Post-change regression summary
Trajectory rerun command:
- `scripts/phase_e1_real_match.py --max-ticks 32400 --out data/phase_e/v6_trajectory_32400s_post_alloc.pkl`

Key observables at required checkpoints (BEFORE fixture vs POST-ALLOC rerun):

| Observable | t=0 | t=100s | t=16200s | t=32400s |
|---|---:|---:|---:|---:|
| `atp_pool` (before) | 1.0 | -43,750 | -5,751,050 | -10,211,500 |
| `atp_pool` (post) | 1.0 | -43,750 | -5,751,050 | -10,211,500 |
| `gtp_pool` (before) | 1.0 | -43,749 | -5,751,049 | -10,211,499 |
| `gtp_pool` (post) | 1.0 | -43,749 | -5,751,049 | -10,211,499 |
| `dntp_pool_total` (before) | 4.0 | 0 | 0 | 0 |
| `dntp_pool_total` (post) | 4.0 | 0 | 0 | 0 |
| `cell_dry_mass_g` (before) | 8.204e-16 | 9.059e-16 | -1.815e-14 | -3.386e-14 |
| `cell_dry_mass_g` (post) | 8.204e-16 | 9.059e-16 | -1.815e-14 | -3.386e-14 |
| `replication_state_code` (before) | 0 | 0 | 0 | 0 |
| `replication_state_code` (post) | 0 | 0 | 0 | 0 |
| `fork_position_norm` (before) | 0 | 0 | 0 | 0 |
| `fork_position_norm` (post) | 0 | 0 | 0 | 0 |

Notes:
- `division_detected` remains `False` at 32400s in both runs.
- `mrna_total_count_estimate` and `protein_total_count_estimate` folds are unchanged (3.724x and 5.600x respectively).
- Allocation arithmetic integrity over 1000 ticks remains strict (`max_overalloc = 0`, no negative allocations), but net substrate delta over 1000 ticks is still strongly negative (`-2,621,067.87`), so the larger substrate-accounting defect persists beyond this enrollment delta.
