"""Curation runner: orchestrate extraction across all manifest entries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from opencell.data.verification import (
    ParameterCard,
    VerificationStatus,
    load_cards_from_yaml,
)
from opencell.extraction import ExtractionResult, ParameterSpec, extract_parameter

from .manifest import CurationManifest, ManifestParameter
from .value_match import CrossCheck, cross_check


@dataclass
class CurationOutcome:
    """Result for one manifest entry."""

    parameter_id: str
    symbol: str
    status: (
        str  # RECOMMEND | AMBIGUOUS | NOT_FOUND | ALL_REJECTED | SKIPPED_EXISTS | SKIPPED_LOCKED
    )
    extraction: ExtractionResult | None = None
    card: ParameterCard | None = None
    note: str = ""
    cross_check: CrossCheck | None = None  # PDF-vs-SBML cross-check (when applicable)


@dataclass
class CurationRun:
    model_slug: str
    doi: str
    started_at: str
    finished_at: str = ""
    outcomes: list[CurationOutcome] = field(default_factory=list)
    cache_file_sha256: dict[str, str] = field(default_factory=dict)
    manifest_path: str = ""

    @property
    def by_status(self) -> dict[str, list[CurationOutcome]]:
        out: dict[str, list[CurationOutcome]] = {}
        for o in self.outcomes:
            out.setdefault(o.status, []).append(o)
        return out

    @property
    def coverage(self) -> dict[str, int]:
        counts = {k: len(v) for k, v in self.by_status.items()}
        counts["TOTAL"] = len(self.outcomes)
        return counts


_LOCKED_STATUSES = {VerificationStatus.REVIEWED, VerificationStatus.APPROVED}


def _read_existing_cards(path: Path) -> dict[str, ParameterCard]:
    if not path.exists():
        return {}
    cards = load_cards_from_yaml(path)
    return {c.parameter_id: c for c in cards}


def _build_draft_card(
    entry: ManifestParameter,
    manifest: CurationManifest,
    result: ExtractionResult,
    xc: CrossCheck | None = None,
) -> ParameterCard | None:
    rec = result.recommendation
    if rec is None:
        return None
    trace_lines = [
        f"Auto-extracted by opencell.curation on {datetime.now(UTC).date()}.",
        f"Method: {rec.method}",
        f"Locator: {rec.locator}",
        f"Score: {rec.score:.2f} (components: {rec.score_components})",
    ]
    if rec.source_path:
        trace_lines.append(f"Source: {rec.source_path}")
    if rec.source_sha256:
        trace_lines.append(f"SHA-256: {rec.source_sha256}")
    if xc is not None:
        trace_lines.append(
            f"Cross-check (PDF vs SBML): status={xc.status}"
            + (
                f", pdf={xc.pdf_value!r}, sbml={xc.sbml_value!r}, rel_diff={xc.rel_diff:.3g}"
                if xc.rel_diff is not None
                else ""
            )
        )
    trace_lines.append(f"Context: ...{rec.context_window.strip()[:300]}...")
    rationale = "\n".join(trace_lines)

    final_value = rec.converted_value if rec.converted_value is not None else rec.raw_value
    final_unit = rec.converted_unit or rec.raw_unit_normalized

    return ParameterCard(
        parameter_id=entry.parameter_id,
        name=entry.name,
        value=final_value,
        unit=final_unit,
        source_doi=manifest.doi,
        source_type="measured" if rec.method == "biomodels_sbml" else "assumed",
        source_table=rec.locator,
        original_quote=rec.context_window.strip()[:500],
        original_value=rec.raw_value,
        original_unit=rec.raw_unit_normalized,
        transformation=rec.transformation,
        organism=entry.organism,
        condition=entry.condition,
        compartment=entry.compartment,
        gene_or_enzyme=entry.gene_or_enzyme,
        status=VerificationStatus.DRAFT,
        selection_rationale=rationale,
    )


ExtractFn = Callable[[ParameterSpec], ExtractionResult]


def run_curation(
    manifest: CurationManifest,
    *,
    output_cards_path: Path | None = None,
    force: bool = False,
    use_biomodels: bool = True,
    extract_fn: ExtractFn = extract_parameter,
) -> CurationRun:
    """Run the curator on every entry of the manifest.

    Args:
      manifest: validated CurationManifest.
      output_cards_path: existing cards YAML; entries already present are
        skipped unless force=True. Cards at REVIEWED/APPROVED status are
        ALWAYS protected (never overwritten regardless of force).
      force: if True, re-extract DRAFT entries that already exist.
      use_biomodels: passed through to ParameterSpec.
      extract_fn: dependency injection for tests (default: real pipeline).
    """
    started = datetime.now(UTC).isoformat(timespec="seconds")
    if not manifest.doi:
        raise ValueError(
            "manifest.paper.doi is empty; cannot run curation. "
            "Run `python tools/verify_paper_pairing.py --manifest <path> --update` "
            "to auto-fill it from PubMed, or fill it manually."
        )
    existing = _read_existing_cards(output_cards_path) if output_cards_path else {}

    outcomes: list[CurationOutcome] = []
    for entry in manifest.parameters:
        prior = existing.get(entry.parameter_id)
        if prior is not None and prior.status in _LOCKED_STATUSES:
            outcomes.append(
                CurationOutcome(
                    parameter_id=entry.parameter_id,
                    symbol=entry.symbol,
                    status="SKIPPED_LOCKED",
                    note=f"existing card has status {prior.status.value}; refusing to overwrite",
                )
            )
            continue
        if prior is not None and not force:
            outcomes.append(
                CurationOutcome(
                    parameter_id=entry.parameter_id,
                    symbol=entry.symbol,
                    status="SKIPPED_EXISTS",
                    note="existing DRAFT card present; pass force=True to re-extract",
                )
            )
            continue

        spec = ParameterSpec(
            symbol=entry.symbol,
            doi=manifest.doi,
            target_unit=entry.target_unit,
            name=entry.name,
            organism=entry.organism,
            condition=entry.condition,
            cache_files=manifest.cache_files_for(entry),
            use_biomodels=use_biomodels,
        )
        result = extract_fn(spec)
        status = result.status
        rec = result.recommendation
        # Cross-check: only run when we have a recommendation and a curated SBML value.
        xc = (
            cross_check(rec, entry.sbml_value)
            if (rec is not None or entry.sbml_value is not None)
            else None
        )
        # Guardrail: if PDF and SBML disagree, downgrade RECOMMEND -> AMBIGUOUS so
        # the mismatch is never silently auto-approved as a draft card.
        downgrade_note = ""
        if xc is not None and xc.disagrees and status == "RECOMMEND":
            status = "AMBIGUOUS"
            downgrade_note = (
                f"downgraded from RECOMMEND because PDF value "
                f"{xc.pdf_value!r} disagrees with SBML value {xc.sbml_value!r} "
                f"(rel_diff={xc.rel_diff:.3g}, tol={xc.rel_tol})"
            )
        card = _build_draft_card(entry, manifest, result, xc) if status == "RECOMMEND" else None
        outcomes.append(
            CurationOutcome(
                parameter_id=entry.parameter_id,
                symbol=entry.symbol,
                status=status,
                extraction=result,
                card=card,
                cross_check=xc,
                note=downgrade_note,
            )
        )

    return CurationRun(
        model_slug=manifest.model_slug,
        doi=manifest.doi,
        started_at=started,
        finished_at=datetime.now(UTC).isoformat(timespec="seconds"),
        outcomes=outcomes,
        cache_file_sha256=dict(manifest.cache_file_sha256),
        manifest_path=manifest.source_manifest_path,
    )
