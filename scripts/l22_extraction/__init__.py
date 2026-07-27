"""L2.2 full multi-seed Karr oracle extraction tooling.

This package holds the minimal launcher/validator/manifester infrastructure
for the L2.2 Design-A full-extraction task (see
``docs/phase_f/l2_2_design_a/L22_FULL_EXTRACTION_SCOPE.md``). It deliberately
reuses the existing extractor (``scripts/matlab/extract_per_process_traces_v2.m``)
and loader (``tests/vivarium/_l2_2_design_a_runner_helpers.py``) rather than
re-implementing MATLAB extraction or oracle-loading logic.
"""
