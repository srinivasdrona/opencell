"""Tests for scripts/log_llm_interaction.py CLI behaviors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.log_llm_interaction as cli
from opencell.provenance.llm_log import LlmLog, log_interaction


def _seed_log(log_path: Path) -> None:
    log_interaction(
        LlmLog(
            role="main_agent",
            model="model-a",
            task_summary="wk20-main",
            output_summary="done",
            decision_impact="unblocked x",
            timestamp_utc="2026-05-20T10:00:00+00:00",
        ),
        log_path=log_path,
    )
    log_interaction(
        LlmLog(
            role="sub_agent",
            model="model-b",
            task_summary="wk20-sub",
            output_summary="done",
            timestamp_utc="2026-05-21T08:00:00+00:00",
        ),
        log_path=log_path,
    )
    log_interaction(
        LlmLog(
            role="main_agent",
            model="model-a",
            task_summary="wk21-main",
            output_summary="done",
            timestamp_utc="2026-05-28T09:00:00+00:00",
            linked_commits=["abc123"],
        ),
        log_path=log_path,
    )


def test_log_subcommand_constructs_llm_record(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, object] = {}

    def _fake_log_interaction(record: LlmLog, log_path: str | None = None) -> str:
        captured["record"] = record
        captured["log_path"] = log_path
        return "sha256:test-event"

    monkeypatch.setattr(cli, "log_interaction", _fake_log_interaction)

    rc = cli.main(
        [
            "log",
            "--role",
            "main_agent",
            "--model",
            "gpt-5.4",
            "--task-summary",
            "task",
            "--output-summary",
            "output",
            "--linked-commits",
            "a1,b2",
            "--tags",
            "meta,cli",
            "--log-path",
            "tmp/events.jsonl",
        ]
    )

    assert rc == 0
    assert capsys.readouterr().out.strip() == "sha256:test-event"

    record = captured["record"]
    assert isinstance(record, LlmLog)
    assert record.role == "main_agent"
    assert record.model == "gpt-5.4"
    assert record.task_summary == "task"
    assert record.output_summary == "output"
    assert record.linked_commits == ["a1", "b2"]
    assert record.tags == ["meta", "cli"]
    assert record.verification_status == "pending"
    assert captured["log_path"] == "tmp/events.jsonl"


def test_query_subcommand_filters_by_model_role_since(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_path = tmp_path / "events.jsonl"
    _seed_log(log_path)

    rc = cli.main(
        [
            "query",
            "--by-model",
            "model-a",
            "--by-role",
            "main_agent",
            "--since",
            "2026-05-25",
            "--log-path",
            str(log_path),
        ]
    )

    assert rc == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    payloads = [json.loads(line) for line in lines]
    assert len(payloads) == 1
    assert payloads[0]["task_summary"] == "wk21-main"
    assert payloads[0]["model"] == "model-a"
    assert payloads[0]["role"] == "main_agent"


def test_stats_subcommand_counts_correctly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log_path = tmp_path / "events.jsonl"
    _seed_log(log_path)

    rc = cli.main(["stats", "--log-path", str(log_path)])
    assert rc == 0
    output = capsys.readouterr().out
    assert "Total records: 3" in output
    assert "Unique models: 2" in output
    assert "- main_agent: 2" in output
    assert "- sub_agent: 1" in output


def test_report_markdown_has_expected_structure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_path = tmp_path / "events.jsonl"
    _seed_log(log_path)

    rc = cli.main(["report", "--markdown", "--log-path", str(log_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("# LLM Interaction Weekly Report")
    assert "## Week 2026-W21" in out
    assert "## Week 2026-W22" in out
    assert "- Records:" in out
    assert "- Notable events:" in out


@pytest.mark.parametrize(
    "argv",
    [
        ["log", "--role", "main_agent", "--model", "gpt-5.4", "--task-summary", "task"],
        ["report"],
    ],
)
def test_missing_required_args_raise_system_exit(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(argv)


def test_invalid_query_since_date_raises_parse_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_path = tmp_path / "events.jsonl"
    _seed_log(log_path)

    with pytest.raises(SystemExit):
        cli.main(["query", "--since", "not-a-date", "--log-path", str(log_path)])

    err = capsys.readouterr().err
    assert "Invalid date/time 'not-a-date'" in err
