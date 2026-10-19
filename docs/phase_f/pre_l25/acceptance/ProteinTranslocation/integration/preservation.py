import sys
sys.dont_write_bytecode = True
from integration_common import *

event("preservation_" + sys.argv[1] + "_start")
if sys.argv[1] == "before":
    paths = {ROOT / p for p in tree("sealed_tree.txt")}
    paths.update(p for p in OLD_REVIEW.rglob("*") if p.is_file())
    paths.update(p for p in (ORIGINAL / "artifacts/m1_cohort/m1_pt/evidence_bundle/ProteinTranslocation/latest").rglob("*") if p.is_file())
    paths.update(ROOT / r["path"] for r in load(PT / "input_manifest.json")["inputs"])
    snapshot = {str(p): {"sha256": sha(p), "bytes": p.stat().st_size,
                         "mtime_ns": p.stat().st_mtime_ns}
                for p in sorted(paths) if p.is_file()}
    save("preservation_before.json", snapshot)
    event("preservation_before_complete", files=len(snapshot),
          bytes=sum(r["bytes"] for r in snapshot.values()))
else:
    old = load(OUT / "preservation_before.json")
    changes = []
    for name, expected in old.items():
        p = Path(name)
        actual = ({"sha256": sha(p), "bytes": p.stat().st_size,
                   "mtime_ns": p.stat().st_mtime_ns} if p.is_file() else None)
        if actual != expected:
            changes.append({"path": name, "expected": expected, "actual": actual})
    save("preservation_after.json", {"files": len(old), "changes": changes,
                                    "finished_at": now()})
    event("preservation_after_complete", files=len(old), changes=changes)
    assert not changes
