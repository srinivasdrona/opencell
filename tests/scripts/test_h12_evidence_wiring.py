"""Tests for the H12 evidence-index linkage wiring in
`scripts/l22_evidence/generator.py` (`_load_h12_evidence_index` /
`_with_h12_evidence_ref`).

This covers the "wire evidence generator to consume h12_evidence_ref"
requirement via a SEPARATE tracked side-index
(`docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json`,
`schema.H12_EVIDENCE_INDEX_PATH`) rather than by hand-editing any
process's `result.json` -- the on-disk `result.json` authority file is
never mutated by this wiring. `verdict.h12_support_reason` (already
covered by `tests/scripts/test_l22_evidence_verdict.py`) independently
re-validates the referenced artifact's own verdict/nontrivial_sample_count
/exact_match_rate/hash-freshness every time, so the side-index can only
ever point the check at an artifact -- it can never itself force a green
verdict.

Run via `bin\\oc-pytest tests/scripts/test_h12_evidence_wiring.py -v`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

from tests.scripts._l22_evidence_fixtures import write_full_valid_evidence  # noqa: E402

_ENTRIES = cat.in_scope_processes()
_CLOSED_FORM_PROCESS = "MacromolecularComplexation"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_valid_h12_artifact(path: Path, *, process: str) -> None:
    """Build a fully-valid (per `h12.validate_h12_support`) H12 artifact for
    a REAL catalog process, using REAL on-disk hashes (the actual
    `scripts/l22_evidence/h12.py`, the actual process fixture, and the
    actual vendored Karr source file) -- predictor_source_path is now
    hard-pinned and all three hashes are hard-verified against the CURRENT
    on-disk files, so fake tmp-path files can no longer be made to pass.
    `branches_confirmed` is fabricated here (a synthetic wiring-mechanism
    test, not a real machine-evidence run) to cover every branch
    `REQUIRED_BRANCHES[process]` names, purely so this file's own
    `verdict == H12_CONFIRMED` claim is internally self-consistent.
    """
    from scripts.l22_evidence import h12

    path.parent.mkdir(parents=True, exist_ok=True)
    predictor_path_on_disk = REPO_ROOT / h12.EXPECTED_PREDICTOR_SOURCE_PATH
    fixture = h12.load_fixture(process)
    karr_citation = h12.karr_source_citation(process)
    _write_json(
        path,
        {
            "process": process,
            "verdict": "H12_CONFIRMED",
            "nontrivial_sample_count": 100,
            "exact_match_rate": 1.0,
            "trivial_mismatch_count": 0,
            "branches_confirmed": sorted(h12.REQUIRED_BRANCHES[process]),
            "predictor_source_path": h12.EXPECTED_PREDICTOR_SOURCE_PATH,
            "predictor_source_sha256_lf_normalized": h12._sha256_lf_normalized(predictor_path_on_disk),
            "fixture_path": fixture["__fixture_path__"],
            "fixture_sha256": fixture["__fixture_sha256__"],
            "karr_source_citation": karr_citation,
        },
    )


def _write_closed_form_evidence_dir(evidence_root: Path, *, result_overrides: dict | None = None) -> Path:
    entry = _ENTRIES[_CLOSED_FORM_PROCESS]
    assert entry.closed_form_dominant == "confirmed_biology_validated"
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    evidence_dir = evidence_root / _CLOSED_FORM_PROCESS / subdir
    channel = {
        "verdict": "PASS",
        "aggregation": "per_tick_vector_w1_mean",
        "is_primary": True,
        "is_event_channel": False,
        "w1_oc_vs_karr": 0.1,
        "threshold": 1.0,
        "q95_null": 0.05,
        "n_nonzero_oc": 100,
        "n_nonzero_karr": 100,
    }
    write_full_valid_evidence(
        evidence_dir,
        process=_CLOSED_FORM_PROCESS,
        seeds=entry.n_seeds,
        m_ticks=entry.m_ticks,
        channels={entry.primary_channel: channel},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched the Karr oracle exactly"],
        result_overrides=result_overrides,
        oc_module=entry.oc_module,
        harness_type=entry.harness_type,
    )
    return evidence_dir


def _row_for(payload: dict, process_name: str) -> dict:
    matches = [row for row in payload["rows"] if row["process"] == process_name]
    assert len(matches) == 1
    return matches[0]


# --- _load_h12_evidence_index --------------------------------------------


def test_load_h12_evidence_index_missing_file_soft_fails_to_empty(tmp_path):
    assert gen._load_h12_evidence_index(tmp_path / "does_not_exist.json") == {}


def test_load_h12_evidence_index_malformed_json_soft_fails_to_empty(tmp_path):
    index_path = tmp_path / "h12_evidence_index.json"
    index_path.write_text("{ not valid json", encoding="utf-8")
    assert gen._load_h12_evidence_index(index_path) == {}


def test_load_h12_evidence_index_missing_entries_key_soft_fails_to_empty(tmp_path):
    index_path = tmp_path / "h12_evidence_index.json"
    _write_json(index_path, {"schema_version": 1})
    assert gen._load_h12_evidence_index(index_path) == {}


def test_load_h12_evidence_index_reads_real_tracked_file():
    """The real tracked side-index must parse and contain all 5 target
    processes pointing at their real artifact paths."""
    entries = gen._load_h12_evidence_index(schema.H12_EVIDENCE_INDEX_PATH)
    for process in (
        "MacromolecularComplexation",
        "ProteinFolding",
        "ProteinProcessingI",
        "ProteinProcessingII",
        "tRNAAminoacylation",
    ):
        assert process in entries
        assert (REPO_ROOT / entries[process]).is_file()


# --- _with_h12_evidence_ref -----------------------------------------------


def test_with_h12_evidence_ref_leaves_payload_unchanged_when_already_present(monkeypatch, tmp_path):
    monkeypatch.setattr(schema, "H12_EVIDENCE_INDEX_PATH", tmp_path / "unused.json")
    original = {"h12_evidence_ref": "some/existing/ref.json"}
    merged = gen._with_h12_evidence_ref("AnyProcess", original)
    assert merged is original  # identity: no copy made when nothing to merge


def test_with_h12_evidence_ref_leaves_payload_unchanged_when_no_index_entry(monkeypatch, tmp_path):
    index_path = tmp_path / "h12_evidence_index.json"
    _write_json(index_path, {"entries": {"SomeOtherProcess": "x.json"}})
    monkeypatch.setattr(schema, "H12_EVIDENCE_INDEX_PATH", index_path)
    original = {"process": "AnyProcess"}
    merged = gen._with_h12_evidence_ref("AnyProcess", original)
    assert merged is original


def test_with_h12_evidence_ref_injects_ref_from_index_without_mutating_original(monkeypatch, tmp_path):
    index_path = tmp_path / "h12_evidence_index.json"
    _write_json(index_path, {"entries": {"AnyProcess": "docs/phase_f/l2_2_design_a/h12/AnyProcess_h12.json"}})
    monkeypatch.setattr(schema, "H12_EVIDENCE_INDEX_PATH", index_path)
    original = {"process": "AnyProcess"}
    merged = gen._with_h12_evidence_ref("AnyProcess", original)
    assert merged is not original
    assert "h12_evidence_ref" not in original
    assert merged["h12_evidence_ref"] == "docs/phase_f/l2_2_design_a/h12/AnyProcess_h12.json"


# --- End-to-end: build_evidence_index picks up the side-index ------------


def test_closed_form_row_is_green_when_side_index_supplies_valid_h12_ref(monkeypatch, tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_closed_form_evidence_dir(evidence_root)

    h12_dir = tmp_path / "h12_artifacts"
    h12_path = h12_dir / f"{_CLOSED_FORM_PROCESS}_h12.json"
    _write_valid_h12_artifact(h12_path, process=_CLOSED_FORM_PROCESS)

    index_path = tmp_path / "h12_evidence_index.json"
    _write_json(index_path, {"entries": {_CLOSED_FORM_PROCESS: str(h12_path)}})
    monkeypatch.setattr(schema, "H12_EVIDENCE_INDEX_PATH", index_path)

    payload = gen.build_evidence_index(evidence_root=evidence_root)
    row = _row_for(payload, _CLOSED_FORM_PROCESS)
    assert row["mechanical_verdict"] == schema.STATUS_PASS
    assert row["green"] is True
    assert row["reasons"] == []


def test_closed_form_row_stays_non_green_when_side_index_entry_is_dangling(monkeypatch, tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_closed_form_evidence_dir(evidence_root)

    index_path = tmp_path / "h12_evidence_index.json"
    _write_json(index_path, {"entries": {_CLOSED_FORM_PROCESS: str(tmp_path / "no_such_artifact.json")}})
    monkeypatch.setattr(schema, "H12_EVIDENCE_INDEX_PATH", index_path)

    payload = gen.build_evidence_index(evidence_root=evidence_root)
    row = _row_for(payload, _CLOSED_FORM_PROCESS)
    assert row["green"] is False
    assert any("h12_evidence_ref" in reason for reason in row["reasons"])


def test_closed_form_row_stays_non_green_when_h12_artifact_is_stale(monkeypatch, tmp_path):
    """If the artifact's recorded predictor_source_sha256_lf_normalized no
    longer matches the on-disk predictor file, the row must stay non-green
    even though the side-index entry resolves and the artifact's own
    verdict says H12_CONFIRMED -- proving the freshness check is actually
    exercised via this wiring path, not just bypassed by the side-index
    shortcut. Simulated via a deliberately-wrong recorded hash written
    directly into the artifact JSON (the real production h12.py is never
    mutated by this test, since predictor_source_path is now hard-pinned
    to it)."""
    evidence_root = tmp_path / "evidence"
    _write_closed_form_evidence_dir(evidence_root)

    h12_dir = tmp_path / "h12_artifacts"
    h12_path = h12_dir / f"{_CLOSED_FORM_PROCESS}_h12.json"
    _write_valid_h12_artifact(h12_path, process=_CLOSED_FORM_PROCESS)
    # Tamper: overwrite the recorded predictor hash with a wrong value,
    # simulating an artifact generated against a since-edited predictor.
    payload = json.loads(h12_path.read_text(encoding="utf-8"))
    payload["predictor_source_sha256_lf_normalized"] = "0" * 64
    _write_json(h12_path, payload)

    index_path = tmp_path / "h12_evidence_index.json"
    _write_json(index_path, {"entries": {_CLOSED_FORM_PROCESS: str(h12_path)}})
    monkeypatch.setattr(schema, "H12_EVIDENCE_INDEX_PATH", index_path)

    payload = gen.build_evidence_index(evidence_root=evidence_root)
    row = _row_for(payload, _CLOSED_FORM_PROCESS)
    assert row["green"] is False
    assert any("STALE" in reason for reason in row["reasons"])


def test_own_result_json_h12_evidence_ref_takes_priority_over_side_index(monkeypatch, tmp_path):
    """If result.json already carries its own h12_evidence_ref (e.g. a
    future runner-native field), the side-index must not override it --
    _with_h12_evidence_ref only ever fills a GAP, never replaces an
    existing value."""
    evidence_root = tmp_path / "evidence"
    own_h12_path = tmp_path / "own_h12.json"
    _write_valid_h12_artifact(own_h12_path, process=_CLOSED_FORM_PROCESS)
    _write_closed_form_evidence_dir(evidence_root, result_overrides={"h12_evidence_ref": str(own_h12_path)})

    # Side-index points at a DANGLING path -- if it were consulted despite
    # result.json's own ref being present, the row would go non-green.
    index_path = tmp_path / "h12_evidence_index.json"
    _write_json(index_path, {"entries": {_CLOSED_FORM_PROCESS: str(tmp_path / "no_such_artifact.json")}})
    monkeypatch.setattr(schema, "H12_EVIDENCE_INDEX_PATH", index_path)

    payload = gen.build_evidence_index(evidence_root=evidence_root)
    row = _row_for(payload, _CLOSED_FORM_PROCESS)
    assert row["green"] is True
