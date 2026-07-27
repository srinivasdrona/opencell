"""Targeted tests for scripts/l22_extraction/launcher.py planning logic.

Covers the hard policy items from the L2.2 full-extraction task:
  - seed 0 is never touched (SeedZeroForbiddenError)
  - validate-before-skip (not existence-only)
  - disjoint per-worker output directories
  - resumability (missing vs invalid vs already-valid classification)
  - deterministic, JSON-serializable plan/manifest shape

Run via `bin\\oc-pytest tests/scripts/test_l22_launcher_planning.py -v`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from scripts.l22_extraction import launcher  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def test_seed_zero_is_rejected_by_seed_output_dir(tmp_path):
    with pytest.raises(launcher.SeedZeroForbiddenError):
        launcher.seed_output_dir(0, karr_native_root=tmp_path)


def test_seed_zero_is_rejected_by_plan_extraction(tmp_path):
    with pytest.raises(launcher.SeedZeroForbiddenError):
        launcher.plan_extraction(["RNADecay"], [0, 1], karr_native_root=tmp_path)


def test_canonical_seed0_path_is_unsuffixed(tmp_path):
    path = launcher.canonical_seed0_path("RNADecay", karr_native_root=tmp_path)
    assert path == tmp_path / "per_process_traces_v2" / "RNADecay_100ticks.mat"
    assert "per_process_traces_v2_s000" not in str(path)


def test_missing_files_are_planned_as_generate_missing(tmp_path):
    plan = launcher.plan_extraction(["RNADecay", "ProteinDecay"], [1, 2], n_workers=2, karr_native_root=tmp_path)
    actions = {(d.process, d.seed): d.action for d in plan.decisions}
    assert actions == {
        ("RNADecay", 1): "generate_missing",
        ("ProteinDecay", 1): "generate_missing",
        ("RNADecay", 2): "generate_missing",
        ("ProteinDecay", 2): "generate_missing",
    }


def test_valid_existing_file_is_skipped_not_regenerated(tmp_path):
    write_synthetic_trace(
        launcher.seed_mat_path("RNADecay", 1, karr_native_root=tmp_path),
        process_name="RNADecay",
        seed=1,
        n_ticks=launcher.DEFAULT_N_TICKS,
    )
    plan = launcher.plan_extraction(["RNADecay"], [1], n_workers=1, karr_native_root=tmp_path)
    assert plan.decisions[0].action == "skip_valid"
    assert sum(len(w.jobs) for w in plan.workers) == 0


def test_invalid_existing_file_is_flagged_for_regeneration(tmp_path):
    # Wrong process_name inside the file -> structurally present but invalid.
    write_synthetic_trace(
        launcher.seed_mat_path("RNADecay", 1, karr_native_root=tmp_path),
        process_name="SomeOtherProcess",
        seed=1,
    )
    plan = launcher.plan_extraction(["RNADecay"], [1], n_workers=1, karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert plan.decisions[0].reason
    assert sum(len(w.jobs) for w in plan.workers) == 1


def test_apply_invalidations_deletes_only_flagged_files(tmp_path):
    bad_path = launcher.seed_mat_path("RNADecay", 1, karr_native_root=tmp_path)
    write_synthetic_trace(bad_path, process_name="WrongName", seed=1, n_ticks=launcher.DEFAULT_N_TICKS)
    good_path = launcher.seed_mat_path("ProteinDecay", 1, karr_native_root=tmp_path)
    write_synthetic_trace(good_path, process_name="ProteinDecay", seed=1, n_ticks=launcher.DEFAULT_N_TICKS)

    plan = launcher.plan_extraction(["RNADecay", "ProteinDecay"], [1], n_workers=1, karr_native_root=tmp_path)
    deleted = launcher.apply_invalidations(plan)

    assert deleted == [str(bad_path)]
    assert not bad_path.exists()
    assert good_path.exists()


def test_no_validate_mode_skips_without_checking_content(tmp_path):
    bad_path = launcher.seed_mat_path("RNADecay", 1, karr_native_root=tmp_path)
    write_synthetic_trace(bad_path, process_name="WrongName", seed=1)
    plan = launcher.plan_extraction(
        ["RNADecay"], [1], n_workers=1, karr_native_root=tmp_path, validate_existing=False
    )
    assert plan.decisions[0].action == "skip_valid"


def test_workers_receive_disjoint_seeds(tmp_path):
    plan = launcher.plan_extraction(["RNADecay"], list(range(1, 8)), n_workers=3, karr_native_root=tmp_path)
    seen: set[int] = set()
    for worker in plan.workers:
        worker_seeds = {job.seed for job in worker.jobs}
        assert not (worker_seeds & seen), "a seed was assigned to more than one worker"
        seen |= worker_seeds
    assert seen == set(range(1, 8))


def test_worker_output_dirs_are_disjoint_across_workers(tmp_path):
    plan = launcher.plan_extraction(["RNADecay"], list(range(1, 5)), n_workers=2, karr_native_root=tmp_path)
    dirs_by_worker = [{job.output_dir for job in w.jobs} for w in plan.workers]
    assert not (dirs_by_worker[0] & dirs_by_worker[1])


def test_build_matlab_command_never_writes_to_seed000(tmp_path):
    command = launcher.build_matlab_command(("RNADecay",), 1, log_relpath="x.log")
    assert "per_process_traces_v2_s001" in command
    assert "per_process_traces_v2_s000" not in command


def test_build_matlab_command_is_diary_wrapped_when_log_given():
    command = launcher.build_matlab_command(("RNADecay",), 3, log_relpath="artifacts/seed003.log")
    assert "diary('artifacts/seed003.log')" in command
    assert "diary off" in command
    assert "try;" in command and "catch err;" in command


def test_plan_to_dict_is_json_serializable(tmp_path):
    plan = launcher.plan_extraction(["RNADecay", "ProteinDecay"], [1, 2, 3], n_workers=2, karr_native_root=tmp_path)
    payload = json.dumps(plan.to_dict())
    reloaded = json.loads(payload)
    assert reloaded["n_workers"] == 2
    assert reloaded["seeds"] == [1, 2, 3]
    assert sum(len(w["jobs"]) for w in reloaded["workers"]) == sum(len(w.jobs) for w in plan.workers)


def test_plan_extraction_rejects_zero_workers(tmp_path):
    with pytest.raises(ValueError):
        launcher.plan_extraction(["RNADecay"], [1], n_workers=0, karr_native_root=tmp_path)
