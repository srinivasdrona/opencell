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
        )

    monkeypatch.setattr(ftsz_gate, "_collect_surface", fake_surface)
    payload = ftsz_gate.build_gate(context=_context(selected))
    channel = payload["result"]["channels"]["enzymes"]
    assert channel["w1_oc_vs_karr"] > channel["threshold"]
    assert payload["result"]["gate_surface"]["activity_failures"]
    assert payload["analytical_check"]["passed"] is False


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
    assert payload["summary"]["oc_completed_seed_count"] == 0


def test_cytokinesis_duplicate_completion_semantics_are_rejected():
    with pytest.raises(Exception, match="single_firing semantics"):
        cyt_gate.find_completion_tick(
            [2.0e-7, 1.5e-7, 1.0e-7, 5.0e-8],
            [0.0, 0.0, 5.0e-8, 0.0],
        )
