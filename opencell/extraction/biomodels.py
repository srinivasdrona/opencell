"""Best-effort BioModels Database lookup.

We use the public REST API to find a BIOMD entry for a given DOI, then
parse the SBML for parameters matching the requested symbol.  Network
failures are non-fatal: this module always returns a (possibly empty)
candidate list and never raises.

Reference: https://www.ebi.ac.uk/biomodels/docs/
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

from .candidate import ExtractionCandidate, SectionType

BIOMODELS_SEARCH = "https://www.ebi.ac.uk/biomodels/search"
BIOMODELS_DOWNLOAD = "https://www.ebi.ac.uk/biomodels/model/download"
USER_AGENT = "OpenCell-ParamExtractor/0.1"
TIMEOUT = 10  # seconds

SBML_NS = "http://www.sbml.org/sbml/level2"
SBML_NS_L3 = "http://www.sbml.org/sbml/level3/version1/core"


def _http_get(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,application/xml"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


def search_by_doi(doi: str) -> list[str]:
    """Return list of BIOMD IDs for the given DOI, or [] if none/network down."""
    q = urllib.parse.quote(f'doi:"{doi}"')
    url = f"{BIOMODELS_SEARCH}?query={q}&format=json"
    raw = _http_get(url)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    models = data.get("models", []) if isinstance(data, dict) else []
    ids: list[str] = []
    for m in models:
        if isinstance(m, dict) and "id" in m:
            ids.append(m["id"])
    return ids


def download_sbml(biomd_id: str) -> bytes | None:
    """Download the curated SBML for a BIOMD entry."""
    url = f"{BIOMODELS_DOWNLOAD}/{biomd_id}?filename={biomd_id}_url.xml"
    return _http_get(url)


def parse_sbml_parameters(sbml_bytes: bytes) -> list[tuple[str, float, str]]:
    """Return [(id, value, units)] for all <parameter> elements."""
    try:
        root = ET.fromstring(sbml_bytes)
    except ET.ParseError:
        return []
    out: list[tuple[str, float, str]] = []
    # Namespace-agnostic walk
    for elem in root.iter():
        tag = elem.tag.split("}", 1)[-1]
        if tag != "parameter":
            continue
        pid = elem.attrib.get("id", "") or elem.attrib.get("name", "")
        value_str = elem.attrib.get("value", "")
        units = elem.attrib.get("units", "")
        try:
            value = float(value_str)
        except (TypeError, ValueError):
            continue
        out.append((pid, value, units))
    return out


def extract_from_biomodels(doi: str, symbol: str) -> list[ExtractionCandidate]:
    """Search BioModels for `doi`, parse SBML, return matching candidates.

    Symbol matching is case-insensitive and tries underscore variants.
    Always returns a list (empty on any failure).
    """
    candidates: list[ExtractionCandidate] = []
    ids = search_by_doi(doi)
    if not ids:
        return []
    sym_norm = symbol.replace("_", "").lower()
    for biomd_id in ids[:3]:  # cap to avoid hammering
        sbml = download_sbml(biomd_id)
        if not sbml:
            continue
        for pid, value, units in parse_sbml_parameters(sbml):
            if pid.replace("_", "").lower() == sym_norm or pid.lower() == symbol.lower():
                candidates.append(ExtractionCandidate(
                    raw_value=value,
                    raw_unit=units,
                    raw_unit_normalized=units,
                    method="biomodels_sbml",
                    locator=f"BioModels:{biomd_id}/parameter[@id='{pid}']",
                    context_window=f"<parameter id='{pid}' value='{value}' units='{units}'/>",
                    section_type=SectionType.SBML,
                    score=0.7,  # curated SBML is high-confidence
                    score_components={"sbml_curated": 0.7},
                    source_path=f"biomodels://{biomd_id}",
                ))
    return candidates
