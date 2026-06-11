# STATUS batch-b-rnas

## Beat 1 - SUT inspection

Catalog authority:

```yaml
  - name: RNAProcessing
    oc_module: opencell/vivarium/karr_rna_processing.py
    bucket: ALGORITHMIC_SHALLOW
    in_scope_L2_2: true
    M_ticks: 100
    N_seeds: 50
    event_density: moderate
    input_channels: [substrates, enzymes, rnas]
    output_channels: [substrates, rnas]
    primary_channel: rnas
    karr_artifact: per_process_traces_v2

  - name: RNAModification
    oc_module: opencell/vivarium/karr_rna_modification.py
    bucket: ALGORITHMIC_SHALLOW
    in_scope_L2_2: true
    M_ticks: 100
    N_seeds: 50
    event_density: moderate
    input_channels: [substrates, enzymes, rnas]
    output_channels: [substrates, rnas]
    primary_channel: rnas
    karr_artifact: per_process_traces_v2
    notes: "Audit flagged: L2.1 currently SKIP for no-op trace. Fix L2.1 trace first."

  - name: tRNAAminoacylation
    oc_module: opencell/vivarium/karr_trna_aminoacylation.py
    bucket: ALGORITHMIC_SHALLOW
    in_scope_L2_2: true
    M_ticks: 50
    N_seeds: 50
    event_density: dense
    input_channels: [substrates, enzymes, rnas]
    output_channels: [substrates, rnas]
    primary_channel: rnas
    karr_artifact: per_process_traces_v2
```

Read surfaces:

- `opencell/vivarium/karr_rna_processing.py`
- `opencell/vivarium/karr_rna_modification.py`
- `opencell/vivarium/karr_trna_aminoacylation.py`
- `tests/vivarium/_l2_2_design_a_runner_helpers.py:832-1365`
- `tests/vivarium/l2_2_design_a_runner.py:638-817`

Findings:

| Process | SUT class | `next_update` write surface | Primary channel WID attribute | Notes |
| --- | --- | --- | --- | --- |
| `RNAProcessing` | `KarrRNAProcessingProcess` | `substrates` plus `rna.counts` keyed by `unprocessed_rna_wids` and `processed_rna_wids` (`opencell/vivarium/karr_rna_processing.py`) | `rna_wids` for modeled lanes; `intergenicRNAs` exists in trace and is not a process store attribute | Trace channels are `substrates`, `enzymes`, `boundEnzymes`, `unprocessedRNAs`, `processedRNAs`, `intergenicRNAs`. |
| `RNAModification` | `KarrRNAModificationProcess` | `substrates` plus `rna.counts` and `rna.modified_counts` keyed by active-target `unmodified_rna_wids` / `modified_rna_wids` (`opencell/vivarium/karr_rna_modification.py`) | No single `rna_wids`; primary surface must combine full trace `unmodifiedRNAs` + `modifiedRNAs` while projecting SUT writes onto active target WIDs | Trace carries 347+347 RNA lanes; SUT models the active 38+38 subset. |
| `tRNAAminoacylation` | `KarrTRNAAminoacylationProcess` | `substrates` plus `rna.counts` and `rna.aminoacylated_counts` keyed by `free_rna_wids` / `aminoacylated_rna_wids` (`opencell/vivarium/karr_trna_aminoacylation.py`) | No single `rna_wids`; primary surface must combine `free_rna_wids` + `aminoacylated_rna_wids` | Catalog override: `M_ticks: 50`, not the 100-tick default. |

Beat 1 notes:

- Existing helper dispatch only supports `Metabolism`, `Translation`, `Transcription`, `RNADecay`, `ProteinDecay`, `MacromolecularComplexation`, and `Cytokinesis`.
- Existing runner support table is derived from `_implemented_processes()` and currently excludes these three.
- The worktree-local `data/m1_sources/karr_native` mirror does not contain the new v2 seed traces, but the shared source tree does: `E:/opencell/data/m1_sources/karr_native/per_process_traces_v2_s000..s049/<Process>_100ticks.mat` for all three.
- `RNAModification` carries the catalog note about the prior L2.1 no-op skip; this batch will document the smoke outcome but will not alter L2.1 here.
