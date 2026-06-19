# Task: PE-2 scorecard bridge (CSV→pkl) + canary pkl-emit + git rev-parse fix

You are extending the OpenCell Phase E.2 phenotype scorecard so we can score
TODAY's post-strip canary trajectory against the 28 Karr phenotypes (KP01-28)
without re-running the 20-minute canary.

## Repo & branch

- cwd: `/mnt/e/opencell` (you should already be here)
- branch: `main` (just merged track-p2/karr-divergence-audit; HEAD = `172183b`)
- create a new branch for this work: `phase-e/scorecard-bridge`

## ⚠️ Python interpreter — MANDATORY

You are running on Windows. Windows `python.exe` and `py.exe` do NOT have this
project's editable install and WILL fail with `ModuleNotFoundError`. You MUST
run every Python command through WSL with the project venv:

  CORRECT:   `wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && pytest ..."`
  CORRECT:   `wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && python -m scripts.foo ..."`
  WRONG:     `pytest ...` (Windows PATH resolves to wrong interpreter)
  WRONG:     `python -m pytest ...`
  WRONG:     `py -3.12 -m pytest ...`

For THIS task specifically:
  - venv activate: `source /mnt/e/opencell/.venv-wsl/bin/activate`
  - repo root (WSL): `/mnt/e/opencell`

If `python` or `pytest` from Windows PATH "works" but tests fail with import
errors, you are using the wrong interpreter. STOP and switch to the WSL venv.

## Token budget contract

Hard ceiling: 200,000 tokens. Self-managed handoff: 150,000 (75%). If you
approach 150k, commit whatever is green and write STATUS with a checkpoint
marker so the orchestrator can resume cleanly. Do NOT push past 150k.

## Commit-as-you-go

Commit each logical chunk to git the moment it is green, BEFORE moving to
the next chunk. The chunks below are designed to be commit boundaries.

## Context

### The scorecard
- `opencell/validation/phenotype_scorecard.py` — Phase E.2 scorecard engine.
- `opencell/validation/phenotype_registry.py` — 28 KP definitions in `_SPECS`.
- `opencell/validation/phenotype_extractors.py` — 28 extractor functions.
- Entry point: `phenotype_scorecard.run_from_fixture(fixture_path, out_path)`.
- Default fixture: `data/phase_e/v6_trajectory_32400s.pkl` (May 23, **pre-strip**).
- Default output: `docs/phase_e/E2_scorecard.md`.

### Required pkl schema (from phenotype_scorecard.py top, ~lines 19-36)

Top-level dict:
```python
{
  "snapshots": [snap1, snap2, ...],   # list of per-tick or per-bucket snapshots
  "wall_time_s": float,
  "ticks_completed": int,
  "division_detected": bool,
}
```

Per snapshot dict:
```python
{
  "tick": int,
  "time_s": float,
  "state": {
    "cell_dry_mass_g": float,
    "replication_state_code": int,
    "fork_position_norm": float,
    "mrna_total_count_estimate": int,
    "protein_total_count_estimate": int,
    "atp_pool": float,
    "gtp_pool": float,
    "dntp_pool_total": float,
    "division_event_timestamp_s": Optional[float],
  }
}
```

**IMPORTANT**: read the actual loader (`load_v6_trajectory_fixture` in
`phenotype_scorecard.py`) before assuming the schema. It is the source of truth.

### Today's canary CSV outputs (post-strip, parity_mode=True)

Location: `/mnt/e/opencell-worktrees/p2-karr-divergence-audit/artifacts/canary_post_strip_20260526_153956/`

Files:
- `key_substrates.csv` (~7.8 MB) — per-tick substrate counts, including ATP, GTP, dNTP species
- `substrates_full.csv` (~64 MB) — all substrates per tick
- `conservation.csv` (~75 MB) — conservation diagnostics
- `replication_events.csv` (~982 KB) — replication state transitions
- `division_event.json` — `{"division_occurred": false, ...}`
- `process_traces/` — per-process trace CSVs (TX, TL, mass, etc.)

You will need to inspect column headers first (use `head -1` on each CSV) to
map them to the schema fields. The exact column names are:
- Use `wsl bash -lc "head -1 <csv>"` to discover them — do NOT guess.

### The git rev-parse bug

`scripts/run_chassis_v6_32400t.py` line ~688 crashes in the post-run manifest writer:

```python
subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
```

`ROOT = Path(__file__).resolve().parents[1]` yields a Windows-style path
inside WSL, causing `git` to fail with `fatal: not a git repository`.

Fix: either drop the `cwd=` argument (the canary is always launched from the
repo root) or wrap with try/except and write a placeholder commit SHA on
failure. The bug means all scientific artifacts write fine but the run dies
in the manifest. Pick the cleanest fix.

## Work plan (4 chunks)

### Chunk 1 — Bridge script: CSVs → pkl

Create `scripts/canary_csvs_to_e2_pkl.py`. It should:

1. Take two CLI args: input CSV dir, output pkl path.
2. Inspect column headers from `key_substrates.csv`, `replication_events.csv`,
   `conservation.csv`, and the relevant `process_traces/*.csv` files.
3. Build per-tick snapshots in the exact schema the scorecard expects.
   - You may need to **downsample** if the CSVs are per-tick (32,400 rows) —
     the existing `v6_trajectory_32400s.pkl` has 325 snapshots (~100-tick stride).
     Match that cadence so KP extractors that index snapshots work identically.
   - For substrate pools (ATP, GTP, dNTPs): sum the appropriate Karr species IDs.
     ATP = `ATP[c]` or whichever column the CSV uses. GTP similarly. dNTP_total
     = sum of dATP+dCTP+dGTP+dTTP (compartmented as needed).
   - For mass: look in `conservation.csv` or `process_traces/cell_mass.csv` if present.
   - For mRNA/protein counts: look in process traces (TX/TL outputs).
   - For replication state: parse `replication_events.csv` for state transitions,
     hold-last between events.
4. Top-level fields: `wall_time_s` from the canary log if available (else 0),
   `ticks_completed` from the max tick in the CSVs, `division_detected` from
   `division_event.json`.
5. Print a one-line summary on stdout: `Wrote {path}: {N} snapshots, ticks_completed={T}, division={B}`.

**Self-test**: also load the existing `data/phase_e/v6_trajectory_32400s.pkl`
and print its schema (top-level keys, sample snapshot keys, sample state keys).
Make sure your output matches that schema exactly.

Commit: `phase-e: scripts/canary_csvs_to_e2_pkl.py CSV→pkl bridge for E.2 scorecard`

### Chunk 2 — Fix git rev-parse bug in canary script

Edit `scripts/run_chassis_v6_32400t.py` line ~688:
- Smallest fix: drop the `cwd=ROOT` argument (let git use current working dir,
  which is the WSL path from launch). Verify the rest of the manifest code
  still works.
- If unclear, wrap the `git rev-parse` in try/except and write `"unknown"` on
  failure — better to lose one diagnostic field than to crash the manifest writer.

Commit: `fix(canary): drop cwd=ROOT in git rev-parse — Windows path fails inside WSL`

### Chunk 3 — Add pkl-emit to canary script (future-proof)

In `scripts/run_chassis_v6_32400t.py`, after the existing CSV writes, also
write a pkl in the E.2 scorecard schema. Re-use the snapshot builder from
chunk 1 (factor it into a helper if needed; do NOT duplicate logic).

Output path: `<out_dir>/trajectory.pkl` (alongside the CSVs).

Commit: `feat(canary): emit E.2-schema pkl alongside CSVs for future scorecard runs`

### Chunk 4 — Run the bridge + scorecard against today's canary

1. Run the bridge:
   ```
   wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && python scripts/canary_csvs_to_e2_pkl.py /mnt/e/opencell-worktrees/p2-karr-divergence-audit/artifacts/canary_post_strip_20260526_153956 data/phase_e/v6_trajectory_32400s_post_strip.pkl"
   ```

2. Run the E.2 scorecard against the new pkl:
   ```
   wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && python -c 'from opencell.validation.phenotype_scorecard import run_from_fixture; from pathlib import Path; run_from_fixture(Path(\"data/phase_e/v6_trajectory_32400s_post_strip.pkl\"), Path(\"docs/phase_e/E2_scorecard_post_strip.md\"))'"
   ```

3. Commit both files:
   - `data/phase_e/v6_trajectory_32400s_post_strip.pkl`
   - `docs/phase_e/E2_scorecard_post_strip.md`

Commit: `phase-e: first post-strip scorecard — N/28 PASS, M FAIL, K BLOCKED` (fill in the actual numbers)

### Final step — push branch

```
wsl bash -lc "cd /mnt/e/opencell && git push -u origin phase-e/scorecard-bridge"
```

## STATUS report (write to STATUS_pe2_bridge.md as you go)

Write the full report into `/mnt/e/opencell/STATUS_pe2_bridge.md` using your
file-edit tools as each chunk completes. Final assistant message should be
ONE LINE pointing at this file.

Required sections:
1. **Chunks completed** — for each of the 4 chunks, the commit SHA and 1-line outcome
2. **Schema confirmation** — paste the schema from the existing pkl and from your new pkl, side-by-side, to prove they match
3. **Post-strip scorecard summary** — PASS/FAIL/BLOCKED counts, plus the per-KP table from `docs/phase_e/E2_scorecard_post_strip.md`
4. **Delta vs pre-strip scorecard** — which KPs moved (e.g. KP01: FAIL→PASS), keyed on KP id
5. **Blockers / followups** — anything you couldn't complete, what you tried, what the orchestrator should do next

## Out of scope (do NOT do these)

- Do NOT fix any FAILing extractors. We want the honest current state first.
- Do NOT implement any of the 8 stub extractors (KP15, KP21, KP25-28).
- Do NOT modify `phenotype_scorecard.py`, `phenotype_registry.py`, or
  `phenotype_extractors.py` — those are working as designed.
- Do NOT re-run the 32,400-tick canary itself. Use the existing CSV outputs.

## Sandbox

You are running with `--dangerously-bypass-approvals-and-sandbox`. Network
access is fine but not needed for this task. Everything you need is on disk.
