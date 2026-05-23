# Extract Karr 2012 Reference Trajectories

## Why this matters

We've spent 10 days fixing substrate cascades. We now have a chassis that runs without negative drift. But "no cascade" ≠ "correct biology". To convert this work into a reproducible scientific result, we need a benchmark: do our trajectories match the Karr 2012 published simulation of *Mycoplasma genitalium* whole-cell behavior?

Karr et al. 2012 (*Cell*, "A Whole-Cell Computational Model Predicts Phenotype from Genotype"): https://doi.org/10.1016/j.cell.2012.05.044

Their open-source MATLAB code: https://github.com/CovertLab/WholeCell

We need to extract reference single-cell-cycle trajectories from their published artifacts so we can compare our 32,400-tick run against them quantitatively.

## Hard rules

- 130k token ceiling. Compact and STATUS before crossing.
- Commit incrementally after each step.
- **DO NOT pause to ask the user questions.** Make safe defaults; document choices in STATUS.
- Untracked `.codex*.log` / `.launch*.ps1` files: ignore.
- Work in a NEW worktree to avoid colliding with phase-2-fix.
- This is RESEARCH + LIGHT CODING. Output is a clean reference dataset + extraction script. No production code in `opencell/`.

## Setup

```powershell
cd E:\opencell
git fetch
git worktree add E:\opencell-worktrees\karr-reference -b agent/karr-reference origin/main
cd E:\opencell-worktrees\karr-reference
```

## Your task

### Step 1: Locate Karr 2012's published trajectories

Three candidate sources, in order of preference:

1. **CovertLab/WholeCell GitHub repo** — clone it locally to `E:\opencell-worktrees\karr-reference\external\WholeCell` (use `--depth 1`). Look for:
   - `out/` or `output/` folders with pre-run simulation `.mat` files
   - Documentation pointing to S3 buckets / Synapse / FigShare with simulation outputs
   - Any `single_cell_cycle.mat` or similar fixture
2. **Cell journal supplement** — the paper's Supplementary Data S2/S3 (often hosted on https://www.cell.com or linked from PubMed PMC). Look for trajectories as Excel/CSV.
3. **CovertLab successor data** — they later moved to E. coli, but the M. genitalium reference may be archived. Check https://covertlab.stanford.edu/publications/ and any linked Synapse / Zenodo dataset.

If the repo has them: great. If not: scrape from the supplement PDF or contact the corresponding-author URL listed in the paper (just document the URL; don't actually email).

### Step 2: Identify the reference trajectories we need

For a single ~9-hour cell cycle of wild-type *M. genitalium*:

| Quantity | Unit | What we use it for |
|---|---|---|
| Cell mass (total dry mass) | fg or kg | Pass criterion: doubles in ~9 hr |
| ATP concentration | molecules or mM | Pass criterion: ~steady-state with small oscillation |
| dNTP pools (dATP/dCTP/dGTP/dTTP) | molecules | Pass criterion: transient depletion at replication |
| Replication initiation time | seconds | Pass criterion: single event at ~6 hr (±10%) |
| RNA polymerase synthesis rate | nt/s or molecules/s | Pass criterion: matches Karr's reference |
| Protein synthesis rate | aa/s or molecules/s | Pass criterion: matches Karr's reference |
| Cell division time | seconds | Pass criterion: ~9 hr (32,400 s) |

If `.mat` files are present, use `scipy.io.loadmat` to read them. Be aware MATLAB struct arrays load as nested numpy object arrays — handle that.

### Step 3: Extract and normalize

Write `scripts/extract_karr_reference.py` that:
- Reads the raw artifact (`.mat` or `.csv` or whatever Step 1 finds)
- Extracts each quantity above as a `(time_s, value)` numpy array
- Saves to `data/reference/karr_2012_<quantity>.csv` with columns `time_s, value, unit`
- Saves a manifest `data/reference/karr_2012_manifest.json` with: source URL, source filename, extraction date, raw shape, normalized units, any caveats

Commit each new CSV individually so the diff is reviewable.

### Step 4: Sanity plot

Write `scripts/plot_karr_reference.py` that loads the CSVs and produces a multi-panel PNG at `data/reference/karr_2012_overview.png` showing:
- Cell mass vs time (panel 1)
- ATP vs time (panel 2)
- dNTPs vs time (panel 3)
- Vertical line at replication initiation
- Vertical line at division

Use matplotlib (already a dep). Don't be fancy.

Commit the PNG (it's a reference artifact, fine to commit).

### Step 5: Write STATUS_karr_reference.md

Include:
- Source(s) used and confidence (high/medium/low)
- Files created (paths, sizes)
- Pasted summary table: trajectory name, t=0 value, t=32400 value, peak value, sources verified
- Any quantities you could NOT find — flag as gaps
- Caveats: e.g. "Karr's units differ from ours by factor of X", "their tick is 1s, ours is 2s"
- Verdict: `reference-extracted-complete` | `partial-with-gaps` | `blocked-need-human`

## What you must NOT do

- Don't modify any code in `opencell/` package itself — this is reference data work
- Don't try to run our simulation — that's a separate task
- Don't email anyone. If a source requires emailing the authors, just document the URL in STATUS
- Don't fabricate data. If a trajectory isn't available, flag it as a gap in STATUS, don't make up values.

## Token budget

130k. Compact + STATUS before crossing.
