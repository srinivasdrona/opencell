#!/usr/bin/env python3
"""
Build the authoritative Karr per-process METHOD INVENTORY (ground truth).

This is the substrate for the L1b method-completeness gate: it enumerates every
method each Karr 2012 process class defines, so we can verify the OpenCell port
implements a counterpart for each one (no Karr method may be silently dropped).

Provenance
----------
The inventory was verified by FOUR independent parsers on 2026-07-03:
  - two written by the orchestrator (flat regex; comment-strip + continuation),
  - one by a Claude Haiku sub-agent (char-level comment state machine),
  - one by a codex gpt-5.4-mini sub-agent (block-stack scope tracker).
They converged on the class-method set except for 6 entries, all resolved by
direct source inspection:
  * FtsZPolymerization.diff / .jacobian  -> file-local functions AFTER the
    `classdef end` (L449 / L500); NOT class methods; EXCLUDED.
  * MacromolecularComplexation.buildProteinComplexs_montecarlokinetic /
    _rates_collisionTheory / _bounds -> file-local functions after classdef
    (L334+); NOT class methods; EXCLUDED.
  * Metabolism.calcGrowthRate -> real class method with a multi-line signature
    (L1266-67); INCLUDED (a flat-regex parser missed it).
The block-stack scoping used here (record a `function` only while the block
stack contains both `classdef` and `methods`) is what correctly excludes the
file-local helpers. Those helpers are still ported -- inside their parent method
(integrateODEs / the complexation build) -- so they are not dropped, just not
tracked as top-level methods.

Classification (against base `Process.m`)
-----------------------------------------
  biology_contract        evolveState, calcResourceRequirements_Current/_LifeCycle
  biology_substep         evolveState_* sub-steps
  init_contract           initializeConstants / initializeState (+ variants)
  process_specific_helper  defined in one class, called by the contract methods
  framework_override      a base Process.m plumbing method overridden per process
  property_getter_setter  get.* / set.* accessors  (EXEMPT from completeness)

`require_oc_counterpart` = biology_contract + biology_substep + init_contract
+ process_specific_helper. framework_override is verified at the chassis level;
property_getter_setter is exempt.

Usage:  python scripts/build_karr_method_inventory.py [--check]
  --check  exit non-zero if the regenerated inventory differs from the committed
           JSON (for CI drift detection).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROC_DIR = REPO / "data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process"
BASE_CLASS = REPO / "data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m"
OUT_JSON = REPO / "data/karr_method_inventory/karr_process_methods.json"

CLASSDEF_RE = re.compile(r"^\s*classdef\b(?:\s*\([^)]*\))?\s+(?P<name>[A-Za-z_]\w*)")
METHODS_RE = re.compile(r"^\s*methods\b")
PROPERTIES_RE = re.compile(r"^\s*properties\b")
EVENTS_RE = re.compile(r"^\s*events\b")
ENUMERATION_RE = re.compile(r"^\s*enumeration\b")
ARGUMENTS_RE = re.compile(r"^\s*arguments\b")
FUNCTION_RE = re.compile(r"^\s*function\b")
END_RE = re.compile(r"^\s*end\s*;?\s*$")
BLOCK_OPENERS_RE = re.compile(r"^\s*(if|for|while|switch|try|parfor|spmd)\b")

BIOLOGY_CONTRACT = {
    "evolveState",
    "calcResourceRequirements_Current",
    "calcResourceRequirements_LifeCycle",
    "initializeState",
}
INIT_CONTRACT = {"initializeConstants", "initializeState"}

REQUIRE_CATEGORIES = {
    "biology_contract",
    "biology_substep",
    "init_contract",
    "process_specific_helper",
}


@dataclass(frozen=True)
class LLine:
    no: int
    text: str


def strip_line_comment(line: str) -> str:
    out, in_s, in_d, i = [], False, False, 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            if in_s and i + 1 < len(line) and line[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "%" and not in_s and not in_d:
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def preprocess(path: Path) -> list[LLine]:
    lines, in_block = [], False
    for idx, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = raw.strip()
        if in_block:
            if s.startswith("%}"):
                in_block = False
            continue
        if s.startswith("%{"):
            in_block = True
            continue
        lines.append(LLine(idx, strip_line_comment(raw)))
    return lines


def collect_signature(lines: list[LLine], start: int) -> tuple[str, int]:
    parts, idx = [], start
    while True:
        text = lines[idx].text.rstrip()
        if text.endswith("..."):
            parts.append(text[:-3].rstrip())
            idx += 1
            while idx < len(lines) and not lines[idx].text.strip():
                idx += 1
            if idx >= len(lines):
                break
            continue
        parts.append(text)
        break
    return " ".join(p.strip() for p in parts if p.strip()), idx


def extract_name(sig: str) -> str | None:
    m = FUNCTION_RE.match(sig)
    if not m:
        return None
    rest = sig[m.end():].strip()
    if rest.startswith("["):
        close = rest.find("]")
        if close != -1:
            after = rest[close + 1:].lstrip()
            if after.startswith("="):
                rest = after[1:].lstrip()
    else:
        pre = re.match(r"[A-Za-z_]\w*\s*=\s*(?P<rhs>.*)$", rest)
        if pre:
            rest = pre.group("rhs").lstrip()
    nm = re.match(r"(?:get|set)\.[A-Za-z_]\w*|[A-Za-z_]\w*", rest)
    return nm.group(0) if nm else None


def update_stack(stack: list[str], line: str) -> None:
    if END_RE.match(line):
        if stack:
            stack.pop()
    elif FUNCTION_RE.match(line):
        stack.append("function")
    elif CLASSDEF_RE.match(line):
        stack.append("classdef")
    elif METHODS_RE.match(line):
        if "classdef" in stack:
            stack.append("methods")
    elif PROPERTIES_RE.match(line):
        if "classdef" in stack:
            stack.append("properties")
    elif EVENTS_RE.match(line):
        if "classdef" in stack:
            stack.append("events")
    elif ENUMERATION_RE.match(line):
        if "classdef" in stack:
            stack.append("enumeration")
    elif ARGUMENTS_RE.match(line):
        if stack and stack[-1] == "function":
            stack.append("arguments")
    elif BLOCK_OPENERS_RE.match(line):
        stack.append("block")


def base_framework_names() -> set[str]:
    names = set()
    for m in re.finditer(
        r"^\s*function\s+(?:\[[^\]]*\]\s*=\s*|[A-Za-z_][\w.]*\s*=\s*)?(?P<n>(?:get\.|set\.)?[A-Za-z_][\w.]*)\s*\(",
        BASE_CLASS.read_text(encoding="utf-8", errors="replace"),
        re.MULTILINE,
    ):
        n = m.group("n")
        names.add(n.split(".")[-1] if "." in n else n)
    return names


def classify(name: str, framework: set[str]) -> str:
    if name == "get" or name.startswith("get.") or name.startswith("set."):
        return "property_getter_setter"
    if name in BIOLOGY_CONTRACT:
        return "biology_contract"
    if name.startswith("evolveState_"):
        return "biology_substep"
    if name in INIT_CONTRACT or name.startswith("initializeState") or name.startswith("initializeConstants"):
        return "init_contract"
    if name in framework:
        return "framework_override"
    return "process_specific_helper"


def parse_process(path: Path, framework: set[str]) -> dict:
    lines = preprocess(path)
    cls = CLASSDEF_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    class_name = cls.group("name") if cls else path.stem
    stack: list[str] = []
    methods: list[dict] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].text
        if FUNCTION_RE.match(line):
            sig, end = collect_signature(lines, idx)
            name = extract_name(sig) or f"<UNPARSED@{lines[idx].no}>"
            if "classdef" in stack and "methods" in stack:
                is_ctor = name == class_name
                methods.append(
                    {
                        "name": name,
                        "line": lines[idx].no,
                        "is_constructor": is_ctor,
                        "category": "constructor" if is_ctor else classify(name, framework),
                    }
                )
            stack.append("function")
            idx = end + 1
            continue
        update_stack(stack, line)
        idx += 1
    non_ctor = [m for m in methods if not m["is_constructor"]]
    require = [m for m in non_ctor if m["category"] in REQUIRE_CATEGORIES]
    return {
        "class": class_name,
        "matlab_file": str(path.relative_to(REPO)).replace("\\", "/"),
        "method_count_excl_ctor": len(non_ctor),
        "require_oc_counterpart_count": len(require),
        "methods": methods,
    }


def build() -> dict:
    framework = base_framework_names()
    inv = {}
    for mf in sorted(PROC_DIR.glob("*.m")):
        parsed = parse_process(mf, framework)
        inv[parsed["class"]] = parsed
    totals = {"processes": len(inv)}
    for cat in (
        "biology_contract",
        "biology_substep",
        "init_contract",
        "process_specific_helper",
        "framework_override",
        "property_getter_setter",
    ):
        totals[cat] = sum(
            1 for p in inv.values() for m in p["methods"] if m.get("category") == cat
        )
    totals["require_oc_counterpart"] = sum(p["require_oc_counterpart_count"] for p in inv.values())
    totals["class_methods_excl_ctor"] = sum(p["method_count_excl_ctor"] for p in inv.values())
    return {
        "schema": "karr_process_method_inventory/1.0",
        "generated_by": "scripts/build_karr_method_inventory.py",
        "provenance": "4-parser reconciliation (2 orchestrator + Haiku + codex gpt-5.4-mini); 6 discrepancies resolved by source inspection; see script docstring.",
        "resolved_discrepancies": {
            "FtsZPolymerization.diff": "file-local fn after classdef end (L449); excluded",
            "FtsZPolymerization.jacobian": "file-local fn after classdef end (L500); excluded",
            "MacromolecularComplexation.buildProteinComplexs_montecarlokinetic": "file-local fn after classdef (L334); excluded",
            "MacromolecularComplexation.buildProteinComplexs_rates_collisionTheory": "file-local fn (L360); excluded",
            "MacromolecularComplexation.buildProteinComplexs_bounds": "file-local fn (L390); excluded",
            "Metabolism.calcGrowthRate": "real class method, multi-line signature (L1266-67); included",
        },
        "totals": totals,
        "processes": inv,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if committed JSON is stale")
    args = ap.parse_args()

    data = build()
    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not OUT_JSON.exists():
            print(f"MISSING: {OUT_JSON}")
            return 1
        current = OUT_JSON.read_text(encoding="utf-8")
        if current != rendered:
            print("DRIFT: committed karr_process_methods.json is stale; re-run generator.")
            return 1
        print("OK: inventory matches source.")
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(rendered, encoding="utf-8")
    t = data["totals"]
    print(f"Wrote {OUT_JSON.relative_to(REPO)}")
    print(f"  processes:                 {t['processes']}")
    print(f"  class methods (excl ctor): {t['class_methods_excl_ctor']}")
    print(f"  REQUIRE OC counterpart:    {t['require_oc_counterpart']}")
    print(f"    biology_contract:        {t['biology_contract']}")
    print(f"    biology_substep:         {t['biology_substep']}")
    print(f"    init_contract:           {t['init_contract']}")
    print(f"    process_specific_helper: {t['process_specific_helper']}")
    print(f"  framework_override:        {t['framework_override']}  (chassis-level)")
    print(f"  property_getter_setter:    {t['property_getter_setter']}  (exempt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
