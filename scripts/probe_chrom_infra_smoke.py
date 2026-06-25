"""Quick import + smoke test for chromosome infrastructure."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from _l2_2_design_a_runner_helpers import (
    _run_dna_supercoiling_tick,
    _dna_supercoiling_process,
    load_chromosome_oracle_for_process,
    chromosome_projection_matrix,
    _chromosome_projection_component,
    _overlay_chromosome_into_state,
    _apply_chromosome_update,
)
print("Imports OK")

# Load oracle for 2 seeds × 10 ticks
oracle = load_chromosome_oracle_for_process("DNASupercoiling", [0, 1], 10)
print(f"Oracle: n_seeds={oracle['n_seeds']}, m_ticks={oracle['m_ticks']}")
print(f"  before_stores[0][0] fields: {sorted(oracle['before_stores'][0][0]._fields.keys())[:5]}...")

# Compute projection
proj = chromosome_projection_matrix(
    before_stores=oracle["before_stores"],
    after_stores=oracle["after_stores"],
    projection_spec=("linkingNumbers.delta_value_sum", "linkingNumbers.delta_nnz"),
)
print(f"Projection shape: {proj.shape}")
print(f"Projection seed 0 ticks 0-4: {proj[0, :5, :]}")
