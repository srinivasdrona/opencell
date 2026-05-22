"""Find Karr's serializer / fixture-builder source."""

import json
import urllib.request

req = urllib.request.Request(
    "https://api.github.com/repos/CovertLab/WholeCell/git/trees/master?recursive=1",
    headers={"User-Agent": "opencell"},
)
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.load(r)

candidates = [
    t
    for t in data["tree"]
    if t["path"].endswith(".m")
    and ("Sparse" in t["path"] or "serial" in t["path"].lower() or "fixture" in t["path"].lower())
]
print(f"candidates: {len(candidates)}")
for f in sorted(candidates, key=lambda x: x.get("size", 0))[:30]:
    sz = f.get("size", 0)
    print(f"  {sz:>7}  {f['path']}")
