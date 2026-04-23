"""CLI: verify a manifest's paper pairing via NCBI eutils.

Confirms that the PubMed ID claimed by the SBML annotations resolves to the
DOI claimed by the manifest.  Optionally writes a structured
``paper.verification`` block back into the manifest, and (with --update)
auto-fills ``paper.doi`` when it was empty.

Examples:
    # Verify (read-only)
    python tools/verify_paper_pairing.py \\
        --manifest manifests/chassagnole2002.draft.yaml

    # Verify and update the manifest in place (writes paper.verification + doi)
    python tools/verify_paper_pairing.py \\
        --manifest manifests/chassagnole2002.draft.yaml \\
        --update

    # Use only cached eutils response (no network)
    python tools/verify_paper_pairing.py \\
        --manifest manifests/chassagnole2002.draft.yaml \\
        --offline

    # Force re-fetch from NCBI (overwrites any cached response)
    python tools/verify_paper_pairing.py \\
        --manifest manifests/chassagnole2002.draft.yaml --refresh

Exit codes:
    0  pairing verified
    2  manifest schema/data problem (missing pubmed id, ambiguous pmid, ...)
    3  network error / offline mode and no cache
    4  DOI MISMATCH between manifest and eutils
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from opencell.manifest.pairing import (  # noqa: E402
    PairingError,
    verify_paper_pairing,
)


def _write_back(manifest_path: Path, manifest_data: dict, result) -> None:
    """Persist verification block (and possibly doi) back to the YAML file."""
    paper = manifest_data.setdefault("paper", {})
    if result.auto_filled_doi:
        paper["doi"] = result.auto_filled_doi
    if result.verification is not None:
        paper["verification"] = result.verification.to_dict()
    # Preserve `paper` key order: keep doi/biomodels_id/pubmed_id at top
    manifest_path.write_text(
        yaml.dump(manifest_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Verify manifest paper pairing via NCBI eutils",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--manifest", required=True, help="Path to manifest YAML")
    p.add_argument("--cache-dir", default=".paper_cache",
                   help="Directory for cached eutils responses (default: .paper_cache)")
    p.add_argument("--offline", action="store_true",
                   help="Use only cached responses; never touch the network")
    p.add_argument("--refresh", action="store_true",
                   help="Force re-fetch from NCBI even if a cache exists")
    p.add_argument("--update", action="store_true",
                   help="Write paper.verification (and auto-filled doi) back to the manifest")
    args = p.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    manifest_data = yaml.safe_load(manifest_path.read_text()) or {}

    try:
        result = verify_paper_pairing(
            manifest_data,
            cache_dir=Path(args.cache_dir),
            refresh=args.refresh,
            offline=args.offline,
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except PairingError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 (CLI surface)
        print(f"error: eutils fetch failed: {e}", file=sys.stderr)
        print("       hint: re-run with --offline if a cached response exists",
              file=sys.stderr)
        return 3

    print(result.message)
    if result.verification:
        v = result.verification
        print(f"  pubmed_id     : {v.pubmed_id}")
        print(f"  doi           : {v.doi}")
        print(f"  title         : {v.title}")
        print(f"  first_author  : {v.first_author}")
        print(f"  year          : {v.year}")
        print(f"  journal       : {v.journal}")
        print(f"  cache         : {v.cache_path}")
        print(f"  response_sha  : {v.response_sha256[:16]}...")

    if not result.ok:
        if "MISMATCH" in result.message:
            return 4
        return 2

    if args.update:
        _write_back(manifest_path, manifest_data, result)
        if result.auto_filled_doi:
            print(f"  -> wrote paper.doi = {result.auto_filled_doi!r}")
        print(f"  -> wrote paper.verification block to {manifest_path}")
    else:
        print("  (re-run with --update to persist verification to the manifest)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
