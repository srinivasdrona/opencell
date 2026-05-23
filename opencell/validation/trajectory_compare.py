"""Trajectory comparison helpers for Phase E.1 scaffold."""

from __future__ import annotations

from typing import Any

import numpy as np

from opencell.diff.multi_level import DiffSpec, run_diff

_A6_REL_TOL_BY_KIND: dict[str, float] = {
    "concentration": 0.05,
    "signal": 0.10,
    "count": 0.50,
}

_OBSERVABLE_KIND: dict[str, str] = {
    "cell_dry_mass_g": "count",
    "replication_state_code": "signal",
    "fork_position_norm": "signal",
    "mrna_total_count_estimate": "count",
    "protein_total_count_estimate": "count",
    "atp_pool": "concentration",
    "gtp_pool": "concentration",
    "dntp_pool_total": "concentration",
    "division_event_timestamp_s": "signal",
}

KARR_28_PHENOTYPE_IDS: tuple[str, ...] = tuple(f"p{i}" for i in range(1, 29))


def _to_array(x: Any) -> np.ndarray:
    return np.asarray(x, dtype=np.float64).reshape(-1)


def _canonicalize_karr28_phenotypes(phenotypes: dict[str, Any] | None) -> dict[str, float]:
    if not phenotypes:
        return {}

    out: dict[str, float] = {}
    for raw_key, raw_value in phenotypes.items():
        key = str(raw_key)
        value = float(raw_value)
        if key in KARR_28_PHENOTYPE_IDS:
            out[key] = value
            continue
        prefix = key.split("_", 1)[0]
        if prefix in KARR_28_PHENOTYPE_IDS:
            out[prefix] = value
    return out


def compare_trajectories(
    opencell_trajectory: dict[str, Any],
    karr_trajectory: dict[str, Any],
) -> dict[str, Any]:
    """Compare two trajectories and return per-observable + phenotype diffs."""
    op_time = _to_array(opencell_trajectory.get("time_s", []))
    karr_time = _to_array(karr_trajectory.get("time_s", []))
    n = min(op_time.size, karr_time.size)
    if n <= 0:
        raise ValueError("Both trajectories must have non-empty `time_s`.")

    op_obs_all = opencell_trajectory.get("observables", {})
    karr_obs_all = karr_trajectory.get("observables", {})
    shared_observables = sorted(set(op_obs_all) & set(karr_obs_all))
    if not shared_observables:
        raise ValueError("No shared observables between trajectories.")

    op_obs = {k: _to_array(op_obs_all[k])[:n] for k in shared_observables}
    karr_obs = {k: _to_array(karr_obs_all[k])[:n] for k in shared_observables}

    op_diff_traj = {
        "time": op_time[:n],
        "observables": op_obs,
        "phenotypes_canonical": _canonicalize_karr28_phenotypes(opencell_trajectory.get("phenotypes")),
    }
    karr_diff_traj = {
        "time": karr_time[:n],
        "observables": karr_obs,
        "phenotypes_canonical": _canonicalize_karr28_phenotypes(karr_trajectory.get("phenotypes")),
    }

    comparable_variables: dict[tuple[str, str], dict[str, Any]] = {}
    for observable in shared_observables:
        kind = _OBSERVABLE_KIND.get(observable, "count")
        comparable_variables[("observables", observable)] = {
            "abs": 0.0,
            "rel": _A6_REL_TOL_BY_KIND[kind],
            "kind": kind if kind in {"concentration", "signal", "count"} else "count",
        }

    spec = DiffSpec(
        engine_a_name="opencell",
        engine_b_name="karr",
        comparable_variables=comparable_variables,
        scalar_phenotypes=list(KARR_28_PHENOTYPE_IDS),
        structural_required_paths=[("observables", name) for name in shared_observables],
    )

    report = run_diff(
        op_diff_traj,
        karr_diff_traj,
        spec=spec,
        phenotype_fn=lambda traj: traj.get("phenotypes_canonical", {}),
        phenotype_abs_tol=0.0,
        phenotype_rel_tol=0.5,
    )

    observable_errors: dict[str, dict[str, Any]] = {}
    for finding in report.level3_findings:
        path = finding.detail.get("path", [])
        if len(path) != 2 or path[0] != "observables":
            continue
        name = str(path[1])
        observable_errors[name] = {
            "l_inf_abs": float(finding.detail["L_inf_abs"]),
            "l_inf_rel": float(finding.detail["L_inf_rel"]),
            "l2_abs": float(finding.detail["L2_abs"]),
            "abs_tol": float(finding.detail["abs_tol"]),
            "rel_tol": float(finding.detail["rel_tol"]),
            "pass": finding.severity == "ok",
        }

    phenotype_scalar_diff: dict[str, dict[str, Any]] = {}
    for finding in report.level4_findings:
        if finding.name == "phenotype" and "phenotype" in finding.detail:
            pid = str(finding.detail["phenotype"])
            phenotype_scalar_diff[pid] = {
                "a": float(finding.detail["a"]),
                "b": float(finding.detail["b"]),
                "abs_diff": float(finding.detail["abs_diff"]),
                "rel_diff": float(finding.detail["rel_diff"]),
                "status": finding.severity,
            }
            continue
        if finding.name == "phenotype_missing":
            pid = finding.message.split(":", 1)[0].strip()
            phenotype_scalar_diff[pid] = {
                "a": None,
                "b": None,
                "abs_diff": None,
                "rel_diff": None,
                "status": "missing",
            }

    return {
        "n_timepoints_compared": n,
        "shared_observables": shared_observables,
        "observable_errors": observable_errors,
        "phenotype_scalar_diff": phenotype_scalar_diff,
        "summary": report.summary(),
    }


__all__ = ["KARR_28_PHENOTYPE_IDS", "compare_trajectories"]
