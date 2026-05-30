#!/usr/bin/env python3
"""Round-trip validator for per-process schema TOMLs."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import Any

from extract_per_process_schema import (
    OUTPUT_DIR_REL,
    build_paths,
    extract_process_schema,
    render_schema_toml,
)


def _diff_fields(a: Any, b: Any, prefix: str = "") -> list[str]:
    diffs: list[str] = []
    if type(a) is not type(b):
        diffs.append(prefix or "<root>")
        return diffs

    if isinstance(a, dict):
        a_keys = set(a.keys())
        b_keys = set(b.keys())
        for key in sorted(a_keys - b_keys):
            diffs.append(f"{prefix}.{key}" if prefix else key)
        for key in sorted(b_keys - a_keys):
            diffs.append(f"{prefix}.{key}" if prefix else key)
        for key in sorted(a_keys & b_keys):
            child = f"{prefix}.{key}" if prefix else key
            diffs.extend(_diff_fields(a[key], b[key], child))
        return diffs

    if isinstance(a, list):
        if len(a) != len(b):
            diffs.append(prefix or "<root>")
            return diffs
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(_diff_fields(x, y, f"{prefix}[{i}]"))
        return diffs

    if a != b:
        diffs.append(prefix or "<root>")
    return diffs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema-dir",
        default=str(OUTPUT_DIR_REL),
        help="Directory containing per-process TOML schema files.",
    )
    parser.add_argument(
        "--wholecell-root",
        default=None,
        help="Optional explicit WholeCell root containing src/",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = build_paths(args.wholecell_root)
    schema_dir = (
        Path(args.schema_dir)
        if Path(args.schema_dir).is_absolute()
        else paths.repo_root / args.schema_dir
    )
    toml_files = sorted(schema_dir.glob("*.toml"))
    if not toml_files:
        print(f"no TOML files found in {schema_dir}")
        return 1

    passed = 0
    failures: list[tuple[str, list[str]]] = []

    for toml_path in toml_files:
        text = toml_path.read_text(encoding="utf-8")
        parsed = tomllib.loads(text)
        process_name = parsed.get("process", {}).get("name")
        if not process_name:
            failures.append((toml_path.name, ["process.name"]))
            print(f"[FAIL] {toml_path.name}: missing process.name")
            continue

        extracted = extract_process_schema(process_name, paths)
        rendered = render_schema_toml(extracted)
        extracted_parsed = tomllib.loads(rendered)

        field_diffs = _diff_fields(parsed, extracted_parsed)
        if text != rendered:
            field_diffs = sorted(set(field_diffs + ["<bytewise_toml_mismatch>"]))

        if field_diffs:
            failures.append((process_name, field_diffs))
            joined = ", ".join(field_diffs[:12])
            if len(field_diffs) > 12:
                joined += ", ..."
            print(f"[FAIL] {process_name}: {joined}")
        else:
            passed += 1
            print(f"[PASS] {process_name}")

    total = len(toml_files)
    print(f"{passed}/{total} round-trip pass")
    if failures:
        print("failing fields:")
        for proc, fields in failures:
            print(f"  - {proc}: {', '.join(fields)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
