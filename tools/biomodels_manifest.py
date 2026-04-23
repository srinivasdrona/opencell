"""CLI: SBML → parameter-extraction-manifest.

Usage:
    # Offline (recommended): SBML already in cache
    python tools/biomodels_manifest.py \\
        --sbml-path .paper_cache/BIOMD0000000051.xml \\
        --paper-doi 10.1002/bit.10288 \\
        --biomodels-id BIOMD0000000051 \\
        --organism "Escherichia coli K-12" \\
        --condition "glucose-limited continuous culture, mu=0.1 h^-1" \\
        --pdf-cache .paper_cache/chassagnole2002.txt \\
        --model-slug chassagnole2002 \\
        --output data/manifests/chassagnole2002.yaml

    # Online (when network allows): download SBML by BIOMD id first
    python tools/biomodels_manifest.py \\
        --biomodels-id BIOMD0000000051 \\
        --download-to .paper_cache/BIOMD0000000051.xml \\
        --paper-doi 10.1002/bit.10288 \\
        --output data/manifests/chassagnole2002.yaml

    # Skip species (only kinetic parameters, no initial concentrations)
    python tools/biomodels_manifest.py ... --no-species

If the BioModels API is blocked (HTTP 403 from Cloudflare-class WAF, common
from CI/cloud/CLI environments), use the GitHub mirror instead:

    git clone --depth 1 https://github.com/biomodels/BIOMD0000000051.git
    cp BIOMD0000000051/BIOMD0000000051/BIOMD0000000051.xml .paper_cache/

The EBI publishes a per-model git repo under github.com/biomodels/* that
mirrors the same SBML released by the BioModels database, without going
through the WAF-protected web/API.

Auto-fill: explicit --paper-doi / --biomodels-id / --organism flags are
honored as-is. When omitted, the tool extracts these from the SBML's
embedded MIRIAM annotations (bqmodel:is, bqmodel:isDescribedBy,
bqbiol:hasTaxon) when available.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from opencell.manifest import (  # noqa: E402
    ManifestHeader,
    build_manifest,
    extract_metadata,
    parse_sbml,
    write_manifest_yaml,
)


def _maybe_download(biomd_id: str, dest: Path) -> bool:
    """Best-effort download.  Returns True if dest now contains valid SBML."""
    from opencell.extraction.biomodels import download_sbml
    sbml = download_sbml(biomd_id)
    if not sbml or not sbml.lstrip().startswith(b"<"):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(sbml)
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="SBML -> parameter-extraction-manifest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="If BioModels API is blocked, try: "
               "git clone https://github.com/biomodels/<BIOMD_ID>.git",
    )
    p.add_argument("--sbml-path", help="Path to local SBML XML file (preferred)")
    p.add_argument("--biomodels-id", default="", help="BioModels ID (e.g. BIOMD0000000051)")
    p.add_argument("--download-to", default="", help="If set with --biomodels-id, attempt download")
    p.add_argument("--paper-doi", default="", help="Source paper DOI")
    p.add_argument("--organism", default="")
    p.add_argument("--condition", default="")
    p.add_argument("--pdf-cache", action="append", default=[], help="Path(s) to PDF text cache (repeatable)")
    p.add_argument("--model-slug", default="", help="Short identifier for parameter_id prefixing")
    p.add_argument("--no-species", action="store_true", help="Skip species initial concentrations")
    p.add_argument("--no-auto-metadata", action="store_true",
                   help="Disable MIRIAM-annotation auto-fill of paper.doi/biomodels_id/organism")
    p.add_argument("--output", required=True, help="Output YAML path")
    args = p.parse_args(argv)

    sbml_path = Path(args.sbml_path) if args.sbml_path else None
    if sbml_path is None and args.biomodels_id and args.download_to:
        dl = Path(args.download_to)
        if _maybe_download(args.biomodels_id, dl):
            sbml_path = dl
            print(f"[ok] downloaded SBML to {dl}", file=sys.stderr)
        else:
            print(f"[fail] could not download SBML for {args.biomodels_id}", file=sys.stderr)
            print(f"       try the GitHub mirror instead:", file=sys.stderr)
            print(f"       git clone https://github.com/biomodels/{args.biomodels_id}.git",
                  file=sys.stderr)
            return 3

    if sbml_path is None or not sbml_path.exists():
        print("error: provide --sbml-path or working --biomodels-id + --download-to",
              file=sys.stderr)
        return 2

    sbml_bytes = sbml_path.read_bytes()
    entities, udefs = parse_sbml(sbml_bytes, include_species=not args.no_species)

    # Auto-fill metadata from SBML MIRIAM annotations (CLI flags win).
    md = None if args.no_auto_metadata else extract_metadata(sbml_bytes)
    auto_filled: list[str] = []

    def _pick(cli_value: str, sbml_value: str, label: str) -> str:
        if cli_value:
            return cli_value
        if sbml_value:
            auto_filled.append(f"{label}={sbml_value!r}")
            return sbml_value
        return ""

    paper_doi = _pick(args.paper_doi, md.doi if md else "", "doi")
    biomodels_id = _pick(args.biomodels_id, md.biomodels_id if md else "", "biomodels_id")
    organism = _pick(args.organism, md.organism if md else "", "organism")

    slug = args.model_slug or sbml_path.stem.lower()
    notes = f"Auto-generated by tools/biomodels_manifest.py from {sbml_path.name}"
    if md:
        if md.pubmed_id:
            notes += f"; pubmed:{md.pubmed_id}"
        if md.taxonomy_id and not organism:
            notes += f"; taxonomy:{md.taxonomy_id} (unmapped)"
    header = ManifestHeader(
        doi=paper_doi,
        biomodels_id=biomodels_id,
        pubmed_id=(md.pubmed_id if md else ""),
        pdf_cache=args.pdf_cache,
        organism=organism,
        condition=args.condition,
        notes=notes,
    )
    manifest = build_manifest(entities, header=header, model_slug=slug)
    write_manifest_yaml(manifest, args.output)

    n_global = sum(1 for e in entities if e.kind == "global_parameter")
    n_local = sum(1 for e in entities if e.kind == "local_parameter")
    n_species = sum(1 for e in entities if e.kind == "species_initial")
    n_total = len(manifest["parameters"])
    n_units = len(udefs)

    print(f"=== Manifest written: {args.output} ===")
    print(f"  total entries        : {n_total}")
    print(f"  global parameters    : {n_global}")
    print(f"  local kinetic params : {n_local}")
    print(f"  species initials     : {n_species}")
    print(f"  unit definitions     : {n_units}")
    if auto_filled:
        print(f"  auto-filled from SBML: {', '.join(auto_filled)}")
    if md and md.pubmed_id and not paper_doi:
        print(f"  NOTE: SBML has pubmed:{md.pubmed_id} but no DOI annotation;")
        print(f"        look up the DOI manually and rerun with --paper-doi")
    print()
    print("NEXT STEPS:")
    print("  1. Open the YAML and prune entries you don't need")
    print("  2. Fill 'symbol' fields where SBML id != paper symbol")
    print("  3. Add 'gene_or_enzyme' annotations where helpful")
    print("  4. Run: python tools/curate_params.py --manifest <path>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

