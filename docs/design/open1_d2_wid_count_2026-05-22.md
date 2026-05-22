# OPEN-1 Audit: D.2 WID Count Reconciliation (2026-05-22)

## Scope

This audit reconciles the D.2-owned complex WID count three ways, per
`docs/design/a3_step3_joint_design_v1.md` §1.1 and §6.3.

Inputs used:

- `docs/karr_extracts/process/23_MacromolecularComplexation.md`
- `docs/karr_extracts/process/24_RibosomeAssembly.md`
- `data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat`
- `data/karr_fixtures/per_process/RibosomeAssembly_flat.mat`
- `data/karr_fixtures/per_process/ProteinComplex_flat.mat`
- `data/karr_fixtures/per_process/Metabolite_flat.mat` (needed to decode process index -> process name)

Audit script: `scripts/audit_d2_wid_count.py`

## Results (side-by-side)

| Source | MC count | RibAsm count | Total |
|---|---:|---:|---:|
| 1. Karr docstring claim (`23_*.md` + `24_*.md`) | 149 | 2 | 151 |
| 2. Existing fixture extraction used by `karr_d2_stub` | 147 | 2 | 149 |
| 3. Live cross-check from `ProteinComplex_flat.mat` `formationProcesses` | 147 | 2 | 149 |

### Where the current `147` actually comes from

The existing d2-stub path reads:

- `MacromolecularComplexation_flat.mat` -> `data.fixture.complexWholeCellModelIDs` (length **147**)
- `RibosomeAssembly_flat.mat` -> `data.fixture.complexWholeCellModelIDs` (length **2**)

Union = **149** total D.2-owned WIDs in current fixtures.

## WID-level diffs

Compared explicit sets:

- Source 2 (`MC fixture union RA fixture`) vs Source 3 (`ProteinComplex formationProcesses in {Process_MacromolecularComplexation, Process_RibosomeAssembly}`)

Result:

- Source 2 only: **none**
- Source 3 only: **none**

So the two fixture-derived methods are identical at WID level.

## Conclusion

Canonical count for A3.3 should be **149 total D.2-owned WIDs**
(`147 MC + 2 RibAsm`) based on live fixture data, because:

1. Two independent fixture-derived methods agree exactly at set level.
2. The discrepancy is between historical docstring text (`149 + 2 = 151`) and the model snapshot fixtures, not between fixture extraction paths.

### Is there a fixture-extraction bug?

No extraction-side mismatch was detected in this audit.

- Producer of `_flat.mat` files: `scripts/matlab/extract_per_process_fixtures.m`
- Python ingest pipeline: `scripts/extract_per_process_fixtures.py --from-flat`

Given Source 2 == Source 3 (including exact WID set), there is no evidence that these scripts introduced a D.2 ownership count bug for this case.

### Proposed one-line fix (design/doc side, not fixture build)

Because the mismatch is doc-claim-side, the actionable one-line fix before A3.3 is in design text:

- Replace `149 by MacromolecularComplexation + 2 by RibosomeAssembly = 151` with
  `147 by MacromolecularComplexation + 2 by RibosomeAssembly = 149 (per live fixtures)`.

(Do not apply here; leave for design-doc update as requested.)

## Repro

```bash
python scripts/audit_d2_wid_count.py
```

Observed output:

```text
=== OPEN-1 D.2 WID count audit ===
source1_docstring_claim: mc=149 ra=2 total=151
source2_fixture_union : mc=147 ra=2 total=149
source3_live_crosschk : mc=147 ra=2 total=149

source2_total only (0): <none>
source3_total only (0): <none>

docstring_minus_live_total=2 (positive means docstring claim is larger)
```
