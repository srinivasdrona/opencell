"""Versioned L2.event registry (requirement 1).

This is a **separate** file from ``docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml``
-- this task must not edit that catalog (its content hash gates Design-A's
own staleness checks; touching it would silently stale every Design-A
evidence row). The registry lives at
``docs/phase_f/l2_event/event_registry.yaml`` and is *derived/validated*
against the catalog's process names and ``harness_type`` field read-only,
via the same ``scripts/l22_extraction/derive_scope`` parser Design-A's own
evidence tooling uses (so there is exactly one YAML parser for this file in
the repo, not two that can drift).
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l22_extraction import derive_scope as _ds  # noqa: E402  (reuse, read-only)
from scripts.l2_event.schema import EVENT_TIMING_MODELS, REGISTRY_SCHEMA_VERSION  # noqa: E402

REPO_ROOT = _REPO_ROOT
REGISTRY_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_event" / "event_registry.yaml"
CATALOG_PATH = _ds.CATALOG_PATH


class RegistryError(Exception):
    """Raised for any registry load/validation failure. Distinct from
    :class:`scripts.l2_event.window_loader.EventWindowRefused` -- this is a
    configuration-time error, not a per-run refusal."""


@dataclass(frozen=True)
class EventRegistryEntry:
    process: str
    in_scope_v4: bool
    adapter_id: str | None
    adapter_status: str
    event_timing_model: str | None
    magnitude_gateable: bool
    required_n_seeds: int
    deferred_reason: str | None
    notes: str = ""


def registry_sha256(path: Path = REGISTRY_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_raw(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RegistryError(f"{path}: expected a top-level mapping.")
    version = raw.get("schema_version")
    if version != REGISTRY_SCHEMA_VERSION:
        raise RegistryError(
            f"{path}: schema_version={version!r}, expected {REGISTRY_SCHEMA_VERSION!r}."
        )
    return raw


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, EventRegistryEntry]:
    raw = _load_raw(path)
    entries: dict[str, EventRegistryEntry] = {}
    for row in raw.get("processes", []):
        name = row.get("process")
        if not name:
            raise RegistryError(f"{path}: a process row is missing 'process' key: {row!r}")
        model = row.get("event_timing_model")
        if model is not None and model not in EVENT_TIMING_MODELS:
            raise RegistryError(
                f"{path}: process '{name}' has event_timing_model={model!r}, "
                f"expected one of {EVENT_TIMING_MODELS!r} or null."
            )
        entries[name] = EventRegistryEntry(
            process=name,
            in_scope_v4=bool(row.get("in_scope_v4", False)),
            adapter_id=row.get("adapter_id"),
            adapter_status=str(row.get("adapter_status", "not_implemented")),
            event_timing_model=model,
            magnitude_gateable=bool(row.get("magnitude_gateable", False)),
            required_n_seeds=int(row.get("required_n_seeds", 50)),
            deferred_reason=row.get("deferred_reason"),
            notes=str(row.get("notes", "")),
        )
    if not entries:
        raise RegistryError(f"{path}: no 'processes' rows found.")
    return entries


def validate_against_catalog(
    registry: dict[str, EventRegistryEntry],
    catalog_path: Path = CATALOG_PATH,
) -> list[str]:
    """Read-only cross-check: every registry process must exist in
    ``PROCESS_CATALOG.yaml`` with ``harness_type: event_class``. Returns a
    list of human-readable problems (empty list = fully consistent). Never
    reads or writes anything other than the catalog's in-memory parse."""
    problems: list[str] = []
    catalog = _ds.load_catalog(Path(catalog_path))
    by_name = {p.name: p for p in _ds._iter_processes(catalog)}
    for name, entry in registry.items():
        cp = by_name.get(name)
        if cp is None:
            problems.append(f"Registry process '{name}' not found in {catalog_path.name}.")
            continue
        if cp.harness_type != "event_class":
            problems.append(
                f"Registry process '{name}' expects catalog harness_type='event_class', "
                f"found {cp.harness_type!r}."
            )
        if entry.in_scope_v4 and not cp.in_scope_l2_2:
            problems.append(
                f"Registry process '{name}' is in_scope_v4=true but catalog "
                "in_scope_L2_2=false."
            )
    return problems


def resolve_process_entry(process: str, path: Path = REGISTRY_PATH) -> EventRegistryEntry:
    registry = load_registry(path)
    if process not in registry:
        raise RegistryError(
            f"Process '{process}' has no entry in {path}. Known processes: "
            f"{sorted(registry)}"
        )
    return registry[process]
