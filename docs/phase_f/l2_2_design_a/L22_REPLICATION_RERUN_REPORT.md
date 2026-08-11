# L22 Replication Rerun Report

## Scope

This lane reran the current-tree L2.2 Design-A gate for `Replication` only.
No code, metric, threshold, catalog, or shared evidence-index files were
edited.

Catalog entry (authoritative spec):

```yaml
name: Replication
bucket: ALGORITHMIC_SHALLOW
M_ticks: 100
N_seeds: 50
primary_channel: chromosome
primary_projection: [polymerizedRegions.delta_value_sum_strand_1, polymerizedRegions.delta_value_sum_strand_2, polymerizedRegions.delta_value_sum_strand_3, polymerizedRegions.delta_value_sum_strand_4, polymerizedRegions.delta_nnz]
karr_artifact: per_process_traces_v2
```

## Oracle Reuse

This worktree did not initially contain the Replication `per_process_traces_v2`
cohort. The existing cohort was reused, not regenerated:

- Source inventory path: `E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\per_process_traces_v2*`
- Measured inventory: `50` files, `50` unique SHA256 hashes
- Targeted copy into this worktree: only `Replication_100ticks.mat` for seed
  `0..49`

Mechanical raw-input verification then passed:

```text
bin\oc-py scripts/l22_extraction/report.py final --seeds 1-49 \
  --processes Replication --skip-specialized \
  --out artifacts/l22_replication/final_report_replication.json
```

Result: `PASS`.

## Canonical Rerun

Executed the canonical launcher, forced for the current tree:

```text
bin\oc-py scripts/l22_evidence/sweep.py run --processes Replication \
  --max-workers 1 --force \
  --evidence-root artifacts/l2_2_gates \
  --log-dir artifacts/l2_2_gates/_sweep_logs \
  --report-out artifacts/l22_replication/sweep_report_replication.json
```

Measured runtime from `sweep_report_replication.json`: `3910.516s`
(`65m10.516s`), status `RAN_EXIT_0`.

`artifacts/l2_2_gates/Replication/latest/sweep_provenance.json` confirms:

- `completion_status: COMPLETE`
- `inputs_verified: true`
- `git_sha: 0f2e0397f5adbb2b3409b901a1368ebf5a3acbc6`

## Measured Outcome

Process verdict: `PASS`

Primary channel:

- `chromosome`: `PASS`
- Aggregation: `per_component_scaled`
- Threshold: `1.0`
- Scaled component distances:
  - `polymerizedRegions.delta_nnz = 0.002800000000000036`
  - `polymerizedRegions.delta_value_sum_strand_1 = 0.0`
  - `polymerizedRegions.delta_value_sum_strand_2 = 0.022816`
  - `polymerizedRegions.delta_value_sum_strand_3 = 0.018615999999999994`
  - `polymerizedRegions.delta_value_sum_strand_4 = 0.040251000000000016`

Secondary channels:

- `substrates`: `SEED_NOISE`, `w1_oc_vs_karr = 13.0535625`, `q95_null = 169082.0404275`, `threshold = 338164.080855`
- `boundEnzymes`: `SEED_NOISE`, `w1_oc_vs_karr = 0.1284923076923076`, `q95_null = 0.1519084615384614`, `threshold = 1.0`

Runner log tail:

```text
Replication PASS substrates=SEED_NOISE@13.053562 boundEnzymes=SEED_NOISE@0.128492 chromosome=PASS@0.000000
```

## Bundling

Only Replication compact authority files were mirrored into the tracked bundle:

- `docs/phase_f/l2_2_design_a/evidence_bundle/Replication/latest/result.json`
- `docs/phase_f/l2_2_design_a/evidence_bundle/Replication/latest/input_manifest.json`
- `docs/phase_f/l2_2_design_a/evidence_bundle/Replication/latest/provenance.json`
- `docs/phase_f/l2_2_design_a/evidence_bundle/Replication/latest/thresholds.json`
- `docs/phase_f/l2_2_design_a/evidence_bundle/Replication/latest/null_calibration.json`
- `docs/phase_f/l2_2_design_a/evidence_bundle/Replication/latest/SUMMARY.json`
- `docs/phase_f/l2_2_design_a/evidence_bundle/Replication/latest/analytical_check.json`
- `docs/phase_f/l2_2_design_a/evidence_bundle/Replication/latest/sweep_provenance.json`

Shared files left untouched by this lane:

- `docs/phase_f/l2_2_design_a/evidence_index.json`
- `docs/phase_f/l2_2_design_a/sweep_report.json`
- `docs/phase_f/l2_2_design_a/sweep_status.json`
