from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers

ALPHAS = (1.0, 0.5, 0.1, 0.05, 0.01)
N_SEEDS = 5
PASS_MEAN_W1 = 0.5
PASS_MAX_W1 = 2.0


def _karr_native_root_candidates() -> tuple[Path, ...]:
    candidates = (
        _REPO_ROOT / "data" / "m1_sources" / "karr_native",
        Path("/mnt/e/opencell/data/m1_sources/karr_native"),
        Path("E:/opencell/data/m1_sources/karr_native"),
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return tuple(unique)


def _seed_paths() -> list[Path]:
    paths: list[Path] = []
    for seed in range(N_SEEDS):
        rel = Path(f"per_process_traces_v2_s{seed:03d}") / "ProteinProcessingI_100ticks.mat"
        for root in _karr_native_root_candidates():
            candidate = root / rel
            if candidate.exists():
                paths.append(candidate)
                break
        else:
            paths.append(_karr_native_root_candidates()[0] / rel)
    return paths


def _load_trace() -> tuple[dict[str, np.ndarray], np.ndarray]:
    before, after, _ = runner_helpers._load_seeded_mat_channels(_seed_paths())
    required = ("substrates", "enzymes", "unprocessedMonomers")
    missing = [name for name in required if name not in before]
    if missing:
        raise KeyError(f"Missing states_before channels: {missing}")
    if "unprocessedMonomers" not in after:
        raise KeyError("Missing states_after.unprocessedMonomers")
    return before, np.asarray(after["unprocessedMonomers"], dtype=np.float64)


def _reference_wids() -> dict[str, tuple[str, ...]]:
    process = runner_helpers._protein_processing_i_process(0)
    return {
        "substrate_wids": tuple(str(wid) for wid in process.substrate_wids),
        "enzyme_wids": tuple(str(wid) for wid in process.enzyme_wids),
        "monomer_wids": tuple(str(wid) for wid in process.monomer_wids),
    }


def _scale_substrates(substrates: np.ndarray, alpha: float) -> np.ndarray:
    scaled = np.floor(np.clip(np.asarray(substrates, dtype=np.float64), a_min=0.0, a_max=None) * alpha)
    return np.asarray(scaled, dtype=np.float64)


def _processing_events(before_unprocessed: np.ndarray, after_unprocessed: np.ndarray) -> int:
    return int(round(float(np.sum(np.asarray(before_unprocessed, dtype=np.float64) - after_unprocessed))))


def _run_oc_tick(
    *,
    seed: int,
    tick: int,
    before: dict[str, np.ndarray],
    alpha: float,
    wids: dict[str, tuple[str, ...]],
) -> np.ndarray:
    tick_state = {
        "substrate_wids": wids["substrate_wids"],
        "enzyme_wids": wids["enzyme_wids"],
        "monomer_wids": wids["monomer_wids"],
        "oracle_before_substrates": _scale_substrates(before["substrates"][seed, tick], alpha),
        "oracle_before_enzymes": np.asarray(before["enzymes"][seed, tick], dtype=np.float64),
        "oracle_before_monomers": np.asarray(before["unprocessedMonomers"][seed, tick], dtype=np.float64),
    }
    return np.asarray(
        runner_helpers._run_protein_processing_i_tick(seed, tick, tick_state)["monomers"],
        dtype=np.float64,
    )


def _run_alpha(
    *,
    alpha: float,
    before: dict[str, np.ndarray],
    karr_after_monomers: np.ndarray,
    wids: dict[str, tuple[str, ...]],
) -> dict[str, object]:
    w1_values: list[float] = []
    total_oc_events = 0
    total_karr_events = 0
    _, n_ticks, _ = before["unprocessedMonomers"].shape
    for seed in range(N_SEEDS):
        for tick in range(n_ticks):
            monomers_before = np.asarray(before["unprocessedMonomers"][seed, tick], dtype=np.float64)
            oc_after = _run_oc_tick(seed=seed, tick=tick, before=before, alpha=alpha, wids=wids)
            karr_after = np.asarray(karr_after_monomers[seed, tick], dtype=np.float64)
            if oc_after.shape != karr_after.shape:
                raise ValueError(
                    f"unprocessedMonomers shape mismatch at seed={seed} tick={tick}: "
                    f"oc={oc_after.shape} karr={karr_after.shape}"
                )
            w1_values.append(runner_helpers.compute_w1(oc_after, karr_after))
            total_oc_events += _processing_events(monomers_before, oc_after)
            total_karr_events += _processing_events(monomers_before, karr_after)
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
    before, karr_after_monomers = _load_trace()
    wids = _reference_wids()
    rows = [_run_alpha(alpha=alpha, before=before, karr_after_monomers=karr_after_monomers, wids=wids) for alpha in ALPHAS]
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
