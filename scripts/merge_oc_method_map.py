#!/usr/bin/env python3
"""
Merge per-process confirmation fragments into the OC method map.

The source-confirmation fleet writes one fragment per process to
tmp/oc_map_confirm/<Process>.yaml. This script folds each fragment's decided
statuses (confirmed | inlined | gap) + oc anchors + notes into
data/karr_method_inventory/oc_method_map.yaml, leaving un-touched methods as-is.

Safeguards:
  - only updates methods that exist in the map for that process,
  - only accepts status in {confirmed, inlined, gap},
  - refuses to downgrade an already-confirmed entry back to needs_confirmation,
  - reports any fragment method not present in the map (typo / stale).

Usage: python scripts/merge_oc_method_map.py [--dry-run]
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")

REPO = Path(__file__).resolve().parents[1]
MAP = REPO / "data/karr_method_inventory/oc_method_map.yaml"
FRAG_DIR = REPO / "tmp/oc_map_confirm"

VALID = {"confirmed", "inlined", "gap"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mp = yaml.safe_load(MAP.read_text())
    procs = mp["processes"]

    fragments = sorted(p for p in FRAG_DIR.glob("*.yaml") if not p.name.startswith("STATUS"))
    if not fragments:
        print(f"no fragments in {FRAG_DIR.relative_to(REPO)}")
        return 0

    applied = 0
    warnings: list[str] = []
    for frag_path in fragments:
        frag = yaml.safe_load(frag_path.read_text())
        cls = frag.get("process")
        if cls not in procs:
            warnings.append(f"{frag_path.name}: unknown process {cls!r}")
            continue
        target = procs[cls].get("runtime_methods", {})
        for name, e in (frag.get("runtime_methods") or {}).items():
            if name not in target:
                warnings.append(f"{cls}.{name}: not in map (stale/typo)")
                continue
            status = (e or {}).get("status")
            if status not in VALID:
                warnings.append(f"{cls}.{name}: invalid status {status!r} (skipped)")
                continue
            oc = e.get("oc")
            note = (e.get("note") or "").strip()
            if status in ("confirmed", "inlined") and not oc:
                warnings.append(f"{cls}.{name}: status={status} but no oc anchor (skipped)")
                continue
            if status == "gap" and not note:
                warnings.append(f"{cls}.{name}: gap without note (skipped)")
                continue
            entry = target[name]
            entry["status"] = status
            entry["oc"] = oc
            entry["note"] = note
            entry.pop("hint", None)
            entry.pop("hint_kind", None)
            applied += 1

    print(f"fragments: {len(fragments)}   methods applied: {applied}")
    if warnings:
        print(f"warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")

    if args.dry_run:
        print("(dry-run: map not written)")
        return 0

    MAP.write_text(yaml.safe_dump(mp, sort_keys=False, width=100), encoding="utf-8")
    print(f"wrote {MAP.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
