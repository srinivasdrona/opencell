import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import l21_active_window_audit as aw  # noqa: E402

manifest_path = REPO_ROOT / "docs" / "phase_f" / "l2_1" / "L21_ACTIVE_WINDOWS_MANIFEST.json"

for process in ("TranscriptionalRegulation", "Cytokinesis"):
    result = aw.verify_active_window_manifest_row(manifest_path, process, progress=True)
    print("=" * 20, process, "=" * 20)
    print("verification_status:", result["verification_status"])
    print("verified:", result["verified"])
    print("recorded_classification:", result["recorded_classification"])
    print("fresh_classification:", result["fresh_classification"])
    print("failure_reason:", result["failure_reason"])
