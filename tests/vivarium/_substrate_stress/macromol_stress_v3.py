from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.vivarium.karr_macromolecular_complexation import MacromolecularComplexationProcess
from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers

ALPHAS = (1.0, 0.5, 0.1, 0.05, 0.01)
N_SEEDS = 5
PASS_MEAN_W1 = 0.5
PASS_MAX_W1 = 2.0
PASS_EVENT_REL_DIFF = 0.10
_TRACE_ROOT_CANDIDATES = (
    _REPO_ROOT / "data" / "m1_sources" / "karr_native",
    Path("E:/opencell/data/m1_sources/karr_native"),
    Path("/mnt/e/opencell/data/m1_sources/karr_native"),
)
_MONOMER_STORE_PATH_OVERRIDE = {"monomers": ("substrates",)}


def _seed_paths() -> list[Path]:
    paths: list[Path] = []
    for seed in range(N_SEEDS):
        rel = Path(f"per_process_traces_v2_s{seed:03d}") / "MacromolecularComplexation_100ticks.mat"
        for root in _TRACE_ROOT_CANDIDATES:
            candidate = root / rel
            if candidate.exists():
                paths.append(candidate)
                break
        else:
            raise FileNotFoundError(f"Missing v2 trace for seed s{seed:03d}: {rel}")
    return paths


def _load_trace() -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, list[str]]:
    before, after, _ = runner_helpers._load_seeded_mat_channels(_seed_paths())
    required = ("substrates", "complexs")
    missing = [name for name in required if name not in before]
    if missing:
        raise KeyError(f"Missing states_before channels: {missing}")
    if "complexs" not in after:
        raise KeyError("Missing states_after.complexs")
    metadata = runner_helpers._macromol_channel_metadata()
    monomer_indices = np.asarray(metadata["monomer_indices"], dtype=np.int64)
    monomer_wids = list(metadata["monomer_wids"])
    return before, np.asarray(after["complexs"], dtype=np.float64), monomer_indices, monomer_wids


def _scale_substrates(substrates: np.ndarray, alpha: float) -> np.ndarray:
    scaled = np.floor(np.clip(np.asarray(substrates, dtype=np.float64), a_min=0.0, a_max=None) * alpha)
    return np.asarray(scaled, dtype=np.float64)


def _complex_events(before_complexs: np.ndarray, after_complexs: np.ndarray) -> int:
    delta = np.asarray(after_complexs, dtype=np.float64) - np.asarray(before_complexs, dtype=np.float64)
    return int(round(float(np.sum(delta))))


def _event_rel_diff(total_oc_events: int, total_karr_events: int) -> float:
    return abs(total_oc_events - total_karr_events) / max(1, total_karr_events)


def _run_oc_tick(
    seed: int,
    tick: int,
    before: dict[str, np.ndarray],
    alpha: float,
    monomer_indices: np.ndarray,
    monomer_wids: list[str],
) -> np.ndarray:
    scaled_substrates = _scale_substrates(before["substrates"][seed, tick], alpha)
    complexs_before = np.asarray(before["complexs"][seed, tick], dtype=np.float64)
    process = MacromolecularComplexationProcess({"rng_seed": int(runner_helpers._sample_seed(seed, tick))})
    runtime_state = runner_helpers.build_state_template(process)
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=scaled_substrates,
        wids=list(process.substrate_wids),
    )
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="monomers",
        vector=scaled_substrates[monomer_indices],
        wids=monomer_wids,
        store_path_override=_MONOMER_STORE_PATH_OVERRIDE,
    )
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="complexs",
        vector=complexs_before,
        wids=list(process.complex_wids),
    )
    runner_helpers.refresh_allocator_views(process, runtime_state)
    with runner_helpers.forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    runner_helpers.apply_count_update(runtime_state, update)
    return np.asarray(
        runner_helpers.project_observable_from_state(
            process=process,
            state=runtime_state,
            observable="complexs",
            wids=list(process.complex_wids),
            bound_enzymes_before=None,
        ),
        dtype=np.float64,
    )


def _run_alpha(
    alpha: float,
    before: dict[str, np.ndarray],
    karr_after_complexs: np.ndarray,
    monomer_indices: np.ndarray,
    monomer_wids: list[str],
) -> dict[str, object]:
    w1_values: list[float] = []
    total_oc_events = 0
    total_karr_events = 0
    _, n_ticks, _ = before["complexs"].shape
    for seed in range(N_SEEDS):
        for tick in range(n_ticks):
            complexs_before = np.asarray(before["complexs"][seed, tick], dtype=np.float64)
            oc_after = _run_oc_tick(
                seed=seed,
                tick=tick,
                before=before,
                alpha=alpha,
                monomer_indices=monomer_indices,
                monomer_wids=monomer_wids,
            )
            karr_after = np.asarray(karr_after_complexs[seed, tick], dtype=np.float64)
            if oc_after.shape != karr_after.shape:
                raise ValueError(
                    f"complexs shape mismatch at seed={seed} tick={tick}: "
                    f"oc={oc_after.shape} karr={karr_after.shape}"
                )
            w1_values.append(runner_helpers.compute_w1(oc_after, karr_after))
            total_oc_events += _complex_events(complexs_before, oc_after)
            total_karr_events += _complex_events(complexs_before, karr_after)
    mean_w1 = float(np.mean(w1_values))
    max_w1 = float(np.max(w1_values))
    event_rel_diff = _event_rel_diff(total_oc_events, total_karr_events)
    subgate_a_pass = mean_w1 < PASS_MEAN_W1 and max_w1 < PASS_MAX_W1
    subgate_b_pass = event_rel_diff < PASS_EVENT_REL_DIFF
    verdict = "PASS" if subgate_a_pass and subgate_b_pass else "FAIL"
    return {
        "alpha": alpha,
        "per_tick_W1_mean": mean_w1,
        "per_tick_W1_max": max_w1,
        "total_oc_events": total_oc_events,
        "total_karr_events": total_karr_events,
        "event_rel_diff": event_rel_diff,
        "subgate_a": "PASS" if subgate_a_pass else "FAIL",
        "subgate_b": "PASS" if subgate_b_pass else "FAIL",
        "verdict": verdict,
    }


def main() -> int:
    before, karr_after_complexs, monomer_indices, monomer_wids = _load_trace()
    rows = [
        _run_alpha(alpha, before, karr_after_complexs, monomer_indices, monomer_wids)
        for alpha in ALPHAS
    ]
    print(
        "alpha | per_tick_W1_mean | per_tick_W1_max | total_oc_events | "
        "total_karr_events | event_rel_diff | subgate_a | subgate_b | verdict"
    )
    for row in rows:
        print(
            f"{row['alpha']:.2f} | "
            f"{row['per_tick_W1_mean']:.6f} | "
            f"{row['per_tick_W1_max']:.6f} | "
            f"{row['total_oc_events']} | "
            f"{row['total_karr_events']} | "
            f"{row['event_rel_diff']:.6f} | "
            f"{row['subgate_a']} | "
            f"{row['subgate_b']} | "
            f"{row['verdict']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
