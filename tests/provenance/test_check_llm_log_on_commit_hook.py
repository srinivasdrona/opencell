"""Tests for scripts/hooks/check_llm_log_on_commit.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_hook_module():
    repo_root = Path(__file__).resolve().parents[2]
    hook_path = repo_root / "scripts" / "hooks" / "check_llm_log_on_commit.py"
    spec = importlib.util.spec_from_file_location("check_llm_log_on_commit", hook_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hook_skips_non_copilot_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hook = _load_hook_module()

    def _fake_git_output(*args: str) -> str:
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path)
        if args == ("diff", "--cached", "--name-only"):
            return "opencell/provenance/llm_log.py\n"
        if args == ("config", "user.name"):
            return "Regular Developer"
        raise AssertionError(args)

    monkeypatch.setattr(hook, "_git_output", _fake_git_output)
    monkeypatch.setattr(hook, "_read_commit_message", lambda _repo_root: "refactor provenance")
    monkeypatch.setattr(hook, "_has_today_entry", lambda _log_path: False)

    assert hook.main() == 0


def test_hook_blocks_copilot_author_without_today_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = _load_hook_module()

    def _fake_git_output(*args: str) -> str:
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path)
        if args == ("diff", "--cached", "--name-only"):
            return "scripts/log_llm_interaction.py\n"
        if args == ("config", "user.name"):
            return "GitHub Copilot"
        raise AssertionError(args)

    monkeypatch.setattr(hook, "_git_output", _fake_git_output)
    monkeypatch.setattr(hook, "_read_commit_message", lambda _repo_root: "feat: add cli")
    monkeypatch.setattr(hook, "_has_today_entry", lambda _log_path: False)

    rc = hook.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "git commit --no-verify" in err
    assert "opencell/provenance/llm_interactions.jsonl" in err


def test_hook_blocks_when_message_mentions_copilot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _load_hook_module()

    def _fake_git_output(*args: str) -> str:
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path)
        if args == ("diff", "--cached", "--name-only"):
            return "scripts/log_llm_interaction.py\n"
        if args == ("config", "user.name"):
            return "Regular Developer"
        raise AssertionError(args)

    monkeypatch.setattr(hook, "_git_output", _fake_git_output)
    monkeypatch.setattr(
        hook,
        "_read_commit_message",
        lambda _repo_root: "feat: add cli\n\nCo-authored-by: Copilot <copilot@github.com>",
    )
    monkeypatch.setattr(hook, "_has_today_entry", lambda _log_path: False)

    assert hook.main() == 1


def test_hook_allows_copilot_commit_when_today_entry_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _load_hook_module()

    def _fake_git_output(*args: str) -> str:
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path)
        if args == ("diff", "--cached", "--name-only"):
            return "scripts/log_llm_interaction.py\n"
        if args == ("config", "user.name"):
            return "GitHub Copilot"
        raise AssertionError(args)

    monkeypatch.setattr(hook, "_git_output", _fake_git_output)
    monkeypatch.setattr(hook, "_read_commit_message", lambda _repo_root: "feat: add cli")
    monkeypatch.setattr(hook, "_has_today_entry", lambda _log_path: True)

    assert hook.main() == 0
