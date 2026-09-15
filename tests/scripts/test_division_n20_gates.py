"""Anti-cheat and semantics tests for the two division N=20 gates."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess  # noqa: E402
from scripts.l2_event import cytokinesis_n20_gate as cyt_gate  # noqa: E402
from scripts.l2_event import division_gate_common as common  # noqa: E402
from scripts.l2_event import ftsz_windowed_n20_gate as ftsz_gate  # noqa: E402
from scripts.l2_event.division_cohort_selector import CohortAudit  # noqa: E402
from scripts.l2_event.window_loader import WindowGrid  # noqa: E402
from scripts.l22_evidence import catalog as l22_catalog  # noqa: E402
from scripts.l22_evidence import generator as l22_generator  # noqa: E402
from scripts.l22_evidence import verdict as l22_verdict  # noqa: E402


def _audit(selected: list[int], *, satisfied: bool) -> CohortAudit:
    return CohortAudit(
        candidate_seed_start=0,
        required_completed_windows=20,
        selection_horizon_max_search_ticks=100000,
        contiguous_prefix_end=max(selected, default=-1),
        next_seed_to_attempt=max(selected, default=-1) + 1,
        attempted_seeds=list(selected),
        completed_seeds=list(selected),
        selected_seeds=list(selected),
        selection_satisfied=satisfied,
        attempted_count=len(selected),
        completed_count=len(selected),
        completion_fraction=1.0 if selected else 0.0,
    )


def _context(selected: list[int]) -> common.DivisionGateContext:
    return common.DivisionGateContext(
        mode="pilot",
        source_root=Path("."),
        selected_seeds=tuple(selected),
        audit=_audit(selected, satisfied=False),
    )


def test_authority_refuses_n19_even_when_audit_claims_satisfied(tmp_path, monkeypatch):
    monkeypatch.setattr(
        common.division_cohort_selector,
        "audit_cohort",
        lambda **_kwargs: _audit(list(range(19)), satisfied=True),
    )
    with pytest.raises(common.DivisionGateRefusalError, match="exactly N=20"):
        common.resolve_gate_context(source_root=tmp_path, mode="authority")


def test_pilot_accepts_n19_but_labels_it_insufficient(tmp_path, monkeypatch):
    monkeypatch.setattr(
        common.division_cohort_selector,
        "audit_cohort",
        lambda **_kwargs: _audit(list(range(19)), satisfied=False),
    )
    context = common.resolve_gate_context(source_root=tmp_path, mode="pilot")
    assert len(context.selected_seeds) == 19
    assert context.cohort_status == "PILOT_INSUFFICIENT_ENSEMBLE"
    assert context.authoritative is False


def test_pilot_output_never_overlaps_authority_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PILOT_ROOT", tmp_path / "pilots")
    path = common.write_pilot_report(process="Cytokinesis", payload={"status": "pilot"})
    assert path == tmp_path / "pilots" / "Cytokinesis" / "pilot_report.json"
    assert "evidence_bundle" not in path.parts
    assert "l2_2_gates" not in path.parts


def test_oracle_paths_are_portable_across_worktrees():
    path = Path(
        "E:/opencell-worktrees/main-integrate/data/m1_sources/karr_native/"
        "dual_division_cohort_current/per_process_traces_v2_event_s000/"
        "Cytokinesis_5000ticks.mat"
    )
    portable = common.portable_oracle_path(path)
    assert portable.startswith("data/m1_sources/karr_native/")


def test_generator_accepts_noncontiguous_selector_owned_completed_seeds():
    entry = l22_catalog.in_scope_processes()["Cytokinesis"]
    selected = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 15, 16, 17, 18, 19, 20, 21, 22]
    manifest = {
        "resolved_seeds": selected,
        "seed_selection": {
            "selector": "division_cohort_selector",
            "required_completed_windows": 20,
            "selected_seeds": selected,
        },
        "inputs": [{"path": "data/m1_sources/karr_native/fake.mat", "sha256": "x"}],
    }
    reasons = l22_generator._check_current_tree_staleness(manifest, entry=entry)
    assert not any("NM_MISMATCH" in reason for reason in reasons)


def test_generator_refuses_selector_manifest_with_only_n19():
    entry = l22_catalog.in_scope_processes()["Cytokinesis"]
    selected = list(range(19))
    manifest = {
        "resolved_seeds": selected,
        "seed_selection": {
            "selector": "division_cohort_selector",
            "required_completed_windows": 20,
            "selected_seeds": selected,
        },
        "inputs": [{"path": "data/m1_sources/karr_native/fake.mat", "sha256": "x"}],
    }
    reasons = l22_generator._check_current_tree_staleness(manifest, entry=entry)
    assert any("NM_MISMATCH" in reason for reason in reasons)


def test_cytokinesis_catalog_preserves_declared_surfaces_and_result_semantics():
    entry = l22_catalog.in_scope_processes()["Cytokinesis"]
    assert entry.primary_channel == "substrates"
    assert {"substrates", "chromosome"} <= set(entry.output_channels)
    assert set(entry.event_channels) == {"pinchedDiameter"}
    assert entry.primary_channel not in entry.event_channels


def test_exact_n20_authority_writes_live_root_only(tmp_path, monkeypatch):
    live_root = tmp_path / "live"
    tracked_root = tmp_path / "tracked"
    monkeypatch.setattr(common.l22_schema, "EVIDENCE_ROOT", live_root)
    monkeypatch.setattr(common.l22_schema, "BUNDLE_ROOT", tracked_root)

    selected = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 15, 16, 17, 18, 19, 20, 21, 22]
    inputs = []
    for seed in selected:
        source = tmp_path / f"seed-{seed}.mat"
        source.write_bytes(f"seed-{seed}".encode())
        inputs.append(
            {
                "kind": "oracle_data",
                "path": f"data/fake/seed-{seed}.mat",
                "_verify_path": str(source),
                "sha256": common.sha256_file(source),
                "seed": seed,
                "n_ticks": 5000,
            }
        )

    output = common.write_authority_bundle(
        process="Cytokinesis",
        harness_type="event_class",
        expected_selected_seeds=tuple(selected),
        result={
            "process": "Cytokinesis",
            "seeds": selected,
            "ticks": 5000,
            "channels": {},
        },
        inputs=inputs,
        thresholds={},
        null_calibration={},
        summary={},
        analytical_check={"applicable": True},
    )
    assert output == live_root / "Cytokinesis" / "latest_event"
    assert not tracked_root.exists()
    manifest = json.loads((output / "input_manifest.json").read_text())
    assert manifest["resolved_seeds"] == selected
    assert manifest["seed_selection"]["selected_seeds"] == selected
    assert all("_verify_path" not in record for record in manifest["inputs"])


def test_authority_writer_refuses_result_seed_drift_from_selector_context():
    selected = tuple(range(20))
    drifted = [*range(19), 99]
    with pytest.raises(common.DivisionGateRefusalError, match="selector-owned context"):
        common.write_authority_bundle(
            process="Cytokinesis",
            harness_type="event_class",
            expected_selected_seeds=selected,
            result={
                "process": "Cytokinesis",
                "seeds": drifted,
                "ticks": 5000,
                "channels": {},
            },
            inputs=[],
            thresholds={},
            null_calibration={},
            summary={},
            analytical_check={"applicable": True},
        )


def test_ftsz_calibration_api_cannot_receive_oc_outcomes():
    signature = inspect.signature(ftsz_gate.calibrate_karr_only)
    assert tuple(signature.parameters) == ("channel", "karr_seed_arrays")
    source = inspect.getsource(ftsz_gate.calibrate_karr_only)
    assert "oc_" not in source.lower()


def test_ftsz_karr_only_calibration_is_deterministic_and_nonzero():
    arrays = tuple(
        np.asarray([[seed, 0.0], [seed + 1.0, (-1.0) ** seed]])
        for seed in range(6)
    )
    first = ftsz_gate.calibrate_karr_only("enzymes", arrays)
    second = ftsz_gate.calibrate_karr_only("enzymes", arrays)
    assert first == second
    assert first.q95_null > 0.0
    assert first.threshold == pytest.approx(3.0 * first.q95_null)
    assert first.seed_count == 6
    assert first.unique_split_count == 3
    assert first.symmetry_collapsed is True
    assert len(first.split_statistics) == 3


def test_ftsz_odd_karr_calibration_keeps_all_rotations():
    arrays = tuple(
        np.asarray([[seed, 0.0], [seed + 1.0, (-1.0) ** seed]])
        for seed in range(5)
    )
    calibration = ftsz_gate.calibrate_karr_only("enzymes", arrays)
    assert calibration.seed_count == 5
    assert calibration.unique_split_count == 5
    assert calibration.symmetry_collapsed is False


def test_ftsz_n20_disclosure_is_five_calibration_splits_ten_evaluation_seeds():
    calibration_half = tuple(
        np.asarray([[seed, 0.0], [seed + 1.0, (-1.0) ** seed]])
        for seed in range(10)
    )
    calibration = ftsz_gate.calibrate_karr_only("enzymes", calibration_half)
    assert calibration.seed_count == 10
    assert calibration.unique_split_count == 5
    assert calibration.symmetry_collapsed is True
    assert 20 - calibration.seed_count == 10


def test_ftsz_support_guard_is_per_active_component():
    karr = np.zeros((40, 3), dtype=float)
    oc = np.zeros((40, 3), dtype=float)
    karr[:, 0] = 1.0
    oc[:, 0] = 1.0
    karr[0, 1] = 1.0
    oc[0, 1] = 1.0

    findings = ftsz_gate._component_support_findings(
        (karr,),
        (oc,),
        wids=("well_supported", "sparse", "jointly_zero"),
    )

    assert findings == [
        {
            "wid": "sparse",
            "karr_nonzero": 1,
            "oc_nonzero": 1,
            "minimum_required_per_side": ftsz_gate.MIN_NONZERO_SAMPLES,
            "reason": "insufficient per-component nonzero support",
        }
    ]


def test_ftsz_sparse_active_component_forces_non_green(monkeypatch):
    selected = list(range(8))

    def fake_surface(*, seed, trace_path, process_factory):
        del process_factory
        karr_enzymes = np.zeros((40, 11), dtype=float)
        karr_enzymes[:, 0] = (np.arange(40) + seed) % 3
        oc_enzymes = karr_enzymes.copy()
        if seed >= 4:
            karr_enzymes[:, 1] = 0.0
            oc_enzymes[:, 1] = 0.0
            karr_enzymes[0, 1] = 1.0
            oc_enzymes[0, 1] = 1.0

        karr_substrates = np.zeros((40, 5), dtype=float)
        karr_substrates[:, 0] = (np.arange(40) + seed) % 3
        return ftsz_gate.SeedSurface(
            seed=seed,
            trace_path=trace_path,
            trace_sha256=f"{seed:064x}",
            karr_enzymes=karr_enzymes,
            oc_enzymes=oc_enzymes,
            karr_substrates=karr_substrates,
            oc_substrates=karr_substrates.copy(),
            karr_activity_ticks=39,
            oc_activity_ticks=39,
            monomer_projection_max_abs_discrepancy=0.0,
            geometry_volume_min_l=1.0,
            geometry_volume_max_l=1.0,
        )

    monkeypatch.setattr(ftsz_gate, "_collect_surface", fake_surface)
    payload = ftsz_gate.build_gate(context=_context(selected))

    failures = payload["result"]["gate_surface"][
        "enzyme_component_support_failures"
    ]
    assert failures[0]["wid"] == "MG_224_MONOMER_GDP"
    assert payload["result"]["channels"]["enzymes"]["w1_oc_vs_karr"] > (
        payload["result"]["channels"]["enzymes"]["threshold"]
    )
    assert payload["analytical_check"]["passed"] is False


def test_ftsz_constant_noop_surface_is_forced_non_green(monkeypatch):
    selected = list(range(8))

    def fake_surface(*, seed, trace_path, process_factory):
        del process_factory
        karr_enzymes = np.zeros((40, 11), dtype=float)
        karr_enzymes[:, 0] = np.arange(40) % (seed + 2)
        karr_enzymes[:, 3] = -karr_enzymes[:, 0] / 2.0
        karr_substrates = np.zeros((40, 5), dtype=float)
        karr_substrates[:, 1] = np.arange(40) % (seed + 3)
        return ftsz_gate.SeedSurface(
            seed=seed,
            trace_path=trace_path,
            trace_sha256=f"{seed:064x}",
            karr_enzymes=karr_enzymes,
            oc_enzymes=np.zeros_like(karr_enzymes),
            karr_substrates=karr_substrates,
            oc_substrates=np.zeros_like(karr_substrates),
            karr_activity_ticks=39,
            oc_activity_ticks=0,
            monomer_projection_max_abs_discrepancy=10.0,
            geometry_volume_min_l=1.0,
            geometry_volume_max_l=1.0,
        )

    monkeypatch.setattr(ftsz_gate, "_collect_surface", fake_surface)
    payload = ftsz_gate.build_gate(context=_context(selected))
    channel = payload["result"]["channels"]["enzymes"]
    assert channel["w1_oc_vs_karr"] > channel["threshold"]
    assert payload["result"]["gate_surface"]["activity_failures"]
    assert payload["analytical_check"]["passed"] is False


def test_ftsz_geometry_volume_replay_input_is_fail_closed():
    base = {
        "enzymes": np.zeros((1, 11), dtype=float),
        "substrates": np.zeros((1, 5), dtype=float),
    }
    missing = WindowGrid(
        process_name="FtsZPolymerization",
        seed=0,
        n_ticks=1,
        tick_offset=0.0,
        trace_path=Path("missing-volume.mat"),
        observables=tuple(base),
        states_before=base,
        states_after=base,
    )
    with pytest.raises(ftsz_gate.FtsZGateError, match="missing required"):
        ftsz_gate._geometry_volume_for_tick(missing, 0)

    with_volume = {
        **base,
        ftsz_gate.GEOMETRY_VOLUME_CHANNEL: np.asarray([[1.2e-17]]),
    }
    changed_after = {
        **with_volume,
        ftsz_gate.GEOMETRY_VOLUME_CHANNEL: np.asarray([[1.3e-17]]),
    }
    changed = WindowGrid(
        process_name="FtsZPolymerization",
        seed=0,
        n_ticks=1,
        tick_offset=0.0,
        trace_path=Path("changed-volume.mat"),
        observables=tuple(with_volume),
        states_before=with_volume,
        states_after=changed_after,
    )
    with pytest.raises(ftsz_gate.FtsZGateError, match="changed geometry_volume"):
        ftsz_gate._geometry_volume_for_tick(changed, 0)


def _synthetic_cyt_grid(seed: int) -> WindowGrid:
    process = KarrCytokinesisProcess({"rng_seed": seed})
    n_ticks = 4
    diameter = np.asarray([2.0e-7, 1.5e-7, 1.0e-7, 5.0e-8])
    after_diameter = np.asarray([1.5e-7, 1.0e-7, 5.0e-8, 0.0])
    num_edges = np.asarray(
        [
            process.calc_num_edges(value, process.default_filament_length_nm)
            for value in diameter
        ],
        dtype=float,
    )
    substrates_before = np.full((n_ticks, 3), 1.0e6)
    substrates_after = substrates_before.copy()
    substrates_after[:, process.substrate_index_water] -= 18.0
    substrates_after[:, process.substrate_index_pi] += 18.0
    substrates_after[:, process.substrate_index_hydrogen] += 18.0
    states_before = {
        "substrates": substrates_before,
        "enzymes": np.full((n_ticks, 4), 100.0),
        "boundEnzymes": np.full((n_ticks, 4), 100.0),
        "pinchedDiameter": diameter.reshape(-1, 1),
        "ftsZRing_numEdgesOneStraight": np.zeros((n_ticks, 1)),
        "ftsZRing_numEdgesTwoStraight": num_edges.reshape(-1, 1),
        "ftsZRing_numEdgesTwoBent": np.zeros((n_ticks, 1)),
        "ftsZRing_numResidualBent": np.zeros((n_ticks, 1)),
        "chromosome_segregated": np.ones((n_ticks, 1)),
    }
    states_after = {
        **states_before,
        "substrates": substrates_after,
        "pinchedDiameter": after_diameter.reshape(-1, 1),
        "ftsZRing_numEdgesTwoStraight": np.zeros((n_ticks, 1)),
        "ftsZRing_numEdgesTwoBent": num_edges.reshape(-1, 1),
    }
    return WindowGrid(
        process_name="Cytokinesis",
        seed=seed,
        n_ticks=n_ticks,
        tick_offset=0.0,
        trace_path=Path(f"seed-{seed}.mat"),
        observables=tuple(states_before),
        states_before=states_before,
        states_after=states_after,
        tick_start=1,
        window_anchor=4,
        onset_tick=1,
    )


def _synthetic_full_replay_grid(seed: int = 7, n_ticks: int = 3) -> WindowGrid:
    process = KarrCytokinesisProcess({"rng_seed": seed})
    substrate_wids = process.fixture_substrate_wids
    enzyme_wids = process.fixture_enzyme_wids
    state = {
        "cell": {
            "division_progress": 0.0,
            "division_complete": False,
        },
        "chromosome": {"segregated": True},
        "geometry": {
            "pinchedDiameter": process.initial_pinched_diameter,
            "pinched": False,
        },
        "ftsZRing": {
            "numEdgesOneStraight": 0,
            "numEdgesTwoStraight": 0,
            "numEdgesTwoBent": 0,
            "numResidualBent": 0,
        },
        "substrates": {wid: 0.0 for wid in substrate_wids},
        "enzymes": {wid: 0.0 for wid in enzyme_wids},
        "boundEnzymes": {wid: 0.0 for wid in enzyme_wids},
        "substrates_allocated": {
            process.name: {
                process.gtp_wid: 0.0,
                process.water_wid: 1_000_000.0,
            }
        },
    }
    state["substrates"][process.water_wid] = 1_000_000.0
    state["enzymes"][
        enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]
    ] = 10_000.0

    fields = (
        "substrates",
        "enzymes",
        "boundEnzymes",
        "pinchedDiameter",
        "ftsZRing_numEdgesOneStraight",
        "ftsZRing_numEdgesTwoStraight",
        "ftsZRing_numEdgesTwoBent",
        "ftsZRing_numResidualBent",
        "chromosome_segregated",
        "randStreamState",
    )
    before_rows = {field: [] for field in fields}
    after_rows = {field: [] for field in fields}

    def vector(port: str, wids: list[str]) -> np.ndarray:
        return np.asarray([state[port][wid] for wid in wids], dtype=float)

    for _ in range(n_ticks):
        before_rows["substrates"].append(vector("substrates", substrate_wids))
        before_rows["enzymes"].append(vector("enzymes", enzyme_wids))
        before_rows["boundEnzymes"].append(vector("boundEnzymes", enzyme_wids))
        before_rows["pinchedDiameter"].append(
            np.asarray([state["geometry"]["pinchedDiameter"]], dtype=float)
        )
        for observable, field_name in (
            ("ftsZRing_numEdgesOneStraight", "numEdgesOneStraight"),
            ("ftsZRing_numEdgesTwoStraight", "numEdgesTwoStraight"),
            ("ftsZRing_numEdgesTwoBent", "numEdgesTwoBent"),
            ("ftsZRing_numResidualBent", "numResidualBent"),
        ):
            before_rows[observable].append(
                np.asarray([state["ftsZRing"][field_name]], dtype=float)
            )
        before_rows["chromosome_segregated"].append(np.asarray([1.0]))
        before_rows["randStreamState"].append(
            np.asarray([process._rng.get_state()], dtype=float)  # noqa: SLF001
        )

        update = process.next_update(1.0, state)
        for port in ("substrates", "enzymes", "boundEnzymes"):
            for wid, delta in update.get(port, {}).items():
                state[port][wid] += float(delta)
        state["geometry"].update(update["geometry"])
        state["ftsZRing"].update(update["ftsZRing"])
        state["cell"].update(
            {
                key: (
                    state["cell"].get(key, 0.0) + value
                    if key == "division_progress"
                    else value
                )
                for key, value in update["cell"].items()
            }
        )

        after_rows["substrates"].append(vector("substrates", substrate_wids))
        after_rows["enzymes"].append(vector("enzymes", enzyme_wids))
        after_rows["boundEnzymes"].append(vector("boundEnzymes", enzyme_wids))
        after_rows["pinchedDiameter"].append(
            np.asarray([state["geometry"]["pinchedDiameter"]], dtype=float)
        )
        for observable, field_name in (
            ("ftsZRing_numEdgesOneStraight", "numEdgesOneStraight"),
            ("ftsZRing_numEdgesTwoStraight", "numEdgesTwoStraight"),
            ("ftsZRing_numEdgesTwoBent", "numEdgesTwoBent"),
            ("ftsZRing_numResidualBent", "numResidualBent"),
        ):
            after_rows[observable].append(
                np.asarray([state["ftsZRing"][field_name]], dtype=float)
            )
        after_rows["chromosome_segregated"].append(np.asarray([1.0]))
        after_rows["randStreamState"].append(
            np.asarray([process._rng.get_state()], dtype=float)  # noqa: SLF001
        )

        state["substrates_allocated"][process.name][process.water_wid] = state[
            "substrates"
        ][process.water_wid]

    return WindowGrid(
        process_name="Cytokinesis",
        seed=seed,
        n_ticks=n_ticks,
        tick_offset=0.0,
        trace_path=Path(f"full-seed-{seed}.mat"),
        observables=fields,
        states_before={
            key: np.stack(value, axis=0) for key, value in before_rows.items()
        },
        states_after={
            key: np.stack(value, axis=0) for key, value in after_rows.items()
        },
        tick_start=1,
        window_anchor=n_ticks,
        onset_tick=1,
    )


def _synthetic_evidence(seed: int, grid: WindowGrid) -> cyt_gate.CytokinesisSeedEvidence:
    return cyt_gate.CytokinesisSeedEvidence(
        seed=seed,
        trace_path=grid.trace_path,
        trace_sha256=f"{seed:064x}",
        onset_offset=0,
        completion_offset=max(0, grid.n_ticks - 1),
        onset_to_completion_ticks=max(0, grid.n_ticks - 1),
        contraction_cycle_count=1,
        source_projection_mismatch_ticks=(),
        water_consumed=0.0,
        phosphate_produced=0.0,
        hydrogen_produced=0.0,
        hydrolysis_stoichiometry_ok=True,
        polymer_payload_redundant=True,
        hydrolysis_tick_count=0,
    )


def _gate_surface(
    *,
    seed: int,
    karr_ticks: tuple[int, ...],
    oc_ticks: tuple[int, ...],
    karr_payloads: tuple[float, ...],
    oc_payloads: tuple[float, ...],
    authority_class: str,
    mismatches: dict[str, int] | None = None,
) -> cyt_gate.CytokinesisProjectionSurface:
    mismatch_counts = {field: 0 for field in cyt_gate.FULL_REPLAY_AUDIT_FIELDS}
    mismatch_counts.update(mismatches or {})
    grid = _synthetic_cyt_grid(seed)
    return cyt_gate.CytokinesisProjectionSurface(
        evidence=_synthetic_evidence(seed, grid),
        karr_event_ticks=karr_ticks,
        oc_event_ticks=(
            oc_ticks if authority_class == "FULL_NEXT_UPDATE_REPLAY_READY" else ()
        ),
        karr_payloads=karr_payloads,
        oc_payloads=oc_payloads,
        oc_payload_ticks=oc_ticks,
        karr_substrate_event_ticks=karr_ticks,
        oc_substrate_event_ticks=(
            oc_ticks if authority_class == "FULL_NEXT_UPDATE_REPLAY_READY" else ()
        ),
        replay_authority_class=authority_class,
        replay_capability_reason=(
            "" if authority_class == "FULL_NEXT_UPDATE_REPLAY_READY" else "missing RNG"
        ),
        full_replay_checked_ticks=(
            grid.n_ticks if authority_class == "FULL_NEXT_UPDATE_REPLAY_READY" else 0
        ),
        full_replay_field_mismatch_counts=mismatch_counts,
        full_replay_first_mismatches=(),
    )


def test_cytokinesis_full_replay_matches_all_captured_fields():
    seed = 7
    grid = _synthetic_full_replay_grid(seed)
    surface = cyt_gate._full_replay_surface(
        row=_synthetic_evidence(seed, grid),
        grid=grid,
        process=KarrCytokinesisProcess({"rng_seed": seed}),
        sut_runner=cyt_gate.DEFAULT_SUT_RUNNER,
    )
    assert surface.full_replay_passed is True
    assert not any(surface.full_replay_field_mismatch_counts.values())


def test_cytokinesis_full_replay_wrong_rng_is_detected():
    seed = 7
    grid = _synthetic_full_replay_grid(seed)

    def wrong_rng_runner(process, states):
        process._rng.set_state(process._rng.get_state() + 1)  # noqa: SLF001
        return process.next_update(1.0, states)

    surface = cyt_gate._full_replay_surface(
        row=_synthetic_evidence(seed, grid),
        grid=grid,
        process=KarrCytokinesisProcess({"rng_seed": seed}),
        sut_runner=wrong_rng_runner,
    )
    assert surface.full_replay_passed is False
    assert surface.full_replay_field_mismatch_counts["randStreamState"] > 0


def test_cytokinesis_full_replay_noop_sut_is_detected():
    seed = 7
    grid = _synthetic_full_replay_grid(seed)
    surface = cyt_gate._full_replay_surface(
        row=_synthetic_evidence(seed, grid),
        grid=grid,
        process=KarrCytokinesisProcess({"rng_seed": seed}),
        sut_runner=lambda _process, _states: {},
    )
    assert surface.full_replay_passed is False
    assert surface.full_replay_field_mismatch_counts["outputContract"] > 0
    assert surface.full_replay_field_mismatch_counts["randStreamState"] > 0


def test_cytokinesis_full_replay_constant_sut_is_detected():
    seed = 7
    grid = _synthetic_full_replay_grid(seed)

    def constant_runner(process, _states):
        return {
            "requests": {
                process.name: {process.gtp_wid: 0.0, process.water_wid: 0.0}
            },
            "geometry": {
                "pinchedDiameter": 0.0,
                "pinched": True,
            },
            "ftsZRing": {
                "numEdges": 0,
                "numEdgesOneStraight": 0,
                "numEdgesTwoStraight": 0,
                "numEdgesTwoBent": 0,
                "numResidualBent": 0,
            },
            "cell": {"division_complete": True},
        }

    surface = cyt_gate._full_replay_surface(
        row=_synthetic_evidence(seed, grid),
        grid=grid,
        process=KarrCytokinesisProcess({"rng_seed": seed}),
        sut_runner=constant_runner,
    )
    assert surface.full_replay_passed is False
    assert surface.full_replay_field_mismatch_counts["pinchedDiameter"] > 0
    assert len(surface.oc_event_ticks) > len(surface.karr_event_ticks)


def test_cytokinesis_full_replay_captured_field_mismatch_is_detected():
    seed = 7
    grid = _synthetic_full_replay_grid(seed)
    mutated_after = dict(grid.states_after)
    mutated_after["enzymes"] = grid.states_after["enzymes"].copy()
    mutated_after["enzymes"][1, 0] += 1.0
    mutated = WindowGrid(
        **{
            **grid.__dict__,
            "states_after": mutated_after,
        }
    )
    surface = cyt_gate._full_replay_surface(
        row=_synthetic_evidence(seed, mutated),
        grid=mutated,
        process=KarrCytokinesisProcess({"rng_seed": seed}),
        sut_runner=cyt_gate.DEFAULT_SUT_RUNNER,
    )
    assert surface.full_replay_passed is False
    assert surface.full_replay_field_mismatch_counts["enzymes"] == 1


def test_cytokinesis_payloads_are_paired_by_seed_and_tick_not_flat_position(
    monkeypatch,
):
    surfaces = {
        seed: _gate_surface(
            seed=seed,
            karr_ticks=(1, 2),
            oc_ticks=(2, 3),
            karr_payloads=(10.0, 20.0),
            oc_payloads=(10.0, 20.0),
            authority_class="CONDITIONAL_PILOT_ONLY",
        )
        for seed in (0, 1)
    }
    monkeypatch.setattr(
        cyt_gate,
        "_evaluate_seed",
        lambda *, seed, **_kwargs: surfaces[seed],
    )
    payload = cyt_gate.build_gate(context=_context([0, 1]), workers=1)
    pinched = payload["result"]["channels"]["pinchedDiameter"]
    assert pinched["w1_oc_vs_karr"] == 6.0
    assert pinched["threshold"] == 0.0
    assert len(pinched["payload"]["mismatches_paired_by_seed_tick"]) == 6


def test_cytokinesis_one_payload_mismatch_fails_exact_threshold(monkeypatch):
    surfaces = {
        0: _gate_surface(
            seed=0,
            karr_ticks=(1,),
            oc_ticks=(1,),
            karr_payloads=(0.0,),
            oc_payloads=(1.0,),
            authority_class="CONDITIONAL_PILOT_ONLY",
        ),
        1: _gate_surface(
            seed=1,
            karr_ticks=(1,),
            oc_ticks=(1,),
            karr_payloads=(0.0,),
            oc_payloads=(0.0,),
            authority_class="CONDITIONAL_PILOT_ONLY",
        ),
    }
    monkeypatch.setattr(
        cyt_gate,
        "_evaluate_seed",
        lambda *, seed, **_kwargs: surfaces[seed],
    )
    payload = cyt_gate.build_gate(context=_context([0, 1]), workers=1)
    pinched = payload["result"]["channels"]["pinchedDiameter"]
    assert pinched["w1_oc_vs_karr"] == 1.0
    assert pinched["threshold"] == 0.0
    assert pinched["w1_oc_vs_karr"] > pinched["threshold"]


def test_cytokinesis_conditional_pilot_is_forced_non_green(monkeypatch):
    surfaces = {
        seed: _gate_surface(
            seed=seed,
            karr_ticks=(1,),
            oc_ticks=(1,),
            karr_payloads=(0.0,),
            oc_payloads=(0.0,),
            authority_class="CONDITIONAL_PILOT_ONLY",
        )
        for seed in (0, 1)
    }
    monkeypatch.setattr(
        cyt_gate,
        "_evaluate_seed",
        lambda *, seed, **_kwargs: surfaces[seed],
    )
    payload = cyt_gate.build_gate(context=_context([0, 1]), workers=1)
    primary = payload["result"]["channels"]["substrates"]
    assert primary["is_primary"] is True
    assert primary["w1_oc_vs_karr"] > primary["threshold"]
    pinched = payload["result"]["channels"]["pinchedDiameter"]
    assert pinched["w1_oc_vs_karr"] > pinched["threshold"]
    timing = payload["result"]["channels"]["onset_to_completion_timing"]
    assert timing["payload"]["onset_to_completion_oc"] is None
    assert payload["summary"]["oc_completed_seed_count"] is None
    assert payload["analytical_check"]["passed"] is False
    assert payload["analytical_check"]["sut_evaluated"] is False


def test_cytokinesis_analytical_check_fails_injected_full_replay_sut(
    monkeypatch,
):
    surfaces = {
        seed: _gate_surface(
            seed=seed,
            karr_ticks=(1,),
            oc_ticks=(1,),
            karr_payloads=(0.0,),
            oc_payloads=(0.0,),
            authority_class="FULL_NEXT_UPDATE_REPLAY_READY",
            mismatches={"enzymes": 1},
        )
        for seed in (0, 1)
    }
    monkeypatch.setattr(
        cyt_gate,
        "_evaluate_seed",
        lambda *, seed, **_kwargs: surfaces[seed],
    )
    payload = cyt_gate.build_gate(context=_context([0, 1]), workers=1)
    assert payload["result"]["channels"]["substrates"]["w1_oc_vs_karr"] == 2.0
    assert payload["analytical_check"]["passed"] is False
    assert payload["analytical_check"]["sut_evaluated"] is True


@pytest.mark.parametrize("mismatch_field", cyt_gate.FULL_REPLAY_AUDIT_FIELDS)
def test_each_full_replay_mismatch_is_mechanically_non_green(
    monkeypatch,
    mismatch_field,
):
    selected = list(range(20))
    surfaces = {
        seed: _gate_surface(
            seed=seed,
            karr_ticks=(1, 2),
            oc_ticks=(1, 2),
            karr_payloads=(10.0, 0.0),
            oc_payloads=(10.0, 0.0),
            authority_class="FULL_NEXT_UPDATE_REPLAY_READY",
            mismatches={mismatch_field: 1} if seed == 0 else None,
        )
        for seed in selected
    }
    monkeypatch.setattr(
        cyt_gate,
        "_evaluate_seed",
        lambda *, seed, **_kwargs: surfaces[seed],
    )
    payload = cyt_gate.build_gate(context=_context(selected), workers=1)
    entry = l22_catalog.in_scope_processes()["Cytokinesis"]
    verdict = l22_verdict.rederive_process(
        "Cytokinesis",
        entry,
        payload["result"],
    )
    assert verdict.mechanical_verdict != "PASS", (
        mismatch_field,
        verdict.channel_verdicts,
        verdict.reasons,
    )
    assert mismatch_field in payload["thresholds"]["channels"]


def test_shifted_full_replay_timeline_is_not_hidden_by_karr_noise_floor(
    monkeypatch,
):
    selected = list(range(20))
    surfaces = {
        seed: _gate_surface(
            seed=seed,
            karr_ticks=(1, 2),
            oc_ticks=((2, 3) if seed == 0 else (1, 2)),
            karr_payloads=(10.0, 0.0),
            oc_payloads=(10.0, 0.0),
            authority_class="FULL_NEXT_UPDATE_REPLAY_READY",
        )
        for seed in selected
    }
    monkeypatch.setattr(
        cyt_gate,
        "_evaluate_seed",
        lambda *, seed, **_kwargs: surfaces[seed],
    )
    payload = cyt_gate.build_gate(context=_context(selected), workers=1)
    timing = payload["result"]["channels"]["onset_to_completion_timing"]
    assert timing["w1_oc_vs_karr"] == 2.0
    assert timing["threshold"] == 0.0
    assert timing["q95_null"] == 0.0
    verdict = l22_verdict.rederive_process(
        "Cytokinesis",
        l22_catalog.in_scope_processes()["Cytokinesis"],
        payload["result"],
    )
    assert verdict.channel_verdicts["onset_to_completion_timing"] not in {
        "SEED_NOISE",
        "PASS",
    }
    assert verdict.mechanical_verdict != "PASS"


def test_cytokinesis_noop_sut_loses_event_and_payload(monkeypatch):
    selected = [0, 1, 2, 3]
    grids = {seed: _synthetic_cyt_grid(seed) for seed in selected}

    monkeypatch.setattr(
        cyt_gate,
        "load_event_window",
        lambda path, **_kwargs: grids[int(path.parent.name[-3:])],
    )
    monkeypatch.setattr(
        cyt_gate,
        "analyze_seed",
        lambda seed, grid: cyt_gate.CytokinesisSeedEvidence(
            seed=seed,
            trace_path=grid.trace_path,
            trace_sha256=f"{seed:064x}",
            onset_offset=0,
            completion_offset=3,
            onset_to_completion_ticks=3 + seed,
            contraction_cycle_count=4,
            source_projection_mismatch_ticks=(),
            water_consumed=72.0 + seed,
            phosphate_produced=72.0 + seed,
            hydrogen_produced=72.0 + seed,
            hydrolysis_stoichiometry_ok=True,
            polymer_payload_redundant=True,
            hydrolysis_tick_count=10,
        ),
    )
    payload = cyt_gate.build_gate(
        context=_context(selected),
        sut_projector=lambda diameter, _filament_length: diameter,
    )
    primary = payload["result"]["channels"]["pinchedDiameter"]
    assert primary["w1_oc_vs_karr"] > primary["threshold"]
    assert payload["result"]["channels"]["contraction_event_count"]["w1_oc_vs_karr"] > 0
    assert payload["summary"]["oc_completed_seed_count"] is None


def test_cytokinesis_duplicate_completion_semantics_are_rejected():
    with pytest.raises(Exception, match="single_firing semantics"):
        cyt_gate.find_completion_tick(
            [2.0e-7, 1.5e-7, 1.0e-7, 5.0e-8],
            [0.0, 0.0, 5.0e-8, 0.0],
        )
