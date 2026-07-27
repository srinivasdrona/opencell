"""End-to-end regression tests for scripts/hooks/check_llm_log_on_commit.py
and its composition with scripts/git_hooks/commit-msg-l2-catalog-conformance.sh
via scripts/git_hooks/install.sh.

These exercise real `git commit` runs through the *installed* hook (not the
script in isolation), proving:

1. The LLM-log check fires at `commit-msg` time, where the commit message
   file is guaranteed to exist and hold the message for the commit in
   progress (the bug this replaces: a `pre-commit` hook reading
   `<repo_root>/.git/COMMIT_EDITMSG` sees nothing on a repo's/worktree's
   very first commit, and a stale message on later commits; `.git` is also
   a *file*, not a directory, in any linked worktree).
2. A brand-new repo's first commit succeeds without `--no-verify` when
   compliant (Copilot-authored commit + a same-day LLM-log entry, or a
   non-Copilot commit with no log requirement at all).
3. Copilot-authored commits (by author name or by `Co-authored-by: Copilot`
   trailer) are blocked without a same-day log entry, and pass once one
   exists.
4. Non-Copilot commits are never blocked by this check regardless of log
   state.
5. install.sh composes this check with the L2 catalog-conformance check
   into a single `commit-msg` shim: both run, in order, and either one
   failing blocks the commit (no silent skip of one for the other).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / "scripts" / "hooks" / "check_llm_log_on_commit.py"

LOG_REL_PATH = "opencell/provenance/llm_interactions.jsonl"
WATCHED_CATALOG_FILE = "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml"


def _run(cmd: list[str], cwd: Path, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check, env=env)


def _write_and_stage(repo: Path, rel_path: str, content: str = "x: 1\n") -> None:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _run(["git", "add", rel_path], cwd=repo)


def _commit(repo: Path, message: str, author_name: str, author_email: str) -> subprocess.CompletedProcess:
    return _run(
        [
            "git",
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
        ],
        cwd=repo,
        check=False,
    )


def _seed_repo_scripts(repo: Path) -> None:
    """Mirror the tracked hook + provenance sources into a throwaway repo,
    so it can install and run the real, tracked scripts exactly as any real
    clone/worktree would. `opencell/__init__.py` and
    `opencell/provenance/__init__.py` are stubbed out (empty) rather than
    copied verbatim: the real `opencell/provenance/__init__.py` re-exports
    from `opencell/provenance/store.py`, which this throwaway repo has no
    need for and does not seed."""
    for rel in (
        "scripts/git_hooks/commit-msg-l2-catalog-conformance.sh",
        "scripts/git_hooks/install.sh",
        "scripts/hooks/check_llm_log_on_commit.py",
        "scripts/log_llm_interaction.py",
        "opencell/provenance/llm_log.py",
    ):
        src = REPO_ROOT / rel
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        dst.chmod(src.stat().st_mode)
    (repo / "opencell" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "opencell" / "provenance" / "__init__.py").write_text("", encoding="utf-8")
    (repo / LOG_REL_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / LOG_REL_PATH).write_text("", encoding="utf-8")


def _install_hook(repo: Path) -> None:
    result = _run(["bash", "scripts/git_hooks/install.sh"], cwd=repo)
    assert result.returncode == 0, result.stderr


def _add_today_log_entry(repo: Path) -> None:
    # Pass an explicit absolute --log-path: `log_llm_interaction.py`'s
    # default path resolution (`_find_repo_root` in
    # opencell/provenance/llm_log.py) walks up looking for a `.git`
    # *directory*, which does not hold in a linked worktree (`.git` is a
    # file there). That repo-root helper is out of scope for this hook fix
    # (it's provenance-log code, not hook code, and the hook itself never
    # hits it -- see check_llm_log_on_commit.py's `_has_today_entry`, which
    # always resolves the log path from `git rev-parse --show-toplevel`,
    # already absolute). Passing an absolute path here sidesteps it in
    # tests without depending on that unrelated resolution behavior.
    result = _run(
        [
            "python3",
            "scripts/log_llm_interaction.py",
            "--role",
            "main_agent",
            "--model",
            "claude-opus-4.7",
            "--task-summary",
            "test entry",
            "--output-summary",
            "test",
            "--verification-status",
            "verified",
            "--verification-notes",
            "test",
            "--log-path",
            str(repo / LOG_REL_PATH),
        ],
        cwd=repo,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture()
def fresh_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test User"], cwd=repo)
    _seed_repo_scripts(repo)
    return repo


class TestDirectScriptInvocation:
    """Invoke the tracked script the way `commit-msg` invokes it: with the
    message file path as $1, independent of any locally installed hook."""

    def test_copilot_author_blocked_without_today_log(self, fresh_repo: Path, tmp_path: Path) -> None:
        _write_and_stage(fresh_repo, "README.md")
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("feat: change\n", encoding="utf-8")
        result = _run(
            ["python3", str(HOOK_SCRIPT), str(msg_file)],
            cwd=fresh_repo,
            check=False,
            env={"GIT_AUTHOR_NAME": "GitHub Copilot", **_base_env()},
        )
        assert result.returncode == 1
        assert "no LLM log entry for today" in result.stderr

    def test_non_copilot_author_true_negative_passes(self, fresh_repo: Path, tmp_path: Path) -> None:
        _write_and_stage(fresh_repo, "README.md")
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("feat: change\n", encoding="utf-8")
        result = _run(
            ["python3", str(HOOK_SCRIPT), str(msg_file)],
            cwd=fresh_repo,
            check=False,
            env={"GIT_AUTHOR_NAME": "Regular Developer", **_base_env()},
        )
        assert result.returncode == 0, result.stderr

    def test_trailer_true_positive_blocked_regardless_of_author(
        self, fresh_repo: Path, tmp_path: Path
    ) -> None:
        _write_and_stage(fresh_repo, "README.md")
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text(
            "feat: change\n\nCo-authored-by: Copilot <copilot@github.com>\n", encoding="utf-8"
        )
        result = _run(
            ["python3", str(HOOK_SCRIPT), str(msg_file)],
            cwd=fresh_repo,
            check=False,
            env={"GIT_AUTHOR_NAME": "Regular Developer", **_base_env()},
        )
        assert result.returncode == 1
        assert "no LLM log entry for today" in result.stderr

    def test_manual_invocation_without_argv_falls_back_to_git_path(
        self, fresh_repo: Path
    ) -> None:
        """No $1 supplied (manual/off-hook invocation): must resolve the
        message via `git rev-parse --git-path COMMIT_EDITMSG`, not a
        hardcoded `.git/COMMIT_EDITMSG` (which is wrong in worktrees and
        stale/absent on a first commit)."""
        _write_and_stage(fresh_repo, "README.md")
        # No COMMIT_EDITMSG exists yet on this repo's first commit -- the
        # hook must still run to completion (treating the message as
        # empty), not crash.
        result = _run(
            ["python3", str(HOOK_SCRIPT)],
            cwd=fresh_repo,
            check=False,
            env={"GIT_AUTHOR_NAME": "Regular Developer", **_base_env()},
        )
        assert result.returncode == 0, result.stderr


def _base_env() -> dict:
    return dict(os.environ)


class TestEndToEndFirstCommit:
    def test_first_commit_non_copilot_succeeds_without_no_verify(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, "README.md")
        result = _commit(fresh_repo, "chore: init", "Regular Dev", "dev@example.com")
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    def test_first_commit_copilot_author_blocked_without_log(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, "README.md")
        result = _commit(fresh_repo, "feat: change", "GitHub Copilot", "copilot@github.com")
        assert result.returncode != 0
        assert "no LLM log entry for today" in result.stderr
        log = _run(["git", "log", "--oneline"], cwd=fresh_repo, check=False)
        assert log.stdout.strip() == ""

    def test_first_commit_copilot_author_passes_with_today_log(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _add_today_log_entry(fresh_repo)
        _write_and_stage(fresh_repo, "README.md")
        result = _commit(fresh_repo, "feat: change", "GitHub Copilot", "copilot@github.com")
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    def test_first_commit_trailer_blocked_without_log(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, "README.md")
        result = _commit(
            fresh_repo,
            "feat: change\n\nCo-authored-by: Copilot <copilot@github.com>",
            "Regular Dev",
            "dev@example.com",
        )
        assert result.returncode != 0
        assert "no LLM log entry for today" in result.stderr

    def test_second_commit_still_enforced_no_stale_message_leak(self, fresh_repo: Path) -> None:
        """Guards against reading a stale COMMIT_EDITMSG from a prior
        commit: the second commit's own message must govern the check."""
        _install_hook(fresh_repo)
        _add_today_log_entry(fresh_repo)
        _write_and_stage(fresh_repo, "README.md")
        first = _commit(fresh_repo, "feat: change", "GitHub Copilot", "copilot@github.com")
        assert first.returncode == 0, first.stderr

        # Wipe today's log entry, then make a second Copilot commit: must
        # be blocked again, not pass by reading the first commit's message.
        (fresh_repo / LOG_REL_PATH).write_text("", encoding="utf-8")
        _write_and_stage(fresh_repo, "NOTE.md", content="hi\n")
        second = _commit(fresh_repo, "feat: change 2", "GitHub Copilot", "copilot@github.com")
        assert second.returncode != 0
        assert "no LLM log entry for today" in second.stderr


class TestLinkedWorktreeInstall:
    """Reproduces the reported bug's exact topology: `.git` as a file in a
    linked worktree, hooks in the shared common git dir, and (specific to
    this check) the legacy `pre-commit` symlink documented by
    docs/archive/diagnostics/BOOTSTRAP.md."""

    @pytest.fixture()
    def repo_with_worktree(self, tmp_path: Path) -> tuple[Path, Path]:
        main = tmp_path / "main"
        main.mkdir()
        _run(["git", "init", "-q"], cwd=main)
        _run(["git", "config", "user.email", "test@example.com"], cwd=main)
        _run(["git", "config", "user.name", "Test User"], cwd=main)
        _seed_repo_scripts(main)
        _run(["git", "add", "-A"], cwd=main)
        _run(["git", "commit", "-m", "initial commit"], cwd=main)

        worktree = tmp_path / "linked-worktree"
        _run(["git", "worktree", "add", "-b", "agent/fix", str(worktree)], cwd=main)
        return main, worktree

    def test_git_dir_is_a_file_in_linked_worktree(self, repo_with_worktree: tuple[Path, Path]) -> None:
        _main, worktree = repo_with_worktree
        assert (worktree / ".git").is_file()

    def test_legacy_pre_commit_symlink_is_migrated_away(
        self, repo_with_worktree: tuple[Path, Path]
    ) -> None:
        """A repo set up per the old BOOTSTRAP.md instructions
        (`ln -sf ../../scripts/hooks/check_llm_log_on_commit.py
        .git/hooks/pre-commit`) must have that stale pre-commit-phase check
        removed by install.sh, not left double-running alongside the new
        commit-msg composition."""
        main, worktree = repo_with_worktree
        common_hooks = main / ".git" / "hooks"
        common_hooks.mkdir(parents=True, exist_ok=True)
        legacy_symlink = common_hooks / "pre-commit"
        legacy_symlink.symlink_to(Path("..") / ".." / "scripts" / "hooks" / "check_llm_log_on_commit.py")

        install_result = _run(["bash", "scripts/git_hooks/install.sh"], cwd=worktree)
        assert install_result.returncode == 0, install_result.stderr
        assert not legacy_symlink.exists()
        assert (main / ".git" / "hooks" / "commit-msg").exists()

    def test_first_commit_in_linked_worktree_copilot_blocked_then_passes(
        self, repo_with_worktree: tuple[Path, Path]
    ) -> None:
        _main, worktree = repo_with_worktree
        install_result = _run(["bash", "scripts/git_hooks/install.sh"], cwd=worktree)
        assert install_result.returncode == 0, install_result.stderr

        _write_and_stage(worktree, "NOTE.md", content="hi\n")
        blocked = _commit(worktree, "feat: change", "GitHub Copilot", "copilot@github.com")
        assert blocked.returncode != 0
        assert "no LLM log entry for today" in blocked.stderr

        _add_today_log_entry(worktree)
        _write_and_stage(worktree, "NOTE2.md", content="hi\n")
        passed = _commit(worktree, "feat: change 2", "GitHub Copilot", "copilot@github.com")
        assert passed.returncode == 0, f"stdout={passed.stdout!r} stderr={passed.stderr!r}"


class TestCoexistenceWithCatalogHook:
    """install.sh composes the L2 catalog-conformance check and this
    LLM-log check into a single `commit-msg` shim. Both must run, in
    order, on the same commit -- neither silently skips the other."""

    def test_catalog_check_runs_and_blocks_before_llm_log_check(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, WATCHED_CATALOG_FILE)
        result = _commit(
            fresh_repo,
            "feat: touch catalog, no trailer",
            "GitHub Copilot",
            "copilot@github.com",
        )
        assert result.returncode != 0
        # Catalog hook fires first and blocks; llm-log hook never runs
        # (its message is not present).
        assert "commit-msg-l2: BLOCKED" in result.stderr
        assert "no LLM log entry for today" not in result.stderr

    def test_catalog_passes_but_llm_log_still_blocks(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, WATCHED_CATALOG_FILE)
        result = _commit(
            fresh_repo,
            "feat: touch catalog\n\nCatalog-Entry: N/A (justification: infra)",
            "GitHub Copilot",
            "copilot@github.com",
        )
        assert result.returncode != 0
        assert "commit-msg-l2: PASS" in result.stderr
        assert "no LLM log entry for today" in result.stderr

    def test_both_checks_satisfied_commit_succeeds(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _add_today_log_entry(fresh_repo)
        _write_and_stage(fresh_repo, WATCHED_CATALOG_FILE)
        result = _commit(
            fresh_repo,
            "feat: touch catalog\n\nCatalog-Entry: N/A (justification: infra)",
            "GitHub Copilot",
            "copilot@github.com",
        )
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        log = _run(["git", "log", "-1", "--pretty=%B"], cwd=fresh_repo)
        assert "Catalog-Entry: N/A" in log.stdout
