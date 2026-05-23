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
