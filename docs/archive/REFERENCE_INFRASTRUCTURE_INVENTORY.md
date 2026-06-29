# Karr 2012 reference infrastructure inventory (2026-05-24)

Discovered during ensemble-launch search. This consolidates EXISTING Karr-reference infrastructure on local disk that any grading / comparison Codex should consult BEFORE building anything new.

## Existing pass-criteria infrastructure (do NOT reinvent)

### 28-KP phenotype scorecard
- **`data/karr_fixtures/karr_phenotype_targets.json`** — 28 phenotype targets with tolerances. Categories: `fba_prediction`, `chassis_wiring`, etc. Schema version `karr_phenotype_targets__v1`. Each has `target`, `tol_rel_min`, `tol_rel_max`, `unit`, `source`, `note`. Some entries are `expected_status: "fail"` (e.g. p4 TX_GLCPTS structurally underwater).
- **`opencell/validation/karr_reference_values.py`** — `KarrReferenceValue` dataclass + `KARR_REFERENCE_VALUES: dict[str, KarrReferenceValue]` populated with values for KP01-KP28, each with `citation`, `source_path`, `sourced_at`, `sourced_by`. The canonical reference table.
- **`tests/phaseE/test_karr_phenotypes.py`** — phenotype tests likely already wired to this data.

The PASS_CRITERIA_32400t.md I drafted (18 criteria) was reinventing this. **Use the 28-KP scorecard as the authoritative pass criteria.** If anything in PASS_CRITERIA_32400t.md is genuinely new (e.g., conservation-drift criteria specific to our chassis), append those as KP29+; do not duplicate.

### Existing comparison tooling
- **`opencell/validation/trajectory_compare.py`** — trajectory comparison module
- **`opencell/validation/karr_trajectory.py`** — Karr trajectory loader/normalizer
- **`tests/validation/test_trajectory_compare_full.py`** — likely has working examples

## Reference data files (per-tick, per-process)

### Most promising: `data/karr_fixtures/per_process/*_flat.mat` (44 files, ~14 MB total)
These look like the **real per-tick flat dumps from Karr's WCM**, organized by process. Sizes suggest meaningful time-series content:

| File | Size | Likely content |
|---|---|---|
| `CellMass_flat.mat` | 1.0 MB | per-tick cell mass time series |
| `ProteinDecay_flat.mat` | 0.70 MB | protein decay events/rates |
| `Metabolism_flat.mat` | 0.62 MB | metabolism state per tick |
| `ReplicationInitiation_flat.mat` | 0.57 MB | replication initiation events |
| `Translation_flat.mat` | 0.55 MB | translation activity |
| `Transcription_flat.mat` | 0.53 MB | transcription activity |
| `RNADecay_flat.mat` | 0.50 MB | RNA decay |
| 30+ smaller files | 0.0-0.4 MB each | per-process traces |

These are likely what we should have been extracting all along. The `cell_cycle_trajectory.mat` file (100 MB) appears to be a different artifact — possibly state snapshots only, not per-tick time series, despite its name.

### Other Karr files (already partially ingested)
- `data/m1_sources/karr_native/cell_cycle_trajectory.mat` (100 MB) — extracted but yields static trajectories; aggregation may have been wrong, OR file is mislabeled. Triage Codex investigating.
- `data/m1_sources/karr_flat/metabolism_dynamics.mat` (31 KB) — metabolism dynamics, not yet extracted.
- `data/m1_sources/karr_native/per_process_traces/*_100ticks.mat` (28 files) — 100-tick per-process traces (bit-identical validation, NOT cell-cycle benchmark scale).
- `data/m1_sources/karr_native/fitted_constants.mat` — Karr's fitConstants() output.
- `data/m1_sources/karr_native/initial_states/*_init.mat` (23 files) — initial state snapshots.
- `data/karr_archive/karr_archive_strings.json` + `karr_archive_manifest.json` + `karr_archive.npz` — ID ↔ name lookup tables (already used by earlier extraction).

### Already-extracted aggregated fixtures (no .mat work needed for these)
- `data/karr_fixtures/karr_native_m1.{json,npz}` — m1 metabolism summary (used by KP01-KP04)
- `data/karr_fixtures/karr_native_m1_dynamics.{json,npz}` — dynamics summary
- `data/karr_fixtures/karr_native_m1_compartmented.{json,npz}` — compartmented m1
- `data/karr_fixtures/karr_native_m2.{json,npz}` + `_v2.{json,npz}` — m2 transcription/RNA reference (KP05 etc.)
- `data/karr_fixtures/karr_native_m3.{json,npz}` + `_v2.{json,npz}` — m3 protein reference (KP06 etc.)
- `data/karr_fixtures/karr_native_m3_vocab.json` — m3 vocab
- `data/karr_fixtures/karr_phenotype_targets.json` — KP01-KP28 targets
- `data/karr_fixtures/karr_protein_complexes.json` — protein complex reference
- `data/karr_fixtures/karr_parameters_unit_map.yaml` — units

### Karr's published supplements
- `data/m1_sources/karr2012_supplement_01.xls` — but `karr_reference_values.py` flagged these as "HTML anti-bot placeholders in this worktree, not usable tables". Check whether re-downloadable.
- `_02.xls` + `_03.xlsx` — same caveat.

## Previous 32,400-tick runs on disk (pre-cascade-fix)

- `data/phase_e/v6_trajectory_32400s.pkl` (1 MB)
- `data/phase_e/v6_trajectory_32400s_post_alloc.pkl` (1 MB)

These pre-date the cascade-fix. They could be:
- A baseline to delta-compare against the fresh ensemble runs (to quantify what the cascade fix changed).
- Useful as a sanity check that our infrastructure can even produce a 32,400-tick pickle.

Don't use them as ground truth; they're our own output.

## Recommended path for the grading Codex (when ensemble runs complete)

1. Load `karr_phenotype_targets.json` and `KARR_REFERENCE_VALUES` from `opencell/validation/karr_reference_values.py`. These ARE our pass criteria.
2. For each of the 4 ensemble runs (seeds 42/43/44/45), compute every KP using the same code paths the existing tests use (`opencell/validation/trajectory_compare.py`).
3. Report per-seed scores and ensemble statistics (mean, std).
4. For any KP whose Karr reference is currently "best-effort" (e.g., based on a single trajectory rather than ensemble), flag the asymmetric confidence.
5. If `per_process/*_flat.mat` extraction unlocks NEW per-tick comparisons not in KP01-KP28, propose them as KP29+ rather than redefining the existing ones.

## What I (Copilot) am NOT going to do

- Load any `.mat` files (Codex's job).
- Build a comparison harness (use the existing `trajectory_compare.py`).
- Re-extract data that's already in `data/karr_fixtures/`.

## Provenance

This inventory was assembled by Copilot on 2026-05-24 ~05:23 IST via filesystem glob/grep while the ensemble (4 seeds) and karr-triage Codex sessions were running in parallel.
