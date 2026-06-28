"""Day-42 probe: isolated writeback audit.

Test: feed OC's writeback Karr's recorded flux + growth + pre_sub at
sample (s=0, t=1), compare OC's computed delta to Karr's recorded delta.

If they match (within RNG floor ~50 molecules L1), the writeback algorithm
is faithful and the L2.2 W1=161 gap is elsewhere (pre-LP allocator, post-clip,
or downstream).

If they don't match, we have an actual writeback bug.

Two modes:
  - "deterministic": replace stochasticRound with rint (eliminates RNG noise)
  - "stochastic": use _Mcg16807 with seed 0

Output: tmp/h_writeback_isolated.json + console table.
"""
import json
import sys
from pathlib import Path

import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
    ATP_HYDROLYSIS_SIGNS,
    CYTOSOL,
    EXTRACELLULAR,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807


class _DetRng:
    """Deterministic round-to-nearest (replaces _Mcg16807 for isolation)."""

    def stochastic_round(self, values):
        arr = np.asarray(values, dtype=np.float64)
        return np.rint(arr).astype(np.int64)


def load_karr_ground_truth(path: Path):
    with h5py.File(path, "r") as f:
        flux = np.array(f["flux"]).ravel().astype(np.float64)
        growth = float(np.array(f["growth"]).ravel()[0])
        pre_sub = np.array(f["pre_sub"]).T  # (585, 3) after transpose
        delta = np.array(f["delta"]).T  # (585, 3) after transpose
        post_sub = np.array(f["post_sub"]).T  # (585, 3) after transpose
    return flux, growth, pre_sub, delta, post_sub


def per_step_decompose_deterministic(flux, growth, pre_sub, fixture, step):
    """Compute each writeback step deterministically (no rounding).
    Returns dict of (step_name -> (585,3) array).
    """
    delta_steps = {}

    d1 = np.zeros((585, 3), dtype=np.float64)
    ext_flow = flux[fixture.fba_idx_external] * step
    d1[fixture.sub_idx_external, EXTRACELLULAR] -= ext_flow
    delta_steps["step1_nutrient_uptake_pre_round"] = d1

    d2 = np.zeros((585, 3), dtype=np.float64)
    int_flow = flux[fixture.fba_idx_internal]
    d2[fixture.sub_idx_internal, CYTOSOL] += int_flow
    delta_steps["step2_recycled_metabolites_pre_round"] = d2

    d3 = fixture.metabolism_new_production * growth * step
    delta_steps["step3_new_biomass_pre_round"] = d3.copy()

    d4 = np.zeros((585, 3), dtype=np.float64)
    unaccounted_qty = fixture.unaccounted_energy_consumption * growth * step
    d4[fixture.sub_idx_atp_hydrolysis, CYTOSOL] += ATP_HYDROLYSIS_SIGNS * unaccounted_qty
    delta_steps["step4_unaccounted_energy_pre_round"] = d4

    return delta_steps


def main():
    sample_path = REPO / "data" / "karr_fixtures" / "matlab_ground_truth" / "metab_flux_allocated_state_s000_tick1.mat"
    fixture_path = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"

    flux, growth, pre_sub, karr_delta, karr_post = load_karr_ground_truth(sample_path)
    fixture = KarrWritebackFixture.from_mat(fixture_path)
    step = fixture.step_size_sec

    print(f"Sample (s=0, t=1): growth={growth:.6e}, step={step}")
    print(f"  flux shape={flux.shape}, pre_sub shape={pre_sub.shape}, karr_delta shape={karr_delta.shape}")
    print(f"  karr_delta integer-valued: {np.all(karr_delta == karr_delta.astype(np.int64))}")
    print(f"  karr_delta L1 sum: {np.abs(karr_delta).sum():.0f}")
    print(f"  karr_delta nnz: {np.sum(karr_delta != 0)}")
    print()

    # MODE 1: deterministic
    det_rng = _DetRng()
    oc_delta_det = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(),
        v_504=flux,
        growth_per_s=growth,
        fixture=fixture,
        rng=det_rng,
        step_size_sec=step,
    )

    # MODE 2: stochastic with seed 0
    sto_rng = _Mcg16807(seed=1)
    oc_delta_sto = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(),
        v_504=flux,
        growth_per_s=growth,
        fixture=fixture,
        rng=sto_rng,
        step_size_sec=step,
    )

    # Compare
    def cmp(label, oc, karr):
        diff = oc.astype(np.int64) - karr.astype(np.int64)
        return {
            "label": label,
            "oc_l1": int(np.abs(oc).sum()),
            "karr_l1": int(np.abs(karr).sum()),
            "diff_l1": int(np.abs(diff).sum()),
            "diff_linf": int(np.abs(diff).max()),
            "diff_nnz": int(np.sum(diff != 0)),
            "diff_per_compartment_l1": [int(np.abs(diff[:, c]).sum()) for c in range(3)],
        }

    r_det = cmp("deterministic (rint)", oc_delta_det, karr_delta)
    r_sto = cmp("stochastic mcg16807 seed=1", oc_delta_sto, karr_delta)

    print("Comparison vs Karr recorded delta at sample (s=0, t=1):")
    print(f"{'mode':<35s} {'oc_L1':>10s} {'karr_L1':>10s} {'diff_L1':>10s} {'diff_Linf':>10s} {'diff_nnz':>10s}")
    print("-" * 95)
    for r in [r_det, r_sto]:
        print(f"{r['label']:<35s} {r['oc_l1']:>10d} {r['karr_l1']:>10d} {r['diff_l1']:>10d} {r['diff_linf']:>10d} {r['diff_nnz']:>10d}")
    print()

    print("Per-compartment diff L1 [cyt, ext, mem]:")
    for r in [r_det, r_sto]:
        print(f"  {r['label']:<35s} {r['diff_per_compartment_l1']}")
    print()

    # Per-step pre-round decomposition (deterministic, no rounding)
    print("Per-step pre-rounding magnitudes (deterministic):")
    steps = per_step_decompose_deterministic(flux, growth, pre_sub, fixture, step)
    for name, d in steps.items():
        l1 = float(np.abs(d).sum())
        per_c = [float(np.abs(d[:, c]).sum()) for c in range(3)]
        print(f"  {name:<45s} L1={l1:>14.2f}  per_comp={per_c}")
    print(f"  sum_pre_round                                 L1={sum(float(np.abs(d).sum()) for d in steps.values()):>14.2f}")

    # Where do the largest mismatches live?
    diff_det = oc_delta_det.astype(np.int64) - karr_delta.astype(np.int64)
    abs_diff_flat = np.abs(diff_det).sum(axis=1)  # per-WID
    top20_idx = np.argsort(-abs_diff_flat)[:20]
    print()
    print("Top-20 per-WID mismatches (deterministic mode):")
    print(f"{'wid_row':>10s} {'diff_per_comp':>30s} {'oc_per_comp':>30s} {'karr_per_comp':>30s}")
    for idx in top20_idx:
        if abs_diff_flat[idx] == 0:
            break
        d = diff_det[idx, :].tolist()
        o = oc_delta_det[idx, :].tolist()
        k = karr_delta[idx, :].astype(np.int64).tolist()
        print(f"{idx:>10d} {str(d):>30s} {str(o):>30s} {str(k):>30s}")

    # Write JSON
    out_path = REPO / "tmp" / "h_writeback_isolated.json"
    out = {
        "sample": {"seed": 0, "tick": 1},
        "growth_per_s": growth,
        "step_size_sec": step,
        "karr_delta_l1": int(np.abs(karr_delta).sum()),
        "karr_delta_nnz": int(np.sum(karr_delta != 0)),
        "results": [r_det, r_sto],
        "per_step_pre_round_l1": {name: float(np.abs(d).sum()) for name, d in steps.items()},
        "top20_per_wid_diff_det": [
            {
                "wid_row": int(i),
                "diff_per_comp": diff_det[i, :].tolist(),
                "oc_per_comp": oc_delta_det[i, :].astype(int).tolist(),
                "karr_per_comp": karr_delta[i, :].astype(int).tolist(),
            }
            for i in top20_idx if abs_diff_flat[i] > 0
        ],
    }
    out_path.write_text(json.dumps(out, indent=2))
    print()
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
