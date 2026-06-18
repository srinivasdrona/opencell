#!/usr/bin/env python3
"""Compute pairwise WID overlap matrix from per-process TOMLs.

For each (process_i, process_j) pair where i < j, compute the size of each
state group's WID intersection. Emit:
1. docs/phase_f/L2_5_PAIR_MATRIX.md
2. data/schemas/l25_pair_list.toml

Pair classification:
- shared_pool: overlap > 0 on any state group
- disjoint: zero overlap on all state groups
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib  # type: ignore[attr-defined]

    _USE_TOMLLIB = True
except ModuleNotFoundError:  # pragma: no cover - exercised only on <3.11
    tomllib = None  # type: ignore[assignment]
    _USE_TOMLLIB = False
    import toml  # type: ignore[no-redef]

import yaml


CANONICAL_STATE_GROUPS = ("substrates", "enzymes", "monomers", "complexs", "rnas")
PAIR_TIER_SORT_ORDER = {1: 0, 2: 1, 3: 2, 0: 3}
STATUS_FIELDS = (
    "validation_status",
    "l2_2_validation_status",
    "l2_2_status",
    "status",
)
PASS_LITERALS = {
    "pass",
    "passed",
    "green",
    "complete",
    "completed",
    "ok",
    "true",
    "yes",
}
FAIL_LITERALS = {
    "fail",
    "failed",
    "red",
    "blocked",
    "false",
    "no",
}

PAIR_MATRIX_REL = Path("docs/phase_f/L2_5_PAIR_MATRIX.md")
PAIR_LIST_REL = Path("data/schemas/l25_pair_list.toml")
RUBRIC_REL = Path("docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md")
PROCESS_TOML_GLOB = "data/schemas/per_process/*.toml"
PROCESS_CATALOG_CANDIDATES = (
    Path("docs/phase_f/PROCESS_CATALOG.yaml"),
    Path("docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml"),
)


@dataclass(frozen=True)
class ProcessSchema:
    name: str
    source_file: Path
    state_groups: dict[str, set[str]]
    l2_2_passed: bool
    l2_2_gate_source: str


@dataclass(frozen=True)
class PairRecord:
    process_a: str
    process_b: str
    substrates_shared: list[str]
    enzymes_shared: list[str]
    monomers_shared: list[str]
    complexs_shared: list[str]
    rnas_shared: list[str]
    substrates_overlap: int
    enzymes_overlap: int
    monomers_overlap: int
    complexs_overlap: int
    rnas_overlap: int
    total_overlap: int
    classification: str
    tier: int
    l2_2_passed_a: bool
    l2_2_passed_b: bool
    l25_honest_required: bool


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_toml(path: Path) -> dict[str, Any]:
    if _USE_TOMLLIB:
        with path.open("rb") as handle:
            return tomllib.load(handle)  # type: ignore[union-attr]
    return toml.load(path)  # type: ignore[name-defined]


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_str(value: str) -> str:
    return f'"{_toml_escape(value)}"'


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_str(v) for v in values) + "]"


def _load_catalog(root: Path) -> tuple[dict[str, dict[str, Any]], Path, str]:
    catalog_path: Path | None = None
    for candidate_rel in PROCESS_CATALOG_CANDIDATES:
        candidate = root / candidate_rel
        if candidate.exists():
            catalog_path = candidate
            break
    if catalog_path is None:
        raise FileNotFoundError(
            "Unable to locate PROCESS_CATALOG.yaml in expected locations."
        )

    catalog_data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    process_entries = catalog_data.get("processes", [])
    if not isinstance(process_entries, list):
        raise ValueError("PROCESS_CATALOG.yaml must define a top-level list `processes`.")

    out: dict[str, dict[str, Any]] = {}
    fallback_mode_used = "explicit_status"
    for entry in process_entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        passed, source = _infer_l2_2_status(entry)
        if source.startswith("fallback:"):
            fallback_mode_used = source
        out[name] = {"passed": passed, "source": source}

    return out, catalog_path, fallback_mode_used


def _infer_l2_2_status(entry: dict[str, Any]) -> tuple[bool, str]:
    for field in STATUS_FIELDS:
        if field in entry:
            parsed = _parse_status_literal(entry[field])
            if parsed is not None:
                return parsed, f"field:{field}"

    if entry.get("blocked_on"):
        return False, "fallback:blocked_on"
    if "in_scope_L2_2" in entry:
        return bool(entry["in_scope_L2_2"]), "fallback:in_scope_L2_2"
    return True, "fallback:default_include"


def _parse_status_literal(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    as_text = str(value).strip().lower()
    if as_text in PASS_LITERALS:
        return True
    if as_text in FAIL_LITERALS:
        return False
    return None


def _load_process_schemas(
    root: Path, catalog_lookup: dict[str, dict[str, Any]]
) -> list[ProcessSchema]:
    toml_paths = sorted((root / "data/schemas/per_process").glob("*.toml"))
    if not toml_paths:
        raise FileNotFoundError("No per-process TOMLs found under data/schemas/per_process.")

    schemas: list[ProcessSchema] = []
    seen_names: set[str] = set()
    for toml_path in toml_paths:
        data = _load_toml(toml_path)
        process = data.get("process", {})
        state_groups = data.get("state_groups", {})
        if not isinstance(process, dict):
            raise ValueError(f"Missing [process] table: {toml_path}")
        if not isinstance(state_groups, dict):
            raise ValueError(f"Missing [state_groups] table: {toml_path}")
        name = str(process.get("name", "")).strip()
        if not name:
            raise ValueError(f"Missing process.name in: {toml_path}")
        if name in seen_names:
            raise ValueError(f"Duplicate process name across TOMLs: {name}")
        seen_names.add(name)

        catalog_entry = catalog_lookup.get(name, {"passed": True, "source": "fallback:missing"})
        group_sets: dict[str, set[str]] = {}
        for group in CANONICAL_STATE_GROUPS:
            raw_values = state_groups.get(group, [])
            if raw_values is None:
                raw_values = []
            if not isinstance(raw_values, list):
                raise ValueError(f"state_groups.{group} must be a list in {toml_path}")
            group_sets[group] = {str(value) for value in raw_values}

        schemas.append(
            ProcessSchema(
                name=name,
                source_file=toml_path,
                state_groups=group_sets,
                l2_2_passed=bool(catalog_entry["passed"]),
                l2_2_gate_source=str(catalog_entry["source"]),
            )
        )

    schemas.sort(key=lambda p: p.name)
    return schemas


def _classify_pair(overlaps: dict[str, int]) -> tuple[str, int]:
    total = sum(overlaps.values())
    if total == 0:
        return "disjoint", 0
    if max(overlaps["substrates"], overlaps["enzymes"]) >= 3:
        return "shared_pool", 1
    if overlaps["substrates"] > 0 or overlaps["enzymes"] > 0:
        return "shared_pool", 2
    return "shared_pool", 3


def _compute_pairs(processes: list[ProcessSchema]) -> list[PairRecord]:
    pairs: list[PairRecord] = []
    for index_a, proc_a in enumerate(processes):
        for proc_b in processes[index_a + 1 :]:
            shared_lists: dict[str, list[str]] = {}
            overlaps: dict[str, int] = {}
            for group in CANONICAL_STATE_GROUPS:
                shared = sorted(proc_a.state_groups[group] & proc_b.state_groups[group])
                shared_lists[group] = shared
                overlaps[group] = len(shared)

            classification, tier = _classify_pair(overlaps)
            total_overlap = sum(overlaps.values())
            l25_honest_required = (
                classification == "shared_pool" and proc_a.l2_2_passed and proc_b.l2_2_passed
            )
            pairs.append(
                PairRecord(
                    process_a=proc_a.name,
                    process_b=proc_b.name,
                    substrates_shared=shared_lists["substrates"],
                    enzymes_shared=shared_lists["enzymes"],
                    monomers_shared=shared_lists["monomers"],
                    complexs_shared=shared_lists["complexs"],
                    rnas_shared=shared_lists["rnas"],
                    substrates_overlap=overlaps["substrates"],
                    enzymes_overlap=overlaps["enzymes"],
                    monomers_overlap=overlaps["monomers"],
                    complexs_overlap=overlaps["complexs"],
                    rnas_overlap=overlaps["rnas"],
                    total_overlap=total_overlap,
                    classification=classification,
                    tier=tier,
                    l2_2_passed_a=proc_a.l2_2_passed,
                    l2_2_passed_b=proc_b.l2_2_passed,
                    l25_honest_required=l25_honest_required,
                )
            )

    pairs.sort(
        key=lambda pair: (
            PAIR_TIER_SORT_ORDER[pair.tier],
            -pair.total_overlap,
            pair.process_a,
            pair.process_b,
        )
    )
    return pairs


def _source_digest(root: Path, processes: list[ProcessSchema], catalog_path: Path) -> str:
    sha = hashlib.sha256()
    all_paths = [process.source_file for process in processes] + [catalog_path]
    for path in sorted(all_paths):
        rel = path.relative_to(root).as_posix()
        sha.update(rel.encode("utf-8"))
        sha.update(b"\0")
        sha.update(path.read_bytes())
        sha.update(b"\0")
    return sha.hexdigest()


def _deterministic_generated_at(source_digest: str) -> str:
    # Deterministic timestamp derived from source bytes for byte-stable output.
    seconds = int(source_digest[:14], 16) % (60 * 60 * 24 * 365 * 40)
    anchor = datetime(2000, 1, 1, tzinfo=timezone.utc)
    value = anchor + timedelta(seconds=seconds)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pair_counts(pairs: list[PairRecord]) -> dict[str, int]:
    shared = sum(1 for pair in pairs if pair.classification == "shared_pool")
    disjoint = sum(1 for pair in pairs if pair.classification == "disjoint")
    tier_1 = sum(1 for pair in pairs if pair.tier == 1)
    tier_2 = sum(1 for pair in pairs if pair.tier == 2)
    tier_3 = sum(1 for pair in pairs if pair.tier == 3)
    honest_required = sum(1 for pair in pairs if pair.l25_honest_required)
    return {
        "shared_pool_pairs": shared,
        "disjoint_pairs": disjoint,
        "tier_1_pairs": tier_1,
        "tier_2_pairs": tier_2,
        "tier_3_pairs": tier_3,
        "l25_honest_required_pairs": honest_required,
    }


def _render_markdown_pair_table(pairs: list[PairRecord]) -> list[str]:
    if not pairs:
        return ["_None_"]
    lines = [
        "| process_A | process_B | substrates_overlap | enzymes_overlap | monomers_overlap | complexs_overlap | rnas_overlap | total |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for pair in pairs:
        lines.append(
            "| "
            f"{pair.process_a} | "
            f"{pair.process_b} | "
            f"{pair.substrates_overlap} | "
            f"{pair.enzymes_overlap} | "
            f"{pair.monomers_overlap} | "
            f"{pair.complexs_overlap} | "
            f"{pair.rnas_overlap} | "
            f"{pair.total_overlap} |"
        )
    return lines


def _render_disjoint_table(pairs: list[PairRecord]) -> list[str]:
    if not pairs:
        return ["_None_"]
    lines = ["| process_A | process_B |", "|---|---|"]
    for pair in pairs:
        lines.append(f"| {pair.process_a} | {pair.process_b} |")
    return lines


def _render_matrix_block(processes: list[ProcessSchema], pairs: list[PairRecord]) -> list[str]:
    names = [process.name for process in processes]
    totals: dict[tuple[str, str], int] = {}
    for pair in pairs:
        totals[(pair.process_a, pair.process_b)] = pair.total_overlap
        totals[(pair.process_b, pair.process_a)] = pair.total_overlap

    lines: list[str] = []
    header = "Idx Process".ljust(30) + "".join(f"{idx:>4}" for idx in range(1, len(names) + 1))
    lines.append(header)
    for idx, name in enumerate(names, start=1):
        row = f"{idx:>3} {name:<24}"
        for jdx, other in enumerate(names, start=1):
            if idx == jdx:
                cell = "-"
            else:
                cell = str(totals[(name, other)])
            row += f"{cell:>4}"
        lines.append(row)
    return lines


def _build_pair_matrix_markdown(
    root: Path,
    processes: list[ProcessSchema],
    pairs: list[PairRecord],
    catalog_path: Path,
    fallback_mode: str,
    source_digest: str,
    generated_at: str,
) -> str:
    counts = _pair_counts(pairs)
    tier_1 = [pair for pair in pairs if pair.tier == 1]
    tier_2 = [pair for pair in pairs if pair.tier == 2]
    tier_3 = [pair for pair in pairs if pair.tier == 3]
    disjoint = [pair for pair in pairs if pair.tier == 0]

    shared_partners: dict[str, int] = {process.name: 0 for process in processes}
    required_partners: dict[str, int] = {process.name: 0 for process in processes}
    for pair in pairs:
        if pair.classification == "shared_pool":
            shared_partners[pair.process_a] += 1
            shared_partners[pair.process_b] += 1
        if pair.l25_honest_required:
            required_partners[pair.process_a] += 1
            required_partners[pair.process_b] += 1

    matrix_lines = _render_matrix_block(processes, pairs)

    lines: list[str] = []
    lines.append("# L2.5 Pair Matrix")
    lines.append("")
    lines.append("## 1. Executive summary")
    lines.append("")
    lines.append(f"- Total processes: {len(processes)}")
    lines.append(f"- Total pairs: {len(pairs)}")
    lines.append(f"- Shared-pool pairs: {counts['shared_pool_pairs']}")
    lines.append(f"- Disjoint pairs: {counts['disjoint_pairs']}")
    lines.append(f"- Tier 1 pairs (must-pass priority): {counts['tier_1_pairs']}")
    lines.append(f"- Tier 2 pairs (should-pass): {counts['tier_2_pairs']}")
    lines.append(f"- Tier 3 pairs (informational): {counts['tier_3_pairs']}")
    lines.append(
        "- L2.5.2 honest-required shared pairs (catalog-filtered): "
        f"{counts['l25_honest_required_pairs']}"
    )
    lines.append(
        "- Catalog filter mode: "
        f"`{fallback_mode}` from `{catalog_path.relative_to(root).as_posix()}`"
    )
    lines.append(f"- Source digest: `{source_digest}`")
    lines.append(f"- Deterministic generated_at: `{generated_at}`")
    lines.append("")
    lines.append("## 2. Pair count matrix")
    lines.append("")
    lines.append("```text")
    lines.extend(matrix_lines)
    lines.append("```")
    lines.append("")
    lines.append("## 3. Tier 1 pair list")
    lines.append("")
    lines.extend(_render_markdown_pair_table(tier_1))
    lines.append("")
    lines.append("## 4. Tier 2 pair list")
    lines.append("")
    lines.extend(_render_markdown_pair_table(tier_2))
    lines.append("")
    lines.append("## 5. Tier 3 pair list")
    lines.append("")
    lines.extend(_render_markdown_pair_table(tier_3))
    lines.append("")
    lines.append("## 6. Disjoint pair list")
    lines.append("")
    lines.extend(_render_disjoint_table(disjoint))
    lines.append("")
    lines.append("## 7. Per-process pair count")
    lines.append("")
    lines.append("| process | shared_pool_partners | honest_required_partners |")
    lines.append("|---|---:|---:|")
    for process in sorted(processes, key=lambda p: p.name):
        lines.append(
            f"| {process.name} | {shared_partners[process.name]} | "
            f"{required_partners[process.name]} |"
        )
    lines.append("")
    lines.append("## 8. Methodology")
    lines.append("")
    lines.append("- Input source: `data/schemas/per_process/*.toml`")
    lines.append(
        "- Canonical state groups: `substrates`, `enzymes`, `monomers`, `complexs`, `rnas`"
    )
    lines.append("- Overlap for a group = `len(set(A[group]) & set(B[group]))`")
    lines.append("- Total overlap = sum of all 5 group overlap counts")
    lines.append("- Classification: `shared_pool` if total overlap > 0 else `disjoint`")
    lines.append(
        "- Tiering: Tier 1 if `max(substrates_overlap, enzymes_overlap) >= 3`; "
        "Tier 2 if substrate/enzyme overlap is 1-2; Tier 3 if overlap is only "
        "in RNAs/monomers/complexs"
    )
    lines.append(
        "- Sorting: tier (1,2,3,disjoint), then `total_overlap` desc, then "
        "`process_a`, then `process_b`"
    )
    lines.append(
        f"- Acceptance tie-in: see `{RUBRIC_REL.as_posix()}` for L2.5 pair policy."
    )
    lines.append(
        "- Regenerate command: "
        "`bin\\oc-py.cmd scripts/derive_l25_pair_matrix.py`"
    )
    lines.append(
        "- Check-only command: "
        "`bin\\oc-py.cmd scripts/derive_l25_pair_matrix.py --check-only`"
    )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_pair_list_toml(
    root: Path,
    pairs: list[PairRecord],
    processes: list[ProcessSchema],
    catalog_path: Path,
    fallback_mode: str,
    source_digest: str,
    generated_at: str,
) -> str:
    counts = _pair_counts(pairs)
    lines: list[str] = []
    lines.append("# AUTOGENERATED by scripts/derive_l25_pair_matrix.py -- DO NOT EDIT")
    lines.append(
        "# Regenerate with: bin\\oc-py.cmd scripts/derive_l25_pair_matrix.py"
    )
    lines.append("")
    lines.append('schema_version = "1.0"')
    lines.append(f"generated_at = {_toml_str(generated_at)}")
    lines.append(f"source_digest = {_toml_str(source_digest)}")
    lines.append(f"source_tomls = {_toml_str(PROCESS_TOML_GLOB)}")
    lines.append(
        f"process_catalog = {_toml_str(catalog_path.relative_to(root).as_posix())}"
    )
    lines.append(f"catalog_filter_mode = {_toml_str(fallback_mode)}")
    lines.append(f"total_processes = {len(processes)}")
    lines.append(f"total_pairs_computed = {len(pairs)}")
    lines.append(f"shared_pool_pairs = {counts['shared_pool_pairs']}")
    lines.append(f"disjoint_pairs = {counts['disjoint_pairs']}")
    lines.append(f"tier_1_pairs = {counts['tier_1_pairs']}")
    lines.append(f"tier_2_pairs = {counts['tier_2_pairs']}")
    lines.append(f"tier_3_pairs = {counts['tier_3_pairs']}")
    lines.append(
        f"l25_honest_required_pairs = {counts['l25_honest_required_pairs']}"
    )
    lines.append("")

    for pair in pairs:
        lines.append("[[pairs]]")
        lines.append(f"process_a = {_toml_str(pair.process_a)}")
        lines.append(f"process_b = {_toml_str(pair.process_b)}")
        lines.append(f"tier = {pair.tier}")
        lines.append(f"classification = {_toml_str(pair.classification)}")
        lines.append(f"l2_2_passed_a = {_toml_bool(pair.l2_2_passed_a)}")
        lines.append(f"l2_2_passed_b = {_toml_bool(pair.l2_2_passed_b)}")
        lines.append(f"l25_honest_required = {_toml_bool(pair.l25_honest_required)}")
        lines.append(f"substrates_overlap = {pair.substrates_overlap}")
        lines.append(f"enzymes_overlap = {pair.enzymes_overlap}")
        lines.append(f"monomers_overlap = {pair.monomers_overlap}")
        lines.append(f"complexs_overlap = {pair.complexs_overlap}")
        lines.append(f"rnas_overlap = {pair.rnas_overlap}")
        lines.append(f"total_overlap = {pair.total_overlap}")
        lines.append(f"substrates_shared = {_toml_array(pair.substrates_shared)}")
        lines.append(f"enzymes_shared = {_toml_array(pair.enzymes_shared)}")
        lines.append(f"monomers_shared = {_toml_array(pair.monomers_shared)}")
        lines.append(f"complexs_shared = {_toml_array(pair.complexs_shared)}")
        lines.append(f"rnas_shared = {_toml_array(pair.rnas_shared)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _read_text_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _write_text_exact(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify generated outputs are up-to-date without rewriting files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = _repo_root()
    catalog_lookup, catalog_path, fallback_mode = _load_catalog(root)
    processes = _load_process_schemas(root, catalog_lookup)
    pairs = _compute_pairs(processes)
    source_digest = _source_digest(root, processes, catalog_path)
    generated_at = _deterministic_generated_at(source_digest)

    pair_matrix_text = _build_pair_matrix_markdown(
        root=root,
        processes=processes,
        pairs=pairs,
        catalog_path=catalog_path,
        fallback_mode=fallback_mode,
        source_digest=source_digest,
        generated_at=generated_at,
    )
    pair_list_text = _build_pair_list_toml(
        root=root,
        pairs=pairs,
        processes=processes,
        catalog_path=catalog_path,
        fallback_mode=fallback_mode,
        source_digest=source_digest,
        generated_at=generated_at,
    )

    outputs = {
        root / PAIR_MATRIX_REL: pair_matrix_text,
        root / PAIR_LIST_REL: pair_list_text,
    }

    if args.check_only:
        stale: list[Path] = []
        for path, expected in outputs.items():
            if not path.exists():
                stale.append(path)
                continue
            if _read_text_exact(path) != expected:
                stale.append(path)
        if stale:
            print("[stale] L2.5 pair-matrix artifacts are out of date:")
            for path in stale:
                print(f"  - {path.relative_to(root).as_posix()}")
            return 1
        print("[ok] L2.5 pair-matrix artifacts are up to date.")
        return 0

    for path, content in outputs.items():
        _write_text_exact(path, content)
        print(f"[ok] wrote {path.relative_to(root).as_posix()}")

    counts = _pair_counts(pairs)
    print(
        "[summary] "
        f"processes={len(processes)} "
        f"pairs={len(pairs)} "
        f"shared_pool={counts['shared_pool_pairs']} "
        f"disjoint={counts['disjoint_pairs']} "
        f"tier1={counts['tier_1_pairs']} "
        f"tier2={counts['tier_2_pairs']} "
        f"tier3={counts['tier_3_pairs']} "
        f"l25_honest_required={counts['l25_honest_required_pairs']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
