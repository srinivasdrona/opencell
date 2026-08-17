# STATUS_MNRND_PROVIDER

## Outcome

`READY_FOR_INDEPENDENT_REVIEW`

Full-simulation extraction now requires the genuine Statistics and Machine
Learning Toolbox implementations of all five repo-shadowed RNG entry points
(`binornd`, `mnrnd`, `poissrnd`, `random`, `randsample`), re-promotes them
after repo paths are added, fails closed if any is missing or shadowed
including by the caller's current directory, records their exact provider
identities, and rejects legacy shim-bound traces.

The repo compatibility shim remains byte-identical and retains its isolated
Octave tests, but is no longer admissible as a full-simulation provider.

## Verified provider

```text
kind: statistics_toolbox
MATLAB release: R2026a
toolbox version: 26.1
path relative to matlabroot: toolbox/stats/stats/mnrnd.m
LF-normalized SHA-256:
d68e8ff78af266ad4977e80cd5366cc59984ada5f73ab591a9c08350bc4471dc
```

## Implementation

- `scripts/matlab/karr_bootstrap.m`
  - checks out Statistics Toolbox;
  - requires all five real providers under `matlabroot`;
  - re-promotes the provider directory after repo/WholeCell paths;
  - verifies every `which(...)` exactly both inside the WholeCell root and
    again after restoring the caller's original working directory;
  - returns provider release/version/path/hash metadata.
- `scripts/matlab/extract_per_process_traces_v2.m`
  - binds genuine-provider metadata into fixed/anchor traces;
  - no longer writes shim identity metadata.
- `scripts/l2_event/launcher.py`
  - promotes the genuine provider in generated MATLAB commands;
  - discovers MATLAB root correctly on Windows and WSL;
  - validates release/version/path/hash for all five RNG providers against
    the local install;
  - marks missing-provider and legacy shim traces invalid.
- `scripts/l2_event/write_cytokinesis_canary_d_evidence.py`
  - carries genuine-provider identity into evidence reasons and summaries.
- `docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md`
  - replaces the former shim-authority contract with the genuine-provider
    fail-closed contract.
- Tests were migrated to provider metadata. A real WSL-to-Windows MATLAB
  smoke proves bootstrap changes all five resolutions from repo shims to the
  toolbox providers, and a caller-CWD shim fails closed.
- `scripts/l22_extraction/launcher.py`
  - mirrors genuine-provider path promotion;
  - rethrows extraction failures so provider errors cannot return exit 0.

## Verification

- Ruff: PASS on all changed Python/test files.
- Targeted provider/extractor/launcher/shim suite:
  - `105 passed` including both real MATLAB smoke cases.
- Expanded affected event suite:
  - `170 passed, 4 skipped`.
  - The four skips are raw local RibosomeAssembly/Cytokinesis trace checks;
    those trace files are absent in this clean worktree.
- `git diff --check`: PASS.
- `scripts/matlab/mnrnd.m`: byte-identical to branch base.

## Regeneration blast radius

Every fixed/anchor trace carrying `mnrnd_shim_*` metadata, or lacking the new
`mnrnd_provider_*` and `statistics_rng_provider_identity_json` fields, is
explicitly non-authoritative and must be regenerated before reuse. The
identity records provider paths and hashes for all five colliding RNG
functions, because provider promotion changes every one of them.

This includes the existing event-window evidence families for Cytokinesis,
FtsZPolymerization, RibosomeAssembly, DNADamage, and any active-window
extraction routed through the event launcher. Main's existing N=50 event
tests will remain red or stale until those cohorts are regenerated.

Process-specific custom extractors must also record/bind this provider before
their outputs can be promoted; this patch does not silently bless old
MacromolecularComplexation or PPII artifacts.
