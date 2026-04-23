"""CLI for deterministic parameter extraction.

Usage examples:
    # Extract Thattai 2001 transcription rate from cached PDF
    python tools/extract_param.py \\
        --doi 10.1073/pnas.151588598 \\
        --symbol kR \\
        --target-unit "min^-1" \\
        --pdf-cache .paper_cache/thattai2001_full.txt \\
        --name "Transcription initiation rate" \\
        --organism "generic prokaryotic gene" \\
        --condition "Thattai 2001 base case" \\
        --parameter-id thattai2001-k1-extracted

    # Save DRAFT card to YAML (only emitted if recommendation exists)
    python tools/extract_param.py ... --output-yaml /tmp/draft.yaml

    # Disable BioModels lookup (offline, faster, deterministic)
    python tools/extract_param.py ... --no-biomodels

Exit codes:
    0  RECOMMEND  — single semantic match found, DRAFT card emitted
    1  AMBIGUOUS  — multiple plausible candidates, human must choose
    2  NOT_FOUND  — no candidate matched
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Make sure the package is importable when running as a script
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from opencell.data.verification import (  # noqa: E402
    ParameterCard,
    VerificationStatus,
    save_cards_to_yaml,
)
from opencell.extraction import (  # noqa: E402
    ExtractionResult,
    ParameterSpec,
    extract_parameter,
)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_candidate(idx: int, c, *, indent: str = "  ") -> None:
    status = "✗" if c.rejected else "✓"
    line = f"{indent}[{idx}] {status} value={c.raw_value!r} unit={c.raw_unit_normalized!r}"
    line += f"  score={c.score:.2f}  method={c.method}"
    print(line)
    print(f"{indent}     locator: {c.locator}    section: {c.section_type.value}")
    if c.converted_value is not None:
        print(f"{indent}     → {c.converted_value:g} {c.converted_unit}  ({c.transformation})")
    if c.rejection_reason:
        print(f"{indent}     REJECTED: {c.rejection_reason}")
    # Trim context window for display
    ctx = c.context_window.replace("\n", " ⏎ ")
    if len(ctx) > 240:
        ctx = ctx[:120] + " … " + ctx[-120:]
    print(f"{indent}     context: …{ctx}…")
    print()


def print_report(result: ExtractionResult) -> None:
    print("=" * 72)
    print(f"PARAMETER EXTRACTION  symbol={result.parameter_symbol!r}  doi={result.parameter_doi!r}")
    print(f"target_unit={result.target_unit!r}")
    print(f"methods attempted: {', '.join(result.methods_attempted) or '(none)'}")
    print(f"cache files:       {', '.join(result.cache_files) or '(none)'}")
    if result.notes:
        print("notes:")
        for n in result.notes:
            print(f"  - {n}")
    print()

    survivors = result.surviving
    rejected = result.rejected
    print(f"SURVIVORS: {len(survivors)}    REJECTED: {len(rejected)}    STATUS: {result.status}")
    print()

    if survivors:
        print("--- Surviving candidates ---")
        for i, c in enumerate(survivors):
            _print_candidate(i, c)

    if rejected:
        print("--- Rejected candidates (audit trail) ---")
        for i, c in enumerate(rejected):
            _print_candidate(i, c)

    rec = result.recommendation
    if rec is not None:
        print("=== RECOMMENDATION ===")
        print(f"  raw value : {rec.raw_value} {rec.raw_unit_normalized}")
        if rec.converted_value is not None:
            print(f"  converted : {rec.converted_value:g} {rec.converted_unit}")
        print(f"  locator   : {rec.locator}")
        print(f"  score     : {rec.score:.2f}  components: {rec.score_components}")
    else:
        print("=== NO AUTOMATIC RECOMMENDATION ===")
        print("  Either zero survivors, multiple disagreeing values, or low confidence.")
        print("  Inspect candidates above and curate manually.")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Card emission
# ---------------------------------------------------------------------------

def build_draft_card(args: argparse.Namespace, result: ExtractionResult) -> ParameterCard | None:
    """Build a DRAFT ParameterCard from the recommended candidate, if any."""
    rec = result.recommendation
    if rec is None:
        return None

    # Fold extraction trace into selection_rationale (no schema change needed).
    trace_lines = [
        f"Auto-extracted by {rec.extractor_version or 'opencell.extraction'} on {date.today()}.",
        f"Method: {rec.method}",
        f"Locator: {rec.locator}",
        f"Score: {rec.score:.2f} (components: {rec.score_components})",
    ]
    if rec.source_path:
        trace_lines.append(f"Source: {rec.source_path}")
    if rec.source_sha256:
        trace_lines.append(f"SHA-256: {rec.source_sha256}")
    trace_lines.append(f"Context: …{rec.context_window.strip()[:300]}…")
    rationale = "\n".join(trace_lines)

    final_value = rec.converted_value if rec.converted_value is not None else rec.raw_value
    final_unit = rec.converted_unit or rec.raw_unit_normalized

    return ParameterCard(
        parameter_id=args.parameter_id,
        name=args.name,
        value=final_value,
        unit=final_unit,
        source_doi=args.doi,
        source_type="measured" if rec.method == "biomodels_sbml" else "assumed",
        source_table=rec.locator,
        original_quote=rec.context_window.strip()[:500],
        original_value=rec.raw_value,
        original_unit=rec.raw_unit_normalized,
        transformation=rec.transformation,
        organism=args.organism,
        condition=args.condition,
        compartment=args.compartment,
        gene_or_enzyme=args.gene,
        status=VerificationStatus.DRAFT,
        selection_rationale=rationale,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deterministic parameter extraction.")
    p.add_argument("--doi", required=True, help="Source DOI, e.g. 10.1073/pnas.151588598")
    p.add_argument("--symbol", required=True, help="Symbol as written in paper, e.g. kR or k_R")
    p.add_argument("--target-unit", default="", help="Desired output unit (e.g. min^-1)")
    p.add_argument("--pdf-cache", action="append", default=[], help="Path to cached PDF text (repeatable)")
    p.add_argument("--no-biomodels", action="store_true", help="Skip BioModels lookup")
    p.add_argument("--parameter-id", default="", help="parameter_id for emitted DRAFT card")
    p.add_argument("--name", default="", help="Human-readable parameter name")
    p.add_argument("--organism", default="", help="Organism context")
    p.add_argument("--condition", default="", help="Experimental/model condition")
    p.add_argument("--compartment", default="", help="Cellular compartment")
    p.add_argument("--gene", default="", help="Gene or enzyme identity")
    p.add_argument("--output-yaml", default="", help="If set and recommendation exists, append DRAFT card to this YAML file")
    args = p.parse_args(argv)

    spec = ParameterSpec(
        symbol=args.symbol,
        doi=args.doi,
        target_unit=args.target_unit,
        name=args.name,
        organism=args.organism,
        condition=args.condition,
        cache_files=args.pdf_cache,
        use_biomodels=not args.no_biomodels,
    )
    result = extract_parameter(spec)
    print_report(result)

    if args.output_yaml and args.parameter_id:
        card = build_draft_card(args, result)
        if card is not None:
            out = Path(args.output_yaml)
            existing = []
            if out.exists():
                from opencell.data.verification import load_cards_from_yaml
                existing = load_cards_from_yaml(out)
            existing.append(card)
            save_cards_to_yaml(existing, out)
            print(f"\nDRAFT card written: {out} (total cards: {len(existing)})")

    status = result.status
    return {"RECOMMEND": 0, "AMBIGUOUS": 1, "NOT_FOUND": 2, "ALL_REJECTED": 2}.get(status, 1)


if __name__ == "__main__":
    sys.exit(main())
