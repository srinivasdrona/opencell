"""Paper-pairing verifier: confirm SBML's claimed paper is actually that paper.

Pipeline:
  manifest.paper.pubmed_id  --eutils-->  {doi, title, first_author, year, journal}
  → compare against manifest.paper.doi (loud failure on mismatch)
  → write structured `paper.verification` block back to manifest

Why this exists: BioModels SBML annotations claim a PubMed ID via
<bqmodel:isDescribedBy>. We want machine-verifiable proof that:
  (a) the PubMed ID actually resolves
  (b) its DOI matches what the manifest says (or, if manifest.doi was
      blank, auto-fill it)
  (c) the paper title/authors match what a human would expect
  (d) the eutils response itself is hashed for future audit

Network: NCBI eutils esummary, JSON.  Cached by pubmed-id under
``.paper_cache/eutils-pubmed-{ID}.json`` for offline reproducibility.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Match "10.xxxx/..." anywhere in a string (DOI grammar is permissive but
# always begins with "10." followed by a registrant prefix and "/").
_DOI_RX = re.compile(r"10\.\d{4,9}/[\w.\-;()/:]+", re.IGNORECASE)
_PUBMED_NOTES_RX = re.compile(r"pubmed[:\s]\s*(\d+)", re.IGNORECASE)

EUTILS_ESUMMARY_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    "?db=pubmed&id={pmid}&retmode=json"
)


class PairingError(RuntimeError):
    """Raised when the manifest claims a DOI that disagrees with eutils."""


@dataclass
class PairingVerification:
    """Structured record written back to manifest.paper.verification."""

    source: str = "ncbi-eutils"
    verified_at: str = ""
    pubmed_id: str = ""
    doi: str = ""
    title: str = ""
    first_author: str = ""
    year: str = ""
    journal: str = ""
    response_sha256: str = ""
    cache_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_doi(d: str) -> str:
    """Lowercase + strip 'doi:'/'https://doi.org/'/whitespace prefixes."""
    if not d:
        return ""
    s = d.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    return s


def extract_pubmed_ids(paper_block: dict, fallback_notes: str = "") -> list[str]:
    """Return all PubMed IDs declared in the manifest paper block.

    Preference order:
      1. structured `paper.pubmed_id` (string or list)
      2. regex-extracted from `paper.notes` (back-compat for older drafts)

    Returns a list with duplicates removed, preserving order.
    """
    raw = paper_block.get("pubmed_id")
    ids: list[str] = []
    if isinstance(raw, (int, str)) and str(raw).strip():
        ids.append(str(raw).strip())
    elif isinstance(raw, list):
        for item in raw:
            if str(item).strip():
                ids.append(str(item).strip())
    if not ids:
        notes = paper_block.get("notes") or fallback_notes or ""
        ids.extend(_PUBMED_NOTES_RX.findall(notes))
    # Dedup-preserve-order
    seen: set[str] = set()
    out: list[str] = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def fetch_eutils(
    pubmed_id: str,
    *,
    cache_dir: Path,
    refresh: bool = False,
    offline: bool = False,
    timeout: float = 20.0,
) -> tuple[dict, Path, str, bool]:
    """Fetch the eutils esummary JSON for a PubMed ID.

    Returns (parsed_json, cache_path, sha256_of_bytes, was_cached).

    If a cache file exists and not refresh, returns cached. If offline and no
    cache, raises FileNotFoundError. Otherwise calls NCBI and writes cache.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"eutils-pubmed-{pubmed_id}.json"
    if cache_path.exists() and not refresh:
        raw = cache_path.read_bytes()
        return json.loads(raw), cache_path, hashlib.sha256(raw).hexdigest(), True
    if offline:
        raise FileNotFoundError(
            f"offline mode and no cache at {cache_path}; "
            f"re-run without --offline to populate the cache"
        )
    url = EUTILS_ESUMMARY_URL.format(pmid=pubmed_id)
    req = urllib.request.Request(url, headers={"User-Agent": "opencell/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
        raw = resp.read()
    cache_path.write_bytes(raw)
    return json.loads(raw), cache_path, hashlib.sha256(raw).hexdigest(), False


def parse_eutils_payload(payload: dict, pubmed_id: str) -> PairingVerification:
    """Pull canonical fields out of an esummary JSON payload."""
    result = (payload or {}).get("result") or {}
    record = result.get(pubmed_id) or {}
    if not record:
        raise PairingError(
            f"eutils returned no record for pubmed:{pubmed_id} "
            f"(payload keys: {sorted(result.keys())[:5]})"
        )
    # DOI may appear under articleids[].
    doi = ""
    for entry in record.get("articleids", []):
        if (entry.get("idtype") or "").lower() == "doi":
            doi = (entry.get("value") or "").strip()
            break
    pub = record.get("pubdate") or ""
    year = pub.split(" ", 1)[0] if pub else ""
    authors = record.get("authors") or []
    first_author = (authors[0].get("name") if authors else "") or ""
    return PairingVerification(
        source="ncbi-eutils",
        verified_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        pubmed_id=pubmed_id,
        doi=doi,
        title=(record.get("title") or "").strip(),
        first_author=first_author,
        year=year,
        journal=(record.get("source") or record.get("fulljournalname") or "").strip(),
    )


# ---------------------------------------------------------------------------
# Top-level verify
# ---------------------------------------------------------------------------

@dataclass
class VerifyResult:
    ok: bool
    message: str
    verification: PairingVerification | None = None
    auto_filled_doi: str = ""           # populated when manifest doi was blank
    pubmed_ids_found: list[str] = field(default_factory=list)


def verify_paper_pairing(
    manifest_data: dict,
    *,
    cache_dir: Path,
    refresh: bool = False,
    offline: bool = False,
) -> VerifyResult:
    """Perform the full pairing check against eutils.

    Args:
      manifest_data: the parsed YAML manifest dict (NOT a CurationManifest).
      cache_dir: where to read/write eutils JSON caches.
      refresh: if True, ignore any existing cache and re-fetch.
      offline: if True, fail rather than touch the network.

    Returns:
      VerifyResult.ok is True iff a pubmed_id resolved AND its DOI matches
      manifest.paper.doi (or manifest.paper.doi was empty).
    """
    paper = manifest_data.get("paper") or {}
    pmids = extract_pubmed_ids(paper)
    if not pmids:
        return VerifyResult(
            ok=False,
            message=(
                "no PubMed ID found in manifest.paper.pubmed_id or paper.notes; "
                "cannot verify pairing"
            ),
        )
    if len(pmids) > 1:
        return VerifyResult(
            ok=False,
            pubmed_ids_found=pmids,
            message=(
                f"manifest declares {len(pmids)} PubMed IDs ({pmids}); "
                "ambiguous pairing — set paper.pubmed_id to the single primary "
                "publication and re-run"
            ),
        )
    pmid = pmids[0]
    payload, cache_path, sha, cached = fetch_eutils(
        pmid, cache_dir=cache_dir, refresh=refresh, offline=offline
    )
    ver = parse_eutils_payload(payload, pmid)
    ver.response_sha256 = sha
    ver.cache_path = str(cache_path)

    manifest_doi_norm = normalize_doi(paper.get("doi") or "")
    eutils_doi_norm = normalize_doi(ver.doi)

    auto_filled = ""
    if not manifest_doi_norm:
        if not eutils_doi_norm:
            return VerifyResult(
                ok=False,
                pubmed_ids_found=[pmid],
                verification=ver,
                message=f"pubmed:{pmid} has no DOI in eutils; cannot auto-fill",
            )
        auto_filled = ver.doi
        msg = (f"OK: manifest.paper.doi was empty; auto-filled from "
               f"eutils → {auto_filled} ({'cached' if cached else 'fetched'})")
        return VerifyResult(
            ok=True,
            verification=ver,
            auto_filled_doi=auto_filled,
            pubmed_ids_found=[pmid],
            message=msg,
        )

    if manifest_doi_norm != eutils_doi_norm:
        return VerifyResult(
            ok=False,
            pubmed_ids_found=[pmid],
            verification=ver,
            message=(
                f"DOI MISMATCH: manifest claims {paper.get('doi')!r} but "
                f"pubmed:{pmid} resolves to {ver.doi!r}. The manifest is "
                f"pointing at the wrong paper, or pubmed_id is wrong."
            ),
        )

    return VerifyResult(
        ok=True,
        verification=ver,
        pubmed_ids_found=[pmid],
        message=(f"OK: pubmed:{pmid} matches manifest.paper.doi "
                 f"({'cached' if cached else 'fetched'})"),
    )
