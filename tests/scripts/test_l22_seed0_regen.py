"""Targeted tests for scripts/l22_extraction/seed0_regen.py.

Covers the narrow, explicit exception this module makes to the launcher's
general SeedZeroForbiddenError policy:
  - only STALE5_PROCESSES may ever be planned (UnauthorizedSeed0RegenError
    for anything else)
  - missing canonical seed0 -> generate_missing
  - existing canonical seed0 missing the required extra channel(s) -> flagged
    regenerate_stale (the pre-decision stale schema)
  - existing canonical seed0 already carrying the required extra channel(s)
    -> skip_valid (resumable: a partial regen run can be re-invoked safely)
  - apply_seed0_invalidations only deletes regenerate_stale-flagged files
  - the MATLAB command targets the canonical unsuffixed directory and
    seed=0 explicitly (never a _s000 suffix)

Run via `bin\\oc-pytest tests/scripts/test_l22_seed0_regen.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from scripts.l22_extraction import seed0_regen  # noqa: E402
from scripts.l22_extraction.launcher import canonical_seed0_path  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def test_unauthorized_process_is_rejected(tmp_path):
    with pytest.raises(seed0_regen.UnauthorizedSeed0RegenError):
        seed0_regen.plan_seed0_regen(["Transcription"], karr_native_root=tmp_path)


def test_partially_unauthorized_list_is_rejected(tmp_path):
    with pytest.raises(seed0_regen.UnauthorizedSeed0RegenError):
        seed0_regen.plan_seed0_regen(["RNADecay", "Translation"], karr_native_root=tmp_path)


def test_all_five_stale_processes_are_authorized(tmp_path):
    plan = seed0_regen.plan_seed0_regen(list(seed0_regen.STALE5_PROCESSES), karr_native_root=tmp_path)
    assert {d.process for d in plan.decisions} == set(seed0_regen.STALE5_PROCESSES)


def test_missing_canonical_file_is_generate_missing(tmp_path):
    plan = seed0_regen.plan_seed0_regen(["RNADecay"], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "generate_missing"
    assert plan.matlab_command is not None


def test_stale_schema_file_is_flagged_regenerate_stale(tmp_path):
    # Old-schema RNADecay canonical seed0: only substrates/enzymes, no RNAs.
    write_synthetic_trace(
        canonical_seed0_path("RNADecay", karr_native_root=tmp_path),
        process_name="RNADecay",
        seed=0,
        n_ticks=100,
        channels=("substrates", "enzymes", "boundEnzymes"),
    )
    plan = seed0_regen.plan_seed0_regen(["RNADecay"], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_stale"
    assert "RNAs" in plan.decisions[0].reason
    assert plan.matlab_command is not None
    assert "uint32(0)" in plan.matlab_command
    assert "per_process_traces_v2'" in plan.matlab_command
    assert "per_process_traces_v2_s000" not in plan.matlab_command


def test_already_regenerated_file_is_skip_valid(tmp_path):
    # New-schema RNADecay canonical seed0: already carries RNAs.
    write_synthetic_trace(
        canonical_seed0_path("RNADecay", karr_native_root=tmp_path),
        process_name="RNADecay",
        seed=0,
        n_ticks=100,
        channels=("substrates", "enzymes", "boundEnzymes", "RNAs"),
    )
    plan = seed0_regen.plan_seed0_regen(["RNADecay"], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "skip_valid"
    assert plan.matlab_command is None


def test_mixed_batch_only_regenerates_what_is_needed(tmp_path):
    # RNADecay already regenerated; ProteinDecay still stale; RNAProcessing missing.
    write_synthetic_trace(
        canonical_seed0_path("RNADecay", karr_native_root=tmp_path),
        process_name="RNADecay",
        seed=0,
        n_ticks=100,
        channels=("substrates", "enzymes", "RNAs"),
    )
    write_synthetic_trace(
        canonical_seed0_path("ProteinDecay", karr_native_root=tmp_path),
        process_name="ProteinDecay",
        seed=0,
        n_ticks=100,
        channels=("substrates", "enzymes", "monomers"),
    )
    plan = seed0_regen.plan_seed0_regen(
        ["RNADecay", "ProteinDecay", "RNAProcessing"], karr_native_root=tmp_path
    )
    actions = {d.process: d.action for d in plan.decisions}
    assert actions == {
        "RNADecay": "skip_valid",
        "ProteinDecay": "regenerate_stale",
        "RNAProcessing": "generate_missing",
    }
    assert plan.matlab_command is not None
    assert "'ProteinDecay'" in plan.matlab_command
    assert "'RNAProcessing'" in plan.matlab_command
    assert "'RNADecay'" not in plan.matlab_command


def test_apply_seed0_invalidations_deletes_only_stale_files(tmp_path):
    stale_path = canonical_seed0_path("RNADecay", karr_native_root=tmp_path)
    write_synthetic_trace(stale_path, process_name="RNADecay", seed=0, n_ticks=100, channels=("substrates",))
    good_path = canonical_seed0_path("ProteinDecay", karr_native_root=tmp_path)
    write_synthetic_trace(
        good_path, process_name="ProteinDecay", seed=0, n_ticks=100, channels=("substrates", "RNAs")
    )

    plan = seed0_regen.plan_seed0_regen(["RNADecay", "ProteinDecay"], karr_native_root=tmp_path)
    deleted = seed0_regen.apply_seed0_invalidations(plan)

    assert deleted == [str(stale_path)]
    assert not stale_path.exists()
    assert good_path.exists()


def test_build_seed0_matlab_command_targets_canonical_dir_and_seed_zero():
    command = seed0_regen.build_seed0_matlab_command(("RNADecay", "ProteinDecay"), log_relpath="artifacts/x.log")
    assert "'per_process_traces_v2'" in command
    assert "uint32(0)" in command
    assert "per_process_traces_v2_s000" not in command
    assert "diary('artifacts/x.log')" in command
    assert "diary off" in command


def test_build_seed0_matlab_command_without_log_has_no_diary():
    command = seed0_regen.build_seed0_matlab_command(("RNADecay",), log_relpath=None)
    assert "diary" not in command


def test_required_extra_channels_cover_all_five_processes():
    assert set(seed0_regen.REQUIRED_EXTRA_CHANNELS.keys()) == set(seed0_regen.STALE5_PROCESSES)
    for process in seed0_regen.STALE5_PROCESSES:
        assert len(seed0_regen.REQUIRED_EXTRA_CHANNELS[process]) >= 1
