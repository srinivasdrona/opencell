import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from l21_promote_cytokinesis_manifest import _repo_relative_source_path  # noqa: E402


def test_repo_relative_source_path_normalizes_trace_inside_current_checkout(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "data" / "trace.mat"
    trace.parent.mkdir()
    trace.touch()

    assert _repo_relative_source_path(str(trace), repo_root=tmp_path) == "data/trace.mat"


def test_repo_relative_source_path_rejects_sibling_worktree_trace(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "current"
    repo_root.mkdir()
    sibling_trace = tmp_path / "sibling" / "data" / "trace.mat"
    sibling_trace.parent.mkdir(parents=True)
    sibling_trace.touch()

    with pytest.raises(ValueError, match="inside the current repository root"):
        _repo_relative_source_path(str(sibling_trace), repo_root=repo_root)
