#!/usr/bin/env python3
"""
Build the OC method-map SEED from the completeness report.

For each of the 115 runtime_port_required Karr methods, emit an entry mapping it
to its OpenCell counterpart. Mechanically-confident matches are pre-filled
(status: mechanical); the rest are marked needs_confirmation for the fleet.

The fleet's job: for every needs_confirmation entry, read the Karr .m method +
the process's OC files, and set:
  status: confirmed   oc: "<file>:<symbol>:<line>"   (a real OC def implements it)
  status: inlined     oc: "<file>:<parent_symbol>:<line>"  note: "folded into <parent>"
  status: gap         oc: null   note: "<why genuinely absent>"

The L1b method-completeness gate then requires every runtime method to be
confirmed|inlined|gap with a resolvable anchor (no needs_confirmation left).

Usage: python scripts/build_oc_method_map.py
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")

REPO = Path(__file__).resolve().parents[1]
INV = REPO / "data/karr_method_inventory/karr_process_methods.json"
REPORT = REPO / "tmp/_oc_completeness_report.json"
OUT = REPO / "data/karr_method_inventory/oc_method_map.yaml"

# tiers from the completeness checker -> seed status
TIER_TO_STATUS = {
    "covered": "mechanical",          # high-confidence name/convention match (fleet still verifies anchor)
    "inlined_or_renamed": "needs_confirmation",
    "likely_gap": "needs_confirmation",
}


def main() -> int:
    inv = json.loads(INV.read_text())
    report = json.loads(REPORT.read_text())

    processes = {}
    for cls, pdata in inv["processes"].items():
        runtime = [m for m in pdata["methods"] if m.get("port_requirement") == "runtime_port_required"]
        if not runtime:
            continue
        rep = report.get(cls, {})
        rep_by_method = {r["method"]: r for r in rep.get("results", [])}
        oc_files = rep.get("oc_files", [])

        entries = {}
        for m in sorted(runtime, key=lambda x: x["line"]):
            r = rep_by_method.get(m["name"], {})
            hint = r.get("oc")
            # Every runtime method requires source confirmation. Mechanical matches
            # are recorded as non-authoritative HINTS only (they can be wrong, e.g.
            # evolveState grabbing a shared RequestCalculator's next_update).
            entry = {
                "matlab": f"{pdata['matlab_file']}:{m['name']}:{m['line']}",
                "status": "needs_confirmation",
                "oc": None,
                "hint": hint if hint and hint != "RequestCalculator*.next_update" else None,
                "hint_kind": r.get("status") if hint else None,
                "note": "",
            }
            entries[m["name"]] = entry

        processes[cls] = {
            "oc_files": oc_files,
            "runtime_methods": entries,
        }

    doc = {
        "schema": "oc_method_map/1.0",
        "purpose": "Map each runtime_port_required Karr method to its OpenCell counterpart. Filled by source-confirmation fleet; enforced by the L1b method-completeness gate.",
        "status_legend": {
            "needs_confirmation": "not yet verified at source — fleet TODO (a `hint` may suggest the OC location but is non-authoritative)",
            "confirmed": "a real OC def implements this method (oc = file:symbol:line)",
            "inlined": "behavior folded into a larger OC method (oc = file:parent:line, note names parent)",
            "gap": "genuinely absent in OC (oc = null, note explains) — a real porting gap to fix",
        },
        "processes": processes,
    }
    OUT.write_text(yaml.safe_dump(doc, sort_keys=False, width=100), encoding="utf-8")

    # summary
    tot = with_hint = needs = 0
    for cls, p in processes.items():
        for name, e in p["runtime_methods"].items():
            tot += 1
            needs += 1
            if e.get("hint"):
                with_hint += 1
    print(f"Wrote {OUT.relative_to(REPO)}")
    print(f"  runtime methods mapped:  {tot}")
    print(f"  all status:              needs_confirmation (fleet confirms every one at source)")
    print(f"  with a non-authoritative hint: {with_hint}")
    print(f"  no hint (from scratch):        {tot - with_hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
