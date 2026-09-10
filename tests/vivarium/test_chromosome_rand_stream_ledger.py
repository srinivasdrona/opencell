"""Dedicated unit tests for the SHARED chromosome-rand-stream ledger loader
(`tests/vivarium/chromosome_rand_stream_ledger.py`), covering both the
DNADamage lane and the TranscriptionalRegulation lane (dec-006).

All fixtures here are synthetic and self-contained (a fresh `tmp_path` per
test) -- this suite never depends on or mutates the real
`data/m1_sources/WholeCell` checkout for its PASS-path assertions, except
where explicitly testing the real-main-checkout fallback resolution.

Companion to `tests/util/test_txreg_mcg_rand.py` (the RNG generator/replay
stream classes themselves) and the L2.1 replay tests that exercise this
loader end-to-end against real genuine traces
(`test_karr_dna_damage_l2_replay.py`,
`test_karr_transcriptional_regulation_l2_replay.py`).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import h5py
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import chromosome_rand_stream_ledger as ledger_mod

_CHROMOSOME_PARTS = ("src", "+edu", "+stanford", "+covert", "+cell", "+sim", "+state", "Chromosome.m")
_RANDSTREAM_PARTS = ("src", "+edu", "+stanford", "+covert", "+util", "RandStream.m")

_DEFAULT_DNADAMAGE_SHA = "d" * 64


def _make_fake_repo(tmp_path: Path) -> Path:
    """Build a minimal synthetic repo_root with just enough of the
    worktree-local WCM layout for `resolve_wcm_source_path` to prefer it
    over the real E:\\opencell/`/mnt/e/opencell` fallbacks (a
    `data/Simulation_fitted.mat` sentinel file is all that gate checks
    for)."""
    wcm_root = tmp_path / "data" / "m1_sources" / "WholeCell"
    (wcm_root / "data").mkdir(parents=True)
    (wcm_root / "data" / "Simulation_fitted.mat").write_bytes(b"fake-fitted-snapshot")
    return tmp_path


def _write_source_file(repo_root: Path, *parts: str, content: bytes) -> Path:
    path = repo_root / "data" / "m1_sources" / "WholeCell" / Path(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _write_fake_trace(trace_path: Path, *, dnadamage_source_resolved_sha256: str | None) -> None:
    """A minimal real HDF5 (.mat -v7.3 style) file with just the
    `/metadata/dnadamage_source_resolved_sha256` field the loader's
    DNADamage cross-check reads -- `_read_trace_metadata_text` opens
    `trace_path` via `h5py.File`, so a plain-bytes stub file (as used by
    an earlier, since-superseded version of this fixture) will not do."""
    with h5py.File(trace_path, "w") as handle:
        meta = handle.create_group("metadata")
        if dnadamage_source_resolved_sha256 is not None:
            meta.create_dataset(
                "dnadamage_source_resolved_sha256",
                data=dnadamage_source_resolved_sha256.encode("utf-8"),
            )


def _build_valid_ledger(
    repo_root: Path,
    trace_path: Path,
    *,
    chromosome_content: bytes = b"function result = isRegionAccessible()\nend\n",
    randstream_content: bytes = b"function state = get.state(this)\nend\n",
    dnadamage_source_sha256: str = _DEFAULT_DNADAMAGE_SHA,
    trace_dnadamage_sha256: str | None = _DEFAULT_DNADAMAGE_SHA,
) -> tuple[Path, dict]:
    _write_fake_trace(trace_path, dnadamage_source_resolved_sha256=trace_dnadamage_sha256)
    chromosome_path = _write_source_file(repo_root, *_CHROMOSOME_PARTS, content=chromosome_content)
    randstream_path = _write_source_file(repo_root, *_RANDSTREAM_PARTS, content=randstream_content)

    payload = {
        "trace_sha256": ledger_mod.sha256_raw_bytes(trace_path),
        "chromosome_source_sha256": ledger_mod.sha256_raw_bytes(chromosome_path),
        "randstream_util_source_sha256": ledger_mod.sha256_raw_bytes(randstream_path),
        "dnadamage_source_sha256": dnadamage_source_sha256,
        "n_ticks": 1,
        "per_tick": [{"tick": 1, "state_before": 1.0, "state_after": 2.0, "n_draws": 2, "draws": [0.1, 0.2]}],
    }
    ledger_path = trace_path.with_suffix("").with_suffix(".chromosome_rand_stream_ledger.json")
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")
    return ledger_path, payload


def test_valid_ledger_loads_successfully(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    _build_valid_ledger(repo_root, trace_path)

    result = ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)
    assert result == [[0.1, 0.2]]


def test_absent_ledger_returns_none_cleanly(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    _write_fake_trace(trace_path, dnadamage_source_resolved_sha256=_DEFAULT_DNADAMAGE_SHA)

    result = ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)
    assert result is None


def test_tampered_trace_sha256_fails_closed(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    payload["trace_sha256"] = "0" * 64
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="DIFFERENT trace file"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_tampered_chromosome_source_sha256_fails_closed(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    payload["chromosome_source_sha256"] = "0" * 64
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="DIFFERENT.*Chromosome.m"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_tampered_randstream_source_sha256_fails_closed(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    payload["randstream_util_source_sha256"] = "0" * 64
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="DIFFERENT.*RandStream.m"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_missing_trace_sha256_field_fails_closed(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    del payload["trace_sha256"]
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_missing_chromosome_source_sha256_field_fails_closed(tmp_path: Path) -> None:
    """A missing hash field must raise (fail-CLOSED), never silently
    `continue` past the check (fail-OPEN)."""
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    del payload["chromosome_source_sha256"]
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ledger_mod.ChromosomeRandStreamLedgerError, match="missing its required chromosome_source_sha256"
    ):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_unresolvable_source_path_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A source path that cannot be resolved under any candidate root
    must raise, never silently skip verification. Main's
    `resolve_wcm_source_path` returns `None` on failure (rather than
    raising itself); the LOADER is responsible for turning that `None`
    into a hard failure."""
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    _build_valid_ledger(repo_root, trace_path)

    monkeypatch.setattr(ledger_mod, "resolve_wcm_source_path", lambda *parts, repo_root: None)

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="could not be resolved on disk"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


# ---------------------------------------------------------------------------
# DNADamage source-hash cross-check (mandatory for EVERY lane, including
# TranscriptionalRegulation -- see module docstring and dec-006).
# ---------------------------------------------------------------------------


def test_missing_dnadamage_source_sha256_field_fails_closed(tmp_path: Path) -> None:
    """This field is mandatory for every lane (DNADamage AND
    TranscriptionalRegulation) -- never weakened per-process. A ledger
    missing it (e.g. one produced by a lane-specific writer that dropped
    this field) must be rejected, not silently trusted."""
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    del payload["dnadamage_source_sha256"]
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="dnadamage_source_sha256"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_trace_missing_dnadamage_metadata_fails_closed(tmp_path: Path) -> None:
    """The trace itself must carry the cross-check metadata field (written
    unconditionally by `extract_per_process_traces_v2.m` for 'fixed'/
    'anchor' window_contract traces regardless of target process) -- a
    trace extracted without it can never be validated against the
    ledger's own recorded value, so this must be a hard failure, not a
    silent skip."""
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, _payload = _build_valid_ledger(repo_root, trace_path, trace_dnadamage_sha256=None)

    with pytest.raises(
        ledger_mod.ChromosomeRandStreamLedgerError, match="no dnadamage_source_resolved_sha256 metadata"
    ):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_dnadamage_source_sha256_mismatch_fails_closed(tmp_path: Path) -> None:
    """The ledger's recorded `dnadamage_source_sha256` must agree with the
    TRACE's own recorded value -- a mismatch means the ledger was
    reconstructed against a different DNADamage.m revision than the one
    that produced this trace."""
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(
        repo_root,
        trace_path,
        dnadamage_source_sha256="a" * 64,
        trace_dnadamage_sha256="b" * 64,
    )

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="DIFFERENT DNADamage.m"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


# ---------------------------------------------------------------------------
# per_tick payload shape validation
# ---------------------------------------------------------------------------


def test_malformed_per_tick_missing_draws_fails_closed(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    payload["per_tick"] = [{"tick": 1, "n_draws": 2}]  # missing "draws"
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="malformed/missing draws array"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_malformed_per_tick_n_draws_mismatch_fails_closed(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    payload["per_tick"] = [{"tick": 1, "n_draws": 5, "draws": [0.1, 0.2]}]
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="does not match len"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_empty_per_tick_fails_closed(tmp_path: Path) -> None:
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    payload["per_tick"] = []
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="missing/empty per_tick"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_bare_scalar_draws_normalized_for_single_draw_tick(tmp_path: Path) -> None:
    """MATLAB's `jsonencode` collapses a 1-element numeric row vector to a
    bare JSON scalar (observed on the TranscriptionalRegulation lane,
    whose per-tick draw counts are frequently 0 or 1) -- confirm this is
    normalized correctly, not rejected as malformed."""
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    payload["per_tick"] = [{"tick": 1, "n_draws": 1, "draws": 0.42}]
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    result = ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)
    assert result == [[0.42]]


def test_bare_scalar_draws_rejected_when_n_draws_disagrees(tmp_path: Path) -> None:
    """The scalar-normalization special case must be narrowly scoped to
    `n_draws == 1`; a bare scalar claiming a different `n_draws` is a
    genuinely malformed ledger, not a serialization quirk to paper over."""
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    ledger_path, payload = _build_valid_ledger(repo_root, trace_path)
    payload["per_tick"] = [{"tick": 1, "n_draws": 2, "draws": 0.42}]
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="malformed/missing draws array"):
        ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)


def test_raw_convention_matches_matlab_style_hash_even_with_crlf_bytes(tmp_path: Path) -> None:
    """A source file containing embedded `\\r` bytes (simulating a CRLF
    checkout) must still validate correctly when the ledger records a RAW
    (non-LF-normalized) hash -- proving the loader uses the SAME
    convention as `scripts/matlab/reconstruct_chromosome_draw_ledger.m`'s
    own `sha256_of_file` (which never strips `\\r`)."""
    repo_root = _make_fake_repo(tmp_path)
    trace_path = tmp_path / "Fake_1ticks.mat"
    crlf_content = b"function result = isRegionAccessible()\r\n    result = true;\r\nend\r\n"

    # Sanity check: this fixture must actually distinguish the two
    # conventions, otherwise this test would pass even with a stray
    # LF-normalization bug reintroduced.
    raw_hash = hashlib.sha256(crlf_content).hexdigest()
    lf_stripped_hash = hashlib.sha256(crlf_content.replace(b"\r", b"")).hexdigest()
    assert raw_hash != lf_stripped_hash, "fixture must contain \\r bytes to be discriminating"

    ledger_path, payload = _build_valid_ledger(repo_root, trace_path, chromosome_content=crlf_content)
    assert payload["chromosome_source_sha256"] == raw_hash

    result = ledger_mod.load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)
    assert result == [[0.1, 0.2]]


def test_resolve_wcm_source_path_falls_back_to_real_main_checkout_when_worktree_local_absent(
) -> None:
    """This worktree itself has no worktree-local `data/m1_sources/
    WholeCell/data/Simulation_fitted.mat` sentinel, so
    `resolve_wcm_source_path` must fall through to the real main-checkout
    sibling (`_resolve_main_checkout_wcm_root`'s `opencell-worktrees` ->
    sibling `opencell` substitution) and resolve to the REAL, existing
    `Chromosome.m` there -- exercised end-to-end against this actual
    repo's own layout, not a synthetic fixture (a synthetic `tmp_path` has
    no `opencell-worktrees` path segment for that substitution to key
    off, so it cannot exercise this fallback at all)."""
    assert not (_REPO_ROOT / "data" / "m1_sources" / "WholeCell" / "data" / "Simulation_fitted.mat").exists(), (
        "test precondition violated: this worktree unexpectedly has a local WholeCell "
        "fitted-simulation snapshot, which would make this test exercise the worktree-local "
        "branch instead of the real-main-checkout fallback it is meant to prove"
    )
    resolved = ledger_mod.resolve_wcm_source_path(*_CHROMOSOME_PARTS, repo_root=_REPO_ROOT)
    assert resolved is not None
    assert resolved.exists()
    assert resolved.name == "Chromosome.m"
    assert resolved.read_bytes()  # genuinely readable, not a broken symlink/stub
