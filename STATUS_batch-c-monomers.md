## Beat 1 - SUT inspection

### Contract

- Target scope is limited to the 4 catalog-authorized batch-C processes:
  - `ProteinModification`
  - `ProteinFolding`
  - `ProteinTranslocation`
  - `RibosomeAssembly`
- Authoritative wiring contract is the quoted catalog entry from the task prompt:
  - `ProteinModification`: primary `monomers`, inputs `substrates/enzymes/monomers`, outputs `substrates/monomers`, `M_ticks=100`, `N_seeds=50`
  - `ProteinFolding`: primary `monomers`, inputs `substrates/enzymes/monomers`, outputs `substrates/monomers`, `M_ticks=100`, `N_seeds=50`
  - `ProteinTranslocation`: primary `monomers`, inputs `substrates/enzymes/monomers`, outputs `substrates/monomers`, `M_ticks=100`, `N_seeds=50`
  - `RibosomeAssembly`: primary `complexs`, inputs `substrates/monomers/complexs/rnas`, outputs `substrates/complexs`, `M_ticks=200`, `N_seeds=50`, blocked on non-no-op L2.1 trace

### Real oracle availability

- Worktree-local `data/m1_sources/karr_native/per_process_traces_v2_sNNN/` is incomplete for these 4 processes:
  - `E:\opencell-worktrees\batch-c-monomers\data\m1_sources\karr_native`: 0/50 seed files for all 4 targets
- Main-repo data root is populated:
  - `E:\opencell\data\m1_sources\karr_native`: 50/50 seed files for all 4 targets
- Repo-local `ensembles/` coverage is unrelated to batch-C:
  - only `translation/` and `transcription/` exist under `data/m1_sources/karr_native/ensembles`
- Wiring consequence:
  - Beat 2 needs the same style of external-root v2 fallback that MacromolecularComplexation already uses, otherwise `load_karr_oracle()` will not reach `canonical_seed_count=50` for batch-C.

### Raw v2 schema cross-check

- `ProteinModification`
  - `states_before`: `boundEnzymes`, `enzymes`, `modifiedMonomers`, `substrates`, `unmodifiedMonomers`
  - `states_after`: `boundEnzymes`, `enzymes`, `modifiedMonomers`, `substrates`, `unmodifiedMonomers`
  - widths at seed 0 / tick 0: `substrates=15`, `enzymes=3`, `boundEnzymes=3`, `modifiedMonomers=482`, `unmodifiedMonomers=482`
- `ProteinFolding`
  - `states_before`: `boundEnzymes`, `enzymes`, `foldedComplexs`, `foldedMonomers`, `substrates`, `unfoldedComplexs`, `unfoldedMonomers`
  - `states_after`: `boundEnzymes`, `enzymes`, `foldedComplexs`, `foldedMonomers`, `substrates`, `unfoldedComplexs`, `unfoldedMonomers`
  - widths at seed 0 / tick 0: `substrates=11`, `enzymes=5`, `boundEnzymes=5`, `foldedMonomers=482`, `unfoldedMonomers=482`, `foldedComplexs=201`, `unfoldedComplexs=201`
- `ProteinTranslocation`
  - `states_before`: `boundEnzymes`, `enzymes`, `monomers`, `substrates`
  - `states_after`: `boundEnzymes`, `enzymes`, `monomers`, `substrates`
  - widths at seed 0 / tick 0: `substrates=7`, `enzymes=4`, `boundEnzymes=4`, `monomers=2892`
- `RibosomeAssembly`
  - `states_before`: `RNAs`, `boundEnzymes`, `complexs`, `enzymes`, `monomers`, `substrates`
  - `states_after`: `RNAs`, `boundEnzymes`, `complexs`, `enzymes`, `monomers`, `substrates`
  - widths at seed 0 / tick 0: `substrates=5`, `enzymes=6`, `boundEnzymes=6`, `monomers=52`, `complexs=2`, `RNAs=3`

### Required Beat-1 SUT notes

#### ProteinModification

- SUT class:
  - `KarrProteinModificationProcess` in `opencell/vivarium/karr_protein_modification.py:61`
- `next_update` write surface:
  - writes `substrates` and `protein.{unmodified_counts, modified_counts}` in `opencell/vivarium/karr_protein_modification.py:194`
  - no `enzymes` or `boundEnzymes` writes
- `_maybe_replay_from_hint` / `trace_hint` check:
  - no `_maybe_replay_from_hint`, `trace_hint`, or replay-helper token in this SUT module
- Primary-channel WID attribute:
  - catalog primary is `monomers`
  - SUT exposes split monomer WIDs as `modified_monomer_wids` and `unmodified_monomer_wids` (20 each) in `opencell/vivarium/karr_protein_modification.py:123-126`
  - raw Karr monomer observables are 482-wide, so L2.2 must synthesize catalog-facing `monomers` from the paired Karr observables rather than from a native `process.monomer_wids`
- `load_karr_oracle canonical_seed_count=50` expectation:
  - reachable only if batch-C v2 loader resolves to `E:\opencell\data\m1_sources\karr_native`

#### ProteinFolding

- SUT class:
  - `KarrProteinFoldingProcess` in `opencell/vivarium/karr_protein_folding.py:98`
- `next_update` write surface:
  - writes `substrates` and `protein.{unfolded_counts, counts}` in `opencell/vivarium/karr_protein_folding.py:237`
  - no `enzymes` or `boundEnzymes` writes
- `_maybe_replay_from_hint` / `trace_hint` check:
  - no `_maybe_replay_from_hint`, `trace_hint`, or replay-helper token in this SUT module
- Primary-channel WID attribute:
  - catalog primary is `monomers`
  - SUT exposes split monomer WIDs as `folded_monomer_wids` and `unfolded_monomer_wids` (482 each) in `opencell/vivarium/karr_protein_folding.py:143-144`
  - catalog-facing `monomers` therefore has to be synthesized from the split folded/unfolded channels for oracle formatting and projection
- `load_karr_oracle canonical_seed_count=50` expectation:
  - reachable only if batch-C v2 loader resolves to `E:\opencell\data\m1_sources\karr_native`

#### ProteinTranslocation

- SUT class:
  - `KarrProteinTranslocationProcess` in `opencell/vivarium/karr_protein_translocation.py:93`
- `next_update` write surface:
  - writes `protein.{location, unprocessed_counts}` and `substrates` in `opencell/vivarium/karr_protein_translocation.py:307`
  - no `enzymes` or `boundEnzymes` writes
- `_maybe_replay_from_hint` / `trace_hint` check:
  - no `_maybe_replay_from_hint`, `trace_hint`, or replay-helper token in this SUT module
- Primary-channel WID attribute:
  - catalog primary is `monomers`
  - SUT exposes `monomer_wids` (482) in `opencell/vivarium/karr_protein_translocation.py:115`
  - raw Karr `monomers` trace is 2892-wide, matching the L2.1 cytosol-slice pattern rather than the 482-WID process surface
- `load_karr_oracle canonical_seed_count=50` expectation:
  - reachable only if batch-C v2 loader resolves to `E:\opencell\data\m1_sources\karr_native`

#### RibosomeAssembly

- SUT class:
  - `KarrRibosomeAssemblyProcess` in `opencell/vivarium/karr_ribosome_assembly.py:75`
- `next_update` write surface:
  - writes `substrates`, `rna.counts`, `protein.counts`, and `complex.counts` in `opencell/vivarium/karr_ribosome_assembly.py:325`
  - catalog output remains `substrates` + `complexs` only
- `_maybe_replay_from_hint` / `trace_hint` check:
  - no `_maybe_replay_from_hint`, `trace_hint`, or replay-helper token in this SUT module
- Primary-channel WID attribute:
  - catalog primary is `complexs`
  - SUT exposes `complex_wids` (2) in `opencell/vivarium/karr_ribosome_assembly.py:124`
  - supporting input surfaces are `monomer_subunit_wids` (52) and `rna_subunit_wids` (3) in `opencell/vivarium/karr_ribosome_assembly.py:122-124`
- `load_karr_oracle canonical_seed_count=50` expectation:
  - reachable only if batch-C v2 loader resolves to `E:\opencell\data\m1_sources\karr_native`
- blocked note:
  - catalog says `blocked_on: ["L2.1 trace must be non-no-op for this process"]`
  - raw v2 traces do include `RNAs` alongside `substrates/monomers/complexs`, so Beat 2 should wire the RNA input overlay and Beat 5 should document any no-op smoke signature rather than silently omitting the process

### Existing helper/runner surfaces to modify

- Helper oracle / dispatcher surface:
  - `_oracle_dispatch()` at `tests/vivarium/_l2_2_design_a_runner_helpers.py:511`
  - `load_karr_oracle()` at `tests/vivarium/_l2_2_design_a_runner_helpers.py:523`
  - `_tick_dispatch()` at `tests/vivarium/_l2_2_design_a_runner_helpers.py:832`
  - template helpers to mirror:
    - `_run_protein_decay_tick()` at `tests/vivarium/_l2_2_design_a_runner_helpers.py:1219`
    - `_run_macromol_tick()` at `tests/vivarium/_l2_2_design_a_runner_helpers.py:1300`
- Runner surface:
  - `SUPPORTED_PROCESSES` table roots at `tests/vivarium/l2_2_design_a_runner.py:165`
  - `_process_sample_process()` at `tests/vivarium/l2_2_design_a_runner.py:638`
  - `_observable_wids()` at `tests/vivarium/l2_2_design_a_runner.py:656`
  - sample-state assembly in `run_design_a()` at `tests/vivarium/l2_2_design_a_runner.py:686`

### Suspect patterns / pre-mortem

- The obvious false-green risk is projecting the wrong monomer surface:
  - `ProteinModification` and `ProteinFolding` do not carry raw `monomers` in v2; if I treat `modifiedMonomers` or `foldedMonomers` alone as catalog `monomers`, the wiring will be structurally valid but biologically wrong.
- The second false-green risk is accidental trace laundering:
  - the new dispatchers must not populate `trace_hint`, even for the split-state processes where the raw Karr before/after tensors are tempting to thread through.
- The third risk is incomplete 50-seed resolution:
  - if Beat 2 only extends `_oracle_dispatch()` without teaching `_load_v2_ensemble()` to resolve the main-repo root, these processes will look supported but fail the required `canonical_seed_count=50` contract.

## Beat 2 - dispatchers + factories

- Pending.

## Beat 3 - wire runner

- Pending.

## Beat 4 - inversion

- Pending.

## Beat 5 - smoke gates

- Pending.

verdict: PENDING
