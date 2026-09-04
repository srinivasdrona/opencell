import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import l21_active_window_audit as aw

MANIFEST_PATH = Path("docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json")

# sanity: valid JSON
json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
print("JSON parses OK")

result = aw.verify_active_window_manifest_row(MANIFEST_PATH, "HostInteraction")
print(json.dumps({k: v for k, v in result.items() if k not in ("live_candidate",)}, indent=2, default=str))
