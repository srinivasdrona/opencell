"""Lightweight PROCESS_CATALOG.yaml access for the evidence-index generator.

Deliberately reuses ``scripts/l22_extraction/derive_scope.py``'s catalog
parsing (``load_catalog`` / ``_iter_processes``) instead of re-implementing
PROCESS_CATALOG.yaml parsing a second time, so "in scope" can never drift
between the raw-extraction tooling and the evidence-index generator.

Note this module's scope is intentionally *broader* than
``derive_scope.derive_scope()``: that function computes the raw-extraction
*production set* (``design_a_per_tick`` harness minus processes that already
have a valid specialized 50-seed ensemble on disk). The evidence index's
scope is every catalog process flagged ``in_scope_L2_2: true``, regardless
of harness_type or raw-extraction/specialized-ensemble status -- i.e. the
full 22-process L2.2 in-scope GREEN-claim set (18 ``design_a_per_tick`` +
4 ``event_class``).
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_extraction import derive_scope as _ds  # noqa: E402

REPO_ROOT = _ds.REPO_ROOT
CATALOG_PATH = _ds.CATALOG_PATH

# Fallback used only if a catalog somehow omits universals.N_seeds entirely.
DEFAULT_N_SEEDS = 50


@dataclass(frozen=True)
class ProcessEntry:
    name: str
    bucket: str
    harness_type: str
    m_ticks: int | None
    n_seeds: int
    primary_channel: str | None
    closed_form_dominant: str
    event_channels: tuple[str, ...]
    output_channels: tuple[str, ...]
    primary_distance: str

    @property
    def uses_projection_distance(self) -> bool:
        """True for chromosome-primary processes (per_component_scaled / hurdle_*)."""
        return self.primary_distance != "per_tick_vector_w1_mean"


def catalog_sha256(path: Path = CATALOG_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def in_scope_processes(path: Path = CATALOG_PATH) -> dict[str, ProcessEntry]:
    """All ``in_scope_L2_2: true`` processes, keyed by canonical name.

    Fails closed the same way ``derive_scope._iter_processes`` does: a
    catalog process that is in-scope but declares no explicit or
    bucket-default ``harness_type`` raises ``ValueError`` rather than being
    silently skipped or guessed.
    """
    catalog = _ds.load_catalog(Path(path))
    universals = catalog.get("universals", {}) or {}
    default_n = int(universals.get("N_seeds", DEFAULT_N_SEEDS))

    entries: dict[str, ProcessEntry] = {}
    for proc in _ds._iter_processes(catalog):
        if not proc.in_scope_l2_2:
            continue
        raw = proc.raw
        entries[proc.name] = ProcessEntry(
            name=proc.name,
            bucket=proc.bucket,
            harness_type=proc.harness_type,
            m_ticks=raw.get("M_ticks"),
            n_seeds=int(raw.get("N_seeds", default_n)),
            primary_channel=raw.get("primary_channel"),
            closed_form_dominant=str(raw.get("closed_form_dominant", "false")),
            event_channels=tuple(raw.get("event_channels") or ()),
            output_channels=tuple(raw.get("output_channels") or ()),
            primary_distance=str(raw.get("primary_distance", "per_tick_vector_w1_mean")),
        )
    return entries


def relative_to_repo(path: Path) -> str:
    """Best-effort repo-relative path string; falls back to str(path) if unrelated."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
