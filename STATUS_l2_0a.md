## L2.0a Allocator Input Gate

### Progress
- Read `SESSION_CONTEXT.md` and `docs/phase_f/L2_0A_ALLOCATOR_INPUT_GATE.md`.
- Confirmed the local oracle exists at `data/m1_sources/karr_native/l2_0a_allocator_oracle_s000.mat` and inspected its HDF5 layout with `h5py`.
- Confirmed the expected arithmetic fork is live in the oracle inputs: oversupply columns are present, so a RED baseline is plausible and meaningful.
- Derived the gate approach:
  - run `KarrAllocationStep` on synthetic compartment-qualified keys for the full flattened oracle matrix,
  - map reportable `(process, WID)` cells from schema substrate WIDs to flattened oracle cells only when the mapping is unambiguous,
  - report unmapped WIDs explicitly rather than silently dropping them.
- Implemented `scripts/probe_l2_0a_allocator_input.py`.
- First real-oracle baseline:
  - checked cells: 403
  - matched cells: 292
  - diverged cells: 111
  - unmapped WIDs: 1022
  - divergence diagnosis: 111/111 mismatches are the known oversupply-cap fork (`pool > total_demand`, OC returns capped request, Karr over-allocates then returns surplus later)
- Implemented `tests/integration/test_l2_0a_allocator_gate.py`.
- Verification:
  - `bin\oc-pytest tests/integration/test_l2_0a_allocator_gate.py -q` -> `5 passed`
  - `bin\oc-py -m ruff check scripts/probe_l2_0a_allocator_input.py tests/integration/test_l2_0a_allocator_gate.py` -> clean

### In Progress
- Final STATUS capture and commit.

### Baseline Per Process
- `ChromosomeCondensation`: checked=3, pass=1, fail=2, unmapped=2
- `ChromosomeSegregation`: checked=2, pass=2, fail=0, unmapped=3
- `Cytokinesis`: checked=1, pass=0, fail=1, unmapped=2
- `DNADamage`: checked=9, pass=8, fail=1, unmapped=39
- `DNARepair`: checked=20, pass=20, fail=0, unmapped=257
- `DNASupercoiling`: checked=3, pass=1, fail=2, unmapped=2
- `FtsZPolymerization`: checked=2, pass=1, fail=1, unmapped=3
- `HostInteraction`: checked=0, pass=0, fail=0, unmapped=0
- `MacromolecularComplexation`: checked=0, pass=0, fail=0, unmapped=210
- `Metabolism`: checked=190, pass=121, fail=69, unmapped=395
- `ProteinActivation`: checked=0, pass=0, fail=0, unmapped=10
- `ProteinDecay`: checked=34, pass=32, fail=2, unmapped=19
- `ProteinFolding`: checked=2, pass=2, fail=0, unmapped=9
- `ProteinModification`: checked=9, pass=9, fail=0, unmapped=6
- `ProteinProcessingI`: checked=1, pass=1, fail=0, unmapped=3
- `ProteinProcessingII`: checked=1, pass=1, fail=0, unmapped=4
- `ProteinTranslocation`: checked=4, pass=4, fail=0, unmapped=3
- `Replication`: checked=11, pass=9, fail=2, unmapped=5
- `ReplicationInitiation`: checked=2, pass=2, fail=0, unmapped=3
- `RibosomeAssembly`: checked=3, pass=1, fail=2, unmapped=2
- `RNADecay`: checked=29, pass=28, fail=1, unmapped=10
- `RNAModification`: checked=19, pass=19, fail=0, unmapped=10
- `RNAProcessing`: checked=4, pass=4, fail=0, unmapped=3
- `TerminalOrganelleAssembly`: checked=0, pass=0, fail=0, unmapped=8
- `Transcription`: checked=9, pass=6, fail=3, unmapped=3
- `TranscriptionalRegulation`: checked=0, pass=0, fail=0, unmapped=0
- `Translation`: checked=19, pass=17, fail=2, unmapped=7
- `tRNAAminoacylation`: checked=26, pass=3, fail=23, unmapped=4

### Unmapped WID Breakdown
- `multiple_active_compartment_candidates`: 123
- `multiple_local_nonzero_candidates`: 11
- `no_active_compartment_candidate`: 640
- `wid_missing_from_oracle_metabolite_list`: 248

### Notes
- The worktree has unrelated dirty files; I am staying scoped to:
  - `scripts/probe_l2_0a_allocator_input.py`
  - `tests/integration/test_l2_0a_allocator_gate.py`
  - `STATUS_l2_0a.md`
