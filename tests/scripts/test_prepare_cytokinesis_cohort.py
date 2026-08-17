"""Tests for `scripts/l2_event/prepare_cytokinesis_cohort.py`.

These stay MATLAB-free and use synthetic HDF5 event-window fixtures only.
The goal is to prove three things:

1. inventory never confuses old standard 100-tick traces with authoritative
   Cytokinesis event-window cohort members;
2. the global cohort prep excludes already-valid seeds from the 1-49
   extraction plan instead of regenerating them blindly;
3. local seed-0 materialization never overwrites a non-identical file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.prepare_cytokinesis_cohort import (  # noqa: E402
    AUTHORITATIVE_N_TICKS,
    PROCESS,
    REQUIRED_N_SEEDS,
    REQUIRED_OBSERVABLES,
    autodiscover_karr_native_roots,
    build_inventory,
    materialize_seed0,
    prepare_cohort,
)


@pytest.fixture(autouse=True)
def _fake_local_genuine_provider(monkeypatch, tmp_path):
    matlab_root = tmp_path / "MATLAB"
    for name in launcher.STATISTICS_RNG_FUNCTIONS:
        provider_path = launcher.genuine_statistics_rng_path(name, matlab_root=matlab_root)
        provider_path.parent.mkdir(parents=True, exist_ok=True)
        provider_path.write_text(f"% fake genuine {name} provider\n", encoding="utf-8", newline="\n")
    contents_path = matlab_root / launcher.STATISTICS_TOOLBOX_CONTENTS_RELATIVE_PATH
    contents_path.write_text(
        "% Statistics and Machine Learning Toolbox\n% Version 26.1 (R2026a) 12-Jan-2026\n",
        encoding="utf-8",
        newline="\n",
    )
    version_info_path = matlab_root / launcher.MATLAB_VERSION_INFO_RELATIVE_PATH
    version_info_path.write_text(
        "<?xml version=\"1.0\"?><MathWorks_version_info><release>R2026a</release></MathWorks_version_info>\n",
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.setattr(launcher, "DEFAULT_MATLAB_ROOT", matlab_root)


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


def _write_valid_anchor_trace(
    root: Path,
    *,
    seed: int,
    onset_row: int = 120,
    completion_row: int = 240,
    tick_start: int = 1000,
) -> Path:
    path = root / f"per_process_traces_v2_event_s{seed:03d}" / f"{PROCESS}_{AUTHORITATIVE_N_TICKS}ticks.mat"
    path.parent.mkdir(parents=True, exist_ok=True)
    n_ticks = AUTHORITATIVE_N_TICKS

    before_pinched = np.full(n_ticks, 10.0, dtype=float)
    after_pinched = np.full(n_ticks, 10.0, dtype=float)
    n_steps = completion_row - onset_row + 1
    step = 10.0 / n_steps
    current = 10.0
    for row in range(onset_row, completion_row + 1):
        before_pinched[row] = current
        current = max(0.0, current - step)
        if row == completion_row:
            current = 0.0
        after_pinched[row] = current
    before_pinched[completion_row + 1 :] = 0.0
    after_pinched[completion_row + 1 :] = 0.0

    onset_tick = tick_start + onset_row
    completion_tick = tick_start + completion_row
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata(PROCESS))
        metadata.create_dataset("rng_seed", data=np.array([seed]))
        metadata.create_dataset("tick_offset", data=np.array([0.0]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("window_anchor", data=np.array([completion_tick]))
        metadata.create_dataset("onset_tick", data=np.array([onset_tick]))
        metadata.create_dataset("signal_kind", data=_encode_char_metadata("diameter_decrease"))
        metadata.create_dataset("signal_property", data=_encode_char_metadata("geometry"))
        metadata.create_dataset("signal_field", data=_encode_char_metadata("pinchedDiameter"))
        metadata.create_dataset("max_search_ticks", data=np.array([launcher.DEFAULT_MAX_SEARCH_TICKS]))
        metadata.create_dataset(
            "event_observable_projection_version",
            data=np.array([launcher.EVENT_OBSERVABLE_PROJECTION_VERSION]),
        )
        provider = launcher.current_genuine_mnrnd_provider()
        metadata.create_dataset("mnrnd_provider_kind", data=_encode_char_metadata(provider["kind"]))
        metadata.create_dataset(
            "mnrnd_provider_matlab_release",
            data=_encode_char_metadata(provider["matlab_release"]),
        )
        metadata.create_dataset(
            "mnrnd_provider_toolbox_version",
            data=_encode_char_metadata(provider["toolbox_version"]),
        )
        metadata.create_dataset(
            "mnrnd_provider_path_relative_to_matlabroot",
            data=_encode_char_metadata(provider["provider_path_relative_to_matlabroot"]),
        )
        metadata.create_dataset(
            "mnrnd_provider_sha256",
            data=_encode_char_metadata(provider["sha256_lf_normalized"]),
        )
        metadata.create_dataset(
            "statistics_rng_provider_identity_json",
            data=_encode_char_metadata(
                json.dumps(
                    launcher.current_genuine_statistics_rng_provider(),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
        )

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in REQUIRED_OBSERVABLES:
            if observable == "pinchedDiameter":
                before = before_pinched
                after = after_pinched
            elif observable == "chromosome_segregated":
                before = np.ones(n_ticks, dtype=float)
                after = np.ones(n_ticks, dtype=float)
            else:
                before = np.zeros(n_ticks, dtype=float)
                after = np.zeros(n_ticks, dtype=float)
            states_before.create_dataset(observable, data=before.reshape(1, -1))
            states_after.create_dataset(observable, data=after.reshape(1, -1))
    return path


def test_build_inventory_keeps_standard_traces_out_of_the_authoritative_cohort(tmp_path):
    search_root = tmp_path / "karr_native"
    standard_path = search_root / "per_process_traces_v2" / f"{PROCESS}_100ticks.mat"
    standard_path.parent.mkdir(parents=True, exist_ok=True)
    standard_path.write_bytes(b"not an event window")
    event_path = _write_valid_anchor_trace(search_root, seed=0)

    inventory = build_inventory([search_root])
    by_path = {row["path"]: row for row in inventory}

    assert by_path[str(event_path)]["valid_for_authoritative_cohort"] is True
    assert by_path[str(event_path)]["seed"] == 0
    assert by_path[str(standard_path)]["valid_for_authoritative_cohort"] is False
    assert by_path[str(standard_path)]["cohort_eligible"] is False
    assert by_path[str(standard_path)]["validation_reason"] == "not an event-window Cytokinesis seed trace"


def test_autodiscover_karr_native_roots_includes_sibling_worktrees(tmp_path):
    repo_root = tmp_path / "opencell-worktrees" / "wave-l22-cytokinesis"
    current_root = repo_root / "data" / "m1_sources" / "karr_native"
    sibling_root = tmp_path / "opencell-worktrees" / "l2-event-cytokinesis-20260805" / "data" / "m1_sources" / "karr_native"
    main_root = tmp_path / "opencell" / "data" / "m1_sources" / "karr_native"

    current_root.mkdir(parents=True, exist_ok=True)
    sibling_root.mkdir(parents=True, exist_ok=True)
    main_root.mkdir(parents=True, exist_ok=True)

    discovered = autodiscover_karr_native_roots(repo_root=repo_root)

    assert current_root.resolve() in discovered
    assert sibling_root.resolve() in discovered
    assert main_root.resolve() in discovered


def test_materialize_seed0_refuses_nonidentical_existing_target(tmp_path):
    source_root = tmp_path / "source"
    output_root = tmp_path / "output"
    source_path = _write_valid_anchor_trace(source_root, seed=0)

    target_path = launcher.event_window_mat_path(
        PROCESS,
        0,
        n_ticks=AUTHORITATIVE_N_TICKS,
        karr_native_root=output_root,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(b"different bytes")

    with pytest.raises(RuntimeError, match="Refusing to overwrite non-identical existing seed-0 trace"):
        materialize_seed0(source_path, output_root=output_root)


def test_prepare_cohort_writes_plan_only_for_missing_seeds_and_copies_seed0(tmp_path):
    current_root = tmp_path / "current" / "data" / "m1_sources" / "karr_native"
    sibling_root = tmp_path / "sibling" / "data" / "m1_sources" / "karr_native"
    out_dir = tmp_path / "artifacts"

    seed0_source = _write_valid_anchor_trace(sibling_root, seed=0)
    _write_valid_anchor_trace(sibling_root, seed=7, onset_row=100, completion_row=150, tick_start=2000)

    summary = prepare_cohort(
        search_roots=[current_root, sibling_root],
        output_root=current_root,
        out_dir=out_dir,
        materialize_seed0_locally=True,
    )

    materialized = current_root / "per_process_traces_v2_event_s000" / f"{PROCESS}_{AUTHORITATIVE_N_TICKS}ticks.mat"
    assert materialized.exists()
    assert materialized.read_bytes() == seed0_source.read_bytes()
    assert summary["seed0_materialization"]["status"] == "copied"
    assert summary["valid_event_seeds"] == [0, 7]
    assert 7 not in summary["missing_event_seeds"]
    assert 0 not in summary["missing_event_seeds"]
    assert len(summary["missing_event_seeds"]) == REQUIRED_N_SEEDS - 2

    specs = json.loads((out_dir / "seed_1_49_specs.json").read_text(encoding="utf-8"))
    spec_seeds = {row["seed"] for row in specs}
    assert 0 not in spec_seeds
    assert 7 not in spec_seeds
    assert 1 in spec_seeds
    assert 49 in spec_seeds
    assert len(spec_seeds) == REQUIRED_N_SEEDS - 2

    plan = json.loads((out_dir / "seed_1_49_plan.json").read_text(encoding="utf-8"))
    decision_actions = {row["seed"]: row["action"] for row in plan["decisions"]}
    assert decision_actions[1] == "generate_missing"
    assert decision_actions[49] == "generate_missing"
    assert 7 not in decision_actions
