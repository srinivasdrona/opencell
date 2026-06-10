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

Change:

```matlab
function props = pick_snapshot_properties(proc)
props = intersect(properties(proc), { ...
    'substrates', 'enzymes', 'boundEnzymes', 'chromosome', ...
    ...
    'complexs', 'monomers', 'rnas', 'RNAs', ...
});
end
```

Notes:
- Added exactly one new top-level entry: `chromosome`.
- Did not add chromosome subfields such as `delta_fork_position_bp` or `replication_state`; those remain downstream Python projections from the saved chromosome struct/state object.

## Beat 3 - single-seed verification

MATLAB command run:

```powershell
& "E:\MATLAB\bin\matlab.exe" -batch "cd('E:/opencell-worktrees/bug2-extractor-chromosome/scripts/matlab'); extract_per_process_traces_v2({'Replication'}, 'per_process_traces_v2_s000_bug2test', 100, uint32(0))"
```

MATLAB stdout highlight:

```text
[trace_v2] Replication snapshot properties: boundEnzymes, chromosome, enzymes, substrates
[trace_v2] saved: E:\opencell-worktrees\bug2-extractor-chromosome\data\m1_sources\karr_native\per_process_traces_v2_s000_bug2test\Replication_100ticks.mat
```

`h5py` probe output:

```text
top-level keys: ['#refs#', 'metadata', 'states_after', 'states_before']
states_before keys: ['boundEnzymes', 'chromosome', 'enzymes', 'substrates']
states_after keys: ['boundEnzymes', 'chromosome', 'enzymes', 'substrates']
metadata snapshot_properties: ['boundEnzymes', 'chromosome', 'enzymes', 'substrates']
```

Result:
- PASS: `states_before/chromosome` exists.
- PASS: `states_after/chromosome` exists.
- PASS: `metadata/snapshot_properties` includes `chromosome`.
- Cleanup required after capture: delete `data/m1_sources/karr_native/per_process_traces_v2_s000_bug2test/`.

## Beat 4 - inversion

Pending.

## Beat 5 - operator handoff note

Pending.

verdict: PENDING
