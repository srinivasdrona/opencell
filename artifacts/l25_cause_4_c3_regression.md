# C3 Regression Record ? l25-cause-4

Date: 2026-06-05

Commands and results:

1. `bin\\oc-pytest.cmd tests/vivarium/test_l2_5_ppi_ppii_v2.py tests/vivarium/test_karr_protein_processing_i_l2_replay.py tests/vivarium/test_karr_protein_processing_ii_l2_replay.py tests/unit/test_karr_protein_processing_i_strict_zero.py tests/unit/test_karr_protein_processing_ii_strict_zero.py -q --tb=short`
- Result: `6 passed in 11.89s`

2. `bin\\oc-pytest.cmd tests/vivarium/ -k "l2_2_v2 or l2_2_replay" -q --tb=short`
- Result: `402 deselected / 0 selected` (no additional L2.2-replay tests matched this selector in this worktree)
