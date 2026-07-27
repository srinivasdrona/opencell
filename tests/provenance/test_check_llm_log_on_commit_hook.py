"""Tests for scripts/hooks/check_llm_log_on_commit.py.

The hook runs at the `commit-msg` phase (not `pre-commit`): its enforcement
depends on the commit message body, which Git only writes to disk once
`commit-msg` runs. These tests cover the unit-level behavior and the
message-path resolution logic (Git's $1 vs. the manual-invocation fallback).
See tests/git_hooks/test_llm_log_commit_msg_hook_e2e.py for full `git commit`
end-to-end coverage.
"""

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
    monkeypatch.setattr(hook, "_resolve_commit_msg_path", lambda _argv: Path("unused"))
    monkeypatch.setattr(hook, "_read_commit_message", lambda _msg_path: "refactor provenance")
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
    monkeypatch.setattr(hook, "_resolve_commit_msg_path", lambda _argv: Path("unused"))
    monkeypatch.setattr(hook, "_read_commit_message", lambda _msg_path: "feat: add cli")
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
    monkeypatch.setattr(hook, "_resolve_commit_msg_path", lambda _argv: Path("unused"))
    monkeypatch.setattr(
        hook,
        "_read_commit_message",
        lambda _msg_path: "feat: add cli\n\nCo-authored-by: Copilot <copilot@github.com>",
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
    monkeypatch.setattr(hook, "_resolve_commit_msg_path", lambda _argv: Path("unused"))
    monkeypatch.setattr(hook, "_read_commit_message", lambda _msg_path: "feat: add cli")
    monkeypatch.setattr(hook, "_has_today_entry", lambda _log_path: True)

    assert hook.main() == 0


class TestResolveCommitMsgPath:
    """Message-path resolution: Git's $1 (the commit-msg phase contract)
    with a worktree-correct fallback for manual invocation."""

    def test_uses_argv1_when_provided(self) -> None:
        hook = _load_hook_module()
        resolved = hook._resolve_commit_msg_path(["check_llm_log_on_commit.py", "/some/msg/file"])
        assert resolved == Path("/some/msg/file")

    def test_falls_back_to_git_path_when_no_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hook = _load_hook_module()

        def _fake_git_output(*args: str) -> str:
            if args == ("rev-parse", "--git-path", "COMMIT_EDITMSG"):
                return "/repo/.git/COMMIT_EDITMSG"
            raise AssertionError(args)

        monkeypatch.setattr(hook, "_git_output", _fake_git_output)
        resolved = hook._resolve_commit_msg_path(["check_llm_log_on_commit.py"])
        assert resolved == Path("/repo/.git/COMMIT_EDITMSG")


class TestReadCommitMessage:
    def test_returns_empty_string_for_missing_file(self, tmp_path: Path) -> None:
        hook = _load_hook_module()
        assert hook._read_commit_message(tmp_path / "does-not-exist") == ""

    def test_reads_existing_message_file(self, tmp_path: Path) -> None:
        hook = _load_hook_module()
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("feat: add cli\n", encoding="utf-8")
        assert hook._read_commit_message(msg_file) == "feat: add cli\n"
