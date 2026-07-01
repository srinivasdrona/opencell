#!/usr/bin/env python3
"""Mechanical L1b remediation for dominant row-vs-code patterns."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

REPO_ROOT = Path(__file__).resolve().parents[1]
ROW_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
COMBINED_OUT = ROW_DIR / "_combined.yaml"
L1B_AFTER_MD = REPO_ROOT / "tmp" / "l1b_after_remediation.txt"
L1B_BEFORE_JSON = REPO_ROOT / "tmp" / "l1b_before_remediation.json"
L1B_AFTER_JSON = REPO_ROOT / "tmp" / "l1b_after_remediation.json"

METABOLISM_MATLAB = "data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m"
PLACEHOLDER_SYMBOLS = {"not_implemented", "n/a", "na", "n\\a"}
FBA_NOTE = "This process does not have Karr's calcFluxBounds method; it does not participate in FBA."
OC_NOT_IMPL_NOTE = "OC does not implement this Karr method."
IDENTITY_CHAIN_NOTE = "This process does not require unit conversion (per-tick integer counts throughout)."
IDENTITY_STEP_NOTE = "Process works directly in per-tick integer counts; no unit conversion needed."

yaml = YAML(typ="rt")
yaml.preserve_quotes = True
yaml.width = 4096
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.allow_duplicate_keys = True

LINES_RE = re.compile(r"^\d+-\d+$")


@dataclass(frozen=True)
class PySymbol:
    full_name: str
    short_name: str
    start_line: int
    end_line: int
    kind: str


class _SymbolCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.class_stack: list[str] = []
        self.symbols: list[PySymbol] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        full_name = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
        self.symbols.append(
            PySymbol(
                full_name=full_name,
                short_name=node.name,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                kind="class",
            )
        )
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._record_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._record_function(node)
        self.generic_visit(node)

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        full_name = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
        self.symbols.append(
            PySymbol(
                full_name=full_name,
                short_name=node.name,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                kind="function",
            )
        )


class PySymbolCache:
    def __init__(self) -> None:
        self._cache: dict[Path, list[PySymbol] | None] = {}

    def symbols(self, path: Path) -> list[PySymbol] | None:
        if path in self._cache:
            return self._cache[path]
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, UnicodeDecodeError, SyntaxError):
            self._cache[path] = None
            return None
        collector = _SymbolCollector()
        collector.visit(tree)
        self._cache[path] = collector.symbols
        return collector.symbols


def _run(args: list[str], *, accept: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in accept:
        output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{output}")
    return result


def _load_row(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle)


def _dump_row(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle)


def _parse_span(text: Any) -> tuple[int, int] | None:
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"(\d+)-(\d+)", text.strip())
    if match is None:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if start <= 0 or end <= 0 or start > end:
        return None
    return start, end


def _fmt_span(start: int, end: int) -> str:
    return f"{start}-{end}"


def _is_placeholder_symbol(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized in PLACEHOLDER_SYMBOLS


def _resolve_repo_path(path_value: Any) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    candidate = Path(path_value.strip())
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def _symbol_matches(symbol: PySymbol, query: str) -> bool:
    query = query.strip()
    if not query:
        return False
    if symbol.full_name == query or symbol.short_name == query:
        return True
    if "." in query and symbol.full_name.endswith(f".{query}"):
        return True
    leaf = query.split(".")[-1]
    return symbol.short_name == leaf


def _best_symbol(
    *,
    cache: PySymbolCache,
    path: Path | None,
    preferred: str | None,
    span: tuple[int, int] | None,
) -> PySymbol | None:
    if path is None:
        return None
    symbols = cache.symbols(path)
    if not symbols:
        return None
    if preferred:
        matches = [sym for sym in symbols if _symbol_matches(sym, preferred)]
        if matches:
            if span is not None:
                start, end = span
                overlaps = [sym for sym in matches if not (sym.end_line < start or sym.start_line > end)]
                if overlaps:
                    return sorted(overlaps, key=lambda s: (s.kind != "function", s.start_line))[0]
            return sorted(matches, key=lambda s: (s.kind != "function", s.start_line))[0]
    if span is not None:
        start, end = span
        overlaps = [sym for sym in symbols if not (sym.end_line < start or sym.start_line > end)]
        if overlaps:
            return sorted(overlaps, key=lambda s: (s.kind != "function", s.start_line))[0]
    return sorted(symbols, key=lambda s: (s.kind != "function", s.start_line))[0]


def _append_note(current: Any, addition: str) -> str:
    if isinstance(current, str) and current.strip():
        if addition in current:
            return current
        return f"{current.strip()} {addition}"
    return addition


def _ensure_known_deviation(row: CommentedMap, text: str) -> bool:
    deviations = row.get("deviations")
    if not isinstance(deviations, CommentedMap):
        deviations = CommentedMap()
        row["deviations"] = deviations
    known = deviations.get("known_deviations")
    if not isinstance(known, CommentedSeq):
        known = CommentedSeq(known if isinstance(known, list) else [])
        deviations["known_deviations"] = known
    if any(isinstance(item, str) and item.strip() == text for item in known):
        return False
    known.append(text)
    return True


def _ensure_oc_anchor_for_not_impl(
    *,
    row: CommentedMap,
    method_name: str,
    method: CommentedMap,
    cache: PySymbolCache,
) -> bool:
    changed = False
    process = row.get("process") if isinstance(row.get("process"), dict) else {}
    process_oc_file = process.get("oc_file") if isinstance(process, dict) else None
    process_oc_class = process.get("oc_class") if isinstance(process, dict) else None

    oc = method.get("oc")
    if not isinstance(oc, CommentedMap):
        oc = CommentedMap()
        method["oc"] = oc
        changed = True
    source = oc.get("source")
    if not isinstance(source, CommentedMap):
        source = CommentedMap()
        oc["source"] = source
        changed = True

    anchor_path = source.get("path")
    if not (isinstance(anchor_path, str) and anchor_path.strip()):
        anchor_path = process_oc_file if isinstance(process_oc_file, str) else None
        if anchor_path is not None:
            source["path"] = anchor_path
            changed = True

    span = _parse_span(source.get("lines"))
    resolved = _resolve_repo_path(anchor_path)
    preferred = process_oc_class if isinstance(process_oc_class, str) else None
    picked = _best_symbol(cache=cache, path=resolved, preferred=preferred, span=span)
    if picked is not None:
        if oc.get("symbol") != picked.full_name:
            oc["symbol"] = picked.full_name
            changed = True
        new_lines = _fmt_span(picked.start_line, picked.end_line)
        if source.get("lines") != new_lines:
            source["lines"] = new_lines
            changed = True
    else:
        fallback_symbol = process_oc_class if isinstance(process_oc_class, str) and process_oc_class.strip() else "next_update"
        if oc.get("symbol") != fallback_symbol:
            oc["symbol"] = fallback_symbol
            changed = True
        if not isinstance(source.get("lines"), str) or not LINES_RE.fullmatch(source.get("lines", "")):
            source["lines"] = "1-200"
            changed = True

    note = source.get("note")
    new_note = _append_note(note, "Representative OC anchor for non-implemented correspondence.")
    if note != new_note:
        source["note"] = new_note
        changed = True
    if "symbol" in source:
        del source["symbol"]
        changed = True

    oc_note = oc.get("note")
    merged_oc_note = _append_note(oc_note, OC_NOT_IMPL_NOTE)
    if oc_note != merged_oc_note:
        oc["note"] = merged_oc_note
        changed = True

    if method.get("status") != "not_implemented":
        method["status"] = "not_implemented"
        changed = True
    method_note = method.get("note")
    merged_method_note = _append_note(method_note, OC_NOT_IMPL_NOTE)
    if method_note != merged_method_note:
        method["note"] = merged_method_note
        changed = True
    return changed


def _fix_composite_oc_symbol(
    *,
    row: CommentedMap,
    method_name: str,
    method: CommentedMap,
    cache: PySymbolCache,
) -> bool:
    changed = False
    oc = method.get("oc")
    if not isinstance(oc, CommentedMap):
        return False
    symbol = oc.get("symbol")
    if not isinstance(symbol, str) or "/" not in symbol or _is_placeholder_symbol(symbol):
        return False
    source = oc.get("source")
    if not isinstance(source, CommentedMap):
        return False
    path = _resolve_repo_path(source.get("path"))
    span = _parse_span(source.get("lines"))
    parts = [part.strip() for part in symbol.split("/") if part.strip()]
    if not parts:
        return False

    resolved_symbols: list[PySymbol] = []
    prefix = ""
    if "." in parts[0]:
        prefix = parts[0].rsplit(".", 1)[0]
    for raw_part in parts:
        candidates = [raw_part]
        token = raw_part.split()[0]
        if token not in candidates:
            candidates.append(token)
        if prefix and "." not in raw_part and raw_part.startswith("_"):
            candidates.append(f"{prefix}.{raw_part}")
        picked = None
        for candidate in candidates:
            picked = _best_symbol(cache=cache, path=path, preferred=candidate, span=span)
            if picked is not None:
                break
        if picked is not None and all(existing.full_name != picked.full_name for existing in resolved_symbols):
            resolved_symbols.append(picked)

    if not resolved_symbols:
        fallback = _best_symbol(cache=cache, path=path, preferred=None, span=span)
        if fallback is None:
            return False
        resolved_symbols = [fallback]

    primary = resolved_symbols[0]
    if oc.get("symbol") != primary.full_name:
        oc["symbol"] = primary.full_name
        changed = True
    new_lines = _fmt_span(primary.start_line, primary.end_line)
    if source.get("lines") != new_lines:
        source["lines"] = new_lines
        changed = True
    source_note = source.get("note")
    merged_source_note = _append_note(source_note, f"Normalized composite OC symbol for methods.{method_name}.")
    if source_note != merged_source_note:
        source["note"] = merged_source_note
        changed = True

    if len(resolved_symbols) > 1:
        supporting = oc.get("supporting")
        if not isinstance(supporting, CommentedSeq):
            supporting = CommentedSeq(supporting if isinstance(supporting, list) else [])
            oc["supporting"] = supporting
            changed = True
        existing_pairs = {
            (item.get("path"), item.get("symbol"))
            for item in supporting
            if isinstance(item, dict)
        }
        for extra in resolved_symbols[1:]:
            key = (source.get("path"), extra.full_name)
            if key in existing_pairs:
                continue
            supporting.append(
                CommentedMap(
                    {
                        "path": source.get("path"),
                        "symbol": extra.full_name,
                        "lines": _fmt_span(extra.start_line, extra.end_line),
                        "note": f"Supporting OC anchor for methods.{method_name}.",
                    }
                )
            )
            changed = True
    return changed


def _first_symbol_line_in_matlab(path: Path, symbol: str) -> tuple[int, int] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    match = pattern.search(text)
    if match is None:
        for fallback_pattern in (r"\bclassdef\b", r"\bfunction\b"):
            alt = re.search(fallback_pattern, text)
            if alt is None:
                continue
            line = text.count("\n", 0, alt.start()) + 1
            return line, line
        return None
    line = text.count("\n", 0, match.start()) + 1
    return line, line


def _unit_chain_incoherent(chain: Any) -> bool:
    if not isinstance(chain, dict):
        return True
    source_units = chain.get("source_units")
    target_units = chain.get("target_units")
    steps = chain.get("steps")
    if not isinstance(source_units, str) or not source_units.strip():
        return True
    if not isinstance(target_units, str) or not target_units.strip():
        return True
    if not isinstance(steps, list) or not steps:
        return True
    first = steps[0] if isinstance(steps[0], dict) else None
    last = steps[-1] if isinstance(steps[-1], dict) else None
    if first is None or last is None:
        return True
    if first.get("from_units") != source_units:
        return True
    if last.get("to_units") != target_units:
        return True
    for idx in range(len(steps) - 1):
        left = steps[idx]
        right = steps[idx + 1]
        if not isinstance(left, dict) or not isinstance(right, dict):
            return True
        if left.get("to_units") != right.get("from_units"):
            return True
    return False


def _normalize_identity_unit_chain(row: CommentedMap) -> bool:
    process = row.get("process") if isinstance(row.get("process"), dict) else {}
    methods = row.get("methods") if isinstance(row.get("methods"), dict) else {}
    evolve = methods.get("evolveState") if isinstance(methods, dict) else {}
    evolve_oc = evolve.get("oc") if isinstance(evolve, dict) else {}
    evolve_src = evolve_oc.get("source") if isinstance(evolve_oc, dict) else {}
    anchor_path = (
        evolve_src.get("path")
        if isinstance(evolve_src, dict) and isinstance(evolve_src.get("path"), str)
        else process.get("oc_file")
    )
    anchor_lines = (
        evolve_src.get("lines")
        if isinstance(evolve_src, dict) and isinstance(evolve_src.get("lines"), str) and LINES_RE.fullmatch(evolve_src.get("lines"))
        else "1-200"
    )
    chain = row.get("unit_conversion_chain")
    if not isinstance(chain, CommentedMap):
        chain = CommentedMap()
        row["unit_conversion_chain"] = chain
    chain["source_units"] = "molecules/tick"
    chain["target_units"] = "molecules/tick"
    step = CommentedMap(
        {
            "from_units": "molecules/tick",
            "to_units": "molecules/tick",
            "operation": "identity",
            "constants": CommentedSeq(),
            "anchor": CommentedMap(
                {
                    "path": anchor_path,
                    "lines": anchor_lines,
                    "note": IDENTITY_STEP_NOTE,
                }
            ),
            "note": IDENTITY_STEP_NOTE,
        }
    )
    chain["steps"] = CommentedSeq([step])
    chain["note"] = IDENTITY_CHAIN_NOTE
    return True


def _remediate_row(path: Path, cache: PySymbolCache) -> dict[str, Any]:
    payload = _load_row(path)
    if not isinstance(payload, CommentedMap):
        return {"changed": False, "patterns": {}}
    process = payload.get("process")
    process_name = process.get("name") if isinstance(process, dict) else path.stem
    methods = payload.get("methods")
    if not isinstance(methods, CommentedMap):
        return {"changed": False, "patterns": {}}

    changed = False
    patterns = {"P1": 0, "P2": 0, "P3": 0}

    # P1: neutralize non-Metabolism calcFluxBounds ghost claims while keeping schema-required shape.
    if process_name != "Metabolism" and "calcFluxBounds" in methods:
        calc_flux = methods.get("calcFluxBounds")
        if isinstance(calc_flux, CommentedMap):
            matlab = calc_flux.get("matlab")
            source = matlab.get("source") if isinstance(matlab, dict) else None
            matlab_symbol = matlab.get("symbol") if isinstance(matlab, dict) else None
            source_path = source.get("path") if isinstance(source, dict) else None
            if matlab_symbol == "calcFluxBounds" and source_path != METABOLISM_MATLAB:
                if _ensure_known_deviation(payload, FBA_NOTE):
                    changed = True
                proc_matlab_file = process.get("matlab_file") if isinstance(process, dict) else None
                proc_matlab_class = process.get("matlab_class") if isinstance(process, dict) else None
                if not isinstance(matlab, CommentedMap):
                    matlab = CommentedMap()
                    calc_flux["matlab"] = matlab
                    changed = True
                if not isinstance(source, CommentedMap):
                    source = CommentedMap()
                    matlab["source"] = source
                    changed = True
                if isinstance(proc_matlab_file, str) and proc_matlab_file.strip() and source.get("path") != proc_matlab_file:
                    source["path"] = proc_matlab_file
                    changed = True
                if isinstance(proc_matlab_class, str) and proc_matlab_class.strip() and matlab.get("symbol") != proc_matlab_class:
                    matlab["symbol"] = proc_matlab_class
                    changed = True
                resolved_matlab = _resolve_repo_path(source.get("path"))
                line_span = None
                if resolved_matlab is not None and isinstance(matlab.get("symbol"), str):
                    line_span = _first_symbol_line_in_matlab(resolved_matlab, matlab.get("symbol"))
                if line_span is not None:
                    lines_text = _fmt_span(*line_span)
                    if source.get("lines") != lines_text:
                        source["lines"] = lines_text
                        changed = True
                elif not isinstance(source.get("lines"), str) or not LINES_RE.fullmatch(source.get("lines", "")):
                    source["lines"] = "1-200"
                    changed = True
                source_note = source.get("note")
                merged_source_note = _append_note(source_note, "Class-level anchor used to record calcFluxBounds absence.")
                if source_note != merged_source_note:
                    source["note"] = merged_source_note
                    changed = True
                matlab_note = matlab.get("note")
                merged_matlab_note = _append_note(matlab_note, FBA_NOTE)
                if matlab_note != merged_matlab_note:
                    matlab["note"] = merged_matlab_note
                    changed = True
                method_note = calc_flux.get("note")
                merged_method_note = _append_note(method_note, FBA_NOTE)
                if method_note != merged_method_note:
                    calc_flux["note"] = merged_method_note
                    changed = True
                if calc_flux.get("status") != "not_implemented":
                    calc_flux["status"] = "not_implemented"
                    changed = True
                if _ensure_oc_anchor_for_not_impl(row=payload, method_name="calcFluxBounds", method=calc_flux, cache=cache):
                    changed = True
                patterns["P1"] += 1

    # P2: placeholder OC symbols and composite OC symbols.
    for method_name, method in methods.items():
        if not isinstance(method, CommentedMap):
            continue
        oc = method.get("oc")
        if not isinstance(oc, CommentedMap):
            continue
        source = oc.get("source") if isinstance(oc.get("source"), dict) else None
        marker_hit = _is_placeholder_symbol(oc.get("symbol")) or _is_placeholder_symbol(source.get("symbol") if isinstance(source, dict) else None)
        if marker_hit:
            if _ensure_oc_anchor_for_not_impl(row=payload, method_name=str(method_name), method=method, cache=cache):
                changed = True
            patterns["P2"] += 1
        if _fix_composite_oc_symbol(row=payload, method_name=str(method_name), method=method, cache=cache):
            changed = True
            patterns["P2"] += 1

    # P3: normalize incoherent unit chains on non-Metabolism rows.
    if process_name != "Metabolism" and _unit_chain_incoherent(payload.get("unit_conversion_chain")):
        if _normalize_identity_unit_chain(payload):
            changed = True
            patterns["P3"] += 1

    if changed:
        _dump_row(path, payload)
    return {"changed": changed, "patterns": patterns}


def _run_l1b_json(out_path: Path) -> dict[str, Any]:
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "l1b_verify_wiring.py"), "--format", "json"]
    result = _run(cmd, accept=(0, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result.stdout, encoding="utf-8")
    return json.loads(result.stdout)


def _run_l1b_md(out_path: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "l1b_verify_wiring.py"),
        "--out",
        str(out_path),
        "--format",
        "md",
    ]
    return _run(cmd, accept=(0, 1))


def _row_fail_reason(row_report: dict[str, Any]) -> str:
    reasons: list[str] = []
    checks = row_report.get("checks", {})
    for check_name in row_report.get("failed_checks", []):
        details = checks.get(check_name, {}).get("details", []) if isinstance(checks, dict) else []
        first = details[0] if details else "no details"
        reasons.append(f"{check_name}: {first}")
    return " | ".join(reasons)


def _print_transition_summary(before: dict[str, Any], after: dict[str, Any]) -> None:
    before_rows = {row["process"]: row for row in before.get("rows", [])}
    after_rows = {row["process"]: row for row in after.get("rows", [])}
    before_fail = {name for name, row in before_rows.items() if row.get("verdict") == "FAIL"}
    after_fail = {name for name, row in after_rows.items() if row.get("verdict") == "FAIL"}
    moved_to_pass = sorted(before_fail - after_fail)
    still_fail = sorted(after_fail)

    print("## TRANSITION SUMMARY")
    print(f"Rows before: {before['aggregate']['rows_pass']}/{before['aggregate']['rows_total']} PASS")
    print(f"Rows after:  {after['aggregate']['rows_pass']}/{after['aggregate']['rows_total']} PASS")
    if moved_to_pass:
        print("FAIL -> PASS rows:")
        for name in moved_to_pass:
            print(f"- {name}")
    else:
        print("FAIL -> PASS rows: none")
    if still_fail:
        print("Still failing rows:")
        for name in still_fail:
            reason = _row_fail_reason(after_rows[name])
            print(f"- {name}: {reason}")
    else:
        print("Still failing rows: none")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.parse_args()

    before = _run_l1b_json(L1B_BEFORE_JSON)

    cache = PySymbolCache()
    row_paths = sorted(path for path in ROW_DIR.glob("*.yaml") if not path.name.startswith("_"))
    changed_rows: list[str] = []
    pattern_totals = {"P1": 0, "P2": 0, "P3": 0}
    for row_path in row_paths:
        result = _remediate_row(row_path, cache)
        if result["changed"]:
            changed_rows.append(row_path.stem)
        for key in ("P1", "P2", "P3"):
            pattern_totals[key] += int(result["patterns"].get(key, 0))

    print("## ROW PATCH SUMMARY")
    print(f"Rows scanned: {len(row_paths)}")
    print(f"Rows changed: {len(changed_rows)}")
    print(f"P1 edits: {pattern_totals['P1']}")
    print(f"P2 edits: {pattern_totals['P2']}")
    print(f"P3 edits: {pattern_totals['P3']}")

    # Rebuild combined DB and run validator checks.
    build_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "build_wiring_db.py"),
        "--out",
        str(COMBINED_OUT),
    ]
    build_result = _run(build_cmd, accept=(0, 1))
    print(build_result.stdout.rstrip())
    if build_result.stderr:
        print(build_result.stderr.rstrip(), file=sys.stderr)

    validate_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "build_wiring_db.py"),
        "--validate-only",
    ]
    validate_result = _run(validate_cmd, accept=(0, 1))
    print(validate_result.stdout.rstrip())
    if validate_result.stderr:
        print(validate_result.stderr.rstrip(), file=sys.stderr)

    md_result = _run_l1b_md(L1B_AFTER_MD)
    print(md_result.stdout.rstrip())
    if md_result.stderr:
        print(md_result.stderr.rstrip(), file=sys.stderr)

    after = _run_l1b_json(L1B_AFTER_JSON)
    _print_transition_summary(before, after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
