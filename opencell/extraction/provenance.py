"""Source-artifact provenance helpers.

Every extracted candidate must be traceable to a hashed cached file.  This
module computes those hashes and exposes a tiny ``Provenance`` value
object that travels with each candidate.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

EXTRACTOR_VERSION = "opencell.extraction/0.1"


@dataclass(frozen=True)
class Provenance:
    """Minimal provenance record for a cached source file."""

    path: str
    sha256: str
    extractor_version: str = EXTRACTOR_VERSION


def file_sha256(path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_provenance(path: str | Path, version: str = EXTRACTOR_VERSION) -> Provenance:
    return Provenance(path=str(path), sha256=file_sha256(path), extractor_version=version)
