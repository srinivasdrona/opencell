"""Unit tests for `scripts/l2_event/launcher.py` (MATLAB-free planning core
and command builder for the M4 fixed/anchor event-window extractor
contract, docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md).

No MATLAB is invoked anywhere in this file. Every trace fixture is a small
synthetic HDF5 file written directly with h5py (matching the shape
`tests/scripts/test_l2_event_window_loader.py` already exercises the
loader with), never a real Karr oracle trace read for its numeric content
-- FIX_TEMPLATE_L2_REPLAY Rule 8 (no oracle reads). Two inversions this
file specifically guards against (Slot 1 pre-mortem):

* A sparse/firing-only grid (stride != 1, or a trace with only firing-tick
  metadata) must never be silently accepted as `skip_valid` --
  `test_plan_regenerate_invalid_for_stride_not_one` and
  `test_plan_regenerate_invalid_for_pre_m4_trace_missing_stride_contract`.
* A trace produced for a *different* window_contract (or a plain standard
  mid-cycle trace) sitting at the same event-window path must never be
  silently reused as if it satisfied the newly requested extraction (the
  "duplicate existing extraction" failure mode) --
  `test_plan_regenerate_invalid_for_window_contract_kind_mismatch` and
  `test_plan_regenerate_invalid_for_standard_mid_cycle_trace_present_at_event_path`.
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
from scripts.l2_event.window_loader import load_event_window  # noqa: E402


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


# Sentinel distinct from `None`: `None` already means "omit this metadata
# key entirely" for every optional _write_event_window_fixture parameter
# (matching signal_kind/window_anchor/etc.'s existing convention), so a
# separate sentinel is needed to mean "use today's real, valid
# mnrnd-shim-identity value" as the DEFAULT -- keeping every pre-existing
# call site (27 of them) a valid/skip_valid-eligible fixture unless a test
# explicitly overrides mnrnd_shim_version/mnrnd_shim_sha256 to omit or
# mismatch them.
_MNRND_SHIM_DEFAULT = object()


def _write_event_window_fixture(
    path: Path,
    *,
    process_name: str,
    seed: int,
    n_ticks: int = 4,
    tick_offset: float | None = 0.0,
    stride: int | None = 1,
    tick_start: int | None = 0,
    tick_end: int | None = -1,
    window_anchor: int | None = None,
    onset_tick: int | None = None,
    observables: tuple[str, ...] = (),
    # Anchor-config identity-binding metadata (Opus 5 rejection finding:
    # persist signal kind/property/field/max_search_ticks/projection
    # schema so a trace from a different anchor request can never
    # skip-valid). None (the default) omits the key entirely, matching a
    # pre-identity-binding trace shape for inversion tests.
    signal_kind: str | None = None,
    signal_property: str | None = None,
    signal_field: str | None = None,
    max_search_ticks: int | None = None,
    event_observable_projection_version: int | None = None,
    extraction_identity_json: str | None = None,
    # mnrnd-shim identity-binding metadata (legacy-mnrnd defect fix):
    # _MNRND_SHIM_DEFAULT (the default) embeds today's real, valid
    # version/hash so every pre-existing call site stays a valid fixture;
    # pass None explicitly to omit the key (pre-identity-binding trace);
    # pass an explicit wrong value to simulate a stale/tampered shim.
    mnrnd_shim_version: int | None | object = _MNRND_SHIM_DEFAULT,
    mnrnd_shim_sha256: str | None | object = _MNRND_SHIM_DEFAULT,
) -> Path:
    """Write a minimal synthetic event-window trace: a `metadata` group
    plus empty `states_before`/`states_after` groups (optionally with a
    handful of plain-numeric-array observable datasets). Mirrors the shape
    `test_l2_event_window_loader.py`'s `_write_synthetic_trace` uses, kept
    local/independent here on purpose (this file's fixtures are launcher-
    planning-focused, not loader-refusal-gauntlet-focused).
    """
    if tick_end == -1:
        tick_end = n_ticks - 1
    if mnrnd_shim_version is _MNRND_SHIM_DEFAULT:
        mnrnd_shim_version = launcher.MNRND_SHIM_VERSION
    if mnrnd_shim_sha256 is _MNRND_SHIM_DEFAULT:
        mnrnd_shim_sha256 = launcher.mnrnd_shim_sha256_hex()
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata(process_name))
        metadata.create_dataset("rng_seed", data=np.array([seed]))
        if tick_offset is not None:
            metadata.create_dataset("tick_offset", data=np.array([tick_offset]))
        if stride is not None:
            metadata.create_dataset("stride", data=np.array([stride]))
        if tick_start is not None:
            metadata.create_dataset("tick_start", data=np.array([tick_start]))
        if tick_end is not None:
            metadata.create_dataset("tick_end", data=np.array([tick_end]))
        if window_anchor is not None:
            metadata.create_dataset("window_anchor", data=np.array([window_anchor]))
        if onset_tick is not None:
            metadata.create_dataset("onset_tick", data=np.array([onset_tick]))
        if signal_kind is not None:
            metadata.create_dataset("signal_kind", data=_encode_char_metadata(signal_kind))
        if signal_property is not None:
            metadata.create_dataset("signal_property", data=_encode_char_metadata(signal_property))
        if signal_field is not None:
            metadata.create_dataset("signal_field", data=_encode_char_metadata(signal_field))
        if max_search_ticks is not None:
            metadata.create_dataset("max_search_ticks", data=np.array([max_search_ticks]))
        if event_observable_projection_version is not None:
            metadata.create_dataset(
                "event_observable_projection_version", data=np.array([event_observable_projection_version])
            )
        if extraction_identity_json is not None:
            metadata.create_dataset("extraction_identity_json", data=_encode_char_metadata(extraction_identity_json))
        if mnrnd_shim_version is not None:
            metadata.create_dataset("mnrnd_shim_version", data=np.array([mnrnd_shim_version]))
        if mnrnd_shim_sha256 is not None:
            metadata.create_dataset("mnrnd_shim_sha256", data=_encode_char_metadata(mnrnd_shim_sha256))

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in observables:
            states_before.create_dataset(observable, data=np.zeros((1, n_ticks)))
            states_after.create_dataset(observable, data=np.zeros((1, n_ticks)))
    return path


# ---------------------------------------------------------------------------
# WindowSpec construction / config-time error semantics
# ---------------------------------------------------------------------------


def test_fixed_window_spec_rejects_negative_tick_offset():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=-1, required_observables=("substrates",))


def test_fixed_window_spec_rejects_zero_n_ticks():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.FixedWindowSpec(
            process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=0, required_observables=("substrates",)
        )


def test_fixed_window_spec_rejects_empty_required_observables():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, required_observables=())


def test_fixed_window_spec_rejects_non_dict_matlab_extraction_opts():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.FixedWindowSpec(
            process="DNADamage",
            seed=2000,
            tick_offset=0,
            required_observables=("chromosome", "substrates"),
            matlab_extraction_opts="not-a-dict",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "unsafe_process",
    [
        'Bad"Process',
        "Bad`Process`",
        "Bad$Process",
        "Bad;Process",
        "Bad\nProcess",
        "Bad\rProcess",
    ],
)
def test_fixed_window_spec_rejects_shell_metacharacters_in_process(unsafe_process):
    """Opus 5 rejection finding: spec identifiers must be restricted to
    safe tokens (or otherwise made safe at the eventual matlab-batch shell
    boundary) -- a double quote, backtick, `$`, `;`, or newline/carriage-
    return in `process` must be refused at construction time, before any
    command string is ever built."""
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.FixedWindowSpec(
            process=unsafe_process, seed=1, tick_offset=200, required_observables=("substrates",)
        )


def test_fixed_window_spec_accepts_embedded_single_quote_in_process():
    """A plain embedded single quote is NOT a rejected shell metacharacter
    here -- it is a legitimate character `_matlab_quote` already escapes
    correctly (doubling, MATLAB's own convention); see
    `test_build_matlab_command_quotes_embedded_single_quote_in_process_name`."""
    spec = launcher.FixedWindowSpec(
        process="Weird'Process", seed=1, tick_offset=200, required_observables=("substrates",)
    )
    assert spec.process == "Weird'Process"


def test_anchor_window_spec_rejects_max_search_ticks_shorter_than_n_ticks():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(
            process="Cytokinesis", seed=1, n_ticks=100, max_search_ticks=10, required_observables=("pinchedDiameter",)
        )


def test_anchor_window_spec_rejects_empty_signal_property():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(
            process="Cytokinesis", seed=1, signal_property="", required_observables=("pinchedDiameter",)
        )


@pytest.mark.parametrize("unsafe_value", ['Bad"Prop', "Bad`Prop", "Bad$Prop", "Bad;Prop", "Bad\nProp"])
def test_anchor_window_spec_rejects_shell_metacharacters_in_signal_property(unsafe_value):
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(
            process="Cytokinesis", seed=1, signal_property=unsafe_value, required_observables=("pinchedDiameter",)
        )


def test_anchor_window_spec_rejects_shell_metacharacters_in_signal_field():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(
            process="Cytokinesis",
            seed=1,
            signal_field="bad;field",
            required_observables=("pinchedDiameter",),
        )


def test_anchor_window_spec_rejects_empty_required_observables():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(process="Cytokinesis", seed=1, required_observables=())


def test_anchor_window_spec_rejects_invalid_signal_kind():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(
            process="Cytokinesis", seed=1, required_observables=("pinchedDiameter",), signal_kind="bogus_kind"
        )


def test_anchor_window_spec_rejects_scalar_finite_observables_not_subset_of_required():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(
            process="Cytokinesis",
            seed=1,
            required_observables=("pinchedDiameter",),
            scalar_finite_observables=("ftsZRing_numResidualBent",),
        )


def test_anchor_window_spec_default_signal_kind_and_field_are_diameter_decrease():
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=1, required_observables=("pinchedDiameter",))
    assert spec.signal_kind == "diameter_decrease"
    assert spec.signal_field == "pinchedDiameter"


def test_anchor_window_spec_boolean_transition_default_field_is_pinched():
    spec = launcher.AnchorWindowSpec(
        process="FtsZPolymerization",
        seed=1,
        required_observables=("someBool",),
        signal_kind="boolean_transition",
    )
    assert spec.signal_field == "pinched"


def test_spec_from_dict_rejects_unknown_window_contract():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher._spec_from_dict({"process": "X", "seed": 1, "window_contract": "sparse"})


def test_spec_from_dict_rejects_missing_required_observables():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher._spec_from_dict(
            {"process": "RibosomeAssembly", "seed": 3, "window_contract": "fixed", "tick_offset": 200}
        )


def test_spec_from_dict_round_trips_fixed_and_anchor():
    fixed = launcher._spec_from_dict(
        {
            "process": "RibosomeAssembly",
            "seed": 3,
            "window_contract": "fixed",
            "tick_offset": 200,
            "required_observables": ["substrates"],
        }
    )
    assert isinstance(fixed, launcher.FixedWindowSpec)
    assert fixed.tick_offset == 200
    assert fixed.required_observables == ("substrates",)

    anchor = launcher._spec_from_dict(
        {
            "process": "Cytokinesis",
            "seed": 3,
            "window_contract": "anchor",
            "required_observables": list(launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES),
        }
    )
    assert isinstance(anchor, launcher.AnchorWindowSpec)
    assert anchor.signal_property == launcher.DEFAULT_ANCHOR_SIGNAL_PROPERTY
    assert anchor.signal_kind == launcher.DEFAULT_ANCHOR_SIGNAL_KIND


# ---------------------------------------------------------------------------
# Output path / layout
# ---------------------------------------------------------------------------


def test_event_window_output_dir_uses_event_suffix(tmp_path):
    out_dir = launcher.event_window_output_dir(7, karr_native_root=tmp_path)
    assert out_dir.name == "per_process_traces_v2_event_s007"
    assert "per_process_traces_v2_event_s007" in str(out_dir)


def test_event_window_mat_path_matches_contract_layout(tmp_path):
    path = launcher.event_window_mat_path("RibosomeAssembly", 3, n_ticks=100, karr_native_root=tmp_path)
    assert path == tmp_path / "per_process_traces_v2_event_s003" / "RibosomeAssembly_100ticks.mat"


# ---------------------------------------------------------------------------
# build_matlab_command
# ---------------------------------------------------------------------------


def test_build_matlab_command_fixed_window_writes_stride1_contract_call():
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=3, tick_offset=200, n_ticks=100, required_observables=("substrates",)
    )
    command = launcher.build_matlab_command(spec)
    assert "per_process_traces_v2_event_s003" in command
    assert "'RibosomeAssembly'" in command
    assert "uint32(3)" in command
    assert ", 200, 'fixed');" in command
    assert "'anchor'" not in command


def test_build_matlab_command_fixed_window_can_carry_extraction_opts():
    spec = launcher.FixedWindowSpec(
        process="DNADamage",
        seed=2000,
        tick_offset=0,
        n_ticks=20,
        required_observables=("chromosome", "substrates"),
        extraction_identity_json='{"condition":"uvb_mechanism"}',
        matlab_extraction_opts={
            "condition_label": "uvb_mechanism",
            "metadata_identity_json": '{"condition":"uvb_mechanism"}',
            "per_process_substrate_overrides": {
                "DNADamage": {
                    "UVB_radiation": 7.474096569667582,
                }
            },
        },
    )
    command = launcher.build_matlab_command(spec)
    assert "uint32(2000), 0, 'fixed', [], struct(" in command
    assert "'condition_label', 'uvb_mechanism'" in command
    assert "'metadata_identity_json', '{\"condition\":\"uvb_mechanism\"}'" in command
    assert "'per_process_substrate_overrides'" in command
    assert "'DNADamage'" in command
    assert "'UVB_radiation', 7.474096569667582" in command


def test_build_matlab_command_unconditionally_shadows_mnrnd_for_fixed_and_anchor():
    """Documents/tests, rather than leaves implicit, the exact mechanism
    that makes scripts/matlab/mnrnd.m identity-binding necessary: every
    generated command -- 'fixed' or 'anchor', regardless of which process
    is targeted -- prepends addpath('scripts/matlab') BEFORE the default
    (include_addpath=True), so the repo-owned mnrnd/poissrnd/binornd/
    random/randsample fallbacks silently shadow the real Statistics-
    Toolbox implementations for the entire simulated run, not just the
    requested process. include_addpath=False is available (and exercised
    here) precisely so a future caller COULD opt out, but no caller in
    this codebase does -- the shadow is universal today by construction."""
    fixed_spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=30, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    anchor_spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=31, n_ticks=4, required_observables=("pinchedDiameter",))
    for spec in (fixed_spec, anchor_spec):
        command = launcher.build_matlab_command(spec)
        assert command.startswith("addpath('scripts/matlab'); ")
        no_addpath_command = launcher.build_matlab_command(spec, include_addpath=False)
        assert "addpath('scripts/matlab')" not in no_addpath_command


def test_build_matlab_command_anchor_window_never_supplies_tick_offset():
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=7, n_ticks=50, required_observables=("pinchedDiameter",))
    command = launcher.build_matlab_command(spec)
    assert "per_process_traces_v2_event_s007" in command
    assert "'Cytokinesis'" in command
    assert "uint32(7), [], 'anchor'" in command
    assert "max_search_ticks', 50000" in command
    assert "signal_kind', 'diameter_decrease'" in command
    assert "signal_property', 'geometry'" in command
    assert "signal_field', 'pinchedDiameter'" in command
    assert "'fixed'" not in command


def test_build_matlab_command_is_diary_wrapped_when_log_given():
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=1, tick_offset=200, required_observables=("substrates",)
    )
    command = launcher.build_matlab_command(spec, log_relpath="artifacts/seed001.log")
    assert "diary('artifacts/seed001.log')" in command
    assert "diary off" in command
    assert "try;" in command and "catch err;" in command
    assert "exit(1)" in command
    assert command.rstrip().endswith("exit(0);")


def test_build_matlab_command_no_log_still_propagates_exit_codes():
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=1, tick_offset=200, required_observables=("substrates",)
    )
    command = launcher.build_matlab_command(spec)
    assert "exit(1)" in command
    assert command.rstrip().endswith("exit(0);")


def test_build_matlab_command_quotes_embedded_single_quote_in_process_name():
    """Opus 5 rejection finding: MATLAB quoting was incomplete. A process
    name (or any other interpolated string) containing an embedded `'`
    must never terminate the MATLAB literal early -- it must be escaped by
    doubling, MATLAB's own convention."""
    spec = launcher.FixedWindowSpec(
        process="Weird'Process", seed=1, tick_offset=200, required_observables=("substrates",)
    )
    command = launcher.build_matlab_command(spec)
    assert "Weird''Process" in command
    # A naive/unescaped quote would produce an unbalanced-quote command;
    # the escaped form keeps the single-quoted literal well-formed.
    assert "{'Weird''Process'}" in command


def test_matlab_quote_rejects_embedded_newline():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher._matlab_quote("bad\nvalue")


def test_build_matlab_command_custom_anchor_signal_is_reflected():
    spec = launcher.AnchorWindowSpec(
        process="FtsZPolymerization",
        seed=2,
        n_ticks=20,
        signal_property="ftsZRing",
        signal_field="numResidualBent",
        signal_kind="boolean_transition",
        required_observables=("numResidualBent",),
    )
    command = launcher.build_matlab_command(spec)
    assert "signal_kind', 'boolean_transition'" in command
    assert "signal_property', 'ftsZRing'" in command
    assert "signal_field', 'numResidualBent'" in command


def test_build_matlab_command_output_subdir_override_targets_temp_regen_dir(tmp_path):
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=9, n_ticks=4, required_observables=("pinchedDiameter",))
    token = launcher.temp_regen_token()
    temp_subdir = launcher.temp_output_subdir_for(spec, token, karr_native_root=tmp_path)
    assert token in temp_subdir
    command = launcher.build_matlab_command(spec, output_subdir=temp_subdir)
    assert launcher._matlab_quote(temp_subdir) in command
    default_subdir = launcher.output_dir_for(spec, karr_native_root=tmp_path).name
    command_without_override = launcher.build_matlab_command(spec)
    assert launcher._matlab_quote(default_subdir) in command_without_override
    assert launcher._matlab_quote(default_subdir) not in command


# ---------------------------------------------------------------------------
# validate_existing_event_window / plan_event_window_extraction
# ---------------------------------------------------------------------------


def test_plan_missing_file_is_generate_missing(tmp_path):
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "generate_missing"
    assert len(plan.jobs) == 1
    assert plan.jobs[0].window_contract == "fixed"


def test_plan_skip_valid_for_contract_complete_fixed_fixture(tmp_path):
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=1,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=201,  # tick_offset + 1 (absolute 1-based coordinate, burn-in fix)
        tick_end=204,  # tick_offset + n_ticks
        observables=("substrates",),
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "skip_valid"
    assert plan.decisions[0].reason is None
    assert len(plan.jobs) == 0


def test_plan_skip_valid_for_contract_complete_fixed_fixture_with_extraction_identity(tmp_path):
    identity_json = '{"condition":"uvb_mechanism","process":"DNADamage"}'
    spec = launcher.FixedWindowSpec(
        process="DNADamage",
        seed=2000,
        tick_offset=0,
        n_ticks=20,
        required_observables=("chromosome", "substrates"),
        extraction_identity_json=identity_json,
    )
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="DNADamage",
        seed=2000,
        n_ticks=20,
        tick_offset=0.0,
        stride=1,
        tick_start=1,
        tick_end=20,
        observables=("chromosome", "substrates"),
        extraction_identity_json=identity_json,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "skip_valid"
    assert len(plan.jobs) == 0


def test_plan_regenerate_invalid_for_fixed_fixture_missing_extraction_identity(tmp_path):
    identity_json = '{"condition":"uvb_mechanism","process":"DNADamage"}'
    spec = launcher.FixedWindowSpec(
        process="DNADamage",
        seed=2000,
        tick_offset=0,
        n_ticks=20,
        required_observables=("chromosome", "substrates"),
        extraction_identity_json=identity_json,
    )
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="DNADamage",
        seed=2000,
        n_ticks=20,
        tick_offset=0.0,
        stride=1,
        tick_start=1,
        tick_end=20,
        observables=("chromosome", "substrates"),
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "extraction_identity_json" in (plan.decisions[0].reason or "")
    assert len(plan.jobs) == 1


def test_plan_skip_valid_for_contract_complete_anchor_fixture(tmp_path):
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=9, n_ticks=4, required_observables=("pinchedDiameter",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=9,
        n_ticks=4,
        tick_offset=996.0,
        stride=1,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=997,
        observables=("pinchedDiameter",),
        # Identity-binding anchor metadata must match the default spec's
        # resolved signal config exactly for skip_valid to apply.
        signal_kind=spec.signal_kind,
        signal_property=spec.signal_property,
        signal_field=spec.signal_field,
        max_search_ticks=spec.max_search_ticks,
        event_observable_projection_version=launcher.EVENT_OBSERVABLE_PROJECTION_VERSION,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "skip_valid"
    assert len(plan.jobs) == 0


def test_plan_regenerate_invalid_for_pre_m4_trace_missing_stride_contract(tmp_path):
    """The two real pre-M4 traces on disk today (RibosomeAssembly/RNAModification
    seed 000) carry tick_offset but no stride/tick_start/tick_end -- this must
    be `regenerate_invalid`, never `skip_valid`."""
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=0, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=0,
        n_ticks=4,
        tick_offset=200.0,
        stride=None,
        tick_start=None,
        tick_end=None,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "INCOMPLETE_WINDOW" in plan.decisions[0].reason
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_stride_not_one(tmp_path):
    """Inversion guard: a sparse (stride=2) grid must never be silently
    accepted as satisfying a stride-1 fixed-window request."""
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=2, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=2,
        n_ticks=4,
        tick_offset=200.0,
        stride=2,
        tick_start=201,
        tick_end=204,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "stride" in plan.decisions[0].reason


def test_plan_regenerate_invalid_for_fixed_tick_offset_mismatch(tmp_path):
    """Fixed-window identity binding: an on-disk trace whose
    metadata.tick_offset (burn-in count) does not match the requested
    spec's tick_offset must never skip_valid, even though it is otherwise
    a complete stride-1 grid -- it was produced for a DIFFERENT burn-in
    request."""
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=11, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=11,
        n_ticks=4,
        tick_offset=150.0,  # a different burn-in count than the spec requests
        stride=1,
        tick_start=151,
        tick_end=154,
        observables=("substrates",),
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "tick_offset" in plan.decisions[0].reason


def test_plan_regenerate_invalid_for_fixed_tick_start_off_by_one(tmp_path):
    """Fixed-window identity binding, the exact Opus 5 off-by-one: even
    when metadata.tick_offset matches, a tick_start that is still
    `tick_offset` (the pre-Turn-3 formula) instead of `tick_offset + 1`
    must never skip_valid."""
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=12, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=12,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=200,  # off by one: should be tick_offset + 1 = 201
        tick_end=203,  # off by one: should be tick_offset + n_ticks = 204
        observables=("substrates",),
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "tick_start" in plan.decisions[0].reason


def test_plan_regenerate_invalid_for_corrupt_zero_byte_file(tmp_path):
    """Opus 5 rejection finding: a corrupt (here: zero-byte) existing file
    must be classified regenerate_invalid, never crash the planner and
    never skip_valid."""
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=13, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_garbage_non_hdf5_file(tmp_path):
    """Same guarantee for a non-empty but non-HDF5 (garbage/truncated)
    file: h5py raises OSError opening it -- validate_existing_event_window
    must catch this, never crash, and never skip_valid."""
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=14, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not an hdf5 file, just garbage bytes" * 10)
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_anchor_signal_property_mismatch(tmp_path):
    """Anchor identity binding: an on-disk trace produced for a DIFFERENT
    signal_property (even if otherwise contract-complete) must never
    skip_valid against a spec requesting the default ('geometry')."""
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=15, n_ticks=4, required_observables=("pinchedDiameter",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=15,
        n_ticks=4,
        tick_offset=996.0,
        stride=1,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=997,
        observables=("pinchedDiameter",),
        signal_kind=spec.signal_kind,
        signal_property="wrongSignalProperty",  # mismatch
        signal_field=spec.signal_field,
        max_search_ticks=spec.max_search_ticks,
        event_observable_projection_version=launcher.EVENT_OBSERVABLE_PROJECTION_VERSION,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "signal_property" in plan.decisions[0].reason


def test_plan_regenerate_invalid_for_anchor_missing_identity_metadata(tmp_path):
    """A pre-identity-binding anchor trace (structurally complete, but
    missing the new signal_kind/property/field/max_search_ticks/
    projection-version metadata this Turn 3 fix requires) must never
    skip_valid -- it cannot be cross-checked against the requested signal
    configuration at all."""
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=16, n_ticks=4, required_observables=("pinchedDiameter",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=16,
        n_ticks=4,
        tick_offset=996.0,
        stride=1,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=997,
        observables=("pinchedDiameter",),
        # signal_kind/property/field/max_search_ticks/projection_version
        # all omitted -- simulating an older trace.
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"


def test_plan_regenerate_invalid_for_anchor_stale_projection_version(tmp_path):
    """Performance/sufficiency patch: a trace written under the OLD
    EVENT_OBSERVABLE_PROJECTION_VERSION (1 -- full chromosome object, no
    chromosome_segregated) must never skip_valid against a spec expecting
    the current version (2 -- chromosome_segregated present, full
    chromosome object excluded). A stale v1 trace is contract-complete and
    identity-matching in every other respect; only the projection-version
    literal differs."""
    spec = launcher.AnchorWindowSpec(
        process="Cytokinesis", seed=17, n_ticks=4, required_observables=launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES
    )
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=17,
        n_ticks=4,
        tick_offset=996.0,
        stride=1,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=997,
        observables=launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES,
        signal_kind=spec.signal_kind,
        signal_property=spec.signal_property,
        signal_field=spec.signal_field,
        max_search_ticks=spec.max_search_ticks,
        event_observable_projection_version=1,  # stale: pre-patch schema
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "event_observable_projection_version" in plan.decisions[0].reason
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_anchor_missing_chromosome_segregated_observable(tmp_path):
    """Required-observable enforcement: a Cytokinesis diameter-anchor spec
    that requires launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES (which now
    includes 'chromosome_segregated') must regenerate_invalid against a
    trace that is otherwise contract- and identity-complete (current
    projection version, matching signal config) but is simply missing the
    'chromosome_segregated' observable dataset -- proving the new
    observable is actually enforced, not merely documented."""
    spec = launcher.AnchorWindowSpec(
        process="Cytokinesis", seed=18, n_ticks=4, required_observables=launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES
    )
    assert launcher.CYTOKINESIS_CHROMOSOME_OBSERVABLE in spec.required_observables
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    observables_missing_chromosome = tuple(
        obs for obs in launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES if obs != launcher.CYTOKINESIS_CHROMOSOME_OBSERVABLE
    )
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=18,
        n_ticks=4,
        tick_offset=996.0,
        stride=1,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=997,
        observables=observables_missing_chromosome,  # chromosome_segregated deliberately absent
        signal_kind=spec.signal_kind,
        signal_property=spec.signal_property,
        signal_field=spec.signal_field,
        max_search_ticks=spec.max_search_ticks,
        event_observable_projection_version=launcher.EVENT_OBSERVABLE_PROJECTION_VERSION,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "chromosome_segregated" in plan.decisions[0].reason
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_fixed_missing_mnrnd_shim_metadata(tmp_path):
    """Legacy-mnrnd defect fix: a pre-existing 'fixed' trace (structurally
    complete, correct tick_offset/tick_start/tick_end) that was produced
    BEFORE mnrnd-shim identity-binding metadata existed must never
    skip_valid -- build_matlab_command's addpath('scripts/matlab') path-
    shadow was already unconditionally active for every 'fixed' window
    job, so a trace lacking mnrnd_shim_version/mnrnd_shim_sha256 entirely
    cannot be told apart from one produced under the pre-fix, duplicate-
    edge-unsafe mnrnd.m."""
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=21, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=21,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=201,
        tick_end=204,
        observables=("substrates",),
        mnrnd_shim_version=None,
        mnrnd_shim_sha256=None,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "mnrnd_shim_version" in plan.decisions[0].reason
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_anchor_missing_mnrnd_shim_metadata(tmp_path):
    """Same as the 'fixed' case above, but for an otherwise contract- and
    identity-complete 'anchor' trace: mnrnd-shim identity binding is a
    SEPARATE check from signal_kind/property/field/max_search_ticks/
    projection-version, and must independently refuse skip_valid."""
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=22, n_ticks=4, required_observables=("pinchedDiameter",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=22,
        n_ticks=4,
        tick_offset=996.0,
        stride=1,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=997,
        observables=("pinchedDiameter",),
        signal_kind=spec.signal_kind,
        signal_property=spec.signal_property,
        signal_field=spec.signal_field,
        max_search_ticks=spec.max_search_ticks,
        event_observable_projection_version=launcher.EVENT_OBSERVABLE_PROJECTION_VERSION,
        mnrnd_shim_version=None,
        mnrnd_shim_sha256=None,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "mnrnd_shim_version" in plan.decisions[0].reason
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_stale_mnrnd_shim_version(tmp_path):
    """A trace stamped with an OLD/wrong mnrnd_shim_version integer (but a
    matching current sha256 -- simulating a future revision bump where
    only the version literal was forgotten to be updated at write time)
    must still regenerate_invalid: version is checked independently of,
    and before, hash."""
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=23, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=23,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=201,
        tick_end=204,
        observables=("substrates",),
        mnrnd_shim_version=launcher.MNRND_SHIM_VERSION + 1,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "mnrnd_shim_version" in plan.decisions[0].reason
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_mnrnd_shim_sha256_drift(tmp_path):
    """A trace stamped with the CURRENT mnrnd_shim_version but a
    mismatched mnrnd_shim_sha256 (simulating scripts/matlab/mnrnd.m being
    edited without a version bump) must regenerate_invalid -- the hash is
    the strong content binding that catches exactly this case, computed
    fresh from today's on-disk mnrnd.m, never a hardcoded constant."""
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=24, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=24,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=201,
        tick_end=204,
        observables=("substrates",),
        mnrnd_shim_sha256="0" * 64,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "mnrnd_shim_sha256" in plan.decisions[0].reason
    assert len(plan.jobs) == 1


def test_mnrnd_shim_sha256_hex_matches_real_file_and_is_lf_normalized(tmp_path):
    """Direct unit check of the Python-side hash helper: it must read the
    real, current scripts/matlab/mnrnd.m and be insensitive to CRLF vs LF
    line endings (matching the MATLAB-side mnrnd_shim_sha256_hex helper's
    own CR-stripping normalization -- both independently compute the same
    hash for the same logical content regardless of checkout settings)."""
    real_hash = launcher.mnrnd_shim_sha256_hex()
    assert isinstance(real_hash, str)
    assert len(real_hash) == 64
    int(real_hash, 16)  # must be valid hex

    lf_copy = tmp_path / "mnrnd_lf.m"
    crlf_copy = tmp_path / "mnrnd_crlf.m"
    original_bytes = launcher.MNRND_SHIM_PATH.read_bytes()
    lf_bytes = original_bytes.replace(b"\r\n", b"\n")
    crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
    lf_copy.write_bytes(lf_bytes)
    crlf_copy.write_bytes(crlf_bytes)

    assert launcher.mnrnd_shim_sha256_hex(lf_copy) == launcher.mnrnd_shim_sha256_hex(crlf_copy)
    assert launcher.mnrnd_shim_sha256_hex(lf_copy) == real_hash


def test_plan_regenerate_invalid_for_window_contract_kind_mismatch(tmp_path):
    """Inversion guard ('duplicate existing extraction'): an on-disk trace
    produced as an 'anchor' window (carries window_anchor, no tick_end) must
    not be silently reused when the caller now requests a 'fixed' window at
    the same (process, seed) path, and vice versa."""
    spec = launcher.FixedWindowSpec(process="Cytokinesis", seed=5, tick_offset=950, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=5,
        n_ticks=4,
        tick_offset=950.0,
        stride=1,
        tick_start=950,
        tick_end=None,
        window_anchor=953,
        observables=("substrates",),
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "window kind" in plan.decisions[0].reason


def test_plan_regenerate_invalid_for_standard_mid_cycle_trace_present_at_event_path(tmp_path):
    """Inversion guard: a plain standard mid-cycle trace (no tick_offset at
    all -- window_loader's NOT_EVENT_WINDOW_TRACE case) sitting at the
    event-window path must never be treated as satisfying an event-window
    request."""
    spec = launcher.FixedWindowSpec(process="Translation", seed=1, tick_offset=0, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Translation",
        seed=1,
        n_ticks=4,
        tick_offset=None,
        stride=None,
        tick_start=None,
        tick_end=None,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "NOT_EVENT_WINDOW_TRACE" in plan.decisions[0].reason


def test_plan_no_validate_mode_skips_without_checking_content(tmp_path):
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4, required_observables=("substrates",))
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path, process_name="WRONG", seed=99, n_ticks=4, stride=None, tick_start=None, tick_end=None
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path, validate_existing=False)
    assert plan.decisions[0].action == "skip_valid"
    assert len(plan.jobs) == 0


# ---------------------------------------------------------------------------
# Non-destructive atomic regeneration plumbing (replaces apply_invalidations'
# removed pre-emptive delete semantics -- Opus 5 rejection finding: "existing
# corrupt, empty, wrong-window, ... files could be [deleted to force
# regeneration]"). Never invoked against a real MATLAB-produced file in this
# task -- these tests exercise the plumbing directly with synthetic fixtures.
# ---------------------------------------------------------------------------


def test_plan_never_deletes_regenerate_invalid_file_and_records_prior_sha256(tmp_path):
    """The replacement for the old `apply_invalidations`: planning a
    `regenerate_invalid` spec must NEVER delete the prior on-disk file, must
    record its SHA-256 in the decision, and must target the matlab_command
    at a `.tmp-regen-<token>` sibling directory rather than the real path."""
    bad_spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=2, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    bad_path = launcher.mat_path_for(bad_spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        bad_path,
        process_name="RibosomeAssembly",
        seed=2,
        n_ticks=4,
        tick_offset=200.0,
        stride=2,
        tick_start=201,
        tick_end=204,
        observables=("substrates",),
    )
    expected_sha256 = launcher.sha256_of(bad_path)

    good_spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    good_path = launcher.mat_path_for(good_spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        good_path,
        process_name="RibosomeAssembly",
        seed=1,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=201,
        tick_end=204,
        observables=("substrates",),
    )

    plan = launcher.plan_event_window_extraction([bad_spec, good_spec], karr_native_root=tmp_path)

    # Never deleted:
    assert bad_path.exists()
    assert good_path.exists()

    bad_decision = next(d for d in plan.decisions if d.seed == 2)
    assert bad_decision.action == "regenerate_invalid"
    assert bad_decision.prior_file_sha256 == expected_sha256
    good_decision = next(d for d in plan.decisions if d.seed == 1)
    assert good_decision.action == "skip_valid"
    assert good_decision.prior_file_sha256 is None

    bad_job = next(j for j in plan.jobs if j.seed == 2)
    assert bad_job.final_output_path == str(bad_path)
    assert bad_job.temp_output_path is not None
    assert launcher.TEMP_REGEN_SUFFIX in bad_job.output_dir
    assert bad_job.temp_output_path != str(bad_path)
    # The unique per-job token minted for this regeneration must be
    # embedded in the job's own temp output dir name (see
    # `finalize_atomic_regeneration`'s `expected_token` binding).
    assert bad_job.regen_token is not None
    assert bad_job.regen_token in bad_job.output_dir


def test_generate_missing_job_has_no_temp_output_path(tmp_path):
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=3, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.jobs[0].temp_output_path is None
    assert plan.jobs[0].final_output_path == str(launcher.mat_path_for(spec, karr_native_root=tmp_path))
    assert plan.jobs[0].regen_token is None


def test_finalize_atomic_regeneration_replaces_only_after_validation(tmp_path):
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=4, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    final_path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        final_path, process_name="RibosomeAssembly", seed=4, n_ticks=4, tick_offset=200.0, stride=2, tick_start=201, tick_end=204
    )
    prior_sha256 = launcher.sha256_of(final_path)

    token, temp_path = launcher.allocate_unique_temp_output_path(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        temp_path,
        process_name="RibosomeAssembly",
        seed=4,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=201,
        tick_end=204,
        observables=("substrates",),
    )

    ok, reason = launcher.finalize_atomic_regeneration(
        temp_path, final_path, spec, expected_token=token, prior_final_sha256=prior_sha256
    )
    assert ok, reason
    assert not temp_path.exists()
    assert final_path.exists()
    assert launcher.sha256_of(final_path) != prior_sha256


def test_finalize_atomic_regeneration_leaves_prior_file_untouched_when_temp_invalid(tmp_path):
    """The core non-destructive guarantee: a temp regeneration output that
    itself fails validation must NEVER replace the prior file -- the prior
    file (valid or not) is left exactly as it was."""
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=5, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    final_path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        final_path, process_name="RibosomeAssembly", seed=5, n_ticks=4, tick_offset=200.0, stride=2, tick_start=201, tick_end=204
    )
    prior_sha256 = launcher.sha256_of(final_path)

    token, temp_path = launcher.allocate_unique_temp_output_path(spec, karr_native_root=tmp_path)
    # Still stride=2 (invalid) -- simulates a regeneration attempt that
    # produced another contract-incomplete file.
    _write_event_window_fixture(
        temp_path, process_name="RibosomeAssembly", seed=5, n_ticks=4, tick_offset=200.0, stride=2, tick_start=201, tick_end=204
    )

    ok, reason = launcher.finalize_atomic_regeneration(
        temp_path, final_path, spec, expected_token=token, prior_final_sha256=prior_sha256
    )
    assert not ok
    assert reason
    assert temp_path.exists()  # left for inspection
    assert final_path.exists()
    assert launcher.sha256_of(final_path) == prior_sha256  # untouched


def test_finalize_atomic_regeneration_fails_when_temp_missing(tmp_path):
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=6, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    final_path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        final_path, process_name="RibosomeAssembly", seed=6, n_ticks=4, tick_offset=200.0, stride=1, tick_start=201, tick_end=204
    )
    prior_sha256 = launcher.sha256_of(final_path)
    token, temp_path = launcher.allocate_unique_temp_output_path(spec, karr_native_root=tmp_path)
    ok, reason = launcher.finalize_atomic_regeneration(
        temp_path, final_path, spec, expected_token=token, prior_final_sha256=prior_sha256
    )
    assert not ok
    assert "does not exist" in reason
    # A failed/nonzero job must leave the prior final file byte-identical.
    assert launcher.sha256_of(final_path) == prior_sha256


def test_finalize_atomic_regeneration_refuses_stale_or_foreign_temp_token(tmp_path):
    """Opus 5 rejection finding: finalize must bind to the exact job token
    -- a temp directory embedding a DIFFERENT (stale/foreign) token must
    never be promoted, even if its content would otherwise validate."""
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=7, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    final_path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        final_path, process_name="RibosomeAssembly", seed=7, n_ticks=4, tick_offset=200.0, stride=2, tick_start=201, tick_end=204
    )
    prior_sha256 = launcher.sha256_of(final_path)

    foreign_token, temp_path = launcher.allocate_unique_temp_output_path(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        temp_path,
        process_name="RibosomeAssembly",
        seed=7,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=201,
        tick_end=204,
        observables=("substrates",),
    )

    # A DIFFERENT expected_token than the one actually embedded in
    # temp_path's parent directory name -- simulates a stale/foreign temp
    # directory left over from a different job.
    wrong_token = "not" + foreign_token
    ok, reason = launcher.finalize_atomic_regeneration(
        temp_path, final_path, spec, expected_token=wrong_token, prior_final_sha256=prior_sha256
    )
    assert not ok
    assert "token" in reason
    assert temp_path.exists()
    assert launcher.sha256_of(final_path) == prior_sha256


def test_finalize_atomic_regeneration_refuses_when_final_hash_changed_since_plan(tmp_path):
    """Opus 5 rejection finding: finalize must bind to the pre-run manifest
    hash -- if `final_path` changed since the plan captured
    `prior_file_sha256` (some other writer touched it), finalize must
    refuse rather than clobber an identity it never validated."""
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=8, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    final_path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        final_path, process_name="RibosomeAssembly", seed=8, n_ticks=4, tick_offset=200.0, stride=2, tick_start=201, tick_end=204
    )
    stale_prior_sha256 = "0" * 64  # deliberately wrong -- simulates a plan made before final_path changed

    token, temp_path = launcher.allocate_unique_temp_output_path(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        temp_path,
        process_name="RibosomeAssembly",
        seed=8,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=201,
        tick_end=204,
        observables=("substrates",),
    )
    current_final_sha256 = launcher.sha256_of(final_path)

    ok, reason = launcher.finalize_atomic_regeneration(
        temp_path, final_path, spec, expected_token=token, prior_final_sha256=stale_prior_sha256
    )
    assert not ok
    assert "sha256" in reason
    assert temp_path.exists()
    assert launcher.sha256_of(final_path) == current_final_sha256  # untouched


def test_allocate_unique_temp_output_path_avoids_collision_with_existing_temp_dir(tmp_path, monkeypatch):
    """Opus 5 rejection finding: two regeneration attempts (or a stale
    leftover temp dir) must never collide on the same `.tmp-regen-<token>`
    directory -- `allocate_unique_temp_output_path` must retry with a
    fresh token when its first candidate is already occupied."""
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=10, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    tokens = iter(["collide0000000a", "collide0000000a", "fresh000000000b"])
    monkeypatch.setattr(launcher, "temp_regen_token", lambda: next(tokens))

    # Pre-occupy the first candidate's temp directory (simulating a stale
    # leftover from a prior/abandoned run).
    occupied_dir = launcher.temp_output_path_for(spec, "collide0000000a", karr_native_root=tmp_path).parent
    occupied_dir.mkdir(parents=True)

    token, temp_path = launcher.allocate_unique_temp_output_path(spec, karr_native_root=tmp_path)
    assert token == "fresh000000000b"
    assert not temp_path.parent.exists()


def test_list_stale_regeneration_temp_dirs_reports_without_deleting(tmp_path):
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=20, tick_offset=200, n_ticks=4, required_observables=("substrates",)
    )
    token, temp_path = launcher.allocate_unique_temp_output_path(spec, karr_native_root=tmp_path)
    temp_path.parent.mkdir(parents=True)
    temp_path.write_bytes(b"leftover")

    stale = launcher.list_stale_regeneration_temp_dirs(karr_native_root=tmp_path)
    assert temp_path.parent in stale
    # Read-only: nothing is deleted.
    assert temp_path.parent.exists()
    assert temp_path.exists()


def test_sha256_of_missing_file_is_none(tmp_path):
    assert launcher.sha256_of(tmp_path / "nope.mat") is None


def test_plan_to_dict_is_json_serializable(tmp_path):
    specs = [
        launcher.FixedWindowSpec(
            process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4, required_observables=("substrates",)
        ),
        launcher.AnchorWindowSpec(process="Cytokinesis", seed=1, n_ticks=4, required_observables=("pinchedDiameter",)),
    ]
    plan = launcher.plan_event_window_extraction(specs, karr_native_root=tmp_path)
    payload = json.dumps(plan.to_dict())
    reloaded = json.loads(payload)
    assert len(reloaded["jobs"]) == 2
    assert len(reloaded["decisions"]) == 2
    assert plan.contract_version == "M4"
    assert len(reloaded["input_specs"]) == 2
    assert reloaded["input_specs"][0]["process"] == "RibosomeAssembly"


# ---------------------------------------------------------------------------
# Round-trip: the extractor's designed metadata shape is loader-compliant
# ---------------------------------------------------------------------------


def test_fixed_window_extractor_metadata_shape_is_accepted_by_loader_strict_default(tmp_path):
    """Proves (without running MATLAB) that the metadata
    `extract_per_process_traces_v2.m`'s window_contract='fixed' branch is
    designed to write -- stride=1, tick_start=tick_offset+1 (absolute
    1-based coordinate: burn-in consumes ticks 1..tick_offset, so the
    first CAPTURED tick is tick_offset+1), tick_end=tick_offset+n_ticks --
    satisfies window_loader's default require_stride_contract=True
    gauntlet, and that `validate_existing_event_window`'s identity-binding
    formula agrees with it exactly."""
    path = tmp_path / "per_process_traces_v2_event_s003" / "RibosomeAssembly_100ticks.mat"
    tick_offset = 200
    n_ticks = 100
    expected_tick_start = tick_offset + 1
    expected_tick_end = tick_offset + n_ticks
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=3,
        n_ticks=n_ticks,
        tick_offset=float(tick_offset),
        stride=1,
        tick_start=expected_tick_start,
        tick_end=expected_tick_end,
        observables=("substrates",),
    )
    window = load_event_window(path, required_observables=("substrates",))
    assert window.stride_contract_ok is True
    assert window.n_ticks == n_ticks
    assert window.tick_offset == tick_offset
    assert window.tick_start == expected_tick_start
    assert window.tick_end == expected_tick_end
    assert window.absolute_tick(0) == expected_tick_start

    # Same formula, independently exercised through the launcher's own
    # identity-binding validation (not just the raw loader).
    spec = launcher.FixedWindowSpec(
        process="RibosomeAssembly", seed=3, tick_offset=tick_offset, n_ticks=n_ticks, required_observables=("substrates",)
    )
    ok, reason = launcher.validate_existing_event_window(path, spec)
    assert ok, reason


def test_anchor_window_extractor_metadata_shape_is_accepted_by_loader_strict_default(tmp_path):
    """Same proof for window_contract='anchor': stride=1,
    tick_start=discovered onset-side window start, window_anchor=discovered
    completion tick (no tick_end), onset_tick=discovered TIMING anchor
    (distinct from window_anchor, the CAPTURE boundary)."""
    path = tmp_path / "per_process_traces_v2_event_s009" / "Cytokinesis_50ticks.mat"
    n_ticks = 50
    anchor_tick = 27_483
    onset_tick = anchor_tick - 12
    tick_start = anchor_tick - n_ticks + 1
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=9,
        n_ticks=n_ticks,
        tick_offset=float(tick_start),
        stride=1,
        tick_start=tick_start,
        tick_end=None,
        window_anchor=anchor_tick,
        onset_tick=onset_tick,
        observables=("chromosome",),
    )
    window = load_event_window(path, required_observables=("chromosome",))
    assert window.stride_contract_ok is True
    assert window.n_ticks == n_ticks
    assert window.tick_offset == tick_start
    assert window.window_anchor == anchor_tick
    assert window.completion_tick == anchor_tick
    assert window.onset_tick == onset_tick
    assert window.absolute_tick(0) == tick_start


# ---------------------------------------------------------------------------
# CLI (public path)
# ---------------------------------------------------------------------------


def test_cli_plan_subcommand_writes_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    specs_path = tmp_path / "specs.json"
    specs_path.write_text(
        json.dumps(
            [
                {
                    "process": "RibosomeAssembly",
                    "seed": 1,
                    "window_contract": "fixed",
                    "tick_offset": 200,
                    "n_ticks": 4,
                    "required_observables": ["substrates"],
                },
                {
                    "process": "Cytokinesis",
                    "seed": 1,
                    "window_contract": "anchor",
                    "n_ticks": 4,
                    "required_observables": list(launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES),
                    "scalar_finite_observables": list(launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES),
                },
            ]
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "plan.json"
    rc = launcher.main(["plan", "--specs", str(specs_path), "--out", str(out_path)])
    assert rc == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(payload["jobs"]) == 2
    assert payload["contract_version"] == "M4"
    assert len(payload["input_specs"]) == 2
    assert "deleted_invalid_files" not in payload


def test_cli_plan_subcommand_rejects_row_missing_required_observables(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    specs_path = tmp_path / "specs.json"
    specs_path.write_text(
        json.dumps([{"process": "RibosomeAssembly", "seed": 1, "window_contract": "fixed", "tick_offset": 200}]),
        encoding="utf-8",
    )
    out_path = tmp_path / "plan.json"
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.main(["plan", "--specs", str(specs_path), "--out", str(out_path)])


def test_cli_plan_subcommand_rejects_empty_specs_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    specs_path = tmp_path / "specs.json"
    specs_path.write_text(json.dumps([]), encoding="utf-8")
    out_path = tmp_path / "plan.json"
    rc = launcher.main(["plan", "--specs", str(specs_path), "--out", str(out_path)])
    assert rc == 1
    assert not out_path.exists()
