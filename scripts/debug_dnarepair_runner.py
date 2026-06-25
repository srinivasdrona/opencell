"""Debug DNARepair runner error."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))
from l2_2_design_a_runner import run_design_a
try:
    payload = run_design_a(
        process="DNARepair",
        seeds=list(range(50)),
        m_ticks=10,
        out_dir=Path("tmp/dnarepair_debug"),
    )
    print("PAYLOAD:", payload.get("result", {}).get("channels", {}))
except Exception as e:
    import traceback
    traceback.print_exc()
