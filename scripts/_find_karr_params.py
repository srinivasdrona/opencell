"""Find Karr's actual parameter source (knowledge base, XLS, or
hardcoded constants in .m files). The .mat fixtures are STATE
snapshots; M-phase ingestion needs PARAMETERS."""
import json
import urllib.request

req = urllib.request.Request(
    "https://api.github.com/repos/CovertLab/WholeCell/git/trees/master?recursive=1",
    headers={"User-Agent": "opencell"},
)
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.load(r)

# Look for parameter sources
print("=== knowledge base / parameter files ===")
candidates = [
    t for t in data["tree"]
    if any(s in t["path"].lower() for s in ["knowledge", "parameter", "kineticconstant"])
    or t["path"].endswith((".xls", ".xlsx", ".xml", ".csv", ".tsv"))
]
for f in sorted(candidates, key=lambda x: x.get("size", 0))[:30]:
    sz = f.get("size", 0)
    print(f"  {sz:>10}  {f['path']}")

print("\n=== top-level data dirs ===")
top_dirs = sorted({t["path"].split("/")[0] for t in data["tree"] if "/" in t["path"]})
for d in top_dirs:
    n = sum(1 for t in data["tree"] if t["path"].startswith(d + "/"))
    sz = sum(t.get("size", 0) for t in data["tree"] if t["path"].startswith(d + "/"))
    print(f"  {sz/1024/1024:>8.1f} MB  {n:>5} files  {d}")
