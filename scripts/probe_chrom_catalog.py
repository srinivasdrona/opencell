"""Inspect catalog entries for the 6 chromosome-port processes."""
import yaml
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
with open(REPO / "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml") as f:
    cat = yaml.safe_load(f)

targets = ["Replication", "ReplicationInitiation", "DNASupercoiling", "DNARepair", "DNADamage", "FtsZPolymerization"]
print(f"Catalog schema_version: {cat.get('schema_version')}")
print(f"Top-level keys: {list(cat.keys())}")
print()

# Try multiple structures
processes = cat.get("processes", {}) or cat.get("processes_by_name", {})
print(f"processes type: {type(processes).__name__}")
if isinstance(processes, list):
    by_name = {p.get("name", "?"): p for p in processes if isinstance(p, dict)}
elif isinstance(processes, dict):
    by_name = processes
else:
    by_name = {}

for name in targets:
    e = by_name.get(name, {})
    print(f"=== {name} ===")
    if not e:
        print(f"  NOT FOUND in catalog (available: {sorted(by_name.keys())[:10]}...)")
        continue
    for k in sorted(e.keys()):
        v = e[k]
        if isinstance(v, (dict, list)):
            v = str(v)[:200]
        print(f"  {k}: {v}")
    print()
