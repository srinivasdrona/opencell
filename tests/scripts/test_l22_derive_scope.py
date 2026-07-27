"""Targeted tests for scripts/l22_extraction/derive_scope.py.

Confirms the production process set is derived mechanically (not hand-typed)
from `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`, matching the task's
Phase 1 item 1 requirement. The "expected 16" assertion is deliberately
explicit (not just `len(...) == 16`) so any future catalog edit that changes
the derived set is caught by name, not just by count.

Run via `bin\\oc-pytest tests/scripts/test_l22_derive_scope.py -v`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction import derive_scope as ds  # noqa: E402

EXPECTED_PRODUCTION_SET = frozenset(
    {
        "DNARepair",
        "DNASupercoiling",
        "MacromolecularComplexation",
        "Metabolism",
        "ProteinDecay",
        "ProteinFolding",
        "ProteinModification",
        "ProteinProcessingI",
        "ProteinProcessingII",
        "ProteinTranslocation",
        "RNADecay",
        "RNAModification",
        "RNAProcessing",
        "Replication",
        "ReplicationInitiation",
        "tRNAAminoacylation",
    }
)
EXPECTED_SPECIALIZED = frozenset({"Transcription", "Translation"})
EXPECTED_EVENT_CLASS = frozenset({"Cytokinesis", "DNADamage", "FtsZPolymerization", "RibosomeAssembly"})


def test_real_catalog_production_set_matches_expected_16():
    report = ds.derive_scope()
    assert set(report.production) == EXPECTED_PRODUCTION_SET
    assert len(report.production) == 16


def test_real_catalog_specialized_excluded_are_transcription_and_translation():
    report = ds.derive_scope()
    assert set(report.specialized_excluded.keys()) == EXPECTED_SPECIALIZED


def test_real_catalog_event_class_processes_are_never_in_production():
    report = ds.derive_scope()
    assert not (set(report.production) & EXPECTED_EVENT_CLASS)
    assert set(report.event_class_excluded) == EXPECTED_EVENT_CLASS


def test_real_catalog_out_of_scope_processes_are_never_in_production():
    report = ds.derive_scope()
    assert not (set(report.production) & set(report.out_of_scope_excluded))
    assert len(report.out_of_scope_excluded) == 6


def test_production_plus_specialized_equals_design_a_per_tick_in_scope():
    report = ds.derive_scope()
    assert set(report.production) | set(report.specialized_excluded.keys()) == set(
        report.design_a_per_tick_in_scope
    )


def test_specialized_ensemble_with_insufficient_seeds_falls_back_to_production(tmp_path):
    # A process with a specialized-ensemble MANIFEST.json declaring seeds but
    # fewer than 50 actually present on disk must NOT be excluded -- it needs
    # the generic production extraction, not a "trust the manifest" shortcut.
    catalog = {
        "buckets": {"ALGORITHMIC_SHALLOW": {"harness_type": "design_a_per_tick"}},
        "processes": [
            {"name": "RNADecay", "bucket": "ALGORITHMIC_SHALLOW", "in_scope_L2_2": True},
        ],
    }
    ensemble_dir = tmp_path / "ensembles" / "rnadecay"
    ensemble_dir.mkdir(parents=True)
    (ensemble_dir / "MANIFEST.json").write_text(json.dumps({"present_seed_count": 50}), encoding="utf-8")
    # Only 3 seed directories actually exist on disk, contradicting the manifest.
    for seed in range(3):
        seed_dir = ensemble_dir / f"seed_{seed:03d}"
        seed_dir.mkdir()
        (seed_dir / "RNADecay_100ticks.mat").write_bytes(b"")

    report = ds.derive_scope(catalog, karr_native_root=tmp_path)
    assert report.production == ("RNADecay",)
    assert report.specialized_excluded == {}


def test_specialized_ensemble_with_full_seeds_is_excluded(tmp_path):
    catalog = {
        "buckets": {"ALGORITHMIC_DEEP": {"harness_type": "design_a_per_tick"}},
        "processes": [
            {"name": "Transcription", "bucket": "ALGORITHMIC_DEEP", "in_scope_L2_2": True},
        ],
    }
    ensemble_dir = tmp_path / "ensembles" / "transcription"
    ensemble_dir.mkdir(parents=True)
    (ensemble_dir / "MANIFEST.json").write_text(json.dumps({"present_seed_count": 50}), encoding="utf-8")
    for seed in range(50):
        seed_dir = ensemble_dir / f"seed_{seed:03d}"
        seed_dir.mkdir()
        (seed_dir / "Transcription_100ticks.mat").write_bytes(b"")

    report = ds.derive_scope(catalog, karr_native_root=tmp_path)
    assert report.production == ()
    assert "Transcription" in report.specialized_excluded


def test_in_scope_process_missing_harness_type_raises():
    catalog = {
        "buckets": {},
        "processes": [{"name": "Mystery", "bucket": "UNKNOWN_BUCKET", "in_scope_L2_2": True}],
    }
    try:
        ds.derive_scope(catalog, karr_native_root=Path("."))
    except ValueError as exc:
        assert "harness_type" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError for missing harness_type")


def test_out_of_scope_process_without_harness_type_does_not_raise(tmp_path):
    catalog = {
        "buckets": {"DETERMINISTIC": {}},
        "processes": [{"name": "Deterministic1", "bucket": "DETERMINISTIC", "in_scope_L2_2": False}],
    }
    report = ds.derive_scope(catalog, karr_native_root=tmp_path)
    assert report.out_of_scope_excluded == ("Deterministic1",)


def test_report_to_dict_is_json_serializable():
    report = ds.derive_scope()
    json.dumps(report.to_dict())
