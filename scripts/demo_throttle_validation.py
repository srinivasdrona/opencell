"""Phase C.3/C.4 validation snapshot: three modes side-by-side.

Runs the M1+M2+M3 dynamic-bounds composer for 60 simulated seconds in
three modes and captures the observable divergence:

  * off          - throttle disabled, no replenishment (Phase B/C.1)
  * throttle     - throttle on, no replenishment (Phase C.3 alone)
  * t+replenish  - throttle on AND calibrated pool replenishment (Phase C.4)

What we expect
--------------
* Karr snapshot has CTP=0, UTP=0 in cytosol (fast-turnover species).
  M2's `f` is therefore 0 from tick 0 in `throttle` mode -> RNA decays.
* In `t+replenish`, M1 injects baseline NTP/AA replenishment after the
  FBA solve, so within 1-2 ticks the throttle unfreezes and RNA/protein
  trajectories track the `off` baseline (self-stabilising loop).
* M3 throttle stays silent (AAs abundant, f=1) in all three modes.

Outputs
-------
* `artifacts/demo_throttle_validation.json` - summary stats + delta
* `artifacts/demo_throttle_validation.png` - 4-panel comparison
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
T_END_S = 60.0


def _run(enable_throttle: bool, enable_pool_replenishment: bool = False) -> dict:
    eng = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=enable_throttle,
        enable_pool_replenishment=enable_pool_replenishment,
    )
    eng.update(T_END_S)
    ts = eng.emitter.get_timeseries()

    diag = ts["m1_dynamic_diagnostics"]
    growth = np.asarray(diag["growth_per_s"])
    cyt = {k: np.asarray(v) for k, v in diag.items() if k.startswith("cyt_")}

    rna = ts["rna"]["counts"]
    protein = ts["protein"]["counts"]
    rna_total = np.sum([np.asarray(v) for v in rna.values()], axis=0)
    protein_total = np.sum([np.asarray(v) for v in protein.values()], axis=0)

    return {
        "growth": growth,
        "cyt": cyt,
        "rna_total": rna_total,
        "protein_total": protein_total,
        "rna_n_genes": len(rna),
        "protein_n": len(protein),
    }


def main() -> dict:
    print("running throttle-off (Phase B/C.1 baseline)...")
    off = _run(enable_throttle=False)
    print("running throttle-on, no replenishment (Phase C.3)...")
    on = _run(enable_throttle=True)
    print("running throttle-on + replenishment (Phase C.4)...")
    rep = _run(enable_throttle=True, enable_pool_replenishment=True)

    growth_off = off["growth"][1:]
    growth_on = on["growth"][1:]
    growth_rep = rep["growth"][1:]
    rna_off = off["rna_total"]
    rna_on = on["rna_total"]
    rna_rep = rep["rna_total"]
    prot_off = off["protein_total"]
    prot_on = on["protein_total"]
    prot_rep = rep["protein_total"]

    rna_delta_pct_on = 100.0 * (rna_on[-1] - rna_off[-1]) / rna_off[-1]
    rna_delta_pct_rep = 100.0 * (rna_rep[-1] - rna_off[-1]) / rna_off[-1]
    prot_delta_pct_on = 100.0 * (prot_on[-1] - prot_off[-1]) / prot_off[-1]
    prot_delta_pct_rep = 100.0 * (prot_rep[-1] - prot_off[-1]) / prot_off[-1]

    growth_max_abs_diff_on = float(np.max(np.abs(growth_on - growth_off)))
    growth_max_abs_diff_rep = float(np.max(np.abs(growth_rep - growth_off)))

    # AA pool comparison (M3-driven keys).
    aa_keys = [
        k
        for k in off["cyt"]
        if k.startswith("cyt_")
        and len(k) == 7
        and k[4:] in ("ALA", "GLU", "LYS", "MET", "TRP", "CYS")
    ]
    aa_diff: dict = {}
    for k in aa_keys:
        aa = k[4:]
        aa_diff[aa] = {
            "off_end": float(off["cyt"][k][-1]),
            "on_end": float(on["cyt"][k][-1]),
            "rep_end": float(rep["cyt"][k][-1]),
            "abs_diff_on": float(on["cyt"][k][-1] - off["cyt"][k][-1]),
            "abs_diff_rep": float(rep["cyt"][k][-1] - off["cyt"][k][-1]),
        }

    # NTP pool comparison.
    ntp_diff: dict = {}
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        k = f"cyt_{ntp}"
        ntp_diff[ntp] = {
            "off_end": float(off["cyt"][k][-1]),
            "on_end": float(on["cyt"][k][-1]),
            "rep_end": float(rep["cyt"][k][-1]),
            "abs_diff_on": float(on["cyt"][k][-1] - off["cyt"][k][-1]),
            "abs_diff_rep": float(rep["cyt"][k][-1] - off["cyt"][k][-1]),
        }

    summary = {
        "t_end_s": T_END_S,
        "growth_per_s": {
            "off": {
                "min": float(growth_off.min()),
                "mean": float(growth_off.mean()),
                "max": float(growth_off.max()),
            },
            "on": {
                "min": float(growth_on.min()),
                "mean": float(growth_on.mean()),
                "max": float(growth_on.max()),
            },
            "rep": {
                "min": float(growth_rep.min()),
                "mean": float(growth_rep.mean()),
                "max": float(growth_rep.max()),
            },
            "max_abs_diff_on_vs_off": growth_max_abs_diff_on,
            "max_abs_diff_rep_vs_off": growth_max_abs_diff_rep,
        },
        "rna_total_count": {
            "off_t0": float(rna_off[0]),
            "off_end": float(rna_off[-1]),
            "on_t0": float(rna_on[0]),
            "on_end": float(rna_on[-1]),
            "rep_t0": float(rna_rep[0]),
            "rep_end": float(rna_rep[-1]),
            "delta_pct_on": float(rna_delta_pct_on),
            "delta_pct_rep": float(rna_delta_pct_rep),
        },
        "protein_total_count": {
            "off_t0": float(prot_off[0]),
            "off_end": float(prot_off[-1]),
            "on_t0": float(prot_on[0]),
            "on_end": float(prot_on[-1]),
            "rep_t0": float(prot_rep[0]),
            "rep_end": float(prot_rep[-1]),
            "delta_pct_on": float(prot_delta_pct_on),
            "delta_pct_rep": float(prot_delta_pct_rep),
        },
        "ntp_pool_diff": ntp_diff,
        "aa_pool_diff_sample": aa_diff,
    }

    out_json = ARTIFACTS / "demo_throttle_validation.json"
    out_json.write_text(json.dumps(summary, indent=2))

    try:
        import matplotlib.pyplot as plt  # noqa: WPS433

        fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
        t = np.arange(off["growth"].size)
        axes[0, 0].plot(t, off["growth"], "b-", label="off")
        axes[0, 0].plot(t, on["growth"], "r--", label="throttle")
        axes[0, 0].plot(t, rep["growth"], "g-.", label="t+replenish")
        axes[0, 0].set_title("growth_per_s")
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        axes[0, 1].plot(t[: rna_off.size], rna_off, "b-", label="off")
        axes[0, 1].plot(t[: rna_on.size], rna_on, "r--", label="throttle")
        axes[0, 1].plot(t[: rna_rep.size], rna_rep, "g-.", label="t+replenish")
        axes[0, 1].set_title("total RNA count (525 genes)")
        axes[0, 1].legend()
        axes[0, 1].grid(True, alpha=0.3)

        axes[1, 0].plot(t[: prot_off.size], prot_off, "b-", label="off")
        axes[1, 0].plot(t[: prot_on.size], prot_on, "r--", label="throttle")
        axes[1, 0].plot(t[: prot_rep.size], prot_rep, "g-.", label="t+replenish")
        axes[1, 0].set_title("total protein count (482 monomers)")
        axes[1, 0].set_xlabel("emit step")
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)

        for ntp, color in zip(("ATP", "CTP", "GTP", "UTP"), "kbrg", strict=False):
            axes[1, 1].plot(t, off["cyt"][f"cyt_{ntp}"], color + "-", label=f"{ntp} off", alpha=0.5)
            axes[1, 1].plot(t, on["cyt"][f"cyt_{ntp}"], color + "--", label=f"{ntp} thr", alpha=0.7)
            axes[1, 1].plot(t, rep["cyt"][f"cyt_{ntp}"], color + ":", label=f"{ntp} rep", alpha=0.9)
        axes[1, 1].set_title("cytosol NTP pools")
        axes[1, 1].set_xlabel("emit step")
        axes[1, 1].legend(fontsize=6, ncol=3)
        axes[1, 1].grid(True, alpha=0.3)

        fig.suptitle("Phase C.3/C.4 throttle validation: off / throttle / t+replenish")
        fig.tight_layout()
        fig.savefig(ARTIFACTS / "demo_throttle_validation.png", dpi=110)
        plt.close(fig)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] plot skipped: {exc}")

    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
