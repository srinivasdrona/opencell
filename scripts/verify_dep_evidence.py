#!/usr/bin/env python3
"""Derive per-process dependency edges from authoritative machine-readable sources."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WIRING_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
METABOLISM_JSON = (
    REPO_ROOT / "data" / "karr_method_inventory" / "karr_stoichiometry" / "Metabolism.json"
)


@dataclass(frozen=True)
class InputEvidence:
    consumer: str
    wid: str
    source_kind: str
    source_index: int
    producer: str | None
    producer_rule: str

    @property
    def source_ref(self) -> str:
        return f"{self.source_kind}[{self.source_index}]"


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} did not parse to a mapping")
    return payload


def _process_name(row_path: Path, payload: dict[str, Any]) -> str:
    process = payload.get("process")
    if isinstance(process, dict):
        name = process.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return row_path.stem


def _load_rows() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row_path in sorted(path for path in WIRING_DIR.glob("*.yaml") if not path.name.startswith("_")):
        payload = _load_yaml(row_path)
        rows[_process_name(row_path, payload)] = {
            "path": row_path,
            "payload": payload,
        }
    return rows


def _load_metabolism_substrates() -> set[str]:
    payload = json.loads(METABOLISM_JSON.read_text(encoding="utf-8"))
    substrates = payload.get("substrates")
    if not isinstance(substrates, list):
        raise TypeError(f"{METABOLISM_JSON} missing substrates list")
    result: set[str] = set()
    for entry in substrates:
        if isinstance(entry, dict):
            wid = entry.get("wid")
            if isinstance(wid, str) and wid:
                result.add(wid)
    return result


def _classify_producer(wid: str, metabolism_substrates: set[str]) -> tuple[str | None, str]:
    if wid in metabolism_substrates:
        return "Metabolism", "Metabolism.substrates[*].wid"
    if wid.endswith("_MONOMER"):
        return "Translation", "suffix *_MONOMER"
    if wid.startswith("RIBOSOME"):
        return "RibosomeAssembly", "prefix RIBOSOME*"
    if wid.startswith("MGrrn") or "rrna" in wid.lower():
        return "RNAProcessing", "MGrrn* / rRNA"
    if wid.endswith("_DIMER") or wid.endswith("MER"):
        return "MacromolecularComplexation", "suffix *_DIMER or *MER"
    return None, "producer UNKNOWN"


def _collect_input_evidence(
    consumer: str,
    payload: dict[str, Any],
    metabolism_substrates: set[str],
) -> list[InputEvidence]:
    evidence: list[InputEvidence] = []

    consume_entries = payload.get("consume_stoichiometry", [])
    if isinstance(consume_entries, list):
        for idx, entry in enumerate(consume_entries):
            if not isinstance(entry, dict):
                continue
            wid = entry.get("wid")
            if not isinstance(wid, str) or not wid:
                continue
            producer, rule = _classify_producer(wid, metabolism_substrates)
            evidence.append(
                InputEvidence(
                    consumer=consumer,
                    wid=wid,
                    source_kind="consume_stoichiometry",
                    source_index=idx,
                    producer=producer,
                    producer_rule=rule,
                )
            )

    allocator = payload.get("allocator")
    requests = allocator.get("requests", []) if isinstance(allocator, dict) else []
    if isinstance(requests, list):
        for idx, entry in enumerate(requests):
            if not isinstance(entry, dict):
                continue
            wid = entry.get("wid")
            if not isinstance(wid, str) or not wid:
                continue
            producer, rule = _classify_producer(wid, metabolism_substrates)
            evidence.append(
                InputEvidence(
                    consumer=consumer,
                    wid=wid,
                    source_kind="allocator.requests",
                    source_index=idx,
                    producer=producer,
                    producer_rule=rule,
                )
            )

    return evidence


def _derive_graph(
    rows: dict[str, dict[str, Any]],
    metabolism_substrates: set[str],
) -> tuple[dict[str, list[InputEvidence]], dict[str, set[str]], dict[str, set[str]]]:
    evidence_by_process: dict[str, list[InputEvidence]] = {}
    consumes_outputs_of: dict[str, set[str]] = {}
    produces_inputs_for: dict[str, set[str]] = {process: set() for process in rows}

    for consumer, row_info in rows.items():
        evidence = _collect_input_evidence(consumer, row_info["payload"], metabolism_substrates)
        evidence_by_process[consumer] = evidence

        upstreams = {
            item.producer
            for item in evidence
            if item.producer is not None and item.producer != consumer
        }
        consumes_outputs_of[consumer] = set(sorted(upstreams))
        for upstream in upstreams:
            produces_inputs_for[upstream].add(consumer)

    return evidence_by_process, consumes_outputs_of, produces_inputs_for


def _current_dependencies(payload: dict[str, Any], key: str) -> set[str]:
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict):
        return set()
    values = dependencies.get(key, [])
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str) and value}


def _pair_lines(
    *,
    consumer: str,
    upstream: str,
    row_path: Path,
    evidence: list[InputEvidence],
) -> list[str]:
    matched = [item for item in evidence if item.producer == upstream]
    if matched:
        lines = [
            f"EDGE {consumer} <- {upstream}: {len(matched)} supporting same-tick input(s) in {row_path.relative_to(REPO_ROOT).as_posix()}"
        ]
        for item in matched:
            lines.append(
                f"  - {item.source_ref}: wid={item.wid} -> producer={upstream} ({item.producer_rule})"
            )
        return lines

    scanned = ", ".join(
        f"{item.source_ref}:{item.wid}->{item.producer or 'UNKNOWN'}" for item in evidence
    )
    if not scanned:
        scanned = "no consume_stoichiometry or allocator.requests WIDs found"
    return [
        f"NO_EDGE {consumer} <- {upstream}: no same-tick input WID maps to {upstream} in {row_path.relative_to(REPO_ROOT).as_posix()}",
        f"  - scanned: {scanned}",
    ]


def _render_graph(
    rows: dict[str, dict[str, Any]],
    evidence_by_process: dict[str, list[InputEvidence]],
    consumes_outputs_of: dict[str, set[str]],
    produces_inputs_for: dict[str, set[str]],
) -> str:
    lines: list[str] = []
    total_edges = 0
    for consumer in sorted(rows):
        upstreams = sorted(consumes_outputs_of[consumer])
        total_edges += len(upstreams)
        lines.append(f"{consumer}:")
        lines.append(f"  consumes_outputs_of: {upstreams}")
        lines.append(f"  produces_inputs_for: {sorted(produces_inputs_for[consumer])}")
        unknown = [item for item in evidence_by_process[consumer] if item.producer is None]
        if unknown:
            lines.append(
                "  unresolved_unknown_inputs: "
                + str([f"{item.source_ref}:{item.wid}" for item in unknown])
            )
    lines.append(f"total_edges: {total_edges}")
    return "\n".join(lines)


def _render_edge_evidence(
    rows: dict[str, dict[str, Any]],
    evidence_by_process: dict[str, list[InputEvidence]],
    consumes_outputs_of: dict[str, set[str]],
) -> str:
    lines: list[str] = []
    for consumer in sorted(rows):
        row_path = rows[consumer]["path"]
        for upstream in sorted(consumes_outputs_of[consumer]):
            lines.extend(
                _pair_lines(
                    consumer=consumer,
                    upstream=upstream,
                    row_path=row_path,
                    evidence=evidence_by_process[consumer],
                )
            )
    return "\n".join(lines)


def _render_diff(
    rows: dict[str, dict[str, Any]],
    consumes_outputs_of: dict[str, set[str]],
    produces_inputs_for: dict[str, set[str]],
) -> tuple[str, bool]:
    lines: list[str] = []
    matched = True
    for process in sorted(rows):
        payload = rows[process]["payload"]
        current_consumes = _current_dependencies(payload, "consumes_outputs_of")
        current_produces = _current_dependencies(payload, "produces_inputs_for")
        expected_consumes = consumes_outputs_of[process]
        expected_produces = produces_inputs_for[process]

        if current_consumes == expected_consumes and current_produces == expected_produces:
            continue

        matched = False
        lines.append(process)
        if current_consumes != expected_consumes:
            lines.append(
                f"  consumes_outputs_of current={sorted(current_consumes)} expected={sorted(expected_consumes)}"
            )
        if current_produces != expected_produces:
            lines.append(
                f"  produces_inputs_for current={sorted(current_produces)} expected={sorted(expected_produces)}"
            )

    if matched:
        lines.append("current dependency blocks match the derived graph")
    return "\n".join(lines), matched


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Derive dependency edges from consume_stoichiometry/allocator.requests WIDs "
            "and the authoritative producer map."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("graph", "edges", "diff"),
        default="edges",
        help="Render the derived graph, per-edge evidence, or current-vs-derived diff.",
    )
    parser.add_argument("--pair", nargs=2, metavar=("CONSUMER", "UPSTREAM"))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _load_rows()
    metabolism_substrates = _load_metabolism_substrates()
    evidence_by_process, consumes_outputs_of, produces_inputs_for = _derive_graph(
        rows, metabolism_substrates
    )

    if args.pair is not None:
        consumer, upstream = args.pair
        if consumer not in rows:
            print(f"unknown consumer: {consumer}")
            return 2
        if upstream not in rows:
            print(f"unknown upstream process: {upstream}")
            return 2
        print(
            "\n".join(
                _pair_lines(
                    consumer=consumer,
                    upstream=upstream,
                    row_path=rows[consumer]["path"],
                    evidence=evidence_by_process[consumer],
                )
            )
        )
        return 0

    if args.mode == "graph":
        print(_render_graph(rows, evidence_by_process, consumes_outputs_of, produces_inputs_for))
        return 0

    if args.mode == "diff":
        rendered, matched = _render_diff(rows, consumes_outputs_of, produces_inputs_for)
        print(rendered)
        return 0 if matched else 1

    print(_render_edge_evidence(rows, evidence_by_process, consumes_outputs_of))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
