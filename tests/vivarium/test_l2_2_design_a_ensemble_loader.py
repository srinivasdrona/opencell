from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
import l2_2_design_a_runner as runner  # noqa: E402


def _write_mat_trace(
    path: Path,
    *,
    states_before: dict[str, list[np.ndarray]],
    states_after: dict[str, list[np.ndarray]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        refs = handle.create_group("#refs#")
        before_group = handle.create_group("states_before")
        after_group = handle.create_group("states_after")
        handle.create_group("metadata")

        for section_name, section_group, section_values in (
            ("states_before", before_group, states_before),
            ("states_after", after_group, states_after),
        ):
            for channel, tick_vectors in section_values.items():
                dataset = section_group.create_dataset(
                    channel,
                    (1, len(tick_vectors)),
                    dtype=h5py.ref_dtype,
                )
                for tick, vector in enumerate(tick_vectors):
                    ref_ds = refs.create_dataset(
                        f"{section_name}_{channel}_{tick}",
                        data=np.asarray(vector, dtype=np.float64).reshape(1, -1),
                    )
                    dataset[0, tick] = ref_ds.ref


def _metabolism_tick_vectors(seed: int, n_ticks: int = 2) -> tuple[dict[str, list[np.ndarray]], dict[str, list[np.ndarray]]]:
    before = {
        "substrates": [],
        "enzymes": [],
        "boundEnzymes": [],
    }
    after = {"substrates": []}
    for tick in range(n_ticks):
        before["substrates"].append(np.asarray([100 * seed + tick, 100 * seed + tick + 1], dtype=np.float64))
        before["enzymes"].append(np.asarray([10 * seed + tick], dtype=np.float64))
        before["boundEnzymes"].append(np.asarray([seed + tick], dtype=np.float64))
        after["substrates"].append(np.asarray([200 * seed + tick, 200 * seed + tick + 1], dtype=np.float64))
    return before, after


def _rna_decay_tick_vectors(
    seed: int, n_ticks: int = 2, *, rna_width: int = 2
) -> tuple[dict[str, list[np.ndarray]], dict[str, list[np.ndarray]]]:
    before = {"substrates": [], "enzymes": [], "boundEnzymes": [], "RNAs": []}
    after = {"substrates": [], "RNAs": []}
    for tick in range(n_ticks):
        before["substrates"].append(np.asarray([100 * seed + tick, 100 * seed + tick + 1], dtype=np.float64))
        before["enzymes"].append(np.asarray([10 * seed + tick], dtype=np.float64))
        before["boundEnzymes"].append(np.asarray([seed + tick], dtype=np.float64))
        before["RNAs"].append(np.arange(rna_width, dtype=np.float64) + (10 * seed + tick))
        after["substrates"].append(np.asarray([200 * seed + tick, 200 * seed + tick + 1], dtype=np.float64))
        after["RNAs"].append(np.arange(rna_width, dtype=np.float64) + (20 * seed + tick))
    return before, after


def _macromol_tick_vectors(
    seed: int,
    n_ticks: int = 2,
    *,
    complex_base: float,
) -> tuple[dict[str, list[np.ndarray]], dict[str, list[np.ndarray]]]:
    before = {"substrates": [], "monomers": [], "complexs": []}
    after = {"substrates": [], "monomers": [], "complexs": []}
    for tick in range(n_ticks):
        before["substrates"].append(np.asarray([10 * seed + tick, 10 * seed + tick + 1], dtype=np.float64))
        after["substrates"].append(np.asarray([20 * seed + tick, 20 * seed + tick + 1], dtype=np.float64))
        before["monomers"].append(np.asarray([30 * seed + tick, 30 * seed + tick + 1], dtype=np.float64))
        after["monomers"].append(np.asarray([40 * seed + tick, 40 * seed + tick + 1], dtype=np.float64))

        before_complexs = np.zeros(24, dtype=np.float64)
        after_complexs = np.zeros(24, dtype=np.float64)
        before_complexs[22] = complex_base + 10 * seed + tick
        before_complexs[23] = complex_base + 100 + 10 * seed + tick
        after_complexs[22] = before_complexs[22] + 1.0
        after_complexs[23] = before_complexs[23]
        before["complexs"].append(before_complexs)
        after["complexs"].append(after_complexs)
    return before, after


def _generic_v2_path(root: Path, process: str, seed: int) -> Path:
    subdir = "per_process_traces_v2" if seed == 0 else f"per_process_traces_v2_s{seed:03d}"
    return root / subdir / f"{process}_100ticks.mat"


def test_load_v2_ensemble_returns_none_when_no_seeds_present(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)

    assert runner_helpers._load_v2_ensemble("Metabolism", max_seeds=3) is None


def test_load_v2_ensemble_loads_single_seed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    before, after = _metabolism_tick_vectors(seed=0)
    _write_mat_trace(
        tmp_path
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces_v2_s000"
        / "Metabolism_100ticks.mat",
        states_before=before,
        states_after=after,
    )

    oracle = runner_helpers._load_v2_ensemble("Metabolism", max_seeds=3)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 1
    assert oracle["n_ticks_available"] == 2
    assert np.asarray(oracle["before_substrates"]).shape == (1, 2, 2)
    assert np.asarray(oracle["before_enzymes"]).shape == (1, 2, 1)
    assert np.asarray(oracle["before_bound_enzymes"]).shape == (1, 2, 1)
    assert np.asarray(oracle["after_substrates"]).shape == (1, 2, 2)
    assert np.array_equal(np.asarray(oracle["before_substrates"])[0, 1], np.asarray([1.0, 2.0]))
    assert np.array_equal(np.asarray(oracle["after_substrates"])[0, 1], np.asarray([1.0, 2.0]))


def test_load_v2_ensemble_stacks_multiple_present_seeds_in_order(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    for seed in range(3):
        before, after = _metabolism_tick_vectors(seed=seed)
        _write_mat_trace(
            tmp_path
            / "data"
            / "m1_sources"
            / "karr_native"
            / f"per_process_traces_v2_s{seed:03d}"
            / "Metabolism_100ticks.mat",
            states_before=before,
            states_after=after,
        )

    oracle = runner_helpers._load_v2_ensemble("Metabolism", max_seeds=3)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 3
    assert np.asarray(oracle["before_substrates"]).shape == (3, 2, 2)
    assert np.asarray(oracle["after_substrates"]).shape == (3, 2, 2)
    assert np.array_equal(np.asarray(oracle["before_substrates"])[0, 0], np.asarray([0.0, 1.0]))
    assert np.array_equal(np.asarray(oracle["before_substrates"])[1, 0], np.asarray([100.0, 101.0]))
    assert np.array_equal(np.asarray(oracle["before_substrates"])[2, 0], np.asarray([200.0, 201.0]))
    assert np.array_equal(np.asarray(oracle["after_substrates"])[2, 1], np.asarray([401.0, 402.0]))


def test_load_ensembles_layout_reads_real_translation_ensemble() -> None:
    oracle = runner_helpers._load_ensembles_layout("Translation", max_seeds=50)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 50
    assert oracle["oracle_path"] == runner_helpers._ensembles_manifest_path("Translation")
    assert np.asarray(oracle["before_substrates"]).shape[0] == 50
    assert np.asarray(oracle["before_substrates"]).shape[1] == 100
    assert np.asarray(oracle["after_monomers"]).shape[0] == 50
    assert np.asarray(oracle["after_bound_enzymes"]).shape[0] == 50
    assert np.asarray(oracle["before_mrnas"]).shape[0] == 50
    assert "mRNAs" in oracle["ensemble_missing_before_channels"]


def test_load_karr_oracle_uses_v2_loader_when_no_specialized_ensemble_exists(monkeypatch) -> None:
    sentinel = {"process": "Metabolism", "canonical_seed_count": 7}
    monkeypatch.setattr(runner_helpers, "_load_v2_ensemble", lambda process_name, max_seeds=50: sentinel)
    monkeypatch.setattr(runner_helpers, "_load_ensembles_layout", lambda process_name, max_seeds=50: None)

    oracle = runner_helpers.load_karr_oracle("Metabolism")

    assert oracle is sentinel


def test_load_karr_oracle_returns_v2_macromol_without_touching_legacy_loader(monkeypatch) -> None:
    sentinel = {"process": "MacromolecularComplexation", "canonical_seed_count": 50}
    monkeypatch.setattr(runner_helpers, "_load_v2_ensemble", lambda process_name, max_seeds=50: sentinel)
    monkeypatch.setattr(runner_helpers, "_load_ensembles_layout", lambda process_name, max_seeds=50: None)

    oracle = runner_helpers.load_karr_oracle("MacromolecularComplexation")

    assert oracle is sentinel


def test_load_v2_ensemble_uses_process_scoped_oracle_root_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner_helpers, "_macromol_channel_metadata", lambda: {"monomer_indices": np.array([0, 1])})
    process = "MacromolecularComplexation"
    default_root = tmp_path / "data" / "m1_sources" / "karr_native"
    override_root = tmp_path / "macromol_active_root"

    for seed in range(2):
        default_before, default_after = _macromol_tick_vectors(seed, complex_base=100.0)
        override_before, override_after = _macromol_tick_vectors(seed, complex_base=900.0)
        _write_mat_trace(
            _generic_v2_path(default_root, process, seed),
            states_before=default_before,
            states_after=default_after,
        )
        _write_mat_trace(
            _generic_v2_path(override_root, process, seed),
            states_before=override_before,
            states_after=override_after,
        )

    monkeypatch.setenv(runner_helpers._process_oracle_root_env_var(process), str(override_root))
    oracle = runner_helpers._load_v2_ensemble(process, max_seeds=2)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 2
    assert str(oracle["oracle_path"]).startswith(str(override_root))
    assert np.asarray(oracle["before_complexs"])[0, 0, 22] == 900.0


def test_process_scoped_oracle_root_override_is_authoritative_not_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner_helpers, "_macromol_channel_metadata", lambda: {"monomer_indices": np.array([0, 1])})
    process = "MacromolecularComplexation"
    default_root = tmp_path / "data" / "m1_sources" / "karr_native"
    override_root = tmp_path / "macromol_active_root"

    for seed in range(2):
        default_before, default_after = _macromol_tick_vectors(seed, complex_base=100.0)
        _write_mat_trace(
            _generic_v2_path(default_root, process, seed),
            states_before=default_before,
            states_after=default_after,
        )
    override_before, override_after = _macromol_tick_vectors(0, complex_base=700.0)
    _write_mat_trace(
        _generic_v2_path(override_root, process, 0),
        states_before=override_before,
        states_after=override_after,
    )

    monkeypatch.setenv(runner_helpers._process_oracle_root_env_var(process), str(override_root))
    oracle = runner_helpers._load_v2_ensemble(process, max_seeds=2)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 1
    assert str(oracle["oracle_path"]).startswith(str(override_root))
    assert np.asarray(oracle["before_complexs"])[0, 0, 22] == 700.0


def test_load_karr_oracle_prefers_richer_specialized_ensemble_over_partial_v2(monkeypatch) -> None:
    partial_v2 = {"process": "Translation", "canonical_seed_count": 1}
    specialized = {"process": "Translation", "canonical_seed_count": 50}
    monkeypatch.setattr(runner_helpers, "_load_v2_ensemble", lambda process_name, max_seeds=50: partial_v2)
    monkeypatch.setattr(runner_helpers, "_load_ensembles_layout", lambda process_name, max_seeds=50: specialized)

    oracle = runner_helpers.load_karr_oracle("Translation")

    assert oracle is specialized


def test_load_karr_oracle_falls_back_to_legacy_with_warning(monkeypatch) -> None:
    monkeypatch.setattr(runner_helpers, "_load_v2_ensemble", lambda process_name, max_seeds=50: None)
    monkeypatch.setattr(runner_helpers, "_load_ensembles_layout", lambda process_name, max_seeds=50: None)

    oracle = runner_helpers.load_karr_oracle("Metabolism")

    assert oracle["canonical_seed_count"] == 1
    assert any("KARR_LEGACY_SINGLE_SEED_FALLBACK" in warning for warning in oracle["warnings"])


# ----------------------------------------------------------------------
# Canonical seed-0 recognition + schema-drift preflight
# (fix(l2.2): recognize canonical seed zero and reject schema drift)
# ----------------------------------------------------------------------


def _rna_decay_canonical_path(root: Path) -> Path:
    return root / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2" / "RNADecay_100ticks.mat"


def _rna_decay_suffixed_path(root: Path, seed: int) -> Path:
    return (
        root
        / "data"
        / "m1_sources"
        / "karr_native"
        / f"per_process_traces_v2_s{seed:03d}"
        / "RNADecay_100ticks.mat"
    )


def _resolve_git_dir_and_worktree(repo_root: Path) -> tuple[str, str]:
    """Resolve `--git-dir`/`--work-tree` args that work even when this repo
    root is a git *worktree* whose `.git` pointer file records a Windows-style
    absolute path (e.g. `gitdir: E:/opencell/.git/worktrees/<name>`). Native
    WSL git cannot parse a drive-letter path as absolute and fails with
    "not a git repository"; translate it to `/mnt/<drive>/...` first."""
    dot_git = repo_root / ".git"
    git_dir = str(dot_git)
    if dot_git.is_file():
        content = dot_git.read_text(encoding="utf-8").strip()
        if content.startswith("gitdir:"):
            raw = content.split(":", 1)[1].strip()
            match = re.match(r"^([A-Za-z]):[/\\](.*)$", raw)
            if match:
                drive, rest = match.groups()
                raw = f"/mnt/{drive.lower()}/{rest.replace(chr(92), '/')}"
            git_dir = raw
    return git_dir, str(repo_root)


def test_v2_seed_mat_path_seed0_prefers_canonical_unsuffixed_when_only_canonical_exists(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    before, after = _rna_decay_tick_vectors(seed=0)
    canonical_path = _rna_decay_canonical_path(tmp_path)
    _write_mat_trace(canonical_path, states_before=before, states_after=after)

    resolved = runner_helpers._v2_seed_mat_path("RNADecay", 0)

    assert resolved == canonical_path
    assert resolved.exists()


def test_v2_seed_mat_path_seed0_falls_back_to_suffixed_when_canonical_absent(
    monkeypatch, tmp_path: Path
) -> None:
    """Backward compatibility: an `_s000/` file alone (no canonical file) must
    still be discovered, matching the pre-fix behaviour this test suite
    already relied on (see `test_load_v2_ensemble_loads_single_seed`)."""
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    before, after = _rna_decay_tick_vectors(seed=0)
    suffixed_path = _rna_decay_suffixed_path(tmp_path, 0)
    _write_mat_trace(suffixed_path, states_before=before, states_after=after)

    resolved = runner_helpers._v2_seed_mat_path("RNADecay", 0)

    assert resolved == suffixed_path


def test_v2_seed_mat_path_seed0_returns_canonical_when_suffixed_is_byte_identical(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    before, after = _rna_decay_tick_vectors(seed=0)
    canonical_path = _rna_decay_canonical_path(tmp_path)
    suffixed_path = _rna_decay_suffixed_path(tmp_path, 0)
    _write_mat_trace(canonical_path, states_before=before, states_after=after)
    suffixed_path.parent.mkdir(parents=True, exist_ok=True)
    suffixed_path.write_bytes(canonical_path.read_bytes())

    resolved = runner_helpers._v2_seed_mat_path("RNADecay", 0)

    assert resolved == canonical_path


def test_v2_seed_mat_path_seed0_conflict_between_canonical_and_suffixed_raises(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    canonical_before, canonical_after = _rna_decay_tick_vectors(seed=0)
    suffixed_before, suffixed_after = _rna_decay_tick_vectors(seed=1)  # deliberately divergent content
    _write_mat_trace(
        _rna_decay_canonical_path(tmp_path), states_before=canonical_before, states_after=canonical_after
    )
    _write_mat_trace(
        _rna_decay_suffixed_path(tmp_path, 0), states_before=suffixed_before, states_after=suffixed_after
    )

    with pytest.raises(ValueError, match=r"Seed-0 conflict for 'RNADecay'"):
        runner_helpers._v2_seed_mat_path("RNADecay", 0)


def test_load_v2_ensemble_canonical_seed0_plus_suffixed_seed1_equals_two_seeds(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    seed0_before, seed0_after = _rna_decay_tick_vectors(seed=0)
    seed1_before, seed1_after = _rna_decay_tick_vectors(seed=1)
    _write_mat_trace(_rna_decay_canonical_path(tmp_path), states_before=seed0_before, states_after=seed0_after)
    _write_mat_trace(_rna_decay_suffixed_path(tmp_path, 1), states_before=seed1_before, states_after=seed1_after)

    oracle = runner_helpers._load_v2_ensemble("RNADecay", max_seeds=3)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 2
    # The seed-0 slot must resolve via the canonical unsuffixed path, not a
    # `_s000/` workaround.
    assert oracle["oracle_path"].parent.name == "per_process_traces_v2"


def test_load_v2_ensemble_canonical_seed0_only_yields_single_seed_and_runner_warns_on_reuse(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    before, after = _rna_decay_tick_vectors(seed=0)
    _write_mat_trace(_rna_decay_canonical_path(tmp_path), states_before=before, states_after=after)

    oracle = runner_helpers._load_v2_ensemble("RNADecay", max_seeds=3)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 1

    warnings = runner._warning_strings(
        process="RNADecay",
        oc_vectors_by_channel={},
        karr_vectors_by_channel={},
        canonical_seed_count=oracle["canonical_seed_count"],
        requested_seed_count=2,
    )
    assert any("KARR_SINGLE_SEED_REUSED" in warning for warning in warnings)


def test_warning_strings_omits_reuse_warning_when_two_genuine_seeds_available() -> None:
    """A genuine 2-seed pilot must not be flagged as seed reuse."""
    warnings = runner._warning_strings(
        process="RNADecay",
        oc_vectors_by_channel={},
        karr_vectors_by_channel={},
        canonical_seed_count=2,
        requested_seed_count=2,
    )

    assert not any("KARR_SINGLE_SEED_REUSED" in warning for warning in warnings)


def test_load_v2_ensemble_missing_channel_schema_drift_raises_actionable_error(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    seed0_before, seed0_after = _rna_decay_tick_vectors(seed=0)
    # Simulate an older-schema seed-1 fixture that predates the "RNAs" channel
    # (the exact drift class MULTISEED_PILOT_REPORT.md flags for Translation).
    seed1_before = {key: value for key, value in seed0_before.items() if key != "RNAs"}
    seed1_after = {key: value for key, value in seed0_after.items() if key != "RNAs"}
    _write_mat_trace(_rna_decay_canonical_path(tmp_path), states_before=seed0_before, states_after=seed0_after)
    _write_mat_trace(_rna_decay_suffixed_path(tmp_path, 1), states_before=seed1_before, states_after=seed1_after)

    with pytest.raises(ValueError, match=r"Schema drift for RNADecay.*missing=\['RNAs'\]"):
        runner_helpers._load_v2_ensemble("RNADecay", max_seeds=3)


def test_load_v2_ensemble_channel_width_schema_drift_raises_actionable_error(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    seed0_before, seed0_after = _rna_decay_tick_vectors(seed=0, rna_width=2)
    seed1_before, seed1_after = _rna_decay_tick_vectors(seed=1, rna_width=5)
    _write_mat_trace(_rna_decay_canonical_path(tmp_path), states_before=seed0_before, states_after=seed0_after)
    _write_mat_trace(_rna_decay_suffixed_path(tmp_path, 1), states_before=seed1_before, states_after=seed1_after)

    with pytest.raises(ValueError, match=r"Schema drift for RNADecay.*states_before/RNAs.*width"):
        runner_helpers._load_v2_ensemble("RNADecay", max_seeds=3)


def test_transcription_specialized_ensemble_still_wins_over_generic_v2_loader() -> None:
    """Real, unmocked check (no monkeypatching): Transcription's committed
    50-seed specialized ensemble must keep winning over the generic v2
    loader, matching MULTISEED_PILOT_REPORT.md section 5.3. This is the
    control case proving the canonical-seed0 fix does not disturb a process
    that already has a richer, unrelated oracle."""
    oracle = runner_helpers.load_karr_oracle("Transcription")

    assert oracle["canonical_seed_count"] == 50
    assert "ensembles/transcription" in str(oracle["oracle_path"]).replace("\\", "/")


_UNMOCKED_PILOT_PROCESSES = ("RNADecay", "ProteinDecay")


def _unmocked_pilot_files_present() -> bool:
    return all(
        _rna_decay_canonical_path(_REPO_ROOT).with_name(f"{process}_100ticks.mat").exists()
        and _rna_decay_suffixed_path(_REPO_ROOT, 1).with_name(f"{process}_100ticks.mat").exists()
        for process in _UNMOCKED_PILOT_PROCESSES
    )


@pytest.mark.skipif(
    not _unmocked_pilot_files_present(),
    reason=(
        "Local unsuffixed-canonical + seed-1 RNADecay/ProteinDecay traces are "
        "gitignored pilot evidence not present on this machine; copy them from "
        "the accepted L2.2 multi-seed pilot (see "
        "docs/phase_f/l2_2_design_a/MULTISEED_PILOT_REPORT.md) to re-run this check."
    ),
)
@pytest.mark.parametrize("process", _UNMOCKED_PILOT_PROCESSES)
def test_rna_decay_and_protein_decay_use_real_canonical_seed0_via_loader_unmocked(process: str) -> None:
    """Item 7: unmocked check using the accepted pilot's regenerated seed-0/
    seed-1 traces, materialized at the canonical unsuffixed path (not a
    `_s000/` workaround) in this worktree."""
    oracle = runner_helpers.load_karr_oracle(process)

    assert oracle["canonical_seed_count"] == 2
    assert not oracle.get("warnings")
    assert oracle["oracle_path"].parent.name == "per_process_traces_v2"


@pytest.mark.skipif(
    not _unmocked_pilot_files_present(),
    reason=(
        "Local unsuffixed-canonical + seed-1 RNADecay/ProteinDecay traces are "
        "gitignored pilot evidence not present on this machine."
    ),
)
def test_new_v2_seed_files_remain_git_ignored() -> None:
    """The canonical-seed0 fix must not require committing new binary blobs:
    both the unsuffixed `per_process_traces_v2/` directory and per-process
    `_sNNN/` seed files stay covered by `.gitignore`."""
    candidates = [
        _rna_decay_canonical_path(_REPO_ROOT).with_name(f"{process}_100ticks.mat")
        for process in _UNMOCKED_PILOT_PROCESSES
    ] + [
        _rna_decay_suffixed_path(_REPO_ROOT, 1).with_name(f"{process}_100ticks.mat")
        for process in _UNMOCKED_PILOT_PROCESSES
    ]

    git_dir, work_tree = _resolve_git_dir_and_worktree(_REPO_ROOT)
    for path in candidates:
        result = subprocess.run(
            ["git", f"--git-dir={git_dir}", f"--work-tree={work_tree}", "check-ignore", "-q", str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{path} is not covered by .gitignore (git check-ignore exit={result.returncode})"
