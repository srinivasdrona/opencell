"""List the Karr +state .m source files by size, find the ones
that match the .mat fixtures we already downloaded."""

import json
import urllib.request

req = urllib.request.Request(
    "https://api.github.com/repos/CovertLab/WholeCell/git/trees/master?recursive=1",
    headers={"User-Agent": "opencell"},
)
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.load(r)

state_m = [
    t
    for t in data["tree"]
    if "+state/" in t["path"] and t["path"].endswith(".m") and "test" not in t["path"]
]
print(f"+state .m files (non-test): {len(state_m)}")
print()
for f in sorted(state_m, key=lambda x: x.get("size", 0)):
    sz = f.get("size", 0)
    path = f["path"]
    print(f"  {sz:>7}  {path}")
