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

- 🟢 GREEN: 28
- 🟡 AMBER: 0
- 🔴 RED: 0
- ⚪ ERROR: 0
- **Total**: 28

## Per-process verdicts

| Process | Verdict | karr_obs | oc_obs | overlap | karr_only | oc_only |
|---|---|---:|---:|---:|---|---|
| ChromosomeCondensation | 🟢 GREEN | 3 | 6 | 3 | — | chromosome, requests, substrates_allocated |
| ChromosomeSegregation | 🟢 GREEN | 3 | 8 | 3 | — | chromosome, complex, protein, requests (+1 more) |
| Cytokinesis | 🟢 GREEN | 3 | 7 | 3 | — | cell, chromosome, requests, substrates_allocated |
| DNADamage | 🟢 GREEN | 3 | 4 | 3 | — | chromosome |
| DNARepair | 🟢 GREEN | 3 | 8 | 3 | — | chromosome, complex, protein, requests (+1 more) |
| DNASupercoiling | 🟢 GREEN | 3 | 8 | 3 | — | chromosome, complex, protein, requests (+1 more) |
| FtsZPolymerization | 🟢 GREEN | 3 | 6 | 3 | — | cell, requests, substrates_allocated |
| HostInteraction | 🟢 GREEN | 3 | 5 | 3 | — | cell, protein |
| MacromolecularComplexation | 🟢 GREEN | 4 | 7 | 4 | — | complex, requests, substrates_allocated |
| Metabolism | 🟢 GREEN | 3 | 4 | 3 | — | metabolic_reaction |
| ProteinActivation | 🟢 GREEN | 3 | 5 | 3 | — | protein, stimuli |
| ProteinDecay | 🟢 GREEN | 5 | 10 | 5 | — | complex, protein, requests, rna (+1 more) |
| ProteinFolding | 🟢 GREEN | 5 | 8 | 5 | — | complex, protein, substrates_allocated |
| ProteinModification | 🟢 GREEN | 5 | 9 | 5 | — | complex, protein, requests, substrates_allocated |
| ProteinProcessingI | 🟢 GREEN | 5 | 9 | 5 | — | complex, protein, requests, substrates_allocated |
| ProteinProcessingII | 🟢 GREEN | 5 | 8 | 5 | — | protein, requests, substrates_allocated |
| ProteinTranslocation | 🟢 GREEN | 4 | 8 | 4 | — | complex, protein, requests, substrates_allocated |
| Replication | 🟢 GREEN | 3 | 6 | 3 | — | chromosome, requests, substrates_allocated |
| ReplicationInitiation | 🟢 GREEN | 3 | 7 | 3 | — | chromosome, protein, requests, substrates_allocated |
| RibosomeAssembly | 🟢 GREEN | 5 | 10 | 5 | — | complex, protein, requests, rna (+1 more) |
| RNADecay | 🟢 GREEN | 3 | 6 | 3 | — | requests, rna, substrates_allocated |
| RNAModification | 🟢 GREEN | 5 | 10 | 5 | — | complex, protein, requests, rna (+1 more) |
| RNAProcessing | 🟢 GREEN | 5 | 10 | 5 | — | complex, protein, requests, rna (+1 more) |
| TerminalOrganelleAssembly | 🟢 GREEN | 3 | 5 | 3 | — | cell, protein |
| Transcription | 🟢 GREEN | 3 | 4 | 3 | — | rna |
| TranscriptionalRegulation | 🟢 GREEN | 3 | 7 | 3 | — | complex, protein, tf_binding, tx_rate_fold_change |
| Translation | 🟢 GREEN | 4 | 5 | 4 | — | protein |
| tRNAAminoacylation | 🟢 GREEN | 5 | 10 | 5 | — | complex, protein, requests, rna (+1 more) |

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
