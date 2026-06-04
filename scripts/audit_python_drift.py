#!/usr/bin/env python3
"""Audit drift between extracted schema TOMLs and current Python process sources.

This is informational only: schema values are the reference, Python values are
potentially drifted implementation declarations.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import tomllib
from pathlib import Path
from typing import Any

from extract_per_process_schema import OUTPUT_DIR_REL, _repo_root


@dataclasses.dataclass
class DriftRow:
    process: str
    field: str
    schema_value: Any
    python_value: Any
    drift_kind: str
    severity: int


def _value_from_ast(node: ast.AST) -> Any | None:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        values = []
        for elt in node.elts:
            v = _value_from_ast(elt)
            if v is None:
                return None
            values.append(v)
        return values
    if isinstance(node, ast.Tuple):
        values = []
        for elt in node.elts:
            v = _value_from_ast(elt)
            if v is None:
                return None
            values.append(v)
        return values
    return None


def _collect_literals(tree: ast.AST) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            v = _value_from_ast(node.value)
            if v is None:
                continue
            for t in node.targets:
                if isinstance(t, ast.Name):
                    values[t.id] = v
                elif isinstance(t, ast.Attribute):
                    values[t.attr] = v
        elif isinstance(node, ast.AnnAssign):
            v = _value_from_ast(node.value) if node.value is not None else None
            if v is None:
                continue
            t = node.target
            if isinstance(t, ast.Name):
                values[t.id] = v
            elif isinstance(t, ast.Attribute):
                values[t.attr] = v
    return values


def _pick_best(values: dict[str, Any], includes: list[str], typ: type) -> Any | None:
    candidates: list[tuple[str, Any]] = []
    for k, v in values.items():
        lk = k.lower()
        if not all(token in lk for token in includes):
            continue
        if not isinstance(v, typ):
            continue
        candidates.append((k, v))
    if not candidates:
        return None
    # Prefer the longest list, then shortest key for stability.
    candidates.sort(key=lambda kv: (-len(kv[1]) if isinstance(kv[1], list) else 0, len(kv[0])))
    return candidates[0][1]


def _severity(kind: str) -> int:
    if kind == "value_mismatch":
        return 3
    if kind == "missing_python_decl":
        return 2
    return 1


def _compare(process: str, field: str, schema_value: Any, python_value: Any) -> DriftRow:
    if python_value is None:
        kind = "missing_python_decl"
    elif schema_value == python_value:
        kind = "match"
    else:
        kind = "value_mismatch"
    return DriftRow(
        process=process,
        field=field,
        schema_value=schema_value,
        python_value=python_value,
        drift_kind=kind,
        severity=_severity(kind),
    )


def _load_python_decls(py_path: Path) -> dict[str, Any]:
    if not py_path.exists():
        return {}
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return {}
    return _collect_literals(tree)


def _audit_process(schema: dict[str, Any], py_path: Path) -> list[DriftRow]:
    process = schema["process"]["name"]
    decls = _load_python_decls(py_path)
    rows: list[DriftRow] = []

    # Class name
    py_class = None
    if py_path.exists():
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    py_class = node.name
                    break
        except SyntaxError:
            py_class = None
    rows.append(_compare(process, "process.class", schema["process"]["class"], py_class))

    sub_wids_py = _pick_best(decls, ["substrate"], list)
    enz_wids_py = _pick_best(decls, ["enzyme"], list)
    sub_shape_py = _pick_best(decls, ["substrate", "shape"], list)
    enz_shape_py = _pick_best(decls, ["enzyme", "shape"], list)
    bound_shape_py = _pick_best(decls, ["bound", "shape"], list)

    rows.append(_compare(process, "substrates.wids", schema["substrates"]["wids"], sub_wids_py))
    rows.append(_compare(process, "substrates.count", schema["substrates"]["count"], (len(sub_wids_py) if isinstance(sub_wids_py, list) else None)))
    rows.append(_compare(process, "substrates.shape", schema["substrates"]["shape"], sub_shape_py))
    rows.append(_compare(process, "enzymes.free.wids", schema["enzymes"]["free"]["wids"], enz_wids_py))
    rows.append(_compare(process, "enzymes.free.count", schema["enzymes"]["free"]["count"], (len(enz_wids_py) if isinstance(enz_wids_py, list) else None)))
    rows.append(_compare(process, "enzymes.free.shape", schema["enzymes"]["free"]["shape"], enz_shape_py))
    rows.append(_compare(process, "enzymes.bound.shape", schema["enzymes"]["bound"]["shape"], bound_shape_py))
    return rows


def _fmt_value(v: Any) -> str:
    s = repr(v)
    if len(s) > 120:
        return s[:117] + "..."
    return s


def render_markdown(rows: list[DriftRow], total_processes: int) -> str:
    total_drifts = sum(1 for r in rows if r.drift_kind != "match")
    lines: list[str] = []
    lines.append("# Python Drift Report")
    lines.append("")
    lines.append("Schema is treated as reference; Python declarations are audited as drift candidates.")
    lines.append("")
    lines.append(f"- Total processes audited: {total_processes}")
    lines.append(f"- Total field checks: {len(rows)}")
    lines.append(f"- Total drifts (non-match): {total_drifts}")
    lines.append("")

    worst = sorted([r for r in rows if r.drift_kind != "match"], key=lambda r: (-r.severity, r.process, r.field))
    lines.append("## Top Drifts")
    lines.append("")
    if not worst:
        lines.append("No drifts detected.")
    else:
        for r in worst[:50]:
            lines.append(
                f"- `{r.process}` `{r.field}`: `{r.drift_kind}` "
                f"(schema={_fmt_value(r.schema_value)}, python={_fmt_value(r.python_value)})"
            )
    lines.append("")
    lines.append("## Full Field Audit")
    lines.append("")
    lines.append("| process | field | drift_kind | schema_value | python_value |")
    lines.append("|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: (x.process, x.field)):
        lines.append(
            f"| `{r.process}` | `{r.field}` | `{r.drift_kind}` | `{_fmt_value(r.schema_value)}` | `{_fmt_value(r.python_value)}` |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema-dir",
        default=str(OUTPUT_DIR_REL),
        help="Directory containing per-process schema TOML files.",
    )
    parser.add_argument(
        "--output",
        default="docs/phase_f/PYTHON_DRIFT_REPORT.md",
        help="Markdown output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = _repo_root()
    schema_dir = (
        Path(args.schema_dir)
        if Path(args.schema_dir).is_absolute()
        else repo_root / args.schema_dir
    )
    out_path = Path(args.output) if Path(args.output).is_absolute() else repo_root / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[DriftRow] = []
    processes = 0
    for toml_path in sorted(schema_dir.glob("*.toml")):
        schema = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        process = schema["process"]["name"]
        snake = toml_path.stem
        py_path = repo_root / "opencell/vivarium" / f"karr_{snake}.py"
        rows.extend(_audit_process(schema, py_path))
        processes += 1

    report = render_markdown(rows, processes)
    out_path.write_text(report, encoding="utf-8")
    print(f"wrote report: {out_path}")
    print(f"audited processes: {processes}")
    print(f"drifts: {sum(1 for r in rows if r.drift_kind != 'match')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
