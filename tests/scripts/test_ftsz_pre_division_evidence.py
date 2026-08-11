"""Tests for `scripts/l2_event/ftsz_pre_division_evidence.py` -- the
catalog-conformant, no-hint, pre-division event-window evidence path that
replaces the honest N=1/no-hint FtsZ diagnostic
(`tests/vivarium/test_karr_ftsz_polymerization_honest_canary.py`).

Covers, per the task's Beat-3 predicted outcome and pre-mortem:
* window-contract acceptance/rejection (division-anchored, exact
  n_ticks/span, correct process/seed labeling) -- synthetic HDF5 fixtures,
  no real data dependency;
* the preregistered activity-transition rule, and why it is computed from
  the raw enzyme-delta L1 norm rather than the (conserved-by-construction)
  monomer projection;
* the monomer-projection primary-channel statistic;
* no-hint, no-synthetic-activation end-to-end replay of one seed's window
  through the REAL, unmodified `KarrFtsZPolymerizationProcess` ODE port;
* duplicate-seed detection and the "never promote N < 50 to
  SUFFICIENT_ENSEMBLE" guard (the "N=1 relabeled diagnostic-green"
  pre-mortem risk, generalized to N=3);
* the exact resumable-extraction-command surface against real data roots
  (0 real division-anchored FtsZ seeds exist anywhere at the time of
  writing -- see the audit's own INSUFFICIENT_ENSEMBLE/deficit=50 result).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l2_event.ftsz_pre_division_evidence import (  # noqa: E402
    DEFAULT_DATA_ROOTS,
    PROCESS_NAME,
    REQUIRED_M_TICKS,
    REQUIRED_N_SEEDS,
    FtsZWindowContractError,
    audit_pre_division_evidence,
    compute_seed_evidence,
    discover_candidate_paths,
    enzyme_delta_l1,
    first_activity_transition,
    project_monomer_total,
    resumable_extraction_command,
    validate_seed_window,
)

_MATLAB_DRIVER = _REPO_ROOT / "scripts" / "matlab" / "extract_ftsz_pre_division_window_seeds.m"

# Real Karr fixture WID/weight values (see opencell/vivarium/karr_ftsz_polymerization.py),
# confirmed via scripts/l2_event/_probe_ftsz_wids.py during development:
_ENZYME_WIDTH = 11
_SUBSTRATE_WIDTH = 5
_REAL_INITIAL_ENZYME_COUNTS = np.array([0, 3, 6, 1, 1, 2, 3, 5, 8, 12, 20], dtype=np.float64)
_REAL_N_MONOMERS = np.array([1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9], dtype=np.float64)


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


def _write_cell_series(handle: h5py.File, group: h5py.Group, name: str, rows: np.ndarray) -> None:
    """Write an (n_ticks, width) matrix as a MATLAB cell-array-of-vectors
    dataset (HDF5 object references), the only layout `window_loader`'s
    `_cell_series` supports for non-scalar (width > 1) per-tick observables
    -- mirrors `tests/scripts/test_l2_event_window_loader.py`'s
    `_write_synthetic_trace` non_scalar_observable branch, generalized to
    write every tick's full-width row (that helper only demonstrates a
    single 2-wide placeholder row)."""
    n_ticks = rows.shape[0]
    group_label = group.name.lstrip("/")
    refs = np.empty((1, n_ticks), dtype=h5py.special_dtype(ref=h5py.Reference))
    for tick in range(n_ticks):
        dset = handle.create_dataset(f"__data/{group_label}/{name}/{tick}", data=rows[tick])
        refs[0, tick] = dset.ref
    group.create_dataset(name, data=refs, dtype=h5py.special_dtype(ref=h5py.Reference))


def _write_ftsz_window(
    path: Path,
    *,
    seed: int,
    n_ticks: int = REQUIRED_M_TICKS,
    tick_start: int = 1801,
    window_anchor: int | None = None,
    process_name: str = PROCESS_NAME,
    stride: int = 1,
    tick_offset: float = 0.0,
    enzymes_before: np.ndarray | None = None,
    enzymes_after: np.ndarray | None = None,
    substrates_before: np.ndarray | None = None,
    substrates_after: np.ndarray | None = None,
) -> Path:
    """Write a synthetic FtsZ division-anchored event-window trace.

    Defaults to a well-formed, catalog-conformant window (exact
    ``window_anchor - tick_start + 1 == n_ticks`` span) with constant,
    physically plausible enzyme/substrate levels (real initial-fixture
    enzyme counts, generous substrate stock) so a caller only needs to
    override the handful of keyword arguments relevant to the behavior
    under test.
    """
    if window_anchor is None:
        window_anchor = tick_start + n_ticks - 1

    if enzymes_before is None:
        enzymes_before = np.tile(_REAL_INITIAL_ENZYME_COUNTS, (n_ticks, 1))
    if enzymes_after is None:
        enzymes_after = enzymes_before.copy()
    if substrates_before is None:
        substrates_before = np.full((n_ticks, _SUBSTRATE_WIDTH), 1.0e6, dtype=np.float64)
    if substrates_after is None:
        substrates_after = substrates_before.copy()

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata(process_name))
        metadata.create_dataset("rng_seed", data=np.array([seed]))
        metadata.create_dataset("tick_offset", data=np.array([tick_offset]))
        metadata.create_dataset("stride", data=np.array([stride]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("window_anchor", data=np.array([window_anchor]))

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        _write_cell_series(handle, states_before, "enzymes", enzymes_before)
        _write_cell_series(handle, states_after, "enzymes", enzymes_after)
        _write_cell_series(handle, states_before, "substrates", substrates_before)
        _write_cell_series(handle, states_after, "substrates", substrates_after)
    return path


def _seed_dir(root: Path, seed: int) -> Path:
    return root / f"per_process_traces_v2_event_s{seed:03d}"


def _trace_path(root: Path, seed: int) -> Path:
    return _seed_dir(root, seed) / f"{PROCESS_NAME}_{REQUIRED_M_TICKS}ticks.mat"


# ---------------------------------------------------------------------------
# Window-contract validation (synthetic, no real data dependency)
# ---------------------------------------------------------------------------


def test_validate_seed_window_accepts_well_formed_division_anchored_window(tmp_path):
    trace_path = _write_ftsz_window(_trace_path(tmp_path, 7), seed=7)
    grid = validate_seed_window(7, trace_path)
    assert grid.process_name == PROCESS_NAME
    assert grid.seed == 7
    assert grid.n_ticks == REQUIRED_M_TICKS
    assert grid.window_anchor - grid.tick_start + 1 == REQUIRED_M_TICKS


def test_validate_seed_window_rejects_post_division_leakage(tmp_path):
    """window_anchor one tick beyond tick_start + n_ticks - 1 means a
    post-division tick leaked into the window -- must be refused, not
    silently trimmed."""
    trace_path = _write_ftsz_window(
        _trace_path(tmp_path, 1), seed=1, tick_start=1801, window_anchor=2001
    )
    with pytest.raises(FtsZWindowContractError, match="post-division ticks leaked"):
        validate_seed_window(1, trace_path)


def test_validate_seed_window_rejects_truncated_window(tmp_path):
    trace_path = _write_ftsz_window(
        _trace_path(tmp_path, 2), seed=2, tick_start=1801, window_anchor=1998
    )
    with pytest.raises(FtsZWindowContractError, match="truncated"):
        validate_seed_window(2, trace_path)


def test_validate_seed_window_rejects_fixed_non_anchor_window(tmp_path):
    """A fixed (tick_end-only, no window_anchor) window cannot represent
    "ends at division" -- must be refused as NOT_DIVISION_ANCHORED, not
    silently accepted as if it were anchor-relative."""
    path = _trace_path(tmp_path, 3)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([REQUIRED_M_TICKS]))
        metadata.create_dataset("process_name", data=_encode_char_metadata(PROCESS_NAME))
        metadata.create_dataset("rng_seed", data=np.array([3]))
        metadata.create_dataset("tick_offset", data=np.array([0.0]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("tick_start", data=np.array([1801]))
        metadata.create_dataset("tick_end", data=np.array([2000]))  # fixed, no window_anchor
        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        rows = np.tile(_REAL_INITIAL_ENZYME_COUNTS, (REQUIRED_M_TICKS, 1))
        srows = np.full((REQUIRED_M_TICKS, _SUBSTRATE_WIDTH), 1.0e6)
        _write_cell_series(handle, states_before, "enzymes", rows)
        _write_cell_series(handle, states_after, "enzymes", rows)
        _write_cell_series(handle, states_before, "substrates", srows)
        _write_cell_series(handle, states_after, "substrates", srows)
    with pytest.raises(FtsZWindowContractError, match="division-anchored"):
        validate_seed_window(3, path)


def test_validate_seed_window_rejects_wrong_process_name(tmp_path):
    trace_path = _write_ftsz_window(
        _trace_path(tmp_path, 4), seed=4, process_name="SomeOtherProcess"
    )
    with pytest.raises(FtsZWindowContractError, match="process_name"):
        validate_seed_window(4, trace_path)


def test_validate_seed_window_rejects_mislabeled_seed_directory(tmp_path):
    """metadata/rng_seed disagrees with the seed implied by the directory
    name -- a mislabeled or misplaced extraction output, must be refused
    rather than silently trusted."""
    trace_path = _write_ftsz_window(_trace_path(tmp_path, 5), seed=99)
    with pytest.raises(FtsZWindowContractError, match="mislabeled"):
        validate_seed_window(5, trace_path)


def test_validate_seed_window_rejects_wrong_m_ticks(tmp_path):
    trace_path = _write_ftsz_window(_trace_path(tmp_path, 6), seed=6, n_ticks=100, tick_start=1901)
    with pytest.raises(FtsZWindowContractError, match="M_ticks"):
        validate_seed_window(6, trace_path)


# ---------------------------------------------------------------------------
# Preregistered activity rule + monomer projection (pure-function units)
# ---------------------------------------------------------------------------


def test_first_activity_transition_returns_none_when_entirely_inactive():
    assert first_activity_transition([0.0] * REQUIRED_M_TICKS) is None


def test_first_activity_transition_returns_first_nonzero_index():
    magnitudes = [0.0, 0.0, 0.0, 3.5, 0.0, -2.0]
    assert first_activity_transition(magnitudes) == 3


def test_project_monomer_total_matches_hand_computed_dot_product():
    counts = np.array([1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1], dtype=np.float64)  # weights 1,2,9
    expected = 1 * 1 + 1 * 2 + 1 * 9

    class _StubProcess:
        n_monomers = _REAL_N_MONOMERS

    assert project_monomer_total(_StubProcess(), counts) == pytest.approx(expected)


def test_enzyme_delta_l1_matches_manual_sum():
    delta = np.array([2.0, -3.0, 0.0, 1.5])
    assert enzyme_delta_l1(delta) == pytest.approx(2.0 + 3.0 + 0.0 + 1.5)


def test_monomer_projection_is_not_a_useful_activity_signal_for_mass_preserving_redistribution():
    """Documents *why* first_activity_transition must be fed the raw
    enzyme-delta L1 norm and not the monomer projection: a purely
    mass-preserving redistribution (2 monomers -> 1 dimer, weight 1+1 == 2)
    has a real, nonzero enzyme_delta_l1 but a zero monomer-projection
    delta. Using the projection as the activity signal would silently
    report "no activity" for a real polymerization transition."""

    class _StubProcess:
        n_monomers = _REAL_N_MONOMERS

    delta = np.zeros(_ENZYME_WIDTH)
    delta[0] = -2.0  # lose 2 monomers
    delta[3] = 1.0  # gain 1 dimer (weight 2)
    assert enzyme_delta_l1(delta) == pytest.approx(3.0)
    assert project_monomer_total(_StubProcess(), delta) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# End-to-end, no-hint replay through the real ODE port
# ---------------------------------------------------------------------------


def test_compute_seed_evidence_detects_real_no_hint_oc_activity_without_karr_hint(tmp_path):
    """Feeds a constant, physically plausible starting state (real initial
    enzyme distribution, generous substrate stock) into the REAL,
    unmodified `KarrFtsZPolymerizationProcess.next_update` every tick, with
    Karr's own `states_after` held IDENTICAL to `states_before` (i.e. the
    synthetic Karr side of this fixture shows no activity at all). If OC's
    detected activity were secretly derived from Karr's trace instead of
    its own honest ODE integration, `oc_activity_transition_tick` would
    also come back None. It does not: the real ODE port evolves the
    given state on its own regardless of what Karr's trace says, proving
    the "no synthetic activation, no trace hint" contract end to end."""
    n_ticks = REQUIRED_M_TICKS
    trace_path = _write_ftsz_window(
        _trace_path(tmp_path, 11),
        seed=11,
        n_ticks=n_ticks,
        tick_start=1801,
    )
    grid = validate_seed_window(11, trace_path)
    evidence = compute_seed_evidence(11, grid)

    assert evidence.karr_activity_transition_tick is None  # synthetic Karr side: no change
    assert evidence.oc_activity_transition_tick is not None  # real, independently computed
    assert evidence.monomer_l1_mean >= 0.0
    assert evidence.monomer_l1_max >= 0.0


def test_compute_seed_evidence_reports_no_activity_for_all_zero_enzyme_counts(tmp_path):
    """`KarrFtsZPolymerizationProcess.next_update` explicitly early-returns
    `{}` when `not np.any(current_counts)` -- a real "process is dormant"
    condition (e.g. before FtsZ is first synthesized). No transition must
    ever be fabricated for this seed."""
    n_ticks = REQUIRED_M_TICKS
    zeros = np.zeros((n_ticks, _ENZYME_WIDTH))
    trace_path = _write_ftsz_window(
        _trace_path(tmp_path, 12),
        seed=12,
        n_ticks=n_ticks,
        tick_start=1801,
        enzymes_before=zeros,
        enzymes_after=zeros,
    )
    grid = validate_seed_window(12, trace_path)
    evidence = compute_seed_evidence(12, grid)
    assert evidence.karr_activity_transition_tick is None
    assert evidence.oc_activity_transition_tick is None


# ---------------------------------------------------------------------------
# Duplicate-seed detection + never-promote-partial-N guard
# ---------------------------------------------------------------------------


def test_audit_flags_duplicate_seed_content_and_never_double_counts(tmp_path):
    root = tmp_path / "karr_native"
    _write_ftsz_window(_trace_path(root, 0), seed=0, n_ticks=REQUIRED_M_TICKS, tick_start=1801)
    # Byte-identical copy under a different seed directory -- a duplicated
    # trace must not increase ensemble size.
    import shutil

    dst = _trace_path(root, 1)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_trace_path(root, 0), dst)
    # Metadata rng_seed inside the copy still says 0; validate_seed_window
    # would reject seed 1 as mislabeled anyway, but duplicate detection (by
    # sha256) must trigger first, before any per-seed window validation.

    report = audit_pre_division_evidence(data_roots=(root,))
    assert len(report.duplicate_seeds) == 1
    assert report.duplicate_seeds[0]["seed"] == 1
    assert report.duplicate_seeds[0]["duplicate_of_seed"] == 0
    assert report.found_seeds == [0]
    assert report.deficit == REQUIRED_N_SEEDS - 1
    assert report.status == "INSUFFICIENT_ENSEMBLE"


def test_audit_never_promotes_partial_ensemble_to_sufficient(tmp_path):
    """Three distinct, individually valid seeds must still report
    INSUFFICIENT_ENSEMBLE with an exact deficit -- there is no partial-
    credit branch. This is the generalized guard against the "N=1
    relabeled diagnostic-green" pre-mortem risk."""
    root = tmp_path / "karr_native"
    for seed in (0, 1, 2):
        enzymes = np.tile(_REAL_INITIAL_ENZYME_COUNTS, (REQUIRED_M_TICKS, 1))
        enzymes[:, 0] += seed  # vary content so sha256 differs per seed
        _write_ftsz_window(
            _trace_path(root, seed),
            seed=seed,
            n_ticks=REQUIRED_M_TICKS,
            tick_start=1801,
            enzymes_before=enzymes,
        )

    report = audit_pre_division_evidence(data_roots=(root,))
    assert sorted(report.found_seeds) == [0, 1, 2]
    assert report.duplicate_seeds == []
    assert report.deficit == REQUIRED_N_SEEDS - 3
    assert report.status == "INSUFFICIENT_ENSEMBLE"
    assert report.monomer_primary_statistic is not None
    assert report.monomer_primary_statistic["n_seeds"] == 3
    assert report.activity_summary["seeds_total"] == 3


def test_audit_surfaces_rejected_window_reason_without_counting_it_found(tmp_path):
    root = tmp_path / "karr_native"
    _write_ftsz_window(_trace_path(root, 0), seed=0, n_ticks=100, tick_start=1901)  # wrong n_ticks

    report = audit_pre_division_evidence(data_roots=(root,))
    assert report.found_seeds == []
    assert len(report.rejected_windows) == 1
    assert report.rejected_windows[0]["seed"] == 0
    assert "M_ticks" in report.rejected_windows[0]["reason"]
    assert report.deficit == REQUIRED_N_SEEDS
    assert report.status == "INSUFFICIENT_ENSEMBLE"


def test_discover_candidate_paths_finds_all_seed_directories(tmp_path):
    root = tmp_path / "karr_native"
    for seed in (0, 3, 49):
        _write_ftsz_window(_trace_path(root, seed), seed=seed, n_ticks=20, tick_start=1981)
    found = discover_candidate_paths((root,))
    assert sorted(found.keys()) == [0, 3, 49]


# ---------------------------------------------------------------------------
# Real data roots: expected INSUFFICIENT_ENSEMBLE / deficit=50 (0 real
# division-anchored FtsZ seeds exist anywhere at the time of writing) and a
# well-formed resumable extraction command.
# ---------------------------------------------------------------------------


def test_audit_against_real_data_roots_reports_insufficient_ensemble_with_exact_deficit():
    report = audit_pre_division_evidence(data_roots=DEFAULT_DATA_ROOTS)
    assert report.status == "INSUFFICIENT_ENSEMBLE"
    assert report.deficit == REQUIRED_N_SEEDS - len(report.found_seeds)
    assert report.deficit > 0
    if not report.found_seeds:
        assert report.deficit == REQUIRED_N_SEEDS


def test_direct_script_entrypoint_runs_from_repo_root_without_import_error():
    script_path = _REPO_ROOT / "scripts" / "l2_event" / "ftsz_pre_division_evidence.py"
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode in (0, 2), (
        "direct script execution must reach main() and return its documented "
        f"status code, not crash during imports (rc={result.returncode}, stderr={result.stderr!r})"
    )
    assert '"process": "FtsZPolymerization"' in result.stdout
    assert "status=" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def test_resumable_extraction_command_is_well_formed_and_driver_exists():
    missing = list(range(REQUIRED_N_SEEDS))
    command = resumable_extraction_command(missing)
    assert "extract_ftsz_pre_division_window_seeds(0, 49, [])" in command
    assert f"NO output file at all -- extracted fresh, never overwritten: {missing}" in command
    assert _MATLAB_DRIVER.exists(), (
        f"resumable_extraction_command references {_MATLAB_DRIVER}, which must exist "
        "on disk for the command to actually be runnable."
    )


def test_resumable_extraction_command_empty_for_no_missing_seeds():
    assert resumable_extraction_command([]) == ""


def test_resumable_extraction_command_passes_invalid_seeds_as_force_seeds_not_missing():
    """Opus 5 review finding: a seed with an existing-but-rejected/duplicate
    file must never be silently folded into the plain "missing" command --
    the driver's skip-if-exists check would then leave the bad file on disk
    forever. The invalid seed(s) must appear in the emitted command's third
    (force_seeds) argument, and the command text must explicitly warn that
    the plain path alone would not re-extract them."""
    command = resumable_extraction_command(missing_seeds=[7, 8], invalid_seeds=[3])
    # Range spans both missing and invalid seeds; force_seeds names ONLY
    # the invalid one.
    assert "extract_ftsz_pre_division_window_seeds(3, 8, [3])" in command
    assert "2 seed(s) with NO output file at all" in command
    assert "1 seed(s) already have an on-disk" in command
    assert "[3]" in command
    assert "would leave them stale forever" in command


def test_resumable_extraction_command_invalid_seeds_alone_still_forces_overwrite():
    command = resumable_extraction_command(missing_seeds=[], invalid_seeds=[12])
    assert "extract_ftsz_pre_division_window_seeds(12, 12, [12])" in command
    assert "0 seed(s) with NO output file" in command
    assert "1 seed(s) already have an on-disk" in command


def test_audit_never_folds_invalid_present_seed_into_missing_seeds(tmp_path):
    """End-to-end proof (real audit, not just the command builder in
    isolation): a seed whose file exists but is rejected must show up in
    report.invalid_seeds and report.rejected_windows, and must NEVER appear
    in report.missing_seeds -- and the emitted resumable command must name
    it as a force_seeds entry, not a plain-range extraction target."""
    root = tmp_path / "karr_native"
    _write_ftsz_window(
        _trace_path(root, 5), seed=5, n_ticks=100, tick_start=1901
    )  # wrong n_ticks -> rejected

    report = audit_pre_division_evidence(data_roots=(root,))
    assert report.found_seeds == []
    assert report.rejected_windows[0]["seed"] == 5
    assert 5 in report.invalid_seeds
    assert 5 not in report.missing_seeds
    assert 0 in report.missing_seeds  # every other required seed is truly absent
    assert "[5]" in report.resumable_extraction_command
    assert "force_seeds" in report.resumable_extraction_command or "already have an on-disk" in (
        report.resumable_extraction_command
    )


def test_audit_never_folds_duplicate_present_seed_into_missing_seeds(tmp_path):
    root = tmp_path / "karr_native"
    _write_ftsz_window(_trace_path(root, 0), seed=0, n_ticks=REQUIRED_M_TICKS, tick_start=1801)
    import shutil

    dst = _trace_path(root, 1)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_trace_path(root, 0), dst)  # byte-identical -> duplicate

    report = audit_pre_division_evidence(data_roots=(root,))
    assert report.duplicate_seeds and report.duplicate_seeds[0]["seed"] == 1
    assert 1 in report.invalid_seeds
    assert 1 not in report.missing_seeds
    assert 0 not in report.missing_seeds  # seed 0 itself was accepted (found)
    assert 0 in report.found_seeds
