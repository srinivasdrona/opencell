from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers

PROCESS_NAME = "tRNAAminoacylation"
ALPHAS = (1.0, 0.5, 0.1, 0.05, 0.01)
N_SEEDS = 5
PASS_MEAN_W1 = 0.5
PASS_MAX_W1 = 2.0


def _seed_paths() -> list[Path]:
    return [runner_helpers._v2_seed_mat_path(PROCESS_NAME, seed) for seed in range(N_SEEDS)]


def _load_trace() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    before, after, _ = runner_helpers._load_seeded_mat_channels(_seed_paths())
    required = ("substrates", "enzymes", "boundEnzymes", "freeRNAs", "aminoacylatedRNAs")
    missing_before = [name for name in required if name not in before]
    missing_after = [name for name in required if name not in after]
    if missing_before:
        raise KeyError(f"Missing states_before channels: {missing_before}")
    if missing_after:
        raise KeyError(f"Missing states_after channels: {missing_after}")
    return before, after


def _scale_substrates(substrates: np.ndarray, alpha: float) -> np.ndarray:
    scaled = np.floor(np.clip(np.asarray(substrates, dtype=np.float64), a_min=0.0, a_max=None) * alpha)
    return np.asarray(scaled, dtype=np.float64)


def _concat_rnas(free_rna: np.ndarray, aminoacylated_rna: np.ndarray) -> np.ndarray:
    return np.asarray(
        np.concatenate(
            [
                np.asarray(free_rna, dtype=np.float64),
                np.asarray(aminoacylated_rna, dtype=np.float64),
            ]
        ),
        dtype=np.float64,
    )


def _charge_events(before_aminoacylated: np.ndarray, after_aminoacylated: np.ndarray) -> int:
    diff = np.asarray(after_aminoacylated, dtype=np.float64) - np.asarray(before_aminoacylated, dtype=np.float64)
    return int(round(float(np.sum(diff))))


def _run_oc_tick(
    seed: int,
    tick: int,
    before: dict[str, np.ndarray],
    alpha: float,
) -> dict[str, np.ndarray]:
    sample_seed = runner_helpers._sample_seed(seed, tick)
    process = runner_helpers._trna_aminoacylation_process(sample_seed)
    runtime_state = runner_helpers.build_state_template(process)
    substrate_wids = list(runner_helpers.load_fixture_channel_wids(PROCESS_NAME, "substrates"))
    enzyme_wids = list(runner_helpers.load_fixture_channel_wids(PROCESS_NAME, "enzymes"))
    bound_enzymes_before = np.asarray(before["boundEnzymes"][seed, tick], dtype=np.float64)

    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=_scale_substrates(before["substrates"][seed, tick], alpha),
        wids=substrate_wids,
    )
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=np.asarray(before["enzymes"][seed, tick], dtype=np.float64),
        wids=enzyme_wids,
    )
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="freeRNAs",
        vector=np.asarray(before["freeRNAs"][seed, tick], dtype=np.float64),
        wids=list(process.free_rna_wids),
    )
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="aminoacylatedRNAs",
        vector=np.asarray(before["aminoacylatedRNAs"][seed, tick], dtype=np.float64),
        wids=list(process.aminoacylated_rna_wids),
    )

    runner_helpers.refresh_allocator_views(process, runtime_state)
    with runner_helpers.forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    runner_helpers.apply_count_update(runtime_state, update)

    free_after = np.asarray(
        runner_helpers.project_observable_from_state(
            process=process,
            state=runtime_state,
            observable="freeRNAs",
            wids=list(process.free_rna_wids),
            bound_enzymes_before=bound_enzymes_before,
        ),
        dtype=np.float64,
    )
    aminoacylated_after = np.asarray(
        runner_helpers.project_observable_from_state(
            process=process,
            state=runtime_state,
            observable="aminoacylatedRNAs",
            wids=list(process.aminoacylated_rna_wids),
            bound_enzymes_before=bound_enzymes_before,
        ),
        dtype=np.float64,
    )
    substrates_after = np.asarray(
        runner_helpers.project_observable_from_state(
            process=process,
            state=runtime_state,
            observable="substrates",
            wids=substrate_wids,
            bound_enzymes_before=bound_enzymes_before,
        ),
        dtype=np.float64,
    )
    return {
        "substrates": substrates_after,
        "freeRNAs": free_after,
        "aminoacylatedRNAs": aminoacylated_after,
        "RNAs": _concat_rnas(free_after, aminoacylated_after),
    }


def _run_alpha(
    alpha: float,
    before: dict[str, np.ndarray],
    after: dict[str, np.ndarray],
) -> dict[str, object]:
    w1_values: list[float] = []
    total_oc_events = 0
    total_karr_events = 0
    _, n_ticks, _ = before["freeRNAs"].shape
    for seed in range(N_SEEDS):
        for tick in range(n_ticks):
            amino_before = np.asarray(before["aminoacylatedRNAs"][seed, tick], dtype=np.float64)
            oc_after = _run_oc_tick(seed=seed, tick=tick, before=before, alpha=alpha)
            karr_free_after = np.asarray(after["freeRNAs"][seed, tick], dtype=np.float64)
            karr_amino_after = np.asarray(after["aminoacylatedRNAs"][seed, tick], dtype=np.float64)
            karr_rnas_after = _concat_rnas(karr_free_after, karr_amino_after)
            if oc_after["RNAs"].shape != karr_rnas_after.shape:
                raise ValueError(
                    f"RNAs shape mismatch at seed={seed} tick={tick}: "
                    f"oc={oc_after['RNAs'].shape} karr={karr_rnas_after.shape}"
                )
            w1_values.append(runner_helpers.compute_w1(oc_after["RNAs"], karr_rnas_after))
            total_oc_events += _charge_events(amino_before, oc_after["aminoacylatedRNAs"])
            total_karr_events += _charge_events(amino_before, karr_amino_after)
    mean_w1 = float(np.mean(w1_values))
    max_w1 = float(np.max(w1_values))
    verdict = "PASS" if mean_w1 < PASS_MEAN_W1 and max_w1 < PASS_MAX_W1 else "FAIL"
    return {
        "alpha": alpha,
        "per_tick_W1_mean": mean_w1,
        "per_tick_W1_max": max_w1,
        "total_oc_events": total_oc_events,
        "total_karr_events": total_karr_events,
        "verdict": verdict,
    }


def main() -> int:
    before, after = _load_trace()
    rows = [_run_alpha(alpha, before, after) for alpha in ALPHAS]
    print("alpha | per_tick_W1_mean | per_tick_W1_max | total_oc_events | total_karr_events | verdict")
    for row in rows:
        print(
            f"{row['alpha']:.2f} | "
            f"{row['per_tick_W1_mean']:.6f} | "
            f"{row['per_tick_W1_max']:.6f} | "
            f"{row['total_oc_events']} | "
            f"{row['total_karr_events']} | "
            f"{row['verdict']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
