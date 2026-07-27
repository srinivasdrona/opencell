"""Mechanical derivation of the L2.2 full-extraction production process set.

Per the task's hard policy, the production process set for the full
multi-seed extraction must be derived *mechanically* from
``docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`` rather than hand-picked:

    production_set = {
        p : p.in_scope_L2_2 == True
        and effective_harness_type(p) == "design_a_per_tick"
    } - {
        p : p has a valid specialized 50-seed ensemble under
            data/m1_sources/karr_native/ensembles/<p.lower()>/
    }

``effective_harness_type`` is the per-process ``harness_type`` field if
present, else the bucket-level default declared under ``buckets.<BUCKET>``.

Run directly for a human-readable report:

    bin\\oc-py scripts/l22_extraction/derive_scope.py

Or import ``derive_scope()`` / ``production_process_set()`` from other
tooling (the launcher and tests both do this) to avoid re-deriving the list
by hand and risking drift from the catalog.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
KARR_NATIVE_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native"

# A specialized ensemble is only trusted as "valid" (and therefore excludable
# from the generic v2 production set) once its manifest declares 50 present
# seeds. This is a static, mechanically-checkable declaration on disk, not a
# hardcoded process name list -- see `_specialized_ensemble_candidates`.
EXPECTED_SPECIALIZED_SEED_COUNT = 50


@dataclass(frozen=True)
class CatalogProcess:
    name: str
    bucket: str
    in_scope_l2_2: bool
    harness_type: str
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class ScopeReport:
    production: tuple[str, ...]
    specialized_excluded: dict[str, str]
    event_class_excluded: tuple[str, ...]
    out_of_scope_excluded: tuple[str, ...]
    design_a_per_tick_in_scope: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "production": list(self.production),
            "specialized_excluded": dict(self.specialized_excluded),
            "event_class_excluded": list(self.event_class_excluded),
            "out_of_scope_excluded": list(self.out_of_scope_excluded),
            "design_a_per_tick_in_scope": list(self.design_a_per_tick_in_scope),
        }


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _iter_processes(catalog: dict[str, Any]) -> list[CatalogProcess]:
    buckets = catalog.get("buckets", {})
    processes: list[CatalogProcess] = []
    for raw in catalog.get("processes", []):
        bucket = raw["bucket"]
        in_scope = bool(raw.get("in_scope_L2_2", False))
        harness_type = raw.get("harness_type") or buckets.get(bucket, {}).get("harness_type")
        if in_scope and harness_type is None:
            raise ValueError(
                f"Process {raw['name']!r} (bucket={bucket!r}) is in_scope_L2_2=true but has no "
                "explicit or bucket-default harness_type; refusing to guess."
            )
        harness_type = harness_type or "n/a"
        processes.append(
            CatalogProcess(
                name=raw["name"],
                bucket=bucket,
                in_scope_l2_2=in_scope,
                harness_type=harness_type,
                raw=raw,
            )
        )
    return processes


def _specialized_ensemble_manifest(process_name: str, karr_native_root: Path) -> dict[str, Any] | None:
    manifest_path = karr_native_root / "ensembles" / process_name.lower() / "MANIFEST.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _specialized_ensemble_seed_count_on_disk(process_name: str, karr_native_root: Path) -> int:
    ensemble_dir = karr_native_root / "ensembles" / process_name.lower()
    if not ensemble_dir.is_dir():
        return 0
    count = 0
    for seed_dir in sorted(ensemble_dir.glob("seed_*")):
        if any(seed_dir.glob(f"{process_name}_*ticks.mat")):
            count += 1
    return count


def derive_scope(
    catalog: dict[str, Any] | None = None,
    *,
    karr_native_root: Path = KARR_NATIVE_ROOT,
) -> ScopeReport:
    catalog = catalog if catalog is not None else load_catalog()
    processes = _iter_processes(catalog)

    design_a_per_tick_in_scope = tuple(
        sorted(p.name for p in processes if p.in_scope_l2_2 and p.harness_type == "design_a_per_tick")
    )
    event_class_excluded = tuple(
        sorted(p.name for p in processes if p.in_scope_l2_2 and p.harness_type == "event_class")
    )
    out_of_scope_excluded = tuple(sorted(p.name for p in processes if not p.in_scope_l2_2))

    specialized_excluded: dict[str, str] = {}
    production: list[str] = []
    for name in design_a_per_tick_in_scope:
        manifest = _specialized_ensemble_manifest(name, karr_native_root)
        on_disk_count = _specialized_ensemble_seed_count_on_disk(name, karr_native_root)
        if manifest is not None and on_disk_count >= EXPECTED_SPECIALIZED_SEED_COUNT:
            manifest_count = manifest.get("present_seed_count", manifest.get("expected_seed_count"))
            specialized_excluded[name] = (
                f"specialized ensemble at data/m1_sources/karr_native/ensembles/{name.lower()}/ "
                f"declares {manifest_count} seeds, {on_disk_count} present on disk "
                f"(>= expected {EXPECTED_SPECIALIZED_SEED_COUNT}); preferred by load_karr_oracle()"
            )
        else:
            production.append(name)

    return ScopeReport(
        production=tuple(sorted(production)),
        specialized_excluded=specialized_excluded,
        event_class_excluded=event_class_excluded,
        out_of_scope_excluded=out_of_scope_excluded,
        design_a_per_tick_in_scope=design_a_per_tick_in_scope,
    )


def production_process_set(
    catalog: dict[str, Any] | None = None, *, karr_native_root: Path = KARR_NATIVE_ROOT
) -> tuple[str, ...]:
    """The exact list this launcher will extract seeds for. Single source of truth."""
    return derive_scope(catalog, karr_native_root=karr_native_root).production


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text.")
    args = parser.parse_args()

    report = derive_scope()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    print(f"design_a_per_tick in-scope ({len(report.design_a_per_tick_in_scope)}):")
    for name in report.design_a_per_tick_in_scope:
        print(f"  - {name}")
    print(f"\nspecialized-ensemble excluded ({len(report.specialized_excluded)}):")
    for name, why in report.specialized_excluded.items():
        print(f"  - {name}: {why}")
    print(f"\nPRODUCTION SET ({len(report.production)}):")
    for name in report.production:
        print(f"  - {name}")
    print(f"\nevent_class excluded ({len(report.event_class_excluded)}): {', '.join(report.event_class_excluded)}")
    print(
        f"out_of_scope (in_scope_L2_2=false) excluded ({len(report.out_of_scope_excluded)}): "
        f"{', '.join(report.out_of_scope_excluded)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
