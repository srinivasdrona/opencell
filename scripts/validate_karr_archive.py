"""Validate the Karr archive end-to-end: re-runs every ingest script
from the archive, computes sha256 of each output fixture, and prints a
table comparing to the previously-committed sha256.

Usage:
    python scripts/validate_karr_archive.py
    python scripts/validate_karr_archive.py --update  # refresh expected hashes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXPECTED_PATH = REPO / "data" / "karr_archive" / "fixture_hashes.json"

INGEST_SCRIPTS = [
    "karr_native_ingest_m1.py",
    "karr_native_ingest_m2.py",
    "karr_native_ingest_m3.py",
    "karr_native_ingest_compartmented.py",
    "karr_native_ingest_complexes.py",
    "karr_native_ingest_m1_dynamics.py",
    "karr_native_ingest_m2v2.py",
    "karr_native_ingest_m3v2.py",
]

FIXTURE_DIR = REPO / "data" / "karr_fixtures"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fixture_paths() -> list[Path]:
    return sorted(
        p
        for p in FIXTURE_DIR.glob("karr_*")
        if p.suffix in (".json", ".npz") and ".bak" not in p.name
    )


def _hash_npz_arrays(path: Path) -> str:
    """Stable hash over npz array contents (insensitive to zip metadata)."""
    import numpy as np

    h = hashlib.sha256()
    with np.load(path, allow_pickle=True) as nz:
        for k in sorted(nz.files):
            arr = nz[k]
            h.update(k.encode())
            h.update(str(arr.dtype).encode())
            h.update(str(arr.shape).encode())
            h.update(arr.tobytes())
    return h.hexdigest()


def _hash_json_payload(path: Path) -> str:
    """Hash of JSON content excluding `source_*` metadata keys."""
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if not k.startswith("source_")}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _hash_fixture(path: Path) -> str:
    if path.suffix == ".npz":
        return _hash_npz_arrays(path)
    return _hash_json_payload(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--update", action="store_true", help="Refresh expected hashes from current fixtures."
    )
    ap.add_argument(
        "--skip-rerun",
        action="store_true",
        help="Skip re-running ingest scripts; just hash existing fixtures.",
    )
    args = ap.parse_args()

    if not args.skip_rerun:
        print("Re-running all ingest scripts from archive...")
        for s in INGEST_SCRIPTS:
            print(f"  -> {s}")
            r = subprocess.run(
                [sys.executable, str(REPO / "scripts" / s)], capture_output=True, text=True
            )
            if r.returncode != 0:
                print(f"FAIL: {s}\nstderr:\n{r.stderr}")
                sys.exit(1)

    fixtures = _fixture_paths()
    actual = {p.name: _hash_fixture(p) for p in fixtures}

    if args.update:
        EXPECTED_PATH.write_text(json.dumps(actual, indent=2, sort_keys=True))
        print(f"Wrote {len(actual)} expected hashes to {EXPECTED_PATH.name}")
        return

    if not EXPECTED_PATH.exists():
        print(f"NOTE: {EXPECTED_PATH.name} missing; run with --update to seed.")
        for name, h in sorted(actual.items()):
            print(f"  {name}  {h[:16]}")
        sys.exit(0)

    expected = json.loads(EXPECTED_PATH.read_text())
    bad = []
    for name, h in sorted(actual.items()):
        exp = expected.get(name)
        ok = exp == h
        flag = "OK  " if ok else "FAIL"
        print(f"  [{flag}] {name}  {h[:16]}")
        if not ok:
            bad.append(name)
    missing = sorted(set(expected) - set(actual))
    for name in missing:
        print(f"  [FAIL] {name}  (missing — expected hash present but fixture not produced)")
        bad.append(name)
    if bad:
        print(f"\n{len(bad)} fixture(s) drifted from committed hashes.")
        sys.exit(1)
    print(f"\nAll {len(actual)} fixtures match committed hashes.")


if __name__ == "__main__":
    main()
