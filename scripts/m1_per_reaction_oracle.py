"""M1 per-reaction oracle: Karr-native predicted vs Karr stored fluxs.

Now trivially Karr-vs-Karr: the new opencell.m1.karr_metabolism module
solves Karr's exact fitted FBA snapshot, then we compare its predicted
fluxes (504-col) against Karr's stored runtime fluxs[645] for every
metabolicConversion column that carries a WCM reaction ID.

No ID mapping table is required (this entire problem went away when we
dropped iPS189).

Outputs:
  - artifacts/M1_per_reaction_oracle.json
  - docs/phase5/M1_per_reaction_oracle.md

Run via .venv-wsl:
  wsl bash -lc 'source /mnt/e/opencell/.venv-wsl/bin/activate && \
                python /mnt/e/opencell/scripts/m1_per_reaction_oracle.py'
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from opencell.m1 import karr_metabolism as km

REPO = Path(__file__).resolve().parents[1]
OUT_JSON = REPO / "artifacts" / "M1_per_reaction_oracle.json"
OUT_MD = REPO / "docs" / "phase5" / "M1_per_reaction_oracle.md"

ACCEPTANCE_THRESHOLD = 1.0  # median |log2(predicted/karr_stored)| < 1.0


def _safe_log2_abs_ratio(p: float, k: float) -> float | None:
    if p == 0 or k == 0:
        return None
    if not (math.isfinite(p) and math.isfinite(k)):
        return None
    return math.log2(abs(p) / abs(k))


def _sign(p: float, k: float, tol: float = 1e-9) -> str:
    if abs(k) < tol and abs(p) < tol:
        return "both_zero"
    if abs(k) < tol:
        return "karr_zero_pred_nonzero"
    if abs(p) < tol:
        return "pred_zero_karr_nonzero"
    return "agree" if (p * k > 0) else "disagree"


def main() -> None:
    model = km.load_default()
    v, info = km.solve_fba(model, use_full_objective=True, sense="max")

    rows_all = km.per_reaction_comparison(model, v, nonzero_only=False)

    log2_ratios: list[float] = []
    sign_counts: dict[str, int] = {}
    enriched = []
    for r in rows_all:
        lr = _safe_log2_abs_ratio(r["predicted"], r["karr_stored"])
        s = _sign(r["predicted"], r["karr_stored"])
        sign_counts[s] = sign_counts.get(s, 0) + 1
        if lr is not None:
            log2_ratios.append(abs(lr))
        enriched.append({**r, "log2_abs_ratio": lr, "sign": s})

    median_abs = float(np.median(log2_ratios)) if log2_ratios else None
    p90_abs = float(np.percentile(log2_ratios, 90)) if log2_ratios else None
    n_within_2x = sum(1 for r in log2_ratios if r < 1.0)
    n_within_8x = sum(1 for r in log2_ratios if r < 3.0)

    acceptance = {
        "metric": "median_abs_log2_ratio",
        "threshold": ACCEPTANCE_THRESHOLD,
        "value": median_abs,
        "passed": (median_abs is not None and median_abs < ACCEPTANCE_THRESHOLD),
        "n_comparable": len(log2_ratios),
    }

    artifact = {
        "schema_version": "v2_karr_native",
        "kind": "M1_per_reaction_oracle",
        "module": "opencell.m1.karr_metabolism",
        "fixture": str(km.DEFAULT_FIXTURE_JSON.relative_to(REPO)),
        "lp": info,
        "stored_runtime": model.stored_runtime,
        "summary": {
            "n_metabolic_conversion_cols": sum(
                1 for x in model.fba_col_rxn_wcm if x is not None),
            "n_rows_emitted": len(rows_all),
            "n_comparable": len(log2_ratios),
            "median_abs_log2_ratio": median_abs,
            "p90_abs_log2_ratio": p90_abs,
            "n_within_2x": n_within_2x,
            "n_within_8x": n_within_8x,
            "sign_counts": sign_counts,
        },
        "acceptance": acceptance,
        "rows": enriched,
        "interpretation": (
            "Karr-native per-reaction oracle: opencell.m1.karr_metabolism "
            "solves Karr's fitted FBA exactly (S 376x504, RHS 376, full "
            "objective with biomass +1000 and 35 parsimony penalties, "
            "no enzyme bounds because they are post-step). Predicted "
            "fluxes are compared 1:1 against Karr's stored runtime "
            "fluxs[645] indexed by reactionWholeCellModelID -- no ID "
            "mapping required (iPS189 fully dropped). Acceptance: "
            "median |log2(predicted/karr_stored)| < 1.0 over reactions "
            "where both fluxes are nonzero. Sign disagreement on a "
            "reversible reaction indicates direction inversion under "
            "biomass-max vs Karr's runtime context."
        ),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(artifact, indent=2))

    lines = [
        "# M1 per-reaction validation oracle (Karr-native)",
        "",
        f"- Module: `{artifact['module']}`",
        f"- Fixture: `{artifact['fixture']}`",
        f"- LP: biomass flux = `{info['biomass_flux_per_h']:.4f} /h` "
        f"(stored = `{model.stored_runtime['growth_per_h']:.4f} /h`)",
        f"- Total nonzero predicted fluxes: `{info['n_nonzero']}`",
        "",
        "## Acceptance",
        f"- Metric: `median |log2(predicted/karr_stored)|`",
        f"- Threshold: `< {ACCEPTANCE_THRESHOLD}`",
        f"- Value: `{median_abs}`",
        f"- Comparable reactions (both nonzero): `{len(log2_ratios)}`",
        f"- **Passed: `{acceptance['passed']}`**",
        "",
        "## Summary",
        f"- Within 2x: `{n_within_2x}` / `{len(log2_ratios)}`",
        f"- Within 8x: `{n_within_8x}` / `{len(log2_ratios)}`",
        f"- p90 |log2 ratio|: `{p90_abs}`",
        f"- Sign counts: `{sign_counts}`",
        "",
        "## Top-disagreeing reactions (by |log2 ratio|, both nonzero)",
        "",
        "| WCM ID | fba col | predicted | karr stored | |log2 ratio| | sign |",
        "|---|---:|---:|---:|---:|---|",
    ]
    nonzero_rows = [r for r in enriched if r["log2_abs_ratio"] is not None]
    nonzero_rows.sort(key=lambda r: -abs(r["log2_abs_ratio"]))
    for r in nonzero_rows[:25]:
        lines.append(
            f"| `{r['wcm_id']}` | {r['fba_col']} | "
            f"{r['predicted']:.4g} | {r['karr_stored']:.4g} | "
            f"{abs(r['log2_abs_ratio']):.3f} | {r['sign']} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        artifact["interpretation"],
    ]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))

    print(f"wrote {OUT_JSON.relative_to(REPO)}")
    print(f"wrote {OUT_MD.relative_to(REPO)}")
    ratio = info["biomass_flux_per_h"] / model.stored_runtime["growth_per_h"]
    print(f"\nbiomass = {info['biomass_flux_per_h']:.4f} /h "
          f"(stored {model.stored_runtime['growth_per_h']:.4f} /h, "
          f"ratio {ratio:.3f}x)")
    print(f"per-reaction: median |log2 ratio| = {median_abs} "
          f"over {len(log2_ratios)} reactions; passed = {acceptance['passed']}")


if __name__ == "__main__":
    main()
