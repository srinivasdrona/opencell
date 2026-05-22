"""Phase B demo: M1+M2+M3 with dynamic FBA bounds for 60 simulated seconds.

What this demonstrates (and what it does NOT):

* M1 derives its 504-reaction flux bounds via Karr's calcFluxBounds()
  port (rules 1-5) every tick, from a private compartmented state
  (585, 3) initialised from Karr's snapshot.
* That internal cytosol slice is drained each tick by the negative
  NTP / amino-acid deltas that M2 (transcription) and M3 (translation)
  write into the shared `substrates` store: the first piece of real
  intra-cell feedback in the chassis.
* The static-bounds central-dogma demo (`scripts/demo_central_dogma.py`)
  remains the regression baseline; this script is a *companion* that
  reports how the dynamic-bound trajectory diverges, not a replacement.

Honest limits (Phase B):
* Enzyme counts (104,) are FROZEN at the snapshot.  Phase C will wire
  M3 protein counts into them.
* Rule 6 (protein bounds) is not run.
* M1 does NOT mirror its own production back to the shared store, so
  the cytosol view here decreases monotonically.  Phase C will close
  that loop.

Outputs:
* `artifacts/demo_central_dogma_dynamic.json` — summary stats.
* `artifacts/demo_central_dogma_dynamic.png` — trajectories of growth
  rate and four representative cytosol pools.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
T_END_S = 60.0


def proc_snapshot_pools(engine) -> dict[str, float]:
    """Reach into the M1 process to fetch the cytosol snapshot pool
    counts for the demand-side substrates.  Helper-derived (no
    hard-coded numbers)."""
    proc = engine.processes["m1_karr"]
    return {
        sid: float(proc._dyn.substrates_snapshot[idx, 0]) for sid, idx in proc._demand_idx_pairs
    }


def main() -> dict:
    eng = build_karr_m1_m2_m3_engine(dynamic_bounds=True)
    eng.update(T_END_S)
    ts = eng.emitter.get_timeseries()

    diag = ts["m1_dynamic_diagnostics"]
    growth = np.asarray(diag["growth_per_s"])
    n_changed = np.asarray(diag["n_active_bounds_changed"])

    cyt_keys = sorted(k for k in diag if k.startswith("cyt_"))
    cyt = {k: np.asarray(diag[k]) for k in cyt_keys}

    # Drop the t=0 initial-state emit (default 0.0); keep the per-tick
    # values from the first M1 tick onwards.
    growth_real = growth[1:]
    n_changed_real = n_changed[1:]

    # ------- self-consistency checks (no hard-coded numbers) --------
    checks: list[tuple[str, bool, str]] = []

    checks.append(
        (
            "C1: growth_per_s strictly positive on every tick",
            bool(np.all(growth_real > 0.0)),
            f"min={growth_real.min():.3e}, max={growth_real.max():.3e}",
        )
    )

    checks.append(
        (
            "C2: dynamic bounds actually differ from static",
            bool(np.all(n_changed_real > 0)),
            f"n_changed range [{int(n_changed_real.min())}, {int(n_changed_real.max())}]",
        )
    )

    # NTP cytosol pools.  In Karr's fitted snapshot, ATP and GTP have
    # nonzero cytosol counts (~36k each); CTP and UTP cytosol counts are
    # 0 (fast turnover species, kept near-zero in the steady state).
    # M2 writes consumption deltas for all four; M1 reads them but
    # clamps at 0 for pools already empty.
    snap = proc_snapshot_pools(eng)
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        v = cyt[f"cyt_{ntp}"][1:]
        diffs = np.diff(v)
        non_increasing = bool(np.all(diffs <= 1e-6))
        clamp_ok = bool(np.all(v >= 0.0))
        # If the snapshot pool is non-empty we expect to see drain;
        # otherwise we just expect the floor to hold at 0.
        if snap[ntp] > 0.0:
            ok = non_increasing and clamp_ok and bool(v[-1] < snap[ntp])
            tag = "drained-from-snapshot"
        else:
            ok = non_increasing and clamp_ok and bool(v[-1] == 0.0)
            tag = "snapshot-empty-stays-zero"
        checks.append(
            (
                f"C3-{ntp} ({tag})",
                ok,
                f"snapshot={snap[ntp]:.1f}, t1={v[0]:.1f}, end={v[-1]:.1f}",
            )
        )

    # Amino-acid pools: M3 now writes per-AA negative deltas using the
    # 20 standard-AA WCM IDs (which already live in M1's 585 substrate
    # vocabulary), so M1's cytosol pools for those AAs MUST drain or
    # stay at zero (if the snapshot started empty).  This is the Phase
    # C handshake: M3 demand reaches the dynamic-bounds chassis.
    for aa in ("ALA", "GLU", "LYS"):
        v = cyt[f"cyt_{aa}"][1:]
        non_increasing = bool(np.all(np.diff(v) <= 1e-9))
        clamp_ok = bool(np.all(v >= 0.0))
        if snap[aa] > 0.0:
            ok = non_increasing and clamp_ok and bool(v[-1] < snap[aa])
            tag = "drained-from-snapshot"
        else:
            ok = non_increasing and clamp_ok and bool(v[-1] == 0.0)
            tag = "snapshot-empty-stays-zero"
        checks.append(
            (
                f"C4-{aa} ({tag})",
                ok,
                f"snapshot={snap[aa]:.1f}, t1={v[0]:.1f}, end={v[-1]:.1f}",
            )
        )

    summary = {
        "t_end_s": T_END_S,
        "n_emitted_steps": int(growth.size),
        "growth_per_s": {
            "min": float(growth_real.min()),
            "mean": float(growth_real.mean()),
            "max": float(growth_real.max()),
        },
        "n_active_bounds_changed": {
            "min": int(n_changed_real.min()),
            "max": int(n_changed_real.max()),
        },
        "cytosol_first_last": {
            k.replace("cyt_", ""): {"t0": float(v[1]), "tend": float(v[-1])} for k, v in cyt.items()
        },
        "checks": [{"name": n, "passed": p, "detail": d} for n, p, d in checks],
        "all_checks_passed": all(p for _, p, _ in checks),
    }

    out_json = ARTIFACTS / "demo_central_dogma_dynamic.json"
    out_json.write_text(json.dumps(summary, indent=2))

    try:
        import matplotlib.pyplot as plt  # noqa: WPS433

        fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        t = np.arange(growth.size)
        axes[0].plot(t, growth, "b-")
        axes[0].set_ylabel("growth_per_s")
        axes[0].grid(True, alpha=0.3)
        for ntp in ("ATP", "CTP", "GTP", "UTP"):
            axes[1].plot(t, cyt[f"cyt_{ntp}"], label=ntp)
        axes[1].set_xlabel("emit step")
        axes[1].set_ylabel("cytosol count")
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        fig.suptitle("Phase B: dynamic FBA bounds, 60 s")
        fig.tight_layout()
        fig.savefig(ARTIFACTS / "demo_central_dogma_dynamic.png", dpi=110)
        plt.close(fig)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] plot skipped: {exc}")

    print(json.dumps(summary, indent=2))
    if not summary["all_checks_passed"]:
        raise SystemExit("dynamic demo: one or more checks FAILED")
    return summary


if __name__ == "__main__":
    main()
