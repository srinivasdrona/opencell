"""Regression tests for scripts/git_hooks/commit-msg-l2-catalog-conformance.sh.

These tests exercise the *tracked* hook script directly (not whatever may or
may not be installed under a given worktree's .git/hooks), including full
end-to-end `git commit` runs in a throwaway repo, to prove:

1. The hook fires at `commit-msg` time, where the commit message file is
   guaranteed to exist and to hold the message for the commit in progress
   (the bug this replaces: a `pre-commit` hook reading
   `${REPO_ROOT}/.git/COMMIT_EDITMSG` fails on a repo's/worktree's very
   first commit, because pre-commit runs before Git has written any commit
   message, and because that hardcoded path is wrong for worktrees anyway,
   where `.git` is a file, not the message-holding directory).
2. Fresh, brand-new repos (i.e. worktree-first-commit-shaped) can commit
   successfully through the real hook without `--no-verify` when compliant.
3. Missing/malformed catalog entries still fail closed.
4. The `Catalog-Entry: N/A (justification: ...)` escape hatch still works,
   now at the phase where it can actually be evaluated.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / "scripts" / "git_hooks" / "commit-msg-l2-catalog-conformance.sh"

WATCHED_FILE = "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml"
UNWATCHED_FILE = "README_for_test.md"

VALID_CATALOG_ENTRY_MSG = """infra: touch catalog file

Catalog-Entry:
```yaml
  - name: Cytokinesis
    bucket: ALGORITHMIC_SHALLOW
    primary_channel: substrates
```
"""

NA_ESCAPE_MSG = "infra: refactor catalog loader\n\nCatalog-Entry: N/A (justification: no process-specific behavior change)\n"

MALFORMED_ENTRY_MSG = "infra: touch catalog file\n\nCatalog-Entry: forgot the fenced yaml block\n"

NO_TRAILER_MSG = "infra: touch catalog file\n\nNo trailer here at all.\n"


def _run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture()
def fresh_repo(tmp_path: Path) -> Path:
    """A brand-new git repo with zero commits: the exact shape of the bug."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test User"], cwd=repo)
    return repo


def _seed_llm_log_sources(repo: Path) -> None:
    """Mirror the LLM-log check's source tree into a throwaway repo.
    install.sh composes commit-msg-l2-catalog-conformance.sh with
    scripts/hooks/check_llm_log_on_commit.py into one `commit-msg` shim, so
    both must exist for install.sh to succeed, exactly as in any real
    clone/worktree of this repo."""
    for rel in (
        "scripts/hooks/check_llm_log_on_commit.py",
        "opencell/provenance/llm_log.py",
    ):
        src_file = REPO_ROOT / rel
        dest_file = repo / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_bytes(src_file.read_bytes())
        dest_file.chmod(src_file.stat().st_mode)
    (repo / "opencell" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "opencell" / "provenance" / "__init__.py").write_text("", encoding="utf-8")
    log_path = repo / "opencell" / "provenance" / "llm_interactions.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")


def _install_hook(repo: Path) -> None:
    """Mirror scripts/git_hooks/ into the throwaway repo, then run the real,
    tracked install.sh against it. install.sh resolves paths relative to
    `git rev-parse --show-toplevel`, so it must operate on a repo that has
    its own copy of scripts/git_hooks/ (as any real clone/worktree does).

    install.sh composes this catalog check with the LLM-log check
    (scripts/hooks/check_llm_log_on_commit.py) into one `commit-msg` shim
    (see scripts/git_hooks/install.sh and
    tests/git_hooks/test_llm_log_commit_msg_hook_e2e.py), so both source
    trees must exist for install.sh to succeed -- exactly as they do in any
    real clone/worktree of this repo."""
    dest_hooks_dir = repo / "scripts" / "git_hooks"
    dest_hooks_dir.mkdir(parents=True, exist_ok=True)
    src_hooks_dir = REPO_ROOT / "scripts" / "git_hooks"
    for src_file in src_hooks_dir.iterdir():
        dest_file = dest_hooks_dir / src_file.name
        dest_file.write_bytes(src_file.read_bytes())
        dest_file.chmod(src_file.stat().st_mode)

    _seed_llm_log_sources(repo)

    result = _run(["bash", str(dest_hooks_dir / "install.sh")], cwd=repo)
    assert result.returncode == 0, result.stderr


def _write_and_stage(repo: Path, rel_path: str, content: str = "x: 1\n") -> None:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _run(["git", "add", rel_path], cwd=repo)


def _commit(repo: Path, message: str) -> subprocess.CompletedProcess:
    return _run(["git", "commit", "-m", message], cwd=repo, check=False)


class TestDirectScriptInvocation:
    """Invoke the tracked script the way `commit-msg` invokes it: with the
    message file path as $1, independent of any locally installed hook."""

    def test_untriggered_when_no_watched_file_staged(self, fresh_repo: Path, tmp_path: Path) -> None:
        _write_and_stage(fresh_repo, UNWATCHED_FILE)
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text(NO_TRAILER_MSG, encoding="utf-8")
        result = _run(["bash", str(HOOK_SCRIPT), str(msg_file)], cwd=fresh_repo, check=False)
        assert result.returncode == 0, result.stderr

    def test_blocks_watched_file_without_trailer(self, fresh_repo: Path, tmp_path: Path) -> None:
        _write_and_stage(fresh_repo, WATCHED_FILE)
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text(NO_TRAILER_MSG, encoding="utf-8")
        result = _run(["bash", str(HOOK_SCRIPT), str(msg_file)], cwd=fresh_repo, check=False)
        assert result.returncode == 1
        assert "BLOCKED" in result.stderr

    def test_blocks_malformed_catalog_entry(self, fresh_repo: Path, tmp_path: Path) -> None:
        _write_and_stage(fresh_repo, WATCHED_FILE)
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text(MALFORMED_ENTRY_MSG, encoding="utf-8")
        result = _run(["bash", str(HOOK_SCRIPT), str(msg_file)], cwd=fresh_repo, check=False)
        assert result.returncode == 1
        assert "no fenced yaml block" in result.stderr

    def test_passes_with_valid_catalog_entry(self, fresh_repo: Path, tmp_path: Path) -> None:
        _write_and_stage(fresh_repo, WATCHED_FILE)
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text(VALID_CATALOG_ENTRY_MSG, encoding="utf-8")
        result = _run(["bash", str(HOOK_SCRIPT), str(msg_file)], cwd=fresh_repo, check=False)
        assert result.returncode == 0, result.stderr

    def test_passes_with_na_escape_hatch(self, fresh_repo: Path, tmp_path: Path) -> None:
        _write_and_stage(fresh_repo, WATCHED_FILE)
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text(NA_ESCAPE_MSG, encoding="utf-8")
        result = _run(["bash", str(HOOK_SCRIPT), str(msg_file)], cwd=fresh_repo, check=False)
        assert result.returncode == 0, result.stderr


class TestEndToEndFirstCommit:
    """Full `git commit` runs through the installed hook, reproducing the
    original bug's exact scenario: a brand-new repo's very first commit."""

    def test_first_commit_with_na_escape_succeeds_without_no_verify(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, WATCHED_FILE)
        result = _commit(fresh_repo, NA_ESCAPE_MSG)
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        log = _run(["git", "log", "-1", "--pretty=%B"], cwd=fresh_repo)
        assert "Catalog-Entry: N/A" in log.stdout

    def test_first_commit_with_valid_entry_succeeds(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, WATCHED_FILE)
        result = _commit(fresh_repo, VALID_CATALOG_ENTRY_MSG)
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    def test_first_commit_without_trailer_is_blocked(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, WATCHED_FILE)
        result = _commit(fresh_repo, NO_TRAILER_MSG)
        assert result.returncode != 0
        assert "BLOCKED" in result.stderr
        log = _run(["git", "log", "--oneline"], cwd=fresh_repo, check=False)
        assert log.stdout.strip() == ""

    def test_first_commit_unwatched_file_succeeds_with_any_message(self, fresh_repo: Path) -> None:
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, UNWATCHED_FILE)
        result = _commit(fresh_repo, NO_TRAILER_MSG)
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    def test_second_commit_still_enforced(self, fresh_repo: Path) -> None:
        """Guards against any accidental state leaking from the first commit
        (e.g. reading a stale message file from a prior commit)."""
        _install_hook(fresh_repo)
        _write_and_stage(fresh_repo, UNWATCHED_FILE)
        first = _commit(fresh_repo, NO_TRAILER_MSG)
        assert first.returncode == 0

        _write_and_stage(fresh_repo, WATCHED_FILE, content="x: 2\n")
        second = _commit(fresh_repo, NO_TRAILER_MSG)
        assert second.returncode != 0
        assert "BLOCKED" in second.stderr


class TestLinkedWorktreeInstall:
    """Reproduces the reported bug's exact topology: a *linked* worktree of
    a repo that already has commits, where `.git` is a file (a gitdir
    pointer) rather than a directory, and hooks live in the shared common
    git dir. This is the scenario that broke under the old pre-commit-phase
    hook (stale/hardcoded `.git/COMMIT_EDITMSG` path + reading the message
    before Git had written it for this commit)."""

    @pytest.fixture()
    def repo_with_worktree(self, tmp_path: Path) -> tuple[Path, Path]:
        main = tmp_path / "main"
        main.mkdir()
        _run(["git", "init", "-q"], cwd=main)
        _run(["git", "config", "user.email", "test@example.com"], cwd=main)
        _run(["git", "config", "user.name", "Test User"], cwd=main)
        # Mirror the tracked hook sources into the main checkout, and give
        # it at least one prior commit, mimicking a real, established repo.
        hooks_dir = main / "scripts" / "git_hooks"
        hooks_dir.mkdir(parents=True)
        src_hooks_dir = REPO_ROOT / "scripts" / "git_hooks"
        for src_file in src_hooks_dir.iterdir():
            dest_file = hooks_dir / src_file.name
            dest_file.write_bytes(src_file.read_bytes())
            dest_file.chmod(src_file.stat().st_mode)
        _seed_llm_log_sources(main)
        _run(["git", "add", "-A"], cwd=main)
        _run(["git", "commit", "-m", "initial commit"], cwd=main)

        worktree = tmp_path / "linked-worktree"
        _run(
            ["git", "worktree", "add", "-b", "agent/fix", str(worktree)],
            cwd=main,
        )
        return main, worktree

    def test_git_dir_is_a_file_in_linked_worktree(self, repo_with_worktree: tuple[Path, Path]) -> None:
        _main, worktree = repo_with_worktree
        assert (worktree / ".git").is_file()

    def test_install_from_linked_worktree_targets_shared_hooks_dir(
        self, repo_with_worktree: tuple[Path, Path]
    ) -> None:
        main, worktree = repo_with_worktree
        result = _run(["bash", "scripts/git_hooks/install.sh"], cwd=worktree)
        assert result.returncode == 0, result.stderr
        # Installed into the shared common dir, visible from the main
        # checkout too (there is exactly one hooks/ dir for the whole repo).
        assert (main / ".git" / "hooks" / "commit-msg").exists()

    def test_first_commit_in_linked_worktree_succeeds_with_escape_hatch(
        self, repo_with_worktree: tuple[Path, Path]
    ) -> None:
        """The exact reported failure: a linked worktree's first commit
        touching a watched file, using the `Catalog-Entry: N/A` escape
        hatch, must succeed without `--no-verify`."""
        _main, worktree = repo_with_worktree
        install_result = _run(["bash", "scripts/git_hooks/install.sh"], cwd=worktree)
        assert install_result.returncode == 0, install_result.stderr

        _write_and_stage(worktree, WATCHED_FILE)
        result = _commit(worktree, NA_ESCAPE_MSG)
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    def test_stale_managed_pre_commit_shim_is_migrated_away(
        self, repo_with_worktree: tuple[Path, Path]
    ) -> None:
        """A repo that installed the old pre-commit-phase hook must not be
        left with a broken shim exec'ing the now-renamed script."""
        main, worktree = repo_with_worktree
        common_hooks = main / ".git" / "hooks"
        common_hooks.mkdir(parents=True, exist_ok=True)
        stale_shim = common_hooks / "pre-commit"
        stale_shim.write_text(
            "#!/usr/bin/env bash\n"
            "# L2-CATALOG-CONFORMANCE-HOOK-MANAGED\n"
            "# Installed from scripts/git_hooks/pre-commit-l2-catalog-conformance.sh\n"
            'REPO_ROOT="$(git rev-parse --show-toplevel)"\n'
            'exec "${REPO_ROOT}/scripts/git_hooks/pre-commit-l2-catalog-conformance.sh" "$@"\n',
            encoding="utf-8",
        )
        stale_shim.chmod(0o755)

        install_result = _run(["bash", "scripts/git_hooks/install.sh"], cwd=worktree)
        assert install_result.returncode == 0, install_result.stderr
        assert not stale_shim.exists()

        _write_and_stage(worktree, UNWATCHED_FILE)
        result = _commit(worktree, NO_TRAILER_MSG)
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
