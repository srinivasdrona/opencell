# L2.0 Observable-Schema Audit

Static comparison of `karr_obs` (top-level keys under `states_before/` in each
per-process .mat oracle) vs `oc_obs` (top-level keys returned by the OC process's
`ports_schema()`).

**Verdict rules:**
- 🟢 GREEN: `karr_obs ⊆ oc_obs` (OC emits every channel Karr's oracle records; `oc_only` is informational)
- 🟡 AMBER: `overlap ⊂ karr_obs` and `overlap ≠ ∅` (partial port — channels in `karr_only` are model debt)
- 🔴 RED: `overlap = ∅` (no shared channels — vacuous gate, blocks L2.1 for this process)
- ⚪ ERROR: process could not be instantiated for schema introspection (see error column)

## Summary

- 🟢 GREEN: 0
- 🟡 AMBER: 24
- 🔴 RED: 4
- ⚪ ERROR: 0
- **Total**: 28

## Per-process verdicts

| Process | Verdict | karr_obs | oc_obs | overlap | karr_only | oc_only |
|---|---|---:|---:|---:|---|---|
| ChromosomeCondensation | 🟡 AMBER | 3 | 4 | 1 | boundEnzymes, enzymes | chromosome, requests, substrates_allocated |
| ChromosomeSegregation | 🟡 AMBER | 3 | 6 | 1 | boundEnzymes, enzymes | chromosome, complex, protein, requests (+1 more) |
| Cytokinesis | 🟡 AMBER | 3 | 5 | 1 | boundEnzymes, enzymes | cell, chromosome, requests, substrates_allocated |
| DNADamage | 🔴 RED | 3 | 1 | 0 | boundEnzymes, enzymes, substrates | chromosome |
| DNARepair | 🟡 AMBER | 3 | 6 | 1 | boundEnzymes, enzymes | chromosome, complex, protein, requests (+1 more) |
| DNASupercoiling | 🟡 AMBER | 3 | 6 | 1 | boundEnzymes, enzymes | chromosome, complex, protein, requests (+1 more) |
| FtsZPolymerization | 🟡 AMBER | 3 | 4 | 1 | boundEnzymes, enzymes | cell, requests, substrates_allocated |
| HostInteraction | 🔴 RED | 3 | 2 | 0 | boundEnzymes, enzymes, substrates | cell, protein |
| MacromolecularComplexation | 🟡 AMBER | 4 | 4 | 1 | boundEnzymes, complexs, enzymes | complex, requests, substrates_allocated |
| Metabolism | 🟡 AMBER | 3 | 2 | 1 | boundEnzymes, enzymes | metabolic_reaction |
| ProteinActivation | 🟡 AMBER | 3 | 3 | 1 | boundEnzymes, enzymes | protein, stimuli |
| ProteinDecay | 🟡 AMBER | 5 | 6 | 1 | boundEnzymes, complexs, enzymes, monomers | complex, protein, requests, rna (+1 more) |
| ProteinFolding | 🟡 AMBER | 5 | 4 | 1 | boundEnzymes, enzymes, foldedMonomers, unfoldedMonomers | complex, protein, substrates_allocated |
| ProteinModification | 🟡 AMBER | 5 | 5 | 1 | boundEnzymes, enzymes, modifiedMonomers, unmodifiedMonomers | complex, protein, requests, substrates_allocated |
| ProteinProcessingII | 🟡 AMBER | 5 | 4 | 1 | boundEnzymes, enzymes, processedMonomers, unprocessedMonomers | protein, requests, substrates_allocated |
| ProteinProcessingI | 🟡 AMBER | 5 | 5 | 1 | boundEnzymes, enzymes, processedMonomers, unprocessedMonomers | complex, protein, requests, substrates_allocated |
| ProteinTranslocation | 🟡 AMBER | 4 | 5 | 1 | boundEnzymes, enzymes, monomers | complex, protein, requests, substrates_allocated |
| RNADecay | 🟡 AMBER | 3 | 4 | 1 | boundEnzymes, enzymes | requests, rna, substrates_allocated |
| RNAModification | 🟡 AMBER | 5 | 6 | 1 | boundEnzymes, enzymes, modifiedRNAs, unmodifiedRNAs | complex, protein, requests, rna (+1 more) |
| RNAProcessing | 🟡 AMBER | 5 | 6 | 1 | boundEnzymes, enzymes, processedRNAs, unprocessedRNAs | complex, protein, requests, rna (+1 more) |
| ReplicationInitiation | 🟡 AMBER | 3 | 5 | 1 | boundEnzymes, enzymes | chromosome, protein, requests, substrates_allocated |
| Replication | 🟡 AMBER | 3 | 4 | 1 | boundEnzymes, enzymes | chromosome, requests, substrates_allocated |
| RibosomeAssembly | 🟡 AMBER | 5 | 6 | 1 | boundEnzymes, complexs, enzymes, monomers | complex, protein, requests, rna (+1 more) |
| TerminalOrganelleAssembly | 🔴 RED | 3 | 2 | 0 | boundEnzymes, enzymes, substrates | cell, protein |
| Transcription | 🟡 AMBER | 3 | 2 | 1 | boundEnzymes, enzymes | rna |
| TranscriptionalRegulation | 🔴 RED | 3 | 4 | 0 | boundEnzymes, enzymes, substrates | complex, protein, tf_binding, tx_rate_fold_change |
| Translation | 🟡 AMBER | 4 | 2 | 1 | boundEnzymes, enzymes, monomers | protein |
| tRNAAminoacylation | 🟡 AMBER | 5 | 6 | 1 | aminoacylatedRNAs, boundEnzymes, enzymes, freeRNAs | complex, protein, requests, rna (+1 more) |

## Errors (if any)

(none)

## Methodology notes

- This is a **static** schema audit. Each process is instantiated with an empty config (`cls({})`)
  and its `ports_schema()` is introspected for top-level port keys. Processes that require a non-empty
  config (e.g., fixture paths) will appear as ERROR and need a per-process probe config.
- A GREEN verdict here does **not** imply L2.1 (bit-identity) passes — it only confirms the schema
  surfaces match. L2.1 is a behavioural check on overlap channels.
- A RED verdict blocks L2.1 entirely: there is nothing to compare bit-for-bit. The process either
  needs port-completeness work (start emitting the karr-recorded channels) or the .mat oracle needs
  re-extraction at a layer that does emit shared channels.
