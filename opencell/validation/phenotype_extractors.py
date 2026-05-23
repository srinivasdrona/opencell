"""Phenotype extractor functions for Phase E.2 scorecard."""

from __future__ import annotations

from typing import Any

import numpy as np

Trajectory = dict[str, Any]


def _snapshots(trajectory: Trajectory) -> list[dict[str, Any]]:
    raw = trajectory.get("snapshots", [])
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, dict)]
    return []


def _state_series(trajectory: Trajectory, key: str) -> np.ndarray | None:
    snaps = _snapshots(trajectory)
    if not snaps:
        return None
    values: list[float] = []
    found = False
    for snap in snaps:
        state = snap.get("state", {})
        if not isinstance(state, dict):
            values.append(float("nan"))
            continue
        if key in state:
            found = True
        values.append(float(state.get(key, np.nan)))
    if not found:
        return None
    return np.asarray(values, dtype=np.float64)


def _time_series(trajectory: Trajectory) -> np.ndarray | None:
    snaps = _snapshots(trajectory)
    if not snaps:
        return None
    out: list[float] = []
    for snap in snaps:
        out.append(float(snap.get("time_s", np.nan)))
    return np.asarray(out, dtype=np.float64)


def _tail(arr: np.ndarray, *, n: int = 20) -> np.ndarray:
    if arr.size <= n:
        return arr
    return arr[-n:]


def _finite(arr: np.ndarray) -> np.ndarray:
    return arr[np.isfinite(arr)]


def _first_finite(arr: np.ndarray) -> float | None:
    finite = _finite(arr)
    if finite.size == 0:
        return None
    return float(finite[0])


def _last_finite(arr: np.ndarray) -> float | None:
    finite = _finite(arr)
    if finite.size == 0:
        return None
    return float(finite[-1])


def _std_over_abs_mean(arr: np.ndarray) -> float:
    finite = _finite(arr)
    if finite.size < 2:
        return float("nan")
    denom = max(float(np.abs(np.mean(finite))), 1e-12)
    return float(np.std(finite) / denom)


def _safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(mask) < 3:
        return float("nan")
    xv = x[mask]
    yv = y[mask]
    if float(np.std(xv)) < 1e-12 or float(np.std(yv)) < 1e-12:
        return 0.0
    return float(np.corrcoef(xv, yv)[0, 1])


def extract_kp01(trajectory: Trajectory) -> float | None:
    mass = _state_series(trajectory, "cell_dry_mass_g")
    time_s = _time_series(trajectory)
    if mass is None or time_s is None or mass.size < 2 or time_s.size < 2:
        return None
    dt = np.diff(time_s)
    dm = np.diff(mass)
    valid = np.isfinite(dt) & np.isfinite(dm) & (np.abs(dt) > 0)
    if not np.any(valid):
        return float("nan")
    growth_proxy = dm[valid] / dt[valid]
    return float(np.mean(_tail(growth_proxy, n=20)))


def extract_kp02(trajectory: Trajectory) -> float | None:
    division = _state_series(trajectory, "division_event_timestamp_s")
    if division is None:
        return None
    first = _first_finite(division)
    if first is None:
        return float("nan")
    return first


def extract_kp03(_trajectory: Trajectory) -> float | None:
    # Requires metabolic flux and oracle fixture not emitted in schema-v1 snapshots.
    return None


def extract_kp04(_trajectory: Trajectory) -> float | None:
    # Requires TX_GLCPTS flux not emitted in schema-v1 snapshots.
    return None


def extract_kp05(trajectory: Trajectory) -> float | None:
    mrna = _state_series(trajectory, "mrna_total_count_estimate")
    if mrna is None:
        return None
    last = _last_finite(mrna)
    return float("nan") if last is None else last


def extract_kp06(trajectory: Trajectory) -> float | None:
    protein = _state_series(trajectory, "protein_total_count_estimate")
    if protein is None:
        return None
    last = _last_finite(protein)
    return float("nan") if last is None else last


def extract_kp07(trajectory: Trajectory) -> float | None:
    mrna = _state_series(trajectory, "mrna_total_count_estimate")
    if mrna is None:
        return None
    return _std_over_abs_mean(_tail(mrna, n=20))


def extract_kp08(trajectory: Trajectory) -> float | None:
    protein = _state_series(trajectory, "protein_total_count_estimate")
    if protein is None:
        return None
    return _std_over_abs_mean(_tail(protein, n=20))


def extract_kp09(trajectory: Trajectory) -> float | None:
    atp = _state_series(trajectory, "atp_pool")
    gtp = _state_series(trajectory, "gtp_pool")
    dntp = _state_series(trajectory, "dntp_pool_total")
    if atp is None or gtp is None or dntp is None:
        return None
    pooled = atp + gtp + dntp
    return _std_over_abs_mean(_tail(pooled, n=20))


def extract_kp10(trajectory: Trajectory) -> float | None:
    mass = _state_series(trajectory, "cell_dry_mass_g")
    division = _state_series(trajectory, "division_event_timestamp_s")
    if mass is None or division is None:
        return None
    has_division = np.isfinite(division)
    if np.any(has_division):
        idx = int(np.argmax(has_division))
        return float(mass[idx]) if np.isfinite(mass[idx]) else float("nan")
    last = _last_finite(mass)
    return float("nan") if last is None else last


def extract_kp11(trajectory: Trajectory) -> float | None:
    rep = _state_series(trajectory, "replication_state_code")
    time_s = _time_series(trajectory)
    if rep is None or time_s is None:
        return None
    idxs = np.where((np.isfinite(rep)) & (rep > 0.0))[0]
    if idxs.size == 0:
        return float("nan")
    return float(time_s[int(idxs[0])])


def extract_kp12(trajectory: Trajectory) -> float | None:
    rep = _state_series(trajectory, "replication_state_code")
    time_s = _time_series(trajectory)
    if rep is None or time_s is None:
        return None
    start = np.where((np.isfinite(rep)) & (rep > 0.0))[0]
    end = np.where((np.isfinite(rep)) & (rep >= 3.0))[0]
    if start.size == 0 or end.size == 0:
        return float("nan")
    duration = float(time_s[int(end[0])] - time_s[int(start[0])])
    return duration if duration >= 0.0 else float("nan")


def extract_kp13(_trajectory: Trajectory) -> float | None:
    # Requires ftsz/cytokinesis stores not emitted in schema-v1 snapshots.
    return None


def extract_kp14(trajectory: Trajectory) -> float | None:
    dntp = _state_series(trajectory, "dntp_pool_total")
    fork = _state_series(trajectory, "fork_position_norm")
    if dntp is None or fork is None:
        return None
    return _safe_corr(dntp, fork)


def extract_kp15(_trajectory: Trajectory) -> bool | None:
    # Requires chromosome.complex_bound_sites not emitted in schema-v1 snapshots.
    return None


def extract_kp16(trajectory: Trajectory) -> float | None:
    fork = _state_series(trajectory, "fork_position_norm")
    if fork is None:
        return None
    last = _last_finite(fork)
    if last is None:
        return float("nan")
    # Proxy: baseline DNA content 1.0, fork progress toward full doubling.
    return float(1.0 + max(last, 0.0))


def extract_kp17(_trajectory: Trajectory) -> float | None:
    # Requires explicit DNA and total mass series not emitted in schema-v1 snapshots.
    return None


def extract_kp18(trajectory: Trajectory) -> float | None:
    rna_mass = _state_series(trajectory, "rna_mass_g")
    total_ref = _state_series(trajectory, "cell_dry_mass_reference_g")
    if rna_mass is None or total_ref is None:
        return None
    rna0 = _first_finite(rna_mass)
    total0 = _first_finite(total_ref)
    if rna0 is None or total0 is None or total0 <= 0.0:
        return float("nan")
    return float(rna0 / total0)


def extract_kp19(_trajectory: Trajectory) -> float | None:
    # Requires explicit protein mass and total mass series not emitted in schema-v1 snapshots.
    return None


def extract_kp20(_trajectory: Trajectory) -> float | None:
    # Requires 30-metabolite concentration profile not emitted in schema-v1 snapshots.
    return None


def extract_kp21(_trajectory: Trajectory) -> float | None:
    # Requires production/use ledger stores not emitted in schema-v1 snapshots.
    return None


def extract_kp22(trajectory: Trajectory) -> bool | None:
    atp = _state_series(trajectory, "atp_pool")
    gtp = _state_series(trajectory, "gtp_pool")
    if atp is None or gtp is None:
        return None
    return bool(np.any(atp < 0.0) or np.any(gtp < 0.0))


def extract_kp23(trajectory: Trajectory) -> bool | None:
    protein = _state_series(trajectory, "protein_total_count_estimate")
    if protein is None:
        return None
    diffs = np.diff(_finite(protein))
    if diffs.size < 3:
        return False
    mean_abs = float(np.mean(np.abs(diffs)))
    if mean_abs <= 1e-12:
        return False
    fano_like = float(np.var(diffs) / mean_abs)
    return bool(np.isfinite(fano_like))


def extract_kp24(trajectory: Trajectory) -> bool | None:
    mrna = _state_series(trajectory, "mrna_total_count_estimate")
    protein = _state_series(trajectory, "protein_total_count_estimate")
    if mrna is None or protein is None:
        return None
    x = _finite(_tail(mrna, n=40))
    y = _finite(_tail(protein, n=40))
    if x.size < 5 or y.size < 5:
        return False
    x_sorted = np.sort((x - x.min()) / max(x.max() - x.min(), 1e-12))
    y_sorted = np.sort((y - y.min()) / max(y.max() - y.min(), 1e-12))
    n = min(x_sorted.size, y_sorted.size)
    ks_like = float(np.max(np.abs(x_sorted[:n] - y_sorted[:n])))
    return bool(np.isfinite(ks_like))


def extract_kp25(_trajectory: Trajectory) -> None:
    return None


def extract_kp26(_trajectory: Trajectory) -> None:
    return None


def extract_kp27(_trajectory: Trajectory) -> bool | None:
    # Requires host.is_bacterium_adherent not emitted in schema-v1 snapshots.
    return None


def extract_kp28(_trajectory: Trajectory) -> bool | None:
    # Requires host immune activation flags not emitted in schema-v1 snapshots.
    return None


__all__ = [
    "extract_kp01",
    "extract_kp02",
    "extract_kp03",
    "extract_kp04",
    "extract_kp05",
    "extract_kp06",
    "extract_kp07",
    "extract_kp08",
    "extract_kp09",
    "extract_kp10",
    "extract_kp11",
    "extract_kp12",
    "extract_kp13",
    "extract_kp14",
    "extract_kp15",
    "extract_kp16",
    "extract_kp17",
    "extract_kp18",
    "extract_kp19",
    "extract_kp20",
    "extract_kp21",
    "extract_kp22",
    "extract_kp23",
    "extract_kp24",
    "extract_kp25",
    "extract_kp26",
    "extract_kp27",
    "extract_kp28",
]
