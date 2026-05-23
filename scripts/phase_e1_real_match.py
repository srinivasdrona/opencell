"""Phase E.1 real-match run: chassis_v6 full trajectory fixture."""

from __future__ import annotations

import argparse
import pickle
import time
from pathlib import Path
from typing import Any

import numpy as np
from vivarium.core.engine import Engine

from opencell.analysis.cell_mass import compute_cell_mass
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import build_karr_chassis_v6

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "phase_e" / "v6_trajectory_32400s.pkl"
SNAPSHOT_STRIDE_TICKS = 100
MAX_TICKS = 32400

_REPLICATION_CODE_MAP = {
    "idle": 0.0,
    "initiating": 1.0,
    "elongating": 2.0,
    "complete": 3.0,
}


def _safe_sum_counts(counts: Any) -> float:
    if isinstance(counts, dict):
        return float(sum(float(v) for v in counts.values()))
    if isinstance(counts, (list, tuple)):
        return float(sum(float(v) for v in counts))
    if counts is None:
        return 0.0
    arr = np.asarray(counts, dtype=np.float64).reshape(-1)
    return float(np.sum(arr))


def _fork_position_norm(chromosome: dict[str, Any], *, fork_scale_bp: float) -> float:
    fork_bp = chromosome.get("fork_position_bp", {})
    if isinstance(fork_bp, dict):
        values = [float(v) for v in fork_bp.values()]
    else:
        values = np.asarray(fork_bp, dtype=np.float64).reshape(-1).tolist()
    if not values:
        return 0.0
    peak = float(np.max(np.abs(np.asarray(values, dtype=np.float64))))
    scale = max(float(fork_scale_bp), 1.0)
    return float(np.clip(peak / scale, 0.0, 1.0))


def _division_detected(state: dict[str, Any]) -> bool:
    cell = state.get("cell", {})
    if bool(cell.get("division_complete", False)):
        return True
    if float(cell.get("division_event_count", 0.0)) > 0.0:
        return True
    phase = str(cell.get("cycle_phase", "")).strip().lower()
    return phase in {"division_complete", "divided"}


def _extract_observables(
    state: dict[str, Any],
    *,
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
    fork_scale_bp: float,
    tick_s: float,
    division_detected: bool,
) -> dict[str, float]:
    mass = compute_cell_mass(state, m1_model, m2_model, m3_model)
    chromosome = state.get("chromosome", {})
    substrates = state.get("substrates", {})
    rna_counts = state.get("rna", {}).get("counts", {})
    protein_counts = state.get("protein", {}).get("counts", {})

    replication_label = str(chromosome.get("replication_state", "idle"))
    replication_state_code = _REPLICATION_CODE_MAP.get(replication_label, 0.0)
    phenotype_obs = state.get("phenotype_observables", {})

    dntp_pool_total = float(
        substrates.get("DATP", 0.0)
        + substrates.get("DCTP", 0.0)
        + substrates.get("DGTP", 0.0)
        + substrates.get("DTTP", 0.0)
    )

    return {
        "cell_dry_mass_g": float(mass.total_g),
        "replication_state_code": float(replication_state_code),
        "fork_position_norm": _fork_position_norm(chromosome, fork_scale_bp=fork_scale_bp),
        "mrna_total_count_estimate": _safe_sum_counts(rna_counts),
        "protein_total_count_estimate": _safe_sum_counts(protein_counts),
        "atp_pool": float(substrates.get("ATP", np.nan)),
        "gtp_pool": float(substrates.get("GTP", np.nan)),
        "dntp_pool_total": dntp_pool_total,
        "division_event_timestamp_s": float(tick_s if division_detected else np.nan),
        "rna_mass_g": float(phenotype_obs.get("rna_mass_g", np.nan)),
        "protein_mass_g": float(phenotype_obs.get("protein_mass_g", np.nan)),
        "dna_mass_g": float(phenotype_obs.get("dna_mass_g", np.nan)),
        "cytokinesis_start_tick_s": float(phenotype_obs.get("cytokinesis_start_tick_s", np.nan)),
        "cytokinesis_complete_tick_s": float(
            phenotype_obs.get("cytokinesis_complete_tick_s", np.nan)
        ),
        "metabolite_pools": dict(phenotype_obs.get("metabolite_pools", {})),
        "cell_dry_mass_reference_g": float(phenotype_obs.get("cell_dry_mass_reference_g", np.nan)),
    }


def run_v6_trajectory(
    *,
    out_path: Path = DEFAULT_OUT,
    snapshot_stride_ticks: int = SNAPSHOT_STRIDE_TICKS,
    max_ticks: int = MAX_TICKS,
    stop_on_division: bool = True,
) -> dict[str, Any]:
    m1_model = km.load_default()
    m2_model = tx.load_default()
    m3_model = tl.load_default()

    composite = build_karr_chassis_v6(
        m1_model=m1_model,
        m2_model=m2_model,
        m3_model=m3_model,
        time_step_s=1.0,
        emit_step_s=float(snapshot_stride_ticks),
    )
    engine = Engine(composite=composite, emit_step=float(snapshot_stride_ticks), display_info=False)

    rep_proc = composite.processes.get("karr_replication") if hasattr(composite, "processes") else None
    fork_scale_bp = float(getattr(rep_proc, "terc_position_bp", 1.0))

    snapshots: list[dict[str, Any]] = []
    t0 = time.time()
    state = engine.state.get_value()
    division = False

    for tick in range(0, int(max_ticks) + 1, int(snapshot_stride_ticks)):
        if tick > 0:
            engine.update(float(snapshot_stride_ticks))
            state = engine.state.get_value()

        division = _division_detected(state)
        observables = _extract_observables(
            state,
            m1_model=m1_model,
            m2_model=m2_model,
            m3_model=m3_model,
            fork_scale_bp=fork_scale_bp,
            tick_s=float(tick),
            division_detected=division,
        )
        snapshots.append(
            {
                "tick": int(tick),
                "time_s": float(tick),
                "state": observables,
            }
        )
        if division and stop_on_division:
            break

    payload = {
        "snapshots": snapshots,
        "wall_time_s": float(time.time() - t0),
        "ticks_completed": int(snapshots[-1]["tick"]) if snapshots else 0,
        "division_detected": bool(division),
        "chassis": "v6",
        "schema_version": 1,
        "snapshot_stride_ticks": int(snapshot_stride_ticks),
        "max_ticks_requested": int(max_ticks),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        pickle.dump(payload, f)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--snapshot-stride-ticks", type=int, default=SNAPSHOT_STRIDE_TICKS)
    parser.add_argument("--max-ticks", type=int, default=MAX_TICKS)
    parser.add_argument("--no-stop-on-division", action="store_true")
    args = parser.parse_args()

    result = run_v6_trajectory(
        out_path=args.out,
        snapshot_stride_ticks=args.snapshot_stride_ticks,
        max_ticks=args.max_ticks,
        stop_on_division=not args.no_stop_on_division,
    )
    print(
        "phase_e1_real_match:"
        f" snapshots={len(result['snapshots'])}"
        f" ticks_completed={result['ticks_completed']}"
        f" division_detected={result['division_detected']}"
        f" wall_time_s={result['wall_time_s']:.2f}"
        f" out={args.out}"
    )


if __name__ == "__main__":
    main()
