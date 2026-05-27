"""Phase E.2 scorecard runner and markdown renderer."""

from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from opencell.validation.phenotype_registry import PHENOTYPES, PhenotypeDef

V6_FIXTURE_PATH = Path("data/phase_e/v6_trajectory_32400s.pkl")
E2_SCORECARD_PATH = Path("docs/phase_e/E2_scorecard.md")

_REQUIRED_TOP_LEVEL_KEYS = {
    "snapshots",
    "wall_time_s",
    "ticks_completed",
    "division_detected",
}
_REQUIRED_SNAPSHOT_KEYS = {"tick", "time_s", "state"}
_REQUIRED_STATE_KEYS = {
    "cell_dry_mass_g",
    "replication_state_code",
    "fork_position_norm",
    "mrna_total_count_estimate",
    "protein_total_count_estimate",
    "atp_pool",
    "gtp_pool",
    "dntp_pool_total",
    "division_event_timestamp_s",
}

_DEFERRED_KPS = {"KP25", "KP26"}
_EMITTER_GAP_KPS = {"KP15", "KP27", "KP28"}
_ENERGY_BALANCE_SUBSTRATES = {"ATP", "GTP"}


@dataclass(frozen=True)
class ScorecardRow:
    kp_id: str
    label: str
    bucket: str
    opencell_value: float | bool | None
    karr_value: float | bool | None
    rel_err: float | None
    status: str
    disposition: str
    disposition_todo_id: str | None = None


def load_v6_trajectory_fixture(path: Path = V6_FIXTURE_PATH) -> dict[str, Any]:
    """Load the pre-banked v6 fixture and validate schema-v1 contract."""
    if not path.exists():
        raise FileNotFoundError(
            f"Phase E fixture missing: {path}. Rebuild is intentionally disabled for E.2."
        )
    with path.open("rb") as f:
        payload = pickle.load(f)

    if not isinstance(payload, dict):
        raise ValueError("Invalid fixture: expected dict payload.")
    if payload.get("chassis") != "v6":
        raise ValueError(f"Invalid fixture chassis: {payload.get('chassis')!r}")
    if int(payload.get("schema_version", -1)) != 1:
        raise ValueError(f"Invalid fixture schema_version: {payload.get('schema_version')!r}")

    missing = sorted(_REQUIRED_TOP_LEVEL_KEYS - set(payload))
    if missing:
        raise ValueError(f"Fixture missing top-level keys: {missing}")

    snapshots = payload.get("snapshots", [])
    if not isinstance(snapshots, list) or not snapshots:
        raise ValueError("Fixture snapshots missing or empty.")

    for idx, snap in enumerate(snapshots):
        if not isinstance(snap, dict):
            raise ValueError(f"Snapshot {idx} is not a dict.")
        missing_snapshot = sorted(_REQUIRED_SNAPSHOT_KEYS - set(snap))
        if missing_snapshot:
            raise ValueError(f"Snapshot {idx} missing keys: {missing_snapshot}")
        state = snap.get("state", {})
        if not isinstance(state, dict):
            raise ValueError(f"Snapshot {idx} state is not a dict.")
        missing_state = sorted(_REQUIRED_STATE_KEYS - set(state))
        if missing_state:
            raise ValueError(f"Snapshot {idx} missing required state keys: {missing_state}")
    return payload


def _load_karr_flux_oracle_map() -> dict[str, float]:
    json_path = Path("data/karr_fixtures/karr_native_m1.json")
    if not json_path.exists():
        return {}
    try:
        fixture = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    ids = fixture.get("ids", {})
    rxn_ids = ids.get("reaction_wcm_645") if isinstance(ids, dict) else None
    matrix_npz = fixture.get("matrix_npz")
    if not isinstance(rxn_ids, list) or not isinstance(matrix_npz, str):
        return {}
    npz_path = Path(matrix_npz)
    if not npz_path.exists():
        return {}
    try:
        fluxes = np.load(npz_path, allow_pickle=False)["fluxs_stored"]
    except Exception:
        return {}
    if fluxes.shape[0] != len(rxn_ids):
        return {}
    out: dict[str, float] = {}
    for rxn_id, flux in zip(rxn_ids, fluxes):
        try:
            out[str(rxn_id)] = float(flux)
        except (TypeError, ValueError):
            continue
    return out


def _build_sidecar_metrics(trajectory_path: Path) -> dict[str, float]:
    seed_dir = trajectory_path.parent
    process_trace_path = seed_dir / "process_traces" / "karr_metabolism.csv"
    conservation_path = seed_dir / "conservation.csv"
    metrics: dict[str, float] = {}

    process_stats: dict[str, tuple[float, int]] = {}
    if process_trace_path.exists():
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        with process_trace_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                substrate = str(row.get("substrate", "")).strip()
                if not substrate:
                    continue
                try:
                    delta = float(row.get("delta", "nan"))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(delta):
                    continue
                sums[substrate] = sums.get(substrate, 0.0) + delta
                counts[substrate] = counts.get(substrate, 0) + 1
        process_stats = {k: (sums[k], counts[k]) for k in sums if counts.get(k, 0) > 0}

    tx_glcpts = process_stats.get("TX_GLCPTS")
    if tx_glcpts is not None:
        mean_flux = tx_glcpts[0] / max(tx_glcpts[1], 1)
        metrics["kp04_tx_glcpts_mean_abs_flux"] = float(abs(mean_flux))

    oracle = _load_karr_flux_oracle_map()
    if process_stats and oracle:
        log2_errors: list[float] = []
        for substrate, (total_delta, n) in process_stats.items():
            if substrate not in oracle:
                continue
            predicted = total_delta / max(n, 1)
            reference = oracle[substrate]
            if (not math.isfinite(predicted)) or (not math.isfinite(reference)):
                continue
            if abs(predicted) <= 1e-12 or abs(reference) <= 1e-12:
                continue
            log2_errors.append(abs(math.log2(abs(predicted) / abs(reference))))
        if log2_errors:
            metrics["kp03_flux_oracle_median_abs_log2_ratio"] = float(np.median(log2_errors))

    _ = conservation_path  # KP21 sidecar extraction lands in a follow-up commit.

    return metrics


def load_trajectory(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        payload = pickle.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid trajectory payload at {path}: expected dict.")
    metrics = _build_sidecar_metrics(path)
    if metrics:
        payload["_sidecar_metrics"] = metrics
    return payload


def _safe_rel_err(observed: float, expected: float) -> float:
    if math.isclose(expected, 0.0, abs_tol=1e-30):
        return abs(observed)
    return abs(observed - expected) / abs(expected)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, np.floating, np.integer)):
        return float(value)
    return None


def _is_finite_number(value: Any) -> bool:
    val = _as_float(value)
    return val is not None and math.isfinite(val)


def _fallback_todo_id(kp_id: str, reason: str) -> str:
    slug = reason.upper().replace(" ", "-")
    return f"E2-V1_1-{kp_id}-{slug}"


def _evaluate(defn: PhenotypeDef, observed: float | bool | None) -> ScorecardRow:
    kp_id = defn.id
    if observed is None:
        todo_id = defn.disposition_todo_id or _fallback_todo_id(kp_id, "schema-mismatch")
        if kp_id in _DEFERRED_KPS:
            # Keep TODO linkage visible for deferred-by-design KPs (disposition_todo_id).
            return ScorecardRow(
                kp_id=kp_id,
                label=defn.label,
                bucket=defn.bucket,
                opencell_value=None,
                karr_value=defn.karr_value,
                rel_err=None,
                status="DEFERRED",
                disposition="multi-run KO sweep required",
                disposition_todo_id=todo_id,
            )
        if kp_id in _EMITTER_GAP_KPS:
            return ScorecardRow(
                kp_id=kp_id,
                label=defn.label,
                bucket=defn.bucket,
                opencell_value=None,
                karr_value=defn.karr_value,
                rel_err=None,
                status="NEEDS_EMITTER",
                disposition="missing emitted trajectory field(s)",
                disposition_todo_id=todo_id,
            )
        return ScorecardRow(
            kp_id=kp_id,
            label=defn.label,
            bucket=defn.bucket,
            opencell_value=None,
            karr_value=defn.karr_value,
            rel_err=None,
            status="BLOCKED",
            disposition="Extractor unavailable for emitted schema.",
            disposition_todo_id=todo_id,
        )

    if defn.comparator == "bool":
        expected = defn.karr_value if isinstance(defn.karr_value, bool) else True
        actual = bool(observed)
        status = "PASS" if actual is bool(expected) else "FAIL"
        disposition = "qualitative boolean matched" if status == "PASS" else "qualitative boolean mismatch"
        return ScorecardRow(
            kp_id=kp_id,
            label=defn.label,
            bucket=defn.bucket,
            opencell_value=actual,
            karr_value=expected,
            rel_err=0.0 if status == "PASS" else 1.0,
            status=status,
            disposition=disposition,
        )

    observed_num = _as_float(observed)
    if observed_num is None or not math.isfinite(observed_num):
        return ScorecardRow(
            kp_id=kp_id,
            label=defn.label,
            bucket=defn.bucket,
            opencell_value=observed_num,
            karr_value=defn.karr_value,
            rel_err=None,
            status="FAIL",
            disposition="Extractor returned NaN/non-finite value.",
        )

    if defn.comparator == "threshold_max":
        threshold = _as_float(defn.karr_value)
        if threshold is None:
            threshold = float(defn.rel_tol)
        rel_err = observed_num / max(abs(threshold), 1e-12)
        status = "PASS" if observed_num <= threshold else "FAIL"
        return ScorecardRow(
            kp_id=kp_id,
            label=defn.label,
            bucket=defn.bucket,
            opencell_value=observed_num,
            karr_value=threshold,
            rel_err=rel_err,
            status=status,
            disposition="threshold_max satisfied" if status == "PASS" else "threshold_max exceeded",
        )

    if defn.comparator == "threshold_min":
        threshold = _as_float(defn.karr_value)
        if threshold is None:
            threshold = float(defn.rel_tol)
        gap = max(threshold - observed_num, 0.0)
        rel_err = gap / max(abs(threshold), 1e-12)
        status = "PASS" if observed_num >= threshold else "FAIL"
        return ScorecardRow(
            kp_id=kp_id,
            label=defn.label,
            bucket=defn.bucket,
            opencell_value=observed_num,
            karr_value=threshold,
            rel_err=rel_err,
            status=status,
            disposition="threshold_min satisfied" if status == "PASS" else "below minimum threshold",
        )

    expected_num = _as_float(defn.karr_value)
    if expected_num is None or not math.isfinite(expected_num):
        todo_id = defn.disposition_todo_id or _fallback_todo_id(kp_id, "missing-reference")
        return ScorecardRow(
            kp_id=kp_id,
            label=defn.label,
            bucket=defn.bucket,
            opencell_value=observed_num,
            karr_value=defn.karr_value,
            rel_err=None,
            status="BLOCKED",
            disposition="Missing Karr reference value.",
            disposition_todo_id=todo_id,
        )

    if defn.comparator == "ratio_band":
        if math.isclose(expected_num, 0.0, abs_tol=1e-12):
            rel_err = _safe_rel_err(observed_num, expected_num)
            status = "PASS" if rel_err <= defn.rel_tol else "FAIL"
        else:
            ratio = observed_num / expected_num
            rel_err = abs(1.0 - ratio)
            status = "PASS" if 0.4 <= ratio <= 2.5 else "FAIL"
        return ScorecardRow(
            kp_id=kp_id,
            label=defn.label,
            bucket=defn.bucket,
            opencell_value=observed_num,
            karr_value=expected_num,
            rel_err=rel_err,
            status=status,
            disposition="ratio band satisfied" if status == "PASS" else "ratio out of [0.4, 2.5]",
        )

    rel_err = _safe_rel_err(observed_num, expected_num)
    status = "PASS" if rel_err <= defn.rel_tol else "FAIL"
    return ScorecardRow(
        kp_id=kp_id,
        label=defn.label,
        bucket=defn.bucket,
        opencell_value=observed_num,
        karr_value=expected_num,
        rel_err=rel_err,
        status=status,
        disposition="within tolerance" if status == "PASS" else "tolerance exceeded",
    )


def score(trajectory: dict[str, Any]) -> list[ScorecardRow]:
    rows: list[ScorecardRow] = []
    for kp_id in sorted(PHENOTYPES):
        defn = PHENOTYPES[kp_id]
        observed = defn.extractor(trajectory)
        rows.append(_evaluate(defn, observed))
    return rows


def _fmt_value(value: float | bool | None) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "True" if value else "False"
    if not math.isfinite(float(value)):
        return "NaN"
    return f"{float(value):.6g}"


def _fmt_rel_err(value: float | None) -> str:
    if value is None:
        return "NA"
    if not math.isfinite(value):
        return "NaN"
    return f"{value:.4g}"


def _bucket_totals(rows: list[ScorecardRow]) -> dict[str, tuple[int, int]]:
    totals: dict[str, tuple[int, int]] = {}
    for row in rows:
        pass_count, total = totals.get(row.bucket, (0, 0))
        totals[row.bucket] = (pass_count + (1 if row.status == "PASS" else 0), total + 1)
    return totals


def make_stdout_summary(rows: list[ScorecardRow]) -> str:
    pass_count = sum(1 for r in rows if r.status == "PASS")
    fail_count = sum(1 for r in rows if r.status == "FAIL")
    blocked = sum(1 for r in rows if r.status == "BLOCKED")
    deferred = sum(1 for r in rows if r.status == "DEFERRED")
    needs_emitter = sum(1 for r in rows if r.status == "NEEDS_EMITTER")
    totals = _bucket_totals(rows)
    oc = totals.get("opencell-tooling", (0, 0))
    val = totals.get("validation-and-organism-scaling", (0, 0))
    inc = totals.get("karr-known-incomplete", (0, 0))
    bey = totals.get("biology-beyond-Karr", (0, 0))
    return (
        f"E2_PASS={pass_count}/28 "
        f"OC={oc[0]}/{oc[1]} "
        f"VAL={val[0]}/{val[1]} "
        f"INC={inc[0]}/{inc[1]} "
        f"BEY={bey[0]}/{bey[1]} "
        f"FAIL={fail_count} "
        f"BLOCKED={blocked} "
        f"DEFERRED={deferred} "
        f"NEEDS_EMITTER={needs_emitter}"
    )


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return "unknown"


def render_scorecard_markdown(rows: list[ScorecardRow], *, wall_time_s: float | None = None) -> str:
    pass_count = sum(1 for r in rows if r.status == "PASS")
    blocked_rows = [r for r in rows if r.status == "BLOCKED"]
    deferred_rows = [r for r in rows if r.status == "DEFERRED"]
    needs_emitter_rows = [r for r in rows if r.status == "NEEDS_EMITTER"]
    blocked_text = ", ".join(r.kp_id for r in blocked_rows) if blocked_rows else "None"
    deferred_text = ", ".join(r.kp_id for r in deferred_rows) if deferred_rows else "None"
    needs_emitter_text = ", ".join(r.kp_id for r in needs_emitter_rows) if needs_emitter_rows else "None"
    totals = _bucket_totals(rows)
    sha = _git_sha()
    summary = make_stdout_summary(rows)

    wall = "NA" if wall_time_s is None or not math.isfinite(wall_time_s) else f"{wall_time_s:.2f}"
    lines: list[str] = [
        "# Phase E.2 - 28-Phenotype Scorecard",
        "",
        f"`{summary}`",
        "",
        f"**Run**: chassis_v6 @ commit `{sha}`",
        f"**Wall-time**: `{wall}` s",
        f"**Pass count**: `{pass_count}/28` (pre-fix baseline gate >=6)",
        (
            "**Bucket summary**: "
            f"opencell-tooling {totals.get('opencell-tooling', (0, 0))[0]}/"
            f"{totals.get('opencell-tooling', (0, 0))[1]} · "
            f"validation-and-organism-scaling {totals.get('validation-and-organism-scaling', (0, 0))[0]}/"
            f"{totals.get('validation-and-organism-scaling', (0, 0))[1]} · "
            f"karr-known-incomplete {totals.get('karr-known-incomplete', (0, 0))[0]}/"
            f"{totals.get('karr-known-incomplete', (0, 0))[1]} · "
            f"biology-beyond-Karr {totals.get('biology-beyond-Karr', (0, 0))[0]}/"
            f"{totals.get('biology-beyond-Karr', (0, 0))[1]}"
        ),
        f"**Blocked**: `{len(blocked_rows)}` ({blocked_text})",
        f"**Deferred**: `{len(deferred_rows)}` ({deferred_text})",
        f"**Needs emitter**: `{len(needs_emitter_rows)}` ({needs_emitter_text})",
        "",
        "## Pre-fix vs Post-fix",
        "",
        "This scorecard is the **BEFORE-fix baseline** captured on the known broken chassis_v6 "
        "(allocation-bypass cascade from E.1). Failures and blocked rows are expected inputs to E.3. "
        "A second E.2 run will be produced after the allocation-consumer fix lands.",
        "",
        "## Per-KP detail",
        "",
        "| KP | Label | Bucket | Opencell | Karr | rel_err | Status | Disposition |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        disposition = row.disposition
        if row.status in {"BLOCKED", "DEFERRED", "NEEDS_EMITTER"} and row.disposition_todo_id:
            disposition = f"{disposition} ({row.disposition_todo_id})"
        lines.append(
            "| "
            f"{row.kp_id} | {row.label} | {row.bucket} | {_fmt_value(row.opencell_value)} | "
            f"{_fmt_value(row.karr_value)} | {_fmt_rel_err(row.rel_err)} | {row.status} | {disposition} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_scorecard_report(
    trajectory: dict[str, Any],
    *,
    out_path: Path = E2_SCORECARD_PATH,
) -> tuple[list[ScorecardRow], str]:
    rows = score(trajectory)
    content = render_scorecard_markdown(rows, wall_time_s=float(trajectory.get("wall_time_s", np.nan)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    summary = make_stdout_summary(rows)
    print(summary)
    return rows, summary


def run_from_fixture(
    fixture_path: Path = V6_FIXTURE_PATH,
    out_path: Path = E2_SCORECARD_PATH,
) -> tuple[list[ScorecardRow], str]:
    trajectory = load_v6_trajectory_fixture(fixture_path)
    return write_scorecard_report(trajectory, out_path=out_path)


def run_from_trajectory(
    trajectory_path: Path,
    *,
    out_path: Path = E2_SCORECARD_PATH,
) -> tuple[list[ScorecardRow], str]:
    trajectory = load_trajectory(trajectory_path)
    return write_scorecard_report(trajectory, out_path=out_path)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trajectory",
        type=Path,
        help="Path to trajectory.pkl (sidecar CSVs are auto-discovered from sibling files).",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=V6_FIXTURE_PATH,
        help="Path to canonical v6 fixture when --trajectory is not provided.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=E2_SCORECARD_PATH,
        help="Output markdown path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.trajectory is not None:
        run_from_trajectory(args.trajectory, out_path=args.out)
    else:
        run_from_fixture(fixture_path=args.fixture, out_path=args.out)
    return 0


__all__ = [
    "E2_SCORECARD_PATH",
    "ScorecardRow",
    "V6_FIXTURE_PATH",
    "load_trajectory",
    "load_v6_trajectory_fixture",
    "make_stdout_summary",
    "main",
    "render_scorecard_markdown",
    "run_from_fixture",
    "run_from_trajectory",
    "score",
    "write_scorecard_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
