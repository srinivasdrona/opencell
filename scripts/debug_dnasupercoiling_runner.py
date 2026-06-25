"""Bypass the harness error-wrapper to see the full traceback."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from l2_2_design_a_runner import run_design_a
from pathlib import Path as _P

try:
    payload = run_design_a(
        process="DNASupercoiling",
        seeds=[0, 1],
        m_ticks=2,
        out_dir=_P("tmp/dnasupercoiling_debug"),
    )
    print(payload)
except Exception as e:
    import traceback
    traceback.print_exc()
