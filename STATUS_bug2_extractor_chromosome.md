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
- Cleanup complete: deleted `data/m1_sources/karr_native/per_process_traces_v2_s000_bug2test/` after verification.

## Beat 4 - inversion

Falsifier 1:
- Evidence that would justify NOT adding `chromosome`: if `chromosome` were exposed as a property but serialized as a transient/handle reference that did not survive `-v7.3` save in a meaningful way.
- Why that did not materialize here: Beat 3 showed `states_before/chromosome`, `states_after/chromosome`, and metadata inclusion in the saved MAT file itself, falsifying the "metadata-only / non-serializing handle" failure mode.

Falsifier 2:
- Evidence that would justify adding MORE chromosome subfields explicitly to the allowlist: if `properties(proc)` returned chromosome subfields as separate top-level properties for any affected process.
- Why that did not materialize here: the extractor works from `properties(proc)` top-level names, and the fix only needed the single top-level `chromosome` entry. Beat 3 showed the saved channel is the top-level chromosome object/state, matching the downstream Python-side projection design.

Falsifier 3:
- What would make the fix wrong for `ReplicationInitiation` specifically: if its `chromosome` property were read-only, always empty, or otherwise semantically irrelevant to that process.
- Why the fix still stands: the authoritative catalog lists `chromosome` in `ReplicationInitiation` input channels, output channels, and event channels, so the extractor should snapshot it when the property is exposed.

## Beat 5 - operator handoff note

Bug 2 fix landed. To benefit from the fix, the operator must re-run the 50-seed MATLAB extraction for the 3 affected processes (`Replication`, `DNARepair`, `ReplicationInitiation`). The existing `per_process_traces_v2_s{000..049}/` extracts for these processes are stale - they have substrates/enzymes/boundEnzymes but not chromosome.

Suggested invocation (serial, single MATLAB license):

```powershell
& bash scripts/git_hooks/install.sh   # ensure hook is installed
& "E:\MATLAB\bin\matlab.exe" -batch "cd('E:/opencell-worktrees/bug2-extractor-chromosome/scripts/matlab'); processes = {'Replication','DNARepair','ReplicationInitiation'}; for s = 0:49, seed_dir = sprintf('per_process_traces_v2_s%03d', s); extract_per_process_traces_v2(processes, seed_dir, 100, uint32(s)); end"
```

Expected wall:
- ~50 min total (`3 processes x 50 seeds`, about `~20s` per seed-process combination based on Day-23 timing).

Unaffected extracts:
- `MacromolecularComplexation` and `Cytokinesis` Day-23 extracts remain valid and should not be re-extracted.

verdict: PASS
