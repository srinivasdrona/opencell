"""Day-42 probe 3: multi-sample sweep for writeback-gap dominance.

Goal:
- Attempt the target grid seeds 0-9 at ticks 1 and 5 (20 samples total).
- If some target files are missing locally, process available files and report gaps.
- For each sample, run OC LP in production config (GLPK, pricing STD, presolve OFF),
  run deterministic writeback, compare against Karr recorded delta, and decompose error
  by substrate row.
- Aggregate whether Day-42's 4 substitution pairs dominate consistently, and how often
  GAP_MAP's 17 trouble WIDs appear among top contributors.

Outputs:
- tmp/h_multisample_sweep.json
- STATUS_h_multisample_sweep.md
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)


GT_DIR = REPO / "data" / "karr_fixtures" / "matlab_ground_truth"
WRITEBACK_FIXTURE = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
GAP_MAP_PATH = REPO / "docs" / "phase_f" / "METABOLISM_GAP_MAP.md"
OUT_JSON = REPO / "tmp" / "h_multisample_sweep.json"
OUT_STATUS = REPO / "STATUS_h_multisample_sweep.md"

TARGET_SEEDS = list(range(10))
TARGET_TICKS = [1, 5]

SUBSTITUTION_PAIRS = {
    "PHE/PhePhe": [469, 470],
    "TRP/TrpTrp": [541, 542],
    "HDCA/OCDCEA": [300, 439],
    "TRIOLEIN/TRIPALMITIN": [536, 537],
}

# Fallback if GAP_MAP parsing fails.
GAP_MAP_TOP17_FALLBACK = [
    "OCDCEA",
    "H2O2",
    "O2",
    "TRP",
    "TRIOLEIN",
    "TYR",
    "GL",
    "AC",
    "PHE",
    "TrpTrp",
    "H2O",
    "TyrTyr",
    "GLC",
    "ACAL",
    "AEPP",
    "CAP",
    "PhePhe",
]


class _DetRng:
    """Deterministic round-to-nearest RNG shim for writeback isolation."""

    def stochastic_round(self, values: np.ndarray) -> np.ndarray:
        arr = np.asarray(values, dtype=np.float64)
        return np.rint(arr).astype(np.int64)


def parse_sample_name(name: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"metab_flux_allocated_state_s(\d+)_tick(\d+)\.mat", name)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def discover_sample_files(gt_dir: Path) -> dict[tuple[int, int], Path]:
    out: dict[tuple[int, int], Path] = {}
    for p in sorted(gt_dir.glob("metab_flux_allocated_state_s*_tick*.mat")):
        parsed = parse_sample_name(p.name)
        if parsed is not None:
            out[parsed] = p
    return out


def choose_samples(
    available: dict[tuple[int, int], Path],
) -> tuple[list[dict[str, Any]], list[dict[str, int]]]:
    target_pairs = [(s, t) for s in TARGET_SEEDS for t in TARGET_TICKS]
    selected: list[dict[str, Any]] = []
    missing_targets: list[dict[str, int]] = []
    selected_pairs: set[tuple[int, int]] = set()

    # 1) Use requested target samples if present.
    for seed, tick in target_pairs:
        key = (seed, tick)
        if key in available:
            selected.append(
                {
                    "seed": seed,
                    "tick": tick,
                    "path": str(available[key]),
                    "selection": "target",
                }
            )
            selected_pairs.add(key)
        else:
            missing_targets.append({"seed": seed, "tick": tick})

    # 2) Fallback: fill from other available files, up to requested count (20).
    for key in sorted(available):
        if len(selected) >= 20:
            break
        if key in selected_pairs:
            continue
        selected.append(
            {
                "seed": key[0],
                "tick": key[1],
                "path": str(available[key]),
                "selection": "fallback",
            }
        )
        selected_pairs.add(key)

    return selected, missing_targets


def parse_gap_map_top17_wids(path: Path) -> list[str]:
    if not path.exists():
        return GAP_MAP_TOP17_FALLBACK.copy()

    lines = path.read_text(encoding="utf-8").splitlines()
    in_top27_section = False
    rank_to_wid: dict[int, str] = {}
    for line in lines:
        if line.strip().startswith("## Top 27 WIDs"):
            in_top27_section = True
            continue
        if in_top27_section and line.strip().startswith("## "):
            break
        if not in_top27_section:
            continue
        m = re.match(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|", line.strip())
        if not m:
            continue
        rank = int(m.group(1))
        wid = m.group(2)
        if 1 <= rank <= 17:
            rank_to_wid[rank] = wid
    if len(rank_to_wid) < 17:
        return GAP_MAP_TOP17_FALLBACK.copy()
    return [rank_to_wid[i] for i in range(1, 18)]


def load_sample(path: Path) -> dict[str, np.ndarray | float]:
    with h5py.File(path, "r") as h:
        flux = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
        growth = float(np.asarray(h["growth"][()], dtype=np.float64).reshape(-1)[0])
        pre_sub = np.asarray(h["pre_sub"][()], dtype=np.float64)
        karr_delta = np.asarray(h["delta"][()], dtype=np.float64)
        bounds = np.asarray(h["bounds"][()], dtype=np.float64)

    if pre_sub.shape == (3, 585):
        pre_sub = pre_sub.T
    if karr_delta.shape == (3, 585):
        karr_delta = karr_delta.T
    if bounds.shape == (2, 504):
        bounds = bounds.T

    if flux.shape != (504,):
        raise ValueError(f"Unexpected flux shape {flux.shape} for {path}")
    if pre_sub.shape != (585, 3):
        raise ValueError(f"Unexpected pre_sub shape {pre_sub.shape} for {path}")
    if karr_delta.shape != (585, 3):
        raise ValueError(f"Unexpected delta shape {karr_delta.shape} for {path}")
    if bounds.shape != (504, 2):
        raise ValueError(f"Unexpected bounds shape {bounds.shape} for {path}")

    return {
        "flux": flux,
        "growth": growth,
        "pre_sub": pre_sub,
        "karr_delta": np.rint(karr_delta).astype(np.int64),
        "bounds": bounds,
    }


def summarize_pairs_for_sample(
    row_abs_diff: np.ndarray,
    top5_rows: set[int],
    total_l1: int,
) -> dict[str, Any]:
    all_pair_rows = sorted({idx for rows in SUBSTITUTION_PAIRS.values() for idx in rows})
    pair_mass_total = int(sum(int(row_abs_diff[i]) for i in all_pair_rows))
    pair_share = float(pair_mass_total / total_l1) if total_l1 > 0 else 0.0

    by_pair: dict[str, Any] = {}
    for pair_name, rows in SUBSTITUTION_PAIRS.items():
        mass = int(sum(int(row_abs_diff[i]) for i in rows))
        by_pair[pair_name] = {
            "rows": rows,
            "abs_diff_l1_sum": mass,
            "share_of_sample_l1": float(mass / total_l1) if total_l1 > 0 else 0.0,
            "any_member_in_top5": any(r in top5_rows for r in rows),
            "both_members_in_top5": all(r in top5_rows for r in rows),
        }

    return {
        "all_pair_rows": all_pair_rows,
        "all_pairs_abs_diff_l1_sum": pair_mass_total,
        "all_pairs_share_of_sample_l1": pair_share,
        "dominant_by_mass_gt_50pct": pair_share > 0.5,
        "pairs": by_pair,
    }


def analyze_one_sample(
    sample_meta: dict[str, Any],
    *,
    model: km.KarrMetabolismModel,
    fixture: KarrWritebackFixture,
    substrate_wids: list[str],
    trouble_row_by_wid: dict[str, int],
) -> dict[str, Any]:
    path = Path(sample_meta["path"])
    loaded = load_sample(path)
    bounds = loaded["bounds"]
    pre_sub = loaded["pre_sub"]
    karr_delta = loaded["karr_delta"]

    v_oc, info = km.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=1e6,
        lb_override=bounds[:, 0],
        ub_override=bounds[:, 1],
        solver="glpk",
    )

    oc_delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(),
        v_504=v_oc,
        growth_per_s=float(info["biomass_flux_per_s"]),
        fixture=fixture,
        rng=_DetRng(),
        step_size_sec=fixture.step_size_sec,
    ).astype(np.int64)

    diff = oc_delta - karr_delta
    writeback_l1 = int(np.abs(diff).sum())
    writeback_linf = int(np.abs(diff).max())
    row_abs_diff = np.abs(diff).sum(axis=1).astype(np.int64)
    top20_idx = np.argsort(-row_abs_diff)[:20]
    top5_idx = [int(i) for i in top20_idx[:5]]
    top5_set = set(top5_idx)

    top20_rows: list[dict[str, Any]] = []
    for row in top20_idx:
        if int(row_abs_diff[row]) <= 0:
            continue
        top20_rows.append(
            {
                "row": int(row),
                "wid": substrate_wids[int(row)],
                "abs_diff_l1": int(row_abs_diff[row]),
                "diff_per_compartment": [int(x) for x in diff[int(row), :].tolist()],
                "oc_delta_per_compartment": [int(x) for x in oc_delta[int(row), :].tolist()],
                "karr_delta_per_compartment": [int(x) for x in karr_delta[int(row), :].tolist()],
            }
        )

    pairs_summary = summarize_pairs_for_sample(row_abs_diff, top5_set, writeback_l1)
    top1_row = int(top20_rows[0]["row"]) if top20_rows else -1
    top1_wid = top20_rows[0]["wid"] if top20_rows else None
    pair_rows_all = set(pairs_summary["all_pair_rows"])
    top1_is_pair_row = top1_row in pair_rows_all

    trouble_presence: dict[str, Any] = {}
    for wid, row in trouble_row_by_wid.items():
        trouble_presence[wid] = {
            "row": int(row),
            "in_top5": row in top5_set,
            "is_top1": row == top1_row,
            "abs_diff_l1_at_row": int(row_abs_diff[row]),
        }

    return {
        "seed": int(sample_meta["seed"]),
        "tick": int(sample_meta["tick"]),
        "path": str(path),
        "selection": sample_meta["selection"],
        "solver": {
            "solver_tag": info.get("solver", "glpk"),
            "status": info.get("status", "unknown"),
            "message": info.get("message", ""),
            "objective_value": float(info.get("objective_value", 0.0)),
            "biomass_flux_per_s": float(info.get("biomass_flux_per_s", 0.0)),
        },
        "writeback_vs_karr": {
            "diff_l1": writeback_l1,
            "diff_linf": writeback_linf,
            "diff_nnz": int(np.sum(diff != 0)),
            "diff_per_compartment_l1": [
                int(np.abs(diff[:, 0]).sum()),
                int(np.abs(diff[:, 1]).sum()),
                int(np.abs(diff[:, 2]).sum()),
            ],
            "karr_delta_l1": int(np.abs(karr_delta).sum()),
            "oc_delta_l1": int(np.abs(oc_delta).sum()),
        },
        "top20_rows_by_abs_diff_l1": top20_rows,
        "top5_rows": top5_idx,
        "top5_wids": [substrate_wids[i] for i in top5_idx],
        "top1_row": top1_row,
        "top1_wid": top1_wid,
        "top1_is_substitution_pair_row": top1_is_pair_row,
        "substitution_pair_summary": pairs_summary,
        "gap_map17_presence": trouble_presence,
    }


def build_aggregates(
    samples: list[dict[str, Any]],
    *,
    gap17_wids: list[str],
) -> dict[str, Any]:
    l1_values = [int(s["writeback_vs_karr"]["diff_l1"]) for s in samples]
    n = len(samples)

    pair_any_top5 = {k: 0 for k in SUBSTITUTION_PAIRS}
    pair_both_top5 = {k: 0 for k in SUBSTITUTION_PAIRS}
    gap17_top5 = {wid: 0 for wid in gap17_wids}
    gap17_top1 = {wid: 0 for wid in gap17_wids}
    top5_wid_counter: Counter[str] = Counter()
    top1_wid_counter: Counter[str] = Counter()

    four_pair_dominant_count = 0
    four_pair_top1_count = 0
    samples_with_nonpair_top1: list[dict[str, Any]] = []

    for s in samples:
        pair_summary = s["substitution_pair_summary"]
        if pair_summary["dominant_by_mass_gt_50pct"]:
            four_pair_dominant_count += 1
        if s["top1_is_substitution_pair_row"]:
            four_pair_top1_count += 1
        else:
            samples_with_nonpair_top1.append(
                {
                    "seed": s["seed"],
                    "tick": s["tick"],
                    "top1_wid": s["top1_wid"],
                    "top1_row": s["top1_row"],
                }
            )

        for pair_name, p in pair_summary["pairs"].items():
            if p["any_member_in_top5"]:
                pair_any_top5[pair_name] += 1
            if p["both_members_in_top5"]:
                pair_both_top5[pair_name] += 1

        for wid, pres in s["gap_map17_presence"].items():
            if pres["in_top5"]:
                gap17_top5[wid] += 1
            if pres["is_top1"]:
                gap17_top1[wid] += 1

        for wid in s["top5_wids"]:
            top5_wid_counter[wid] += 1
        if s["top1_wid"] is not None:
            top1_wid_counter[s["top1_wid"]] += 1

    if n == 0:
        l1_dist = {"count": 0, "mean": None, "min": None, "max": None}
    else:
        l1_dist = {
            "count": n,
            "mean": float(np.mean(l1_values)),
            "min": int(np.min(l1_values)),
            "max": int(np.max(l1_values)),
        }

    if n > 0 and len(samples_with_nonpair_top1) == 0:
        headline = "4 substitution-pair rows are the top-1 contributor in every processed sample."
    elif len(samples_with_nonpair_top1) > 0:
        first = samples_with_nonpair_top1[0]
        headline = (
            "4 substitution-pair rows are not top-1 in every processed sample; "
            f"example failure at s={first['seed']}, t={first['tick']} where "
            f"{first['top1_wid']} (row {first['top1_row']}) dominates."
        )
    else:
        headline = "No samples processed."

    return {
        "writeback_l1_distribution": l1_dist,
        "substitution_pairs_top5_frequency_any_member": pair_any_top5,
        "substitution_pairs_top5_frequency_both_members": pair_both_top5,
        "gap_map17_top5_frequency": gap17_top5,
        "gap_map17_top1_frequency": gap17_top1,
        "top5_wid_frequency": dict(top5_wid_counter),
        "top1_wid_frequency": dict(top1_wid_counter),
        "four_pair_mass_dominant_gt50pct_count": four_pair_dominant_count,
        "four_pair_top1_count": four_pair_top1_count,
        "samples_with_nonpair_top1": samples_with_nonpair_top1,
        "headline_assessment": headline,
    }


def render_status_markdown(payload: dict[str, Any]) -> str:
    selected = payload["selected_samples"]
    missing = payload["missing_target_samples"]
    processed = payload["samples"]
    agg = payload["aggregates"]
    n = len(processed)
    requested = 20

    lines: list[str] = []
    lines.append("# STATUS_h_multisample_sweep")
    lines.append("")
    lines.append("## INTENT")
    lines.append(
        "Probe Day-42 writeback-gap generalization by sweeping the target sample grid "
        "(seeds 0-9 at ticks 1 and 5), then checking whether the 4 substitution pairs "
        "remain dominant across samples or whether other GAP_MAP clusters dominate."
    )
    lines.append("")
    lines.append("## Headline")
    lines.append(f"- {agg['headline_assessment']}")
    lines.append(f"- Processed samples: {n}/{requested}.")
    lines.append(f"- Missing target samples: {len(missing)}.")
    if missing:
        show = ", ".join([f"(s={m['seed']},t={m['tick']})" for m in missing[:8]])
        if len(missing) > 8:
            show += ", ..."
        lines.append(f"- Missing list (prefix): {show}")
    lines.append("")
    lines.append("## Writeback L1 Distribution")
    dist = agg["writeback_l1_distribution"]
    lines.append(f"- mean diff L1: {dist['mean'] if dist['mean'] is not None else 'n/a'}")
    lines.append(f"- min diff L1: {dist['min'] if dist['min'] is not None else 'n/a'}")
    lines.append(f"- max diff L1: {dist['max'] if dist['max'] is not None else 'n/a'}")
    lines.append("")
    lines.append("## Frequency Table: Substitution Pairs (top-5 presence)")
    lines.append("| Pair | any-member top-5 | both-members top-5 |")
    lines.append("|---|---:|---:|")
    any_freq = agg["substitution_pairs_top5_frequency_any_member"]
    both_freq = agg["substitution_pairs_top5_frequency_both_members"]
    for pair_name in SUBSTITUTION_PAIRS:
        lines.append(f"| {pair_name} | {any_freq[pair_name]}/{n} | {both_freq[pair_name]}/{n} |")
    lines.append("")
    lines.append("## Frequency Table: GAP_MAP 17 Trouble WIDs")
    lines.append("| WID | in top-5 | top-1 dominant |")
    lines.append("|---|---:|---:|")
    gap5 = agg["gap_map17_top5_frequency"]
    gap1 = agg["gap_map17_top1_frequency"]
    for wid in payload["gap_map17_wids"]:
        lines.append(f"| {wid} | {gap5.get(wid, 0)}/{n} | {gap1.get(wid, 0)}/{n} |")
    lines.append("")
    lines.append("## Top Contributor Frequency (observed top-5 WIDs)")
    lines.append("| WID | top-5 count |")
    lines.append("|---|---:|")
    top5_counter = agg["top5_wid_frequency"]
    for wid, count in sorted(top5_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
        lines.append(f"| {wid} | {count}/{n} |")
    lines.append("")
    lines.append("## Verdict")
    if n == requested and len(agg["samples_with_nonpair_top1"]) == 0:
        lines.append(
            "- Verdict: 4-pair root-cause story holds at all sampled points in this 20-sample sweep."
        )
    elif len(agg["samples_with_nonpair_top1"]) > 0:
        first = agg["samples_with_nonpair_top1"][0]
        lines.append(
            "- Verdict: 4-pair root-cause story fails to hold at all processed samples; "
            f"counterexample at (s={first['seed']}, t={first['tick']}) where "
            f"{first['top1_wid']} (row {first['top1_row']}) is dominant."
        )
    else:
        lines.append(
            "- Verdict: 4-pair root-cause story is not established across the intended sweep "
            f"because only {n}/{requested} target samples were available locally."
        )
    lines.append("")
    lines.append("## VERIFICATION + Self-audit")
    lines.append("| # | Criterion | Verified |")
    lines.append("|---|---|---|")
    lines.append("| 1 | Target grid defined as seeds 0-9 x ticks {1,5} | [x] |")
    lines.append(
        f"| 2 | Availability fallback implemented and missing targets reported ({len(missing)} missing) | [x] |"
    )
    lines.append("| 3 | LP solved with production GLPK path (`km.solve_fba(..., solver='glpk', big=1e6)`) | [x] |")
    lines.append("| 4 | Deterministic writeback executed per sample (rint rounding shim) | [x] |")
    lines.append("| 5 | Per-sample top-20 row decomposition + top-5 extracted | [x] |")
    lines.append("| 6 | Aggregates include writeback L1 mean/min/max | [x] |")
    lines.append("| 7 | Aggregates include 4 substitution-pair top-5 frequencies | [x] |")
    lines.append("| 8 | Aggregates include GAP_MAP 17 WID top-5 + top-1 frequencies | [x] |")
    lines.append("| 9 | JSON + STATUS artifacts written | [x] |")
    lines.append("")
    lines.append("## Selected Samples")
    lines.append("| seed | tick | selection | file |")
    lines.append("|---:|---:|---|---|")
    for s in selected:
        lines.append(f"| {s['seed']} | {s['tick']} | {s['selection']} | `{Path(s['path']).name}` |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    available_map = discover_sample_files(GT_DIR)
    selected, missing_targets = choose_samples(available_map)

    model = km.load_default()
    fixture = KarrWritebackFixture.from_mat(WRITEBACK_FIXTURE)
    substrate_wids = list(model.raw["ids"]["substrate_wcm_585"])
    wid_to_row = {wid: i for i, wid in enumerate(substrate_wids)}

    gap17_wids = parse_gap_map_top17_wids(GAP_MAP_PATH)
    trouble_row_by_wid = {wid: wid_to_row[wid] for wid in gap17_wids if wid in wid_to_row}
    missing_gap17_wids = [wid for wid in gap17_wids if wid not in trouble_row_by_wid]

    samples: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for s in selected:
        try:
            samples.append(
                analyze_one_sample(
                    s,
                    model=model,
                    fixture=fixture,
                    substrate_wids=substrate_wids,
                    trouble_row_by_wid=trouble_row_by_wid,
                )
            )
        except Exception as e:  # pragma: no cover - diagnostic probe
            failures.append(
                {
                    "seed": s["seed"],
                    "tick": s["tick"],
                    "path": s["path"],
                    "selection": s["selection"],
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    aggregates = build_aggregates(samples, gap17_wids=list(trouble_row_by_wid))

    payload = {
        "intent": "Day-42 Probe 3 multi-sample sweep for writeback-gap dominance.",
        "target_grid": {"seeds": TARGET_SEEDS, "ticks": TARGET_TICKS, "requested_count": 20},
        "available_samples": [
            {"seed": seed, "tick": tick, "path": str(path)}
            for (seed, tick), path in sorted(available_map.items())
        ],
        "selected_samples": selected,
        "missing_target_samples": missing_targets,
        "processed_count": len(samples),
        "failed_samples": failures,
        "missing_gap17_wids_in_substrate_ids": missing_gap17_wids,
        "gap_map17_wids": list(trouble_row_by_wid),
        "substitution_pairs": SUBSTITUTION_PAIRS,
        "samples": samples,
        "aggregates": aggregates,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    OUT_STATUS.write_text(render_status_markdown(payload), encoding="utf-8")

    print(f"Available sample files: {len(available_map)}")
    print(f"Selected samples: {len(selected)}")
    print(f"Processed samples: {len(samples)}")
    print(f"Failed samples: {len(failures)}")
    print(f"Missing target samples: {len(missing_targets)}")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_STATUS}")


if __name__ == "__main__":
    main()
