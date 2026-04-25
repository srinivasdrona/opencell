"""End-to-end demo of the M1+M2+M3 (Karr central-dogma) chassis.

Builds and runs the Vivarium engine that hosts:

  * M1 -- Karr metabolism (645 reactions, 585 substrate placeholders)
  * M2 -- Karr-prescribed transcription (525 RNAs, NTP writeback)
  * M3 -- Karr-prescribed translation  (482 proteins, AA writeback)

It then runs a series of *independent self-consistency checks* on the
trajectory.  None of the pass/fail thresholds is a hard-coded biology
value; every "expected" quantity is derived from the model fixture
itself or from the v2 mechanism modules.  This keeps the demo honest:
if either the chassis or the underlying models change, the checks
recompute from the new state.

Categories of checks (all evaluated, none fatal-fast):

  C1. **Engine ran**: requested duration matches emitted t_end.
  C2. **Steady state**: RNA + protein variances after t=1s are ~0
      (M2 v1 + M3 v1 are SS-by-construction; deviation = bug).
  C3. **NTP writeback conservation**: emitted substrate delta over the
      run equals -dt * ntp_consumption_per_s(model)[ntp] within tol.
      Compares the engine's actual emit to the *helper function's*
      independent integration of the same model.
  C4. **AA_total writeback conservation**: same for AA bulk.
  C5. **Dimensions**: 645/525/482 emitted, derived from model attrs.
  C6. **Growth rate stable**: M1 growth_per_h variance ~0.
  C7. **M2 v2 conservation invariant**: total_nt_polymerization_per_s
      computed from the v2 mechanism equals N_active * elongation_rate
      from the SAME fixture (pure invariant, no oracle target).
  C8. **M3 v2 conservation invariant**: same for ribosomes.
  C9. **M2 v1 vs v2 (cycle-averaged)**: documents the 2x snapshot vs
      cycle-averaged factor; reports median |log2| ratio.
  C10. **M3 v1 vs v2 ratio**: documents the ~23x gap; reports the
       observed ratio relative to the documented band [10, 50].
  C11. **Identity check on initial state**: emitted t=0 RNA matches
       model.expression[:, condition], protein matches counts_mature.

Outputs:
  artifacts/demo_central_dogma.json   numerical summary + per-check status
  artifacts/demo_central_dogma.png    multi-panel trajectory figure

This is **not** a unit test - it is an integration demo.  Failures are
reported as a banner at the end with a non-zero exit code.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m2 import transcription_v2 as txv2
from opencell.m3 import translation as tl
from opencell.m3 import translation_v2 as tlv2
from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine

ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)

T_END_S = 60.0
TIME_STEP_S = 1.0
CONDITION = 1
TOL_REL = 1e-6
TOL_NTP_REL = 0.02   # writeback uses uniform 1/4 split; 2% covers FP rounding
TOL_AA_REL = 0.02


def _check(name: str, ok: bool, detail: dict) -> dict:
    return {"name": name, "ok": bool(ok), **detail}


def _rel_err(actual: float, expected: float) -> float:
    if expected == 0.0:
        return abs(actual)
    return abs(actual - expected) / abs(expected)


def main() -> int:
    print("Loading models...")
    m1 = km.load_default()
    m2 = tx.load_default()
    m3 = tl.load_default()
    m2v2 = txv2.load_default()
    m3v2 = tlv2.load_default()

    print(f"Building M1+M2+M3 engine (dt={TIME_STEP_S}s, t_end={T_END_S}s)...")
    eng = build_karr_m1_m2_m3_engine(
        m1_model=m1, m2_model=m2, m3_model=m3,
        time_step_s=TIME_STEP_S, condition=CONDITION,
    )

    t0 = time.perf_counter()
    eng.update(T_END_S)
    wall_s = time.perf_counter() - t0
    print(f"Engine update done in {wall_s:.2f}s wall.")

    ts = eng.emitter.get_timeseries()
    t = np.asarray(ts["time"], dtype=float)

    checks: list[dict] = []

    # -- C1 engine ran ---------------------------------------------------
    checks.append(_check(
        "C1_engine_ran",
        ok=(t[-1] >= T_END_S - 1e-9 and len(t) >= int(T_END_S / TIME_STEP_S)),
        detail={"t_end_emit": float(t[-1]), "t_end_request": T_END_S,
                "n_emit": int(len(t))},
    ))

    # -- C5 dimensions (derived from model attrs) ------------------------
    n_rxn = len(m1.rxn_wcm_ids_645)
    n_rna = m2.n_genes
    n_prot = m3.n_proteins
    rxn_emit = len(ts["metabolic_reaction"]["fluxs"])
    rna_emit = len(ts["rna"]["counts"])
    prot_emit = len(ts["protein"]["counts"])
    checks.append(_check(
        "C5_dimensions",
        ok=(rxn_emit == n_rxn and rna_emit == n_rna and prot_emit == n_prot),
        detail={"emitted": [rxn_emit, rna_emit, prot_emit],
                "expected_from_models": [n_rxn, n_rna, n_prot]},
    ))

    # -- C6 growth-per-h stable ------------------------------------------
    g = np.asarray(ts["metabolic_reaction"]["growth_per_h"], dtype=float)
    g_range = float(g[1:].max() - g[1:].min())
    checks.append(_check(
        "C6_growth_stable",
        ok=(g_range < 1e-9),
        detail={"growth_per_h_initial": float(g[0]),
                "growth_per_h_range_after_t1": g_range},
    ))

    # -- C2 RNA + protein steady state -----------------------------------
    rna_max_range = 0.0
    rna_worst_id = None
    for gid, series in ts["rna"]["counts"].items():
        a = np.asarray(series, dtype=float)
        rng = float(a[1:].max() - a[1:].min()) if a.size > 1 else 0.0
        if rng > rna_max_range:
            rna_max_range = rng
            rna_worst_id = gid
    prot_max_range = 0.0
    prot_worst_id = None
    for pid, series in ts["protein"]["counts"].items():
        a = np.asarray(series, dtype=float)
        rng = float(a[1:].max() - a[1:].min()) if a.size > 1 else 0.0
        if rng > prot_max_range:
            prot_max_range = rng
            prot_worst_id = pid
    checks.append(_check(
        "C2_steady_state_after_t1",
        ok=(rna_max_range < 1e-3 and prot_max_range < 1.0),
        detail={"rna_max_range": rna_max_range, "rna_worst": rna_worst_id,
                "prot_max_range": prot_max_range, "prot_worst": prot_worst_id},
    ))

    # -- C3 NTP writeback conservation -----------------------------------
    expected_ntp = tx.ntp_consumption_per_s(m2, condition=CONDITION)
    ntp_results = {}
    ntp_ok = True
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        a = np.asarray(ts["substrates"][ntp], dtype=float)
        observed_delta = float(a[-1] - a[0])
        expected_delta = -(t[-1] - t[0]) * expected_ntp[ntp]
        rel = _rel_err(observed_delta, expected_delta)
        ntp_results[ntp] = {
            "observed_delta": observed_delta,
            "expected_delta": expected_delta,
            "rel_err": rel,
        }
        if rel > TOL_NTP_REL:
            ntp_ok = False
    checks.append(_check(
        "C3_ntp_writeback_vs_helper",
        ok=ntp_ok,
        detail={"per_ntp": ntp_results,
                "total_nt_per_s_helper": expected_ntp["_total_nt_per_s"]},
    ))

    # -- C4 AA_total writeback conservation ------------------------------
    aa_helper = tl.aa_consumption_per_s(m3)
    aa_series = np.asarray(ts["substrates"]["AA_total"], dtype=float)
    observed_aa_delta = float(aa_series[-1] - aa_series[0])
    expected_aa_delta = -(t[-1] - t[0]) * aa_helper["_total_aa_per_s"]
    aa_rel = _rel_err(observed_aa_delta, expected_aa_delta)
    checks.append(_check(
        "C4_aa_total_writeback_vs_helper",
        ok=(aa_rel < TOL_AA_REL),
        detail={"observed_delta": observed_aa_delta,
                "expected_delta": expected_aa_delta,
                "rel_err": aa_rel,
                "total_aa_per_s_helper": aa_helper["_total_aa_per_s"]},
    ))

    # -- C7 M2 v2 conservation invariant ---------------------------------
    total_nt_v2 = txv2.total_nt_polymerization_per_s(m2v2)
    inv_v2_m2 = m2v2.n_active_rnap * m2v2.elongation_rate_nt_per_s
    rel_inv_m2 = _rel_err(total_nt_v2, inv_v2_m2)
    checks.append(_check(
        "C7_m2v2_conservation_invariant",
        ok=(rel_inv_m2 < TOL_REL),
        detail={"total_nt_per_s_from_predictor": total_nt_v2,
                "n_active_x_elong_from_fixture": float(inv_v2_m2),
                "rel_err": rel_inv_m2},
    ))

    # -- C8 M3 v2 conservation invariant ---------------------------------
    total_aa_v2 = tlv2.total_aa_polymerization_per_s(m3v2)
    inv_v2_m3 = m3v2.n_active_ribosomes * m3v2.elongation_rate_aa_per_s
    rel_inv_m3 = _rel_err(total_aa_v2, inv_v2_m3)
    checks.append(_check(
        "C8_m3v2_conservation_invariant",
        ok=(rel_inv_m3 < TOL_REL),
        detail={"total_aa_per_s_from_predictor": total_aa_v2,
                "n_active_x_elong_from_fixture": float(inv_v2_m3),
                "rel_err": rel_inv_m3},
    ))

    # -- C9 M2 v1 vs v2 cross-comparison ---------------------------------
    pred_gene_snapshot = txv2.predict_gene_synthesis_per_s(m2v2)
    pred_gene_cycle = txv2.predict_gene_synthesis_per_s(
        m2v2, n_active=2.0 * m2v2.n_active_rnap,
    )
    summary_snap = txv2.compare_to_karr(
        pred_gene_snapshot, m2v2.karr_fitted_synth_per_s,
    )
    summary_cycle = txv2.compare_to_karr(
        pred_gene_cycle, m2v2.karr_fitted_synth_per_s,
    )
    # NOT a hard threshold; both numbers reported. Pass = cycle-averaged
    # is closer than snapshot (sanity that direction is right).
    checks.append(_check(
        "C9_m2v2_cycle_avg_better_than_snapshot",
        ok=(summary_cycle["median_abs_log2_ratio"]
            < summary_snap["median_abs_log2_ratio"]),
        detail={"snapshot": summary_snap, "cycle_2x": summary_cycle},
    ))

    # -- C10 M3 v1 vs v2 ratio (documented ~23x gap) ---------------------
    karr_total_v1 = float(np.sum(m3v2.karr_v1_synth_per_s
                                 * m3v2.length_aa))
    ratio_v2_over_v1 = total_aa_v2 / karr_total_v1 if karr_total_v1 > 0 else float("inf")
    checks.append(_check(
        "C10_m3_v2_over_v1_in_documented_band",
        ok=(10.0 < ratio_v2_over_v1 < 50.0),
        detail={"v2_total_aa_per_s": total_aa_v2,
                "v1_total_aa_per_s": karr_total_v1,
                "ratio_v2_v1": ratio_v2_over_v1,
                "documented_band": [10.0, 50.0]},
    ))

    # -- C11 initial state matches model -----------------------------------
    rna0 = {gid: float(series[0]) for gid, series in ts["rna"]["counts"].items()}
    prot0 = {pid: float(series[0]) for pid, series in ts["protein"]["counts"].items()}
    rna_max_dev = max(
        abs(rna0[g] - float(m2.expression[i, CONDITION]))
        for i, g in enumerate(m2.gene_wcm_ids)
    )
    prot_max_dev = max(
        abs(prot0[p] - float(m3.counts_mature[i]))
        for i, p in enumerate(m3.protein_wcm_ids)
    )
    checks.append(_check(
        "C11_initial_state_matches_models",
        ok=(rna_max_dev < TOL_REL and prot_max_dev < TOL_REL),
        detail={"rna_max_abs_dev_from_expression": rna_max_dev,
                "protein_max_abs_dev_from_counts_mature": prot_max_dev},
    ))

    # ---- Plot ----------------------------------------------------------
    fig, axes = plt.subplots(4, 1, figsize=(9.5, 12.0), sharex=True)

    # Panel 1: NTP substrates (should decay linearly)
    ax = axes[0]
    for ntp, color in [("ATP", "tab:blue"), ("CTP", "tab:orange"),
                       ("GTP", "tab:green"), ("UTP", "tab:red")]:
        a = np.asarray(ts["substrates"][ntp], dtype=float)
        ax.plot(t, a, color=color, lw=1.5, label=f"{ntp} (engine)")
        # overlay the helper-function-predicted line from t=0 baseline
        slope = -expected_ntp[ntp]
        ax.plot(t, a[0] + slope * t, color=color, lw=0.8, ls=":",
                alpha=0.6, label=f"{ntp} predicted ({slope:.4g}/s)")
    ax.set_ylabel("NTP substrate (placeholder units)")
    ax.set_title("C3 NTP writeback: solid=engine emit, dotted=helper-function prediction")
    ax.legend(fontsize=7, loc="lower left", ncol=2)
    ax.grid(alpha=0.3)

    # Panel 2: AA_total
    ax = axes[1]
    ax.plot(t, aa_series, color="tab:purple", lw=1.6, label="AA_total (engine)")
    aa_slope = -aa_helper["_total_aa_per_s"]
    ax.plot(t, aa_series[0] + aa_slope * t, color="tab:purple",
            lw=0.8, ls=":", alpha=0.7,
            label=f"AA_total predicted ({aa_slope:.4g}/s)")
    ax.set_ylabel("AA_total (placeholder units)")
    ax.set_title("C4 AA writeback: solid=engine, dotted=helper")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(alpha=0.3)

    # Panel 3: Growth + a few representative RNAs
    ax = axes[2]
    ax.plot(t, g, color="black", lw=1.6, label="growth_per_h (M1)")
    ax.set_ylabel("growth_per_h", color="black")
    ax.tick_params(axis="y", labelcolor="black")
    ax2 = ax.twinx()
    # pick the 4 highest-expressed RNAs as witnesses
    expr_idx = np.argsort(m2.expression[:, CONDITION])[-4:]
    for i in expr_idx:
        gid = m2.gene_wcm_ids[i]
        a = np.asarray(ts["rna"]["counts"][gid], dtype=float)
        ax2.plot(t, a, lw=1.2, alpha=0.85, label=f"RNA[{gid}]")
    ax2.set_ylabel("RNA copies (top-4 expressed)")
    ax2.legend(fontsize=7, loc="upper right")
    ax.set_title("C2/C6: growth + RNA stable at SS (flat lines expected)")
    ax.grid(alpha=0.3)

    # Panel 4: a few representative proteins
    ax = axes[3]
    ct_idx = np.argsort(m3.counts_mature)[-5:]
    for i in ct_idx:
        pid = m3.protein_wcm_ids[i]
        a = np.asarray(ts["protein"]["counts"][pid], dtype=float)
        ax.plot(t, a, lw=1.2, alpha=0.85, label=f"P[{pid}]")
    ax.set_xlabel("time (s, simulated)")
    ax.set_ylabel("protein copies (top-5 abundant)")
    ax.set_title("C2: top-5 proteins stable at SS (flat expected)")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(alpha=0.3)

    fig.suptitle(
        "OpenCell central-dogma demo (M1 + M2 + M3 chassis)",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig_path = ARTIFACT_DIR / "demo_central_dogma.png"
    fig.savefig(fig_path, dpi=130)
    plt.close(fig)
    print(f"Wrote {fig_path}")

    # ---- JSON summary --------------------------------------------------
    summary = {
        "config": {
            "t_end_s": T_END_S,
            "time_step_s": TIME_STEP_S,
            "condition": CONDITION,
            "tol_rel": TOL_REL,
            "tol_ntp_rel": TOL_NTP_REL,
            "tol_aa_rel": TOL_AA_REL,
        },
        "wall_seconds": wall_s,
        "n_emit_steps": int(len(t)),
        "model_dimensions_from_attrs": {
            "n_reactions": n_rxn, "n_rna": n_rna, "n_protein": n_prot,
        },
        "checks": checks,
        "all_pass": all(c["ok"] for c in checks),
    }
    json_path = ARTIFACT_DIR / "demo_central_dogma.json"
    json_path.write_text(json.dumps(summary, indent=2, default=float))
    print(f"Wrote {json_path}")

    # ---- Banner --------------------------------------------------------
    print("")
    print("=" * 64)
    print("Central-dogma chassis demo: per-check status")
    print("=" * 64)
    for c in checks:
        mark = "PASS" if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']}")
    print("=" * 64)
    if summary["all_pass"]:
        print("All checks passed.")
        return 0
    print("One or more checks FAILED. See artifacts/demo_central_dogma.json")
    return 1


if __name__ == "__main__":
    sys.exit(main())
