#!/usr/bin/env python3
"""
OC-side method completeness check.

For each of the 222 required Karr methods (data/karr_method_inventory/
karr_process_methods.json), determine whether a counterpart exists in the
OpenCell code for that process. Emits a per-process deviation report.

Method sources per process are gathered from the wiring row:
  process.oc_file, methods[*].oc.source.path, source_anchors.oc_blocks[*].path
plus the shared request-calculator module. All OC .py files are AST-parsed to
collect every function/method name (with class + line).

Matching tiers per Karr method:
  FOUND_CONTRACT  contract/init method mapped to a known OC convention that exists
  FOUND_NAME      helper/substep matched by normalized-name search
  GAP             no OC counterpart found by any rule (potential porting gap OR
                  inlined logic — needs manual confirmation)

Caveat: this is a STRUCTURAL existence check, not a semantic-equivalence check.
GAP means "no name-matched OC counterpart"; a contract-method GAP is high-signal,
a helper GAP may be inlined into a larger OC method.

Output: JSON report + stdout per-process summary.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INV = REPO / "data/karr_method_inventory/karr_process_methods.json"
WIRING = REPO / "data/schemas/per_process_wiring"
REQUEST_CALC = "opencell/vivarium/karr_request_calculators.py"
OUT = REPO / "tmp/_oc_completeness_report.json"

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")


def camel_to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.lower().replace("__", "_")


def oc_files_for(row: dict) -> list[Path]:
    paths: set[str] = set()
    proc = row.get("process") or {}
    if proc.get("oc_file"):
        paths.add(proc["oc_file"])
    for mb in (row.get("methods") or {}).values():
        oc = (mb or {}).get("oc") or {}
        src = oc.get("source") or {}
        if src.get("path"):
            paths.add(src["path"])
        for sup in oc.get("supporting") or []:
            if isinstance(sup, dict) and sup.get("path"):
                paths.add(sup["path"])
    for a in ((row.get("source_anchors") or {}).get("oc_blocks") or {}).values():
        if isinstance(a, dict) and a.get("path"):
            paths.add(a["path"])
    paths.add(REQUEST_CALC)
    out = []
    for p in sorted(paths):
        fp = REPO / p
        if fp.exists() and fp.suffix == ".py":
            out.append(fp)
    return out


def collect_oc_symbols(files: list[Path]) -> dict[str, list[tuple[str, str, int]]]:
    """Return {lower_name: [(file, qualname, line)]} for every def/async def."""
    index: dict[str, list[tuple[str, str, int]]] = {}
    for fp in files:
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = str(fp.relative_to(REPO)).replace("\\", "/")

        class V(ast.NodeVisitor):
            def __init__(self):
                self.stack: list[str] = []

            def visit_ClassDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def _add(self, node):
                qual = ".".join([*self.stack, node.name])
                index.setdefault(node.name.lower(), []).append((rel, qual, node.lineno))

            def visit_FunctionDef(self, node):
                self._add(node)
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

        V().visit(tree)
    return index


# OC convention name candidates for the canonical contract/init methods.
CONTRACT_CANDIDATES = {
    "evolveState": ["next_update", "evolve_state", "evolvestate", "update"],
    "calcResourceRequirements_Current": [
        "calculate_request", "calc_request", "calculate_requests",
        "calc_resource_requirements_current", "calculate_requirements",
        "compute_request", "requests", "request",
    ],
    "calcResourceRequirements_LifeCycle": [
        "calc_resource_requirements_life_cycle", "lifecycle_request",
        "calculate_lifecycle_request", "life_cycle_request",
    ],
    "initializeState": ["initialize_state", "init_state", "__init__", "initializestate"],
    "initializeConstants": [
        "initialize_constants", "init_constants", "__init__",
        "load_constants", "initializeconstants",
    ],
}


STOPWORDS = {"calc", "evolve", "state", "initialize", "build", "compute", "get",
             "the", "and", "for", "current", "from", "based", "rate", "rates"}


def _tokens(snake: str) -> list[str]:
    return [t for t in snake.split("_") if len(t) >= 4 and t not in STOPWORDS]


def match_method(name: str, category: str, oc_index: dict,
                 global_index: dict, global_text: str,
                 has_reqcalc: bool) -> dict:
    def look(cands, idx):
        for c in cands:
            if c.lower() in idx:
                f, q, ln = idx[c.lower()][0]
                return f"{f}:{q}:{ln}"
        return None

    # Special case A: per-tick request calc is ported as a RequestCalculator class
    if name == "calcResourceRequirements_Current":
        if has_reqcalc:
            return {"status": "COVERED_REQCALC", "oc": "RequestCalculator*.next_update"}
    # Special case B: lifecycle resource requirement (no OC lifecycle layer found)
    if name == "calcResourceRequirements_LifeCycle":
        if "life_cycle" in global_text or "lifecycle" in global_text:
            pass  # ambiguous, fall through to normal matching
        return {"status": "LIKELY_GAP_LIFECYCLE", "oc": None}

    # 1) contract/init known conventions (local)
    if name in CONTRACT_CANDIDATES:
        hit = look(CONTRACT_CANDIDATES[name], oc_index)
        if hit:
            return {"status": "FOUND_CONTRACT", "oc": hit}

    snake = camel_to_snake(name)
    candidates = [name, name.lower(), snake, "_" + snake, snake.replace("_", "")]

    # 2) local name match
    hit = look(candidates, oc_index)
    if hit:
        return {"status": "FOUND_NAME", "oc": hit}

    # 3) global (repo-wide) def-name match -> counterpart under a different module
    hit = look(candidates, global_index)
    if hit:
        return {"status": "FOUND_ELSEWHERE", "oc": hit}

    # 4) distinctive-token text search -> likely inlined/renamed vs truly absent
    toks = _tokens(snake)
    if toks and any(t in global_text for t in toks):
        present = [t for t in toks if t in global_text]
        return {"status": "LIKELY_INLINED", "oc": None, "tokens_present": present}

    return {"status": "LIKELY_MISSING", "oc": None}


def build_global_index() -> tuple[dict, str]:
    """Repo-wide OC def index + concatenated lowercased source text."""
    files = sorted((REPO / "opencell").rglob("*.py"))
    index = collect_oc_symbols(files)
    text = []
    for fp in files:
        try:
            text.append(fp.read_text(encoding="utf-8", errors="replace").lower())
        except Exception:
            pass
    return index, "\n".join(text)


def has_request_calculator(files: list[Path]) -> bool:
    for fp in files:
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("RequestCalculator"):
                if any(isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name == "next_update"
                       for b in node.body):
                    return True
    return False


TIERS = {
    "FOUND_CONTRACT": "covered",
    "FOUND_NAME": "covered",
    "FOUND_ELSEWHERE": "covered",
    "COVERED_REQCALC": "covered",
    "LIKELY_INLINED": "inlined_or_renamed",
    "LIKELY_GAP_LIFECYCLE": "likely_gap",
    "LIKELY_MISSING": "likely_gap",
}


def main() -> int:
    inv = json.loads(INV.read_text())
    global_index, global_text = build_global_index()
    report = {}
    for cls, pdata in inv["processes"].items():
        row_path = WIRING / f"{cls}.yaml"
        if not row_path.exists():
            report[cls] = {"error": f"no wiring row {row_path.name}"}
            continue
        row = yaml.safe_load(row_path.read_text())
        files = oc_files_for(row)
        oc_index = collect_oc_symbols(files)
        reqcalc = has_request_calculator(files)

        required = [m for m in pdata["methods"]
                    if not m["is_constructor"]
                    and m.get("port_requirement") == "runtime_port_required"]
        results = []
        for m in required:
            res = match_method(m["name"], m["category"], oc_index, global_index, global_text, reqcalc)
            res["tier"] = TIERS.get(res["status"], "unknown")
            results.append({"method": m["name"], "category": m["category"], **res})

        def count(tier):
            return sum(1 for r in results if r["tier"] == tier)

        report[cls] = {
            "oc_files": [str(f.relative_to(REPO)).replace("\\", "/") for f in files],
            "required": len(required),
            "covered": count("covered"),
            "inlined_or_renamed": count("inlined_or_renamed"),
            "likely_gap": count("likely_gap"),
            "likely_gap_methods": [r["method"] for r in results if r["tier"] == "likely_gap"],
            "inlined_methods": [r["method"] for r in results if r["tier"] == "inlined_or_renamed"],
            "results": results,
        }

    OUT.write_text(json.dumps(report, indent=2))

    tot = {"required": 0, "covered": 0, "inlined_or_renamed": 0, "likely_gap": 0}
    for r in report.values():
        for k in tot:
            tot[k] += r.get(k, 0)

    print("=" * 100)
    print("OC-SIDE COMPLETENESS (tiered) — covered / inlined-or-renamed / likely-gap")
    print("=" * 100)
    print(f"{'Process':<28} {'req':>4} {'cov':>4} {'inln':>5} {'gap':>4}   likely-gap methods")
    print("-" * 100)
    for cls in sorted(report, key=lambda c: -report[c].get("likely_gap", 0)):
        r = report[cls]
        if "error" in r:
            print(f"{cls:<28} ERROR: {r['error']}")
            continue
        gm = ", ".join(r["likely_gap_methods"][:5])
        if len(r["likely_gap_methods"]) > 5:
            gm += f" +{len(r['likely_gap_methods'])-5}"
        print(f"{cls:<28} {r['required']:>4} {r['covered']:>4} {r['inlined_or_renamed']:>5} {r['likely_gap']:>4}   {gm}")
    print("-" * 100)
    print(f"{'TOTAL':<28} {tot['required']:>4} {tot['covered']:>4} {tot['inlined_or_renamed']:>5} {tot['likely_gap']:>4}")
    print()
    print("Tiers: covered = OC counterpart found (name/convention/req-calc).")
    print("       inlined_or_renamed = distinctive tokens present in OC but no same-named def (needs source confirm).")
    print("       likely_gap = no OC trace found (genuine port gap OR deeper rename — highest-priority to verify).")
    print(f"\n[full report: {OUT.relative_to(REPO)}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
