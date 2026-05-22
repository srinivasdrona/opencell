"""Phase E.0 — first phenotype validation report.

Runs all phenotype extractors and prints a markdown table summarising
predicted vs target vs status. This is the deliverable companion to
the pytest-based assertions in tests/phaseE/.

Usage:  python scripts/phase_e_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

from opencell.analysis import phenotypes as ph
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data" / "karr_fixtures" / "karr_phenotype_targets.json"


def fmt(x: float) -> str:
    if x == 0:
        return "0"
    if abs(x) >= 1e4 or abs(x) < 1e-3:
        return f"{x:+.4e}"
    return f"{x:+.4f}"


def main() -> None:
    with TARGETS.open() as f:
        spec_root = json.load(f)
    specs = spec_root["phenotypes"]

    print("# Phase E.0 — Phenotype Validation Report")
    print(f"\nTargets fixture: {TARGETS.relative_to(ROOT)}")
    print(f"Schema:          {spec_root['schema_version']}\n")

    m1 = km.load_default()
    m2 = tx.load_default()
    m3 = tl.load_default()

    extractors = [
        ("p1_growth_per_s", lambda: ph.measure_growth_per_s(m1)),
        ("p2_doubling_time_h", lambda: ph.measure_doubling_time_h(m1)),
        ("p3_fba_oracle_median_log2_ratio", lambda: ph.measure_fba_oracle_median_log2(m1)),
        ("p4_glucose_uptake_TX_GLCPTS", lambda: ph.measure_glucose_uptake(m1)),
        ("p5_mrna_total_chassis_wiring", lambda: ph.measure_mrna_total_chassis_wiring(m2)),
        ("p6_protein_total_chassis_wiring", lambda: ph.measure_protein_total_chassis_wiring(m3)),
        ("p7_mrna_stability_over_20s", lambda: ph.measure_mrna_stability(20)),
        ("p8_protein_stability_over_20s", lambda: ph.measure_protein_stability(20)),
        ("p9_aa_pool_stability_over_20s", lambda: ph.measure_aa_pool_stability(20)),
        ("p10_cell_dry_mass_g", lambda: ph.measure_cell_dry_mass(m1, m2, m3)),
    ]

    rows = []
    for key, extractor in extractors:
        spec = specs[key]
        try:
            m = extractor()
            predicted = m.predicted
            target = m.target
            unit = m.unit
        except Exception as e:
            rows.append(
                (key, "ERROR", "-", "-", "-", spec.get("category", "?"), f"{type(e).__name__}: {e}")
            )
            continue

        # Status logic mirrors the test assertions.
        status = "?"
        detail = ""
        if "tol_rel_min" in spec and "tol_rel_max" in spec and target:
            ratio = predicted / target
            inside = spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"]
            status = "PASS" if inside else "FAIL"
            detail = f"ratio={ratio:.3f}"
        elif "tol_abs_max" in spec:
            status = "PASS" if predicted <= spec["tol_abs_max"] else "FAIL"
            detail = f"abs<= {spec['tol_abs_max']}"
        elif "tol_rel" in spec and target:
            rel = abs(predicted - target) / target if target else float("inf")
            status = "PASS" if rel < spec["tol_rel"] else "FAIL"
            detail = f"rel_err={rel:.3e}"
        elif "tol_rel" in spec:  # stability tests, no target
            status = "PASS" if predicted < spec["tol_rel"] else "FAIL"
            detail = f"drift={predicted:.3e}"

        if spec.get("expected_status") == "fail":
            status = (
                f"XFAIL (expected; {spec.get('fail_reason', '')[:80]}...)"
                if status == "FAIL"
                else "UNEXPECTED PASS"
            )

        rows.append(
            (
                key,
                status,
                fmt(predicted),
                fmt(target) if target is not None else "-",
                unit,
                spec.get("category", "?"),
                detail,
            )
        )

    # Render markdown table.
    print("| # | Phenotype | Status | Predicted | Target | Unit | Category | Detail |")
    print("|---|-----------|--------|-----------|--------|------|----------|--------|")
    for i, row in enumerate(rows, 1):
        key, status, pred, tgt, unit, cat, detail = row
        # Truncate xfail status string for table.
        s = status if len(status) < 80 else status[:77] + "..."
        print(f"| {i} | `{key}` | {s} | {pred} | {tgt} | {unit} | {cat} | {detail} |")

    n_pass = sum(1 for r in rows if r[1] == "PASS")
    n_fail = sum(1 for r in rows if r[1] == "FAIL")
    n_xfail = sum(1 for r in rows if r[1].startswith("XFAIL"))
    n_err = sum(1 for r in rows if r[1] == "ERROR")
    print(
        f"\n**Summary: {n_pass} pass, {n_fail} fail, {n_xfail} xfail (expected), {n_err} error / {len(rows)} total.**"
    )


if __name__ == "__main__":
    main()
