import sys
sys.dont_write_bytecode = True
from review_common import *

event("preservation_" + sys.argv[1] + "_start")
if sys.argv[1] == "before":
    paths = set()
    for name in (OUT / "tracked_paths.txt").read_text(encoding="utf-8-sig").splitlines():
        path = ROOT / name
        if path.is_file():
            paths.add(path)
    for directory in (LANE, RAW.parent, ROOT / "data/m1_sources/karr_native"):
        for path in directory.rglob("*"):
            if path.is_file() and not path.is_relative_to(OUT):
                if directory.name == "karr_native" and path.name != "ProteinTranslocation_100ticks.mat":
                    continue
                paths.add(path)
    for path in (ROOT / "STATUS_m1_pt.md", ROOT / "PROMPT_m1_pt.md",
                 ROOT / "SESSION_CONTEXT.md",
                 ROOT / "artifacts/l2_2_gates/_sweep_logs/ProteinTranslocation.log"):
        if path.is_file():
            paths.add(path)
    snapshot = {}
    for path in sorted(paths):
        stat = path.stat()
        snapshot[relative(path)] = {"sha256": sha(path), "size": stat.st_size,
                                    "mtime_ns": stat.st_mtime_ns}
    save("preservation_before.json", snapshot)
    event("preservation_before_complete", files=len(snapshot),
          bytes=sum(r["size"] for r in snapshot.values()))
else:
    snapshot = load(OUT / "preservation_before.json")
    changes = []
    for name, old in snapshot.items():
        path = ROOT / name
        current = ({"sha256": sha(path), "size": path.stat().st_size,
                    "mtime_ns": path.stat().st_mtime_ns} if path.is_file() else None)
        if current != old:
            changes.append({"path": name, "before": old, "after": current})
    known = set(snapshot)
    new_prior_outputs = [relative(path) for directory in (LANE, RAW.parent)
                         for path in directory.rglob("*")
                         if path.is_file() and not path.is_relative_to(OUT)
                         and relative(path) not in known]
    report = {"files": len(snapshot), "changes": changes,
              "new_prior_outputs": new_prior_outputs, "finished_at": now()}
    save("preservation_after.json", report)
    event("preservation_after_complete", **report)
    assert not changes and not new_prior_outputs
