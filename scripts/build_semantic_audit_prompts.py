"""Build per-process semantic-audit prompts from the template.

Reads process rows from `data/schemas/per_process_wiring/*.yaml`,
substitutes placeholders in
`docs/prompts/PROMPT_semantic_audit_TEMPLATE.md`,
and writes one prompt per process to an output directory.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WIRING_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
TEMPLATE_PATH = REPO_ROOT / "docs" / "prompts" / "PROMPT_semantic_audit_TEMPLATE.md"


def _default_output_dir() -> Path:
    # `bin/oc-py` executes inside WSL in this repo, so we provide a WSL path
    # that maps to the operator's requested Windows location.
    if os.name == "nt":
        return Path(r"E:\opencell-worktree-prompts")
    return Path("/mnt/e/opencell-worktree-prompts")


DEFAULT_OUTPUT_DIR = _default_output_dir()


def _process_slug(name: str) -> str:
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", name)
    return "_".join(p.lower() for p in parts if p)


def _bullet_list(items: list[str]) -> str:
    if not items:
        return "- `<none>`"
    return "\n".join(f"- `{item}`" for item in items)


def _load_row(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected mapping at root")
    return payload


def _sorted_row_paths() -> list[Path]:
    return sorted(
        [
            p
            for p in WIRING_DIR.glob("*.yaml")
            if not p.name.startswith("_")
        ],
        key=lambda p: p.name.lower(),
    )


def _matlab_support_files(row: dict[str, Any], main_matlab_file: str) -> list[str]:
    provenance = row.get("provenance", {})
    referenced = provenance.get("matlab_files_referenced", [])
    if not isinstance(referenced, list):
        return []
    out: list[str] = []
    for item in referenced:
        if not isinstance(item, str):
            continue
        if item == main_matlab_file:
            continue
        if item not in out:
            out.append(item)
    return out


def _oc_files(row: dict[str, Any], fallback_oc_file: str | None) -> list[str]:
    provenance = row.get("provenance", {})
    referenced = provenance.get("oc_files_referenced", [])
    out: list[str] = []
    if isinstance(referenced, list):
        for item in referenced:
            if isinstance(item, str) and item not in out:
                out.append(item)
    if not out and fallback_oc_file:
        out.append(fallback_oc_file)
    return out


def build_prompts(output_dir: Path, dry_run: bool = False) -> list[Path]:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    row_paths = _sorted_row_paths()
    for row_path in row_paths:
        row = _load_row(row_path)
        proc = row.get("process", {})
        if not isinstance(proc, dict):
            raise ValueError(f"{row_path}: missing process mapping")

        process_name = str(proc.get("name") or row_path.stem)
        process_slug = _process_slug(process_name)
        matlab_file = str(proc.get("matlab_file", "")).strip()
        oc_file = str(proc.get("oc_file", "")).strip() or None

        if not matlab_file:
            raise ValueError(f"{row_path}: missing process.matlab_file")

        matlab_support = _matlab_support_files(row, matlab_file)
        oc_files = _oc_files(row, oc_file)

        rendered = template
        rendered = rendered.replace("{PROCESS_NAME}", process_name)
        rendered = rendered.replace("{PROCESS_SLUG}", process_slug)
        rendered = rendered.replace("{MATLAB_FILE}", matlab_file)
        rendered = rendered.replace("{MATLAB_SUPPORT_FILES}", _bullet_list(matlab_support))
        rendered = rendered.replace("{OC_FILES}", _bullet_list(oc_files))

        out_path = output_dir / f"PROMPT_semantic_audit_{process_name}.md"
        if not dry_run:
            out_path.write_text(rendered, encoding="utf-8")
        written.append(out_path)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for generated prompts (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and report outputs without writing files.",
    )
    args = parser.parse_args()

    written = build_prompts(args.output_dir, dry_run=args.dry_run)

    print(f"Rows discovered: {len(_sorted_row_paths())}")
    print(f"Prompts rendered: {len(written)}")
    print(f"Output directory: {args.output_dir}")
    if written:
        print("Sample outputs:")
        for path in written[:3]:
            print(f"  - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
