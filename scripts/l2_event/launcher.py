"""Planning core + MATLAB command builder for the L2.event window extractor.

Companion to ``scripts/l22_extraction/launcher.py`` (same planning shape:
MATLAB-free, side-effect-light, validate-before-skip, JSON-serializable
plan) but scoped to the two M4 event-window kinds defined in
``docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md``:

* ``fixed``  -- a caller-supplied ``tick_offset`` burn-in window (e.g.
  RibosomeAssembly's tick_offset=200 firing window).
* ``anchor`` -- a division-anchored window whose start/anchor tick is
  discovered by ``extract_per_process_traces_v2.m`` from a REAL simulation
  completion signal (e.g. Cytokinesis/CellGeometry.pinched), never supplied
  or fabricated by this launcher.

This module never invokes MATLAB and never reads a real Karr oracle trace
to decide pass/fail -- ``plan_event_window_extraction``'s validate-before-skip
step re-uses ``scripts/l2_event/window_loader.load_event_window`` (the same
authoritative D1/M4 refusal gauntlet a real gate computation would apply)
strictly to classify an *already-produced* trace as structurally
compliant or not; it does not loosen that loader and does not derive any
planning decision from the trace's per-tick numeric content.

Actual MATLAB process spawning is out of scope for this module (and for
this task -- "no MATLAB execution/extraction"): ``build_matlab_command``
only returns the command string a future, separately-run job would use.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
# Self-contained sys.path bootstrap (mirrors scripts/l22_extraction/launcher.py):
# makes `scripts.l2_event.*` absolute imports work whether this module is run
# directly as a script or imported by pytest from tests/scripts/.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.window_loader import EventWindowRefused, load_event_window  # noqa: E402

KARR_NATIVE_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native"
EXTRACTOR_SCRIPT = REPO_ROOT / "scripts" / "matlab" / "extract_per_process_traces_v2.m"
DEFAULT_N_TICKS = 100
DEFAULT_MAX_SEARCH_TICKS = 50000
DEFAULT_ANCHOR_SIGNAL_PROPERTY = "geometry"
DEFAULT_ANCHOR_SIGNAL_FIELD = "pinched"

WindowContract = Literal["fixed", "anchor"]
_VALID_WINDOW_CONTRACTS = ("fixed", "anchor")


class WindowContractConfigError(ValueError):
    """Raised for any launcher-side request that would violate the D1/M4
    stride-1 event-window contract before MATLAB is ever invoked.

    Examples: an explicit ``stride != 1`` request, a ``tick_offset``
    supplied alongside ``window_contract='anchor'`` (the window start must
    be discovered, not requested), or an unknown ``window_contract`` value.
    This is a config-time refusal, distinct from
    :class:`scripts.l2_event.window_loader.EventWindowRefused`, which is
    raised only against an already-produced trace file.
    """


def event_window_output_dir(seed: int, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    """The M4 contract's fixed event-window layout:
    ``per_process_traces_v2_event_s{seed:03d}/``. Deliberately distinct
    from ``scripts/l22_extraction/launcher.seed_output_dir``'s
    ``per_process_traces_v2_s{seed:03d}/`` (the standard mid-cycle layout)
    -- the two directory families are how ``window_loader.classify_trace_dir``
    and ``load_event_window``'s ``tick_offset`` discriminator distinguish an
    event-window trace from a standard mid-cycle trace at all.
    """
    return karr_native_root / f"per_process_traces_v2_event_s{int(seed):03d}"


def event_window_mat_path(
    process: str, seed: int, *, n_ticks: int = DEFAULT_N_TICKS, karr_native_root: Path = KARR_NATIVE_ROOT
) -> Path:
    return event_window_output_dir(seed, karr_native_root=karr_native_root) / f"{process}_{n_ticks}ticks.mat"


@dataclass(frozen=True)
class FixedWindowSpec:
    """A stride-1 fixed burn-in event window (e.g. RibosomeAssembly)."""

    process: str
    seed: int
    tick_offset: int
    n_ticks: int = DEFAULT_N_TICKS
    window_contract: str = field(default="fixed", init=False)

    def __post_init__(self) -> None:
        if self.tick_offset < 0:
            raise WindowContractConfigError(f"tick_offset must be >= 0, got {self.tick_offset}")
        if self.n_ticks < 1:
            raise WindowContractConfigError(f"n_ticks must be >= 1, got {self.n_ticks}")


@dataclass(frozen=True)
class AnchorWindowSpec:
    """A division-anchored event window (e.g. Cytokinesis).

    ``n_ticks`` is the only window-*length* decision this launcher accepts
    from a caller; the window's *position* (tick_start/window_anchor) is
    never supplied here -- it is discovered at extraction time from a real
    simulation signal. ``n_ticks`` intentionally has no launcher-side
    default distinct from the repo-wide ``DEFAULT_N_TICKS`` convention (see
    also ``scripts/l22_extraction/launcher.DEFAULT_N_TICKS``); it is NOT a
    stand-in for the still-unresolved QO1 (exact division-relative window
    bounds, see docs/phase_f/L2_EVENT_GATE_SPEC_v4.md) operator decision.
    """

    process: str
    seed: int
    n_ticks: int = DEFAULT_N_TICKS
    max_search_ticks: int = DEFAULT_MAX_SEARCH_TICKS
    signal_property: str = DEFAULT_ANCHOR_SIGNAL_PROPERTY
    signal_field: str = DEFAULT_ANCHOR_SIGNAL_FIELD
    window_contract: str = field(default="anchor", init=False)

    def __post_init__(self) -> None:
        if self.n_ticks < 1:
            raise WindowContractConfigError(f"n_ticks must be >= 1, got {self.n_ticks}")
        if self.max_search_ticks < self.n_ticks:
            raise WindowContractConfigError(
                f"max_search_ticks ({self.max_search_ticks}) must be >= n_ticks ({self.n_ticks}); "
                "a search bound shorter than the window itself can never find a full window."
            )
        if not self.signal_property or not self.signal_field:
            raise WindowContractConfigError(
                "signal_property/signal_field must both be non-empty real-state accessors "
                "(e.g. 'geometry'/'pinched'); an anchor window with no real signal to check "
                "would have no way to discover a non-fabricated anchor tick."
            )


WindowSpec = FixedWindowSpec | AnchorWindowSpec


def output_dir_for(spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    return event_window_output_dir(spec.seed, karr_native_root=karr_native_root)


def mat_path_for(spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    return event_window_mat_path(spec.process, spec.seed, n_ticks=spec.n_ticks, karr_native_root=karr_native_root)


def build_matlab_command(
    spec: WindowSpec,
    *,
    log_relpath: str | None = None,
    include_addpath: bool = True,
    karr_native_root: Path = KARR_NATIVE_ROOT,
) -> str:
    """Build the MATLAB statement(s) for one (process, seed) event-window
    extraction job. Never executed by this module -- this only returns the
    command string a separately-run MATLAB process would use.
    """
    output_subdir = output_dir_for(spec, karr_native_root=karr_native_root).name
    proc_arg = f"{{'{spec.process}'}}"

    if isinstance(spec, FixedWindowSpec):
        call = (
            f"extract_per_process_traces_v2({proc_arg}, '{output_subdir}', {int(spec.n_ticks)}, "
            f"uint32({int(spec.seed)}), {int(spec.tick_offset)}, 'fixed');"
        )
    elif isinstance(spec, AnchorWindowSpec):
        anchor_opts = (
            "struct("
            f"'max_search_ticks', {int(spec.max_search_ticks)}, "
            f"'signal_property', '{spec.signal_property}', "
            f"'signal_field', '{spec.signal_field}')"
        )
        call = (
            f"extract_per_process_traces_v2({proc_arg}, '{output_subdir}', {int(spec.n_ticks)}, "
            f"uint32({int(spec.seed)}), [], 'anchor', {anchor_opts});"
        )
    else:  # pragma: no cover - exhaustiveness guard
        raise WindowContractConfigError(f"Unrecognized window spec type: {type(spec)!r}")

    prefix = "addpath('scripts/matlab'); " if include_addpath else ""
    if log_relpath is None:
        return f"{prefix}{call}"
    return (
        f"{prefix}"
        f"diary('{log_relpath}'); "
        f"try; {call} catch err; disp(getReport(err, 'extended', 'hyperlinks', 'off')); end; "
        f"diary off;"
    )


def event_window_log_relpath(
    process: str, seed: int, *, log_dir: str = "artifacts/l2_event_extraction/logs"
) -> str:
    return f"{log_dir}/{process}_seed{int(seed):03d}.log"


def _window_boundary_kind(path: Path) -> str:
    """Classify which of ``tick_end``/``window_anchor`` an on-disk trace's
    metadata carries: ``'fixed'``, ``'anchor'``, ``'both'``, or
    ``'neither'``. Used only to detect a window-kind MISMATCH between what
    is on disk and what was requested (rule-6/rule-8 guard against
    "duplicate extraction" silently being accepted as satisfying a
    different request) -- never to decide stride/completeness, which stays
    the sole authority of ``window_loader``.
    """
    import h5py

    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if metadata is None:
            return "neither"
        has_end = "tick_end" in metadata
        has_anchor = "window_anchor" in metadata
    if has_end and has_anchor:
        return "both"
    if has_end:
        return "fixed"
    if has_anchor:
        return "anchor"
    return "neither"


@dataclass
class WindowDecision:
    process: str
    seed: int
    window_contract: str
    path: str
    action: str  # "skip_valid" | "generate_missing" | "regenerate_invalid"
    reason: str | None = None


@dataclass
class WindowJob:
    process: str
    seed: int
    window_contract: str
    output_dir: str
    matlab_command: str
    log_path: str


@dataclass
class WindowExtractionPlan:
    n_ticks: int
    decisions: list[WindowDecision]
    jobs: list[WindowJob]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_ticks": self.n_ticks,
            "decisions": [asdict(d) for d in self.decisions],
            "jobs": [asdict(j) for j in self.jobs],
            "generated_at": self.generated_at,
        }


def validate_existing_event_window(
    path: Path,
    spec: WindowSpec,
    *,
    required_observables: tuple[str, ...] = (),
) -> tuple[bool, str]:
    """Validate-before-skip (never existence-only) for one on-disk trace
    against one requested window spec.

    Re-uses ``window_loader.load_event_window(..., require_stride_contract=True)``
    -- the same refusal gauntlet a real (non-smoke) L2.event gate
    computation applies -- so a trace this function calls valid is, by
    construction, one the loader will also accept; and a trace the loader
    would refuse (missing stride contract, stride != 1, sparse/partial
    grid, or not even an event-window trace at all) is never marked
    ``skip_valid`` here. Returns ``(ok, reason)``; ``reason`` is empty iff
    ``ok`` is True.
    """
    if not path.exists():
        return False, "file does not exist"

    try:
        window = load_event_window(path, required_observables=required_observables, require_stride_contract=True)
    except EventWindowRefused as exc:
        return False, f"{exc.reason}: {exc}"

    if window.process_name != spec.process:
        return False, f"metadata.process_name={window.process_name!r} != expected {spec.process!r}"
    if window.seed != int(spec.seed):
        return False, f"metadata.rng_seed={window.seed!r} != expected {spec.seed!r}"
    if window.n_ticks != int(spec.n_ticks):
        return False, f"metadata.n_ticks={window.n_ticks!r} != expected {spec.n_ticks!r}"

    on_disk_kind = _window_boundary_kind(path)
    if on_disk_kind != spec.window_contract:
        return False, (
            f"on-disk window kind={on_disk_kind!r} != requested window_contract={spec.window_contract!r} "
            "(a trace produced under a different window_contract must never be silently reused)"
        )

    return True, ""


def plan_event_window_extraction(
    specs: list[WindowSpec],
    *,
    karr_native_root: Path = KARR_NATIVE_ROOT,
    required_observables: tuple[str, ...] = (),
    validate_existing: bool = True,
) -> WindowExtractionPlan:
    """Build a resumable extraction plan for a list of (process, seed,
    window_contract) specs.

    For every spec, decides ``skip_valid`` / ``generate_missing`` /
    ``regenerate_invalid`` via ``validate_existing_event_window`` (a real
    structural + contract-compliance pass, not an existence-only check)
    when ``validate_existing`` is True. Every job's ``output_dir`` is keyed
    by seed (``per_process_traces_v2_event_s{seed:03d}/``), matching the M4
    contract layout.
    """
    decisions: list[WindowDecision] = []
    jobs: list[WindowJob] = []
    n_ticks_seen: set[int] = set()

    for spec in specs:
        n_ticks_seen.add(int(spec.n_ticks))
        path = mat_path_for(spec, karr_native_root=karr_native_root)

        if not validate_existing:
            if path.exists():
                decisions.append(
                    WindowDecision(
                        process=spec.process,
                        seed=spec.seed,
                        window_contract=spec.window_contract,
                        path=str(path),
                        action="skip_valid",
                    )
                )
                continue
        else:
            ok, reason = (False, "file does not exist")
            if path.exists():
                ok, reason = validate_existing_event_window(path, spec, required_observables=required_observables)
            if ok:
                decisions.append(
                    WindowDecision(
                        process=spec.process,
                        seed=spec.seed,
                        window_contract=spec.window_contract,
                        path=str(path),
                        action="skip_valid",
                    )
                )
                continue
            action = "regenerate_invalid" if path.exists() else "generate_missing"
            decisions.append(
                WindowDecision(
                    process=spec.process,
                    seed=spec.seed,
                    window_contract=spec.window_contract,
                    path=str(path),
                    action=action,
                    reason=reason if path.exists() else None,
                )
            )

        output_dir = output_dir_for(spec, karr_native_root=karr_native_root)
        log_relpath = event_window_log_relpath(spec.process, spec.seed)
        command = build_matlab_command(spec, log_relpath=log_relpath)
        jobs.append(
            WindowJob(
                process=spec.process,
                seed=spec.seed,
                window_contract=spec.window_contract,
                output_dir=str(output_dir),
                matlab_command=command,
                log_path=log_relpath,
            )
        )

    n_ticks = n_ticks_seen.pop() if len(n_ticks_seen) == 1 else -1
    return WindowExtractionPlan(
        n_ticks=n_ticks,
        decisions=decisions,
        jobs=jobs,
        generated_at=datetime.now(UTC).isoformat(),
    )


def apply_invalidations(plan: WindowExtractionPlan) -> list[str]:
    """Delete files the plan marked ``regenerate_invalid`` so a subsequent
    MATLAB run (whose own skip check is existence-only, see
    ``extract_per_process_traces_v2.m``) will actually regenerate them
    instead of silently reusing a contract-incomplete trace.
    """
    deleted: list[str] = []
    for decision in plan.decisions:
        if decision.action == "regenerate_invalid":
            path = Path(decision.path)
            if path.exists():
                path.unlink()
                deleted.append(str(path))
    return deleted


def _spec_from_dict(row: dict[str, Any]) -> WindowSpec:
    window_contract = row.get("window_contract")
    if window_contract == "fixed":
        return FixedWindowSpec(
            process=row["process"],
            seed=int(row["seed"]),
            tick_offset=int(row["tick_offset"]),
            n_ticks=int(row.get("n_ticks", DEFAULT_N_TICKS)),
        )
    if window_contract == "anchor":
        return AnchorWindowSpec(
            process=row["process"],
            seed=int(row["seed"]),
            n_ticks=int(row.get("n_ticks", DEFAULT_N_TICKS)),
            max_search_ticks=int(row.get("max_search_ticks", DEFAULT_MAX_SEARCH_TICKS)),
            signal_property=str(row.get("signal_property", DEFAULT_ANCHOR_SIGNAL_PROPERTY)),
            signal_field=str(row.get("signal_field", DEFAULT_ANCHOR_SIGNAL_FIELD)),
        )
    raise WindowContractConfigError(
        f"row {row!r}: window_contract must be one of {_VALID_WINDOW_CONTRACTS}, got {window_contract!r}"
    )


def _cmd_plan(args: argparse.Namespace) -> int:
    rows = json.loads(Path(args.specs).read_text(encoding="utf-8"))
    specs = [_spec_from_dict(row) for row in rows]
    plan = plan_event_window_extraction(specs, validate_existing=not args.no_validate)
    deleted: list[str] = []
    if args.apply_invalidation:
        deleted = apply_invalidations(plan)
    out = plan.to_dict()
    out["deleted_invalid_files"] = deleted
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[l2_event.launcher] wrote plan with {len(plan.jobs)} jobs to {args.out}")
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan_parser = sub.add_parser(
        "plan",
        help=(
            "Build a resumable event-window extraction plan JSON from a JSON "
            "list of {process, seed, window_contract, ...} spec rows."
        ),
    )
    plan_parser.add_argument(
        "--specs",
        required=True,
        help=(
            'Path to a JSON file: a list of rows, each either '
            '{"process", "seed", "window_contract": "fixed", "tick_offset", "n_ticks"?} or '
            '{"process", "seed", "window_contract": "anchor", "n_ticks"?, "max_search_ticks"?, '
            '"signal_property"?, "signal_field"?}.'
        ),
    )
    plan_parser.add_argument("--no-validate", action="store_true", help="Existence-only skip (debug only).")
    plan_parser.add_argument(
        "--apply-invalidation", action="store_true", help="Delete files marked regenerate_invalid."
    )
    plan_parser.add_argument("--out", required=True)
    plan_parser.set_defaults(func=_cmd_plan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
