#!/usr/bin/env python3
"""
L1b method-completeness gate.

Enforces that OpenCell implements a counterpart for every runtime_port_required
Karr method (from data/karr_method_inventory/karr_process_methods.json), using
the OC method map (data/karr_method_inventory/oc_method_map.yaml) as the record
of correspondence.

PASS requires, for every runtime method:
  - a map entry exists,
  - status is confirmed | inlined | gap  (NOT needs_confirmation),
  - for confirmed|inlined: the `oc` anchor "file:symbol:line" resolves — the file
    exists, the symbol is a def/class at/around that line (AST),
  - for gap: a non-empty `note` justifying the genuine absence.

Exit 0 only when all runtime methods are resolved. This is the harness the
source-confirmation fleet works behind: it cannot silently pass while methods
remain unconfirmed.

Usage: python scripts/l1b_method_completeness.py [--format plain|json]
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")

REPO = Path(__file__).resolve().parents[1]
INV = REPO / "data/karr_method_inventory/karr_process_methods.json"
MAP = REPO / "data/karr_method_inventory/oc_method_map.yaml"

_AST_CACHE: dict[Path, dict[str, tuple[int, int]]] = {}


def _symbol_ranges(fp: Path) -> dict[str, tuple[int, int]]:
    if fp in _AST_CACHE:
        return _AST_CACHE[fp]
    ranges: dict[str, tuple[int, int]] = {}
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, FileNotFoundError):
        _AST_CACHE[fp] = ranges
        return ranges

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack: list[str] = []

        def _add(self, node):
            qual = ".".join([*self.stack, node.name])
            end = getattr(node, "end_lineno", node.lineno)
            ranges[qual] = (node.lineno, end)
            ranges.setdefault(node.name, (node.lineno, end))

        def visit_ClassDef(self, node):
            self._add(node)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node):
            self._add(node)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

    V().visit(tree)
    _AST_CACHE[fp] = ranges
    return ranges


def _resolve_oc_anchor(anchor: str) -> str | None:
    """Return an error string if the anchor doesn't resolve, else None."""
    parts = anchor.split(":")
    if len(parts) < 3:
        return f"malformed anchor (need file:symbol:line): {anchor!r}"
    path, symbol, line = parts[0], parts[1], parts[-1]
    fp = REPO / path
    if not fp.exists():
        return f"missing file {path}"
    try:
        want = int(line)
    except ValueError:
        return f"bad line {line!r}"
    ranges = _symbol_ranges(fp)
    if symbol not in ranges:
        return f"symbol {symbol!r} not found in {path}"
    lo, hi = ranges[symbol]
    if not (lo - 3 <= want <= hi + 3):
        return f"line {want} outside {symbol} range {lo}-{hi} in {path}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["plain", "json"], default="plain")
    args = ap.parse_args()

    inv = json.loads(INV.read_text())
    mp = yaml.safe_load(MAP.read_text()) if MAP.exists() else {"processes": {}}
    map_procs = mp.get("processes", {})

    per_process = {}
    total = {"confirmed": 0, "inlined": 0, "gap": 0, "unconfirmed": 0, "error": 0}
    failures: list[str] = []

    for cls, pdata in inv["processes"].items():
        runtime = [m for m in pdata["methods"] if m.get("port_requirement") == "runtime_port_required"]
        if not runtime:
            continue
        entries = (map_procs.get(cls) or {}).get("runtime_methods", {})
        counts = {"confirmed": 0, "inlined": 0, "gap": 0, "unconfirmed": 0, "error": 0}
        for m in runtime:
            name = m["name"]
            e = entries.get(name)
            if e is None:
                counts["unconfirmed"] += 1
                failures.append(f"{cls}.{name}: no map entry")
                continue
            status = e.get("status")
            if status in ("needs_confirmation", None):
                counts["unconfirmed"] += 1
                failures.append(f"{cls}.{name}: needs_confirmation")
            elif status == "gap":
                if not (e.get("note") or "").strip():
                    counts["error"] += 1
                    failures.append(f"{cls}.{name}: gap without justification note")
                else:
                    counts["gap"] += 1
            elif status in ("confirmed", "inlined"):
                anchor = e.get("oc")
                if not anchor:
                    counts["error"] += 1
                    failures.append(f"{cls}.{name}: status={status} but no oc anchor")
                else:
                    err = _resolve_oc_anchor(anchor)
                    if err:
                        counts["error"] += 1
                        failures.append(f"{cls}.{name}: {err}")
                    else:
                        counts[status] += 1
            else:
                counts["error"] += 1
                failures.append(f"{cls}.{name}: unknown status {status!r}")
        per_process[cls] = {"runtime": len(runtime), **counts}
        for k in total:
            total[k] += counts[k]

    ok = total["unconfirmed"] == 0 and total["error"] == 0
    resolved = total["confirmed"] + total["inlined"] + total["gap"]
    grand = resolved + total["unconfirmed"] + total["error"]

    if args.format == "json":
        print(json.dumps({"pass": ok, "total": total, "per_process": per_process,
                          "failures": failures}, indent=2))
        return 0 if ok else 1

    print("=" * 84)
    print(f"L1b METHOD-COMPLETENESS: {'PASS' if ok else 'FAIL'} "
          f"({resolved}/{grand} runtime methods resolved)")
    print("=" * 84)
    print(f"  confirmed:   {total['confirmed']}")
    print(f"  inlined:     {total['inlined']}")
    print(f"  gap:         {total['gap']}")
    print(f"  unconfirmed: {total['unconfirmed']}  <-- fleet TODO")
    print(f"  error:       {total['error']}  <-- unresolvable anchors / missing justification")
    print()
    print(f"{'Process':<28} {'run':>4} {'conf':>5} {'inln':>5} {'gap':>4} {'??':>4} {'err':>4}")
    print("-" * 84)
    for cls in sorted(per_process, key=lambda c: -(per_process[c]['unconfirmed'] + per_process[c]['error'])):
        r = per_process[cls]
        print(f"{cls:<28} {r['runtime']:>4} {r['confirmed']:>5} {r['inlined']:>5} "
              f"{r['gap']:>4} {r['unconfirmed']:>4} {r['error']:>4}")
    if failures and not ok:
        print(f"\nFirst failures ({min(len(failures), 10)} of {len(failures)}):")
        for f in failures[:10]:
            print(f"  - {f}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
