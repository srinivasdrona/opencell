# L2.2 Harness v1 Baseline (Frozen)

- Scope: `tests/vivarium/test_l2_2_translation_plus_rna_processing.py`
- Run date: 2026-06-01
- Command: `pytest tests/vivarium/test_l2_2_translation_plus_rna_processing.py -q`

First mismatch tuple (v1):
- `tick=5`
- `process=RNAProcessing`
- `observable=substrates`
- `index=5`
- `oc_val=0.0`
- `karr_val=1679927.0`
- `diff=-1679927.0`

Cause string emitted by v1:
- `"upstream pollution from earlier composed updates"`

Why v2 supersedes:
- v1 emits a generic upstream label on positional index compare; v2 keeps the RED but classifies this first-pair case as explicit WID-space mismatch (`H2O` vs `GLN` at index 5), with structured diagnostics and deterministic union-master evidence.
