"""Tooling for the DNASupercoiling N=100-seed power diagnostic (l22-dnas-power).

This package is diagnostic-only tooling. It does not modify:
  - DNASupercoiling biology (`opencell/vivarium/karr_dna_supercoiling.py`)
  - the Design-A metric/threshold/null-calibration code
    (`tests/vivarium/l2_2_design_a_runner.py`,
    `tests/vivarium/_l2_2_design_a_projections.py`)
  - `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` (N_seeds/M_ticks stay 50/100)
  - the canonical evidence bundle/index/sentinel for DNASupercoiling
  - the already-accepted seeds 0-49 raw Karr traces (copied read-only)

See `docs/phase_f/l2_2_design_a/L22_DNAS_POWER_PREREG.md` for the
pre-registered diagnostic spec and decision rule this tooling implements.
"""
