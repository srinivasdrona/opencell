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
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[2]
# Self-contained sys.path bootstrap (mirrors scripts/l22_extraction/launcher.py):
# makes `scripts.l2_event.*` absolute imports work whether this module is run
# directly as a script or imported by pytest from tests/scripts/.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.window_loader import (  # noqa: E402
    EventWindowRefused,
    _decode_char_metadata,
    _read_optional_scalar,
    load_event_window,
)

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
# Chromosome.segregated (data/m1_sources/WholeCell/src/+edu/+stanford/
# +covert/+cell/+sim/+state/Chromosome.m) -- the exact scalar boolean
# Cytokinesis.evolveState() itself reads to gate contraction (Cytokinesis.m:
# `if ~this.chromosome.segregated; return; end`). This is the ONLY
# chromosome-state field Cytokinesis ever reads; the .m extractor now
# flattens just this scalar (see merge_event_observables) instead of
# snapshotting the full sparse Chromosome state object on every searched
# anchor tick (performance/sufficiency patch, post-Turn-3 -- see
# exclude_chromosome_object_for_diameter_anchor in the .m file).
CYTOKINESIS_CHROMOSOME_OBSERVABLE = "chromosome_segregated"
CYTOKINESIS_SCALAR_FINITE_OBSERVABLES = (
    CYTOKINESIS_DIAMETER_OBSERVABLE,
    *CYTOKINESIS_FTSZRING_OBSERVABLES,
    CYTOKINESIS_CHROMOSOME_OBSERVABLE,
)

# Schema/version tag for merge_event_observables()'s flattened numeric
# event-observable projection (extract_per_process_traces_v2.m writes this
# literal value into metadata/event_observable_projection_version for every
# 'anchor' trace). Bump this, and the corresponding literal in the .m file,
# only if the projection's field set/semantics ever changes incompatibly --
# validate_existing_event_window cross-checks it so an on-disk trace from a
# stale projection schema can never silently skip-valid.
#
# 2 (this patch): signal_kind='diameter_decrease' traces gained
# 'chromosome_segregated' and no longer carry the full 'chromosome' object;
# a v1 on-disk trace (either signal_kind) must refuse/regenerate, never
# silently skip-valid against a v2 spec.
EVENT_OBSERVABLE_PROJECTION_VERSION = 2

DEFAULT_MATLAB_ROOT = Path(
    os.environ.get(
        "OPENCELL_MATLAB_ROOT",
        r"E:\MATLAB" if os.name == "nt" else "/mnt/e/MATLAB",
    )
)
GENUINE_MNRND_KIND = "statistics_toolbox"
STATISTICS_RNG_FUNCTIONS = ("binornd", "mnrnd", "poissrnd", "random", "randsample")
STATISTICS_TOOLBOX_FUNCTIONS_RELATIVE_DIR = Path("toolbox") / "stats" / "stats"
GENUINE_MNRND_RELATIVE_PATH = STATISTICS_TOOLBOX_FUNCTIONS_RELATIVE_DIR / "mnrnd.m"
STATISTICS_TOOLBOX_CONTENTS_RELATIVE_PATH = Path("toolbox") / "stats" / "stats" / "Contents.m"
MATLAB_VERSION_INFO_RELATIVE_PATH = Path("VersionInfo.xml")


def lf_normalized_sha256_hex(path: Path) -> str:
    """SHA-256 (lowercase hex) of ``path`` after stripping CR bytes so the
    identity is stable across CRLF/LF checkouts."""
    raw = path.read_bytes().replace(b"\r", b"")
    return hashlib.sha256(raw).hexdigest()


def genuine_mnrnd_path(*, matlab_root: Path | None = None) -> Path:
    root = DEFAULT_MATLAB_ROOT if matlab_root is None else Path(matlab_root)
    return root / GENUINE_MNRND_RELATIVE_PATH


def genuine_statistics_rng_path(name: str, *, matlab_root: Path | None = None) -> Path:
    if name not in STATISTICS_RNG_FUNCTIONS:
        raise ValueError(f"unsupported Statistics Toolbox RNG function: {name!r}")
    root = DEFAULT_MATLAB_ROOT if matlab_root is None else Path(matlab_root)
    return root / STATISTICS_TOOLBOX_FUNCTIONS_RELATIVE_DIR / f"{name}.m"


def _matlab_release(*, matlab_root: Path | None = None) -> str:
    root = DEFAULT_MATLAB_ROOT if matlab_root is None else Path(matlab_root)
    version_info_path = root / MATLAB_VERSION_INFO_RELATIVE_PATH
    if not version_info_path.is_file():
        raise FileNotFoundError(f"MATLAB VersionInfo.xml not found at {version_info_path}")
    tree = ElementTree.parse(version_info_path)
    release = tree.findtext("./release")
    if not release:
        raise ValueError(f"MATLAB VersionInfo.xml at {version_info_path} has no <release> entry")
    return release.strip()


def _statistics_toolbox_version(*, matlab_root: Path | None = None) -> str:
    root = DEFAULT_MATLAB_ROOT if matlab_root is None else Path(matlab_root)
    contents_path = root / STATISTICS_TOOLBOX_CONTENTS_RELATIVE_PATH
    if not contents_path.is_file():
        raise FileNotFoundError(f"Statistics Toolbox Contents.m not found at {contents_path}")
    header = contents_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^% Version (?P<version>[0-9.]+) \((?P<release>R[0-9]{4}[ab])\)", header, re.MULTILINE)
    if match is None:
        raise ValueError(f"could not parse Statistics Toolbox version from {contents_path}")
    return match.group("version")


def current_genuine_statistics_rng_provider(*, matlab_root: Path | None = None) -> dict[str, Any]:
    """Current local MathWorks identity for every repo-shadowed RNG helper."""
    functions: list[dict[str, str]] = []
    for name in STATISTICS_RNG_FUNCTIONS:
        provider_path = genuine_statistics_rng_path(name, matlab_root=matlab_root)
        if not provider_path.is_file():
            raise FileNotFoundError(
                f"genuine Statistics Toolbox {name}.m not found at {provider_path}; "
                "repo-shim trajectories are non-authoritative"
            )
        functions.append(
            {
                "name": name,
                "provider_path_relative_to_matlabroot": (
                    STATISTICS_TOOLBOX_FUNCTIONS_RELATIVE_DIR / f"{name}.m"
                ).as_posix(),
                "sha256_lf_normalized": lf_normalized_sha256_hex(provider_path),
            }
        )
    return {
        "kind": GENUINE_MNRND_KIND,
        "matlab_release": _matlab_release(matlab_root=matlab_root),
        "toolbox_version": _statistics_toolbox_version(matlab_root=matlab_root),
        "functions": functions,
    }


def current_genuine_mnrnd_provider(*, matlab_root: Path | None = None) -> dict[str, str]:
    """Backward-compatible mnrnd view of the complete RNG-provider identity."""
    provider = current_genuine_statistics_rng_provider(matlab_root=matlab_root)
    mnrnd = next(row for row in provider["functions"] if row["name"] == "mnrnd")
    return {
        "kind": provider["kind"],
        "matlab_release": provider["matlab_release"],
        "toolbox_version": provider["toolbox_version"],
        "provider_path_relative_to_matlabroot": mnrnd["provider_path_relative_to_matlabroot"],
        "sha256_lf_normalized": mnrnd["sha256_lf_normalized"],
    }


# Suffix for a not-yet-validated regeneration's output directory (see
# `temp_output_subdir_for`/`finalize_atomic_regeneration`). Never the real
# per-process-trace directory a `skip_valid` lookup or the standard mid-cycle
# extractor would resolve to. Always paired with a unique per-job token (see
# `allocate_unique_temp_output_path`) -- never reused bare, so two
# regeneration attempts (even for the same spec) can never collide.
TEMP_REGEN_SUFFIX = ".tmp-regen"

WindowContract = Literal["fixed", "anchor"]
_VALID_WINDOW_CONTRACTS = ("fixed", "anchor")

# Safe canonical-token restriction for every spec identifier string that
# build_matlab_command interpolates into a MATLAB command (process name,
# signal_property, signal_field). This is enforced at spec-construction
# time (__post_init__), independent of/in addition to `_matlab_quote`:
# `_matlab_quote` only secures the MATLAB single-quoted string-literal
# context itself (doubling an embedded `'`, per MATLAB's own escaping
# convention -- see test_build_matlab_command_quotes_embedded_single_quote_
# in_process_name), never a not-yet-existing future shell boundary (e.g. a
# job runner invoking `wsl bash -c "matlab -batch '...'"`). A single quote
# is therefore NOT rejected here -- it is a legitimate character that
# `_matlab_quote` already escapes correctly. What IS refused here, before
# any command string is ever built, is the specific set of characters that
# would let a value break out of *that* future shell boundary regardless
# of MATLAB-level quoting: an unescaped double quote, backtick, `$`
# (shell/command substitution), `;` (command separator), and any newline/
# carriage-return (command injection via embedded newline).
_UNSAFE_IDENTIFIER_CHARS_RE = re.compile(r'["`$;\n\r]')


def _require_safe_identifier(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value or _UNSAFE_IDENTIFIER_CHARS_RE.search(value):
        raise WindowContractConfigError(
            f"{field_name}={value!r} contains a character that is unsafe at the eventual "
            "matlab-batch shell boundary a future job runner will pass this value through "
            "(double quote, backtick, $, ;, or a newline/carriage-return) -- _matlab_quote "
            "alone secures the MATLAB string-literal context, not that shell boundary, so "
            "this is refused here at config time instead. A plain embedded single quote is "
            "not rejected: _matlab_quote already escapes it correctly (doubling, MATLAB's "
            "own convention)."
        )


def _matlab_quote(value: str) -> str:
    """Quote ``value`` as a single-quoted MATLAB char-vector literal, safe
    against embedded single quotes (Opus 5 rejection finding: "MATLAB
    quoting ... incomplete"). MATLAB's own escaping convention is doubling
    the embedded quote (``'it''s'``); this mirrors that exactly. An
    embedded newline/carriage-return is rejected outright -- no legitimate
    process name, signal property/field, or output-subdir component can
    contain one, so silently accepting it would only be a MATLAB-source-
    injection vector via a crafted spec field.

    This function secures only the MATLAB single-quoted string-literal
    context it targets -- it does NOT, by itself, secure a future shell
    boundary this command string might be passed through (e.g. a job
    runner invoking ``wsl bash -c "matlab -batch '...'"``); no such shell
    invocation exists in this module. The actual defense for that future
    boundary is restricting every interpolated identifier field (process
    name, signal_property, signal_field) to a safe canonical token at
    spec-construction time -- see ``_require_safe_identifier`` and its
    call sites in ``FixedWindowSpec``/``AnchorWindowSpec.__post_init__``.
    """
    if "\n" in value or "\r" in value:
        raise WindowContractConfigError(
            f"value {value!r} contains a newline/carriage-return; not a safe MATLAB string literal"
        )
    return "'" + value.replace("'", "''") + "'"


def _matlab_literal(value: Any) -> str:
    """Render a small Python scalar/dict tree as a MATLAB literal."""
    if isinstance(value, dict):
        if not value:
            return "struct()"
        parts: list[str] = []
        for key, inner in value.items():
            if not isinstance(key, str) or not key:
                raise WindowContractConfigError(
                    f"MATLAB struct literal keys must be non-empty strings, got {key!r}"
                )
            parts.append(f"{_matlab_quote(key)}, {_matlab_literal(inner)}")
        return "struct(" + ", ".join(parts) + ")"
    if isinstance(value, str):
        return _matlab_quote(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "[]"
    if isinstance(value, (int, float)):
        return repr(value)
    raise WindowContractConfigError(
        f"Unsupported MATLAB literal payload {value!r} ({type(value).__name__}) in matlab_extraction_opts"
    )


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
    extraction_identity_json: str | None = None
    matlab_extraction_opts: dict[str, Any] = field(default_factory=dict)
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
        _require_safe_identifier("process", self.process)
        if self.extraction_identity_json is not None and not isinstance(self.extraction_identity_json, str):
            raise WindowContractConfigError(
                "extraction_identity_json must be a string when provided "
                f"(got {type(self.extraction_identity_json).__name__})"
            )
        if not isinstance(self.matlab_extraction_opts, dict):
            raise WindowContractConfigError(
                f"matlab_extraction_opts must be a dict, got {type(self.matlab_extraction_opts).__name__}"
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
        _require_safe_identifier("process", self.process)
        _require_safe_identifier("signal_property", self.signal_property)
        _require_safe_identifier("signal_field", resolved_signal_field)


WindowSpec = FixedWindowSpec | AnchorWindowSpec


def output_dir_for(spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    return event_window_output_dir(spec.seed, karr_native_root=karr_native_root)


def mat_path_for(spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    return event_window_mat_path(spec.process, spec.seed, n_ticks=spec.n_ticks, karr_native_root=karr_native_root)


def temp_output_subdir_for(spec: WindowSpec, token: str, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> str:
    """The event-window output subdirectory name a *regeneration* job must
    target instead of the real one. ``extract_per_process_traces_v2.m``
    already ``mkdir``s its output root if missing and skips existence-only
    (never overwrites) -- so a not-yet-validated regeneration can be
    produced into this sibling ``.tmp-regen-<token>`` directory with zero
    changes to the .m contract, and the prior on-disk trace (valid or not)
    is never touched until ``finalize_atomic_regeneration`` explicitly
    validates and replaces it (Opus 5 rejection finding: "existing
    corrupt/stale ... files could be [deleted to force regeneration]" --
    replaced here with a non-destructive atomic-replace-after-validation
    flow). ``token`` (see ``allocate_unique_temp_output_path``) makes each
    regeneration attempt's temp directory unique -- never a bare, reusable
    ``.tmp-regen`` name two jobs (or a stale leftover from a prior run)
    could collide on.
    """
    return f"{output_dir_for(spec, karr_native_root=karr_native_root).name}{TEMP_REGEN_SUFFIX}-{token}"


def extractor_output_subdir_for(path: Path, *, repo_karr_native_root: Path | None = None) -> str:
    """Return the ``output_subdir`` string `extract_per_process_traces_v2.m`
    must receive to write into ``path`` under the repo-owned
    ``data/m1_sources/karr_native`` tree.

    The MATLAB extractor always resolves its output root as
    ``repo_root/data/m1_sources/karr_native/<output_subdir>``. When a caller
    plans traces under a nested descendant such as
    ``.../karr_native/dnadamage_stimulus_cohort/uvb_mechanism/...``, passing
    only ``path.name`` would silently drop the condition-root prefix and
    write into the default top-level event-window directory instead. This
    helper preserves that nested identity by emitting the repo-relative
    subpath when possible.

    If ``path`` is not under ``repo_karr_native_root`` (for example, a unit
    test using a scratch ``tmp_path`` tree disconnected from the repo),
    fall back to the leaf directory name. That fallback preserves existing
    MATLAB-free test behavior; such a command is not executed in those
    scratch-path tests.
    """
    if repo_karr_native_root is None:
        repo_karr_native_root = KARR_NATIVE_ROOT
    try:
        return path.relative_to(repo_karr_native_root).as_posix()
    except ValueError:
        return path.name


def temp_output_path_for(spec: WindowSpec, token: str, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    filename = mat_path_for(spec, karr_native_root=karr_native_root).name
    return karr_native_root / temp_output_subdir_for(spec, token, karr_native_root=karr_native_root) / filename


def temp_regen_token() -> str:
    """A fresh per-job token for a ``.tmp-regen-<token>`` directory name. A
    random UUID4 hex fragment, not a counter/timestamp, so two
    independently planned jobs (even for the identical spec, e.g. a
    retried plan) can never collide on the same temp directory name."""
    return uuid.uuid4().hex[:16]


def allocate_unique_temp_output_path(
    spec: WindowSpec, *, karr_native_root: Path = KARR_NATIVE_ROOT, max_attempts: int = 8
) -> tuple[str, Path]:
    """Generate a fresh per-job token and confirm its ``.tmp-regen-<token>``
    output directory does not already exist on disk before returning it --
    so two plans, or a stale leftover directory from a prior/abandoned run,
    can never collide on the same temp directory (Opus 5 rejection
    finding: the prior bare ``.tmp-regen`` name was reusable and nothing
    checked the temp path was absent before a job started). Returns
    ``(token, temp_path)``. Never invoked against a real MATLAB run in this
    task -- no extraction/regeneration is executed here.
    """
    for _ in range(max_attempts):
        token = temp_regen_token()
        temp_path = temp_output_path_for(spec, token, karr_native_root=karr_native_root)
        if not temp_path.parent.exists():
            return token, temp_path
    raise RuntimeError(
        f"could not allocate a unique .tmp-regen directory for {spec.process}/seed {spec.seed} "
        f"after {max_attempts} attempts -- inspect {karr_native_root} for stale temp directories "
        "(see list_stale_regeneration_temp_dirs)"
    )


def list_stale_regeneration_temp_dirs(*, karr_native_root: Path = KARR_NATIVE_ROOT) -> list[Path]:
    """Read-only report of leftover ``.tmp-regen-<token>`` directories under
    ``karr_native_root`` (e.g. from an interrupted or abandoned
    regeneration run). Never deletes anything: this is purely a listing
    for an operator/future targeted-cleanup tool to inspect and decide on.
    The real per-process trace files never live inside a ``.tmp-regen-*``
    directory, so even an incautious future cleanup acting only on the
    paths returned here could never touch final evidence.
    """
    if not karr_native_root.exists():
        return []
    return sorted(p for p in karr_native_root.glob(f"*{TEMP_REGEN_SUFFIX}-*") if p.is_dir())


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


def finalize_atomic_regeneration(
    temp_path: Path,
    final_path: Path,
    spec: WindowSpec,
    *,
    expected_token: str,
    prior_final_sha256: str | None,
) -> tuple[bool, str]:
    """Validate a not-yet-trusted regeneration output at ``temp_path``
    against ``spec``'s full contract (the same gauntlet
    ``validate_existing_event_window`` applies to any on-disk trace) and
    ONLY on success atomically replace ``final_path`` with it via
    ``os.replace`` (atomic rename within one filesystem/volume).

    Binds finalize to the exact job it belongs to (Opus 5 rejection
    finding: "bind finalize to the exact spec + token + pre-run
    manifest"):

    * ``expected_token`` -- the unique token
      ``allocate_unique_temp_output_path`` minted for THIS job; ``temp_path``'s
      parent directory name must embed it, or finalize refuses (guards
      against operating on a stale/foreign ``.tmp-regen-*`` directory left
      over from a different job).
    * ``prior_final_sha256`` -- the SHA-256 of ``final_path`` captured at
      plan time (``WindowDecision.prior_file_sha256``), i.e. the pre-run
      manifest. If ``final_path``'s CURRENT hash no longer matches, some
      other writer changed it since the plan was made and finalize refuses
      rather than clobber an identity it never validated.
    * ``spec`` -- the full ``validate_existing_event_window`` gauntlet
      (process/seed/n_ticks/window kind/stride/bounds/anchor-identity),
      applied to ``temp_path`` before it may ever replace ``final_path``.

    Never invoked by this task -- no MATLAB run occurred, so no temp output
    exists to finalize. Implemented so a *future* regeneration run has a
    safe, non-destructive finalize step to call instead of the removed
    ``apply_invalidations`` pre-emptive delete. On ANY failure (token
    mismatch, missing temp, stale/changed final, or a failed validation),
    ``temp_path`` is left on disk for inspection and ``final_path`` (the
    prior file, valid or not) is left byte-identical: corrupt/stale
    evidence must never be destroyed to force regeneration (Opus 5
    rejection finding), and that guarantee must hold for a *failed*
    regeneration attempt too, not just for the pre-regeneration planning
    step. A stale/foreign temp directory must never be promoted.
    """
    if expected_token not in temp_path.parent.name:
        return False, (
            f"{temp_path}: temp directory name does not embed the expected job token "
            f"{expected_token!r} -- refusing to finalize a mismatched/stale temp output "
            f"({final_path} left untouched)"
        )
    if not temp_path.exists():
        return False, f"{temp_path}: temp regeneration output does not exist"
    current_final_sha256 = sha256_of(final_path)
    if current_final_sha256 != prior_final_sha256:
        return False, (
            f"{final_path}: current sha256 ({current_final_sha256!r}) does not match the "
            f"pre-run manifest sha256 ({prior_final_sha256!r}) captured at plan time -- refusing "
            f"to finalize against a file that changed since the plan was made ({final_path} left "
            "untouched)"
        )
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
    "MATLAB quoting ... incomplete"). When ``include_addpath`` is left at
    its default True, the command both adds ``scripts/matlab`` (so the
    extractor itself is callable) and immediately re-promotes the genuine
    Statistics Toolbox provider directory to the front of the MATLAB path,
    so ``mnrnd`` does not silently resolve to the repo shim before
    ``karr_bootstrap()`` gets its own fail-closed check. The wrapped form
    (when ``log_relpath`` is given) also creates the log's parent
    directory if missing and propagates a nonzero process exit code on
    any caught error -- no broad catch that prints an error and returns
    success-shaped (exit 0) output.

    ``output_subdir`` overrides the spec's own event-window output
    directory name; used only by ``plan_event_window_extraction`` to
    redirect a not-yet-validated *regeneration* job into a sibling
    ``.tmp-regen`` directory (see ``temp_output_subdir_for``) so a prior
    on-disk trace is never overwritten/deleted before its replacement is
    validated.
    """
    resolved_output_subdir = (
        output_subdir
        if output_subdir is not None
        else extractor_output_subdir_for(output_dir_for(spec, karr_native_root=karr_native_root))
    )
    proc_arg = f"{{{_matlab_quote(spec.process)}}}"
    output_subdir_lit = _matlab_quote(resolved_output_subdir)

    if isinstance(spec, FixedWindowSpec):
        if spec.matlab_extraction_opts:
            extraction_opts = _matlab_literal(spec.matlab_extraction_opts)
            call = (
                f"extract_per_process_traces_v2({proc_arg}, {output_subdir_lit}, {int(spec.n_ticks)}, "
                f"uint32({int(spec.seed)}), {int(spec.tick_offset)}, 'fixed', [], {extraction_opts});"
            )
        else:
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

    prefix = (
        "addpath('scripts/matlab'); "
        "addpath(fullfile(matlabroot, 'toolbox', 'stats', 'stats'), '-begin'); "
        if include_addpath
        else ""
    )
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
    metadata carries: ``'fixed'``, ``'anchor'``, ``'both'``, ``'neither'``,
    or ``'corrupt'``. Used only to detect a window-kind MISMATCH between
    what is on disk and what was requested (rule-6/rule-8 guard against
    "duplicate extraction" silently being accepted as satisfying a
    different request) -- never to decide stride/completeness, which stays
    the sole authority of ``window_loader``.

    ``'corrupt'`` is a distinct classification from ``'neither'``: a
    zero-byte, garbage, or truncated file cannot even be opened/parsed as
    HDF5 at all (``OSError``/``ValueError``/``KeyError``), which is a
    different failure than a genuinely openable file that simply lacks a
    ``tick_end``/``window_anchor`` key. Never raises -- a corrupt file must
    be classified, never crash the caller (Opus 5 rejection finding).
    """
    import h5py

    try:
        with h5py.File(path, "r") as handle:
            metadata = handle.get("metadata")
            if metadata is None:
                return "neither"
            has_end = "tick_end" in metadata
            has_anchor = "window_anchor" in metadata
    except (OSError, ValueError, KeyError):
        return "corrupt"
    if has_end and has_anchor:
        return "both"
    if has_end:
        return "fixed"
    if has_anchor:
        return "anchor"
    return "neither"


def _read_mnrnd_provider_metadata(path: Path) -> dict[str, Any]:
    """Read the genuine-mnrnd provider identity metadata persisted for
    every 'fixed' or 'anchor' trace.

    Any key absent from ``metadata`` maps to ``None`` (never raises for a
    missing key, matching a pre-provider-binding trace written before this
    check existed); an unreadable/corrupt file DOES raise
    ``OSError``/``ValueError``/``KeyError`` -- callers must catch those
    explicitly (see ``validate_existing_event_window``), consistent with
    ``_window_boundary_kind``'s and ``_read_anchor_signal_metadata``'s
    corrupt-file handling.
    """
    import h5py

    result: dict[str, Any] = {
        "mnrnd_provider_kind": None,
        "mnrnd_provider_matlab_release": None,
        "mnrnd_provider_toolbox_version": None,
        "mnrnd_provider_path_relative_to_matlabroot": None,
        "mnrnd_provider_sha256": None,
        "statistics_rng_provider_identity_json": None,
    }
    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if metadata is None:
            return result
        for key in (
            "mnrnd_provider_kind",
            "mnrnd_provider_matlab_release",
            "mnrnd_provider_toolbox_version",
            "mnrnd_provider_path_relative_to_matlabroot",
            "mnrnd_provider_sha256",
            "statistics_rng_provider_identity_json",
        ):
            if key in metadata:
                result[key] = _decode_char_metadata(metadata[key][()])
    return result


def _read_optional_text_metadata(path: Path, key: str) -> str | None:
    """Read one optional MATLAB char-array metadata field from ``path``."""
    import h5py

    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if metadata is None or key not in metadata:
            return None
        return _decode_char_metadata(metadata[key][()])


def _read_anchor_signal_metadata(path: Path) -> dict[str, Any]:
    """Read the anchor-config identity-binding metadata
    (``signal_kind``/``signal_property``/``signal_field``/
    ``max_search_ticks``/``event_observable_projection_version``)
    ``extract_per_process_traces_v2.m`` persists for ``window_contract=
    'anchor'`` traces, so ``validate_existing_event_window`` can
    cross-check that an on-disk trace was actually produced for the
    requested signal configuration -- never trusting window-kind/tick
    agreement alone (a trace generated for a DIFFERENT signal_property,
    e.g., must never validate/skip-valid against a spec requesting a
    different one). Any key absent from ``metadata`` maps to ``None``
    (never raises for a missing key); an unreadable/corrupt file DOES
    raise ``OSError``/``ValueError``/``KeyError`` -- callers must catch
    those explicitly (see ``validate_existing_event_window``), consistent
    with ``_window_boundary_kind``'s corrupt-file handling.
    """
    import h5py

    result: dict[str, Any] = {
        "signal_kind": None,
        "signal_property": None,
        "signal_field": None,
        "max_search_ticks": None,
        "event_observable_projection_version": None,
    }
    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if metadata is None:
            return result
        for str_key in ("signal_kind", "signal_property", "signal_field"):
            if str_key in metadata:
                result[str_key] = _decode_char_metadata(metadata[str_key][()])
        for int_key in ("max_search_ticks", "event_observable_projection_version"):
            if int_key in metadata:
                value, problem = _read_optional_scalar(metadata, int_key)
                if problem is None and value is not None:
                    result[int_key] = int(value)
    return result


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
    # regeneration output path (a sibling `.tmp-regen-<token>` dir, see
    # `temp_output_subdir_for`) and the real path it would replace only
    # after `finalize_atomic_regeneration` validates it. Both None for a
    # "generate_missing" job -- there is no prior file to protect, so
    # `matlab_command` writes directly to the real path.
    temp_output_path: str | None = None
    final_output_path: str | None = None
    # Populated only for a "regenerate_invalid" job: the unique per-job
    # token `allocate_unique_temp_output_path` minted for `temp_output_path`
    # (see also `WindowDecision.prior_file_sha256`, this job's pre-run
    # manifest hash) -- a future runner must pass BOTH back into
    # `finalize_atomic_regeneration` (`expected_token`, `prior_final_sha256`)
    # so finalize can never be tricked into promoting a stale/foreign temp.
    regen_token: str | None = None


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
    grid, incomplete onset/completion, or not even an event-window trace
    at all) is never marked ``skip_valid`` here. ``required_observables``
    and (for an anchor spec) the scalar/finite numeric-observable set are
    always sourced from ``spec`` -- never an optional kwarg a caller could
    omit (Opus 5 rejection finding: "Make required observables
    process/spec-owned").

    Also binds identity beyond mere structural compliance (Opus 5
    rejection finding): a ``FixedWindowSpec``'s ``tick_offset``/
    ``tick_start``/``tick_end`` must match the corrected absolute-tick
    formula (``tick_start == tick_offset + 1``, ``tick_end == tick_offset +
    n_ticks``) exactly, and an ``AnchorWindowSpec``'s
    ``signal_kind``/``signal_property``/``signal_field``/
    ``max_search_ticks``/observable-projection-schema-version must match
    the on-disk trace's own persisted anchor-config metadata -- so a trace
    produced for a DIFFERENT fixed-offset or anchor-signal request can
    never ``skip_valid`` against this one. Independently of window kind,
    the trace must also carry genuine-provider metadata whose kind,
    MATLAB release, Statistics Toolbox version, provider path relative to
    ``matlabroot``, and LF-normalized provider SHA-256 all match the
    current local MathWorks install exactly. Legacy shim-bound or
    provider-metadata-missing traces are therefore explicitly
    non-authoritative and must regenerate_invalid, never silently
    ``skip_valid``.

    Never crashes on a corrupt/malformed file (Opus 5 rejection finding):
    every path that opens/parses the file (the loader call and the two
    on-disk-metadata helpers below) is guarded against ``OSError``/
    ``ValueError``/``KeyError``, which are converted into an ordinary
    ``(False, reason)`` result -- ``plan_event_window_extraction`` then
    resolves this to ``regenerate_invalid``, never a crash or a silent
    ``skip_valid``. Returns ``(ok, reason)``; ``reason`` is empty iff
    ``ok`` is True.
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
    except (OSError, ValueError, KeyError) as exc:
        return False, (
            f"{path}: failed to open/parse as an event-window trace "
            f"({type(exc).__name__}: {exc}) -- treated as a corrupt/invalid file "
            "(regenerate_invalid), never a crash or silent skip"
        )

    if window.process_name != spec.process:
        return False, f"metadata.process_name={window.process_name!r} != expected {spec.process!r}"
    if window.seed != int(spec.seed):
        return False, f"metadata.rng_seed={window.seed!r} != expected {spec.seed!r}"
    if window.n_ticks != int(spec.n_ticks):
        return False, f"metadata.n_ticks={window.n_ticks!r} != expected {spec.n_ticks!r}"

    try:
        on_disk_kind = _window_boundary_kind(path)
    except (OSError, ValueError, KeyError) as exc:
        return False, f"{path}: failed to inspect on-disk window-kind metadata ({type(exc).__name__}: {exc})"
    if on_disk_kind == "corrupt":
        return False, f"{path}: could not inspect on-disk window-kind metadata (corrupt/unreadable file)"
    if on_disk_kind != spec.window_contract:
        return False, (
            f"on-disk window kind={on_disk_kind!r} != requested window_contract={spec.window_contract!r} "
            "(a trace produced under a different window_contract must never be silently reused)"
        )

    expected_extraction_identity = getattr(spec, "extraction_identity_json", None)
    if expected_extraction_identity is not None:
        try:
            on_disk_extraction_identity = _read_optional_text_metadata(path, "extraction_identity_json")
        except (OSError, ValueError, KeyError) as exc:
            return False, (
                f"{path}: failed to inspect extraction_identity_json metadata "
                f"({type(exc).__name__}: {exc})"
            )
        if on_disk_extraction_identity != expected_extraction_identity:
            return False, (
                f"metadata.extraction_identity_json={on_disk_extraction_identity!r} != expected "
                f"{expected_extraction_identity!r} (stimulus-conditioned traces must never be silently "
                "reused across different extractor identity payloads)"
            )

    # Genuine-provider identity binding: applies to BOTH 'fixed' and
    # 'anchor' specs. Event-window traces are authoritative only if they
    # were produced under the current local Statistics Toolbox provider,
    # not the repo shim.
    try:
        mnrnd_meta = _read_mnrnd_provider_metadata(path)
    except (OSError, ValueError, KeyError) as exc:
        return False, (
            f"{path}: failed to inspect genuine mnrnd provider identity-binding metadata "
            f"({type(exc).__name__}: {exc})"
        )
    try:
        expected_provider = current_genuine_mnrnd_provider()
    except (OSError, ValueError, KeyError) as exc:
        return False, (
            f"current local genuine Statistics Toolbox mnrnd provider is unavailable or unreadable "
            f"({type(exc).__name__}: {exc}) -- event-window traces cannot be treated as authoritative "
            "without verifying against the live local provider"
        )
    if mnrnd_meta["mnrnd_provider_kind"] != expected_provider["kind"]:
        return False, (
            f"metadata.mnrnd_provider_kind={mnrnd_meta['mnrnd_provider_kind']!r} != expected "
            f"{expected_provider['kind']!r} -- legacy shim-bound or non-genuine-provider traces are "
            "explicitly non-authoritative"
        )
    if mnrnd_meta["mnrnd_provider_matlab_release"] != expected_provider["matlab_release"]:
        return False, (
            f"metadata.mnrnd_provider_matlab_release={mnrnd_meta['mnrnd_provider_matlab_release']!r} != "
            f"current MATLAB release {expected_provider['matlab_release']!r}"
        )
    if mnrnd_meta["mnrnd_provider_toolbox_version"] != expected_provider["toolbox_version"]:
        return False, (
            f"metadata.mnrnd_provider_toolbox_version={mnrnd_meta['mnrnd_provider_toolbox_version']!r} != "
            f"current Statistics Toolbox version {expected_provider['toolbox_version']!r}"
        )
    if (
        mnrnd_meta["mnrnd_provider_path_relative_to_matlabroot"]
        != expected_provider["provider_path_relative_to_matlabroot"]
    ):
        return False, (
            "metadata.mnrnd_provider_path_relative_to_matlabroot="
            f"{mnrnd_meta['mnrnd_provider_path_relative_to_matlabroot']!r} != current provider path "
            f"{expected_provider['provider_path_relative_to_matlabroot']!r}"
        )
    if mnrnd_meta["mnrnd_provider_sha256"] != expected_provider["sha256_lf_normalized"]:
        return False, (
            f"metadata.mnrnd_provider_sha256={mnrnd_meta['mnrnd_provider_sha256']!r} != current "
            f"provider sha256 {expected_provider['sha256_lf_normalized']!r}"
        )
    raw_rng_identity = mnrnd_meta["statistics_rng_provider_identity_json"]
    if raw_rng_identity is None:
        return False, (
            "metadata.statistics_rng_provider_identity_json is missing -- the trace does not bind "
            "all repo-shadowed Statistics Toolbox RNG providers"
        )
    try:
        trace_rng_identity = json.loads(raw_rng_identity)
    except (TypeError, json.JSONDecodeError) as exc:
        return False, f"metadata.statistics_rng_provider_identity_json is invalid JSON ({exc})"
    try:
        expected_rng_identity = current_genuine_statistics_rng_provider()
    except (OSError, ValueError, KeyError) as exc:
        return False, (
            "current local genuine Statistics Toolbox RNG providers are unavailable or unreadable "
            f"({type(exc).__name__}: {exc})"
        )
    if trace_rng_identity != expected_rng_identity:
        return False, (
            "metadata.statistics_rng_provider_identity_json does not match the current local "
            "binornd/mnrnd/poissrnd/random/randsample provider identities"
        )

    if isinstance(spec, FixedWindowSpec):
        expected_tick_start = int(spec.tick_offset) + 1
        expected_tick_end = int(spec.tick_offset) + int(spec.n_ticks)
        if int(window.tick_offset) != int(spec.tick_offset):
            return False, (
                f"metadata.tick_offset={window.tick_offset!r} != expected burn-in tick count "
                f"{spec.tick_offset!r}"
            )
        if window.tick_start != expected_tick_start:
            return False, (
                f"metadata.tick_start={window.tick_start!r} != expected {expected_tick_start!r} "
                "(tick_offset + 1, absolute 1-based coordinate)"
            )
        if window.tick_end != expected_tick_end:
            return False, (
                f"metadata.tick_end={window.tick_end!r} != expected {expected_tick_end!r} "
                "(tick_offset + n_ticks)"
            )

    if isinstance(spec, AnchorWindowSpec):
        try:
            anchor_meta = _read_anchor_signal_metadata(path)
        except (OSError, ValueError, KeyError) as exc:
            return False, f"{path}: failed to inspect anchor signal metadata ({type(exc).__name__}: {exc})"

        if anchor_meta["signal_kind"] != spec.signal_kind:
            return False, (
                f"metadata.signal_kind={anchor_meta['signal_kind']!r} != expected {spec.signal_kind!r} "
                "(trace was produced for a different anchor signal request)"
            )
        if anchor_meta["signal_property"] != spec.signal_property:
            return False, (
                f"metadata.signal_property={anchor_meta['signal_property']!r} != expected "
                f"{spec.signal_property!r}"
            )
        if anchor_meta["signal_field"] != spec.signal_field:
            return False, (
                f"metadata.signal_field={anchor_meta['signal_field']!r} != expected {spec.signal_field!r}"
            )
        if anchor_meta["max_search_ticks"] != int(spec.max_search_ticks):
            return False, (
                f"metadata.max_search_ticks={anchor_meta['max_search_ticks']!r} != expected "
                f"{spec.max_search_ticks!r}"
            )
        if anchor_meta["event_observable_projection_version"] != EVENT_OBSERVABLE_PROJECTION_VERSION:
            return False, (
                f"metadata.event_observable_projection_version="
                f"{anchor_meta['event_observable_projection_version']!r} != expected "
                f"{EVENT_OBSERVABLE_PROJECTION_VERSION!r} (observable projection schema mismatch)"
            )

        if spec.signal_kind == "diameter_decrease" and window.onset_tick is None:
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
    targets a fresh, existence-checked ``.tmp-regen-<token>`` sibling
    directory (see ``allocate_unique_temp_output_path``) instead: a prior
    on-disk trace is never deleted or overwritten in place; only
    ``finalize_atomic_regeneration`` may replace it, and only after
    rebinding to this exact spec + token + pre-run manifest hash
    (``WindowJob.regen_token``/``WindowDecision.prior_file_sha256``) and
    revalidating the fresh output.
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
            # directly. The job targets a unique-token `.tmp-regen-<token>`
            # sibling directory (never absent-unchecked, never reused
            # bare); only `finalize_atomic_regeneration` may promote it to
            # `path`, and only after it independently revalidates against
            # this exact spec + token + the pre-run manifest hash captured
            # above (`prior_sha256`).
            token, temp_path = allocate_unique_temp_output_path(spec, karr_native_root=karr_native_root)
            temp_subdir = extractor_output_subdir_for(temp_path.parent)
            command = build_matlab_command(
                spec,
                log_relpath=log_relpath,
                output_subdir=temp_subdir,
                karr_native_root=karr_native_root,
            )
            job = WindowJob(
                process=spec.process,
                seed=spec.seed,
                window_contract=spec.window_contract,
                output_dir=str(temp_path.parent),
                matlab_command=command,
                log_path=log_relpath,
                temp_output_path=str(temp_path),
                final_output_path=str(path),
                regen_token=token,
            )
        else:
            output_dir = output_dir_for(spec, karr_native_root=karr_native_root)
            command = build_matlab_command(spec, log_relpath=log_relpath, karr_native_root=karr_native_root)
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
            extraction_identity_json=row.get("extraction_identity_json"),
            matlab_extraction_opts=dict(row.get("matlab_extraction_opts", {})),
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
            "unique '.tmp-regen-<token>' sibling directory (see allocate_unique_temp_output_path), "
            "and only finalize_atomic_regeneration may later replace the real file, after "
            "rebinding to the exact spec+token+pre-run manifest and revalidating."
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
