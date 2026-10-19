import sys
sys.dont_write_bytecode = True
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd().resolve()
OUT = ROOT / "artifacts/m1_integration/independent_pt"
ORIGINAL = Path("/mnt/e/opencell-worktrees/m1-pt-20261017")
OLD_REVIEW = ORIGINAL / "artifacts/m1_cohort/m1_pt/independent_acceptance"
RECEIPTS = ROOT / "docs/phase_f/pre_l25/acceptance/ProteinTranslocation"
BUNDLE_ROOT = ROOT / "docs/phase_f/l2_2_design_a/evidence_bundle"
PT = BUNDLE_ROOT / "ProteinTranslocation/latest"
HEAD = "f87ebf1939a0a172a13f3d15c2ede0af0a3bca95"
assert ROOT == Path("/mnt/e/opencell-worktrees/m1-accepted-20261019")
assert OUT.is_dir()
for name in ("scratch", "scratch/pytest", "scratch/tmp", "scratch/cache"):
    (OUT / name).mkdir(parents=True, exist_ok=True)
os.environ.update({
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": str(OUT / "scratch/tmp"), "TMP": str(OUT / "scratch/tmp"),
    "TEMP": str(OUT / "scratch/tmp"), "XDG_CACHE_HOME": str(OUT / "scratch/cache"),
    "MPLCONFIGDIR": str(OUT / "scratch/cache"),
})
sys.path[:0] = [str(ROOT), str(ROOT / "tests/vivarium")]


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(name, value):
    target = (OUT / name).resolve()
    assert target.is_relative_to(OUT)
    target.write_text(json.dumps(value, indent=2, default=str) + "\n")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def event(stage, **fields):
    record = {"at": now(), "pid": os.getpid(), "cwd": str(ROOT),
              "argv": sys.argv, "stage": stage, **fields}
    with (OUT / "commands.jsonl").open("a") as stream:
        stream.write(json.dumps(record, default=str) + "\n")
    with (OUT / "STATUS.md").open("a") as stream:
        stream.write("\n## " + stage + "\n```json\n" +
                     json.dumps(record, indent=2, default=str) + "\n```\n")
    print(json.dumps(record, default=str), flush=True)


def tree(name):
    records = {}
    for line in (OUT / name).read_text(encoding="utf-8-sig").splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, oid = metadata.split()
        if kind == "blob":
            records[path] = oid
    return records
