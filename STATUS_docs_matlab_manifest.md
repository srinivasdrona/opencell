# STATUS_docs_matlab_manifest

Completed: 2026-05-27 13:12:02 +05:30

## Deliverable
- Wrote `docs/phase_e/MATLAB_FILE_MANIFEST.md`.
- Section coverage: inventory, 5-stream coverage map, license gap buckets, license-restored MATLAB wishlist, quick-reference appendix.

## Headline metrics
- MATLAB `.mat` files inventoried across canonical + worktree fixture roots: **161**
  - Under 2 MB probed with `scipy.io.loadmat`: **150**
  - Over 2 MB size-listed only: **11**
- MATLAB `.m` sources inventoried: **562**
  - WholeCell mirror: 538
  - OpenCell `scripts/matlab`: 18
  - OpenCell mirrored fixture source snippets: 6
- Open work streams covered in Section 2: **5/5**.
- True license-blocker classes (Bucket A): **3**
  1. new simulation generation (ensemble seeds / new sweeps),
  2. regeneration of missing/truncated artifacts via MATLAB runs,
  3. new-field extraction from MCOS sources when no flattened/archive surrogate exists.

## Key findings captured in manifest
- Canonical corpus exists on disk at `E:\opencell\data\m1_sources` (with `WholeCell` symlink to `E:\opencell-mirrors\WholeCell`).
- Worktree `data/m1_sources` is sparse; full assets are outside this worktree in canonical location.
- Karr native trace status: 28 main trace files + 5 `_truncated_backup` duplicates; 23 full-fidelity, 5 tiny/truncated.
- Initial-state coverage: 23/28 (missing 5 process init mats).
- Karr 2012 supplement files are HTML download stubs (placeholders), not real spreadsheet payloads.
- PP2 + ProteinModification immediate triage inputs are already on disk (flat fixtures + full 100-tick traces).

## Commits
1. `docs(phase_e): add MATLAB file manifest + coverage map + license wishlist`
2. `docs(status): summarize matlab manifest inventory run`
