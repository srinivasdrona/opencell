# Grade ensemble OpenCell runs against Karr 2012 reference (4 seeds)

## Goal

Parse the outputs of **all 4 ensemble 32,400-tick OpenCell runs** (seeds 42/43/44/45) AND the Karr 2012 reference data, evaluate against the existing **28-KP phenotype scorecard** (NOT a re-invented criteria list), produce per-seed scorecards plus an ensemble-level summary, and write an honest verdict.

Be brutal. Don't talk results up. If we fail, we fail.

## Hard rules

- 130k token ceiling.
- **DO NOT pause to ask the user questions.**
- Pick a fresh worktree off `main` (suggested: `agent/grade-32400t`).
- Use `E:\opencell\.venv-opencell\Scripts\python.exe`.

## FIRST: read the inventory

Before doing anything else, read `E:\opencell\REFERENCE_INFRASTRUCTURE_INVENTORY.md`. It tells you:
- The 28-KP scorecard already exists at `data/karr_fixtures/karr_phenotype_targets.json`.
- The reference values are populated in `opencell/validation/karr_reference_values.py` (`KARR_REFERENCE_VALUES` dict).
- Comparison tooling already exists at `opencell/validation/trajectory_compare.py` and `karr_trajectory.py`.
- Phase E phenotype tests at `tests/phaseE/test_karr_phenotypes.py` are likely already wired.

**Use the existing infrastructure. Do NOT re-invent pass criteria.**

## Inputs

1. **Our 4 ensemble runs**:
   - `E:\opencell-worktrees\phase-2-fix\artifacts\run_32400t_seed42\`
   - `E:\opencell-worktrees\run-seed-43\artifacts\run_32400t_seed43\`
   - `E:\opencell-worktrees\run-seed-44\artifacts\run_32400t_seed44\`
   - `E:\opencell-worktrees\run-seed-45\artifacts\run_32400t_seed45\`
   Each contains `key_substrates.csv`, `replication_events.csv`, `division_event.json`, `conservation.csv`, `manifest.json`.

2. **Karr 28-KP scorecard**:
   - `data/karr_fixtures/karr_phenotype_targets.json`
   - `opencell/validation/karr_reference_values.py` (`KARR_REFERENCE_VALUES`)

3. **Per-tick reference (if karr-triage Codex unlocked it)**:
   - `data/reference/karr_2012_*.csv` (from `agent/karr-reference` — partial, with caveats)
   - Any newly-extracted CSVs from `data/karr_fixtures/per_process/*_flat.mat` if karr-triage delivered

4. **Existing PASS_CRITERIA draft** (use only for NEW criteria not in KP01-KP28):
   - `E:\opencell\PASS_CRITERIA_32400t.md` — 18 criteria. Cross-reference; treat the conservation-tier as candidates for KP29+, not as a replacement for KP01-KP28.

## What to do

### Step 1: Per-seed scoring against the 28 KPs

For each seed:
1. Load `manifest.json` and key trajectory CSVs.
2. Run the existing scoring code (the one used by Phase E.2 / `tests/phaseE/test_karr_phenotypes.py`) against the trajectory.
3. Compute each of KP01-KP28: our value, target, tol band, score (PASS / PARTIAL / FAIL / EXPECTED_FAIL / UNGRADED).
4. Write `artifacts/grading_ensemble/seed<N>/scorecard.json`.

### Step 2: Ensemble aggregation

For each KP across the 4 seeds:
- mean, std, min, max
- "ensemble verdict" = PASS if ≥3/4 seeds PASS; PARTIAL if mean is in PARTIAL band; FAIL otherwise.

Write `artifacts/grading_ensemble/ensemble_scorecard.json` and `ensemble_scorecard.md`.

### Step 3: Conservation tier (the cascade-fix sanity check)

In addition to the 28 KPs:
- Max `|unattributed_delta|` across each run's full trajectory. Target: < 1e-6 (we got 1e-8 in canaries).
- Number of substrates with cum_store_delta < -100 outside the drainer whitelist. Target: 0.

These are our cascade-fix regression checks at full scale. Call them KP29 + KP30 in the scorecard.

### Step 4: Comparison plots (per quantity, all 4 seeds + Karr)

For each KP that has a per-tick trajectory (mass, ATP, dNTPs, AAs, RNA, protein), generate a multi-line plot showing all 4 seeds + Karr reference on the same axes. Save to `artifacts/grading_ensemble/plots/<kp>_compare.png`.

### Step 5: Verdict + STATUS

`STATUS_grading.md`:
- One-paragraph overall verdict.
- Ensemble scorecard table.
- KPs where we PASSed: list.
- KPs where we PARTIAL'd: list with reason.
- KPs where we FAILed: list with hypothesized cause.
- KPs where reference is missing (UNGRADED): list, with note from REFERENCE_INFRASTRUCTURE_INVENTORY.md about gaps.
- Variance across seeds: which KPs are tight (low std) vs noisy (high std). A noisy KP means seed-sensitivity, which is worth flagging.
- Comparison to prior 32,400-tick run on disk (`data/phase_e/v6_trajectory_32400s.pkl`): did the cascade fix move things in the expected direction?

## What honest grading looks like

- Don't claim PASS based on order-of-magnitude agreement when the KP specifies ±20%.
- If 3 seeds PASS one KP and 1 FAILs catastrophically, that's ensemble-FAIL, not "3/4 PASS so we're good."
- If Karr reference is missing for a KP, mark UNGRADED. Don't fill it in with a guess.
- If conservation drift exceeds 1e-6 at full scale, the cascade fix didn't hold up. Say so.

## Token budget

130k ceiling.

