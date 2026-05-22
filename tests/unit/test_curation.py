"""Tests for opencell.curation (biology-curator agent).

Two layers of tests:

1. Pure unit tests using a fake `extract_fn` (deterministic, hermetic):
   - manifest validation
   - status routing
   - locked-status protection (REVIEWED / APPROVED never overwritten)
   - idempotency via SKIPPED_EXISTS
   - queue emission
   - coverage report rendering
   - provenance JSON

2. Thattai 2001 replay (integration test): runs the REAL extractor on
   the cached PDF and asserts it produces 1 RECOMMEND (k_R, value 0.6
   min^-1) and routes the three derived parameters to non-RECOMMEND
   queues -- proving the curator never invents.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from opencell.curation import (
    ManifestValidationError,
    load_manifest,
    run_curation,
    write_outputs,
)
from opencell.curation.emitter import (
    render_coverage_md,
    write_cards_yaml,
    write_queue,
)
from opencell.data.verification import (
    ParameterCard,
    VerificationStatus,
    save_cards_to_yaml,
)
from opencell.extraction import (
    ExtractionResult,
)
from opencell.extraction.candidate import ExtractionCandidate, SectionType

# ---------------------------------------------------------------------------
# Helpers: synthesize ExtractionResult objects
# ---------------------------------------------------------------------------


def _result_recommend(symbol: str, value: float, unit: str = "min^-1") -> ExtractionResult:
    cand = ExtractionCandidate(
        raw_value=value,
        raw_unit=unit,
        raw_unit_normalized=unit,
        method="pdf_grep",
        locator="cache.txt:1",
        context_window=f"{symbol} = {value} {unit}",
        section_type=SectionType.CAPTION,
        score=0.9,
        score_components={"unit_match": 0.4, "section": 0.3, "context": 0.2},
        convertible_to_target=True,
        converted_value=value,
        converted_unit=unit,
        transformation="identity",
        source_path="cache.txt",
        source_sha256="deadbeef",
        extractor_version="test",
    )
    return ExtractionResult(
        parameter_symbol=symbol,
        parameter_doi="10.0/test",
        target_unit=unit,
        candidates=[cand],
        cache_files=["cache.txt"],
        methods_attempted=["pdf_grep"],
    )


def _result_not_found(symbol: str) -> ExtractionResult:
    return ExtractionResult(
        parameter_symbol=symbol,
        parameter_doi="10.0/test",
        target_unit="min^-1",
        candidates=[],
        cache_files=["cache.txt"],
        methods_attempted=["pdf_grep"],
        notes=["no hits"],
    )


def _result_ambiguous(symbol: str) -> ExtractionResult:
    common = dict(
        raw_unit="s^-1",
        raw_unit_normalized="s^-1",
        method="pdf_grep",
        section_type=SectionType.BODY,
        score=0.7,
        score_components={"unit_match": 0.4, "section": 0.2, "context": 0.1},
        convertible_to_target=True,
        converted_unit="min^-1",
        transformation="x60",
    )
    c1 = ExtractionCandidate(
        raw_value=0.01, locator="L1", context_window="ctx1", converted_value=0.6, **common
    )
    c2 = ExtractionCandidate(
        raw_value=0.02, locator="L2", context_window="ctx2", converted_value=1.2, **common
    )
    return ExtractionResult(
        parameter_symbol=symbol,
        parameter_doi="10.0/test",
        target_unit="min^-1",
        candidates=[c1, c2],
        cache_files=["cache.txt"],
        methods_attempted=["pdf_grep"],
    )


def _make_manifest(tmp_path: Path, *, ids_and_symbols: list[tuple[str, str]]) -> Path:
    cache = tmp_path / "cache.txt"
    cache.write_text("dummy")
    body = {
        "model_slug": "testmodel",
        "manifest_version": "0.1",
        "paper": {
            "doi": "10.0/test",
            "organism": "test organism",
            "condition": "base case",
        },
        "cache_files": [str(cache)],
        "parameters": [
            {
                "parameter_id": pid,
                "symbol": sym,
                "target_unit": "min^-1",
                "name": f"param {sym}",
            }
            for pid, sym in ids_and_symbols
        ],
    }
    mpath = tmp_path / "manifest.yaml"
    mpath.write_text(yaml.safe_dump(body, sort_keys=False))
    return mpath


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


class TestManifestValidation:
    def test_loads_valid_manifest(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        m = load_manifest(mpath)
        assert m.model_slug == "testmodel"
        assert m.doi == "10.0/test"
        assert len(m.parameters) == 1
        assert m.parameters[0].organism == "test organism"  # inherits from paper

    def test_missing_file_raises(self, tmp_path) -> None:
        with pytest.raises(ManifestValidationError, match="not found"):
            load_manifest(tmp_path / "nope.yaml")

    def test_missing_model_slug(self, tmp_path) -> None:
        mpath = tmp_path / "m.yaml"
        mpath.write_text(
            yaml.safe_dump(
                {
                    "paper": {"doi": "10.0/x"},
                    "parameters": [{"parameter_id": "a", "symbol": "k"}],
                }
            )
        )
        with pytest.raises(ManifestValidationError, match="model_slug"):
            load_manifest(mpath)

    def test_missing_doi(self, tmp_path) -> None:
        """A draft manifest may have empty paper.doi (filled later by verifier);
        load_manifest accepts it but run_curation refuses to extract."""
        mpath = tmp_path / "m.yaml"
        mpath.write_text(
            yaml.safe_dump(
                {
                    "model_slug": "x",
                    "paper": {},
                    "cache_files": [],
                    "parameters": [{"parameter_id": "a", "symbol": "k"}],
                }
            )
        )
        m = load_manifest(mpath)  # no exception
        assert m.doi == ""
        with pytest.raises(ValueError, match="paper.doi is empty"):
            run_curation(m)

    def test_empty_parameters(self, tmp_path) -> None:
        mpath = tmp_path / "m.yaml"
        mpath.write_text(
            yaml.safe_dump(
                {
                    "model_slug": "x",
                    "paper": {"doi": "10.0/x"},
                    "parameters": [],
                }
            )
        )
        with pytest.raises(ManifestValidationError, match="non-empty"):
            load_manifest(mpath)

    def test_duplicate_parameter_ids(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA"), ("p1", "kB")])
        with pytest.raises(ManifestValidationError, match="duplicate parameter_id"):
            load_manifest(mpath)

    def test_missing_required_field(self, tmp_path) -> None:
        mpath = tmp_path / "m.yaml"
        mpath.write_text(
            yaml.safe_dump(
                {
                    "model_slug": "x",
                    "paper": {"doi": "10.0/x"},
                    "parameters": [{"parameter_id": "a"}],  # symbol missing
                }
            )
        )
        with pytest.raises(ManifestValidationError, match="missing required field 'symbol'"):
            load_manifest(mpath)

    def test_cache_file_hashed_when_present(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        m = load_manifest(mpath)
        # Exactly one cache file referenced
        assert len(m.cache_file_sha256) == 1
        sha = next(iter(m.cache_file_sha256.values()))
        assert len(sha) == 64  # sha256 hex

    def test_missing_cache_file_no_hash(self, tmp_path) -> None:
        # Reference a non-existent cache file -- should NOT raise but also NOT hash.
        cache_missing = str(tmp_path / "nope.txt")
        body = {
            "model_slug": "x",
            "paper": {"doi": "10.0/x"},
            "cache_files": [cache_missing],
            "parameters": [{"parameter_id": "p1", "symbol": "kA"}],
        }
        mpath = tmp_path / "m.yaml"
        mpath.write_text(yaml.safe_dump(body))
        m = load_manifest(mpath)
        assert cache_missing not in m.cache_file_sha256


# ---------------------------------------------------------------------------
# Runner status routing
# ---------------------------------------------------------------------------


class TestRunnerStatusRouting:
    def test_recommend_produces_card(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        m = load_manifest(mpath)
        run = run_curation(m, extract_fn=lambda spec: _result_recommend("kA", 0.5))
        assert run.coverage["RECOMMEND"] == 1
        assert run.outcomes[0].card is not None
        assert run.outcomes[0].card.status == VerificationStatus.DRAFT
        assert run.outcomes[0].card.value == 0.5

    def test_not_found_no_card(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        m = load_manifest(mpath)
        run = run_curation(m, extract_fn=lambda spec: _result_not_found("kA"))
        assert run.coverage["NOT_FOUND"] == 1
        assert run.outcomes[0].card is None

    def test_ambiguous_no_card(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        m = load_manifest(mpath)
        run = run_curation(m, extract_fn=lambda spec: _result_ambiguous("kA"))
        assert run.coverage["AMBIGUOUS"] == 1
        assert run.outcomes[0].card is None

    def test_mixed_run(self, tmp_path) -> None:
        mpath = _make_manifest(
            tmp_path,
            ids_and_symbols=[
                ("p1", "kA"),
                ("p2", "kB"),
                ("p3", "kC"),
            ],
        )
        m = load_manifest(mpath)
        results = {
            "kA": _result_recommend("kA", 1.0),
            "kB": _result_ambiguous("kB"),
            "kC": _result_not_found("kC"),
        }
        run = run_curation(m, extract_fn=lambda spec: results[spec.symbol])
        cov = run.coverage
        assert cov["RECOMMEND"] == 1
        assert cov["AMBIGUOUS"] == 1
        assert cov["NOT_FOUND"] == 1


# ---------------------------------------------------------------------------
# Cross-check guardrail (PDF↔SBML value match)
# ---------------------------------------------------------------------------


def _make_manifest_with_sbml(tmp_path: Path, *, sbml_value: float | None) -> Path:
    """Variant of _make_manifest that emits a sbml_value per entry."""
    cache = tmp_path / "cache.txt"
    cache.write_text("dummy")
    body = {
        "model_slug": "testmodel",
        "manifest_version": "0.1",
        "paper": {"doi": "10.0/test", "organism": "test", "condition": "base"},
        "cache_files": [str(cache)],
        "parameters": [
            {
                "parameter_id": "p1",
                "symbol": "kA",
                "target_unit": "min^-1",
                "name": "param kA",
                "sbml_value": sbml_value,
                "sbml_id": "kA",
                "sbml_kind": "global_parameter",
            }
        ],
    }
    mpath = tmp_path / "manifest.yaml"
    mpath.write_text(yaml.safe_dump(body, sort_keys=False))
    return mpath


class TestCrossCheckGuardrail:
    def test_loads_sbml_value_from_manifest(self, tmp_path) -> None:
        mpath = _make_manifest_with_sbml(tmp_path, sbml_value=4.27)
        m = load_manifest(mpath)
        assert m.parameters[0].sbml_value == 4.27
        assert m.parameters[0].sbml_id == "kA"
        assert m.parameters[0].sbml_kind == "global_parameter"

    def test_agree_when_pdf_and_sbml_match(self, tmp_path) -> None:
        mpath = _make_manifest_with_sbml(tmp_path, sbml_value=0.5)
        m = load_manifest(mpath)
        run = run_curation(m, extract_fn=lambda spec: _result_recommend("kA", 0.5))
        out = run.outcomes[0]
        assert out.status == "RECOMMEND"
        assert out.cross_check is not None
        assert out.cross_check.status == "AGREE"
        assert out.card is not None  # still emits draft card

    def test_disagree_downgrades_to_ambiguous(self, tmp_path) -> None:
        """The blocking guardrail: PDF value disagrees → no draft card auto-emitted."""
        mpath = _make_manifest_with_sbml(tmp_path, sbml_value=0.5)
        m = load_manifest(mpath)
        # PDF reports 1.5 but SBML says 0.5 (3x off)
        run = run_curation(m, extract_fn=lambda spec: _result_recommend("kA", 1.5))
        out = run.outcomes[0]
        assert out.status == "AMBIGUOUS"  # downgraded from RECOMMEND
        assert out.card is None  # no auto-emitted card
        assert out.cross_check.status == "DISAGREE"
        assert "downgraded" in out.note.lower()
        assert "0.5" in out.note and "1.5" in out.note

    def test_no_sbml_value_does_not_block_recommend(self, tmp_path) -> None:
        """When SBML value missing, behave as before (no cross-check enforcement)."""
        mpath = _make_manifest_with_sbml(tmp_path, sbml_value=None)
        m = load_manifest(mpath)
        run = run_curation(m, extract_fn=lambda spec: _result_recommend("kA", 1.5))
        out = run.outcomes[0]
        assert out.status == "RECOMMEND"
        assert out.card is not None
        assert out.cross_check.status == "NO_SBML"

    def test_card_provenance_records_cross_check(self, tmp_path) -> None:
        mpath = _make_manifest_with_sbml(tmp_path, sbml_value=0.5)
        m = load_manifest(mpath)
        run = run_curation(m, extract_fn=lambda spec: _result_recommend("kA", 0.5))
        rationale = run.outcomes[0].card.selection_rationale
        assert "Cross-check" in rationale
        assert "AGREE" in rationale


# ---------------------------------------------------------------------------
# Locked-status protection
# ---------------------------------------------------------------------------


class TestLockedProtection:
    def _seed_card(
        self, path: Path, *, status: VerificationStatus, value: float = 99.0
    ) -> ParameterCard:
        card = ParameterCard(
            parameter_id="p1",
            name="seeded",
            value=value,
            unit="min^-1",
            source_doi="10.0/test",
            source_type="measured",
            organism="x",
            condition="x",
            compartment="x",
            gene_or_enzyme="x",
            status=status,
        )
        save_cards_to_yaml([card], path)
        return card

    def test_approved_card_never_overwritten(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        cards_path = tmp_path / "cards.yaml"
        self._seed_card(cards_path, status=VerificationStatus.APPROVED, value=42.0)

        m = load_manifest(mpath)
        run = run_curation(
            m,
            output_cards_path=cards_path,
            force=True,  # even with force!
            extract_fn=lambda spec: _result_recommend("kA", 0.5),
        )
        assert run.outcomes[0].status == "SKIPPED_LOCKED"
        # File on disk must still hold the APPROVED 42.0
        from opencell.data.verification import load_cards_from_yaml

        cards = load_cards_from_yaml(cards_path)
        assert cards[0].value == 42.0
        assert cards[0].status == VerificationStatus.APPROVED

    def test_reviewed_card_protected(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        cards_path = tmp_path / "cards.yaml"
        self._seed_card(cards_path, status=VerificationStatus.REVIEWED)
        m = load_manifest(mpath)
        run = run_curation(
            m,
            output_cards_path=cards_path,
            force=True,
            extract_fn=lambda spec: _result_recommend("kA", 0.5),
        )
        assert run.outcomes[0].status == "SKIPPED_LOCKED"

    def test_draft_skipped_without_force(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        cards_path = tmp_path / "cards.yaml"
        self._seed_card(cards_path, status=VerificationStatus.DRAFT)
        m = load_manifest(mpath)
        run = run_curation(
            m,
            output_cards_path=cards_path,
            force=False,
            extract_fn=lambda spec: _result_recommend("kA", 0.5),
        )
        assert run.outcomes[0].status == "SKIPPED_EXISTS"

    def test_draft_re_extracted_with_force(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        cards_path = tmp_path / "cards.yaml"
        self._seed_card(cards_path, status=VerificationStatus.DRAFT, value=99.0)
        m = load_manifest(mpath)
        run = run_curation(
            m,
            output_cards_path=cards_path,
            force=True,
            extract_fn=lambda spec: _result_recommend("kA", 0.5),
        )
        assert run.outcomes[0].status == "RECOMMEND"
        write_cards_yaml(run, cards_path)
        from opencell.data.verification import load_cards_from_yaml

        cards = load_cards_from_yaml(cards_path)
        assert cards[0].value == 0.5  # overwritten
        assert cards[0].status == VerificationStatus.DRAFT


# ---------------------------------------------------------------------------
# Outputs: queues, coverage, provenance
# ---------------------------------------------------------------------------


class TestOutputs:
    def test_full_write_outputs(self, tmp_path) -> None:
        mpath = _make_manifest(
            tmp_path,
            ids_and_symbols=[
                ("p1", "kA"),
                ("p2", "kB"),
                ("p3", "kC"),
            ],
        )
        results = {
            "kA": _result_recommend("kA", 1.0),
            "kB": _result_ambiguous("kB"),
            "kC": _result_not_found("kC"),
        }
        m = load_manifest(mpath)
        run = run_curation(m, extract_fn=lambda spec: results[spec.symbol])

        cards_path = tmp_path / "out" / "cards.yaml"
        out_dir = tmp_path / "out"
        paths = write_outputs(run, cards_path=cards_path, output_dir=out_dir)

        # Cards file: 1 DRAFT card
        assert paths["cards"].exists()
        from opencell.data.verification import load_cards_from_yaml

        cards = load_cards_from_yaml(paths["cards"])
        assert len(cards) == 1
        assert cards[0].parameter_id == "p1"

        # Arbitration queue: 1 entry
        amb = yaml.safe_load(paths["needs_arbitration"].read_text())
        assert amb["count"] == 1
        assert amb["entries"][0]["parameter_id"] == "p2"
        assert len(amb["entries"][0]["surviving_candidates"]) == 2

        # Not-found queue: 1 entry
        nf = yaml.safe_load(paths["not_found"].read_text())
        assert nf["count"] == 1
        assert nf["entries"][0]["parameter_id"] == "p3"

        # Coverage report
        cov_text = paths["coverage"].read_text()
        assert "testmodel" in cov_text
        assert "RECOMMEND" in cov_text
        assert "p1" in cov_text and "p2" in cov_text and "p3" in cov_text

        # Provenance
        prov = json.loads(paths["provenance"].read_text())
        assert prov["model_slug"] == "testmodel"
        assert prov["coverage"]["TOTAL"] == 3
        assert {r["parameter_id"] for r in prov["results"]} == {"p1", "p2", "p3"}
        # cache_file_sha256 carried through
        assert len(prov["cache_file_sha256"]) == 1

    def test_empty_queue_removes_stale_file(self, tmp_path) -> None:
        mpath = _make_manifest(tmp_path, ids_and_symbols=[("p1", "kA")])
        m = load_manifest(mpath)
        # First run: 1 NOT_FOUND -> queue file written
        run1 = run_curation(m, extract_fn=lambda spec: _result_not_found("kA"))
        nf_path = tmp_path / "nf.yaml"
        write_queue(run1.outcomes, nf_path, kind="NOT_FOUND")
        assert nf_path.exists()
        # Second run: all RECOMMEND -> queue file should be removed
        run2 = run_curation(m, extract_fn=lambda spec: _result_recommend("kA", 0.5))
        write_queue(run2.outcomes, nf_path, kind="NOT_FOUND")
        assert not nf_path.exists()

    def test_coverage_md_contains_breakdown(self) -> None:
        from opencell.curation.runner import CurationOutcome, CurationRun

        run = CurationRun(
            model_slug="x",
            doi="10/x",
            started_at="t0",
            finished_at="t1",
            outcomes=[
                CurationOutcome(
                    parameter_id="a",
                    symbol="kA",
                    status="RECOMMEND",
                    extraction=_result_recommend("kA", 1.0),
                ),
                CurationOutcome(
                    parameter_id="b",
                    symbol="kB",
                    status="NOT_FOUND",
                    extraction=_result_not_found("kB"),
                ),
            ],
        )
        md = render_coverage_md(run)
        assert "| RECOMMEND | 1 | 50.0% |" in md
        assert "| NOT_FOUND | 1 | 50.0% |" in md


# ---------------------------------------------------------------------------
# THATTAI 2001 REPLAY (integration with the real extractor)
# ---------------------------------------------------------------------------

THATTAI_CACHE = Path(__file__).resolve().parents[2] / ".paper_cache" / "thattai2001_full.txt"


@pytest.mark.skipif(not THATTAI_CACHE.exists(), reason="Requires .paper_cache/thattai2001_full.txt")
class TestThattaiReplay:
    """End-to-end: real extractor on real Thattai PDF cache.

    Asserts the curator's hard contract:
      * k_R is RECOMMEND with value 0.6 min^-1 (matches APPROVED gold card)
      * The three derived parameters do NOT auto-emit; they go to queues
    """

    @pytest.fixture
    def manifest(self, tmp_path):
        body = {
            "model_slug": "thattai2001_replay",
            "manifest_version": "0.1",
            "paper": {
                "doi": "10.1073/pnas.151588598",
                "organism": "generic prokaryotic gene",
                "condition": "Thattai 2001 base case",
            },
            "cache_files": [str(THATTAI_CACHE)],
            "parameters": [
                {
                    "parameter_id": "thattai-kR",
                    "symbol": "kR",
                    "target_unit": "min^-1",
                    "name": "Transcription rate",
                },
                {
                    "parameter_id": "thattai-gammaR",
                    "symbol": "gammaR",
                    "target_unit": "min^-1",
                    "name": "mRNA degradation",
                },
                {
                    "parameter_id": "thattai-kP",
                    "symbol": "kP",
                    "target_unit": "min^-1",
                    "name": "Translation rate",
                },
                {
                    "parameter_id": "thattai-gammaP",
                    "symbol": "gammaP",
                    "target_unit": "min^-1",
                    "name": "Protein degradation",
                },
            ],
        }
        mpath = tmp_path / "manifest.yaml"
        mpath.write_text(yaml.safe_dump(body, sort_keys=False))
        return load_manifest(mpath)

    def test_kR_recommend_matches_approved_value(self, manifest) -> None:
        run = run_curation(manifest, use_biomodels=False)
        # Find k_R outcome
        kr = next(o for o in run.outcomes if o.parameter_id == "thattai-kR")
        assert kr.status == "RECOMMEND", f"k_R should be RECOMMEND, got {kr.status}"
        assert kr.card is not None
        # Bit-for-bit match with approved gold card
        assert kr.card.value == pytest.approx(0.6, rel=1e-9)
        assert kr.card.unit == "min^-1"
        assert kr.card.status == VerificationStatus.DRAFT  # never auto-promotes

    def test_derived_params_never_auto_emitted(self, manifest) -> None:
        run = run_curation(manifest, use_biomodels=False)
        # The three derived params (gammaR, kP, gammaP) cannot be extracted
        # by the deterministic extractor (they require math the tool refuses
        # to do). They MUST land in non-RECOMMEND statuses.
        derived = [
            o
            for o in run.outcomes
            if o.parameter_id in ("thattai-gammaR", "thattai-kP", "thattai-gammaP")
        ]
        for o in derived:
            assert o.status != "RECOMMEND", (
                f"{o.parameter_id} must NOT auto-emit (status={o.status})"
            )
            assert o.card is None

    def test_full_outputs_written(self, manifest, tmp_path) -> None:
        run = run_curation(manifest, use_biomodels=False)
        cards_path = tmp_path / "cards.yaml"
        out_dir = tmp_path / "out"
        paths = write_outputs(run, cards_path=cards_path, output_dir=out_dir)

        # cards.yaml has exactly 1 DRAFT (k_R only)
        from opencell.data.verification import load_cards_from_yaml

        cards = load_cards_from_yaml(cards_path)
        assert len(cards) == 1
        assert cards[0].parameter_id == "thattai-kR"

        # provenance JSON pins the cache SHA-256
        prov = json.loads(paths["provenance"].read_text())
        assert prov["cache_file_sha256"]
        sha = next(iter(prov["cache_file_sha256"].values()))
        assert len(sha) == 64
