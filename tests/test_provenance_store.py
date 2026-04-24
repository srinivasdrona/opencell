"""Tests for the provenance store (Phase 4 / A3 v0.1)."""

from __future__ import annotations

import json

import pytest

from opencell.provenance import ProvenanceEvent, ProvenanceStore


@pytest.fixture
def store(tmp_path):
    return ProvenanceStore(tmp_path / "test_scope.jsonl")


def _measured(store, *, name="Vmax_PGI", value=1.5, unit="mM/s",
              source="doi:10.1093/bioinformatics/18.4.516"):
    return store.record_measured(
        param_name=name, value=value, unit=unit,
        source_ref=source,
        scope={"model": "Chassagnole2002", "variable": name},
        transformation_lineage=[
            f"Table 2 raw value {value} {unit}",
            "no conversion",
        ],
        recorded_by="human:test",
    )


def test_record_and_read_back(store):
    ev = _measured(store)
    assert ev.event_id, "event_id must be set after record"
    all_ev = store.all()
    assert len(all_ev) == 1
    assert all_ev[0].param_name == "Vmax_PGI"
    assert all_ev[0].value == 1.5


def test_event_id_is_content_addressed(store):
    ev1 = _measured(store)
    # Re-record identical event: should be idempotent.
    ev2 = _measured(store)
    assert ev1.event_id == ev2.event_id
    assert len(store.all()) == 1


def test_jsonl_is_human_readable(tmp_path):
    s = ProvenanceStore(tmp_path / "scope.jsonl")
    _measured(s)
    contents = (tmp_path / "scope.jsonl").read_text("utf-8").splitlines()
    assert len(contents) == 1
    decoded = json.loads(contents[0])
    assert decoded["param_name"] == "Vmax_PGI"
    assert decoded["unit"] == "mM/s"


def test_supersedes_resolves_current(store):
    ev1 = _measured(store, value=1.5)
    ev2 = store.record(
        ProvenanceEvent(
            param_name="Vmax_PGI", value=1.7, unit="mM/s",
            source_kind="primary_literature",
            source_ref="doi:10.9999/correction",
            scope={"model": "Chassagnole2002", "variable": "Vmax_PGI"},
            transformation_lineage=["correction per erratum"],
            event_kind="measured",
            timestamp_utc="2026-04-25T00:00:00Z",
            recorded_by="human:test",
            supersedes=ev1.event_id,
        )
    )
    cur = store.current("Vmax_PGI")
    assert cur is not None
    assert cur.event_id == ev2.event_id
    assert cur.value == 1.7


def test_tuning_within_range_ok(store):
    base = _measured(store, value=1.5)
    tuned = store.record_tuned(
        param_name="Vmax_PGI", value=1.65, unit="mM/s",
        scope={"model": "Chassagnole2002", "variable": "Vmax_PGI"},
        allowed_range=[1.0, 2.0],
        tuning_justification="fit to phenotype Y under bounded-tuning policy",
        supersedes=base.event_id,
        recorded_by="human:test",
    )
    assert tuned.event_kind == "tuned"
    assert store.current("Vmax_PGI").value == 1.65


def test_tuning_outside_range_rejected(store):
    base = _measured(store, value=1.5)
    with pytest.raises(ValueError, match="[Bb]ounded-tuning policy"):
        store.record_tuned(
            param_name="Vmax_PGI", value=99.0, unit="mM/s",
            scope={"model": "Chassagnole2002", "variable": "Vmax_PGI"},
            allowed_range=[1.0, 2.0],
            tuning_justification="should fail",
            supersedes=base.event_id,
            recorded_by="human:test",
        )


def test_query_by_scope(store):
    _measured(store, name="Vmax_PGI")
    _measured(store, name="Vmax_PFK")
    pgi = store.query(param_name="Vmax_PGI")
    assert len(pgi) == 1 and pgi[0].param_name == "Vmax_PGI"
    chass = store.query(scope_filter={"model": "Chassagnole2002"})
    assert len(chass) == 2


def test_no_deletion_api():
    """Append-only is a hard rule. There is no delete method."""
    assert not hasattr(ProvenanceStore, "delete")
    assert not hasattr(ProvenanceStore, "remove")
    assert not hasattr(ProvenanceStore, "update")


def test_corrections_are_new_events_not_mutations(tmp_path):
    s = ProvenanceStore(tmp_path / "x.jsonl")
    ev1 = _measured(s, value=1.5)
    s.record(
        ProvenanceEvent(
            param_name="Vmax_PGI", value=1.7, unit="mM/s",
            source_kind="primary_literature",
            source_ref="erratum",
            scope={"model": "Chassagnole2002", "variable": "Vmax_PGI"},
            transformation_lineage=["correction"],
            event_kind="measured",
            timestamp_utc="2026-04-25T00:00:00Z",
            recorded_by="human:test",
            supersedes=ev1.event_id,
        )
    )
    # File must contain BOTH events. History is preserved.
    lines = (tmp_path / "x.jsonl").read_text("utf-8").strip().splitlines()
    assert len(lines) == 2
