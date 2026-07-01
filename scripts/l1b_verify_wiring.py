#!/usr/bin/env python3
"""L1b row-vs-code wiring conformance gate for per-process wiring DB rows."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WIRING_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
DEFAULT_PROCESS_SCHEMA_DIR = REPO_ROOT / "data" / "schemas" / "per_process"
WIRING_DIR_ENV = "OC_L1B_WIRING_DIR"
PROCESS_SCHEMA_DIR_ENV = "OC_L1B_PROCESS_SCHEMA_DIR"

CHECK_ORDER = (
    "check_matlab_anchors_resolve",
    "check_oc_anchors_resolve",
    "check_consume_produce_wids_in_schema_toml",
    "check_allocator_requests_wids_in_schema_toml",
    "check_unit_conversion_chain_coherent",
    "check_ordering_constraints_reference_valid_processes",
    "check_deviations_reference_valid_anchors",
)

FILE_REF_RE = re.compile(r"([A-Za-z0-9_./+\-@]+?\.(?:py|m))")


class CheckResult(TypedDict):
    verdict: str
    details: list[str]


@dataclass(frozen=True)
class AnchorRef:
    label: str
    path: str
    symbol: str
    lines: str


@dataclass(frozen=True)
class SymbolOccurrence:
    full_name: str
    short_name: str
    start_line: int
    end_line: int


class _SymbolCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.class_stack: list[str] = []
        self.occurrences: list[SymbolOccurrence] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        full_name = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
        self.occurrences.append(
            SymbolOccurrence(
                full_name=full_name,
                short_name=node.name,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
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
        self.occurrences.append(
            SymbolOccurrence(
                full_name=full_name,
                short_name=node.name,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
            )
        )


class FileCache:
    def __init__(self) -> None:
        self._text: dict[Path, str] = {}
        self._lines: dict[Path, list[str]] = {}
        self._ast_tree: dict[Path, ast.AST] = {}
        self._ast_error: dict[Path, str] = {}
        self._symbols: dict[Path, list[SymbolOccurrence]] = {}

    def text(self, path: Path) -> str:
        if path not in self._text:
            self._text[path] = path.read_text(encoding="utf-8")
        return self._text[path]

    def lines(self, path: Path) -> list[str]:
        if path not in self._lines:
            self._lines[path] = self.text(path).splitlines()
        return self._lines[path]

    def symbols(self, path: Path) -> tuple[list[SymbolOccurrence] | None, str | None]:
        if path in self._symbols:
            return self._symbols[path], None
        if path in self._ast_error:
            return None, self._ast_error[path]

        try:
            source_text = self.text(path)
            tree = ast.parse(source_text)
            self._ast_tree[path] = tree
        except SyntaxError as exc:
            self._ast_error[path] = f"ast.parse failed: {exc.msg} at line {exc.lineno}"
            return None, self._ast_error[path]

        collector = _SymbolCollector()
        collector.visit(self._ast_tree[path])
        self._symbols[path] = collector.occurrences
        return self._symbols[path], None


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _process_name(row: dict[str, Any], fallback: str) -> str:
    process = row.get("process")
    if isinstance(process, dict):
        name = process.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return fallback


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _resolve_anchor_path(anchor_path: str, repo_root: Path) -> Path:
    as_path = Path(anchor_path)
    if as_path.is_absolute():
        return as_path
    return repo_root / as_path


def _parse_line_span(lines: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d+)-(\d+)", str(lines).strip())
    if match is None:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if start <= 0 or end <= 0:
        return None
    if start > end:
        return None
    return start, end


def _symbol_leaf(symbol: str) -> str:
    parts = [item for item in symbol.split(".") if item]
    return parts[-1] if parts else symbol


def _symbol_exists_anywhere(text: str, symbol: str) -> bool:
    if symbol in text:
        return True
    leaf = _symbol_leaf(symbol)
    if leaf and re.search(rf"\b{re.escape(leaf)}\b", text):
        return True
    if "." in symbol:
        parts = [part for part in symbol.split(".") if part]
        if parts and all(re.search(rf"\b{re.escape(part)}\b", text) for part in parts):
            return True
    return False


def _symbol_exists_in_window(window_text: str, symbol: str, *, include_python_defs: bool) -> bool:
    leaf = _symbol_leaf(symbol)
    candidates = [item for item in {symbol, leaf} if item]
    patterns: list[str] = []
    for candidate in candidates:
        patterns.extend(
            [
                rf"\bfunction\b[^\n]*\b{re.escape(candidate)}\b",
                rf"\bclassdef\b[^\n]*\b{re.escape(candidate)}\b",
                rf"\b{re.escape(candidate)}\b\s*=",
            ]
        )
        if include_python_defs:
            patterns.extend(
                [
                    rf"\bdef\s+{re.escape(candidate)}\b",
                    rf"\bclass\s+{re.escape(candidate)}\b",
                ]
            )

    for pattern in patterns:
        if re.search(pattern, window_text):
            return True

    return any(candidate in window_text for candidate in candidates)


def _overlaps_window(start: int, end: int, window_start: int, window_end: int) -> bool:
    return not (end < window_start or start > window_end)


def _ast_symbol_in_range(
    *,
    symbol: str,
    occurrences: list[SymbolOccurrence],
    start_line: int,
    end_line: int,
) -> bool:
    window_start = max(1, start_line - 5)
    window_end = end_line + 5

    if "." in symbol:
        matched = [
            item
            for item in occurrences
            if item.full_name == symbol or item.full_name.endswith(f".{symbol}")
        ]
        if not matched:
            leaf = _symbol_leaf(symbol)
            matched = [item for item in occurrences if item.short_name == leaf]
    else:
        matched = [item for item in occurrences if item.short_name == symbol or item.full_name == symbol]

    return any(_overlaps_window(item.start_line, item.end_line, window_start, window_end) for item in matched)


def _anchor_from_mapping(mapping: Any, label: str, symbol_override: str | None = None) -> AnchorRef | None:
    if not isinstance(mapping, dict):
        return None
    path = mapping.get("path")
    symbol = symbol_override if symbol_override is not None else mapping.get("symbol")
    lines = mapping.get("lines")
    if not isinstance(path, str) or not path.strip():
        return None
    if not isinstance(symbol, str) or not symbol.strip():
        return None
    if not isinstance(lines, str) or not lines.strip():
        return None
    return AnchorRef(label=label, path=path.strip(), symbol=symbol.strip(), lines=lines.strip())


def _collect_matlab_anchors(row: dict[str, Any]) -> list[AnchorRef]:
    anchors: list[AnchorRef] = []

    methods = row.get("methods")
    if isinstance(methods, dict):
        for method_name, binding in methods.items():
            if not isinstance(binding, dict):
                continue
            matlab_block = binding.get("matlab")
            if isinstance(matlab_block, dict):
                anchor = _anchor_from_mapping(
                    matlab_block.get("source"),
                    f"methods.{method_name}.matlab.source",
                    matlab_block.get("symbol") if isinstance(matlab_block.get("symbol"), str) else None,
                )
                if anchor is not None:
                    anchors.append(anchor)

    for list_key in ("consume_stoichiometry", "produce_stoichiometry"):
        entries = row.get(list_key)
        if not isinstance(entries, list):
            continue
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            anchor = _anchor_from_mapping(entry.get("matlab_anchor"), f"{list_key}[{idx}].matlab_anchor")
            if anchor is not None:
                anchors.append(anchor)

    source_anchors = row.get("source_anchors")
    if isinstance(source_anchors, dict):
        matlab_blocks = source_anchors.get("matlab_blocks")
        if isinstance(matlab_blocks, dict):
            for block_name, anchor_block in matlab_blocks.items():
                anchor = _anchor_from_mapping(
                    anchor_block,
                    f"source_anchors.matlab_blocks.{block_name}",
                )
                if anchor is not None:
                    anchors.append(anchor)

    deviations = row.get("deviations")
    if isinstance(deviations, dict):
        lp_source = deviations.get("lp_bounds_source")
        if isinstance(lp_source, dict):
            anchor = _anchor_from_mapping(
                lp_source.get("matlab_anchor"),
                "deviations.lp_bounds_source.matlab_anchor",
            )
            if anchor is not None:
                anchors.append(anchor)

    unit_chain = row.get("unit_conversion_chain")
    if isinstance(unit_chain, dict):
        steps = unit_chain.get("steps")
        if isinstance(steps, list):
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                anchor = _anchor_from_mapping(step.get("anchor"), f"unit_conversion_chain.steps[{idx}].anchor")
                if anchor is not None:
                    anchors.append(anchor)

    return anchors


def _collect_oc_anchors(row: dict[str, Any]) -> list[AnchorRef]:
    anchors: list[AnchorRef] = []

    methods = row.get("methods")
    if isinstance(methods, dict):
        for method_name, binding in methods.items():
            if not isinstance(binding, dict):
                continue
            oc_block = binding.get("oc")
            if isinstance(oc_block, dict):
                anchor = _anchor_from_mapping(
                    oc_block.get("source"),
                    f"methods.{method_name}.oc.source",
                    oc_block.get("symbol") if isinstance(oc_block.get("symbol"), str) else None,
                )
                if anchor is not None:
                    anchors.append(anchor)

                supporting = oc_block.get("supporting")
                if isinstance(supporting, list):
                    for idx, support_anchor in enumerate(supporting):
                        anchor = _anchor_from_mapping(
                            support_anchor,
                            f"methods.{method_name}.oc.supporting[{idx}]",
                        )
                        if anchor is not None:
                            anchors.append(anchor)

    for list_key in ("consume_stoichiometry", "produce_stoichiometry"):
        entries = row.get(list_key)
        if not isinstance(entries, list):
            continue
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            anchor = _anchor_from_mapping(entry.get("oc_anchor"), f"{list_key}[{idx}].oc_anchor")
            if anchor is not None:
                anchors.append(anchor)

    source_anchors = row.get("source_anchors")
    if isinstance(source_anchors, dict):
        oc_blocks = source_anchors.get("oc_blocks")
        if isinstance(oc_blocks, dict):
            for block_name, anchor_block in oc_blocks.items():
                anchor = _anchor_from_mapping(
                    anchor_block,
                    f"source_anchors.oc_blocks.{block_name}",
                )
                if anchor is not None:
                    anchors.append(anchor)

    deviations = row.get("deviations")
    if isinstance(deviations, dict):
        lp_source = deviations.get("lp_bounds_source")
        if isinstance(lp_source, dict):
            anchor = _anchor_from_mapping(
                lp_source.get("oc_anchor"),
                "deviations.lp_bounds_source.oc_anchor",
            )
            if anchor is not None:
                anchors.append(anchor)

    return anchors


def _validate_anchor_refs(
    *,
    anchor_refs: list[AnchorRef],
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    require_ast_for_python: bool,
    allow_source_block_line_fallback: bool,
) -> CheckResult:
    failures: list[str] = []
    warnings: list[str] = []

    for anchor in anchor_refs:
        resolved = _resolve_anchor_path(anchor.path, repo_root)
        if not resolved.exists():
            failures.append(f"{anchor.label}: missing file {anchor.path}")
            continue

        try:
            text = cache.text(resolved)
        except Exception as exc:
            failures.append(f"{anchor.label}: could not read file {anchor.path}: {exc}")
            continue

        if strict_anchors:
            span = _parse_line_span(anchor.lines)
            if span is None:
                failures.append(f"{anchor.label}: invalid lines span {anchor.lines!r}")
            else:
                lines = cache.lines(resolved)
                window_start = max(1, span[0] - 5)
                window_end = min(len(lines), span[1] + 5)
                if window_start > window_end:
                    failures.append(
                        f"{anchor.label}: anchor line window empty for lines {anchor.lines!r}"
                    )
                else:
                    window_text = "\n".join(lines[window_start - 1 : window_end])
                    include_python_defs = resolved.suffix.lower() == ".py"
                    if not _symbol_exists_in_window(
                        window_text,
                        anchor.symbol,
                        include_python_defs=include_python_defs,
                    ):
                        failures.append(
                            f"{anchor.label}: symbol {anchor.symbol!r} not found near lines {anchor.lines} in {anchor.path}"
                        )
        elif not _symbol_exists_anywhere(text, anchor.symbol):
            if allow_source_block_line_fallback and anchor.label.startswith("source_anchors.matlab_blocks."):
                span = _parse_line_span(anchor.lines)
                lines = cache.lines(resolved)
                if span is not None and span[0] <= len(lines):
                    warnings.append(
                        f"WARN: {anchor.label} used line-span fallback because symbol {anchor.symbol!r} was not found"
                    )
                else:
                    failures.append(
                        f"{anchor.label}: symbol {anchor.symbol!r} not found in file {anchor.path}"
                    )
            else:
                failures.append(
                    f"{anchor.label}: symbol {anchor.symbol!r} not found in file {anchor.path}"
                )

        if require_ast_for_python and resolved.suffix.lower() == ".py":
            span = _parse_line_span(anchor.lines)
            if span is None:
                failures.append(
                    f"{anchor.label}: cannot AST-validate symbol {anchor.symbol!r} due to invalid lines {anchor.lines!r}"
                )
                continue

            occurrences, ast_error = cache.symbols(resolved)
            if ast_error is not None:
                failures.append(f"{anchor.label}: {ast_error}")
                continue
            if occurrences is None:
                failures.append(f"{anchor.label}: AST symbol table unavailable for {anchor.path}")
                continue

            if not _ast_symbol_in_range(
                symbol=anchor.symbol,
                occurrences=occurrences,
                start_line=span[0],
                end_line=span[1],
            ):
                failures.append(
                    f"{anchor.label}: AST symbol {anchor.symbol!r} not found in line window {anchor.lines} ±5 in {anchor.path}"
                )

    if failures:
        return CheckResult(verdict="FAIL", details=[*failures, *warnings])
    return CheckResult(verdict="PASS", details=[f"validated {len(anchor_refs)} anchors", *warnings])


def check_matlab_anchors_resolve(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
) -> CheckResult:
    del roster
    del process_schema_dir
    anchors = _collect_matlab_anchors(row)
    return _validate_anchor_refs(
        anchor_refs=anchors,
        strict_anchors=strict_anchors,
        repo_root=repo_root,
        cache=cache,
        require_ast_for_python=False,
        allow_source_block_line_fallback=True,
    )


def check_oc_anchors_resolve(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
) -> CheckResult:
    del roster
    del process_schema_dir
    anchors = _collect_oc_anchors(row)
    return _validate_anchor_refs(
        anchor_refs=anchors,
        strict_anchors=strict_anchors,
        repo_root=repo_root,
        cache=cache,
        require_ast_for_python=True,
        allow_source_block_line_fallback=False,
    )


def _resolve_process_schema_toml(process_name: str, process_schema_dir: Path) -> Path | None:
    wanted = _normalize_name(process_name)
    matches = [path for path in sorted(process_schema_dir.glob("*.toml")) if _normalize_name(path.stem) == wanted]
    if len(matches) == 1:
        return matches[0]

    fallback_name = re.sub(r"(?<!^)(?=[A-Z])", "_", process_name).replace("-", "_").lower()
    fallback = process_schema_dir / f"{fallback_name}.toml"
    if fallback.exists():
        return fallback
    return None


def _load_state_groups(toml_path: Path) -> tuple[dict[str, set[str]] | None, str | None]:
    try:
        payload = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return None, f"could not parse {toml_path.name}: {exc}"

    state_groups = payload.get("state_groups")
    if not isinstance(state_groups, dict):
        return None, f"{toml_path.name}: missing [state_groups] table"

    groups: dict[str, set[str]] = {}
    for group_name, members in state_groups.items():
        if isinstance(members, list):
            groups[group_name] = {item for item in members if isinstance(item, str)}
    return groups, None


def _wid_check(
    *,
    row: dict[str, Any],
    process_schema_dir: Path,
    wid_iterables: list[Any],
) -> CheckResult:
    process_name = _process_name(row, "unknown")
    toml_path = _resolve_process_schema_toml(process_name, process_schema_dir)
    if toml_path is None:
        return CheckResult(
            verdict="FAIL",
            details=[
                f"missing process schema TOML for {process_name} under {process_schema_dir}"
            ],
        )

    groups, error = _load_state_groups(toml_path)
    if error is not None or groups is None:
        return CheckResult(verdict="FAIL", details=[error or "unknown TOML load error"])

    union_wids: set[str] = set().union(*groups.values()) if groups else set()
    substrate_wids = groups.get("substrates", set())

    target_wids: set[str] = set()
    for entries in wid_iterables:
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                wid = entry.get("wid")
                if isinstance(wid, str) and wid.strip():
                    target_wids.add(wid.strip())
                elif wid is not None:
                    target_wids.add(str(wid))

    failures: list[str] = []
    warnings: list[str] = []
    for wid in sorted(target_wids):
        if wid not in union_wids:
            failures.append(f"WID {wid!r} not found in {toml_path.name} [state_groups.*]")
            continue
        if wid not in substrate_wids:
            present_groups = sorted(group_name for group_name, group in groups.items() if wid in group)
            warnings.append(
                f"WARN: WID {wid!r} present in {toml_path.name} groups {present_groups}, not in substrates"
            )

    details: list[str] = [f"resolved schema TOML {toml_path.name}", *warnings]
    if failures:
        return CheckResult(verdict="FAIL", details=[*failures, *warnings])
    return CheckResult(verdict="PASS", details=details)


def check_consume_produce_wids_in_schema_toml(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    return _wid_check(
        row=row,
        process_schema_dir=process_schema_dir,
        wid_iterables=[
            row.get("consume_stoichiometry", []),
            row.get("produce_stoichiometry", []),
        ],
    )


def check_allocator_requests_wids_in_schema_toml(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    allocator = row.get("allocator")
    requests: Any = []
    bypasses: Any = []
    if isinstance(allocator, dict):
        requests = allocator.get("requests", [])
        bypasses = allocator.get("bypasses", [])
    return _wid_check(
        row=row,
        process_schema_dir=process_schema_dir,
        wid_iterables=[requests, bypasses],
    )


def check_unit_conversion_chain_coherent(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    del process_schema_dir

    chain = row.get("unit_conversion_chain")
    if not isinstance(chain, dict):
        return CheckResult(verdict="FAIL", details=["unit_conversion_chain missing or not a mapping"])

    source_units = chain.get("source_units")
    target_units = chain.get("target_units")
    steps = chain.get("steps")
    if not isinstance(source_units, str) or not source_units.strip():
        return CheckResult(verdict="FAIL", details=["unit_conversion_chain.source_units missing/invalid"])
    if not isinstance(target_units, str) or not target_units.strip():
        return CheckResult(verdict="FAIL", details=["unit_conversion_chain.target_units missing/invalid"])
    if not isinstance(steps, list) or not steps:
        return CheckResult(verdict="FAIL", details=["unit_conversion_chain.steps missing/empty"])

    failures: list[str] = []

    first_step = steps[0] if isinstance(steps[0], dict) else None
    last_step = steps[-1] if isinstance(steps[-1], dict) else None
    if first_step is None or last_step is None:
        failures.append("unit_conversion_chain.steps contains non-mapping entries")
    else:
        if first_step.get("from_units") != source_units:
            failures.append(
                "unit_conversion_chain.steps[0].from_units does not match unit_conversion_chain.source_units"
            )
        if last_step.get("to_units") != target_units:
            failures.append(
                "unit_conversion_chain.steps[-1].to_units does not match unit_conversion_chain.target_units"
            )

    for idx in range(len(steps) - 1):
        left = steps[idx]
        right = steps[idx + 1]
        if not isinstance(left, dict) or not isinstance(right, dict):
            failures.append(f"unit_conversion_chain.steps[{idx}] or steps[{idx + 1}] not a mapping")
            continue
        left_to = left.get("to_units")
        right_from = right.get("from_units")
        if left_to != right_from:
            failures.append(
                f"unit_conversion_chain break at steps[{idx}] -> steps[{idx + 1}]: {left_to!r} != {right_from!r}"
            )

    if failures:
        return CheckResult(verdict="FAIL", details=failures)
    return CheckResult(verdict="PASS", details=[f"validated {len(steps)} conversion steps"])


def check_ordering_constraints_reference_valid_processes(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del process_schema_dir

    ordering = row.get("ordering_constraints")
    if not isinstance(ordering, dict):
        return CheckResult(verdict="FAIL", details=["ordering_constraints missing or not a mapping"])

    unknown: list[str] = []
    for key in ("hard_before", "hard_after", "soft_before", "soft_after"):
        values = ordering.get(key)
        if not isinstance(values, list):
            unknown.append(f"ordering_constraints.{key} missing/not a list")
            continue
        for value in values:
            if not isinstance(value, str) or not value.strip():
                unknown.append(f"ordering_constraints.{key} contains invalid process name {value!r}")
                continue
            if value not in roster:
                unknown.append(f"ordering_constraints.{key} references unknown process {value!r}")

    if unknown:
        return CheckResult(verdict="FAIL", details=unknown)

    total_refs = sum(
        len(ordering[key])
        for key in ("hard_before", "hard_after", "soft_before", "soft_after")
        if isinstance(ordering.get(key), list)
    )
    return CheckResult(verdict="PASS", details=[f"validated {total_refs} ordering partner references"])


def check_deviations_reference_valid_anchors(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
) -> CheckResult:
    del strict_anchors
    del cache
    del roster
    del process_schema_dir

    warnings: list[str] = []
    deviations = row.get("deviations")
    if not isinstance(deviations, dict):
        return CheckResult(
            verdict="PASS",
            details=["WARN: deviations missing or not a mapping"],
        )

    known_deviations = deviations.get("known_deviations")
    if isinstance(known_deviations, list):
        for idx, item in enumerate(known_deviations):
            if not isinstance(item, str):
                continue
            for match in FILE_REF_RE.findall(item):
                resolved = _resolve_anchor_path(match, repo_root)
                if not resolved.exists():
                    warnings.append(
                        f"WARN: deviations.known_deviations[{idx}] references missing file {match}"
                    )

    lp_source = deviations.get("lp_bounds_source")
    if not isinstance(lp_source, dict):
        warnings.append("WARN: deviations.lp_bounds_source missing or not a mapping")
    else:
        if "matlab_anchor" not in lp_source:
            warnings.append("WARN: deviations.lp_bounds_source.matlab_anchor missing")
        if "oc_anchor" not in lp_source:
            warnings.append("WARN: deviations.lp_bounds_source.oc_anchor missing")

    if warnings:
        return CheckResult(verdict="PASS", details=warnings)
    return CheckResult(verdict="PASS", details=["no deviation reference warnings"])


CHECK_FUNCTIONS = {
    "check_matlab_anchors_resolve": check_matlab_anchors_resolve,
    "check_oc_anchors_resolve": check_oc_anchors_resolve,
    "check_consume_produce_wids_in_schema_toml": check_consume_produce_wids_in_schema_toml,
    "check_allocator_requests_wids_in_schema_toml": check_allocator_requests_wids_in_schema_toml,
    "check_unit_conversion_chain_coherent": check_unit_conversion_chain_coherent,
    "check_ordering_constraints_reference_valid_processes": check_ordering_constraints_reference_valid_processes,
    "check_deviations_reference_valid_anchors": check_deviations_reference_valid_anchors,
}


def _build_row_report(
    *,
    row: dict[str, Any],
    row_file: Path,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
) -> dict[str, Any]:
    process_name = _process_name(row, row_file.stem)
    checks: dict[str, CheckResult] = {}
    failed_checks: list[str] = []
    warning_details: list[str] = []

    for check_name in CHECK_ORDER:
        result = CHECK_FUNCTIONS[check_name](
            row,
            strict_anchors=strict_anchors,
            repo_root=repo_root,
            cache=cache,
            roster=roster,
            process_schema_dir=process_schema_dir,
        )
        checks[check_name] = result
        if result["verdict"] == "FAIL":
            failed_checks.append(check_name)
        warning_details.extend([item for item in result["details"] if item.startswith("WARN:")])

    verdict = "PASS" if not failed_checks else "FAIL"
    return {
        "process": process_name,
        "file": row_file.name,
        "verdict": verdict,
        "failed_checks": failed_checks,
        "warning_count": len(warning_details),
        "warnings": warning_details,
        "checks": checks,
    }


def _discover_rows(wiring_dir: Path) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    load_failures: list[str] = []
    for row_path in sorted(path for path in wiring_dir.glob("*.yaml") if not path.name.startswith("_")):
        try:
            payload = _load_yaml(row_path)
        except Exception as exc:  # pragma: no cover - exercised through integration CLI test
            load_failures.append(f"{row_path.name}: YAML parse failure: {exc}")
            continue
        if not isinstance(payload, dict):
            load_failures.append(f"{row_path.name}: YAML did not parse to mapping")
            continue
        rows.append((row_path, payload))
    rows.sort(key=lambda item: _process_name(item[1], item[0].stem))
    return rows, load_failures


def _build_report(
    *,
    wiring_dir: Path,
    process_schema_dir: Path,
    schema_contract: dict[str, Any],
    process_filter: str | None,
    strict_anchors: bool,
) -> dict[str, Any]:
    del schema_contract

    rows, load_failures = _discover_rows(wiring_dir)
    roster = {_process_name(payload, row_path.stem) for row_path, payload in rows}

    selected_rows = rows
    if process_filter is not None:
        selected_rows = [
            (row_path, payload)
            for row_path, payload in rows
            if _process_name(payload, row_path.stem) == process_filter
        ]

    row_reports: list[dict[str, Any]] = []
    cache = FileCache()
    for row_path, row_payload in selected_rows:
        row_reports.append(
            _build_row_report(
                row=row_payload,
                row_file=row_path,
                strict_anchors=strict_anchors,
                repo_root=REPO_ROOT,
                cache=cache,
                roster=roster,
                process_schema_dir=process_schema_dir,
            )
        )

    check_failures: dict[str, list[str]] = {name: [] for name in CHECK_ORDER}
    check_warnings: dict[str, list[str]] = {name: [] for name in CHECK_ORDER}
    rows_pass = 0
    rows_fail = 0

    for row_report in row_reports:
        if row_report["verdict"] == "PASS":
            rows_pass += 1
        else:
            rows_fail += 1
        for check_name in CHECK_ORDER:
            check_result = row_report["checks"][check_name]
            if check_result["verdict"] == "FAIL":
                check_failures[check_name].append(row_report["process"])
            if any(detail.startswith("WARN:") for detail in check_result["details"]):
                check_warnings[check_name].append(row_report["process"])

    if process_filter is not None and not row_reports:
        load_failures.append(f"requested process {process_filter!r} not found in {wiring_dir}")

    overall_verdict = "PASS"
    if rows_fail > 0 or load_failures:
        overall_verdict = "FAIL"

    return {
        "wiring_dir": str(wiring_dir),
        "process_schema_dir": str(process_schema_dir),
        "process_filter": process_filter,
        "strict_anchors": strict_anchors,
        "load_failures": load_failures,
        "aggregate": {
            "overall_verdict": overall_verdict,
            "rows_total": len(row_reports),
            "rows_pass": rows_pass,
            "rows_fail": rows_fail,
            "check_failures": check_failures,
            "check_warnings": check_warnings,
        },
        "rows": row_reports,
    }


def _render_plain(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines: list[str] = []
    lines.append(
        "L1b wiring conformance: "
        f"{aggregate['overall_verdict']} ({aggregate['rows_pass']}/{aggregate['rows_total']} rows PASS)"
    )
    if report["load_failures"]:
        lines.append("load failures:")
        for item in report["load_failures"]:
            lines.append(f"- {item}")

    lines.append("per-check failures:")
    for check_name in CHECK_ORDER:
        failed_rows = aggregate["check_failures"][check_name]
        if failed_rows:
            lines.append(f"- {check_name}: {len(failed_rows)} ({', '.join(failed_rows)})")
        else:
            lines.append(f"- {check_name}: 0")

    lines.append("rows:")
    for row in report["rows"]:
        lines.append(
            f"- {row['process']}: {row['verdict']}"
            + (f" | failed={', '.join(row['failed_checks'])}" if row["failed_checks"] else "")
        )

    return "\n".join(lines)


def _render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines: list[str] = []

    lines.append("# L1b Wiring Conformance Report")
    lines.append("")
    lines.append(
        f"- Overall verdict: **{aggregate['overall_verdict']}**"
    )
    lines.append(
        f"- Rows: **{aggregate['rows_pass']}/{aggregate['rows_total']} PASS**, "
        f"**{aggregate['rows_fail']} FAIL**"
    )
    lines.append(f"- Strict anchors: `{report['strict_anchors']}`")
    if report["process_filter"] is not None:
        lines.append(f"- Process filter: `{report['process_filter']}`")
    lines.append("")

    if report["load_failures"]:
        lines.append("## Load Failures")
        lines.append("")
        for item in report["load_failures"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## Per-Check Aggregate")
    lines.append("")
    lines.append("| Check | Failed rows | Warning rows |")
    lines.append("| --- | ---: | ---: |")
    for check_name in CHECK_ORDER:
        failed_rows = aggregate["check_failures"][check_name]
        warning_rows = aggregate["check_warnings"][check_name]
        lines.append(f"| {check_name} | {len(failed_rows)} | {len(warning_rows)} |")
    lines.append("")

    lines.append("## Row Verdicts")
    lines.append("")
    lines.append("| Process | Verdict | Failed checks | Warnings |")
    lines.append("| --- | --- | --- | ---: |")
    for row in report["rows"]:
        failed_text = ", ".join(row["failed_checks"]) if row["failed_checks"] else "-"
        lines.append(
            f"| {row['process']} | {row['verdict']} | {failed_text} | {row['warning_count']} |"
        )
    lines.append("")

    lines.append("## Row Details")
    lines.append("")
    for row in report["rows"]:
        lines.append(f"### {row['process']} ({row['verdict']})")
        lines.append("")
        for check_name in CHECK_ORDER:
            result = row["checks"][check_name]
            lines.append(f"- `{check_name}`: **{result['verdict']}**")
            for detail in result["details"]:
                lines.append(f"  - {detail}")
        lines.append("")

    return "\n".join(lines)


def _render_output(report: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    if output_format == "md":
        return _render_markdown(report)
    return _render_plain(report)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="L1b row-vs-code wiring conformance gate",
    )
    parser.add_argument("--process", help="Optional process name filter (e.g., Metabolism)")
    parser.add_argument(
        "--strict-anchors",
        action="store_true",
        help="Require symbol presence in line-window (lines ±5) instead of whole-file symbol existence",
    )
    parser.add_argument("--out", type=Path, help="Optional output path for rendered report")
    parser.add_argument(
        "--format",
        choices=("json", "md", "plain"),
        default="plain",
        help="Report rendering format",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    wiring_dir = Path(os.environ.get(WIRING_DIR_ENV, str(DEFAULT_WIRING_DIR)))
    process_schema_dir = Path(os.environ.get(PROCESS_SCHEMA_DIR_ENV, str(DEFAULT_PROCESS_SCHEMA_DIR)))

    schema_path = wiring_dir / "_schema.yaml"
    if not schema_path.exists():
        message = f"missing schema contract file: {schema_path}"
        print(message)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(message + "\n", encoding="utf-8")
        return 1

    try:
        schema_contract = _load_yaml(schema_path)
    except Exception as exc:  # pragma: no cover - exercised through CLI
        message = f"failed to read schema contract {schema_path}: {exc}"
        print(message)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(message + "\n", encoding="utf-8")
        return 1

    if not isinstance(schema_contract, dict):
        message = f"schema contract {schema_path} did not parse as mapping"
        print(message)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(message + "\n", encoding="utf-8")
        return 1

    report = _build_report(
        wiring_dir=wiring_dir,
        process_schema_dir=process_schema_dir,
        schema_contract=schema_contract,
        process_filter=args.process,
        strict_anchors=args.strict_anchors,
    )

    rendered = _render_output(report, args.format)
    print(rendered)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")

    return 0 if report["aggregate"]["overall_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
