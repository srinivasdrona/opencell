"""Tests for the LLM interaction log."""

from __future__ import annotations

import json
from pathlib import Path

from opencell.provenance.llm_log import (
    DEFAULT_LOG_PATH,
    LlmLog,
    iter_log,
    log_interaction,
)


def _make_record(**overrides: object) -> LlmLog:
    base: dict[str, object] = dict(
        role="main_agent",
        model="claude-opus-4.7",
        task_summary="test task",
        output_summary="test output",
    )
    base.update(overrides)
    return LlmLog(**base)  # type: ignore[arg-type]


def test_log_default_path_is_under_data_provenance() -> None:
    assert DEFAULT_LOG_PATH.as_posix().endswith("data/provenance/llm_interactions.jsonl")


def test_event_id_is_deterministic() -> None:
    a = _make_record(timestamp_utc="2026-05-21T14:00:00+00:00")
    b = _make_record(timestamp_utc="2026-05-21T14:00:00+00:00")
    assert a.compute_event_id() == b.compute_event_id()


def test_event_id_changes_with_content() -> None:
    a = _make_record(timestamp_utc="2026-05-21T14:00:00+00:00")
    b = _make_record(
        timestamp_utc="2026-05-21T14:00:00+00:00",
        task_summary="different task",
    )
    assert a.compute_event_id() != b.compute_event_id()


def test_log_interaction_writes_jsonl_line(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    rec = _make_record(linked_todo="x1", linked_commits=["abc123"])
    event_id = log_interaction(rec, log_path=log)

    assert event_id.startswith("sha256:")
    assert log.exists()

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["event_id"] == event_id
    assert payload["role"] == "main_agent"
    assert payload["linked_todo"] == "x1"
    assert payload["linked_commits"] == ["abc123"]
    assert payload["timestamp_utc"]
    assert payload["verification_status"] == "pending"


def test_log_interaction_appends(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log_interaction(_make_record(task_summary="first"), log_path=log)
    log_interaction(_make_record(task_summary="second"), log_path=log)

    records = list(iter_log(log_path=log))
    assert [r["task_summary"] for r in records] == ["first", "second"]


def test_iter_log_returns_empty_when_missing(tmp_path: Path) -> None:
    log = tmp_path / "nonexistent.jsonl"
    assert list(iter_log(log_path=log)) == []


def test_unknown_optional_fields_serialize_as_null(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log_interaction(_make_record(), log_path=log)
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    for k in ("temperature", "tokens_in", "tokens_out", "session_id", "supersedes"):
        assert k in record
        assert record[k] is None


def test_supersedes_chain(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    first_id = log_interaction(_make_record(task_summary="initial"), log_path=log)
    correction = _make_record(
        task_summary="initial",
        output_summary="corrected output",
        supersedes=first_id,
    )
    second_id = log_interaction(correction, log_path=log)

    assert first_id != second_id
    records = list(iter_log(log_path=log))
    assert records[1]["supersedes"] == first_id
