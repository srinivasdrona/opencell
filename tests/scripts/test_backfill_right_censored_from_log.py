"""Tests for `scripts/l2_event/backfill_right_censored_from_log.py`.

MATLAB-free and WCM/MATLAB-install-free: every "current genuine identity"
lookup (`launcher.current_genuine_dnadamage_source`/
`launcher.current_genuine_mnrnd_provider`/`launcher.genuine_mnrnd_path`) is
monkeypatched to deterministic fake values, so these tests never depend on
this dev machine's real WholeCell source tree or MATLAB installation --
only the parsing/verification/write LOGIC is under test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from scripts.l2_event import backfill_right_censored_from_log as backfill  # noqa: E402
from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.division_cohort_selector import (  # noqa: E402
    CohortContractError,
    event_window_dir,
)
from scripts.l2_event.division_window_spec import (  # noqa: E402
    attempt_record_filename,
    selection_horizon_max_search_ticks,
)
from scripts.l2_event.validate_dual_division_canary import (  # noqa: E402
    CYTOKINESIS_N_TICKS,
    FTSZ_N_TICKS,
)

_FAKE_DNADAMAGE_SHA = "fake-dnadamage-patched-sha256"
_FAKE_MNRND_SHA = "fake-mnrnd-provider-sha256"
_FAKE_MNRND_PATH = "/fake/MATLAB/toolbox/stats/stats/mnrnd.m"
_FAKE_MNRND_RELEASE = "R2026a"
_FAKE_MNRND_TOOLBOX_VERSION = "26.1"


@pytest.fixture(autouse=True)
def _fake_genuine_identity(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "current_genuine_dnadamage_source",
        lambda **_: {"patched_sha256_lf_normalized": _FAKE_DNADAMAGE_SHA},
    )
    monkeypatch.setattr(
        launcher,
        "current_genuine_mnrnd_provider",
        lambda **_: {
            "sha256_lf_normalized": _FAKE_MNRND_SHA,
            "matlab_release": _FAKE_MNRND_RELEASE,
            "toolbox_version": _FAKE_MNRND_TOOLBOX_VERSION,
        },
    )
    monkeypatch.setattr(launcher, "genuine_mnrnd_path", lambda **_: Path(_FAKE_MNRND_PATH))
    # lf_normalized_sha256_hex is real (pure file-hashing logic); tests
    # write real files whose content is exactly what should hash to
    # _FAKE_DNADAMAGE_SHA -- so instead we monkeypatch this too, keyed off
    # a sentinel file content, to keep the test independent of the actual
    # SHA-256 algorithm's output for arbitrary bytes.
    real_hasher = launcher.lf_normalized_sha256_hex

    def _fake_hasher(path: Path) -> str:
        content = path.read_bytes()
        if content == b"GENUINE-CURRENT-OVERLAY-CONTENT":
            return _FAKE_DNADAMAGE_SHA
        return real_hasher(path)

    monkeypatch.setattr(launcher, "lf_normalized_sha256_hex", _fake_hasher)


def _write_log(
    tmp_path: Path,
    *,
    seed: int = 18,
    max_search_ticks: int = 100000,
    overlay_root: Path | None = None,
    mnrnd_path: str = _FAKE_MNRND_PATH,
    mnrnd_release: str = _FAKE_MNRND_RELEASE,
    mnrnd_toolbox_version: str = _FAKE_MNRND_TOOLBOX_VERSION,
    include_error_line: bool = True,
    include_overlay_line: bool = True,
    include_mnrnd_line: bool = True,
) -> Path:
    log_path = tmp_path / f"seed{seed}_100k_probe.log"
    lines = [f"[dual-extract] seed {seed}: single karr_bootstrap() call for BOTH taps..."]
    if include_overlay_line:
        overlay_str = str(overlay_root) if overlay_root is not None else "/does/not/matter"
        lines.append(f"[karr_bootstrap] using generated DNADamage overlay: {overlay_str}")
    if include_mnrnd_line:
        lines.append(f"[karr_bootstrap] mnrnd provider: {mnrnd_path} ({mnrnd_release}, toolbox {mnrnd_toolbox_version})")
    if include_error_line:
        lines.append(
            f"{{Error using extract_dual_division_window (line 207)\n"
            f"seed {seed}: division-completion signal did not fire within "
            f"max_search_ticks={max_search_ticks} ticks -- refusing to fabricate a window_anchor}}"
        )
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path


def _write_valid_overlay(tmp_path: Path) -> Path:
    """Build the overlay 'src' root directory a real karr_bootstrap.m log
    line would name, containing the DNADamage.m file at the exact
    relative path backfill_right_censored_from_log expects, with content
    that the fake hasher above resolves to _FAKE_DNADAMAGE_SHA."""
    overlay_root = tmp_path / "wcm_source_overlay" / "src"
    dnadamage_path = overlay_root.joinpath(*[str(p) for p in backfill._DNADAMAGE_RELATIVE_PATH_UNDER_SRC.parts])
    dnadamage_path.parent.mkdir(parents=True, exist_ok=True)
    dnadamage_path.write_bytes(b"GENUINE-CURRENT-OVERLAY-CONTENT")
    return overlay_root


# ---------------------------------------------------------------------------
# Successful parse + verify + write
# ---------------------------------------------------------------------------


def test_valid_log_parses_verifies_and_writes_a_right_censored_record(tmp_path):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root)
    karr_native_root = tmp_path / "karr_native"

    record_path = backfill.backfill_right_censored_seed(log_path, karr_native_root=karr_native_root)

    assert record_path.exists()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "RIGHT_CENSORED"
    assert record["seed"] == 18
    assert record["max_search_ticks"] == 100000
    assert record["dnadamage_source_resolved_sha256"] == _FAKE_DNADAMAGE_SHA
    assert record["mnrnd_provider_sha256"] == _FAKE_MNRND_SHA
    assert record["cytokinesis_trace_sha256"] is None
    assert record["ftsz_trace_sha256"] is None
    # No trace files were ever created -- mutual exclusivity holds.
    out_dir = event_window_dir(18, karr_native_root=karr_native_root)
    assert not (out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat").exists()
    assert not (out_dir / f"FtsZPolymerization_{FTSZ_N_TICKS}ticks.mat").exists()


def test_dry_run_style_verify_does_not_write(tmp_path):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root)
    evidence = backfill.parse_right_censored_log(log_path)
    verified = backfill.verify_evidence(evidence)
    record = backfill.build_attempt_record(evidence, verified)
    assert record["status"] == "RIGHT_CENSORED"
    assert record["seed"] == 18


# ---------------------------------------------------------------------------
# Parsing failures -- never fabricate from an incomplete log
# ---------------------------------------------------------------------------


def test_missing_error_line_raises(tmp_path):
    log_path = _write_log(tmp_path, include_error_line=False)
    with pytest.raises(backfill.BackfillEvidenceError, match="division-completion signal"):
        backfill.parse_right_censored_log(log_path)


def test_missing_overlay_line_raises(tmp_path):
    log_path = _write_log(tmp_path, include_overlay_line=False)
    with pytest.raises(backfill.BackfillEvidenceError, match="DNADamage overlay"):
        backfill.parse_right_censored_log(log_path)


def test_missing_mnrnd_line_raises(tmp_path):
    log_path = _write_log(tmp_path, include_mnrnd_line=False)
    with pytest.raises(backfill.BackfillEvidenceError, match="mnrnd provider"):
        backfill.parse_right_censored_log(log_path)


def test_missing_log_file_raises(tmp_path):
    with pytest.raises(backfill.BackfillEvidenceError, match="does not exist"):
        backfill.parse_right_censored_log(tmp_path / "does_not_exist.log")


# ---------------------------------------------------------------------------
# Verification failures -- never fabricate a source/provider binding
# ---------------------------------------------------------------------------


def test_horizon_mismatch_raises(tmp_path):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root, max_search_ticks=50000)
    evidence = backfill.parse_right_censored_log(log_path)
    assert evidence.max_search_ticks == 50000
    assert evidence.max_search_ticks != selection_horizon_max_search_ticks()
    with pytest.raises(backfill.BackfillEvidenceError, match="required selection-contract horizon"):
        backfill.verify_evidence(evidence)


def test_overlay_file_missing_on_disk_raises(tmp_path):
    log_path = _write_log(tmp_path, overlay_root=tmp_path / "never_created")
    evidence = backfill.parse_right_censored_log(log_path)
    with pytest.raises(backfill.BackfillEvidenceError, match="no longer exists on disk"):
        backfill.verify_evidence(evidence)


def test_overlay_content_hash_mismatch_raises(tmp_path):
    overlay_root = tmp_path / "wcm_source_overlay" / "src"
    dnadamage_path = overlay_root.joinpath(*[str(p) for p in backfill._DNADAMAGE_RELATIVE_PATH_UNDER_SRC.parts])
    dnadamage_path.parent.mkdir(parents=True, exist_ok=True)
    dnadamage_path.write_bytes(b"SOME OTHER, NON-CURRENT SOURCE CONTENT")
    log_path = _write_log(tmp_path, overlay_root=overlay_root)
    evidence = backfill.parse_right_censored_log(log_path)
    with pytest.raises(backfill.BackfillEvidenceError, match="does NOT match the current"):
        backfill.verify_evidence(evidence)


def test_mnrnd_provider_path_mismatch_raises(tmp_path):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root, mnrnd_path="/some/other/mnrnd.m")
    evidence = backfill.parse_right_censored_log(log_path)
    with pytest.raises(backfill.BackfillEvidenceError, match="does not match the current genuine provider"):
        backfill.verify_evidence(evidence)


def test_mnrnd_provider_release_mismatch_raises(tmp_path):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root, mnrnd_release="R2020a")
    evidence = backfill.parse_right_censored_log(log_path)
    with pytest.raises(backfill.BackfillEvidenceError, match="does not match the current genuine provider"):
        backfill.verify_evidence(evidence)


# ---------------------------------------------------------------------------
# Mutual exclusivity / overwrite refusal on write
# ---------------------------------------------------------------------------


def test_write_refuses_when_a_trace_file_already_exists(tmp_path):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root)
    karr_native_root = tmp_path / "karr_native"
    out_dir = event_window_dir(18, karr_native_root=karr_native_root)
    out_dir.mkdir(parents=True)
    (out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat").write_bytes(b"stray trace bytes")

    with pytest.raises(CohortContractError, match="mutual exclusivity"):
        backfill.backfill_right_censored_seed(log_path, karr_native_root=karr_native_root)


def test_write_refuses_to_overwrite_existing_record_without_force(tmp_path):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root)
    karr_native_root = tmp_path / "karr_native"
    out_dir = event_window_dir(18, karr_native_root=karr_native_root)
    out_dir.mkdir(parents=True)
    (out_dir / attempt_record_filename()).write_text(json.dumps({"status": "RIGHT_CENSORED"}), encoding="utf-8")

    with pytest.raises(CohortContractError, match="already exists"):
        backfill.backfill_right_censored_seed(log_path, karr_native_root=karr_native_root)


def test_write_with_force_overwrites_existing_record(tmp_path):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root)
    karr_native_root = tmp_path / "karr_native"
    out_dir = event_window_dir(18, karr_native_root=karr_native_root)
    out_dir.mkdir(parents=True)
    (out_dir / attempt_record_filename()).write_text(json.dumps({"status": "RIGHT_CENSORED", "seed": 999}), encoding="utf-8")

    record_path = backfill.backfill_right_censored_seed(log_path, karr_native_root=karr_native_root, force=True)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["seed"] == 18


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def test_main_dry_run_prints_record_and_does_not_write(tmp_path, capsys):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root)
    karr_native_root = tmp_path / "karr_native"
    rc = backfill.main(
        ["--log-path", str(log_path), "--karr-native-root", str(karr_native_root), "--dry-run"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "RIGHT_CENSORED"' in out
    assert "not writing any file" in out
    assert not (karr_native_root / "per_process_traces_v2_event_s018").exists()


def test_main_writes_the_record(tmp_path, capsys):
    overlay_root = _write_valid_overlay(tmp_path)
    log_path = _write_log(tmp_path, overlay_root=overlay_root)
    karr_native_root = tmp_path / "karr_native"
    rc = backfill.main(["--log-path", str(log_path), "--karr-native-root", str(karr_native_root)])
    assert rc == 0
    out_dir = event_window_dir(18, karr_native_root=karr_native_root)
    assert (out_dir / attempt_record_filename()).exists()
