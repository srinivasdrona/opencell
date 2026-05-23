# Audit: historical merge integrity (parent-count + content-drop forensics)

## Methodology
- Audit timestamp: 2026-05-23 (Asia/Calcutta), report generated from worktree HEAD `a265de1ff29a842de53bc4e3d0e0bf2c9a33cc46`.
- Enumerated all merge commits matching `Merge agent/` via:
  - `git log --all --merges --pretty='%H %P %s' | grep 'Merge agent/'`
- For each 2-parent merge commit `M` with parents `P1` and `P2`, ran content-landing checks:
  1. Branch-side changed files: `git diff --name-only $(git merge-base P1 P2) P2`
  2. Merge-result files vs mainline parent: `git diff --name-only P1 M`
  3. Suspects = files present in (1) but absent in (2)
  4. For each suspect, compared `P2:<file>` vs `M:<file>` existence, line count, and blob IDs; flagged only if substantive branch content was dropped.
- Merge timing cross-check used:
  - `git log --merges --pretty='%ai %h %s' --all`

## Scope Summary
- Total `Merge agent/*` commits examined (2-parent): 42
- Additional sanity-check commit examined: `41809db` (known defective titled-merge with 1 parent)
- Total commits reviewed in this audit: 43

## Confirmed defects

### 1) `41809db455b67e8a87b10db085aee2185f4389ec`
- Subject: `Merge agent/pd-t1-host-interaction (drop .progress.md)`
- Parent count: **1** (`510a04173847ec910b7938e258793a6c59a7acb9`)
- Defect type: merge-resolution misuse (`git rm + git commit`) causing branch-content drop.
- Evidence:
  - Branch tip later re-merged by `8dd146d` is `7cc0ff123fbd310ce86ce9b6e59bc39ba01a8143`.
  - Branch files (`merge-base(6bc34e9,7cc0ff1)..7cc0ff1`):
    - `.progress.md`
    - `docs/design/pd-t1-host-interaction.md`
    - `opencell/vivarium/karr_host_interaction.py`
    - `tests/vivarium/test_karr_host_interaction.py`
  - `41809db` does **not** contain the substantive HostInteraction files.

| File | Branch tip `7cc0ff1` | `41809db` | Re-merge `8dd146d` |
|---|---:|---:|---:|
| `opencell/vivarium/karr_host_interaction.py` | present (280 lines) | missing | present (280 lines, blob matches branch tip) |
| `tests/vivarium/test_karr_host_interaction.py` | present (163 lines) | missing | present (163 lines, blob matches branch tip) |
| `docs/design/pd-t1-host-interaction.md` | present (70 lines) | missing | present (70 lines, blob matches branch tip) |

- Current state: **Recovered** by `8dd146db38116be52a4cd2176702d5c76703c4dc`.

## Suspect cases (2-parent merges)
7 merges had at least one file in branch-side change-set absent from merge diff. After deep checks, all are **false alarms** (metadata/log files only):

1. `eeb6ebf48db31d06b31c51df0cb998bc6b491d44` (`pb-t7-pp2`) missing file: `STATUS.md` -> false alarm
2. `0c52f433268b866cad2118036142be8ac2f8200f` (`pb-t4-rna-processing`) missing file: `STATUS.md` -> false alarm
3. `b2037d81f07bc5d2f2a8f3b57462b1f2614fa239` (`pb-t11-activation`) missing file: `STATUS.md` -> false alarm
4. `ebe7a0e7a9cc7e5180f7151f2d916c26ad50afeb` (`pb-t6-pp1`) missing file: `STATUS.md` -> false alarm
5. `695d9c64891390b02c726db742dbd115ce6880c2` (`pb-t3-tx-regulation`) missing file: `STATUS.md` -> false alarm (auto-threshold hit due 44 lines; manual review cleared)
6. `09bf411494da03c6d0331e54594b9f575700164c` (`pb-t10-translocation`) missing file: `STATUS.md` -> false alarm
7. `a265de1ff29a842de53bc4e3d0e0bf2c9a33cc46` (`fix-set-accumulate-warnings`) missing file: `.progress.md` -> false alarm

Manual clearing evidence pattern for all 7:
- Every missing file is metadata (`STATUS.md` or `.progress.md`).
- Non-metadata files changed on branch were fully present in merge (`branch_non_meta_count == merge_non_meta_count`, no missing non-metadata paths).

Verdict: **No 2-parent merge showed substantive source/test/design content drop.**

## Merge timing cross-reference
High-density merge windows were reviewed with extra attention:
- `2026-05-22 22:41:28` to `22:50:16` (+0530): rapid Phase B burst with multiple same-second merges. Only metadata-file suspects observed; all source content landed.
- `2026-05-23 09:45:04` to `09:45:17` (+0530): rapid Phase C/design burst (many same-second merges). Zero suspect files.

No timing-correlated evidence of mishandled 2-parent content merges was found.

## Required special-case checks

### Phase C (`pc-*`, 12 merges)
- Checked: `pc-t1`..`pc-t10`, `pc-final-chassis-v5-design`, `pc-final-integration`
- Result: **12/12 clean** (no suspects).

### Phase B (`pb-*`, 12 merges)
- Checked: `pb-t1`..`pb-t11`, `pb-final`
- Result: **12/12 functionally clean**.
- Note: 6 had metadata-only `STATUS.md` suspect; all manually cleared.

### A3.3 (`a33-*`, 5 merges)
- Result: **5/5 clean**.

### Earlier named set (`m1-oracle-regen`, `lint-debt`, `llm-log-*`, `probe*`, `open1-count-audit`)
- Result: **7/7 clean**.

## Clean merges
- Auto-clean (no suspect files): 35
- Suspect but manually cleared: 7
- Confirmed defective 2-parent merges: 0
- Net: all 42 two-parent `Merge agent/*` commits are clean after manual review.

## Recovery actions needed
- **None.**
- No unrecovered 2-parent merge defects found.
- Known defective single-parent commit `41809db` is already recovered by `8dd146d`.
