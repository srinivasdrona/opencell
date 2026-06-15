from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers

ALPHAS = (1.0, 0.5, 0.1, 0.05, 0.01)
N_SEEDS = 5
PASS_MEAN_W1 = 0.5
PASS_MAX_W1 = 2.0


def _seed_paths() -> list[Path]:
    return [runner_helpers._v2_seed_mat_path("ProteinTranslocation", seed) for seed in range(N_SEEDS)]


def _load_trace() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    before, after, _ = runner_helpers._load_seeded_mat_channels(_seed_paths())
    required = ("substrates", "enzymes", "boundEnzymes", "monomers")
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


def _project_karr_monomers(
    process: KarrProteinTranslocationProcess,
    monomers: np.ndarray,
) -> np.ndarray:
    monomer_count = len(process.monomer_wids)
    return np.asarray(np.asarray(monomers, dtype=np.float64)[:monomer_count], dtype=np.float64)


def _translocation_events(before_monomers: np.ndarray, after_monomers: np.ndarray) -> int:
    return int(round(float(np.sum(np.asarray(before_monomers, dtype=np.float64) - np.asarray(after_monomers, dtype=np.float64)))))


def _run_oc_tick(
    seed: int,
    tick: int,
    before: dict[str, np.ndarray],
    alpha: float,
    reference_process: KarrProteinTranslocationProcess,
) -> dict[str, np.ndarray]:
    sample_state = {
        "substrate_wids": list(reference_process.substrate_wids),
        "enzyme_wids": list(reference_process.enzyme_wids),
        "monomer_wids": list(reference_process.monomer_wids),
        "oracle_before_substrates": _scale_substrates(before["substrates"][seed, tick], alpha),
        "oracle_before_enzymes": np.asarray(before["enzymes"][seed, tick], dtype=np.float64),
        "oracle_before_monomers": np.asarray(before["monomers"][seed, tick], dtype=np.float64),
        "oracle_before_bound_enzymes": np.asarray(before["boundEnzymes"][seed, tick], dtype=np.float64),
    }
    oc_after = runner_helpers._run_protein_translocation_tick(seed, tick, sample_state)
    return {
        channel: np.asarray(values, dtype=np.float64)
        for channel, values in oc_after.items()
        if channel in {"substrates", "monomers"}
    }


def _run_alpha(
    alpha: float,
    before: dict[str, np.ndarray],
    after: dict[str, np.ndarray],
    reference_process: KarrProteinTranslocationProcess,
) -> dict[str, object]:
    w1_values: list[float] = []
    total_oc_events = 0
    total_karr_events = 0
    _, n_ticks, _ = before["substrates"].shape
    for seed in range(N_SEEDS):
        for tick in range(n_ticks):
            oc_after = _run_oc_tick(
                seed=seed,
                tick=tick,
                before=before,
                alpha=alpha,
                reference_process=reference_process,
            )
            karr_after_substrates = np.asarray(after["substrates"][seed, tick], dtype=np.float64)
            karr_after_monomers = _project_karr_monomers(reference_process, after["monomers"][seed, tick])
            karr_before_monomers = _project_karr_monomers(reference_process, before["monomers"][seed, tick])

            if oc_after["substrates"].shape != karr_after_substrates.shape:
                raise ValueError(
                    f"substrates shape mismatch at seed={seed} tick={tick}: "
                    f"oc={oc_after['substrates'].shape} karr={karr_after_substrates.shape}"
                )
            if oc_after["monomers"].shape != karr_after_monomers.shape:
                raise ValueError(
                    f"monomers shape mismatch at seed={seed} tick={tick}: "
                    f"oc={oc_after['monomers'].shape} karr={karr_after_monomers.shape}"
                )

            w1_values.append(runner_helpers.compute_w1(oc_after["monomers"], karr_after_monomers))
            total_oc_events += _translocation_events(karr_before_monomers, oc_after["monomers"])
            total_karr_events += _translocation_events(karr_before_monomers, karr_after_monomers)

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
    reference_process = KarrProteinTranslocationProcess({"rng_seed": 0})
    rows = [_run_alpha(alpha, before, after, reference_process) for alpha in ALPHAS]
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
