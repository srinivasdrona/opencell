# Karr 2012 `.mat` Extraction — MATLAB Online Runbook

**Goal:** deserialize the opaque `MatlabOpaque` blobs in Karr's WholeCell `.mat`
files into plain structs that `scipy.io.loadmat` can read, WITHOUT synthesizing
any values.

**Script:** `scripts/matlab/extract_karr_mats.m`

---

## One-time setup (MATLAB Online)

1. Create a free MathWorks account → https://matlab.mathworks.com
2. Sign in to MATLAB Online (browser-based; no install needed).
3. Upload the WholeCell folder. Two options:
   - **Option A (recommended, fastest):** upload just the pieces the script
     needs. Zip these locally and drop the zip in MATLAB Online's *Home*
     folder, then right-click → *Extract*:
     ```
     WholeCell/
       setPath.m
       setWarnings.m
       setPreferences.m         (optional; script tolerates absence)
       getConfig.m              (optional)
       data/                    (contains .mat files to extract)
       src/                     (class definitions — required)
       src_test/                (fixtures + test classes — required)
       lib/absolutepath/        (required by setPath.m)
     ```
     From our clone at `data/m1_sources/WholeCell/`, the total is ~180 MB.
   - **Option B:** clone fresh inside MATLAB Online:
     ```matlab
     !git clone https://github.com/CovertLab/WholeCell.git
     ```
     Same layout.

4. Upload the extraction script:
   - From this repo, copy `scripts/matlab/extract_karr_mats.m` into the
     WholeCell folder in MATLAB Online (or anywhere on the MATLAB path).

---

## Running the extraction

In the MATLAB Online command window:

```matlab
cd('WholeCell')                       % or wherever you put the clone
extract_karr_mats(pwd, fullfile(pwd, 'karr_flat'))
```

Runtime: expect 2–15 minutes depending on how many `src_test/.../fixtures/*.mat`
files are present (~50 files total, most ~1.4 MB each).

The script prints per-file status:
```
[1/52] data/Simulation_fitted.mat
   -> data__Simulation_fitted_flat.mat  (2837421 bytes)
...
[extract_karr_mats] DONE: 48 of 52 files flattened.
```

It tolerates errors: any file that fails to load gets an `error` entry in
`manifest.json` rather than aborting the whole run.

---

## Collecting the output

A `karr_flat/` folder is produced containing:

- `data__Simulation_fitted_flat.mat`     (fitted whole-sim snapshot — the prize)
- `data__knowledgeBase_flat.mat`         (pre-fit KB)
- `data__Simulation_fitted_R<rev>_flat.mat` (revision snapshots, optional)
- `fixtures__Metabolism_flat.mat`        (per-process test fixtures, 25 files)
- `fixtures__Translation_flat.mat`, …
- `fixtures__CellMass_flat.mat`          (per-state test fixtures, 19 files)
- `manifest.json`                        (sha256s, MATLAB release, status per file)

Download `karr_flat/` as a zip from MATLAB Online (right-click → *Download*),
then unzip into this repo at:

```
data/m1_sources/karr_flat/
```

That directory is git-ignored for size; we commit only `manifest.json` as
provenance.

---

## Verifying outputs (back in WSL venv)

```bash
source .venv-wsl/bin/activate
python - <<'PY'
from scipy.io import loadmat
m = loadmat('data/m1_sources/karr_flat/data__Simulation_fitted_flat.mat',
            struct_as_record=False, squeeze_me=True)
d = m['data']
print('top-level fields:', [k for k in dir(d) if not k.startswith('_')])
PY
```

You should see a nested struct tree. If the top entry carries
`x_class_ = 'edu.stanford.covert.cell.sim.Simulation'`, the walk succeeded.

---

## What we do with it next

`m1-karr-flat-ingest` (SQL todo) will:
1. Parse `data__Simulation_fitted_flat.mat` for:
   - the *fitted* biomass composition (replaces our current WCKB xlsx guesswork)
   - fitted kinetic rates, NGAM, GAM, growth rate, exchange caps
   - the exact stoichiometry matrix used by Karr's metabolism process
2. Replace the iPS189-based Mode A of `scripts/m1_validate.py` with a
   Karr-fitted-S pFBA run.
3. Update `artifacts/M1_validation.json` + `docs/phase5/M1_validation_report.md`
   to show a proper 1:1 comparison with Karr's published targets.
4. Fire `tests/m1/test_no_hardcoded_numerics_in_module` and
   `test_validation_artifact` to lock the new values.

Acceptance: ≥ 3 of 4 Karr published targets agree within 10 %.

---

## Troubleshooting

- **"Undefined function or variable 'Simulation'"** → `src/` is not on the
  path. Re-run with `cd` into the correct folder; the script calls
  `setPath()` automatically.
- **"Error using containers.Map"** → MATLAB Online has this by default;
  double-check you're running R2019a or newer (MATLAB Online is always
  current).
- **A specific file fails** → check `manifest.json` for the error id;
  common one is `MATLAB:class:InvalidHandle` for a fixture whose referenced
  class moved between Karr revisions. Safe to skip; we don't need every
  fixture.
- **Script hangs** → MATLAB Online Basic has a 20-hour session cap and no
  timeout on individual calls; but it may appear frozen on large objects.
  Check the Desktop tab to confirm MATLAB is still responsive.
