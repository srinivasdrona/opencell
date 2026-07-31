"""End-to-end N=100 power diagnostic report builder for DNASupercoiling's
`linkingNumbers` primary projection components (see
`docs/phase_f/l2_2_design_a/L22_DNAS_POWER_PREREG.md`).

Orchestrates (all against already-extracted seeds 0-99; does not itself
invoke MATLAB):
  1. `validate_extension.validate_extension_seeds` for seeds 50-99.
  2. Three real `diagnostic_runner.run_seed_config` calls (unmodified
     `run_design_a`): seeds 0-49 (`n50_reproduction`), seeds 0-99
     (`n100_combined`), seeds 50-99 (`half_split_b`; `half_split_a` is
     `n50_reproduction` reused, since it is the same seeds/config).
  3. `power_decision.evaluate_power` on `n100_combined`'s primary components.
  4. `power_decision.project_nonzero_count` comparing the N=50-observed rate's
     projection to N=100 against the actually-observed N=100 count, for both
     primary components.

Writes everything into
`docs/phase_f/l2_2_design_a/evidence_bundle/DNASupercoiling/diagnostic_n100/`
(never `latest/`) plus a top-level `POWER_DIAGNOSTIC_REPORT.json`.

Usage (WSL only, per project convention):
    bin\\oc-py scripts/l22_dnas_power/build_report.py --out-root <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_dnas_power import diagnostic_runner, power_decision  # noqa: E402
from scripts.l22_dnas_power.validate_extension import validate_extension_seeds  # noqa: E402

DEFAULT_OUT_ROOT = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "evidence_bundle" / "DNASupercoiling" / "diagnostic_n100"
)
EXTENSION_SEEDS = list(range(50, 100))
BASELINE_SEEDS = list(range(50))
COMBINED_SEEDS = list(range(100))
PRIMARY_COMPONENTS = ("linkingNumbers.delta_value_sum", "linkingNumbers.delta_nnz")


def build_report(*, out_root: Path = DEFAULT_OUT_ROOT) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "process": "DNASupercoiling",
        "pre_registration": "docs/phase_f/l2_2_design_a/L22_DNAS_POWER_PREREG.md",
    }

    # Step 1: validate the seeds 50-99 extension (structural/drift/non-vacuity).
    validation = validate_extension_seeds(EXTENSION_SEEDS)
    report["extension_validation"] = validation
    if validation["result"] != "PASS":
        report["result"] = "BLOCKED_ON_VALIDATION"
        return report

    # Loader diagnostic count: confirm the widened loader reports 100 seeds.
    import _l2_2_design_a_runner_helpers as helpers  # noqa: PLC0415

    widened_oracle = helpers._load_v2_ensemble("DNASupercoiling", max_seeds=100)  # noqa: SLF001
    loader_seed_count = int(widened_oracle["canonical_seed_count"]) if widened_oracle is not None else 0
    report["loader_diagnostic_count"] = loader_seed_count
    if loader_seed_count != 100:
        report["result"] = "BLOCKED_ON_LOADER_COUNT"
        return report

    # Step 2: three real run_design_a invocations.
    n50 = diagnostic_runner.run_seed_config(
        seeds=BASELINE_SEEDS, out_dir=out_root / "n50_reproduction", max_seeds_override=100
    )
    n100 = diagnostic_runner.run_seed_config(
        seeds=COMBINED_SEEDS, out_dir=out_root / "n100_combined", max_seeds_override=100
    )
    half_b = diagnostic_runner.run_seed_config(
        seeds=EXTENSION_SEEDS, out_dir=out_root / "half_split_b", max_seeds_override=100
    )

    n50_components = diagnostic_runner.extract_primary_components(n50)
    n100_components = diagnostic_runner.extract_primary_components(n100)
    half_b_components = diagnostic_runner.extract_primary_components(half_b)

    report["n50_reproduction"] = {
        "seeds": BASELINE_SEEDS,
        "channel_verdict": n50["result"]["channels"]["chromosome"]["verdict"],
        "per_component": n50_components,
    }
    report["n100_combined"] = {
        "seeds": COMBINED_SEEDS,
        "channel_verdict": n100["result"]["channels"]["chromosome"]["verdict"],
        "per_component": n100_components,
    }
    report["half_split_a_is_n50_reproduction"] = True
    report["half_split_b"] = {
        "seeds": EXTENSION_SEEDS,
        "channel_verdict": half_b["result"]["channels"]["chromosome"]["verdict"],
        "per_component": half_b_components,
    }

    # Step 3: pre-registered power decision on n100_combined.
    power_by_component: dict[str, Any] = {}
    for component in PRIMARY_COMPONENTS:
        n_oc = n100_components["component_n_nonzero_oc"][component]
        n_karr = n100_components["component_n_nonzero_karr"][component]
        power_by_component[component] = power_decision.evaluate_power(n_oc, n_karr).to_dict()
    report["power_decision"] = power_by_component

    # Step 4: rate projection (N=50 observed rate -> projected N=100 count) vs actual N=100.
    rate_projection: dict[str, Any] = {}
    n_trials_50 = 50 * 100
    n_trials_100 = 100 * 100
    for side, key in (("oc", "component_n_nonzero_oc"), ("karr", "component_n_nonzero_karr")):
        for component in PRIMARY_COMPONENTS:
            observed_50 = n50_components[key][component]
            observed_100 = n100_components[key][component]
            projection = power_decision.project_nonzero_count(
                observed_n_nonzero=observed_50, observed_n_trials=n_trials_50, target_n_trials=n_trials_100
            )
            projection["actual_n100_count"] = observed_100
            lo, hi = projection["projected_count_ci95"]
            projection["actual_within_projected_ci95"] = bool(lo <= observed_100 <= hi)
            rate_projection[f"{component}::{side}"] = projection
    report["rate_projection"] = rate_projection

    # Seed half-split stability: compare half_split_a (== n50_reproduction) vs half_split_b.
    stability: dict[str, Any] = {}
    for component in PRIMARY_COMPONENTS:
        stability[component] = {
            "half_a_raw_w1": n50_components["component_raw_w1"][component],
            "half_b_raw_w1": half_b_components["component_raw_w1"][component],
            "half_a_verdict": n50_components["component_verdicts"][component],
            "half_b_verdict": half_b_components["component_verdicts"][component],
            "half_a_n_nonzero_oc": n50_components["component_n_nonzero_oc"][component],
            "half_b_n_nonzero_oc": half_b_components["component_n_nonzero_oc"][component],
            "half_a_n_nonzero_karr": n50_components["component_n_nonzero_karr"][component],
            "half_b_n_nonzero_karr": half_b_components["component_n_nonzero_karr"][component],
        }
    report["seed_half_split_stability"] = stability

    all_powered = all(v["powered"] for v in power_by_component.values())
    if all_powered:
        joint_verdict = n100["result"]["channels"]["chromosome"]["per_component"]["joint_verdict"]
        report["decision"] = "POWERED_AT_N100"
        report["mechanical_metric_verdict"] = joint_verdict
    else:
        report["decision"] = "STILL_UNDERPOWERED_AT_N100"
    report["result"] = "COMPLETE"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    args = parser.parse_args(argv)

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    report = build_report(out_root=out_root)
    report_path = out_root / "POWER_DIAGNOSTIC_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[build_report] wrote {report_path} result={report.get('result')} decision={report.get('decision')}")
    return 0 if report.get("result") == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
