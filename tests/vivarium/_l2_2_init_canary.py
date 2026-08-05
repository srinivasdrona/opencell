"""L2.2 init canary for fitted-init injection + substrate WID intersection."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    ChannelSpec,
    build_state_template,
    cell_vector,
    load_fitted_init_from_mat,
    load_fixture_channel_wids,
    overlay_observable_into_state,
    project_observable_from_state,
    project_pair_to_wid_intersection,
    refresh_allocator_views,
    wasserstein_over_wid_intersection,
)

from opencell.vivarium.karr_transcription import KarrTranscriptionProcess  # noqa: E402
from opencell.vivarium.karr_translation import KarrTranslationProcess  # noqa: E402

N_TICKS_DEFAULT = 100
TICK_SAMPLES = (0, 1, 5, 25, 50, 75, 99)
FITTED_CHANNELS = ("substrates", "enzymes", "boundEnzymes")

_TRANSLATION_MAT_ROOT = Path(
    "/mnt/e/opencell-worktrees/l22-translation/data/m1_sources/karr_native/ensembles/translation"
)
_TRANSCRIPTION_MAT_PATH = Path(
    "/mnt/e/opencell-worktrees/l2-matlab-reextract/data/m1_sources/karr_native/per_process_traces/Transcription_100ticks.mat"
)


@dataclass(frozen=True)
class ProcessCanarySpec:
    process_name: str
    process_factory: Callable[[int], Any]
    mat_path_factory: Callable[[int], Path]
    observables: tuple[str, ...]
    output_path: Path
    min_init_ratio_terminal: dict[str, float]
    cold_baseline_path: Path | None = None


def _translation_mat_path(seed: int) -> Path:
    return _TRANSLATION_MAT_ROOT / f"seed_{seed:03d}" / "Translation_100ticks.mat"


def _transcription_mat_path(seed: int) -> Path:
    del seed
    return _TRANSCRIPTION_MAT_PATH


PROCESS_SPECS: dict[str, ProcessCanarySpec] = {
    "Translation": ProcessCanarySpec(
        process_name="Translation",
        process_factory=lambda seed: KarrTranslationProcess({"rng_seed": int(seed)}),
        mat_path_factory=_translation_mat_path,
        observables=("substrates", "enzymes", "boundEnzymes", "monomers"),
        output_path=Path("data") / "init_canary" / "translation_seed000.json",
        min_init_ratio_terminal={"enzymes": 0.95, "boundEnzymes": 0.95},
        cold_baseline_path=Path("data") / "init_canary" / "translation_seed000.json",
    ),
    "Transcription": ProcessCanarySpec(
        process_name="Transcription",
        process_factory=lambda seed: KarrTranscriptionProcess({"rng_seed": int(seed)}),
        mat_path_factory=_transcription_mat_path,
        observables=("substrates", "enzymes", "boundEnzymes"),
        output_path=Path("data") / "init_canary" / "transcription_seed000.json",
        min_init_ratio_terminal={"enzymes": 0.90},
    ),
}


def _observable_wids(process: Any, observables: tuple[str, ...]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for obs in observables:
        if obs == "substrates":
            if hasattr(process, "allocation_substrate_wids"):
                out[obs] = [str(x) for x in process.allocation_substrate_wids]
            elif hasattr(process, "substrate_wids"):
                out[obs] = [str(x) for x in process.substrate_wids]
            elif hasattr(process, "aa_ids"):
                out[obs] = [str(x) for x in process.aa_ids]
            elif hasattr(process, "consumed_substrates"):
                out[obs] = [str(x) for x in process.consumed_substrates]
            elif hasattr(process, "_substrate_wids"):
                out[obs] = [str(x) for x in process._substrate_wids]
            else:
                out[obs] = []
        elif obs in {"enzymes", "boundEnzymes"}:
            if hasattr(process, "enzyme_wids"):
                out[obs] = [str(x) for x in process.enzyme_wids]
            elif hasattr(process, "fixture_enzyme_wids"):
                out[obs] = [str(x) for x in process.fixture_enzyme_wids]
            else:
                out[obs] = []
        elif obs == "monomers":
            if hasattr(process, "protein_ids"):
                out[obs] = [str(x) for x in process.protein_ids]
            elif hasattr(process, "protein_wids"):
                out[obs] = [str(x) for x in process.protein_wids]
            else:
                out[obs] = []
        else:
            out[obs] = []
    return out


def _load_karr_trajectory(spec: ProcessCanarySpec, seed: int) -> tuple[int, dict[str, np.ndarray]]:
    path = spec.mat_path_factory(seed)
    out: dict[str, np.ndarray] = {}
    with h5py.File(path, "r") as handle:
        n_ticks = N_TICKS_DEFAULT
        if "metadata" in handle and "n_ticks" in handle["metadata"]:
            n_ticks = int(np.asarray(handle["metadata/n_ticks"][()]).reshape(-1)[0])
        for obs in spec.observables:
            rows = [cell_vector(handle, "states_after", obs, tick) for tick in range(n_ticks)]
            out[obs] = np.vstack(rows)
    return n_ticks, out


def _accumulate_leaf(state: dict[str, Any], channel: str, deltas: dict[str, Any]) -> None:
    channel_state = state.setdefault(channel, {})
    for wid, delta in deltas.items():
        wid_s = str(wid)
        channel_state[wid_s] = float(channel_state.get(wid_s, 0.0)) + float(delta)


def _apply_translation_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    protein_update = update.get("protein", {})
    if isinstance(protein_update, dict):
        counts_update = protein_update.get("counts")
        if isinstance(counts_update, dict):
            protein_state = state.setdefault("protein", {})
            counts_state = protein_state.setdefault("counts", {})
            for wid, val in counts_update.items():
                counts_state[str(wid)] = float(val)
    sub_update = update.get("substrates")
    if isinstance(sub_update, dict):
        _accumulate_leaf(state, "substrates", sub_update)


def _apply_transcription_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    rna_update = update.get("rna", {})
    if isinstance(rna_update, dict):
        counts_update = rna_update.get("counts")
        if isinstance(counts_update, dict):
            rna_state = state.setdefault("rna", {})
            counts_state = rna_state.setdefault("counts", {})
            for wid, val in counts_update.items():
                counts_state[str(wid)] = float(val)

    for channel in ("substrates", "enzymes", "boundEnzymes"):
        channel_update = update.get(channel)
        if isinstance(channel_update, dict):
            _accumulate_leaf(state, channel, channel_update)


def _apply_process_update(process_name: str, state: dict[str, Any], update: dict[str, Any]) -> None:
    if process_name == "Translation":
        _apply_translation_update(state, update)
        return
    if process_name == "Transcription":
        _apply_transcription_update(state, update)
        return
    raise ValueError(f"Unsupported canary process update applier: {process_name}")


def _build_fitted_channel_map(
    spec: ProcessCanarySpec,
    oc_wids_by_observable: dict[str, list[str]],
) -> dict[str, ChannelSpec]:
    channel_map: dict[str, ChannelSpec] = {}
    for channel in FITTED_CHANNELS:
        oc_wids = tuple(oc_wids_by_observable.get(channel, ()))
        if not oc_wids:
            continue
        karr_wids = load_fixture_channel_wids(spec.process_name, channel)
        if not karr_wids:
            karr_wids = oc_wids
        channel_map[channel] = ChannelSpec(
            karr_field=channel,
            karr_wids=tuple(karr_wids),
            oc_wids=tuple(oc_wids),
        )
    return channel_map


def _run_oc_trajectory(
    *,
    spec: ProcessCanarySpec,
    seed: int,
    n_ticks: int,
    fitted_init: dict[str, np.ndarray] | None = None,
) -> tuple[dict[str, list[str]], dict[str, np.ndarray]]:
    process = spec.process_factory(seed)
    state = build_state_template(process)
    wids = _observable_wids(process, spec.observables)

    if fitted_init is not None:
        for channel, vec in fitted_init.items():
            if channel not in wids:
                continue
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=channel,
                vector=np.asarray(vec, dtype=np.float64).reshape(-1),
                wids=wids[channel],
            )

    trajectories = {
        obs: np.zeros((n_ticks, len(wids.get(obs, ()))), dtype=np.float64)
        for obs in spec.observables
    }

    for tick in range(n_ticks):
        refresh_allocator_views(process, state)
        update = process.next_update(1.0, state)
        _apply_process_update(spec.process_name, state, update)
        for obs in spec.observables:
            vec = project_observable_from_state(
                process=process,
                state=state,
                observable=obs,
                wids=wids[obs],
                bound_enzymes_before=None,
            )
            trajectories[obs][tick, :] = np.asarray(vec, dtype=np.float64).reshape(-1)
    return wids, trajectories


def _summary_rows(
    *,
    spec: ProcessCanarySpec,
    n_ticks: int,
    karr: dict[str, np.ndarray],
    oc_cold: dict[str, np.ndarray],
    oc_fitted: dict[str, np.ndarray],
    channel_map: dict[str, ChannelSpec],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ticks = tuple(t for t in TICK_SAMPLES if t < n_ticks)
    for obs in spec.observables:
        k_mat = karr[obs]
        c_mat = oc_cold[obs]
        f_mat = oc_fitted[obs]
        for tick in ticks:
            if obs in channel_map:
                channel = channel_map[obs]
                proj_c = project_pair_to_wid_intersection(
                    karr_vector=k_mat[tick, :],
                    oc_vector=c_mat[tick, :],
                    karr_wids=channel.karr_wids,
                    oc_wids=channel.oc_wids,
                )
                proj_f = project_pair_to_wid_intersection(
                    karr_vector=k_mat[tick, :],
                    oc_vector=f_mat[tick, :],
                    karr_wids=channel.karr_wids,
                    oc_wids=channel.oc_wids,
                )
                k_vec = proj_c.karr_projected
                c_vec = proj_c.oc_projected
                f_vec = proj_f.oc_projected
            else:
                n = min(k_mat.shape[1], c_mat.shape[1], f_mat.shape[1])
                k_vec = k_mat[tick, :n]
                c_vec = c_mat[tick, :n]
                f_vec = f_mat[tick, :n]

            k_sum = float(np.sum(k_vec))
            c_sum = float(np.sum(c_vec))
            f_sum = float(np.sum(f_vec))
            cold_gap = float(abs(c_sum - k_sum))
            fitted_gap = float(abs(f_sum - k_sum))
            init_contribution = float(cold_gap - fitted_gap)
            init_ratio = 0.0 if cold_gap == 0.0 else float(init_contribution / cold_gap)
            rows.append(
                {
                    "observable": obs,
                    "tick": int(tick),
                    "karr_sum": k_sum,
                    "cold_sum": c_sum,
                    "fitted_sum": f_sum,
                    "cold_sum_absdiff": cold_gap,
                    "fitted_sum_absdiff": fitted_gap,
                    "cold_max_elem_absdiff": float(np.max(np.abs(c_vec - k_vec))),
                    "fitted_max_elem_absdiff": float(np.max(np.abs(f_vec - k_vec))),
                    "init_contribution_sum": init_contribution,
                    "init_contribution_ratio": init_ratio,
                }
            )
    return rows


def _substrate_projection_metrics(
    *,
    n_ticks: int,
    karr_sub: np.ndarray,
    oc_cold_sub: np.ndarray,
    oc_fitted_sub: np.ndarray,
    channel_spec: ChannelSpec,
) -> dict[str, Any]:
    tick_w1_cold: list[float] = []
    tick_w1_fitted: list[float] = []
    tick0_projection = None
    for tick in range(n_ticks):
        w1_cold, proj_cold = wasserstein_over_wid_intersection(
            karr_vector=karr_sub[tick, :],
            oc_vector=oc_cold_sub[tick, :],
            karr_wids=channel_spec.karr_wids,
            oc_wids=channel_spec.oc_wids,
        )
        w1_fitted, proj_fitted = wasserstein_over_wid_intersection(
            karr_vector=karr_sub[tick, :],
            oc_vector=oc_fitted_sub[tick, :],
            karr_wids=channel_spec.karr_wids,
            oc_wids=channel_spec.oc_wids,
        )
        tick_w1_cold.append(float(w1_cold))
        tick_w1_fitted.append(float(w1_fitted))
        if tick == 0:
            tick0_projection = proj_cold
            assert proj_cold.intersection_wids == proj_fitted.intersection_wids

    if tick0_projection is None:
        raise RuntimeError("No tick-0 projection computed for substrates")

    return {
        "tick0_w1_cold": float(tick_w1_cold[0]),
        "tick0_w1_fitted": float(tick_w1_fitted[0]),
        "tick_w1_cold": tick_w1_cold,
        "tick_w1_fitted": tick_w1_fitted,
        "intersection_wids": list(tick0_projection.intersection_wids),
        "dropped_karr_wids": list(tick0_projection.dropped_karr_wids),
        "dropped_oc_wids": list(tick0_projection.dropped_oc_wids),
    }


def _init_ratio_at_tick(rows: list[dict[str, Any]], observable: str, tick: int) -> float:
    for row in rows:
        if row["observable"] == observable and int(row["tick"]) == int(tick):
            return float(row["init_contribution_ratio"])
    raise KeyError(f"missing row for observable={observable}, tick={tick}")


def run_canary(
    *,
    process_name: str,
    seed: int,
    out_path: Path | None = None,
) -> dict[str, Any]:
    if process_name not in PROCESS_SPECS:
        raise KeyError(f"unsupported process canary: {process_name}")
    spec = PROCESS_SPECS[process_name]
    n_ticks, karr = _load_karr_trajectory(spec, seed)

    process_probe = spec.process_factory(seed)
    oc_wids = _observable_wids(process_probe, spec.observables)
    channel_map = _build_fitted_channel_map(spec, oc_wids)

    fitted_init = load_fitted_init_from_mat(
        spec.mat_path_factory(seed),
        channel_map,
    )

    _, oc_cold = _run_oc_trajectory(
        spec=spec,
        seed=seed,
        n_ticks=n_ticks,
        fitted_init=None,
    )
    _, oc_fitted = _run_oc_trajectory(
        spec=spec,
        seed=seed,
        n_ticks=n_ticks,
        fitted_init=fitted_init,
    )

    rows = _summary_rows(
        spec=spec,
        n_ticks=n_ticks,
        karr=karr,
        oc_cold=oc_cold,
        oc_fitted=oc_fitted,
        channel_map=channel_map,
    )
    terminal_tick = n_ticks - 1
    substrate_metrics = _substrate_projection_metrics(
        n_ticks=n_ticks,
        karr_sub=karr["substrates"],
        oc_cold_sub=oc_cold["substrates"],
        oc_fitted_sub=oc_fitted["substrates"],
        channel_spec=channel_map["substrates"],
    )
    init_ratio_terminal = {
        obs: _init_ratio_at_tick(rows, obs, terminal_tick)
        for obs in spec.min_init_ratio_terminal
    }

    payload = {
        "process": process_name,
        "seed": int(seed),
        "n_ticks": int(n_ticks),
        "tick_samples": [int(t) for t in TICK_SAMPLES if t < n_ticks],
        "observables": list(spec.observables),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "rows": rows,
        "fitted_channel_map": {
            ch: {
                "karr_field": channel_map[ch].karr_field,
                "karr_wids": list(channel_map[ch].karr_wids),
                "oc_wids": list(channel_map[ch].oc_wids),
            }
            for ch in channel_map
        },
        "substrate_projection": substrate_metrics,
        "acceptance": {
            "terminal_tick": int(terminal_tick),
            "min_init_ratio_terminal": spec.min_init_ratio_terminal,
            "init_ratio_terminal": init_ratio_terminal,
        },
    }

    target = out_path or spec.output_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _assert_translation_cold_baseline_stable(payload: dict[str, Any]) -> None:
    baseline_path = PROCESS_SPECS["Translation"].cold_baseline_path
    if baseline_path is None or not baseline_path.exists():
        return
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_rows = {
        (row["observable"], int(row["tick"])): float(row["cold_sum"])
        for row in baseline.get("rows", [])
    }
    new_rows = {
        (row["observable"], int(row["tick"])): float(row["cold_sum"])
        for row in payload.get("rows", [])
    }
    for key, expected in baseline_rows.items():
        assert key in new_rows, f"missing cold row in new payload: {key}"
        got = new_rows[key]
        assert got == pytest.approx(expected, rel=0.0, abs=0.0), (
            f"cold-start drift changed for {key}: expected={expected} got={got}"
        )


@pytest.mark.parametrize("process_name", ["Translation", "Transcription"])
def test_l2_2_init_canary(process_name: str, tmp_path: Path) -> None:
    spec = PROCESS_SPECS[process_name]
    out_path = spec.output_path if process_name == "Transcription" else tmp_path / "translation_seed000.json"
    payload = run_canary(process_name=process_name, seed=0, out_path=out_path)

    for obs, threshold in spec.min_init_ratio_terminal.items():
        observed = float(payload["acceptance"]["init_ratio_terminal"][obs])
        assert observed >= float(threshold), (
            f"fitted-init contribution below threshold: process={process_name} "
            f"observable={obs} observed={observed:.3f} threshold={threshold:.3f}"
        )

    substrate_projection = payload["substrate_projection"]
    assert np.isfinite(float(substrate_projection["tick0_w1_cold"]))
    assert np.isfinite(float(substrate_projection["tick0_w1_fitted"]))

    if process_name == "Translation":
        _assert_translation_cold_baseline_stable(payload)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--process", choices=sorted(PROCESS_SPECS.keys()), default="Translation")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    payload = run_canary(process_name=args.process, seed=args.seed, out_path=args.out)

    print(
        f"[canary] process={payload['process']} seed={payload['seed']} "
        f"tick0_w1_cold={payload['substrate_projection']['tick0_w1_cold']:.6g} "
        f"tick0_w1_fitted={payload['substrate_projection']['tick0_w1_fitted']:.6g}",
        flush=True,
    )
    tick = int(payload["acceptance"]["terminal_tick"])
    for obs, ratio in payload["acceptance"]["init_ratio_terminal"].items():
        thresh = payload["acceptance"]["min_init_ratio_terminal"][obs]
        print(
            f"[canary] tick{tick} init ratio {obs}: {ratio:.3f} (threshold {thresh:.3f})",
            flush=True,
        )
    print(f"[canary] wrote {args.out or PROCESS_SPECS[args.process].output_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
