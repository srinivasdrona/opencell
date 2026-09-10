"""Regression tests for scripts/l22_dnas_promote_n200_evidence.py's source
checkpoint resolution.

Real incident (2026-09-10, second Opus review round): the script computed
`source_checkpoint_sha256` from a path rooted at `LIVE_DIR.parent`
(`artifacts/l2_2_gates/DNASupercoiling/...`, the live/gitignored standard
sweep-output tree), which never actually holds the two-sided-eval
checkpoint -- that file only ever lives in the TRACKED portable bundle,
alongside `two_sided_gate_evaluation.json` itself. The lookup silently fell
back to hashing `b""` whenever the (always-absent) live-tree path was
missing, so the canonical `result.json` recorded the SHA-256 of the empty
string (`e3b0c442...b855`) instead of the real checkpoint's hash
(`7e52aecb...3bd7`), without ever failing loudly.

Fixed by resolving the checkpoint path from `TWO_SIDED_EVAL_PATH.parent`
(the correct, tracked bundle directory) and refusing (fail-closed, exit 1)
if that file is missing, rather than silently hashing empty bytes.

Run via `bin\\oc-pytest tests/scripts/test_l22_dnas_promote_n200_evidence.py -v`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.l22_dnas_promote_n200_evidence as promote_mod  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402


def test_checkpoint_path_resolves_under_tracked_bundle_not_live_tree():
    """The checkpoint must be resolved as a sibling of the tracked
    `two_sided_gate_evaluation.json` (under `schema.BUNDLE_ROOT`), never
    under `schema.EVIDENCE_ROOT` (the live/gitignored sweep-output tree,
    which has no such file)."""
    assert promote_mod.TWO_SIDED_EVAL_CHECKPOINT_PATH.parent == promote_mod.TWO_SIDED_EVAL_PATH.parent
    assert str(schema.BUNDLE_ROOT) in str(promote_mod.TWO_SIDED_EVAL_CHECKPOINT_PATH)
    assert str(schema.EVIDENCE_ROOT) not in str(promote_mod.TWO_SIDED_EVAL_CHECKPOINT_PATH)


def test_main_refuses_fail_closed_when_checkpoint_missing(tmp_path, monkeypatch, capsys):
    """A missing checkpoint file must refuse (exit 1) with an explicit
    message naming the missing path, never silently hash `b""` and
    proceed. `LIVE_DIR` only needs to exist as a directory to reach this
    check (the checkpoint check runs before `result.json` is even read);
    `TWO_SIDED_EVAL_PATH` is left pointing at the real tracked evaluation
    so this test exercises exactly the one guard under test."""
    fake_live_dir = tmp_path / "live"
    fake_live_dir.mkdir()
    monkeypatch.setattr(promote_mod, "LIVE_DIR", fake_live_dir)

    assert promote_mod.TWO_SIDED_EVAL_PATH.is_file(), (
        "precondition: the real tracked two-sided evaluation must exist for this test to be meaningful"
    )

    missing_checkpoint = tmp_path / "does_not_exist_checkpoint.npz"
    assert not missing_checkpoint.is_file()
    monkeypatch.setattr(promote_mod, "TWO_SIDED_EVAL_CHECKPOINT_PATH", missing_checkpoint)

    exit_code = promote_mod.main([])

    assert exit_code == 1, "must refuse (non-zero exit) when the checkpoint file is missing"
    captured = capsys.readouterr()
    assert "REFUSED" in captured.err
    assert str(missing_checkpoint) in captured.err
    assert "source_checkpoint_sha256" in captured.err or "checkpoint" in captured.err


def test_canonical_result_source_checkpoint_sha256_matches_actual_checkpoint_file():
    """Durable regression against the b"" bug: the tracked canonical
    `evidence_bundle/DNASupercoiling/latest/result.json`'s chromosome
    channel `source_checkpoint_sha256` must equal the SHA-256 of the ACTUAL
    checkpoint file bytes on disk, never the hash of empty bytes
    (`e3b0c442...b855`) or any other stand-in."""
    result_path = schema.BUNDLE_ROOT / "DNASupercoiling" / "latest" / "result.json"
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    recorded = result_payload["channels"]["chromosome"]["source_checkpoint_sha256"]

    checkpoint_path = promote_mod.TWO_SIDED_EVAL_CHECKPOINT_PATH
    assert checkpoint_path.is_file(), f"expected tracked checkpoint at {checkpoint_path}"
    actual = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()

    empty_hash = hashlib.sha256(b"").hexdigest()
    assert recorded != empty_hash, (
        "source_checkpoint_sha256 must never be the hash of empty bytes -- "
        "this is exactly the silent b'' fallback bug this test guards against"
    )
    assert recorded == actual, (
        f"source_checkpoint_sha256 ({recorded!r}) does not match the actual checkpoint file's "
        f"SHA-256 ({actual!r}) at {checkpoint_path}"
    )
