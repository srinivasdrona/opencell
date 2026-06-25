"""Print full RI catalog entry to find complexs<->boundEnzymes mapping."""
import yaml
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
with open(REPO / "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml") as f:
    cat = yaml.safe_load(f)

for p in cat["processes"]:
    if p.get("name") == "ReplicationInitiation":
        for k in sorted(p.keys()):
            print(f"  {k}: {p[k]}")
        break
