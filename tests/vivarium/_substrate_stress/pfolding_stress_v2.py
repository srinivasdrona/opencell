from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers

ALPHAS = (1.0, 0.5, 0.1, 0.05, 0.01)
N_SEEDS = 5
PASS_MEAN_W1 = 0.5
PASS_MAX_W1 = 2.0


def _seed_paths() -> list[Path]:
    return [runner_helpers._v2_seed_mat_path("ProteinFolding", seed) for seed in range(N_SEEDS)]


def _load_trace() -> tuple[dict[str, np.ndarray], np.ndarray]:
    before, after, _ = runner_helpers._load_seeded_mat_channels(_seed_paths())
    required = ("substrates", "enzymes", "boundEnzymes", "unfoldedMonomers", "foldedMonomers")
    missing = [name for name in required if name not in before]
    if missing:
        raise KeyError(f"Missing states_before channels: {missing}")
    if "foldedMonomers" not in after:
        raise KeyError("Missing states_after.foldedMonomers")
    return before, np.asarray(after["foldedMonomers"], dtype=np.float64)


def _scale_substrates(substrates: np.ndarray, alpha: float) -> np.ndarray:
    scaled = np.floor(np.clip(np.asarray(substrates, dtype=np.float64), a_min=0.0, a_max=None) * alpha)
    return np.asarray(scaled, dtype=np.float64)


def _fold_events(before_folded: np.ndarray, after_folded: np.ndarray) -> int:
    return int(round(float(np.sum(np.asarray(after_folded, dtype=np.float64) - before_folded))))


def _run_oc_tick(
    seed: int,
    tick: int,
    process: KarrProteinFoldingProcess,
    before: dict[str, np.ndarray],
    alpha: float,
) -> np.ndarray:
    unfolded_before = np.asarray(before["unfoldedMonomers"][seed, tick], dtype=np.float64)
    folded_before = np.asarray(before["foldedMonomers"][seed, tick], dtype=np.float64)
    state = {
        "substrate_wids": tuple(process.substrate_wids),
        "enzyme_wids": tuple(process.enzyme_wids),
        "oracle_before_substrates": _scale_substrates(before["substrates"][seed, tick], alpha),
        "oracle_before_enzymes": np.asarray(before["enzymes"][seed, tick], dtype=np.float64),
        "oracle_before_bound_enzymes": np.asarray(before["boundEnzymes"][seed, tick], dtype=np.float64),
        "oracle_before_monomers": np.concatenate([unfolded_before, folded_before]),
    }
    oc = runner_helpers._run_protein_folding_tick(seed=seed, tick=tick, state=state)
    monomers_after = np.asarray(oc["monomers"], dtype=np.float64)
    return monomers_after[len(process.unfolded_monomer_wids) :]


def _run_alpha(
    alpha: float,
    before: dict[str, np.ndarray],
    karr_after_folded: np.ndarray,
    process: KarrProteinFoldingProcess,
) -> dict[str, object]:
    w1_values: list[float] = []
    total_oc_events = 0
    total_karr_events = 0
    _, n_ticks, _ = before["foldedMonomers"].shape
    for seed in range(N_SEEDS):
        for tick in range(n_ticks):
            folded_before = np.asarray(before["foldedMonomers"][seed, tick], dtype=np.float64)
            oc_after = _run_oc_tick(seed=seed, tick=tick, process=process, before=before, alpha=alpha)
            karr_after = np.asarray(karr_after_folded[seed, tick], dtype=np.float64)
            if oc_after.shape != karr_after.shape:
                raise ValueError(
                    f"foldedMonomers shape mismatch at seed={seed} tick={tick}: "
                    f"oc={oc_after.shape} karr={karr_after.shape}"
                )
            w1_values.append(runner_helpers.compute_w1(oc_after, karr_after))
            total_oc_events += _fold_events(folded_before, oc_after)
            total_karr_events += _fold_events(folded_before, karr_after)
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
    before, karr_after_folded = _load_trace()
    process = KarrProteinFoldingProcess({"rng_seed": 0})
    rows = [_run_alpha(alpha, before, karr_after_folded, process) for alpha in ALPHAS]
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
