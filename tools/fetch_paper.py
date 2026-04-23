"""Fetch published papers and extract text for parameter verification.

Resolution chain (tries in order):
1. NCBI ID Converter: DOI -> PMC ID -> free full text via PMC EFetch
2. Europe PMC fullTextXML (sometimes broader than US PMC)
3. Local PDF (--pdf path) extracted with pypdf

The fetched text is cached under .paper_cache/<doi-slug>.txt so subsequent
verifications are offline.

Usage
-----
    # Open access paper:
    python tools/fetch_paper.py 10.1073/pnas.151588598

    # Search the cached text:
    python tools/fetch_paper.py 10.1073/pnas.151588598 --grep "k_1"

    # Paywalled paper -- download PDF manually, then:
    python tools/fetch_paper.py 10.1073/pnas.151588598 --pdf ~/Downloads/thattai.pdf
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CACHE_DIR = Path(".paper_cache")
USER_AGENT = "OpenCell-PaperFetcher/0.2 (https://github.com/opencell)"


def _slug(doi: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", doi).strip("_")


def _http_get(url: str, accept: str = "*/*", timeout: int = 60) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def doi_to_pmcid(doi: str) -> str | None:
    """Resolve a DOI to a PMC ID via NCBI's ID Converter API."""
    url = (
        "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        + "?ids=" + urllib.parse.quote(doi)
        + "&format=json"
    )
    try:
        data = json.loads(_http_get(url, accept="application/json"))
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"[fetch_paper] id-converter failed: {e}", file=sys.stderr)
        return None
    records = data.get("records", [])
    if not records:
        return None
    return records[0].get("pmcid")


def fetch_pmc_xml(pmcid: str) -> str:
    """Fetch full-text XML from PMC OAI service (no paywall, no captcha)."""
    pmc_num = pmcid.replace("PMC", "")
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        + "?db=pmc&id=" + pmc_num
        + "&rettype=xml"
    )
    return _http_get(url, accept="application/xml").decode("utf-8", errors="replace")


def xml_to_text(xml: str) -> str:
    """Strip XML tags to plain text, preserving structure markers."""
    text = re.sub(r"<title[^>]*>", "\n\n## ", xml)
    text = re.sub(r"</title>", "\n", text)
    text = re.sub(r"<sec[^>]*>", "\n", text)
    text = re.sub(r"<p[^>]*>", "\n", text)
    text = re.sub(r"<table-wrap[^>]*>", "\n[TABLE]\n", text)
    text = re.sub(r"</table-wrap>", "\n[/TABLE]\n", text)
    text = re.sub(r"<fig[^>]*>", "\n[FIGURE]\n", text)
    text = re.sub(r"</fig>", "\n[/FIGURE]\n", text)
    text = re.sub(r"<caption[^>]*>", "\n[CAPTION] ", text)
    text = re.sub(r"</caption>", "\n[/CAPTION]\n", text)
    text = re.sub(r"<label[^>]*>", "\n[LABEL] ", text)
    text = re.sub(r"</label>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    # Normalize whitespace
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_europepmc_xml(pmcid: str) -> str | None:
    """Try Europe PMC fullTextXML — sometimes available when US PMC is not."""
    pmc_num = pmcid.replace("PMC", "")
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/PMC{pmc_num}/fullTextXML"
    try:
        body = _http_get(url, accept="application/xml")
    except urllib.error.URLError as e:
        print(f"[fetch_paper] europepmc failed: {e}", file=sys.stderr)
        return None
    if not body or len(body) < 500:
        return None
    return body.decode("utf-8", errors="replace")


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a local PDF using pypdf."""
    try:
        import pypdf
    except ImportError:
        raise RuntimeError(
            "pypdf is not installed. Run: pip install pypdf"
        )
    reader = pypdf.PdfReader(str(pdf_path))
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        parts.append(f"\n[PAGE {i}]\n")
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:  # noqa: BLE001
            parts.append(f"[extraction failed: {e}]")
    return "\n".join(parts)


def fetch_paper(
    doi: str,
    force: bool = False,
    pdf_path: Path | None = None,
) -> tuple[str, str]:
    """Return (source, text) for a DOI. Caches under .paper_cache/."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / f"{_slug(doi)}.txt"
    if cache.exists() and not force:
        return ("cache", cache.read_text(encoding="utf-8"))

    # Route 1: explicit local PDF
    if pdf_path is not None:
        if not pdf_path.exists():
            raise RuntimeError(f"PDF not found: {pdf_path}")
        print(f"[fetch_paper] extracting local PDF: {pdf_path}", file=sys.stderr)
        text = extract_pdf_text(pdf_path)
        cache.write_text(text, encoding="utf-8")
        return (f"local-pdf ({pdf_path.name})", text)

    # Route 2: PMC + Europe PMC
    pmcid = doi_to_pmcid(doi)
    if pmcid:
        print(f"[fetch_paper] DOI {doi} -> {pmcid}", file=sys.stderr)
        # Try Europe PMC first (broader full-text coverage)
        epmc = fetch_europepmc_xml(pmcid)
        if epmc:
            text = xml_to_text(epmc)
            if len(text) > 5000:  # reasonable full-text threshold
                cache.write_text(text, encoding="utf-8")
                return (f"EuropePMC ({pmcid})", text)
        # Fall back to US PMC
        xml = fetch_pmc_xml(pmcid)
        text = xml_to_text(xml)
        cache.write_text(text, encoding="utf-8")
        if len(text) < 5000:
            print(
                f"[fetch_paper] WARNING: only {len(text)} chars retrieved "
                "(likely abstract-only). Paper may not be open-access. "
                "Download PDF manually and re-run with --pdf <path>.",
                file=sys.stderr,
            )
        return (f"PMC ({pmcid})", text)

    raise RuntimeError(
        f"Could not resolve DOI {doi} to a free full-text source. "
        "Download the PDF manually and run with --pdf <path>."
    )


def grep_text(text: str, pattern: str, context: int = 2) -> list[str]:
    """Return matching lines with surrounding context."""
    lines = text.splitlines()
    rx = re.compile(pattern, re.IGNORECASE)
    hits = []
    for i, line in enumerate(lines):
        if rx.search(line):
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            chunk = "\n".join(
                f"{j+1:5d}{'>' if j == i else ' '} {lines[j]}"
                for j in range(start, end)
            )
            hits.append(chunk)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch a paper by DOI and extract text.")
    ap.add_argument("doi", help="DOI, e.g., 10.1073/pnas.151588598")
    ap.add_argument("--pdf", type=Path, help="Path to a locally-downloaded PDF (overrides web fetch)")
    ap.add_argument("--grep", help="Regex pattern to search for in extracted text")
    ap.add_argument("--context", type=int, default=2, help="Lines of context around grep hits")
    ap.add_argument("--output", help="Write full text to this file")
    ap.add_argument("--force", action="store_true", help="Re-fetch ignoring cache")
    args = ap.parse_args()

    try:
        source, text = fetch_paper(args.doi, force=args.force, pdf_path=args.pdf)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"[fetch_paper] source: {source}, length: {len(text):,} chars", file=sys.stderr)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[fetch_paper] wrote full text to {args.output}", file=sys.stderr)

    if args.grep:
        hits = grep_text(text, args.grep, context=args.context)
        if not hits:
            print(f"No matches for {args.grep!r}", file=sys.stderr)
            return 2
        for h in hits:
            print(h)
            print("---")
        return 0

    if not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
