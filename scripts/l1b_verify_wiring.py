#!/usr/bin/env python3
"""L1b row-vs-code wiring conformance gate for per-process wiring DB rows."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import jsonschema
import numpy as np
import yaml
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WIRING_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
DEFAULT_PROCESS_SCHEMA_DIR = REPO_ROOT / "data" / "schemas" / "per_process"
DEFAULT_OC_METHOD_MAP = REPO_ROOT / "data" / "karr_method_inventory" / "oc_method_map.yaml"
DEFAULT_EXTERNAL_WID_FIXTURE = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
WIRING_DIR_ENV = "OC_L1B_WIRING_DIR"
PROCESS_SCHEMA_DIR_ENV = "OC_L1B_PROCESS_SCHEMA_DIR"
OC_METHOD_MAP_ENV = "OC_L1B_OC_METHOD_MAP"
TOUCHPOINT_METHODS = (
    "calcResourceRequirements_Current",
    "evolveState",
    "calcFluxBounds",
)
REQUEST_FORMULA_SENTINELS = {
    "",
    "todo",
    "notimplemented",
    "not_implemented",
    "n/a",
    "na",
    "none",
}

CHECK_ORDER = (
    "check_schema_conformance",
    "check_stoichiometry_oracle_matches",
    "check_half_a_b_consistency",
    "check_a_invariants",
    "check_matlab_anchors_resolve",
    "check_oc_anchors_resolve",
    "check_consume_produce_wids_in_schema_toml",
    "check_allocator_requests_wids_in_schema_toml",
    "check_unit_conversion_chain_coherent",
    "check_ordering_constraints_reference_valid_processes",
    "check_dependency_symmetry",
    "check_orphan_consume_wids",
    "check_deviations_reference_valid_anchors",
)

FILE_REF_RE = re.compile(r"([A-Za-z0-9_./+\-@]+?\.(?:py|m))")
MIRROR_ROOT_PREFIX = "e:/opencell-mirrors/"
MIRROR_REWRITE_PREFIX = "e:/opencell-mirrors/opencell/"
PROCESS_EXTRACT_DOC_PREFIX = "docs/karr_extracts/process/"
PROCESS_SUMMARY_METHOD_SYMBOLS = {
    "calcresourcerequirementscurrent",
    "evolvestate",
    "calcfluxbounds",
    "initializeconstants",
}


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
            if path.suffix.lower() == ".m":
                self._text[path] = _read_matlab_source(path)
            else:
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


def _read_matlab_source(path: Path) -> str:
    """Read MATLAB source with encoding fallback (Karr sources are latin-1)."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _resolve_matlab_anchor_path(anchor_path: str, repo_root: Path) -> tuple[Path, str | None]:
    resolved = _resolve_anchor_path(anchor_path, repo_root)
    normalized = anchor_path.replace("\\", "/")
    if not normalized.lower().startswith(MIRROR_ROOT_PREFIX):
        return resolved, None

    if not normalized.lower().startswith(MIRROR_REWRITE_PREFIX):
        return resolved, None

    relative_suffix = normalized[len(MIRROR_REWRITE_PREFIX) :]
    rewritten = repo_root / Path(relative_suffix)
    if not rewritten.exists():
        return resolved, None

    try:
        rewritten_display = rewritten.relative_to(repo_root).as_posix()
    except ValueError:
        rewritten_display = str(rewritten)

    warning = (
        f"WARN: mirror anchor path rewritten for portability: {anchor_path} -> {rewritten_display}"
    )
    return rewritten, warning


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


def _normalize_symbol_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _md_symbol_documented(text: str, symbol: str) -> bool:
    if symbol.lower() in text.lower():
        return True
    normalized_symbol = _normalize_symbol_text(symbol)
    if not normalized_symbol:
        return False
    return normalized_symbol in _normalize_symbol_text(text)


def _is_process_extract_doc(path: str, text: str) -> bool:
    normalized_path = path.replace("\\", "/").lower()
    return normalized_path.startswith(PROCESS_EXTRACT_DOC_PREFIX) and (
        "# karr process -" in text.lower() or "@wholecellmodelid" in text.lower()
    )


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
    touchpoints = row.get("integration_touchpoints")
    if isinstance(touchpoints, dict):
        for method_name, binding in touchpoints.items():
            if not isinstance(binding, dict):
                continue
            matlab_block = binding.get("matlab")
            if isinstance(matlab_block, dict):
                anchor = _anchor_from_mapping(
                    matlab_block.get("source"),
                    f"integration_touchpoints.{method_name}.matlab.source",
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

    touchpoints = row.get("integration_touchpoints")
    if isinstance(touchpoints, dict):
        for method_name, binding in touchpoints.items():
            if not isinstance(binding, dict):
                continue
            oc_block = binding.get("oc")
            if isinstance(oc_block, dict):
                anchor = _anchor_from_mapping(
                    oc_block.get("source"),
                    f"integration_touchpoints.{method_name}.oc.source",
                    oc_block.get("symbol") if isinstance(oc_block.get("symbol"), str) else None,
                )
                if anchor is not None:
                    anchors.append(anchor)

                supporting = oc_block.get("supporting")
                if isinstance(supporting, list):
                    for idx, support_anchor in enumerate(supporting):
                        anchor = _anchor_from_mapping(
                            support_anchor,
                            f"integration_touchpoints.{method_name}.oc.supporting[{idx}]",
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
    allow_md_extract_docs: bool,
    resolve_matlab_paths: bool,
) -> CheckResult:
    failures: list[str] = []
    warnings: list[str] = []

    for anchor in anchor_refs:
        if resolve_matlab_paths:
            resolved, maybe_warning = _resolve_matlab_anchor_path(anchor.path, repo_root)
            if maybe_warning is not None:
                warnings.append(maybe_warning)
        else:
            resolved = _resolve_anchor_path(anchor.path, repo_root)

        if not resolved.exists():
            failures.append(f"{anchor.label}: missing file {anchor.path}")
            continue

        try:
            text = cache.text(resolved)
        except Exception as exc:
            failures.append(f"{anchor.label}: could not read file {anchor.path}: {exc}")
            continue

        if allow_md_extract_docs and resolved.suffix.lower() == ".md":
            if _md_symbol_documented(text, anchor.symbol):
                warnings.append(
                    f"WARN: {anchor.label} resolved derived-doc .md anchor with permissive symbol match for {anchor.symbol!r}"
                )
            elif _is_process_extract_doc(anchor.path, text) and (
                _normalize_symbol_text(anchor.symbol) in PROCESS_SUMMARY_METHOD_SYMBOLS
            ):
                warnings.append(
                    f"WARN: {anchor.label} accepted process-summary .md anchor for generic method symbol {anchor.symbol!r}"
                )
            else:
                failures.append(
                    f"{anchor.label}: symbol {anchor.symbol!r} not found in derived-doc file {anchor.path}"
                )
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


def _normalize_sentinel_text(value: str) -> str:
    return re.sub(r"[^a-z0-9/]+", "", value.lower())


def _extract_touchpoint(row: dict[str, Any], method_name: str) -> dict[str, Any] | None:
    touchpoints = row.get("integration_touchpoints")
    if not isinstance(touchpoints, dict):
        return None
    binding = touchpoints.get(method_name)
    return binding if isinstance(binding, dict) else None


def _parse_method_map_symbol(oc_value: Any) -> str | None:
    if not isinstance(oc_value, str):
        return None
    parts = oc_value.split(":")
    if len(parts) < 3:
        return None
    symbol = ":".join(parts[1:-1]).strip()
    return symbol or None


def _resolve_method_map_process(
    row: dict[str, Any],
    method_map_contract: dict[str, Any] | None,
) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(method_map_contract, dict):
        return None, None
    processes = method_map_contract.get("processes")
    if not isinstance(processes, dict):
        return None, None

    candidates: list[str] = []
    process_name = _process_name(row, "")
    if process_name:
        candidates.append(process_name)
    process_meta = row.get("process")
    if isinstance(process_meta, dict):
        matlab_class = process_meta.get("matlab_class")
        if isinstance(matlab_class, str) and matlab_class.strip():
            candidates.append(matlab_class.strip())

    normalized_candidates = {_normalize_name(candidate): candidate for candidate in candidates if candidate}
    for process_key, payload in processes.items():
        if not isinstance(process_key, str) or not isinstance(payload, dict):
            continue
        if process_key in candidates or _normalize_name(process_key) in normalized_candidates:
            return process_key, payload
    return None, None


def _text_mentions_projection(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return "project" in lowered or "flat" in lowered


def check_schema_conformance(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    del process_schema_dir
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source

    if not isinstance(schema_contract, dict):
        return CheckResult(verdict="FAIL", details=["schema contract unavailable"])

    schema_obj = {
        key: schema_contract[key]
        for key in ("type", "additionalProperties", "required", "properties", "definitions")
    }
    validator = jsonschema.Draft7Validator(schema_obj)
    errors = sorted(validator.iter_errors(row), key=lambda exc: list(exc.absolute_path))
    if errors:
        return CheckResult(
            verdict="FAIL",
            details=[f"{'/'.join(map(str, err.absolute_path))}: {err.message}" for err in errors],
        )
    return CheckResult(verdict="PASS", details=["row conforms to schema contract"])


def check_stoichiometry_oracle_matches(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del cache
    del roster
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source

    oracle_block = row.get("stoichiometry_oracle")
    if not isinstance(oracle_block, dict):
        return CheckResult(verdict="FAIL", details=["stoichiometry_oracle block absent"])

    record_path = oracle_block.get("record_path")
    if not isinstance(record_path, str) or not record_path.strip():
        return CheckResult(verdict="FAIL", details=["stoichiometry_oracle.record_path missing/invalid"])

    resolved_record = _resolve_anchor_path(record_path, repo_root)
    try:
        oracle_bytes = resolved_record.read_bytes()
        oracle = json.loads(oracle_bytes.decode("utf-8"))
    except Exception as exc:
        return CheckResult(
            verdict="FAIL",
            details=[f"stoichiometry_oracle.record_path could not be read: {record_path} ({exc})"],
        )

    failures: list[str] = []
    oracle_class = oracle.get("class")
    row_class = oracle_block.get("class")
    if row_class != oracle_class:
        failures.append(
            f"stoichiometry_oracle.class mismatch: row={row_class!r} oracle={oracle_class!r}"
        )

    substrates = oracle.get("substrates")
    if not isinstance(substrates, list):
        failures.append("oracle.substrates missing/not a list")
        substrates = []

    oracle_count = oracle.get("n_substrates", len(substrates))
    if oracle.get("n_substrates") is not None and oracle.get("n_substrates") != len(substrates):
        failures.append(
            "oracle n_substrates disagrees with substrates length: "
            f"n_substrates={oracle.get('n_substrates')!r} len(substrates)={len(substrates)}"
        )

    row_count = oracle_block.get("substrate_count")
    if row_count != oracle_count:
        failures.append(
            f"stoichiometry_oracle.substrate_count mismatch: row={row_count!r} oracle={oracle_count!r}"
        )

    row_hash = oracle_block.get("sha256")
    if row_hash is not None:
        if not isinstance(row_hash, str) or not row_hash.strip():
            failures.append("stoichiometry_oracle.sha256 missing/invalid")
        else:
            actual_hash = hashlib.sha256(oracle_bytes).hexdigest()
            if row_hash != actual_hash:
                failures.append(
                    f"stoichiometry_oracle.sha256 mismatch: row={row_hash!r} oracle={actual_hash!r}"
                )

    if failures:
        return CheckResult(verdict="FAIL", details=failures)
    return CheckResult(
        verdict="PASS",
        details=[f"oracle matched {record_path} ({oracle_count} substrates)"],
    )


def check_half_a_b_consistency(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    del process_schema_dir
    del schema_contract
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source

    if not isinstance(method_map_contract, dict):
        path_display = str(method_map_path) if method_map_path is not None else "unknown"
        return CheckResult(
            verdict="FAIL",
            details=[f"Half A method map unavailable: {path_display}"],
        )

    process_key, process_entry = _resolve_method_map_process(row, method_map_contract)
    if process_entry is None:
        return CheckResult(
            verdict="PASS",
            details=[f"WARN: Half A method map has no process entry for {_process_name(row, 'unknown')}"],
        )

    runtime_methods = process_entry.get("runtime_methods")
    if not isinstance(runtime_methods, dict):
        return CheckResult(
            verdict="PASS",
            details=[f"WARN: Half A method map entry for {process_key} has no runtime_methods mapping"],
        )

    failures: list[str] = []
    warnings: list[str] = []
    for method_name in TOUCHPOINT_METHODS:
        binding = _extract_touchpoint(row, method_name)
        if binding is None:
            continue

        method_entry = runtime_methods.get(method_name)
        if not isinstance(method_entry, dict):
            warnings.append(f"WARN: Half A has no entry for ({process_key}, {method_name})")
            continue

        mapped_symbol = _parse_method_map_symbol(method_entry.get("oc"))
        if mapped_symbol is None:
            warnings.append(f"WARN: Half A has no OC symbol for ({process_key}, {method_name})")
            continue

        oc_block = binding.get("oc")
        row_symbol = oc_block.get("symbol") if isinstance(oc_block, dict) else None
        if not isinstance(row_symbol, str) or not row_symbol.strip():
            failures.append(f"integration_touchpoints.{method_name}.oc.symbol missing/invalid")
            continue

        if row_symbol != mapped_symbol:
            failures.append(
                f"Half A/B drift for {method_name}: row oc.symbol={row_symbol!r} Half A={mapped_symbol!r}"
            )

    if failures:
        return CheckResult(verdict="FAIL", details=[*failures, *warnings])
    return CheckResult(
        verdict="PASS",
        details=[f"validated Half A/B touchpoints for {process_key}", *warnings],
    )


def check_a_invariants(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source

    failures: list[str] = []
    calc_request = _extract_touchpoint(row, "calcResourceRequirements_Current")
    if calc_request is None:
        failures.append("A1: integration_touchpoints.calcResourceRequirements_Current missing")
    else:
        status = calc_request.get("status")
        if status != "implemented":
            failures.append(
                "A1: integration_touchpoints.calcResourceRequirements_Current.status must be 'implemented'"
            )

    allocator = row.get("allocator")
    request_formula = allocator.get("request_formula") if isinstance(allocator, dict) else None
    request_formula_oc = request_formula.get("oc") if isinstance(request_formula, dict) else None
    if not isinstance(request_formula_oc, str) or not request_formula_oc.strip():
        failures.append("A1: allocator.request_formula.oc missing/empty")
    elif _normalize_sentinel_text(request_formula_oc) in REQUEST_FORMULA_SENTINELS:
        failures.append(
            f"A1: allocator.request_formula.oc must not be a sentinel value ({request_formula_oc!r})"
        )

    evolve_state = _extract_touchpoint(row, "evolveState")
    if evolve_state is None:
        failures.append("A3: integration_touchpoints.evolveState missing")
    else:
        status = evolve_state.get("status")
        if status != "implemented":
            failures.append("A3: integration_touchpoints.evolveState.status must be 'implemented'")

    deviations = row.get("deviations")
    merges = deviations.get("shared_pool_projection_merges_compartments") if isinstance(deviations, dict) else None
    if merges is True:
        oc_block = evolve_state.get("oc") if isinstance(evolve_state, dict) else None
        supporting = oc_block.get("supporting") if isinstance(oc_block, dict) else None
        has_projection_anchor = False
        if isinstance(supporting, list):
            for anchor in supporting:
                if not isinstance(anchor, dict):
                    continue
                if _text_mentions_projection(anchor.get("symbol")) or _text_mentions_projection(anchor.get("note")):
                    has_projection_anchor = True
                    break

        known_deviations = deviations.get("known_deviations") if isinstance(deviations, dict) else None
        mentions_projection = False
        if isinstance(known_deviations, list):
            mentions_projection = any(_text_mentions_projection(item) for item in known_deviations)

        if not has_projection_anchor and not mentions_projection:
            failures.append(
                "A3b: shared_pool_projection_merges_compartments=true requires a projection/flat supporting anchor or known deviation"
            )

    if failures:
        return CheckResult(verdict="FAIL", details=failures)
    return CheckResult(verdict="PASS", details=["A-invariants satisfied"])


def check_matlab_anchors_resolve(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del roster
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source
    anchors = _collect_matlab_anchors(row)
    return _validate_anchor_refs(
        anchor_refs=anchors,
        strict_anchors=strict_anchors,
        repo_root=repo_root,
        cache=cache,
        require_ast_for_python=False,
        allow_source_block_line_fallback=True,
        allow_md_extract_docs=True,
        resolve_matlab_paths=True,
    )


def check_oc_anchors_resolve(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del roster
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source
    anchors = _collect_oc_anchors(row)
    return _validate_anchor_refs(
        anchor_refs=anchors,
        strict_anchors=strict_anchors,
        repo_root=repo_root,
        cache=cache,
        require_ast_for_python=True,
        allow_source_block_line_fallback=False,
        allow_md_extract_docs=False,
        resolve_matlab_paths=False,
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


def _collect_dependency_names(row: dict[str, Any], key: str) -> set[str]:
    dependencies = row.get("dependencies")
    if not isinstance(dependencies, dict):
        return set()
    values = dependencies.get(key)
    if not isinstance(values, list):
        return set()
    return {
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    }


def _dependency_partners_from_row(
    row: dict[str, Any],
    *,
    key: str,
) -> tuple[list[str] | None, list[str]]:
    dependencies = row.get("dependencies")
    if not isinstance(dependencies, dict):
        return None, ["dependencies missing or not a mapping"]

    values = dependencies.get(key)
    if not isinstance(values, list):
        return None, [f"dependencies.{key} missing/not a list"]

    failures: list[str] = []
    partners: list[str] = []
    for idx, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            failures.append(f"dependencies.{key}[{idx}] invalid process name {value!r}")
            continue
        partners.append(value.strip())
    return partners, failures


def _build_dependency_index(
    rows: list[tuple[Path, dict[str, Any]]],
) -> dict[str, dict[str, set[str]]]:
    dep_index: dict[str, dict[str, set[str]]] = {}
    for row_path, row in rows:
        process_name = _process_name(row, row_path.stem)
        dep_index[process_name] = {
            "produces_inputs_for": _collect_dependency_names(row, "produces_inputs_for"),
            "consumes_outputs_of": _collect_dependency_names(row, "consumes_outputs_of"),
        }
    return dep_index


def _collect_wids(entries: Any) -> set[str]:
    if not isinstance(entries, list):
        return set()

    wids: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict):
            wid = entry.get("wid")
            if isinstance(wid, str) and wid.strip():
                wids.add(wid.strip())
            elif wid is not None:
                wids.add(str(wid))
            continue
        if isinstance(entry, str) and entry.strip():
            wids.add(entry.strip())
    return wids


def _build_produced_wids(rows: list[tuple[Path, dict[str, Any]]]) -> set[str]:
    produced_wids: set[str] = set()
    allocator_output_keys = ("produces", "produced", "produced_wids", "outputs")

    for _row_path, row in rows:
        produced_wids.update(_collect_wids(row.get("produce_stoichiometry", [])))

        allocator = row.get("allocator")
        if not isinstance(allocator, dict):
            continue
        for key in allocator_output_keys:
            produced_wids.update(_collect_wids(allocator.get(key, [])))

    return produced_wids


def _load_external_wids(repo_root: Path) -> tuple[set[str] | None, str]:
    fixture_path = DEFAULT_EXTERNAL_WID_FIXTURE
    if not fixture_path.exists():
        return None, f"missing external-WID fixture {fixture_path}"

    try:
        mat = loadmat(fixture_path, squeeze_me=True, struct_as_record=False)
        fixture = mat["data"].fixture
        substrate_wids = [
            str(item)
            for item in np.asarray(fixture.substrateWholeCellModelIDs, dtype=object).reshape(-1)
        ]
        external_idx = (
            np.asarray(fixture.substrateIndexs_externalExchangedMetabolites, dtype=np.int64).reshape(-1)
            - 1
        )
    except Exception as exc:
        return None, f"failed to load external-WID fixture {fixture_path}: {exc}"

    external_wids = {
        substrate_wids[idx]
        for idx in external_idx
        if 0 <= idx < len(substrate_wids)
    }
    if not external_wids:
        return None, f"external-WID fixture {fixture_path} resolved zero WIDs"

    try:
        display_path = fixture_path.relative_to(repo_root).as_posix()
    except ValueError:
        display_path = str(fixture_path)
    return external_wids, f"{display_path} via Metabolism.substrateIndexs_externalExchangedMetabolites"


def _build_dependency_graph(
    rows: list[tuple[Path, dict[str, Any]]],
    roster: set[str],
) -> dict[str, set[str]]:
    graph = {process_name: set() for process_name in roster}

    for row_path, row in rows:
        process_name = _process_name(row, row_path.stem)
        for downstream in _collect_dependency_names(row, "produces_inputs_for"):
            if downstream in roster:
                graph[process_name].add(downstream)

        ordering = row.get("ordering_constraints")
        if not isinstance(ordering, dict):
            continue
        hard_before = ordering.get("hard_before")
        if not isinstance(hard_before, list):
            continue
        for downstream in hard_before:
            if isinstance(downstream, str) and downstream.strip() and downstream.strip() in roster:
                graph[process_name].add(downstream.strip())

    return graph


def _canonical_cycle(cycle_nodes: list[str]) -> tuple[str, ...]:
    rotations = [
        tuple(cycle_nodes[idx:] + cycle_nodes[:idx])
        for idx in range(len(cycle_nodes))
    ]
    return min(rotations)


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    visit_state = {node: 0 for node in graph}
    stack: list[str] = []
    stack_index: dict[str, int] = {}
    seen_cycles: set[tuple[str, ...]] = set()
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        visit_state[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)

        for downstream in sorted(graph[node]):
            state = visit_state.get(downstream, 0)
            if state == 0:
                dfs(downstream)
                continue
            if state != 1:
                continue

            cycle_nodes = stack[stack_index[downstream] :].copy()
            if not cycle_nodes:
                continue
            cycle_key = _canonical_cycle(cycle_nodes)
            if cycle_key in seen_cycles:
                continue
            seen_cycles.add(cycle_key)
            cycles.append([*cycle_key, cycle_key[0]])

        stack.pop()
        stack_index.pop(node, None)
        visit_state[node] = 2

    for node in sorted(graph):
        if visit_state[node] == 0:
            dfs(node)

    cycles.sort()
    return cycles


def _check_no_dependency_cycles(
    rows: list[tuple[Path, dict[str, Any]]],
    roster: set[str],
) -> dict[str, Any]:
    graph = _build_dependency_graph(rows, roster)
    cycles = _find_cycles(graph)
    edge_count = sum(len(targets) for targets in graph.values())

    if cycles:
        return {
            "verdict": "FAIL",
            "cycles": cycles,
            "details": [
                f"dependency/ordering graph contains {len(cycles)} cycle(s)",
                *[f"cycle: {' -> '.join(cycle)}" for cycle in cycles],
            ],
            "node_count": len(graph),
            "edge_count": edge_count,
        }

    return {
        "verdict": "PASS",
        "cycles": [],
        "details": [f"validated acyclic dependency/order graph ({len(graph)} nodes, {edge_count} edges)"],
        "node_count": len(graph),
        "edge_count": edge_count,
    }


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
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source
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
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source
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
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source

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
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source

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


def check_dependency_symmetry(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del produced_wids
    del external_wids
    del external_wids_source

    if dep_index is None:
        return CheckResult(verdict="FAIL", details=["dependency index missing"])

    process_name = _process_name(row, "unknown")
    failures: list[str] = []

    produces_inputs_for, produce_failures = _dependency_partners_from_row(
        row,
        key="produces_inputs_for",
    )
    failures.extend(produce_failures)

    consumes_outputs_of, consume_failures = _dependency_partners_from_row(
        row,
        key="consumes_outputs_of",
    )
    failures.extend(consume_failures)

    for downstream in sorted(produces_inputs_for or []):
        if downstream not in roster:
            failures.append(f"dependency references unknown process {downstream!r}")
            continue
        if process_name not in dep_index[downstream]["consumes_outputs_of"]:
            failures.append(
                "dependency asymmetry: "
                f"{process_name}.produces_inputs_for -> {downstream} "
                f"but {downstream}.consumes_outputs_of lacks {process_name}"
            )

    for upstream in sorted(consumes_outputs_of or []):
        if upstream not in roster:
            failures.append(f"dependency references unknown process {upstream!r}")
            continue
        if process_name not in dep_index[upstream]["produces_inputs_for"]:
            failures.append(
                "dependency asymmetry: "
                f"{process_name}.consumes_outputs_of -> {upstream} "
                f"but {upstream}.produces_inputs_for lacks {process_name}"
            )

    if failures:
        return CheckResult(verdict="FAIL", details=failures)

    total_edges = len(produces_inputs_for or []) + len(consumes_outputs_of or [])
    return CheckResult(verdict="PASS", details=[f"validated {total_edges} dependency edges"])


def check_orphan_consume_wids(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del repo_root
    del cache
    del roster
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index

    if produced_wids is None:
        return CheckResult(verdict="FAIL", details=["produced WID index missing"])

    allocator = row.get("allocator")
    requests = allocator.get("requests", []) if isinstance(allocator, dict) else []
    target_wids = _collect_wids(row.get("consume_stoichiometry", []))
    target_wids.update(_collect_wids(requests))

    candidate_orphans = sorted(wid for wid in target_wids if wid not in produced_wids)
    if not candidate_orphans:
        return CheckResult(
            verdict="PASS",
            details=[f"validated {len(target_wids)} consume/request WIDs against produced corpus"],
        )

    if external_wids is None:
        warnings = [
            "WARN: external WID allowlist unresolved; potential orphans kept as warnings "
            f"({external_wids_source or 'no source'})"
        ]
        warnings.extend(
            [
                f"WARN: orphan candidate consume/request WID {wid!r} not produced by any row"
                for wid in candidate_orphans
            ]
        )
        return CheckResult(verdict="PASS", details=warnings)

    failures = [
        f"orphan consume/request WID {wid!r}: not produced by any row and not in external allowlist"
        for wid in candidate_orphans
        if wid not in external_wids
    ]
    if failures:
        return CheckResult(verdict="FAIL", details=failures)

    external_hits = sum(1 for wid in candidate_orphans if wid in external_wids)
    return CheckResult(
        verdict="PASS",
        details=[
            f"validated {len(target_wids)} consume/request WIDs ({external_hits} allowlisted external via {external_wids_source})"
        ],
    )


def check_deviations_reference_valid_anchors(
    row: dict[str, Any],
    *,
    strict_anchors: bool,
    repo_root: Path,
    cache: FileCache,
    roster: set[str],
    process_schema_dir: Path,
    schema_contract: dict[str, Any] | None = None,
    method_map_contract: dict[str, Any] | None = None,
    method_map_path: Path | None = None,
    dep_index: dict[str, dict[str, set[str]]] | None = None,
    produced_wids: set[str] | None = None,
    external_wids: set[str] | None = None,
    external_wids_source: str | None = None,
) -> CheckResult:
    del strict_anchors
    del cache
    del roster
    del process_schema_dir
    del schema_contract
    del method_map_contract
    del method_map_path
    del dep_index
    del produced_wids
    del external_wids
    del external_wids_source

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
    "check_schema_conformance": check_schema_conformance,
    "check_stoichiometry_oracle_matches": check_stoichiometry_oracle_matches,
    "check_half_a_b_consistency": check_half_a_b_consistency,
    "check_a_invariants": check_a_invariants,
    "check_matlab_anchors_resolve": check_matlab_anchors_resolve,
    "check_oc_anchors_resolve": check_oc_anchors_resolve,
    "check_consume_produce_wids_in_schema_toml": check_consume_produce_wids_in_schema_toml,
    "check_allocator_requests_wids_in_schema_toml": check_allocator_requests_wids_in_schema_toml,
    "check_unit_conversion_chain_coherent": check_unit_conversion_chain_coherent,
    "check_ordering_constraints_reference_valid_processes": check_ordering_constraints_reference_valid_processes,
    "check_dependency_symmetry": check_dependency_symmetry,
    "check_orphan_consume_wids": check_orphan_consume_wids,
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
    schema_contract: dict[str, Any],
    method_map_contract: dict[str, Any] | None,
    method_map_path: Path,
    dep_index: dict[str, dict[str, set[str]]],
    produced_wids: set[str],
    external_wids: set[str] | None,
    external_wids_source: str,
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
            schema_contract=schema_contract,
            method_map_contract=method_map_contract,
            method_map_path=method_map_path,
            dep_index=dep_index,
            produced_wids=produced_wids,
            external_wids=external_wids,
            external_wids_source=external_wids_source,
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
    method_map_contract: dict[str, Any] | None,
    method_map_path: Path,
    process_filter: str | None,
    strict_anchors: bool,
) -> dict[str, Any]:
    rows, load_failures = _discover_rows(wiring_dir)
    roster = {_process_name(payload, row_path.stem) for row_path, payload in rows}
    dep_index = _build_dependency_index(rows)
    produced_wids = _build_produced_wids(rows)
    external_wids, external_wids_source = _load_external_wids(REPO_ROOT)
    graph_checks = {
        "no_dependency_cycles": _check_no_dependency_cycles(rows, roster),
    }
    if graph_checks["no_dependency_cycles"]["verdict"] == "FAIL":
        load_failures.extend(graph_checks["no_dependency_cycles"]["details"])

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
                schema_contract=schema_contract,
                method_map_contract=method_map_contract,
                method_map_path=method_map_path,
                dep_index=dep_index,
                produced_wids=produced_wids,
                external_wids=external_wids,
                external_wids_source=external_wids_source,
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
    if rows_fail > 0 or load_failures or any(
        result["verdict"] == "FAIL" for result in graph_checks.values()
    ):
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
            "graph_checks": graph_checks,
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

    graph_checks = aggregate.get("graph_checks", {})
    if graph_checks:
        lines.append("graph checks:")
        for check_name, result in graph_checks.items():
            lines.append(f"- {check_name}: {result['verdict']}")
            for detail in result.get("details", []):
                lines.append(f"  - {detail}")

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

    graph_checks = aggregate.get("graph_checks", {})
    if graph_checks:
        lines.append("## Graph Checks")
        lines.append("")
        for check_name, result in graph_checks.items():
            lines.append(f"- `{check_name}`: **{result['verdict']}**")
            for detail in result.get("details", []):
                lines.append(f"  - {detail}")
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
    method_map_path = Path(os.environ.get(OC_METHOD_MAP_ENV, str(DEFAULT_OC_METHOD_MAP)))

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

    method_map_contract: dict[str, Any] | None = None
    if not method_map_path.exists():
        print(f"WARN: Half A method map not found: {method_map_path}")
    else:
        try:
            loaded_method_map = _load_yaml(method_map_path)
        except Exception as exc:  # pragma: no cover - exercised through CLI
            print(f"WARN: failed to read Half A method map {method_map_path}: {exc}")
        else:
            if isinstance(loaded_method_map, dict):
                method_map_contract = loaded_method_map
            else:
                print(f"WARN: Half A method map {method_map_path} did not parse as mapping")

    report = _build_report(
        wiring_dir=wiring_dir,
        process_schema_dir=process_schema_dir,
        schema_contract=schema_contract,
        method_map_contract=method_map_contract,
        method_map_path=method_map_path,
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
