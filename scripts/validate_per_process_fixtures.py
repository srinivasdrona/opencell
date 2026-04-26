"""Validate the committed per-process fixture payload.

Pattern mirrors `scripts/validate_karr_archive.py`:

  1. Re-extract every fixture into a temp dir.
  2. Hash each emitted .npz / .json byte-for-byte.
  3. Compare against `data/karr_fixtures/per_process/fixture_hashes.json`.
  4. Exit non-zero on any mismatch (or, with --seed, write the manifest).

Run after editing `extract_per_process_fixtures.py` to regenerate hashes:

    python scripts/validate_per_process_fixtures.py --seed
    python scripts/validate_per_process_fixtures.py        # verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_DIR = REPO_ROOT / "data/karr_fixtures/per_process"
HASH_FILE = COMMITTED_DIR / "fixture_hashes.json"
EXTRACT_SCRIPT = REPO_ROOT / "scripts/extract_per_process_fixtures.py"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_dir(d: Path) -> dict[str, str]:
    out = {}
    # Exclude human-maintained docs; only hash auto-generated extraction outputs.
    skip = {"README.md", "fixture_hashes.json"}
    for p in sorted(d.glob("*")):
        if p.is_file() and p.name not in skip:
            out[p.name] = sha256_file(p)
    return out


def reextract(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(EXTRACT_SCRIPT), "--all", "--out", str(target)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("re-extraction failed:", res.returncode, file=sys.stderr)
        print(res.stdout, file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", action="store_true",
                    help="Write fixture_hashes.json from current committed payload")
    args = ap.parse_args()

    if args.seed:
        if not COMMITTED_DIR.exists():
            print(f"missing: {COMMITTED_DIR}", file=sys.stderr)
            return 2
        h = hash_dir(COMMITTED_DIR)
        HASH_FILE.write_text(json.dumps(h, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        print(f"wrote {HASH_FILE.relative_to(REPO_ROOT)} ({len(h)} entries)")
        return 0

    if not HASH_FILE.exists():
        print(f"ERROR: {HASH_FILE} missing — run with --seed first", file=sys.stderr)
        return 2

    expected = json.loads(HASH_FILE.read_text(encoding="utf-8"))
    # NB: cannot use /tmp (sandbox policy); place the validation tempdir
    # under the repo's data/.tmp/ which is gitignored.
    tmp_root = REPO_ROOT / "data/.tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m1_validate_", dir=str(tmp_root)) as tmp:
        tmp_dir = Path(tmp)
        reextract(tmp_dir)
        actual = hash_dir(tmp_dir)

    rc = 0
    missing = sorted(set(expected) - set(actual))
    extra   = sorted(set(actual) - set(expected))
    common  = sorted(set(expected) & set(actual))

    for name in missing:
        print(f"MISSING in re-extraction: {name}")
        rc = 1
    for name in extra:
        print(f"UNEXPECTED in re-extraction: {name}")
        rc = 1
    mismatched = [n for n in common if expected[n] != actual[n]]
    for name in mismatched:
        print(f"HASH MISMATCH: {name}")
        print(f"  expected {expected[name]}")
        print(f"  actual   {actual[name]}")
        rc = 1

    print(f"\n{len(common)} files compared, {len(mismatched)} mismatched, "
          f"{len(missing)} missing, {len(extra)} unexpected")
    if rc == 0:
        print("OK: per-process fixture payload matches committed hashes.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
