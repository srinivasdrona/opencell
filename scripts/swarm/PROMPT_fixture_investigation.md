# Fixture-Pipeline Investigation

## Role

You are the **fixture-pipeline investigator**. The Composition audit (`swarm/composition` branch) confirmed all 28 `<Process>_flat.mat` fixtures have `n_ticks=1`, `inputs=0`, `outputs=0` — they are single-snapshot, not replay-capable. This blocks any future replay-fidelity or t=0-parity audits across the cell.

This investigation is **NOT a rebuild**. It diagnoses the gap and recommends a path. Operator decides whether to rebuild after reading your output.

## Worktree & branch

- Worktree: `E:\opencell-worktrees\swarm-fixture-investigation` (already created)
- Branch: `swarm/fixture-investigation`
- WSL: `wsl -e bash -lc "cd /mnt/e/opencell-worktrees/swarm-fixture-investigation && source /mnt/e/opencell/.venv-wsl/bin/activate && <cmd>"`

## Budget

~60k context. No checkpointing needed.

## Questions to answer (in order)

### Q1 — What does our extraction pipeline produce, and how?
- Locate the script(s) that produced the `<Process>_flat.mat` fixtures. Likely under `opencell/karr_extracts/`, `scripts/`, or `tools/`. Search for `.mat` writers, `scipy.io.savemat` calls, or anything named `extract`, `flatten`, `karr_to`.
- Read the script. What is its input (Karr `.mat` from `CovertLab/WholeCell` simulation runs)? What is its output structure?
- Identify the step where time-series data is collapsed to a single tick. Cite `file:line`. Is this an intentional design choice (e.g., "we only need initial state") or a bug?

### Q2 — What does the Karr source `.mat` actually contain?
- Locate one Karr-source `.mat` we extracted from (if we have a copy locally), or document where they live (likely `CovertLab/WholeCell` simulation output dumps).
- Spot-check the structure: does the source contain `n_ticks > 1`, time-indexed `inputs`/`outputs`? Or is it also single-snapshot?
- If we don't have local Karr `.mat`s, can we get them? (Are they in a release artifact? Need to re-run their simulation?)
- Quote the actual numpy/scipy structure of one source fixture: `mat['<key>'].shape`, `dtype`, and any obvious time axis.

### Q3 — What does our replay harness consume?
- Locate the replay harness (`opencell/validation/replay.py` or similar — the Composition audit cites `replay.py:232,233`).
- What shape does it expect from a fixture? `(n_ticks, n_substrates)` arrays? Per-tick dicts? Cite `file:line`.
- Confirm: the harness CAN'T do anything with `n_ticks=1`, but if we built a multi-tick fixture, would it work as-is, or would the harness also need changes?

### Q4 — Recommendation

Produce a recommendation document (`fixture_pipeline_recommendation.md`, ~2-3 KB):

- **What's broken**: the precise gap (extraction script collapses time, source data missing replay channels, replay harness misaligned with fixture format, or some combo).
- **Confidence level** that we know the right rebuild pattern: HIGH if the script clearly drops time and a 50-LOC fix would restore I/O channels; MEDIUM if the source data needs re-extraction from Karr simulation runs; LOW if we don't yet know where the time-series originally lived.
- **Estimated rebuild scope**:
  - (A) Small (~50 LOC, 1-2 days): extraction script-only fix
  - (B) Medium (~200 LOC, 1 week): re-run Karr simulations + new extraction + harness update
  - (C) Large (~500+ LOC, weeks): rebuild fixture format end-to-end, including new format spec
- **Recommended path**: which option, with justification
- **Does this block Track-A?** Probably no for A1/A2/A3/A4/A5 (the immediate fixes), but enumerate explicitly.

## Output artifacts (2 files)

All under `opencell/validation/swarm/fixture_investigation/`:

1. **`fixture_pipeline_diagnosis.md`** — Q1, Q2, Q3 with `file:line` citations + actual structure dumps from `scipy.io.loadmat`.
2. **`fixture_pipeline_recommendation.md`** — Q4 recommendation.

## Methodology

- Cite `file:line` for every claim.
- Actually run `scipy.io.loadmat()` in WSL python on at least 2 fixtures and quote the output structure. Don't speculate.
- If you can't find Karr source `.mat`s locally, document that and don't guess.

## Commit discipline

One commit. Trailer:
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

## Halt rules

- If you can't locate any extraction script after thorough search — STATUS.md, exit cleanly.
- If `scipy.io` cannot load the fixtures — STATUS.md, exit (this would itself be a major finding worth flagging).
