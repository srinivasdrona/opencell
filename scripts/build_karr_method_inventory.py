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
from collections import deque
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

# ---------------------------------------------------------------------------
# Call-graph reachability -> port_requirement tier (2026-07-03).
#
# A required Karr method is a per-tick RUNTIME port only if it is reachable
# (via this.<m> / obj.<m> calls) from evolveState or calcResourceRequirements_
# Current. Methods reachable only from init/fitting roots are covered in OC via
# fixtures (their fitted outputs are baked into the knowledge base), not as
# per-process runtime ports.
#
# Roots:
#   runtime : evolveState (+ evolveState_* substeps), calcResourceRequirements_Current
#   init    : initializeState*, initializeConstants*
#   fitting : calcResourceRequirements_LifeCycle
#
# Six methods have NO in-file dot-caller (externally invoked / handle-dispatched /
# dead); each is resolved by verified source evidence in ORPHAN_OVERRIDE below.
# ---------------------------------------------------------------------------
RUNTIME_ROOT_NAMES = {"evolveState", "calcResourceRequirements_Current"}
INIT_ROOT_PREFIXES = ("initializeState", "initializeConstants")
FITTING_ROOT_NAMES = {"calcResourceRequirements_LifeCycle"}

# (class, method) -> (tier, evidence). Verified against source 2026-07-03.
ORPHAN_OVERRIDE = {
    ("Metabolism", "formulateFBA"):
        ("fitting", "no in-file caller; built by FBA.m:39/82 + FbaLPWriter.m:15 (FBA network construction)"),
    ("Transcription", "calcStateTransitionProbabilities"):
        ("fitting", "no in-file caller; called by FitConstants.m:1582 (fitting)"),
    ("ReplicationInitiation", "sampleDnaABoxes"):
        ("dead", "defined at L287; no caller anywhere in WholeCell src (dead/handle-dispatched)"),
    ("ReplicationInitiation", "calcuateIsDnaAR5Occupied"):
        ("runtime", "state query; called by SummaryLogger.m:307 + calculateIsDnaAORIComplexAssembled"),
    ("ReplicationInitiation", "calculateIsDnaAORIComplexAssembled"):
        ("runtime", "oriC-assembled state query (replication-initiation trigger)"),
    ("ReplicationInitiation", "calculateDnaABoxStatus"):
        ("runtime", "state query; called by CellState.m:187-188"),
}

_OVERRIDE_TIER_TO_PORT = {
    "runtime": "runtime_port_required",
    "fitting": "fitting_fixture_inherited",
    "dead": "uncalled_no_port",
}


def _build_callgraph(methods: list[dict], lines: list[str]) -> dict[str, set[str]]:
    names = {m["name"] for m in methods}
    by_line = sorted(methods, key=lambda m: m["line"])
    call_re = re.compile(r"(?:this|obj|p|self)\.(" + "|".join(re.escape(n) for n in names) + r")\b")
    graph: dict[str, set[str]] = {}
    for i, m in enumerate(by_line):
        s = m["line"]
        e = by_line[i + 1]["line"] if i + 1 < len(by_line) else len(lines) + 1
        body = "\n".join(lines[s:e - 1])
        graph[m["name"]] = {c for c in call_re.findall(body) if c != m["name"]}
    return graph


def _reachable(graph: dict[str, set[str]], roots: set[str], names: set[str]) -> set[str]:
    seen: set[str] = set()
    q = deque(r for r in roots if r in names)
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in graph.get(cur, ()):
            if nxt not in seen:
                q.append(nxt)
    return seen


def assign_port_requirements(cls: str, methods: list[dict], lines: list[str]) -> None:
    names = {m["name"] for m in methods}
    graph = _build_callgraph(methods, lines)
    runtime_roots = {n for n in names if n in RUNTIME_ROOT_NAMES or n.startswith("evolveState")}
    init_roots = {n for n in names if n.startswith(INIT_ROOT_PREFIXES)}
    fitting_roots = {n for n in names if n in FITTING_ROOT_NAMES}
    R = _reachable(graph, runtime_roots, names)
    I = _reachable(graph, init_roots, names)
    F = _reachable(graph, fitting_roots, names)
    for m in methods:
        n = m["name"]
        if m["is_constructor"]:
            m["port_requirement"] = "n/a_constructor"
            continue
        if m["category"] == "property_getter_setter":
            m["port_requirement"] = "exempt_accessor"
            continue
        if m["category"] == "framework_override":
            m["port_requirement"] = "chassis_level"
            continue
        key = (cls, n)
        if key in ORPHAN_OVERRIDE:
            tier, why = ORPHAN_OVERRIDE[key]
            m["port_requirement"] = _OVERRIDE_TIER_TO_PORT[tier]
            m["port_note"] = why
            continue
        if n in R:
            m["port_requirement"] = "runtime_port_required"
        elif n in init_roots or n in I:
            m["port_requirement"] = "init_fixture_or_logic"
        elif n in fitting_roots or n in F:
            m["port_requirement"] = "fitting_fixture_inherited"
        else:
            m["port_requirement"] = "needs_manual_resolution"


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
        raw_lines = mf.read_text(encoding="utf-8", errors="replace").splitlines()
        assign_port_requirements(parsed["class"], parsed["methods"], raw_lines)
        # recompute require count as RUNTIME ports only
        parsed["runtime_port_required_count"] = sum(
            1 for m in parsed["methods"] if m.get("port_requirement") == "runtime_port_required"
        )
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
    for pr in (
        "runtime_port_required",
        "init_fixture_or_logic",
        "fitting_fixture_inherited",
        "uncalled_no_port",
        "chassis_level",
        "exempt_accessor",
        "needs_manual_resolution",
    ):
        totals[pr] = sum(
            1 for p in inv.values() for m in p["methods"] if m.get("port_requirement") == pr
        )
    totals["require_oc_counterpart"] = sum(p["require_oc_counterpart_count"] for p in inv.values())
    totals["class_methods_excl_ctor"] = sum(p["method_count_excl_ctor"] for p in inv.values())
    return {
        "schema": "karr_process_method_inventory/1.1",
        "generated_by": "scripts/build_karr_method_inventory.py",
        "provenance": "4-parser reconciliation (2 orchestrator + Haiku + codex gpt-5.4-mini); 6 discrepancies resolved by source inspection; port_requirement via call-graph reachability from evolveState/calcResourceRequirements_Current vs init/fitting roots; 6 orphans resolved by source evidence (see ORPHAN_OVERRIDE).",
        "port_requirement_legend": {
            "runtime_port_required": "reachable from evolveState/calcResourceRequirements_Current; MUST have a per-process OC runtime port",
            "init_fixture_or_logic": "init method; fixture-load OK for once-at-t0 init, real logic required for per-cell-cycle init",
            "fitting_fixture_inherited": "offline fitting (FitConstants/FBA build); outputs inherited via fixtures; verify provenance once, not per-process port",
            "uncalled_no_port": "defined but never called in Karr source; no OC port required",
            "chassis_level": "framework override of base Process.m plumbing; verified once at chassis level",
            "exempt_accessor": "get.*/set.* property accessor; exempt",
            "needs_manual_resolution": "call-graph could not classify; requires manual source confirmation",
        },
        "resolved_discrepancies": {
            "FtsZPolymerization.diff": "file-local fn after classdef end (L449); excluded",
            "FtsZPolymerization.jacobian": "file-local fn after classdef end (L500); excluded",
            "MacromolecularComplexation.buildProteinComplexs_montecarlokinetic": "file-local fn after classdef (L334); excluded",
            "MacromolecularComplexation.buildProteinComplexs_rates_collisionTheory": "file-local fn (L360); excluded",
            "MacromolecularComplexation.buildProteinComplexs_bounds": "file-local fn (L390); excluded",
            "Metabolism.calcGrowthRate": "real class method, multi-line signature (L1266-67); included",
        },
        "orphan_resolutions": {f"{c}.{m}": {"tier": t, "evidence": e}
                               for (c, m), (t, e) in ORPHAN_OVERRIDE.items()},
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
    print(f"  biology-category require:  {t['require_oc_counterpart']}")
    print("  --- port_requirement (call-graph reachability) ---")
    print(f"    runtime_port_required:     {t['runtime_port_required']}   <-- true per-process OC port target")
    print(f"    init_fixture_or_logic:     {t['init_fixture_or_logic']}")
    print(f"    fitting_fixture_inherited: {t['fitting_fixture_inherited']}")
    print(f"    uncalled_no_port:          {t['uncalled_no_port']}")
    print(f"    needs_manual_resolution:   {t['needs_manual_resolution']}")
    print(f"    chassis_level:             {t['chassis_level']}  (framework overrides)")
    print(f"    exempt_accessor:           {t['exempt_accessor']}  (get/set)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
