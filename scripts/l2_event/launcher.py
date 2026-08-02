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
import hashlib
import json
import os
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
# 'boolean_transition' generic default field kept for backward compatibility;
# an anchor spec's *effective* default field depends on signal_kind -- see
# AnchorWindowSpec.__post_init__, which mirrors
# extract_per_process_traces_v2.m's default_anchor_opts() exactly (diameter_
# decrease -> 'pinchedDiameter', boolean_transition -> 'pinched').
DEFAULT_ANCHOR_SIGNAL_FIELD = "pinched"
DEFAULT_ANCHOR_SIGNAL_KIND = "diameter_decrease"
_VALID_ANCHOR_SIGNAL_KINDS = ("diameter_decrease", "boolean_transition")

# The smallest source-faithful flattened numeric event-observable projection
# `merge_event_observables()` (extract_per_process_traces_v2.m) writes for
# signal_kind='diameter_decrease' anchor windows (Cytokinesis). Exposed here
# so callers (and the future Cytokinesis adapter, in the sibling worktree)
# have one canonical name list instead of re-deriving it.
CYTOKINESIS_DIAMETER_OBSERVABLE = "pinchedDiameter"
CYTOKINESIS_FTSZRING_OBSERVABLES = (
    "ftsZRing_numEdgesOneStraight",
    "ftsZRing_numEdgesTwoStraight",
    "ftsZRing_numEdgesTwoBent",
    "ftsZRing_numResidualBent",
)
CYTOKINESIS_SCALAR_FINITE_OBSERVABLES = (CYTOKINESIS_DIAMETER_OBSERVABLE, *CYTOKINESIS_FTSZRING_OBSERVABLES)

# Suffix for a not-yet-validated regeneration's output directory (see
# `temp_output_subdir_for`/`finalize_atomic_regeneration`). Never the real
# per-process-trace directory a `skip_valid` lookup or the standard mid-cycle
# extractor would resolve to.
TEMP_REGEN_SUFFIX = ".tmp-regen"

WindowContract = Literal["fixed", "anchor"]
_VALID_WINDOW_CONTRACTS = ("fixed", "anchor")


def _matlab_quote(value: str) -> str:
    """Quote ``value`` as a single-quoted MATLAB char-vector literal, safe
    against embedded single quotes (Opus 5 rejection finding: "MATLAB
    quoting ... incomplete"). MATLAB's own escaping convention is doubling
    the embedded quote (``'it''s'``); this mirrors that exactly. An
    embedded newline/carriage-return is rejected outright -- no legitimate
    process name, signal property/field, or output-subdir component can
    contain one, so silently accepting it would only be a MATLAB-source-
    injection vector via a crafted spec field.
    """
    if "\n" in value or "\r" in value:
        raise WindowContractConfigError(
            f"value {value!r} contains a newline/carriage-return; not a safe MATLAB string literal"
        )
    return "'" + value.replace("'", "''") + "'"


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
    required_observables: tuple[str, ...]
    n_ticks: int = DEFAULT_N_TICKS
    window_contract: str = field(default="fixed", init=False)

    def __post_init__(self) -> None:
        if self.tick_offset < 0:
            raise WindowContractConfigError(f"tick_offset must be >= 0, got {self.tick_offset}")
        if self.n_ticks < 1:
            raise WindowContractConfigError(f"n_ticks must be >= 1, got {self.n_ticks}")
        if not self.required_observables:
            raise WindowContractConfigError(
                "required_observables must be a non-empty, spec-owned set of D1 observable "
                "names -- it must never default to an empty tuple that production planning "
                "can silently omit (Opus 5 rejection finding)."
            )


@dataclass(frozen=True)
class AnchorWindowSpec:
    """A division-anchored event window (e.g. Cytokinesis).

    ``n_ticks`` is the only window-*length* decision this launcher accepts
    from a caller; the window's *position* (tick_start/window_anchor,
    and -- for ``signal_kind='diameter_decrease'`` -- ``onset_tick``) is
    never supplied here -- it is discovered at extraction time from a real
    simulation signal. ``n_ticks`` intentionally has no launcher-side
    default distinct from the repo-wide ``DEFAULT_N_TICKS`` convention (see
    also ``scripts/l22_extraction/launcher.DEFAULT_N_TICKS``); it is NOT a
    stand-in for the still-unresolved QO1 (exact division-relative window
    bounds, see docs/phase_f/L2_EVENT_GATE_SPEC_v4.md) operator decision.

    ``signal_kind`` selects which of the two ratified observed predicates
    (docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md) the MATLAB
    extractor evaluates: ``'diameter_decrease'`` (the ratified Cytokinesis
    timing decision, 2026-08-02 -- onset = first strict
    ``CellGeometry.pinchedDiameter`` decrease, completion = the later
    positive->zero transition) or the generic ``'boolean_transition'``
    (first observed false->true transition of an arbitrary process
    boolean, with a captured prior value). Defaults to
    ``'diameter_decrease'`` (``DEFAULT_ANCHOR_SIGNAL_KIND``), matching
    ``extract_per_process_traces_v2.m``'s own ``default_anchor_opts()``.
    """

    process: str
    seed: int
    required_observables: tuple[str, ...]
    n_ticks: int = DEFAULT_N_TICKS
    max_search_ticks: int = DEFAULT_MAX_SEARCH_TICKS
    signal_kind: str = DEFAULT_ANCHOR_SIGNAL_KIND
    signal_property: str = DEFAULT_ANCHOR_SIGNAL_PROPERTY
    signal_field: str | None = None
    # Subset of required_observables that must be scalar-shaped and finite
    # at every tick (D1's numeric event-observable projection guarantee,
    # see window_loader.load_event_window's require_scalar_finite_observables).
    # For Cytokinesis, pass CYTOKINESIS_SCALAR_FINITE_OBSERVABLES.
    scalar_finite_observables: tuple[str, ...] = ()
    window_contract: str = field(default="anchor", init=False)

    def __post_init__(self) -> None:
        if self.n_ticks < 1:
            raise WindowContractConfigError(f"n_ticks must be >= 1, got {self.n_ticks}")
        if self.max_search_ticks < self.n_ticks:
            raise WindowContractConfigError(
                f"max_search_ticks ({self.max_search_ticks}) must be >= n_ticks ({self.n_ticks}); "
                "a search bound shorter than the window itself can never find a full window."
            )
        if self.signal_kind not in _VALID_ANCHOR_SIGNAL_KINDS:
            raise WindowContractConfigError(
                f"signal_kind must be one of {_VALID_ANCHOR_SIGNAL_KINDS}, got {self.signal_kind!r}"
            )
        if not self.required_observables:
            raise WindowContractConfigError(
                "required_observables must be a non-empty, spec-owned set of D1 observable "
                "names -- it must never default to an empty tuple that production planning "
                "can silently omit (Opus 5 rejection finding)."
            )
        if not set(self.scalar_finite_observables).issubset(self.required_observables):
            raise WindowContractConfigError(
                f"scalar_finite_observables {self.scalar_finite_observables!r} must be a "
                f"subset of required_observables {self.required_observables!r}"
            )
        if not self.signal_property:
            raise WindowContractConfigError(
                "signal_property must be a non-empty real-state accessor (e.g. 'geometry'); "
                "an anchor window with no real signal to check would have no way to discover "
                "a non-fabricated anchor tick."
            )
        resolved_signal_field = self.signal_field
        if not resolved_signal_field:
            # Mirrors extract_per_process_traces_v2.m's default_anchor_opts()
            # exactly: 'pinchedDiameter' for the ratified Cytokinesis
            # diameter-decrease signal, 'pinched' for the generic legacy
            # boolean-transition default.
            resolved_signal_field = (
                CYTOKINESIS_DIAMETER_OBSERVABLE if self.signal_kind == "diameter_decrease" else DEFAULT_ANCHOR_SIGNAL_FIELD
            )
        object.__setattr__(self, "signal_field", resolved_signal_field)


WindowSpec = FixedWindowSpec | AnchorWindowSpec


def output_dir_for(spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    return event_window_output_dir(spec.seed, karr_native_root=karr_native_root)


def mat_path_for(spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    return event_window_mat_path(spec.process, spec.seed, n_ticks=spec.n_ticks, karr_native_root=karr_native_root)


def temp_output_subdir_for(spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> str:
    """The event-window output subdirectory name a *regeneration* job must
    target instead of the real one. ``extract_per_process_traces_v2.m``
    already ``mkdir``s its output root if missing and skips existence-only
    (never overwrites) -- so a not-yet-validated regeneration can be
    produced into this sibling ``.tmp-regen`` directory with zero changes
    to the .m contract, and the prior on-disk trace (valid or not) is never
    touched until ``finalize_atomic_regeneration`` explicitly validates and
    replaces it (Opus 5 rejection finding: "existing corrupt/stale ...
    files could be [deleted to force regeneration]" -- replaced here with a
    non-destructive atomic-replace-after-validation flow).
    """
    return output_dir_for(spec, karr_native_root=karr_native_root).name + TEMP_REGEN_SUFFIX


def temp_output_path_for(spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    filename = mat_path_for(spec, karr_native_root=karr_native_root).name
    return karr_native_root / temp_output_subdir_for(spec, karr_native_root=karr_native_root) / filename


def sha256_of(path: Path) -> str | None:
    """SHA-256 hex digest of an on-disk file, or ``None`` if it does not
    exist. Used to record a prior (possibly-invalid) file's identity in
    the plan/manifest *before* any future regeneration, so a regenerated
    replacement's provenance can always be traced back to what it
    superseded -- without ever needing to have deleted that prior file to
    know its hash.
    """
    if not path.exists():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def finalize_atomic_regeneration(temp_path: Path, final_path: Path, spec: WindowSpec) -> tuple[bool, str]:
    """Validate a not-yet-trusted regeneration output at ``temp_path``
    against ``spec``'s full contract (the same gauntlet
    ``validate_existing_event_window`` applies to any on-disk trace) and
    ONLY on success atomically replace ``final_path`` with it via
    ``os.replace`` (atomic rename within one filesystem/volume).

    Never invoked by this task -- no MATLAB run occurred, so no temp output
    exists to finalize. Implemented so a *future* regeneration run has a
    safe, non-destructive finalize step to call instead of the removed
    ``apply_invalidations`` pre-emptive delete. On failure, ``temp_path``
    is left on disk for inspection and ``final_path`` (the prior file,
    valid or not) is left completely untouched: corrupt/stale evidence
    must never be destroyed to force regeneration (Opus 5 rejection
    finding), and that guarantee must hold for a *failed* regeneration
    attempt too, not just for the pre-regeneration planning step.
    """
    if not temp_path.exists():
        return False, f"{temp_path}: temp regeneration output does not exist"
    ok, reason = validate_existing_event_window(temp_path, spec)
    if not ok:
        return False, f"temp regeneration output at {temp_path} failed validation, {final_path} left untouched: {reason}"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_path, final_path)
    return True, ""


def build_matlab_command(
    spec: WindowSpec,
    *,
    log_relpath: str | None = None,
    include_addpath: bool = True,
    karr_native_root: Path = KARR_NATIVE_ROOT,
    output_subdir: str | None = None,
) -> str:
    """Build the MATLAB statement(s) for one (process, seed) event-window
    extraction job. Never executed by this module -- this only returns the
    command string a separately-run MATLAB process would use.

    Every string interpolated into the returned command (process name,
    output subdir, log path, signal property/field/kind) is passed through
    ``_matlab_quote`` -- an embedded ``'`` can never terminate the literal
    early and splice arbitrary MATLAB source in (Opus 5 rejection finding:
    "MATLAB quoting ... incomplete"). The wrapped form (when ``log_relpath``
    is given) also creates the log's parent directory if missing and
    propagates a nonzero process exit code on any caught error -- no broad
    catch that prints an error and returns success-shaped (exit 0) output.

    ``output_subdir`` overrides the spec's own event-window output
    directory name; used only by ``plan_event_window_extraction`` to
    redirect a not-yet-validated *regeneration* job into a sibling
    ``.tmp-regen`` directory (see ``temp_output_subdir_for``) so a prior
    on-disk trace is never overwritten/deleted before its replacement is
    validated.
    """
    resolved_output_subdir = (
        output_subdir if output_subdir is not None else output_dir_for(spec, karr_native_root=karr_native_root).name
    )
    proc_arg = f"{{{_matlab_quote(spec.process)}}}"
    output_subdir_lit = _matlab_quote(resolved_output_subdir)

    if isinstance(spec, FixedWindowSpec):
        call = (
            f"extract_per_process_traces_v2({proc_arg}, {output_subdir_lit}, {int(spec.n_ticks)}, "
            f"uint32({int(spec.seed)}), {int(spec.tick_offset)}, 'fixed');"
        )
    elif isinstance(spec, AnchorWindowSpec):
        anchor_opts = (
            "struct("
            f"'max_search_ticks', {int(spec.max_search_ticks)}, "
            f"'signal_kind', {_matlab_quote(spec.signal_kind)}, "
            f"'signal_property', {_matlab_quote(spec.signal_property)}, "
            f"'signal_field', {_matlab_quote(spec.signal_field)})"
        )
        call = (
            f"extract_per_process_traces_v2({proc_arg}, {output_subdir_lit}, {int(spec.n_ticks)}, "
            f"uint32({int(spec.seed)}), [], 'anchor', {anchor_opts});"
        )
    else:  # pragma: no cover - exhaustiveness guard
        raise WindowContractConfigError(f"Unrecognized window spec type: {type(spec)!r}")

    prefix = "addpath('scripts/matlab'); " if include_addpath else ""
    if log_relpath is None:
        return (
            f"{prefix}"
            f"try; {call} catch err; disp(getReport(err, 'extended', 'hyperlinks', 'off')); exit(1); end; "
            f"exit(0);"
        )
    log_lit = _matlab_quote(log_relpath)
    return (
        f"{prefix}"
        f"log_dir_ = fileparts({log_lit}); "
        f"if ~isempty(log_dir_) && ~exist(log_dir_, 'dir'); mkdir(log_dir_); end; "
        f"diary({log_lit}); "
        f"try; {call} catch err; disp(getReport(err, 'extended', 'hyperlinks', 'off')); diary off; exit(1); end; "
        f"diary off; exit(0);"
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
    # SHA-256 of the prior on-disk file at plan time, captured whenever one
    # existed (valid or not) -- so a plan/manifest never loses a file's
    # identity even though we no longer delete it up front (see
    # `finalize_atomic_regeneration`).
    prior_file_sha256: str | None = None


@dataclass
class WindowJob:
    process: str
    seed: int
    window_contract: str
    output_dir: str
    matlab_command: str
    log_path: str
    # Populated only for a "regenerate_invalid" job: the not-yet-validated
    # regeneration output path (a sibling `.tmp-regen` dir, see
    # `temp_output_subdir_for`) and the real path it would replace only
    # after `finalize_atomic_regeneration` validates it. Both None for a
    # "generate_missing" job -- there is no prior file to protect, so
    # `matlab_command` writes directly to the real path.
    temp_output_path: str | None = None
    final_output_path: str | None = None


@dataclass
class WindowExtractionPlan:
    n_ticks: int
    decisions: list[WindowDecision]
    jobs: list[WindowJob]
    generated_at: str
    contract_version: str = "M4"
    # Verbatim echo of every input WindowSpec, JSON-serialized -- so the
    # plan/manifest is fully self-describing provenance (what was
    # requested), not just what was decided (Opus 5 rejection finding:
    # "command/input manifests ... were incomplete").
    input_specs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "n_ticks": self.n_ticks,
            "input_specs": self.input_specs,
            "decisions": [asdict(d) for d in self.decisions],
            "jobs": [asdict(j) for j in self.jobs],
            "generated_at": self.generated_at,
        }


def validate_existing_event_window(path: Path, spec: WindowSpec) -> tuple[bool, str]:
    """Validate-before-skip (never existence-only) for one on-disk trace
    against one requested window spec.

    Re-uses ``window_loader.load_event_window(..., require_stride_contract=True)``
    -- the same refusal gauntlet a real (non-smoke) L2.event gate
    computation applies -- so a trace this function calls valid is, by
    construction, one the loader will also accept; and a trace the loader
    would refuse (missing stride contract, stride != 1, sparse/partial
    grid, incomplete/duplicate onset-completion, or not even an
    event-window trace at all) is never marked ``skip_valid`` here.
    ``required_observables`` and (for an anchor spec) the scalar/finite
    numeric-observable set are always sourced from ``spec`` -- never an
    optional kwarg a caller could omit (Opus 5 rejection finding: "Make
    required observables process/spec-owned"). Returns ``(ok, reason)``;
    ``reason`` is empty iff ``ok`` is True.
    """
    if not path.exists():
        return False, "file does not exist"

    scalar_finite_observables = spec.scalar_finite_observables if isinstance(spec, AnchorWindowSpec) else ()
    try:
        window = load_event_window(
            path,
            required_observables=spec.required_observables,
            require_stride_contract=True,
            require_scalar_finite_observables=scalar_finite_observables,
        )
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

    if (
        isinstance(spec, AnchorWindowSpec)
        and spec.signal_kind == "diameter_decrease"
        and window.onset_tick is None
    ):
        return False, (
            "diameter_decrease anchor window has no metadata.onset_tick (window_anchor/"
            "completion alone is insufficient -- the ratified Cytokinesis timing decision "
            "requires the observed onset tick too)"
        )

    return True, ""


def plan_event_window_extraction(
    specs: list[WindowSpec],
    *,
    karr_native_root: Path = KARR_NATIVE_ROOT,
    validate_existing: bool = True,
) -> WindowExtractionPlan:
    """Build a resumable extraction plan for a list of (process, seed,
    window_contract) specs.

    For every spec, decides ``skip_valid`` / ``generate_missing`` /
    ``regenerate_invalid`` via ``validate_existing_event_window`` (a real
    structural + contract-compliance pass, not an existence-only check)
    when ``validate_existing`` is True. Every job's ``output_dir`` is keyed
    by seed (``per_process_traces_v2_event_s{seed:03d}/``), matching the M4
    contract layout -- EXCEPT a ``regenerate_invalid`` job, whose command
    targets a sibling ``.tmp-regen`` directory (see
    ``temp_output_subdir_for``) instead: a prior on-disk trace is never
    deleted or overwritten in place; only ``finalize_atomic_regeneration``
    may replace it, and only after revalidating the fresh output.
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
            action = "generate_missing"
            reason = None
        else:
            ok, reason = (False, "file does not exist")
            if path.exists():
                ok, reason = validate_existing_event_window(path, spec)
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

        prior_sha256 = sha256_of(path) if action == "regenerate_invalid" else None
        decisions.append(
            WindowDecision(
                process=spec.process,
                seed=spec.seed,
                window_contract=spec.window_contract,
                path=str(path),
                action=action,
                reason=reason if action == "regenerate_invalid" else None,
                prior_file_sha256=prior_sha256,
            )
        )

        log_relpath = event_window_log_relpath(spec.process, spec.seed)
        if action == "regenerate_invalid":
            # A prior file already exists at `path` -- never write there
            # directly. The job targets a `.tmp-regen` sibling directory;
            # only `finalize_atomic_regeneration` may promote it to `path`,
            # and only after it independently revalidates.
            temp_subdir = temp_output_subdir_for(spec, karr_native_root=karr_native_root)
            temp_path = temp_output_path_for(spec, karr_native_root=karr_native_root)
            command = build_matlab_command(spec, log_relpath=log_relpath, output_subdir=temp_subdir)
            job = WindowJob(
                process=spec.process,
                seed=spec.seed,
                window_contract=spec.window_contract,
                output_dir=str(temp_path.parent),
                matlab_command=command,
                log_path=log_relpath,
                temp_output_path=str(temp_path),
                final_output_path=str(path),
            )
        else:
            output_dir = output_dir_for(spec, karr_native_root=karr_native_root)
            command = build_matlab_command(spec, log_relpath=log_relpath)
            job = WindowJob(
                process=spec.process,
                seed=spec.seed,
                window_contract=spec.window_contract,
                output_dir=str(output_dir),
                matlab_command=command,
                log_path=log_relpath,
                final_output_path=str(path),
            )
        jobs.append(job)

    n_ticks = n_ticks_seen.pop() if len(n_ticks_seen) == 1 else -1
    return WindowExtractionPlan(
        n_ticks=n_ticks,
        decisions=decisions,
        jobs=jobs,
        generated_at=datetime.now(UTC).isoformat(),
        input_specs=[asdict(spec) for spec in specs],
    )


def _spec_from_dict(row: dict[str, Any]) -> WindowSpec:
    window_contract = row.get("window_contract")
    required_observables = tuple(row.get("required_observables", ()))
    if window_contract == "fixed":
        return FixedWindowSpec(
            process=row["process"],
            seed=int(row["seed"]),
            tick_offset=int(row["tick_offset"]),
            required_observables=required_observables,
            n_ticks=int(row.get("n_ticks", DEFAULT_N_TICKS)),
        )
    if window_contract == "anchor":
        return AnchorWindowSpec(
            process=row["process"],
            seed=int(row["seed"]),
            required_observables=required_observables,
            n_ticks=int(row.get("n_ticks", DEFAULT_N_TICKS)),
            max_search_ticks=int(row.get("max_search_ticks", DEFAULT_MAX_SEARCH_TICKS)),
            signal_kind=str(row.get("signal_kind", DEFAULT_ANCHOR_SIGNAL_KIND)),
            signal_property=str(row.get("signal_property", DEFAULT_ANCHOR_SIGNAL_PROPERTY)),
            signal_field=row.get("signal_field"),
            scalar_finite_observables=tuple(row.get("scalar_finite_observables", ())),
        )
    raise WindowContractConfigError(
        f"row {row!r}: window_contract must be one of {_VALID_WINDOW_CONTRACTS}, got {window_contract!r}"
    )


def _cmd_plan(args: argparse.Namespace) -> int:
    rows = json.loads(Path(args.specs).read_text(encoding="utf-8"))
    if not rows:
        print("[l2_event.launcher] refusing to write a plan for zero input specs", file=sys.stderr)
        return 1
    specs = [_spec_from_dict(row) for row in rows]
    plan = plan_event_window_extraction(specs, validate_existing=not args.no_validate)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    print(f"[l2_event.launcher] wrote plan with {len(plan.jobs)} jobs to {args.out}")
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan_parser = sub.add_parser(
        "plan",
        help=(
            "Build a resumable event-window extraction plan JSON from a JSON "
            "list of {process, seed, window_contract, required_observables, ...} spec rows. "
            "Never deletes an on-disk trace: a 'regenerate_invalid' job's command targets a "
            "'.tmp-regen' sibling directory (see temp_output_subdir_for), and only "
            "finalize_atomic_regeneration may later replace the real file, after revalidating."
        ),
    )
    plan_parser.add_argument(
        "--specs",
        required=True,
        help=(
            'Path to a JSON file: a list of rows, each either '
            '{"process", "seed", "window_contract": "fixed", "tick_offset", "required_observables", "n_ticks"?} or '
            '{"process", "seed", "window_contract": "anchor", "required_observables", "n_ticks"?, '
            '"max_search_ticks"?, "signal_kind"?, "signal_property"?, "signal_field"?, '
            '"scalar_finite_observables"?}. "required_observables" is mandatory and must be '
            "non-empty for every row (production planning must never omit it)."
        ),
    )
    plan_parser.add_argument("--no-validate", action="store_true", help="Existence-only skip (debug only).")
    plan_parser.add_argument("--out", required=True)
    plan_parser.set_defaults(func=_cmd_plan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

