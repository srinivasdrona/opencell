"""Data versioning: content-hashed snapshots for parameter files.

Lightweight alternative to DVC — hashes parameter files and tracks
versions so we know which data version produced which results.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def hash_file(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_directory(dirpath: Path, extensions: tuple[str, ...] = (".yaml", ".yml", ".json", ".sbml")) -> dict[str, str]:
    """Hash all data files in a directory."""
    hashes = {}
    for f in sorted(dirpath.rglob("*")):
        if f.is_file() and f.suffix in extensions:
            rel = f.relative_to(dirpath)
            hashes[str(rel)] = hash_file(f)
    return hashes


def create_snapshot(
    data_dir: Path,
    snapshot_dir: Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Create a versioned snapshot of data files.

    Returns path to the snapshot manifest JSON.
    """
    snapshot_dir = snapshot_dir or data_dir / ".snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    hashes = hash_directory(data_dir)

    # Combined hash of all files
    combined = hashlib.sha256()
    for k in sorted(hashes.keys()):
        combined.update(f"{k}:{hashes[k]}".encode())
    version_hash = combined.hexdigest()[:12]

    snapshot = {
        "version": version_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": hashes,
        "metadata": metadata or {},
    }

    snapshot_path = snapshot_dir / f"snapshot_{version_hash}.json"
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    logger.info(f"Created data snapshot: {version_hash} ({len(hashes)} files)")
    return snapshot_path


def compare_snapshots(snap_a: Path, snap_b: Path) -> dict[str, Any]:
    """Compare two snapshots and return delta report."""
    with open(snap_a) as f:
        a = json.load(f)
    with open(snap_b) as f:
        b = json.load(f)

    files_a = set(a["files"].keys())
    files_b = set(b["files"].keys())

    added = files_b - files_a
    removed = files_a - files_b
    changed = {f for f in files_a & files_b if a["files"][f] != b["files"][f]}

    return {
        "from_version": a["version"],
        "to_version": b["version"],
        "added": sorted(added),
        "removed": sorted(removed),
        "changed": sorted(changed),
        "unchanged": len(files_a & files_b) - len(changed),
    }
