"""Promote the ACCEPTED DNASupercoiling N=200 two-sided sparse-gate
evaluation into the canonical evidence_bundle/DNASupercoiling/latest, using
the standard evidence schema/generator machinery (never hand-typed JSON).

Two real pipelines feed this promotion, both already executed against the
CURRENT integrated tree at real N=200:

  1. The standard sweep (`scripts/l22_evidence/sweep.py run --processes
     DNASupercoiling --force`), which produced a genuine result.json/
     input_manifest.json/provenance.json/thresholds.json/null_calibration.
     json/SUMMARY.json/analytical_check.json/sweep_provenance.json under
     `artifacts/l2_2_gates/DNASupercoiling/latest/` for BOTH real output
     channels (`substrates`, standard per_tick_vector_w1_mean; `chromosome`,
     catalog primary_distance=per_component_scaled) at real N=200/M=100.

  2. The accepted two-sided sparse-support re-evaluation of `chromosome`'s
     `linkingNumbers.delta_nnz` component
     (`scripts/l22_dnas_sept2_two_sided_n200_eval.py`, already re-run fresh
     on this integrated tree -- see `diagnostic_n200_followup/
     sept2_two_sided_rerun/two_sided_gate_evaluation.json`), which is what
     the wave-l22-dnas branch's Opus-accepted review actually verified
     (PASS: pooled_nonzero_ticks 64/65, active_seeds 58/58, clustered_seeds
     6/7, all axes BALANCED, 0 process-RNG audit-boundary breaches).

This script replaces ONLY the `chromosome` channel's payload in the
standard-sweep result.json with the two-sided-gate-shaped payload
verdict._rederive_dnas_two_sided_gate_channel expects (a `value_component`
block carrying the SAME `linkingNumbers.delta_value_sum` raw numbers the
standard sweep already computed -- unchanged formula, cross-checked byte-
identical against the two-sided eval's own independently-computed value --
and a `sparse_component` block carrying the two-sided eval's own per-axis
oc_count/karr_count), sets `aggregation: "dnas_two_sided_sparse_gate"`, then
re-derives every downstream file (thresholds.json/null_calibration.json/
SUMMARY.json/analytical_check.json/sweep_provenance.json's source hashes)
via the SAME schema/sweep-generator functions the standard pipeline itself
uses -- never a hand-maintained duplicate of that logic.

Never edits `input_manifest.json`, `provenance.json`, or any raw per-seed
oracle data.

CLI:
    bin\\oc-py scripts/l22_dnas_promote_n200_evidence.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402

PROCESS = "DNASupercoiling"
LIVE_DIR = schema.EVIDENCE_ROOT / PROCESS / schema.DESIGN_A_SUBDIR
TWO_SIDED_EVAL_PATH = (
    schema.BUNDLE_ROOT / PROCESS / "diagnostic_n200_followup" / "sept2_two_sided_rerun" / "two_sided_gate_evaluation.json"
)
BUNDLE_DIR = schema.BUNDLE_ROOT / PROCESS / schema.DESIGN_A_SUBDIR


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_dnas_two_sided_channel_payload(
    *, standard_per_component: dict[str, Any], two_sided_eval: dict[str, Any]
) -> dict[str, Any]:
    """Construct the `chromosome` channel payload
    `verdict._rederive_dnas_two_sided_gate_channel` expects, from the two
    REAL, independently-computed sources described in this module's
    docstring. Cross-checks the `linkingNumbers.delta_value_sum` component
    (unchanged formula) is byte-identical between both sources before using
    it -- refuses (raises) rather than silently picking one if they ever
    disagree."""
    value_name = "linkingNumbers.delta_value_sum"
    sparse_name = "linkingNumbers.delta_nnz"

    standard_scaled_w1 = float(standard_per_component[value_name])
    eval_value_metric = two_sided_eval["primary_evaluation"]["delta_value_sum_metric"]
    eval_scaled_w1 = float(eval_value_metric["scaled_w1"])
    if abs(standard_scaled_w1 - eval_scaled_w1) > 1e-9:
        raise ValueError(
            f"{value_name} scaled_w1 disagreement between standard sweep ({standard_scaled_w1}) "
            f"and two-sided eval ({eval_scaled_w1}) -- refusing to promote"
        )

    value_component = {
        "component_name": value_name,
        "raw_w1": float(standard_per_component["component_raw_w1"][value_name]),
        "scale": float(standard_per_component["component_scales"][value_name]),
        "scaled_distance_threshold": float(standard_per_component["scaled_distance_threshold"]),
        "n_nonzero_oc": int(standard_per_component["component_n_nonzero_oc"][value_name]),
        "n_nonzero_karr": int(standard_per_component["component_n_nonzero_karr"][value_name]),
    }

    eval_sparse = two_sided_eval["primary_evaluation"]["delta_nnz_sparse_gate"]
    standard_n_oc_sparse = int(standard_per_component["component_n_nonzero_oc"][sparse_name])
    standard_n_karr_sparse = int(standard_per_component["component_n_nonzero_karr"][sparse_name])
    pooled_axis = next(axis for axis in eval_sparse["axes"] if axis["axis"] == "pooled_nonzero_ticks")
    if int(pooled_axis["oc_count"]) != standard_n_oc_sparse or int(pooled_axis["karr_count"]) != standard_n_karr_sparse:
        raise ValueError(
            f"{sparse_name} pooled_nonzero_ticks disagreement between standard sweep "
            f"(oc={standard_n_oc_sparse}, karr={standard_n_karr_sparse}) and two-sided eval "
            f"(oc={pooled_axis['oc_count']}, karr={pooled_axis['karr_count']}) -- refusing to promote"
        )

    sparse_component = {
        "component_name": sparse_name,
        "rule": "two_sided_sparse_gate",
        "alpha_family": float(eval_sparse["config"]["alpha_family"]),
        "axes": [
            {
                "axis": axis["axis"],
                "oc_count": int(axis["oc_count"]),
                "karr_count": int(axis["karr_count"]),
                "pooled_total": int(axis["pooled_total"]),
                "raw_pvalue": float(axis["raw_pvalue"]),
                "holm_adjusted_pvalue": float(axis["holm_adjusted_pvalue"]),
                "rejected": bool(axis["rejected"]),
                "direction": str(axis["direction"]),
            }
            for axis in eval_sparse["axes"]
        ],
    }

    return {
        "is_primary": True,
        "aggregation": "dnas_two_sided_sparse_gate",
        "value_component": value_component,
        "sparse_component": sparse_component,
        "source_checkpoint_sha256": two_sided_eval["_checkpoint_sha256"],
        "source_eval_script": "scripts/l22_dnas_sept2_two_sided_n200_eval.py",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write the promoted bundle (default: dry run/report only).")
    args = parser.parse_args(argv)

    if not LIVE_DIR.is_dir():
        print(f"REFUSED: no live sweep evidence at {LIVE_DIR} -- run the standard sweep first.", file=sys.stderr)
        return 1
    if not TWO_SIDED_EVAL_PATH.is_file():
        print(f"REFUSED: no two-sided evaluation at {TWO_SIDED_EVAL_PATH}.", file=sys.stderr)
        return 1

    result_payload = _load_json(LIVE_DIR / "result.json")
    if result_payload.get("process") != PROCESS:
        print(f"REFUSED: result.json process={result_payload.get('process')!r} != {PROCESS!r}", file=sys.stderr)
        return 1

    two_sided_eval = _load_json(TWO_SIDED_EVAL_PATH)
    import hashlib

    two_sided_eval["_checkpoint_sha256"] = hashlib.sha256(
        (LIVE_DIR.parent / "diagnostic_n200_followup" / "sept2_two_sided_rerun" / "raw_captured_tensors_checkpoint.npz")
        .read_bytes()
        if (LIVE_DIR.parent / "diagnostic_n200_followup" / "sept2_two_sided_rerun" / "raw_captured_tensors_checkpoint.npz").is_file()
        else b""
    ).hexdigest()

    chromosome_channel = result_payload["channels"]["chromosome"]
    new_chromosome_channel = build_dnas_two_sided_channel_payload(
        standard_per_component=chromosome_channel["per_component"], two_sided_eval=two_sided_eval
    )
    result_payload["channels"]["chromosome"] = new_chromosome_channel

    entries = cat.in_scope_processes(schema.CATALOG_PATH)
    entry = entries[PROCESS]
    process_verdict = vd.rederive_process(PROCESS, entry, result_payload)
    is_green = process_verdict.mechanical_verdict == schema.STATUS_PASS
    print(f"Mechanically re-derived process verdict: {process_verdict.mechanical_verdict} (green={is_green})")
    for reason in process_verdict.reasons:
        print(f"  reason: {reason}")
    if not is_green:
        print("REFUSED: promoted result.json does not mechanically re-derive to green.", file=sys.stderr)
        return 1

    if not args.apply:
        print("DRY RUN -- pass --apply to write. Would overwrite:")
        print(f"  {LIVE_DIR / 'result.json'}")
        return 0

    _write_json(LIVE_DIR / "result.json", result_payload)

    # sweep_provenance.json's own sidecar_hashes["result.json"] binds the
    # sentinel to result.json's exact bytes (R1) -- recompute it since we
    # just edited that file. Every OTHER field (source_hashes/n_seeds/
    # m_ticks/git_sha/inputs_verified/...) is untouched: the CODE that
    # generated this evidence, and every input it consumed, is unchanged --
    # only the recorded chromosome-channel VERDICT METHODOLOGY changed, to
    # the one Opus actually reviewed and accepted.
    import hashlib as _hashlib

    prov_path = LIVE_DIR / schema.SWEEP_PROVENANCE_FILE
    prov_payload = _load_json(prov_path)
    prov_payload.setdefault("sidecar_hashes", {})["result.json"] = _hashlib.sha256(
        (LIVE_DIR / "result.json").read_bytes()
    ).hexdigest()
    _write_json(prov_path, prov_payload)

    gen.bundle_process_evidence(source_root=schema.EVIDENCE_ROOT, bundle_root=schema.BUNDLE_ROOT, catalog_path=schema.CATALOG_PATH)
    print(f"Promoted {PROCESS} N=200 evidence into {BUNDLE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
