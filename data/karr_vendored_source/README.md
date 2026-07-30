# Vendored Karr 2012 WholeCell MATLAB process source (H12 evidence)

## Why this directory exists

`data/m1_sources/WholeCell/` is a **gitignored clone target** (see
`.gitignore`: "Karr WholeCell MATLAB source trees (clone targets, not
source-of-truth)") — it is populated on demand by cloning
`https://github.com/CovertLab/WholeCell` locally, and is **not guaranteed
to exist in a fresh checkout** of this repository.

`scripts/l22_evidence/h12.py`'s H12 machine-evidence artifacts
(`docs/phase_f/l2_2_design_a/h12/*.json`) cite specific MATLAB source line
ranges as the derivation basis for each closed-form predictor, per the H12
anti-laundering rule ("predictor must be independently derived from Karr
MATLAB source ... document source line citations"). A hash/citation that
can only be verified against a gitignored, possibly-absent clone target is
not a real provenance guarantee — a fresh clone of this repo could never
re-verify it. This directory vendors the exact 5 `.m` files the H12
predictors cite, **tracked in git**, so:

1. `scripts/l22_evidence/h12.py` hashes and cites line ranges against
   these tracked files (not the gitignored clone target).
2. A fresh clone can always re-verify every H12 artifact's
   `vendored_sha256_lf_normalized` / line-range citations without needing
   network access or a separate MATLAB source clone.

## Provenance

Copied verbatim (byte-for-byte, no modifications) from:

- Upstream repository: `https://github.com/CovertLab/WholeCell`
- Commit: `6cdee6b355aa0f5ff2953b1ab356eea049108e07` (2015-04-22)
- Original path: `src/+edu/+stanford/+covert/+cell/+sim/+process/<File>.m`

| Vendored file | Upstream original path |
|---|---|
| `MacromolecularComplexation.m` | `src/+edu/+stanford/+covert/+cell/+sim/+process/MacromolecularComplexation.m` |
| `ProteinFolding.m` | `src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinFolding.m` |
| `ProteinProcessingI.m` | `src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingI.m` |
| `ProteinProcessingII.m` | `src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingII.m` |
| `tRNAAminoacylation.m` | `src/+edu/+stanford/+covert/+cell/+sim/+process/tRNAAminoacylation.m` |

## License

MIT (Karr, Sanghvi, Macklin, Jacobs, Covert, 2012) — see
`LICENSE_WholeCell.txt` in this directory, copied verbatim from the
upstream repository root (`license.txt`). Already cleared for
"read/port" use in `LICENSES.md`'s "Karr 2012 / Mycoplasma genitalium
model artefacts" table. This notice must remain alongside the vendored
files per the license's own terms ("The above copyright notice and this
permission notice shall be included in all copies or substantial
portions of the Software").

## Integrity

These files are frozen, read-only citations. Do not edit them. If a
predictor's citation needs correcting, correct the citation (line range)
in `scripts/l22_evidence/h12.py`, or re-vendor from a newer upstream
commit and update the table above with the new commit hash — never
hand-edit the vendored `.m` text itself.
