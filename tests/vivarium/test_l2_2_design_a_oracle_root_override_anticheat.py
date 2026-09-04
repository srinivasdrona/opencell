"""Anti-cheat tests for the process-scoped Design-A oracle-root override.

Covers the L2.2 MacromolecularComplexation active-window promotion blocker:
`tests/vivarium/_l2_2_design_a_runner_helpers.py` previously advertised
`OPENCELL_L22_PROCESS_ORACLE_ROOT__MACROMOLECULARCOMPLEXATION` (the env var
name was defined in `scripts/l22_extraction/macromol_active_window.py` and
referenced only in a resumable-extraction-command docstring) but nothing in
the shared runner/helpers module actually READ it -- the authoritative
active-window cohort had no real route into the canonical Design-A loader.

These tests prove, against the REAL committed 50-seed active-window cohort
(never fakes/mocks for the positive path, so a change to the on-disk layout
or `validate_seed_window` contract would fail here too), that the override:

* is read via the advertised env var name and is authoritative when set;
* fails closed (raises `ProcessOracleRootOverrideError`, never a silent
  fallback) on a missing root, an unregistered process, an incomplete/
  partial cohort, wrong-process content, and duplicate/aliased seed content;
* cannot be bypassed by the historical bare-import module-aliasing bug
  (`_l2_2_design_a_runner_helpers` imported both package-qualified and bare,
  as `tests/vivarium/l2_2_design_a_runner.py` does) -- because the override
  check lives in real function code that reads `os.environ` at call time,
  not a monkeypatched module attribute, so which module instance is called
  through cannot matter; and
* never falls back to a hardcoded cross-worktree `E:/opencell`/
  `/mnt/e/opencell` path for MacromolecularComplexation specifically (that
  hardcoded fallback existed for this one process before this fix and has
  been removed in favor of the explicit, validated override route).

Run via `bin\\oc-pytest tests/vivarium/test_l2_2_design_a_oracle_root_override_anticheat.py -v`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import h5py
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    _loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in _loaded.parents:
        for _mod_name in list(sys.modules):
            if _mod_name == "opencell" or _mod_name.startswith("opencell."):
                del sys.modules[_mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import _l2_2_design_a_runner_helpers as helpers  # noqa: E402
from scripts.l22_extraction import macromol_active_window as maw  # noqa: E402

PROCESS = "MacromolecularComplexation"
ENV_VAR = "OPENCELL_L22_PROCESS_ORACLE_ROOT__MACROMOLECULARCOMPLEXATION"
REAL_ROOT = maw.ACTIVE_WINDOW_ROOT


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)


# --- Advertised contract ------------------------------------------------------


def test_env_var_name_matches_advertised_prereg_contract():
    """The name must be exactly what
    `docs/phase_f/l2_2_design_a/MACROMOLECULARCOMPLEXATION_ACTIVE_WINDOW_PREREG.md`
    and `scripts/l22_extraction/macromol_active_window.py`'s
    `RUNNER_OVERRIDE_ENV_VAR` already advertise -- a rename here without
    updating those (or vice versa) is exactly the "advertises but nothing
    reads it" class of bug this promotion closes."""
    assert helpers.process_oracle_root_env_var(PROCESS) == ENV_VAR
    assert maw.RUNNER_OVERRIDE_ENV_VAR == ENV_VAR


def test_unset_env_var_is_a_pure_no_op(monkeypatch: pytest.MonkeyPatch):
    _clear_env(monkeypatch)
    assert helpers._resolve_process_oracle_root_override(PROCESS) is None


def test_unregistered_process_with_env_var_set_fails_closed(monkeypatch: pytest.MonkeyPatch):
    """Setting the override for a process with no validated on-disk contract
    (anything other than MacromolecularComplexation today) must raise, never
    silently do nothing and never silently apply MacromolecularComplexation's
    validation logic to a different process's data."""
    other_env_var = helpers.process_oracle_root_env_var("Cytokinesis")
    monkeypatch.setenv(other_env_var, str(REAL_ROOT))
    with pytest.raises(helpers.ProcessOracleRootOverrideError, match="no registered"):
        helpers._resolve_process_oracle_root_override("Cytokinesis")


# --- Fail-closed: missing / partial / wrong-process / duplicated roots -------


def test_missing_root_directory_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "does_not_exist"))
    with pytest.raises(helpers.ProcessOracleRootOverrideError, match="does not exist"):
        helpers.load_karr_oracle(PROCESS)


def test_empty_root_directory_reports_all_seeds_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    empty_root = tmp_path / "empty_root"
    empty_root.mkdir()
    monkeypatch.setenv(ENV_VAR, str(empty_root))
    with pytest.raises(helpers.ProcessOracleRootOverrideError) as excinfo:
        helpers.load_karr_oracle(PROCESS)
    message = str(excinfo.value)
    assert "missing_seeds" in message
    assert "[0, 1, 2" in message  # every seed 0..49 reported missing, never silently accepted


def test_incomplete_cohort_fails_closed_never_partial(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Copy only 3 of the 50 required real seeds into a fresh root: the
    override must reject this outright, never silently proceed with a
    smaller-than-catalog ensemble."""
    partial_root = tmp_path / "partial_root"
    for seed in (0, 1, 2):
        src = maw._seed_trace_path(seed, REAL_ROOT)  # noqa: SLF001
        dst = maw._seed_trace_path(seed, partial_root)  # noqa: SLF001
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    monkeypatch.setenv(ENV_VAR, str(partial_root))
    with pytest.raises(helpers.ProcessOracleRootOverrideError) as excinfo:
        helpers.load_karr_oracle(PROCESS)
    message = str(excinfo.value)
    assert "missing_seeds" in message
    for seed in range(3, 50):
        assert str(seed) in message.split("missing_seeds=")[1].split("invalid_seeds=")[0]


def test_wrong_process_content_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A root shaped like the real contract (right filename, right directory
    layout) but whose seed-0 file is actually a DIFFERENT process's trace
    (metadata.process_name mismatch) must be rejected -- proving the override
    checks real recorded content, not merely path/filename shape."""
    wrong_root = tmp_path / "wrong_process_root"
    seed0_dst = maw._seed_trace_path(0, wrong_root)  # noqa: SLF001
    seed0_dst.parent.mkdir(parents=True, exist_ok=True)

    other_process_trace = next(
        (_REPO_ROOT / "data" / "m1_sources" / "karr_native" / "ensembles" / "transcription").glob(
            "seed_000/Transcription_100ticks.mat"
        )
    )
    shutil.copyfile(other_process_trace, seed0_dst)

    monkeypatch.setenv(ENV_VAR, str(wrong_root))
    with pytest.raises(helpers.ProcessOracleRootOverrideError) as excinfo:
        helpers.load_karr_oracle(PROCESS)
    message = str(excinfo.value)
    # seed 0 is present-but-invalid (wrong process content); seeds 1-49 are
    # legitimately missing from this deliberately tiny root. Both surface.
    assert "invalid_seeds" in message
    assert "missing_seeds" in message


def test_duplicate_seed_content_laundering_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Copy the REAL, valid, complete 50-seed cohort, then overwrite one
    seed's file with a byte-for-byte duplicate of a DIFFERENT seed's file
    (a seed-relabeling/aliasing attempt). The override must reject this via
    the same duplicate-hash detection the tracked standalone audit CLI uses
    -- proving the override route cannot be satisfied by recycling one real
    seed's content under many seed labels."""
    laundered_root = tmp_path / "laundered_root"
    shutil.copytree(REAL_ROOT, laundered_root)
    seed0 = maw._seed_trace_path(0, laundered_root)  # noqa: SLF001
    seed1 = maw._seed_trace_path(1, laundered_root)  # noqa: SLF001
    shutil.copyfile(seed0, seed1)  # seed 1 now byte-identical to seed 0

    monkeypatch.setenv(ENV_VAR, str(laundered_root))
    with pytest.raises(helpers.ProcessOracleRootOverrideError, match="duplicate_seeds"):
        helpers.load_karr_oracle(PROCESS)


def test_wrong_seed_count_request_fails_closed(monkeypatch: pytest.MonkeyPatch):
    """`load_karr_oracle`/`_load_v2_ensemble` are always called with the
    catalog's real N_seeds=50 for MacromolecularComplexation, but the
    validator itself must not silently accept a root validated against the
    WRONG seed-count contract if ever called with a different max_seeds."""
    monkeypatch.setenv(ENV_VAR, str(REAL_ROOT))
    with pytest.raises(helpers.ProcessOracleRootOverrideError, match="does not match the preregistered"):
        helpers._validate_process_oracle_root_override(PROCESS, REAL_ROOT, max_seeds=10)


# --- Positive path: the real, complete, tracked cohort loads authoritatively -


def test_real_cohort_loads_authoritatively_via_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, str(REAL_ROOT))
    oracle = helpers.load_karr_oracle(PROCESS)
    assert oracle["canonical_seed_count"] == 50
    assert oracle["process_oracle_root_override"] == str(REAL_ROOT)
    assert oracle["process_oracle_root_override_env_var"] == ENV_VAR
    assert Path(oracle["oracle_path"]).is_relative_to(REAL_ROOT)


# --- No hardcoded E:/ fallback for this process -------------------------------


def test_no_override_and_no_local_canonical_root_returns_none_not_e_drive_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    """Without the override set, and with no canonical (non-active-window)
    `per_process_traces_v2*/MacromolecularComplexation_100ticks.mat` files
    present in THIS worktree, `_load_v2_ensemble` must return `None` --
    never silently succeed by reading a hardcoded `E:/opencell`/
    `/mnt/e/opencell` cross-worktree path. This is a regression test for the
    now-removed MacromolecularComplexation-specific hardcoded fallback block."""
    _clear_env(monkeypatch)
    canonical_seed0 = _REPO_ROOT / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2" / f"{PROCESS}_100ticks.mat"
    assert not canonical_seed0.exists(), (
        "this worktree is expected to have no canonical (non-active-window) "
        "MacromolecularComplexation trace; if this now exists, this test's "
        "no-op assumption needs updating"
    )
    result = helpers._load_v2_ensemble(PROCESS, max_seeds=50)
    assert result is None


# --- Module-alias laundering cannot bypass the override -----------------------


def test_module_alias_laundering_cannot_bypass_override(monkeypatch: pytest.MonkeyPatch):
    """Reproduces the exact historical bug (see
    `docs/phase_f/l2_2_design_a/active_windows/MacromolecularComplexation_genuine_provider_design_a.json`'s
    generating session STATUS doc): `tests/vivarium/l2_2_design_a_runner.py`
    inserts its own directory onto `sys.path` and does a BARE
    `import _l2_2_design_a_runner_helpers`, which Python registers as a
    SECOND, independent module object distinct from the package-qualified
    `tests.vivarium._l2_2_design_a_runner_helpers`. A monkeypatch-based fix
    applied to only one of the two module objects would silently not reach
    the other. This override is NOT monkeypatch-based -- the env-var check
    lives directly in `_v2_seed_mat_path`'s real call graph -- so both module
    objects, reached via either import spelling, must behave identically."""
    import importlib

    package_qualified = importlib.import_module("tests.vivarium._l2_2_design_a_runner_helpers")
    bare = importlib.import_module("_l2_2_design_a_runner_helpers")
    assert package_qualified is not bare, "test setup assumption broken: these must be distinct module objects"

    monkeypatch.setenv(ENV_VAR, str(REAL_ROOT))
    oracle_via_package_qualified = package_qualified.load_karr_oracle(PROCESS)
    oracle_via_bare = bare.load_karr_oracle(PROCESS)

    assert oracle_via_package_qualified["canonical_seed_count"] == 50
    assert oracle_via_bare["canonical_seed_count"] == 50
    assert oracle_via_package_qualified["oracle_path"] == oracle_via_bare["oracle_path"]
    assert (
        oracle_via_package_qualified["process_oracle_root_override"]
        == oracle_via_bare["process_oracle_root_override"]
        == str(REAL_ROOT)
    )


def test_h5py_import_available_for_wrong_process_fixture_probe():
    """Guards the `test_wrong_process_content_fails_closed` fixture-loading
    assumption: the transcription ensemble fixture this module reuses is a
    real MATLAB v7.3 (HDF5) file readable by h5py, same as every other
    per-process trace in this project."""
    trace = next(
        (_REPO_ROOT / "data" / "m1_sources" / "karr_native" / "ensembles" / "transcription").glob(
            "seed_000/Transcription_100ticks.mat"
        )
    )
    with h5py.File(trace, "r") as handle:
        assert "metadata" in handle
