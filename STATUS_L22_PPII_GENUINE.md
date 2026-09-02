# STATUS_L22_PPII_GENUINE

## Objective

Replace the rejected `bfbfe5d` ProteinProcessingII full50 active-window
evidence with genuine-provider evidence that is portable, tracked, and
independently re-validatable under the accepted post-`25257ca` Statistics RNG
provider contract.

## Completed Work

- Read and compared:
  - `SESSION_CONTEXT.md`
  - `PROMPT_GENUINE_REEXTRACT.md`
  - `STATUS_L22_PPII_ISOLATED.md`
  - `STATUS_L22_PPII_RESTART.md`
  - `STATUS_MNRND_PROVIDER.md`
  - `plan.md`
  - commits `1a95200`, `25257ca`, `bfbfe5d`
- Confirmed the current rejection causes are still present:
  - `scripts/l22_evidence/ppii_active_windows.py` still accepts
    `accepted_external_fixture`
  - `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_active_window_manifest.full50.json`
    still contains machine-absolute `/mnt/e/...` paths
  - the tracked repo has the 22 rejected replacement-window MATs but no tracked
    producing MATLAB driver
  - the local worktree does not contain the 28 canonical PPII birth traces, so
    a portable full50 manifest cannot keep depending on sibling-worktree paths
- Confirmed the accepted provider contract to reuse:
  - `scripts/matlab/karr_bootstrap.m`
  - `scripts/matlab/extract_per_process_traces_v2.m`
  - `scripts/l2_event/launcher.py`
- Confirmed the best process-local extraction pattern to mirror:
  - `scripts/matlab/extract_macromol_active_window_seeds.m`
  - `scripts/l22_extraction/macromol_active_window.py`
- Landed the first local implementation chunk:
  - added `scripts/l22_extraction/ppii_active_window.py`
  - added `scripts/matlab/extract_ppii_active_window_seeds.m`
  - tightened `scripts/l22_evidence/ppii_active_windows.py` so genuine-provider active-window
    rows must declare `tracked_extraction_provenance` instead of relying on
    `accepted_external_fixture`
  - added focused contract/static tests and made them pass
- Copied the covered28 canonical birth traces from `main-integrate` into this
  worktree's repo-local `data/m1_sources/karr_native/per_process_traces_v2*`
  layout so the rebuilt full50 manifest can be portable.
- Smoke-tested the new MATLAB driver on seed 0 and found a real bug:
  the scan side matched `proc_obj.wholeCellModelID` too strictly and missed
  `Process_ProteinProcessingII`. Fixed the driver to mirror
  `extract_per_process_traces_v2.m`'s canonical token resolution and
  re-ran the focused PPII suite green.
- A second MATLAB smoke on seed 0 reached the real full scheduler and then
  failed on missing WholeCell `lib` helper resolution (`isodd`). Fixed the
  driver's scan prelude to preload the same WholeCell runtime path setup the
  accepted extractor uses (`setPath()`/`src`+`lib` fallback), then re-ran the
  focused PPII suite green again.
- A third MATLAB smoke on seed 0 reached genuine-provider temp trace capture
  and then failed while hashing the driver file for provenance metadata,
  because `mfilename('fullpath')` omitted the `.m` extension. Fixed the
  driver to bind the actual on-disk script path and re-ran the focused PPII
  suite green again.
- Re-launched under the required three-slot MATLAB contract (`-Slots 3`),
  which bypassed unrelated global slot contention from other worktrees.
- Confirmed the existing `artifacts/ppii_active_window` cohort is still
  inadmissible: it covers the right 22 later seeds but lacks tracked driver
  and genuine-provider metadata fields.
- Successfully extracted and internally validated repo-local first
  regime-valid transferase windows on the genuine-provider trajectory for
  seeds `0, 1, 4, 7, 8, 9` under
  `data/m1_sources/karr_native/ppii_active_window/...`.
- Continued the fresh-process slot-3 extraction pass and successfully
  extracted + internally validated genuine-provider active-window MATs for seeds
  `11, 12, 14, 16, 17, 18`. At this checkpoint the genuine repo-local later
  cohort covers 12 of the required 22 missing seeds.
- Began the final ten-seed pass. Seeds `20`, `25`, and `28` completed and
  validated successfully. Seed `30` is still running in its own fresh MATLAB
  process on slot 3 after the batch command timed out, so extraction will
  resume from seed `30` onward instead of re-running the already-complete
  earlier seeds.
- Completed the genuine-provider active-window extraction pass by retrying seed `30`
  successfully in isolation and then finishing seeds
  `31, 32, 33, 36, 41, 49`. The genuine repo-local later cohort now covers
  all 22 previously missing seeds.
- Rebuilt
  `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_active_window_manifest.full50.json`
  as a portable repo-relative full50 manifest:
  - the 28 covered birth rows now resolve to repo-local copied canonical
    oracle traces
  - the 22 replacement rows now resolve to repo-local genuine-provider MATs under
    `data/m1_sources/karr_native/ppii_active_window/...`
  - every genuine-provider row records tracked extraction provenance including driver
    hash, provider identity, fixture/source hashes, seed/window identity, and
    MAT hash
- Re-ran the required verification suite against the rebuilt full50 manifest:
  - `bin\oc-pytest.cmd tests/scripts/test_ppii_active_windows.py tests/scripts/test_ppii_active_window_contract.py tests/scripts/test_extract_ppii_active_window_seeds_static.py -q`
    -> `9 passed`
  - `bin\oc-py.cmd -m ruff check scripts/l22_extraction/ppii_active_window.py scripts/l22_evidence/ppii_active_windows.py tests/scripts/test_ppii_active_windows.py tests/scripts/test_ppii_active_window_contract.py tests/scripts/test_extract_ppii_active_window_seeds_static.py`
    -> `All checks passed!`
  - `bin\oc-py.cmd scripts/l22_evidence/ppii_active_windows.py --manifest docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_active_window_manifest.full50.json --out tmp/ppii_active_window_validation.full50.json --require-full-catalog`
    -> `seeds=50/50 window_verdict=H12_CONFIRMED promotion_ready=True`
- Ran a fresh-clone/path-relocation portability proof from a new local clone:
  - rebuilding the full50 manifest at the relocated path produced no diff
  - rerunning the full-catalog validator at the relocated path again yielded
    `seeds=50/50 window_verdict=H12_CONFIRMED promotion_ready=True`
  - grep checks found no machine-absolute path hits in the relocated manifest
    or relocated validation artifact

## Final Verification

1. Tracked extraction driver:
   `scripts/matlab/extract_ppii_active_window_seeds.m`
2. Portable full50 manifest:
   `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_active_window_manifest.full50.json`
3. Full50 validation artifact:
   `tmp/ppii_active_window_validation.full50.json`
4. Green chunk commits:
   `1b835c7`, `f069060`, `8a739df`, `42f925e`, `d42d471`, `44433b2`,
   `9e4472f`, `5f2d5b2`, `6586513`

## Supersession

- The rejected `bfbfe5d` full50 claim is superseded by the tracked repo-local
  evidence chain above.
- The merge authority for ProteinProcessingII active-window full50 evidence is
  now the rebuilt repo-relative manifest plus the repo-local covered28 traces,
  the repo-local 22-seed genuine-provider-trajectory MAT cohort, and the tracked
  validation artifact.
- The previously rejected shim-derived files under `artifacts/ppii_active_window`
  remain non-authoritative because they lack the accepted tracked driver and
  genuine-provider provenance fields.

## Notes

- Shared `scripts/l22_evidence/h12.py` must remain byte-identical.
- Python execution must use only `bin\oc-py.cmd` and `bin\oc-pytest.cmd`.
- The 22 shim-derived MATs from `bfbfe5d` may be overwritten or replaced
  because their rejection is formally recorded.

## Cohort interpretation

This authority intentionally combines 28 accepted population-era birth traces
with 22 first regime-valid transferase windows from genuine-provider reruns.
For seeds `1`, `4`, `11`, and `20`, the genuine-provider transferase window
falls within absolute ticks `1..100`; it is not "later" than the accepted
birth trace. The two trajectories differ because the RNG provider changed.
The H12 claim is conditional source-faithful convergence on each recorded
window, not trajectory identity between the two provider eras.
