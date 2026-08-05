"""Unit tests for `scripts/l2_event/write_cytokinesis_canary_d_evidence.py`
(Opus review, 2026-08-05, post-Canary-D reuse/integration fixes).

Covers:
* item 1 -- ADAPTER_ID resolves to the real, registered
  `CytokinesisEventAdapter.adapter_id`, never a bespoke invented string.
* item 2 -- `build_evidence` fails CLOSED (raises `ValueError`) if the
  loaded trace's `process_name`/`seed` metadata does not match what the
  caller actually requested, BEFORE any further processing happens.
* item 3 -- the two-commit reproducibility guard
  (`_assert_registry_and_adapter_committed`/`_git_porcelain_status`)
  refuses to proceed while the registry or adapter module has
  uncommitted working-tree changes, and is silent (no-op) when clean.

None of these tests touch the real git working tree or require a real
Cytokinesis MAT trace on disk -- `load_event_window` and
`_git_porcelain_status` are monkeypatched so every branch is exercised
deterministically.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.l2_event.write_cytokinesis_canary_d_evidence as wcde
from scripts.l2_event.adapters.cytokinesis import CytokinesisEventAdapter


def test_adapter_id_resolves_to_the_real_registered_adapter():
    """The module-level ADAPTER_ID constant must be the actual
    `CytokinesisEventAdapter.adapter_id` value, never a hand-typed
    duplicate string that could silently drift out of sync with the
    real adapter (Opus review item 1)."""
    assert CytokinesisEventAdapter.adapter_id == wcde.ADAPTER_ID
    assert wcde.ADAPTER_ID == "cytokinesis.pinched_diameter_completion.v1"
    assert CytokinesisEventAdapter.process_name == wcde.PROCESS


def _fake_window(*, process_name: str, seed: int) -> SimpleNamespace:
    """A minimal stand-in for `window_loader.EventWindow` carrying only
    the two attributes `build_evidence`'s fail-closed guard reads before
    doing anything else -- sufficient because the guard must raise
    BEFORE any other attribute of `window` is ever touched."""
    return SimpleNamespace(process_name=process_name, seed=seed)


def test_build_evidence_refuses_mismatched_process_name(monkeypatch):
    """Fail-closed guard (Opus review item 2): a trace whose own
    `process_name` metadata does not say 'Cytokinesis' must never be
    silently accepted -- e.g. a caller pointing `--trace-path` at the
    wrong process's trace file by mistake."""
    monkeypatch.setattr(wcde, "load_event_window", lambda *a, **k: _fake_window(process_name="RibosomeAssembly", seed=0))
    with pytest.raises(ValueError, match="process_name"):
        wcde.build_evidence(Path("irrelevant.mat"), seed=0)


def test_build_evidence_refuses_mismatched_seed(monkeypatch):
    """Fail-closed guard (Opus review item 2): a trace whose `seed`
    metadata does not match the caller's requested `--seed` must never
    be silently accepted -- e.g. a stale/renamed file pointing at the
    wrong seed's trace."""
    monkeypatch.setattr(wcde, "load_event_window", lambda *a, **k: _fake_window(process_name="Cytokinesis", seed=7))
    with pytest.raises(ValueError, match="seed"):
        wcde.build_evidence(Path("irrelevant.mat"), seed=0)


def test_build_evidence_process_seed_guard_runs_before_the_commit_guard(monkeypatch):
    """The process/seed fail-closed check must run BEFORE the two-commit
    reproducibility guard (`_assert_registry_and_adapter_committed`) --
    a mismatched trace is refused on its own terms, never masked by (or
    dependent on) the git-cleanliness check. Proven by making the commit
    guard itself raise if it is ever reached, and confirming the
    process-name mismatch error surfaces instead."""

    def _explode(*_a, **_k):
        raise AssertionError("_assert_registry_and_adapter_committed must not run before the process/seed guard")

    monkeypatch.setattr(wcde, "load_event_window", lambda *a, **k: _fake_window(process_name="NotCytokinesis", seed=0))
    monkeypatch.setattr(wcde, "_assert_registry_and_adapter_committed", _explode)
    with pytest.raises(ValueError, match="process_name"):
        wcde.build_evidence(Path("irrelevant.mat"), seed=0)


def test_assert_registry_and_adapter_committed_raises_when_dirty(monkeypatch):
    """The two-commit reproducibility guard (Opus review item 3) must
    raise when `_git_porcelain_status` reports any uncommitted change to
    the registry or adapter module."""
    monkeypatch.setattr(wcde, "_git_porcelain_status", lambda paths: " M docs/phase_f/l2_event/event_registry.yaml\n")
    with pytest.raises(RuntimeError, match="uncommitted"):
        wcde._assert_registry_and_adapter_committed(Path("docs/phase_f/l2_event/event_registry.yaml"))


def test_assert_registry_and_adapter_committed_silent_when_clean(monkeypatch):
    """The guard must be a silent no-op (no raise) when the registry and
    adapter module have no uncommitted changes -- the sanctioned state
    for regenerating evidence in a follow-up commit."""
    monkeypatch.setattr(wcde, "_git_porcelain_status", lambda paths: "")
    wcde._assert_registry_and_adapter_committed(Path("docs/phase_f/l2_event/event_registry.yaml"))


def test_git_porcelain_status_passes_translated_git_dir_args_through(monkeypatch):
    """`_git_porcelain_status` must forward whatever `--git-dir=...` args
    `_resolve_git_dir_args` computes (the WSL-worktree-gitdir-translation
    workaround) into the actual `git status` invocation, rather than
    silently running an untranslated command that would fail outright
    under this project's mandated WSL execution (see
    `_resolve_git_dir_args`'s docstring for the empirically-confirmed
    "not a git repository" failure this guards against)."""
    captured_argv: list[str] = []

    class _FakeCompletedProcess:
        stdout = ""

    def _fake_run(argv, **_kwargs):
        captured_argv.extend(argv)
        return _FakeCompletedProcess()

    monkeypatch.setattr(wcde, "_resolve_git_dir_args", lambda: ["--git-dir=/mnt/e/opencell/.git/worktrees/fake"])
    monkeypatch.setattr(wcde.subprocess, "run", _fake_run)
    wcde._git_porcelain_status([Path("some/file.yaml")])
    assert "--git-dir=/mnt/e/opencell/.git/worktrees/fake" in captured_argv
    assert captured_argv[0] == "git"
    assert "status" in captured_argv
    assert "--porcelain" in captured_argv
