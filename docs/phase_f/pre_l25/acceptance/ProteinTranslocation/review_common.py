import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path.cwd().resolve()
OUT = ROOT / "artifacts/m1_cohort/m1_pt/independent_acceptance"
LANE = OUT.parent
RAW = ROOT / "artifacts/l2_2_gates/ProteinTranslocation/latest"
CANDIDATE = LANE / "evidence_bundle"
assert ROOT == Path("/mnt/e/opencell-worktrees/m1-pt-20261017")
assert OUT.is_dir()
for directory in ("scratch", "scratch/pytest", "scratch/tmp", "scratch/homecache"):
    (OUT / directory).mkdir(parents=True, exist_ok=True)
os.environ.update({
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": str(OUT / "scratch/tmp"),
    "TMP": str(OUT / "scratch/tmp"),
    "TEMP": str(OUT / "scratch/tmp"),
    "XDG_CACHE_HOME": str(OUT / "scratch/homecache"),
    "MPLCONFIGDIR": str(OUT / "scratch/homecache"),
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
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def event(stage, **fields):
    record = {"stage": stage, "at": now(), "pid": os.getpid(),
              "argv": sys.argv, "cwd": str(ROOT), **fields}
    with (OUT / "commands.jsonl").open("a") as stream:
        stream.write(json.dumps(record, default=str) + "\n")
    with (OUT / "STATUS.md").open("a") as stream:
        stream.write("\n## " + stage + "\n```json\n" +
                     json.dumps(record, indent=2, default=str) + "\n```\n")
    print(json.dumps(record, default=str), flush=True)


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))
