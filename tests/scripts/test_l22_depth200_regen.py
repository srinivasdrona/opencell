"""Targeted tests for scripts/l22_extraction/depth200_regen.py.

Covers the closed-allowlist policy and the legacy-filename relabel step
that is the core mechanism of this module:
  - only DEPTH200_PROCESSES may ever be planned/relabeled
    (UnauthorizedDepth200RegenError for anything else)
  - real_path_for_seed/legacy_path_for_seed resolve to the natural
    `_200ticks.mat` vs the loader-recognized `_100ticks.mat` name
    respectively, for both seed 0 (canonical unsuffixed) and seeds >= 1
    (suffixed `_sNNN/` directories)
  - build_seed0_depth200_command targets the canonical unsuffixed
    directory, seed=0, and n_ticks=200 explicitly -- never `_s000`
  - plan_depth200_extraction rejects seed 0 (inherited from
    launcher.plan_extraction's SeedZeroForbiddenError) and produces jobs at
    n_ticks=200
  - relabel_seed_to_legacy_filename only renames when the source file is
    structurally valid AND its own metadata.n_ticks matches the expected
    real depth; a missing, corrupt, or wrong-depth source file is reported
    (never silently renamed) and the stale legacy file is left untouched
  - relabel_all aggregates per (process, seed) results across a batch

Run via `bin\\oc-pytest tests/scripts/test_l22_depth200_regen.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from scripts.l22_extraction import depth200_regen  # noqa: E402
from scripts.l22_extraction.launcher import SeedZeroForbiddenError  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def test_unauthorized_process_is_rejected_for_seed0_command():
    with pytest.raises(depth200_regen.UnauthorizedDepth200RegenError):
        depth200_regen.build_seed0_depth200_command(["Transcription"])


def test_unauthorized_process_is_rejected_for_plan(tmp_path):
    with pytest.raises(depth200_regen.UnauthorizedDepth200RegenError):
        depth200_regen.plan_depth200_extraction(["Transcription"], [1], karr_native_root=tmp_path)


def test_partially_unauthorized_list_is_rejected_for_relabel(tmp_path):
    with pytest.raises(depth200_regen.UnauthorizedDepth200RegenError):
        depth200_regen.relabel_all(["DNARepair", "Translation"], [0], karr_native_root=tmp_path)


def test_all_three_depth200_processes_are_authorized(tmp_path):
    plan = depth200_regen.plan_depth200_extraction(
        list(depth200_regen.DEPTH200_PROCESSES), [1], karr_native_root=tmp_path, validate_existing=False
    )
    assert set(plan.processes) == set(depth200_regen.DEPTH200_PROCESSES)
    assert plan.n_ticks == depth200_regen.REAL_N_TICKS


def test_plan_depth200_extraction_rejects_seed_zero(tmp_path):
    with pytest.raises(SeedZeroForbiddenError):
        depth200_regen.plan_depth200_extraction(["DNARepair"], [0, 1], karr_native_root=tmp_path)


def test_real_and_legacy_paths_differ_only_in_filename_ticks_label(tmp_path):
    real0 = depth200_regen.real_path_for_seed("DNARepair", 0, karr_native_root=tmp_path)
    legacy0 = depth200_regen.legacy_path_for_seed("DNARepair", 0, karr_native_root=tmp_path)
    assert real0.parent == legacy0.parent == tmp_path / "per_process_traces_v2"
    assert real0.name == "DNARepair_200ticks.mat"
    assert legacy0.name == "DNARepair_100ticks.mat"

    real5 = depth200_regen.real_path_for_seed("ProteinDecay", 5, karr_native_root=tmp_path)
    legacy5 = depth200_regen.legacy_path_for_seed("ProteinDecay", 5, karr_native_root=tmp_path)
    assert real5.parent == legacy5.parent == tmp_path / "per_process_traces_v2_s005"
    assert real5.name == "ProteinDecay_200ticks.mat"
    assert legacy5.name == "ProteinDecay_100ticks.mat"


def test_build_seed0_depth200_command_targets_canonical_dir_and_n_ticks_200():
    command = depth200_regen.build_seed0_depth200_command(
        ["DNARepair", "ReplicationInitiation"], log_relpath="artifacts/x.log"
    )
    assert "'per_process_traces_v2'" in command
    assert "uint32(0)" in command
    assert ", 200," in command
    assert "per_process_traces_v2_s000" not in command
    assert "diary('artifacts/x.log')" in command


def test_relabel_missing_real_file_is_reported_not_fabricated(tmp_path):
    result = depth200_regen.relabel_seed_to_legacy_filename("DNARepair", 0, karr_native_root=tmp_path)
    assert result.action == "missing_real_file"
    assert result.reason is not None


def test_relabel_wrong_depth_real_file_is_flagged_not_renamed(tmp_path):
    real_path = depth200_regen.real_path_for_seed("ProteinDecay", 1, karr_native_root=tmp_path)
    # A real file that exists but was (incorrectly) written at n_ticks=50.
    write_synthetic_trace(real_path, process_name="ProteinDecay", seed=1, n_ticks=50)
    legacy_path = depth200_regen.legacy_path_for_seed("ProteinDecay", 1, karr_native_root=tmp_path)
    write_synthetic_trace(legacy_path, process_name="ProteinDecay", seed=1, n_ticks=100)

    result = depth200_regen.relabel_seed_to_legacy_filename("ProteinDecay", 1, karr_native_root=tmp_path)

    assert result.action == "verify_failed"
    assert real_path.exists()  # never deleted/moved on failure
    assert legacy_path.exists()  # old file left untouched on failure


def test_relabel_valid_real_file_renames_over_stale_legacy_file(tmp_path):
    real_path = depth200_regen.real_path_for_seed("ReplicationInitiation", 3, karr_native_root=tmp_path)
    write_synthetic_trace(real_path, process_name="ReplicationInitiation", seed=3, n_ticks=200)
    legacy_path = depth200_regen.legacy_path_for_seed("ReplicationInitiation", 3, karr_native_root=tmp_path)
    write_synthetic_trace(legacy_path, process_name="ReplicationInitiation", seed=3, n_ticks=100)
    old_legacy_bytes = legacy_path.read_bytes()
    real_bytes = real_path.read_bytes()

    result = depth200_regen.relabel_seed_to_legacy_filename(
        "ReplicationInitiation", 3, karr_native_root=tmp_path
    )

    assert result.action == "relabeled"
    assert result.real_metadata_n_ticks == 200
    assert not real_path.exists()  # moved, not copied
    assert legacy_path.exists()
    assert legacy_path.read_bytes() == real_bytes
    assert legacy_path.read_bytes() != old_legacy_bytes


def test_relabel_all_aggregates_across_processes_and_seeds(tmp_path):
    for process in ("DNARepair", "ProteinDecay"):
        for seed in (0, 1):
            real_path = depth200_regen.real_path_for_seed(process, seed, karr_native_root=tmp_path)
            write_synthetic_trace(real_path, process_name=process, seed=seed, n_ticks=200)

    results = depth200_regen.relabel_all(
        ["DNARepair", "ProteinDecay"], [0, 1], karr_native_root=tmp_path
    )

    assert len(results) == 4
    assert all(r.action == "relabeled" for r in results)
    for process in ("DNARepair", "ProteinDecay"):
        for seed in (0, 1):
            assert depth200_regen.legacy_path_for_seed(process, seed, karr_native_root=tmp_path).exists()
