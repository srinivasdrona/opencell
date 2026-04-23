"""Tests for opencell.manifest.pairing (paper-pairing verifier)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencell.manifest.pairing import (
    PairingError,
    extract_pubmed_ids,
    fetch_eutils,
    normalize_doi,
    parse_eutils_payload,
    verify_paper_pairing,
)


# Realistic eutils response fixture (mirrors NCBI esummary JSON shape; values
# from pubmed:17590932 - the Chassagnole 2002 paper that BIOMD0000000051 maps to)
CHASSAGNOLE_EUTILS = {
    "header": {"type": "esummary", "version": "0.3"},
    "result": {
        "uids": ["17590932"],
        "17590932": {
            "uid": "17590932",
            "pubdate": "2002 Jul 5",
            "source": "Biotechnol Bioeng",
            "authors": [
                {"name": "Chassagnole C", "authtype": "Author"},
                {"name": "Noisommit-Rizzi N", "authtype": "Author"},
                {"name": "Schmid JW", "authtype": "Author"},
            ],
            "title": "Dynamic modeling of the central carbon metabolism of Escherichia coli.",
            "articleids": [
                {"idtype": "pubmed", "value": "17590932"},
                {"idtype": "doi", "value": "10.1002/bit.10288"},
            ],
            "fulljournalname": "Biotechnology and bioengineering",
        },
    },
}


# ---------------------------------------------------------------------------
# normalize_doi
# ---------------------------------------------------------------------------

class TestNormalizeDoi:
    def test_lowercases(self):
        assert normalize_doi("10.1002/BIT.10288") == "10.1002/bit.10288"

    def test_strips_doi_prefix(self):
        assert normalize_doi("doi:10.1002/bit.10288") == "10.1002/bit.10288"

    def test_strips_url_prefix(self):
        assert normalize_doi("https://doi.org/10.1002/bit.10288") == "10.1002/bit.10288"
        assert normalize_doi("http://doi.org/10.1002/bit.10288") == "10.1002/bit.10288"

    def test_handles_whitespace(self):
        assert normalize_doi("  10.1002/bit.10288  ") == "10.1002/bit.10288"

    def test_empty_returns_empty(self):
        assert normalize_doi("") == ""
        assert normalize_doi("   ") == ""


# ---------------------------------------------------------------------------
# extract_pubmed_ids (precedence: structured > notes regex)
# ---------------------------------------------------------------------------

class TestExtractPubmedIds:
    def test_structured_pubmed_id_string(self):
        assert extract_pubmed_ids({"pubmed_id": "17590932"}) == ["17590932"]

    def test_structured_pubmed_id_int(self):
        assert extract_pubmed_ids({"pubmed_id": 17590932}) == ["17590932"]

    def test_structured_pubmed_id_list(self):
        assert extract_pubmed_ids({"pubmed_id": ["17590932", "12345"]}) == ["17590932", "12345"]

    def test_falls_back_to_notes_regex(self):
        ids = extract_pubmed_ids({"notes": "Auto-generated from BIOMD0000000051; pubmed:17590932"})
        assert ids == ["17590932"]

    def test_structured_overrides_notes(self):
        # When pubmed_id is set explicitly, notes are NOT consulted.
        ids = extract_pubmed_ids({
            "pubmed_id": "17590932",
            "notes": "pubmed:99999999",
        })
        assert ids == ["17590932"]

    def test_no_ids_returns_empty(self):
        assert extract_pubmed_ids({}) == []

    def test_dedupes_preserving_order(self):
        ids = extract_pubmed_ids({"pubmed_id": ["17590932", "17590932", "12345"]})
        assert ids == ["17590932", "12345"]

    def test_finds_multiple_in_notes(self):
        ids = extract_pubmed_ids({"notes": "primary pubmed:17590932; review pubmed:99999999"})
        assert ids == ["17590932", "99999999"]


# ---------------------------------------------------------------------------
# parse_eutils_payload
# ---------------------------------------------------------------------------

class TestParseEutilsPayload:
    def test_parses_chassagnole(self):
        v = parse_eutils_payload(CHASSAGNOLE_EUTILS, "17590932")
        assert v.pubmed_id == "17590932"
        assert v.doi == "10.1002/bit.10288"
        assert "Dynamic modeling" in v.title
        assert v.first_author == "Chassagnole C"
        assert v.year == "2002"
        assert v.journal == "Biotechnol Bioeng"
        assert v.source == "ncbi-eutils"
        assert v.verified_at  # iso timestamp set

    def test_missing_record_raises(self):
        empty = {"result": {"uids": []}}
        with pytest.raises(PairingError, match="no record"):
            parse_eutils_payload(empty, "99999999")

    def test_no_doi_in_record(self):
        payload = {
            "result": {
                "uids": ["123"],
                "123": {"uid": "123", "pubdate": "2020", "title": "x",
                        "authors": [], "articleids": [], "source": "J"},
            }
        }
        v = parse_eutils_payload(payload, "123")
        assert v.doi == ""
        assert v.pubmed_id == "123"


# ---------------------------------------------------------------------------
# fetch_eutils (cache behavior; offline mode; no network in tests)
# ---------------------------------------------------------------------------

class TestFetchEutilsCache:
    def test_returns_cached_when_present(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cache_file = cache_dir / "eutils-pubmed-17590932.json"
        cache_file.write_bytes(json.dumps(CHASSAGNOLE_EUTILS).encode())
        payload, path, sha, cached = fetch_eutils(
            "17590932", cache_dir=cache_dir, offline=True
        )
        assert cached is True
        assert path == cache_file
        assert payload == CHASSAGNOLE_EUTILS
        assert len(sha) == 64

    def test_offline_with_no_cache_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="offline mode"):
            fetch_eutils("17590932", cache_dir=tmp_path, offline=True)

    def test_refresh_ignores_cache_in_offline(self, tmp_path: Path):
        # refresh + offline + no cache → still raises (refresh requires network)
        cache_file = tmp_path / "eutils-pubmed-17590932.json"
        cache_file.write_bytes(b'{"old": "data"}')
        with pytest.raises(FileNotFoundError):
            fetch_eutils("17590932", cache_dir=tmp_path, offline=True, refresh=True)


# ---------------------------------------------------------------------------
# verify_paper_pairing (top-level)
# ---------------------------------------------------------------------------

class TestVerifyPairing:
    @pytest.fixture
    def cache_dir_with_chassagnole(self, tmp_path: Path) -> Path:
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "eutils-pubmed-17590932.json").write_bytes(
            json.dumps(CHASSAGNOLE_EUTILS).encode()
        )
        return cache

    def test_match_succeeds(self, cache_dir_with_chassagnole):
        manifest = {
            "paper": {
                "pubmed_id": "17590932",
                "doi": "10.1002/bit.10288",
            }
        }
        r = verify_paper_pairing(manifest, cache_dir=cache_dir_with_chassagnole, offline=True)
        assert r.ok is True
        assert r.verification.doi == "10.1002/bit.10288"
        assert r.auto_filled_doi == ""

    def test_case_insensitive_doi_match(self, cache_dir_with_chassagnole):
        manifest = {"paper": {
            "pubmed_id": "17590932",
            "doi": "10.1002/BIT.10288",     # uppercase
        }}
        r = verify_paper_pairing(manifest, cache_dir=cache_dir_with_chassagnole, offline=True)
        assert r.ok is True

    def test_doi_url_prefix_match(self, cache_dir_with_chassagnole):
        manifest = {"paper": {
            "pubmed_id": "17590932",
            "doi": "https://doi.org/10.1002/bit.10288",
        }}
        r = verify_paper_pairing(manifest, cache_dir=cache_dir_with_chassagnole, offline=True)
        assert r.ok is True

    def test_auto_fills_when_doi_blank(self, cache_dir_with_chassagnole):
        manifest = {"paper": {"pubmed_id": "17590932", "doi": ""}}
        r = verify_paper_pairing(manifest, cache_dir=cache_dir_with_chassagnole, offline=True)
        assert r.ok is True
        assert r.auto_filled_doi == "10.1002/bit.10288"
        assert "auto-filled" in r.message

    def test_doi_mismatch_fails(self, cache_dir_with_chassagnole):
        manifest = {"paper": {
            "pubmed_id": "17590932",
            "doi": "10.9999/wrong.paper",
        }}
        r = verify_paper_pairing(manifest, cache_dir=cache_dir_with_chassagnole, offline=True)
        assert r.ok is False
        assert "MISMATCH" in r.message

    def test_no_pubmed_id_fails(self, tmp_path):
        manifest = {"paper": {"doi": "10.0/x"}}
        r = verify_paper_pairing(manifest, cache_dir=tmp_path, offline=True)
        assert r.ok is False
        assert "no PubMed ID" in r.message

    def test_multiple_pubmed_ids_fails_closed(self, tmp_path):
        manifest = {"paper": {"pubmed_id": ["17590932", "12345"]}}
        r = verify_paper_pairing(manifest, cache_dir=tmp_path, offline=True)
        assert r.ok is False
        assert "ambiguous" in r.message
        assert r.pubmed_ids_found == ["17590932", "12345"]

    def test_falls_back_to_notes_when_no_structured_id(self, cache_dir_with_chassagnole):
        manifest = {"paper": {
            "doi": "10.1002/bit.10288",
            "notes": "Auto-generated; pubmed:17590932",
        }}
        r = verify_paper_pairing(manifest, cache_dir=cache_dir_with_chassagnole, offline=True)
        assert r.ok is True

    def test_response_sha_is_recorded(self, cache_dir_with_chassagnole):
        manifest = {"paper": {"pubmed_id": "17590932", "doi": "10.1002/bit.10288"}}
        r = verify_paper_pairing(manifest, cache_dir=cache_dir_with_chassagnole, offline=True)
        assert r.verification.response_sha256
        assert len(r.verification.response_sha256) == 64

    def test_verification_to_dict_omits_empty(self):
        from opencell.manifest.pairing import PairingVerification
        v = PairingVerification(source="ncbi-eutils", pubmed_id="123")
        d = v.to_dict()
        assert d["pubmed_id"] == "123"
        assert "doi" not in d
        assert "title" not in d
