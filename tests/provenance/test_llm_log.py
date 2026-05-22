"""Tests for the LLM interaction log."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import opencell.provenance.llm_log as llm_log_module
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


def test_log_default_path_is_under_opencell_provenance() -> None:
    assert DEFAULT_LOG_PATH.as_posix().endswith("opencell/provenance/llm_interactions.jsonl")


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


def test_event_id_changes_with_schema_version() -> None:
    a = _make_record(
        timestamp_utc="2026-05-21T14:00:00+00:00",
        schema_version="1.0.0",
    )
    b = _make_record(
        timestamp_utc="2026-05-21T14:00:00+00:00",
        schema_version="2.0.0",
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
    assert payload["schema_version"] == "1.0.0"
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


@pytest.mark.parametrize(
    ("pattern_name", "secret_text"),
    [
        ("aws_access_key", "my key is AKIA1234567890ABCDEF for deploy"),
        (
            "aws_secret_access_key",
            'secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
        ),
        ("github_pat", "token=ghp_" + ("A" * 36)),
        ("openai_api_key", "export OPENAI_API_KEY=sk-" + ("A" * 24)),
        ("azure_storage_sas_sig", "https://x.blob.core.windows.net/c?sig=" + ("A" * 24)),
        ("generic_bearer_token", "Authorization: Bearer " + ("a" * 25)),
    ],
)
def test_likely_secrets_raise_for_prompt_summary(
    tmp_path: Path, pattern_name: str, secret_text: str
) -> None:
    log = tmp_path / "events.jsonl"
    rec = _make_record(prompt_summary=secret_text)
    with pytest.raises(ValueError, match=rf"Likely secret in prompt_summary: {pattern_name}"):
        log_interaction(rec, log_path=log)
    assert not log.exists()


@pytest.mark.parametrize(
    ("pattern_name", "safe_text"),
    [
        ("aws_access_key", "AKIA1234 is too short to be a key"),
        ("aws_secret_access_key", "secret_access_key=shortsecret"),
        ("github_pat", "ghp_short"),
        ("openai_api_key", "sk-short"),
        ("azure_storage_sas_sig", "https://x.blob.core.windows.net/c?sig=short"),
        ("generic_bearer_token", "Authorization: Bearer shorttoken"),
    ],
)
def test_safe_text_does_not_trigger_secret_detection(
    tmp_path: Path, pattern_name: str, safe_text: str
) -> None:
    log = tmp_path / "events.jsonl"
    rec = _make_record(prompt_summary=f"{pattern_name}: {safe_text}")
    event_id = log_interaction(rec, log_path=log)
    assert event_id.startswith("sha256:")
    assert log.exists()


def test_output_summary_is_scanned_for_secrets(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    rec = _make_record(output_summary="Authorization: Bearer " + ("b" * 30))
    with pytest.raises(
        ValueError,
        match=r"Likely secret in output_summary: generic_bearer_token",
    ):
        log_interaction(rec, log_path=log)
    assert not log.exists()


def test_find_repo_root_from_pyproject_marker(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    nested = repo_root / "src" / "deeper"
    nested.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    assert llm_log_module._find_repo_root(start=nested) == repo_root


def test_find_repo_root_raises_without_markers(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    with pytest.raises(
        RuntimeError,
        match=r"Could not find repo root: no \.git or pyproject\.toml in any parent directory",
    ):
        llm_log_module._find_repo_root(start=nested)


def test_rotation_to_monthly_shards_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "llm_interactions.jsonl"
    monkeypatch.setattr(llm_log_module, "ROTATE_ENTRY_THRESHOLD", 2)

    log_interaction(
        _make_record(task_summary="jan-1", timestamp_utc="2026-01-05T10:00:00+00:00"),
        log_path=log,
    )
    log_interaction(
        _make_record(task_summary="jan-2", timestamp_utc="2026-01-10T10:00:00+00:00"),
        log_path=log,
    )
    log_interaction(
        _make_record(task_summary="feb-1", timestamp_utc="2026-02-03T10:00:00+00:00"),
        log_path=log,
    )

    header = json.loads(log.read_text(encoding="utf-8"))
    assert header == {"rotated": True, "shards": "llm_interactions/"}
    assert (tmp_path / "llm_interactions" / "2026-01.jsonl").exists()
    assert (tmp_path / "llm_interactions" / "2026-02.jsonl").exists()

    tasks = [rec["task_summary"] for rec in iter_log(log_path=log)]
    assert tasks == ["jan-1", "jan-2", "feb-1"]

    llm_log_module._rotate_to_shards(log)
    tasks_after_second_rotation = [rec["task_summary"] for rec in iter_log(log_path=log)]
    assert tasks_after_second_rotation == ["jan-1", "jan-2", "feb-1"]

    log_interaction(
        _make_record(task_summary="mar-1", timestamp_utc="2026-03-02T10:00:00+00:00"),
        log_path=log,
    )
    assert (tmp_path / "llm_interactions" / "2026-03.jsonl").exists()
    all_tasks = [rec["task_summary"] for rec in iter_log(log_path=log)]
    assert all_tasks == ["jan-1", "jan-2", "feb-1", "mar-1"]
