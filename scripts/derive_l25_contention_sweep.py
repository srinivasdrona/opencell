from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import tomllib

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
PAIR_LIST_PATH = REPO_ROOT / "data" / "schemas" / "l25_pair_list.toml"
PROCESS_SCHEMA_DIR = REPO_ROOT / "data" / "schemas" / "per_process"
OUTPUT_PATH = REPO_ROOT / "docs" / "phase_f" / "L2_5_CONTENTION_SWEEP.md"


@dataclass(frozen=True)
class ProcessTraceProfile:
    name: str
    trace_path: Path
    oc_source: str
    substrate_wids: tuple[str, ...]
    direction_by_wid: dict[str, str]
    before_tick0_by_wid: dict[str, float]
    before_series_by_wid: dict[str, np.ndarray]
    activity_mutated_ticks: int


def _resolve_data_path(path_text: str) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    rooted = (REPO_ROOT / candidate).resolve()
    if rooted.exists():
        return rooted
    return rooted


def _read_trace_vector(handle: h5py.File, group: str, observable: str, tick: int) -> np.ndarray:
    ds = handle[f"{group}/{observable}"]
    if ds.dtype == object:
        ref = ds[()][0, tick]
        return np.asarray(handle[ref][()], dtype=np.float64).reshape(-1)
    arr = np.asarray(ds[()], dtype=np.float64)
    if arr.ndim == 1:
        return arr.reshape(-1)
    if arr.ndim == 2:
        return arr[tick].reshape(-1)
    return arr.reshape(arr.shape[-1])


def _project_substrate_vector(vector: np.ndarray, expected_len: int) -> np.ndarray:
    if expected_len <= 0:
        return np.zeros(0, dtype=np.float64)
    flat = np.asarray(vector, dtype=np.float64).reshape(-1)
    if flat.size == expected_len:
        return flat
    # Karr substrate traces may include compartment-flattened vectors
    # (for example, 585 * 3 = 1755); OC substrate stores use the first
    # process-specific substrate slice.
    if flat.size > expected_len:
        return flat[:expected_len]
    out = np.zeros(expected_len, dtype=np.float64)
    out[: flat.size] = flat
    return out


def _classify_direction(deltas: np.ndarray, tol: float = 1.0e-9) -> str:
    has_pos = bool(np.any(deltas > tol))
    has_neg = bool(np.any(deltas < -tol))
    if has_pos and has_neg:
        return "mixed"
    if has_pos:
        return "produce"
    if has_neg:
        return "consume"
    return "none"


def _load_process_profiles() -> dict[str, ProcessTraceProfile]:
    profiles: dict[str, ProcessTraceProfile] = {}

    for schema_path in sorted(PROCESS_SCHEMA_DIR.glob("*.toml")):
        with schema_path.open("rb") as handle:
            schema = tomllib.load(handle)

        process_name = str(schema["process"]["name"])
        trace_path = _resolve_data_path(str(schema["process"]["trace_file"]))
        substrate_wids = tuple(str(wid) for wid in schema["state_groups"].get("substrates", []))
        oc_source = str(schema.get("extractor_diagnostics", {}).get("provenance", {}).get("oc_source", ""))
        activity_mutated_ticks = int(schema.get("activity_profile", {}).get("substrates_mutated_ticks", 0))

        direction_by_wid = {wid: "none" for wid in substrate_wids}
        before_tick0_by_wid = {wid: 0.0 for wid in substrate_wids}
        before_series_by_wid: dict[str, np.ndarray] = {
            wid: np.zeros(0, dtype=np.float64) for wid in substrate_wids
        }

        if trace_path.exists() and substrate_wids:
            with h5py.File(trace_path, "r") as trace:
                n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
                before_matrix = np.zeros((n_ticks, len(substrate_wids)), dtype=np.float64)
                after_matrix = np.zeros_like(before_matrix)
                for tick in range(n_ticks):
                    before_vec = _read_trace_vector(trace, "states_before", "substrates", tick)
                    after_vec = _read_trace_vector(trace, "states_after", "substrates", tick)
                    before_matrix[tick, :] = _project_substrate_vector(
                        before_vec, expected_len=len(substrate_wids)
                    )
                    after_matrix[tick, :] = _project_substrate_vector(
                        after_vec, expected_len=len(substrate_wids)
                    )

            delta_matrix = after_matrix - before_matrix
            for idx, wid in enumerate(substrate_wids):
                direction_by_wid[wid] = _classify_direction(delta_matrix[:, idx])
                before_tick0_by_wid[wid] = float(before_matrix[0, idx])
                before_series_by_wid[wid] = before_matrix[:, idx].copy()

        profiles[process_name] = ProcessTraceProfile(
            name=process_name,
            trace_path=trace_path,
            oc_source=oc_source,
            substrate_wids=substrate_wids,
            direction_by_wid=direction_by_wid,
            before_tick0_by_wid=before_tick0_by_wid,
            before_series_by_wid=before_series_by_wid,
            activity_mutated_ticks=activity_mutated_ticks,
        )

    return profiles


def _contention_class(direction_a: str, direction_b: str) -> str:
    if direction_a == "none" and direction_b == "none":
        return "both_inert"
    if direction_a == "none" or direction_b == "none":
        return "one_active_one_inert"
    if direction_a == "produce" and direction_b == "produce":
        return "both_produce"
    if direction_a == "consume" and direction_b == "consume":
        return "both_consume"
    if (
        (direction_a == "produce" and direction_b == "consume")
        or (direction_a == "consume" and direction_b == "produce")
    ):
        return "one_produce_one_consume"
    return "mixed_direction"


def _substrate_score(*, direction_a: str, direction_b: str, mismatch_any: bool) -> int:
    both_active = direction_a != "none" and direction_b != "none"
    one_active = (direction_a != "none") ^ (direction_b != "none")

    if mismatch_any and both_active:
        return 6
    if mismatch_any and one_active:
        return 5
    if both_active and _contention_class(direction_a, direction_b) == "one_produce_one_consume":
        return 4
    if both_active:
        return 3
    if one_active:
        return 2
    if mismatch_any:
        return 1
    return 0


def _pair_prediction(score: int, mismatch_active: int, both_active: int) -> str:
    if score >= 20 or mismatch_active >= 3:
        return "likely_fail"
    if score >= 10 or mismatch_active >= 1 or both_active >= 3:
        return "at_risk"
    return "likely_pass"


def _fmt_num(value: float) -> str:
    if math.isfinite(value) and float(value).is_integer():
        return str(int(value))
    return f"{value:.3g}"


def _top_detail_snippets(details: list[dict[str, object]], limit: int = 3) -> str:
    if not details:
        return "-"
    ordered = sorted(details, key=lambda item: int(item["score"]), reverse=True)
    parts: list[str] = []
    for detail in ordered[:limit]:
        parts.append(
            f"{detail['wid']}:{detail['contention']}"
            f"(a={detail['direction_a']},b={detail['direction_b']},"
            f"tick0={_fmt_num(float(detail['before0_a']))}/{_fmt_num(float(detail['before0_b']))},"
            f"score={detail['score']})"
        )
    return "; ".join(parts)


def build_sweep_markdown() -> str:
    with PAIR_LIST_PATH.open("rb") as handle:
        pair_data = tomllib.load(handle)

    all_pairs = pair_data.get("pairs", [])
    honest_pairs = [p for p in all_pairs if bool(p.get("l25_honest_required", False))]
    profiles = _load_process_profiles()

    analyzed_rows: list[dict[str, object]] = []
    prediction_counts = {"likely_fail": 0, "at_risk": 0, "likely_pass": 0}

    for pair in honest_pairs:
        process_a = str(pair["process_a"])
        process_b = str(pair["process_b"])
        substrates_shared = [str(wid) for wid in pair.get("substrates_shared", [])]

        profile_a = profiles[process_a]
        profile_b = profiles[process_b]

        details: list[dict[str, object]] = []
        class_counts = {
            "both_produce": 0,
            "both_consume": 0,
            "one_produce_one_consume": 0,
            "mixed_direction": 0,
            "one_active_one_inert": 0,
            "both_inert": 0,
        }

        mismatch_active = 0
        both_active = 0
        pair_score = 0

        for wid in substrates_shared:
            direction_a = profile_a.direction_by_wid.get(wid, "none")
            direction_b = profile_b.direction_by_wid.get(wid, "none")
            before_series_a = profile_a.before_series_by_wid.get(wid, np.zeros(0, dtype=np.float64))
            before_series_b = profile_b.before_series_by_wid.get(wid, np.zeros(0, dtype=np.float64))

            mismatch_any = False
            if before_series_a.size and before_series_b.size:
                n = int(min(before_series_a.size, before_series_b.size))
                mismatch_any = bool(np.any(before_series_a[:n] != before_series_b[:n]))

            score = _substrate_score(
                direction_a=direction_a,
                direction_b=direction_b,
                mismatch_any=mismatch_any,
            )
            pair_score += score

            contention = _contention_class(direction_a, direction_b)
            class_counts[contention] += 1

            if direction_a != "none" and direction_b != "none":
                both_active += 1
            if mismatch_any and (direction_a != "none" or direction_b != "none"):
                mismatch_active += 1

            details.append(
                {
                    "wid": wid,
                    "direction_a": direction_a,
                    "direction_b": direction_b,
                    "contention": contention,
                    "mismatch_any": mismatch_any,
                    "before0_a": profile_a.before_tick0_by_wid.get(wid, 0.0),
                    "before0_b": profile_b.before_tick0_by_wid.get(wid, 0.0),
                    "score": score,
                }
            )

        prediction = _pair_prediction(pair_score, mismatch_active, both_active)
        prediction_counts[prediction] += 1

        analyzed_rows.append(
            {
                "pair": f"{process_a} + {process_b}",
                "process_a": process_a,
                "process_b": process_b,
                "score": pair_score,
                "prediction": prediction,
                "shared_substrates": len(substrates_shared),
                "mismatch_active": mismatch_active,
                "both_active": both_active,
                "class_counts": class_counts,
                "details": details,
                "top_details": _top_detail_snippets(details),
                "tier": int(pair.get("tier", 0)),
                "oracle_complexity": str(pair.get("pair_oracle_complexity", "")),
            }
        )

    analyzed_rows.sort(
        key=lambda row: (
            -int(row["score"]),
            -int(row["mismatch_active"]),
            -int(row["shared_substrates"]),
            str(row["pair"]),
        )
    )

    focus_row = next(
        row
        for row in analyzed_rows
        if row["process_a"] == "ChromosomeCondensation" and row["process_b"] == "ChromosomeSegregation"
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: list[str] = []
    lines.append("# L2.5 Contention Sweep (CAUSE_4 Pattern Risk)")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append("")
    lines.append("## Method")
    lines.append("- Input pair set: `data/schemas/l25_pair_list.toml` filtered to `l25_honest_required=true` (256 pairs).")
    lines.append("- Shared-substrate set per pair: `substrates_shared` from pair list.")
    lines.append("- Per-process direction (`produce`, `consume`, `mixed`, `none`) inferred from per-tick substrate deltas in each process trace (`states_after - states_before`).")
    lines.append("- Baseline mismatch signal: per-WID mismatch between process-A and process-B `states_before` substrate series.")
    lines.append("- Risk score emphasizes the CAUSE_4-style overwrite pattern: shared substrate + baseline mismatch + active writer(s).")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Honest-required pairs analyzed: {len(analyzed_rows)}")
    lines.append(f"- Predicted `likely_fail`: {prediction_counts['likely_fail']}")
    lines.append(f"- Predicted `at_risk`: {prediction_counts['at_risk']}")
    lines.append(f"- Predicted `likely_pass`: {prediction_counts['likely_pass']}")
    lines.append("")
    lines.append("## Focus Pair: ChromosomeCondensation + ChromosomeSegregation")
    lines.append(f"- Score: {focus_row['score']} ({focus_row['prediction']})")
    lines.append(f"- Shared substrates: {focus_row['shared_substrates']}")
    lines.append(f"- Mismatch+active substrates: {focus_row['mismatch_active']}")
    lines.append(f"- Contention counts: {focus_row['class_counts']}")
    lines.append(f"- Highest-risk substrates: {focus_row['top_details']}")
    lines.append("")
    lines.append("## Ranked Pairs")
    lines.append("| Rank | Pair | Score | Prediction | Shared | Mismatch+Active | BothActive | Top substrate risks |")
    lines.append("|---|---|---:|---|---:|---:|---:|---|")

    for idx, row in enumerate(analyzed_rows, start=1):
        lines.append(
            "| "
            f"{idx} | {row['pair']} | {row['score']} | {row['prediction']} | "
            f"{row['shared_substrates']} | {row['mismatch_active']} | {row['both_active']} | "
            f"{row['top_details']} |"
        )

    lines.append("")
    lines.append("## Prediction Legend")
    lines.append("- `likely_fail`: high overwrite-risk score (shared active substrates with baseline mismatches).")
    lines.append("- `at_risk`: moderate contention; could pass if runtime baselines align or mutations are sparse.")
    lines.append("- `likely_pass`: low substrate contention and low overwrite-risk score.")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive L2.5 shared-substrate contention sweep report.")
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Output markdown path (default: docs/phase_f/L2_5_CONTENTION_SWEEP.md)",
    )
    args = parser.parse_args()

    markdown = build_sweep_markdown()
    output_path = args.output
    if not output_path.is_absolute():
        output_path = (REPO_ROOT / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")


if __name__ == "__main__":
    main()
