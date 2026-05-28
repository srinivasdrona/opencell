# Karr Extract Index

Primary-source extracts from MATLAB headers and architecture code.

> **Audit note (2026-05-22, orchestrator):** Verbatim sections in each
> process extract are line-by-line accurate against the source `.m` files
> (audited on samples Metabolism, FtsZPolymerization, RNADecay, simulation_loop).
> The "OpenCell mapping notes" section is partly templated — specifically
> the "Algorithm complexity" line is identical across all 28 process
> extracts (always claims "complex / multi-stage constrained/stochastic").
> Trust the verbatim sections; spot-check the mapping notes against the
> source `.m` body for each process you implement. The architecture
> extracts captured Karr's variable-allocation algorithm verbatim from
> `evolveState.m`, which closes the open gap previously noted in
> `docs/design/karr_execution_plan_2026-05-22.md` §6.1.

## Process extracts

### Transport and metabolism
- [01_Metabolism](process/01_Metabolism.md) - `DONE-v1`

### DNA replication and maintenance
- [02_ReplicationInitiation](process/02_ReplicationInitiation.md) - `NOT-STARTED`
- [03_Replication](process/03_Replication.md) - `NOT-STARTED`
- [04_DNADamage](process/04_DNADamage.md) - `NOT-STARTED`
- [05_DNARepair](process/05_DNARepair.md) - `NOT-STARTED`
- [06_DNASupercoiling](process/06_DNASupercoiling.md) - `NOT-STARTED`
- [07_ChromosomeCondensation](process/07_ChromosomeCondensation.md) - `NOT-STARTED`
- [08_ChromosomeSegregation](process/08_ChromosomeSegregation.md) - `NOT-STARTED`

### RNA synthesis and maturation
- [09_Transcription](process/09_Transcription.md) - `DONE-v2` (was DONE-v1 at extract time; A3 step 2 merged v2 chassis wrapper as `461209e`)
- [10_TranscriptionalRegulation](process/10_TranscriptionalRegulation.md) - `L1-green`
- [11_RNAProcessing](process/11_RNAProcessing.md) - `NOT-STARTED`
- [12_RNAModification](process/12_RNAModification.md) - `NOT-STARTED`
- [13_RNADecay](process/13_RNADecay.md) - `NOT-STARTED`
- [14_tRNAAminoacylation](process/14_tRNAAminoacylation.md) - `NOT-STARTED`

### Protein synthesis and maturation
- [15_Translation](process/15_Translation.md) - `DONE-v2` (was DONE-v1 at extract time; A3 step 2 merged v2 chassis wrapper as `461209e`)
- [16_ProteinProcessingI](process/16_ProteinProcessingI.md) - `NOT-STARTED`
- [17_ProteinProcessingII](process/17_ProteinProcessingII.md) - `NOT-STARTED`
- [18_ProteinModification](process/18_ProteinModification.md) - `NOT-STARTED`
- [19_ProteinFolding](process/19_ProteinFolding.md) - `NOT-STARTED`
- [20_ProteinActivation](process/20_ProteinActivation.md) - `NOT-STARTED`
- [21_ProteinDecay](process/21_ProteinDecay.md) - `QUEUED-A3.3` (ProteinDecay-light scope; joint design with D.2-real)
- [22_ProteinTranslocation](process/22_ProteinTranslocation.md) - `NOT-STARTED`
- [23_MacromolecularComplexation](process/23_MacromolecularComplexation.md) - `STUBBED` (d2-stub; D.2-real in A3.3)
- [24_RibosomeAssembly](process/24_RibosomeAssembly.md) - `STUBBED` (30S/50S only via d2-stub; 70S+30S_IF3 deferred to Translation v2)

### Cytokinesis
- [25_FtsZPolymerization](process/25_FtsZPolymerization.md) - `NOT-STARTED`
- [26_Cytokinesis](process/26_Cytokinesis.md) - `NOT-STARTED`

### Host interaction
- [27_HostInteraction](process/27_HostInteraction.md) - `NOT-STARTED`
- [28_TerminalOrganelleAssembly](process/28_TerminalOrganelleAssembly.md) - `NOT-STARTED`

## Architecture extracts

- [01_simulation_loop](architecture/01_simulation_loop.md) — `run.m` master loop + `evolveState.m` per-tick algorithm including the proportional-fair-share metabolite allocation formula (`allocations = fix(requirements * (mets / sum(requirements, 2)))`)
- [02_state_variables](architecture/02_state_variables.md) — 16 state class headers
- [03_variable_allocation](architecture/03_variable_allocation.md)
- [04_fitConstants](architecture/04_fitConstants.md)
- [05_initializeState](architecture/05_initializeState.md)
