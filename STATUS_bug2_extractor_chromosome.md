# STATUS Bug 2 Extractor Chromosome

## Beat 1 - confirm allowlist gap

Read surface:
- `scripts/matlab/extract_per_process_traces_v2.m:114-131` (`pick_snapshot_properties`)
- `scripts/matlab/extract_per_process_traces_v2.m:133-200` (`evolve_state_with_tap`)

Current `pick_snapshot_properties` allowlist:

```matlab
function props = pick_snapshot_properties(proc)
props = intersect(properties(proc), { ...
    'substrates', 'enzymes', 'boundEnzymes', ...
    'freeRNAs', 'aminoacylatedRNAs', ...
    'mRNAs', 'freeTRNAs', 'freeTMRNA', ...
    'aminoacylatedTRNAs', 'aminoacylatedTMRNA', 'boundTMRNA', ...
    'unprocessedRNAs', 'processedRNAs', 'intergenicRNAs', ...
    'unmodifiedRNAs', 'modifiedRNAs', ...
    'unprocessedMonomers', 'processedMonomers', ...
    'signalSequenceMonomers', ...
    'unmodifiedMonomers', 'modifiedMonomers', ...
    'unfoldedMonomers', 'foldedMonomers', ...
    'unfoldedComplexs', 'foldedComplexs', ...
    'inactiveMonomers', 'matureMonomers', ...
    'inactiveComplexs', 'matureComplexs', ...
    'complexs', 'monomers', 'rnas', 'RNAs', ...
});
end
```

Finding:
- `chromosome` is absent from the allowlist.
- `pick_snapshot_properties` feeds the snapshot structures used by `evolve_state_with_tap`, so omission here means `snapshot_props` excludes `chromosome` even when the process exposes it as a top-level property.
- Adding `chromosome` will cause future extractions for `Replication`, `DNARepair`, and `ReplicationInitiation` to include chromosome in `snapshot_props`, which in turn allows `states_before` and `states_after` to carry that channel forward.

## Beat 2 - extend the allowlist

Pending.

## Beat 3 - single-seed verification

Pending.

## Beat 4 - inversion

Pending.

## Beat 5 - operator handoff note

Pending.

verdict: PENDING
