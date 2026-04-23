"""Emit curation outputs: cards YAML, queues, coverage report, run provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import yaml

from opencell.data.verification import (
    ParameterCard,
    VerificationStatus,
    load_cards_from_yaml,
    save_cards_to_yaml,
)

from .runner import CurationOutcome, CurationRun


def _merge_cards(existing: list[ParameterCard], new_cards: list[ParameterCard]) -> list[ParameterCard]:
    """Replace DRAFTs in-place by parameter_id; never overwrite REVIEWED/APPROVED."""
    locked_ids = {
        c.parameter_id for c in existing
        if c.status in (VerificationStatus.REVIEWED, VerificationStatus.APPROVED)
    }
    by_id = {c.parameter_id: c for c in existing}
    for card in new_cards:
        if card.parameter_id in locked_ids:
            continue   # defense-in-depth; runner should already have skipped
        by_id[card.parameter_id] = card
    return list(by_id.values())


def write_cards_yaml(run: CurationRun, path: Path) -> int:
    """Append/replace DRAFT cards. Returns number of cards in final file."""
    new_cards = [o.card for o in run.outcomes if o.card is not None]
    if not new_cards and not path.exists():
        return 0
    existing = load_cards_from_yaml(path) if path.exists() else []
    merged = _merge_cards(existing, new_cards)
    if merged:
        path.parent.mkdir(parents=True, exist_ok=True)
        save_cards_to_yaml(merged, path)
    return len(merged)


def _outcome_to_queue_entry(o: CurationOutcome) -> dict:
    e: dict = {
        "parameter_id": o.parameter_id,
        "symbol": o.symbol,
        "status": o.status,
        "note": o.note,
    }
    if o.extraction is not None:
        e["target_unit"] = o.extraction.target_unit
        e["methods_attempted"] = list(o.extraction.methods_attempted)
        e["cache_files"] = list(o.extraction.cache_files)
        e["surviving_candidates"] = [
            {
                "raw_value": c.raw_value,
                "raw_unit": c.raw_unit_normalized,
                "converted_value": c.converted_value,
                "converted_unit": c.converted_unit,
                "score": round(c.score, 3),
                "method": c.method,
                "locator": c.locator,
                "context": c.context_window.strip()[:280],
            }
            for c in o.extraction.surviving
        ]
        e["rejected_count"] = len(o.extraction.rejected)
        e["notes"] = list(o.extraction.notes)
    return e


def write_queue(outcomes: Iterable[CurationOutcome], path: Path, *, kind: str) -> int:
    entries = [o for o in outcomes if o.status == kind]
    if not entries:
        # Remove stale queue files from a prior run with these statuses.
        if path.exists():
            path.unlink()
        return 0
    payload = {
        "queue_kind": kind,
        "count": len(entries),
        "entries": [_outcome_to_queue_entry(o) for o in entries],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return len(entries)


def render_coverage_md(run: CurationRun) -> str:
    cov = run.coverage
    total = cov.get("TOTAL", 0)

    def pct(n: int) -> str:
        return f"{(100.0 * n / total):.1f}%" if total else "0.0%"

    order = ["RECOMMEND", "AMBIGUOUS", "NOT_FOUND", "ALL_REJECTED",
            "SKIPPED_EXISTS", "SKIPPED_LOCKED"]
    lines = [
        f"# Curation Coverage — {run.model_slug}",
        "",
        f"- DOI: {run.doi}",
        f"- Manifest: {run.manifest_path}",
        f"- Started: {run.started_at}",
        f"- Finished: {run.finished_at}",
        f"- Total parameters: {total}",
        "",
        "## Status breakdown",
        "",
        "| Status | Count | % |",
        "|---|---:|---:|",
    ]
    for k in order:
        n = cov.get(k, 0)
        if n:
            lines.append(f"| {k} | {n} | {pct(n)} |")
    lines.append("")
    lines.append("## Per-parameter results")
    lines.append("")
    lines.append("| parameter_id | symbol | status | note |")
    lines.append("|---|---|---|---|")
    for o in run.outcomes:
        note = o.note
        if not note and o.extraction is not None:
            n_surv = len(o.extraction.surviving)
            n_rej = len(o.extraction.rejected)
            note = f"survivors={n_surv}, rejected={n_rej}"
        lines.append(f"| `{o.parameter_id}` | `{o.symbol}` | {o.status} | {note} |")
    lines.append("")
    return "\n".join(lines)


def write_coverage_md(run: CurationRun, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_coverage_md(run))


def _exit_code_for(status: str) -> int:
    return {
        "RECOMMEND": 0,
        "AMBIGUOUS": 1,
        "NOT_FOUND": 2,
        "ALL_REJECTED": 2,
        "SKIPPED_EXISTS": 0,
        "SKIPPED_LOCKED": 0,
    }.get(status, 1)


def run_to_provenance(run: CurationRun) -> dict:
    return {
        "model_slug": run.model_slug,
        "doi": run.doi,
        "manifest_path": run.manifest_path,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "cache_file_sha256": dict(run.cache_file_sha256),
        "coverage": run.coverage,
        "results": [
            {
                "parameter_id": o.parameter_id,
                "symbol": o.symbol,
                "status": o.status,
                "note": o.note,
                "exit_code": _exit_code_for(o.status),
                "recommended_value": (
                    (o.extraction.recommendation.converted_value
                     or o.extraction.recommendation.raw_value)
                    if o.extraction is not None and o.extraction.recommendation is not None
                    else None
                ),
                "recommended_unit": (
                    (o.extraction.recommendation.converted_unit
                     or o.extraction.recommendation.raw_unit_normalized)
                    if o.extraction is not None and o.extraction.recommendation is not None
                    else None
                ),
            }
            for o in run.outcomes
        ],
    }


def write_provenance(run: CurationRun, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run_to_provenance(run), indent=2, default=str))


def write_outputs(
    run: CurationRun,
    *,
    cards_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    """Write all four outputs. Returns map of artifact name -> path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = run.model_slug
    queue_amb = output_dir / f"{slug}.needs_arbitration.yaml"
    queue_nf = output_dir / f"{slug}.not_found.yaml"
    coverage = output_dir / f"{slug}.coverage.md"
    provenance = output_dir / f"{slug}.curation_run.json"

    write_cards_yaml(run, cards_path)
    write_queue(run.outcomes, queue_amb, kind="AMBIGUOUS")
    write_queue(run.outcomes, queue_nf, kind="NOT_FOUND")
    write_coverage_md(run, coverage)
    write_provenance(run, provenance)
    return {
        "cards": cards_path,
        "needs_arbitration": queue_amb,
        "not_found": queue_nf,
        "coverage": coverage,
        "provenance": provenance,
    }
