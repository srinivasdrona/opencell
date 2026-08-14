# L2.1 Active Windows Status

Canonical machine-readable artifact:
`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`

Replay command executed:

```text
bin\oc-pytest.cmd -q tests/vivarium/test_karr_dna_repair_l2_replay.py::test_karr_dna_repair_l2_replay_identity_per_tick tests/vivarium/test_karr_metabolism_l2_replay.py::test_karr_metabolism_l2_replay_identity_per_tick tests/vivarium/test_karr_protein_decay_l2_replay.py::test_karr_protein_decay_l2_replay_identity_per_tick tests/vivarium/test_karr_replication_l2_replay.py::test_karr_replication_l2_replay_identity_per_tick tests/vivarium/test_karr_rna_modification_l2_replay.py::test_karr_rna_modification_l2_event_replay tests/vivarium/test_karr_ribosome_assembly_l2_replay.py::test_karr_ribosome_assembly_l2_event_replay
```

Observed result: `6 passed in 47.83s`

Inventory result:

| Process | Classification | Source / hash | Earliest active window | Evidence |
| --- | --- | --- | --- | --- |
| DNARepair | `EXISTING_WINDOW_PASS` | `.../per_process_traces_v2/DNARepair_100ticks.mat` `a26696b9...` | abs tick `8`; trigger `chromosome.repair_event_present` | manifest row + replay test passed |
| Metabolism | `EXISTING_WINDOW_PASS` | `.../per_process_traces_v2/Metabolism_100ticks.mat` `c72ee578...` | abs tick `0`; trigger `substrates[10] 3622 -> 0` | manifest row + replay test passed |
| ProteinDecay | `EXISTING_WINDOW_PASS` | `.../per_process_traces_v2/ProteinDecay_100ticks.mat` `f8699384...` | abs tick `3`; trigger `substrates[0] 0 -> 6` | manifest row + replay test passed |
| Replication | `EXISTING_WINDOW_PASS` | `.../per_process_traces_v2/Replication_100ticks.mat` `6d96e9b9...` | abs tick `0`; trigger `polymerizedRegions.delta_value_sum_strand_2 = -44` | manifest row + replay test passed |
| TranscriptionalRegulation | `MISSING_ACTIVE_EXTRACTION` | `.../per_process_traces_v2/TranscriptionalRegulation_100ticks.mat` `9f998483...` | no non-trivial tick in inspected local standard trace | manifest row |
| ChromosomeSegregation | `MISSING_ACTIVE_EXTRACTION` | `.../per_process_traces_v2/ChromosomeSegregation_100ticks.mat` `18e03828...` | no non-trivial tick in inspected local standard trace | manifest row |
| Cytokinesis | `MISSING_ACTIVE_EXTRACTION` | `.../per_process_traces_v2_event_s000/Cytokinesis_4000ticks.mat` `de09b63c...` | onset abs tick `27556`; captured window starts at `27428`; only 1 Karr seed exists | `docs/phase_f/l2_event/evidence_bundle/Cytokinesis/{SUMMARY,result}.json` report `NOT_APPLICABLE` structural smoke, not replay authority |
| DNADamage | `MISSING_ACTIVE_EXTRACTION` | `.../per_process_traces_v2/DNADamage_100ticks.mat` `996043f7...` | no non-trivial tick in inspected no-stimulus standard trace | manifest row |
| HostInteraction | `MISSING_ACTIVE_EXTRACTION` | `.../per_process_traces_v2/HostInteraction_100ticks.mat` `a87006a3...` | no non-trivial tick in inspected local standard trace | manifest row |
| RNAModification | `EXISTING_WINDOW_PASS` | `.../per_process_traces_v2_event_s000/RNAModification_100ticks.mat` `aebb6d51...` | abs tick `200`; trigger `substrates[0] 0 -> 1` | manifest row + event replay test passed |
| RibosomeAssembly | `EXISTING_WINDOW_PASS` | `.../per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat` `834b0a79...` | abs tick `209`; trigger `complexs[1] 0 -> 1` | manifest row + event replay test passed |

No row produced a verified `CODE_GAP` in this track. The six reusable active-window rows all replayed green, and the other five rows still require new or broader active extractions rather than process-port fixes.

Explicit extraction requests:

| Process | Request |
| --- | --- |
| TranscriptionalRegulation | Request the earliest non-trivial `per_process_traces_v2` seed beyond the current inactive local standard trace. |
| ChromosomeSegregation | Request a late-cell-cycle active window; the inspected birth-window standard trace is inactive. |
| Cytokinesis | Run the authorized onset-span survey, then extract the remaining 49 completion-anchored event-window seeds before any L2.1 batch claim. |
| DNADamage | Request a stimulus-conditioned active window (`UVB_radiation` or `gamma_radiation`); current local traces are no-stimulus. |
| HostInteraction | Request a host-conditioned active window; the local no-host standard trace is inactive by construction. |
