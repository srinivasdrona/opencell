"""Probe H10-refined: does NaN propagation explain the Rule 3 LP paradox?

Run with:
    bin/oc-py scripts/probe_metab_fba_paradox_codex.py

The script compares OC's ``cfb.compute_bounds`` against a faithful port of
Karr's ``Metabolism.calcFluxBounds`` for the tick-0 metabolism trace inputs,
classifies every bound mismatch without dropping NaNs, resolves the LP with the
Karr-faithful bounds, and writes the full transcript to
``tmp/metab_fba_paradox_codex.log``.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import h5py
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture

LOG_PATH = REPO / "tmp" / "metab_fba_paradox_codex.log"
TRACE_PATH = (
    REPO
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_s000"
    / "Metabolism_100ticks.mat"
)
MAT_PATH = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
BIG_BOUND = 1e18


def render_scalar(value: float) -> str:
    if np.isnan(value):
        return "NaN"
    if np.isneginf(value):
        return "-inf"
    if np.isposinf(value):
        return "+inf"
    if value == 0.0:
        return "0"
    return f"{value:.6g}"


def value_label(value: float) -> str:
    if np.isnan(value):
        return "NaN"
    if np.isneginf(value):
        return "-inf"
    if np.isposinf(value):
        return "+inf"
    if value == 0.0:
        return "0"
    return "finite"


def values_differ(left: float, right: float) -> bool:
    if np.isnan(left) or np.isnan(right):
        return not (np.isnan(left) and np.isnan(right))
    return left != right


def classify_pair(oc_value: float, karr_value: float) -> str:
    oc_label = value_label(oc_value)
    karr_label = value_label(karr_value)
    if oc_label == "finite" and karr_label == "finite" and oc_value != karr_value:
        return f"(OC={render_scalar(oc_value)}, Karr={render_scalar(karr_value)}, both finite diff)"
    return f"(OC={oc_label}, Karr={karr_label})"


def sanitize_bounds_for_lp(bounds: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lb = bounds[:, 0].copy()
    ub = bounds[:, 1].copy()

    lb[np.isnan(lb)] = -BIG_BOUND
    ub[np.isnan(ub)] = BIG_BOUND

    lb[np.isneginf(lb)] = -BIG_BOUND
    ub[np.isposinf(ub)] = BIG_BOUND

    lb[np.isposinf(lb)] = BIG_BOUND
    ub[np.isneginf(ub)] = -BIG_BOUND
    return lb, ub


def karr_calc_bounds_faithful(
    *,
    substrates: np.ndarray,
    enzymes: np.ndarray,
    cell_dry_mass: float,
    step_size_sec: float,
    catalysis: np.ndarray,
    enz_bounds: np.ndarray,
    fba_reaction_bounds: np.ndarray,
    dyn: cfb.M1DynamicsInputs,
) -> np.ndarray:
    """Faithful MATLAB-semantic port of Metabolism.calcFluxBounds lines 1318-1402."""
    n_rxn = catalysis.shape[0]
    lower = np.full(n_rxn, -np.inf, dtype=float)
    upper = np.full(n_rxn, np.inf, dtype=float)

    rxn_enz = catalysis.astype(float) @ enzymes.astype(float)

    with np.errstate(invalid="ignore"):
        kin_lo = enz_bounds[:, 0] * rxn_enz
        kin_hi = enz_bounds[:, 1] * rxn_enz
    lower = np.maximum(lower, kin_lo)
    upper = np.minimum(upper, kin_hi)

    any_cat = np.any(catalysis != 0, axis=1)
    zero_mask = any_cat & (rxn_enz <= 0.0)
    lower[zero_mask] = 0.0
    upper[zero_mask] = 0.0

    for sel in (
        dyn.fba_rxn_idx_metab_conv,
        dyn.fba_rxn_idx_internal_exch,
        dyn.fba_rxn_idx_biomass_exchange,
        dyn.fba_rxn_idx_biomass_production,
    ):
        lower[sel] = np.maximum(lower[sel], fba_reaction_bounds[sel, 0])
        upper[sel] = np.minimum(upper[sel], fba_reaction_bounds[sel, 1])

    ext_rxn = dyn.fba_rxn_idx_external_exch
    ext_sub = dyn.substrate_idx_external_exch_0
    avail = substrates[ext_sub, dyn.compartment_extracellular_0based] / step_size_sec
    upper[ext_rxn] = np.minimum(upper[ext_rxn], avail)
    lower[ext_rxn] = np.maximum(lower[ext_rxn], fba_reaction_bounds[ext_rxn, 0] * cell_dry_mass)
    upper[ext_rxn] = np.minimum(upper[ext_rxn], fba_reaction_bounds[ext_rxn, 1] * cell_dry_mass)

    int_rxn = dyn.fba_rxn_idx_internal_lim_exch
    int_sub = dyn.substrate_idx_internal_lim_0
    cytosol_counts = substrates[int_sub, 0]
    lower[int_rxn] = np.maximum(lower[int_rxn], -cytosol_counts / step_size_sec)

    return np.column_stack([lower, upper])


def solve_growth(model: object, bounds: np.ndarray) -> float:
    lb_override, ub_override = sanitize_bounds_for_lp(bounds)
    _, info = km.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        lb_override=lb_override,
        ub_override=ub_override,
    )
    return float(info["biomass_flux_per_s"])


def main() -> int:
    lines: list[str] = []

    def log(message: str = "") -> None:
        print(message)
        lines.append(message)

    try:
        model = km.load_default()
        dyn = cfb.load_default_dynamics()
        fixture = KarrWritebackFixture.from_mat(str(MAT_PATH))

        with h5py.File(TRACE_PATH, "r") as handle:
            def get3d(path: str, tick: int) -> np.ndarray:
                ds = handle[path]
                ref = ds[0, tick] if ds.shape[0] == 1 else ds[tick, 0]
                return np.asarray(handle[ref][()], dtype=np.float64)

            karr_pre = get3d("states_before/substrates", 0).T
            karr_enz = get3d("states_before/enzymes", 0).ravel()

        fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)

        oc_bounds = cfb.compute_bounds(
            substrates=karr_pre,
            enzymes=karr_enz,
            cell_dry_mass=dyn.cell_dry_mass,
            step_size_sec=dyn.step_size_sec,
            catalysis=model.catalysis,
            enz_bounds=model.enz_bounds,
            fba_reaction_bounds=fba_reaction_bounds,
            dyn=dyn,
            apply_protein_bounds=False,
        )
        faithful_bounds = karr_calc_bounds_faithful(
            substrates=karr_pre,
            enzymes=karr_enz,
            cell_dry_mass=dyn.cell_dry_mass,
            step_size_sec=dyn.step_size_sec,
            catalysis=model.catalysis,
            enz_bounds=model.enz_bounds,
            fba_reaction_bounds=fba_reaction_bounds,
            dyn=dyn,
        )
        oc_rule3_off_bounds = cfb.compute_bounds(
            substrates=karr_pre,
            enzymes=karr_enz,
            cell_dry_mass=dyn.cell_dry_mass,
            step_size_sec=dyn.step_size_sec,
            catalysis=model.catalysis,
            enz_bounds=model.enz_bounds,
            fba_reaction_bounds=fba_reaction_bounds,
            dyn=dyn,
            apply_directionality=False,
            apply_protein_bounds=False,
        )

        lb_diff_idx = [idx for idx in range(oc_bounds.shape[0]) if values_differ(oc_bounds[idx, 0], faithful_bounds[idx, 0])]
        ub_diff_idx = [idx for idx in range(oc_bounds.shape[0]) if values_differ(oc_bounds[idx, 1], faithful_bounds[idx, 1])]
        diff_rxn_idx = sorted(set(lb_diff_idx) | set(ub_diff_idx))

        diff_classes = Counter()
        for idx in lb_diff_idx:
            diff_classes[f"lb {classify_pair(oc_bounds[idx, 0], faithful_bounds[idx, 0])}"] += 1
        for idx in ub_diff_idx:
            diff_classes[f"ub {classify_pair(oc_bounds[idx, 1], faithful_bounds[idx, 1])}"] += 1

        oc_growth = solve_growth(model, oc_bounds)
        faithful_growth = solve_growth(model, faithful_bounds)
        oc_rule3_off_growth = solve_growth(model, oc_rule3_off_bounds)

        log("Probe: H10-refined NaN propagation vs Rule 3 paradox")
        log(f"Trace path: {TRACE_PATH}")
        log(f"Loaded fixture external index count: {fixture.fba_idx_external.size}")
        log(f"Reaction count: {oc_bounds.shape[0]}")
        log(f"Lower-bound diff reactions: {len(lb_diff_idx)}")
        log(f"Upper-bound diff reactions: {len(ub_diff_idx)}")
        log(f"Unique diff reactions: {len(diff_rxn_idx)}")

        if diff_rxn_idx:
            log("First 5 differing reactions:")
            for idx in diff_rxn_idx[:5]:
                parts = []
                if idx in lb_diff_idx:
                    parts.append(
                        "lb "
                        + classify_pair(oc_bounds[idx, 0], faithful_bounds[idx, 0])
                        + f" :: OC={render_scalar(oc_bounds[idx, 0])}, Karr={render_scalar(faithful_bounds[idx, 0])}"
                    )
                if idx in ub_diff_idx:
                    parts.append(
                        "ub "
                        + classify_pair(oc_bounds[idx, 1], faithful_bounds[idx, 1])
                        + f" :: OC={render_scalar(oc_bounds[idx, 1])}, Karr={render_scalar(faithful_bounds[idx, 1])}"
                    )
                log(f"  rxn[{idx}]: " + " | ".join(parts))
        else:
            log("First 5 differing reactions: none")

        if diff_classes:
            log("Diff classification counts:")
            for label, count in diff_classes.most_common():
                log(f"  {count:4d}  {label}")
        else:
            log("Diff classification counts: none")

        log("")
        log("Growth comparison (biomass_flux_per_s):")
        log(f"  OC baseline (all rules on):   {oc_growth:.12e}")
        log(f"  Karr-faithful bounds:         {faithful_growth:.12e}")
        log(f"  OC Rule 3 off:               {oc_rule3_off_growth:.12e}")

        if diff_rxn_idx and faithful_growth > oc_growth * 1.5:
            answer = (
                "ANSWER: bounds differ at "
                f"{len(diff_rxn_idx)} reactions; Karr-faithful bounds materially increase LP growth."
            )
        elif diff_rxn_idx:
            answer = (
                "ANSWER: bounds differ at "
                f"{len(diff_rxn_idx)} reactions, but Karr-faithful bounds do not materially restore LP growth."
            )
        else:
            answer = "ANSWER: bounds identical; LP behavior differs without an H10-visible bound divergence."
        log(answer)

        return_code = 0
    except Exception as exc:  # pragma: no cover - investigation logging path
        log(f"ANSWER: unable to determine due to {exc.__class__.__name__}: {exc}")
        return_code = 1
    finally:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Raw log saved to {LOG_PATH}")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
