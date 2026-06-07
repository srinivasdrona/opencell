from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

SAMPLED_TICKS = (1000, 3000, 5000)
ENERGY_OBSERVABLES = {"ATP", "GTP", "AMP", "GMP", "ADP", "GDP", "H+", "H2O", "Pi", "PPi"}
ARTIFACT_CANDIDATES = (
    Path("E:/opencell/artifacts/ensemble_wave2_post_l1c_20260528_123756"),
    Path("/mnt/e/opencell/artifacts/ensemble_wave2_post_l1c_20260528_123756"),
)
OUTPUT_REL = Path("docs/phase_e/L2_TOLERANCE_TABLE.md")


@dataclass(frozen=True)
class ObservableTolerance:
    observable: str
    rtol: float
    atol: float


@dataclass
class ProcessTolerance:
    process_name: str
    trace_name: str
    n_seeds: int
    n_observables: int
    rtol_median: float
    atol_median: float
    rtol_max_obs: float
    atol_max_obs: float
    worst_observable: str
    notes: str
    observables: list[ObservableTolerance]


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def find_artifact_root() -> Path:
    for candidate in ARTIFACT_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Could not resolve ensemble artifact root. Tried: "
        + ", ".join(str(p) for p in ARTIFACT_CANDIDATES)
    )


def discover_canonical_processes(repo_root: Path) -> list[str]:
    tests_dir = repo_root / "tests" / "vivarium"
    names: set[str] = set()
    for path in tests_dir.glob("test_karr_*_l2_replay.py"):
        stem = path.stem
        names.add(stem.replace("test_", "").replace("_l2_replay", ""))
    out = sorted(names)
    if len(out) != 28:
        raise RuntimeError(f"Expected 28 canonical L2 processes, found {len(out)}: {out}")
    return out


def discover_seed_dirs(artifact_root: Path) -> list[Path]:
    seeds = sorted(
        [p for p in artifact_root.iterdir() if p.is_dir() and p.name.startswith("seed_")],
        key=lambda p: p.name,
    )
    if not seeds:
        raise RuntimeError(f"No seed_* directories found under {artifact_root}")
    return seeds


def csv_intersection(seed_dirs: list[Path]) -> set[str]:
    inter: set[str] | None = None
    for seed in seed_dirs:
        names = {p.stem for p in (seed / "process_traces").glob("*.csv")}
        inter = names if inter is None else inter.intersection(names)
    return inter if inter is not None else set()


def _parse_tick(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_trace_csv(path: Path) -> dict[str, dict[int, float]]:
    """Return observable -> tick -> value for one seed/process trace CSV."""
    out: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if "tick" not in fieldnames:
            return {}

        # Most wave2 traces are long-form: tick,process_name,substrate,delta.
        if "substrate" in fieldnames and "delta" in fieldnames:
            for row in reader:
                tick = _parse_tick(row.get("tick", ""))
                if tick is None:
                    continue
                obs = str(row.get("substrate", "")).strip()
                if not obs:
                    continue
                try:
                    val = float(row.get("delta", "0") or 0.0)
                except ValueError:
                    continue
                out[obs][tick] += val
            return {k: dict(v) for k, v in out.items()}

        # Generic wide-format fallback: treat numeric columns as observables.
        numeric_candidates = [c for c in fieldnames if c not in {"tick", "process_name"}]
        for row in reader:
            tick = _parse_tick(row.get("tick", ""))
            if tick is None:
                continue
            for col in numeric_candidates:
                raw = row.get(col, "")
                if raw in ("", None):
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                out[col][tick] += val
    return {k: dict(v) for k, v in out.items()}


def resolve_trace_name(canonical_name: str, intersection: set[str]) -> str | None:
    if canonical_name in intersection:
        return canonical_name
    light_alias = f"{canonical_name}_light"
    if light_alias in intersection:
        return light_alias
    return None


def compute_process_tolerance(
    *,
    canonical_name: str,
    trace_name: str,
    seed_dirs: list[Path],
) -> ProcessTolerance | None:
    per_seed: list[dict[str, dict[int, float]]] = []
    for seed in seed_dirs:
        csv_path = seed / "process_traces" / f"{trace_name}.csv"
        if not csv_path.exists():
            return None
        per_seed.append(parse_trace_csv(csv_path))

    observable_names = sorted(set().union(*(d.keys() for d in per_seed)))
    if not observable_names:
        return None

    obs_tolerances: list[ObservableTolerance] = []
    for obs in observable_names:
        rtol_ticks: list[float] = []
        atol_ticks: list[float] = []
        for tick in SAMPLED_TICKS:
            vals = [seed_obs.get(obs, {}).get(tick, 0.0) for seed_obs in per_seed]
            mu = sum(vals) / len(vals)
            variance = sum((v - mu) ** 2 for v in vals) / len(vals)
            sigma = math.sqrt(max(variance, 0.0))
            denom = max(abs(mu), 1.0)
            rtol_ticks.append((3.0 * sigma) / denom)
            atol_ticks.append(3.0 * sigma)
        obs_tolerances.append(
            ObservableTolerance(observable=obs, rtol=max(rtol_ticks), atol=max(atol_ticks))
        )

    rtol_all = [x.rtol for x in obs_tolerances]
    atol_all = [x.atol for x in obs_tolerances]
    non_energy = [x for x in obs_tolerances if x.observable not in ENERGY_OBSERVABLES]
    notes: list[str] = []

    if trace_name != canonical_name:
        notes.append(f"trace-alias={trace_name}")

    use_for_rollup = obs_tolerances
    if non_energy:
        rtol_all_med = median(rtol_all)
        atol_all_med = median(atol_all)
        rtol_non_energy_med = median([x.rtol for x in non_energy])
        atol_non_energy_med = median([x.atol for x in non_energy])
        if (rtol_all_med > rtol_non_energy_med) or (atol_all_med > atol_non_energy_med):
            use_for_rollup = non_energy
            notes.append("rollup-median-excludes-widening-energy-observables")

    rtol_median = median([x.rtol for x in use_for_rollup])
    atol_median = median([x.atol for x in use_for_rollup])
    worst_rtol = max(obs_tolerances, key=lambda x: x.rtol)
    worst_atol = max(obs_tolerances, key=lambda x: x.atol)
    worst_name = (
        worst_rtol.observable
        if worst_rtol.observable == worst_atol.observable
        else f"rtol:{worst_rtol.observable}; atol:{worst_atol.observable}"
    )

    energy_present = sorted({x.observable for x in obs_tolerances if x.observable in ENERGY_OBSERVABLES})
    if energy_present:
        notes.append("energy-observables=" + ",".join(energy_present))

    return ProcessTolerance(
        process_name=canonical_name,
        trace_name=trace_name,
        n_seeds=len(seed_dirs),
        n_observables=len(obs_tolerances),
        rtol_median=rtol_median,
        atol_median=atol_median,
        rtol_max_obs=worst_rtol.rtol,
        atol_max_obs=worst_atol.atol,
        worst_observable=worst_name,
        notes="; ".join(notes),
        observables=sorted(obs_tolerances, key=lambda x: x.observable),
    )


def write_markdown(
    *,
    out_path: Path,
    artifact_root: Path,
    n_seeds: int,
    canonical_processes: list[str],
    with_data: list[ProcessTolerance],
    no_data: list[str],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    rows = sorted(with_data, key=lambda x: x.rtol_median, reverse=True)
    energy_rows: list[tuple[str, str, float, float, str]] = []
    for proc in rows:
        included = {o.observable for o in proc.observables}
        non_energy = [o for o in proc.observables if o.observable not in ENERGY_OBSERVABLES]
        if non_energy:
            all_rtol_med = median([o.rtol for o in proc.observables])
            all_atol_med = median([o.atol for o in proc.observables])
            non_rtol_med = median([o.rtol for o in non_energy])
            non_atol_med = median([o.atol for o in non_energy])
            if (all_rtol_med > non_rtol_med) or (all_atol_med > non_atol_med):
                included = {o.observable for o in non_energy}
        for obs in proc.observables:
            if obs.observable in ENERGY_OBSERVABLES:
                energy_rows.append(
                    (
                        proc.process_name,
                        obs.observable,
                        obs.rtol,
                        obs.atol,
                        "yes" if obs.observable in included else "no",
                    )
                )

    lines: list[str] = []
    lines.append("# L2 Tolerance Table")
    lines.append("")
    lines.append(f"Generated: {generated}")
    lines.append("")
    lines.append("## 1. Methodology")
    lines.append("")
    lines.append(
        f"- Inputs: `{artifact_root}/seed_*/process_traces/*.csv` (read-only), using filename intersection across discovered seeds."
    )
    lines.append(
        "- Canonical process set: 28 `karr_*` names discovered from `tests/vivarium/test_karr_*_l2_replay.py`."
    )
    lines.append(f"- Sample ticks: `{SAMPLED_TICKS}`.")
    lines.append(
        "- Per-observable at each sampled tick: `mu=mean(across seeds)`, `sigma=std(across seeds)`, `rtol=3*sigma/max(abs(mu),1)`, `atol=3*sigma`."
    )
    lines.append(
        "- Per-observable tolerance: max across sampled ticks (conservative mid-cycle band)."
    )
    lines.append(
        "- Per-process tolerance: median across observables for `rtol` and `atol` (conservative-but-not-pessimistic against single-observable outliers)."
    )
    lines.append(
        "- Energy observables (`ATP,GTP,AMP,GMP,ADP,GDP,H+,H2O,Pi,PPi`) are recorded explicitly; if they widen the roll-up median, they are excluded from roll-up median only."
    )
    lines.append("")
    lines.append("## 2. Per-process table")
    lines.append("")
    lines.append(
        "| process_name | n_seeds | n_observables | rtol_median | atol_median | rtol_max_obs | atol_max_obs | worst_observable | notes |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|")
    for proc in rows:
        notes = proc.notes if proc.notes else ""
        lines.append(
            f"| {proc.process_name} | {proc.n_seeds} | {proc.n_observables} | {_fmt(proc.rtol_median)} | {_fmt(proc.atol_median)} | {_fmt(proc.rtol_max_obs)} | {_fmt(proc.atol_max_obs)} | {proc.worst_observable} | {notes} |"
        )
    for name in sorted(no_data):
        lines.append(
            f"| {name} | {n_seeds} | 0 | NA | NA | NA | NA | NA | no-ensemble-data |"
        )

    lines.append("")
    lines.append("### Energy-observable detail")
    lines.append("")
    lines.append(
        "| process_name | observable | rtol | atol | included_in_rollup_median |"
    )
    lines.append("|---|---|---:|---:|---|")
    for process_name, observable, rtol, atol, included in sorted(energy_rows):
        lines.append(
            f"| {process_name} | {observable} | {_fmt(rtol)} | {_fmt(atol)} | {included} |"
        )
    if not energy_rows:
        lines.append("| _none_ | _none_ | 0 | 0 | no |")

    lines.append("")
    lines.append("## 3. Coverage gaps")
    lines.append("")
    lines.append(
        f"- Canonical processes discovered: {len(canonical_processes)}; with ensemble data: {len(with_data)}; no ensemble data: {len(no_data)}."
    )
    if no_data:
        for name in no_data:
            lines.append(
                f"- `{name}`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance)."
            )
    else:
        lines.append("- None. All 28 canonical processes resolved to ensemble traces.")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    artifact_root = find_artifact_root()
    seed_dirs = discover_seed_dirs(artifact_root)
    intersection = csv_intersection(seed_dirs)
    canonical = discover_canonical_processes(repo_root)

    with_data: list[ProcessTolerance] = []
    no_data: list[str] = []

    for canonical_name in canonical:
        trace_name = resolve_trace_name(canonical_name, intersection)
        if trace_name is None:
            no_data.append(canonical_name)
            continue
        process_tol = compute_process_tolerance(
            canonical_name=canonical_name,
            trace_name=trace_name,
            seed_dirs=seed_dirs,
        )
        if process_tol is None:
            no_data.append(canonical_name)
            continue
        with_data.append(process_tol)

    out_path = repo_root / OUTPUT_REL
    write_markdown(
        out_path=out_path,
        artifact_root=artifact_root,
        n_seeds=len(seed_dirs),
        canonical_processes=canonical,
        with_data=with_data,
        no_data=sorted(no_data),
    )

    print(
        f"wrote {OUTPUT_REL.as_posix()} with {len(canonical)} processes, "
        f"{len(with_data)} with-data, {len(no_data)} no-data"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
