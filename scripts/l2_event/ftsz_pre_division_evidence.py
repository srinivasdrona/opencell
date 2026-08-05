"""FtsZPolymerization pre-division event-window evidence (catalog-conformant).

This module replaces the ad hoc "seed 0, ticks 0-99, no division
correlation" honest-mode diagnostic
(``tests/vivarium/test_karr_ftsz_polymerization_honest_canary.py``, see
``docs/phase_f/l2_windowed/FTSZ_WINDOWED_PROFILE_SPEC.md``) with a mechanism
that is directly conformant with the LIVE, unedited
``docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`` row for
``FtsZPolymerization`` (``bucket: EVENT_CLASS``, ``M_ticks: 200``,
``N_seeds: 50``, ``event_density: sparse``,
``seed_window.tick_range_from_division: [-200, 0]``). That row is
authoritative and is NOT edited by this module -- see the constants below,
each cited back to the catalog field it mirrors.

WHAT THIS MODULE DOES
- Discovers real, on-disk, division-anchored per-seed FtsZPolymerization
  event-window traces (``per_process_traces_v2_event_s{seed:03d}/
  FtsZPolymerization_200ticks.mat``), reusing the shared, unmodified
  ``scripts.l2_event.window_loader.load_event_window`` stride-1/M4
  contract loader -- no new trace-parsing logic is written here.
- Rejects (fails closed, never silently accepts) any window that is not
  exactly the catalog's division-relative range: ``window_anchor -
  tick_start + 1 == 200``. A window that runs long leaks post-division
  ticks in; a window that runs short truncates before -200. Both are
  refused, not clamped or silently trimmed.
- Detects duplicate seeds by content hash (a copy-pasted trace masquerading
  as a second seed does not increase ensemble size).
- Replays each accepted seed's window honestly (no ``trace_hint``, matching
  the existing canary's no-hint contract) through
  ``KarrFtsZPolymerizationProcess.next_update`` and detects the first real
  activity transition (a preregistered rule: the first tick whose raw
  per-species enzyme-count-delta L1 norm departs from zero -- i.e. FtsZ
  subunits were redistributed across oligomer states) on both the Karr
  side and the OC side independently -- no synthetic activation is
  injected. This is deliberately NOT based on the monomer projection below:
  ``next_update``'s ``discretize_enzymes``/``apply_substrate_limits`` are
  mass-preserving by construction (the v3.9 full-ODE-port fix), so the
  monomer-weighted total is a CONSERVED invariant that reads ~0 whether or
  not polymerization activity occurred -- using it as the activity signal
  would silently report "no activity" even during heavy polymerization.
- Projects the catalog's declared ``primary_channel: monomers`` as a
  read-only, post-update STATISTIC (not the activity signal --
  see above): ``monomer_total = dot(process.n_monomers, enzyme_counts)``.
  Because this quantity is conserved by construction, the meaningful
  per-tick cross-check is the OC-vs-Karr discrepancy in this projected
  total (both individually ~0; a nonzero gap between them means OC's
  discretization diverges from Karr's own mass-preserving arithmetic -- a
  real defect, not noise). This does not require (and does not fabricate)
  a ``monomers`` port that ``next_update`` does not emit.
- Reports ``INSUFFICIENT_ENSEMBLE`` with a nonzero, exact seed deficit and
  the precise resumable MATLAB extraction command whenever fewer than
  ``REQUIRED_N_SEEDS`` (50) validated windows exist on disk. It NEVER
  reports a sufficient/gated verdict for N < 50 -- there is no partial-
  credit branch (mirrors the existing honest canary's
  ``classify_ensemble_support``).

WHAT THIS MODULE IS NOT
- Not a gate. No W1/Wasserstein threshold or split-half null is computed
  or invented here (that remains future work, same as the superseded
  canary's section 7 contract).
- Not wired into ``scripts/l2_event/registry.py`` or ``runner.py``, and it
  does not edit ``docs/phase_f/l2_event/event_registry.yaml`` or
  ``docs/phase_f/l2_event/evidence_index.json``. FtsZPolymerization's
  registry row explicitly stays ``in_scope_v4: false`` -- promoting it to
  the generic event gate is a separate, explicit registry-owning decision,
  out of this module's scope. This is deliberately process-local evidence.
- Not a re-extraction: no MATLAB/Octave process is invoked by this module.
  It only discovers and validates whatever event-window traces already
  exist on disk, and prints the exact command a human/CI job would run to
  close the gap.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from scripts.l2_event.window_loader import EventWindowRefused, WindowGrid, load_event_window

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VIVARIUM_TEST_DIR = _REPO_ROOT / "tests" / "vivarium"

# ---------------------------------------------------------------------------
# Catalog-authoritative constants (docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml,
# FtsZPolymerization row). Cited, not re-derived; this module never edits
# that file.
# ---------------------------------------------------------------------------
PROCESS_NAME = "FtsZPolymerization"
REQUIRED_N_SEEDS = 50  # catalog N_seeds
REQUIRED_M_TICKS = 200  # catalog M_ticks
TICK_RANGE_FROM_DIVISION = (-200, 0)  # catalog seed_window.tick_range_from_division
PRIMARY_CHANNEL = "monomers"  # catalog primary_channel (projected, see module docstring)
GATE_CHANNELS = ("enzymes", "substrates")

_EVENT_WINDOW_DIR_PREFIX = "per_process_traces_v2_event_s"
_SEED_DIR_RE = re.compile(r"^per_process_traces_v2_event_s(\d{3})$")
_TRACE_FILENAME = f"{PROCESS_NAME}_{REQUIRED_M_TICKS}ticks.mat"
_MATLAB_DRIVER_REL = "scripts/matlab/extract_ftsz_pre_division_window_seeds.m"

# Data roots to search, in priority order. Mirrors
# tests/vivarium/l2_replay_common.py's resolve_trace_path multi-root
# fallback: raw .mat traces are gitignored (data/m1_sources/karr_native/...
# under .gitignore) so a worktree checkout will not itself contain them --
# the shared physical location they are actually extracted into is the main
# checkout. First match across these roots wins per seed.
DEFAULT_DATA_ROOTS: tuple[Path, ...] = (
    _REPO_ROOT / "data" / "m1_sources" / "karr_native",
    Path("E:/opencell/data/m1_sources/karr_native"),
    Path("/mnt/e/opencell/data/m1_sources/karr_native"),
)


def _import_l2_replay_common():
    """Import the existing L2.2 replay-primitive module by inserting its
    directory onto ``sys.path``, matching the pattern
    ``scripts/l2_event/adapters/ribosome_assembly_smoke.py`` and every
    ``tests/vivarium/test_karr_*_l2_replay.py`` file already use. Done
    lazily so importing this module never has an import-time side effect
    unless evidence computation actually runs."""
    if str(_VIVARIUM_TEST_DIR) not in sys.path:
        sys.path.insert(0, str(_VIVARIUM_TEST_DIR))
    import l2_replay_common  # noqa: PLC0415

    return l2_replay_common


class FtsZWindowContractError(Exception):
    """Raised when a trace that ``load_event_window`` itself accepts still
    fails an FtsZ-specific pre-division window check that the generic
    window_loader has no notion of (it does not know this process's
    catalog ``seed_window``): wrong ``n_ticks``, a fixed (non-division-
    anchored) window, or a division-relative span that is not exactly
    ``[-200, 0]``."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_candidate_paths(
    data_roots: tuple[Path, ...] = DEFAULT_DATA_ROOTS,
) -> dict[int, Path]:
    """Return ``{seed: trace_path}`` for every ``per_process_traces_v2_event_s*``
    directory (across all ``data_roots``, first root wins per seed) that
    contains a ``FtsZPolymerization_200ticks.mat`` file. Pure filesystem
    discovery -- does not open or validate any file's contents."""
    found: dict[int, Path] = {}
    for root in data_roots:
        if not root.exists() or not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            match = _SEED_DIR_RE.match(child.name)
            if not match:
                continue
            seed = int(match.group(1))
            if seed in found:
                continue
            candidate = child / _TRACE_FILENAME
            if candidate.exists():
                found[seed] = candidate
    return found


# ---------------------------------------------------------------------------
# Window validation (FtsZ-specific, layered on top of the shared loader)
# ---------------------------------------------------------------------------


def validate_seed_window(seed: int, trace_path: Path) -> WindowGrid:
    """Load ``trace_path`` via the shared, unmodified stride-1/M4 loader,
    then enforce the FtsZ catalog's division-anchored ``seed_window``
    contract on top of it. Raises :class:`EventWindowRefused` (generic M4
    problems) or :class:`FtsZWindowContractError` (FtsZ-specific problems)
    -- never silently accepts a malformed or wrongly-shaped window."""
    grid = load_event_window(
        trace_path,
        required_observables=GATE_CHANNELS,
        require_stride_contract=True,
    )
    if grid.process_name != PROCESS_NAME:
        raise FtsZWindowContractError(
            f"seed {seed}: trace metadata process_name={grid.process_name!r}, "
            f"expected {PROCESS_NAME!r} ({trace_path})"
        )
    if grid.seed != seed:
        raise FtsZWindowContractError(
            f"seed {seed}: trace metadata rng_seed={grid.seed} does not match the "
            f"seed implied by its directory name ({trace_path}) -- mislabeled or "
            "misplaced extraction output."
        )
    if grid.n_ticks != REQUIRED_M_TICKS:
        raise FtsZWindowContractError(
            f"seed {seed}: n_ticks={grid.n_ticks}, catalog M_ticks requires "
            f"{REQUIRED_M_TICKS} ({trace_path})"
        )
    if grid.window_anchor is None:
        raise FtsZWindowContractError(
            f"seed {seed}: trace has no metadata/window_anchor -- the catalog "
            "seed_window is division-anchored (tick_range_from_division="
            f"{TICK_RANGE_FROM_DIVISION}); a fixed tick_end-only window cannot "
            f"represent 'ends at division' ({trace_path})"
        )
    if grid.tick_start is None:
        raise FtsZWindowContractError(
            f"seed {seed}: trace has no metadata/tick_start ({trace_path})"
        )
    span = grid.window_anchor - grid.tick_start + 1
    if span != REQUIRED_M_TICKS:
        raise FtsZWindowContractError(
            f"seed {seed}: window_anchor({grid.window_anchor}) - "
            f"tick_start({grid.tick_start}) + 1 = {span}, expected exactly "
            f"{REQUIRED_M_TICKS} (catalog tick_range_from_division="
            f"{TICK_RANGE_FROM_DIVISION}). span > {REQUIRED_M_TICKS} means "
            f"post-division ticks leaked into the window; span < "
            f"{REQUIRED_M_TICKS} means the window is truncated before -200 "
            f"({trace_path})."
        )
    return grid


# ---------------------------------------------------------------------------
# Activity detection + monomer projection (no-hint, mechanically tied to
# real Karr/OC state)
# ---------------------------------------------------------------------------


def first_activity_transition(activity_magnitudes: list[float]) -> int | None:
    """Preregistered rule (fixed before any seed's numbers are inspected):
    the index (0-based, local to the window) of the first tick whose
    activity magnitude is nonzero. Returns ``None`` if the entire window is
    inactive -- that is a real finding (no transition occurred in this
    seed's window), never coerced into a fabricated tick.

    ``activity_magnitudes`` MUST be a real per-tick redistribution signal
    (see ``enzyme_delta_l1`` below) -- NOT the monomer-projected delta
    (``project_monomer_total`` of an enzyme delta). ``next_update``'s
    ``discretize_enzymes``/``apply_substrate_limits`` are mass-preserving
    by construction (v3.9 fix note in the catalog): FtsZ polymerization
    redistributes existing subunits across oligomer states without ever
    creating or destroying monomer-equivalent mass, so
    ``dot(process.n_monomers, enzyme_delta)`` is a CONSERVED invariant
    (~0 every tick, active or not) rather than an activity signal. Feeding
    it into this function would report ``None`` even during heavy
    polymerization -- silently failing the beat-3 "at least one real
    activity transition" requirement. The raw per-species enzyme delta L1
    norm is the actual redistribution signal."""
    for idx, value in enumerate(activity_magnitudes):
        if abs(value) > 0.0:
            return idx
    return None


def enzyme_delta_l1(delta_vec: np.ndarray) -> float:
    """Raw per-species enzyme-count-delta L1 norm for one tick -- the real
    "did FtsZ redistribute any subunits this tick" activity signal (see
    ``first_activity_transition`` docstring for why the monomer projection
    below cannot serve this purpose)."""
    return float(np.sum(np.abs(delta_vec)))


def project_monomer_total(process: Any, counts: np.ndarray) -> float:
    """Read-only projection of the catalog's ``primary_channel: monomers``
    onto real enzyme-count state: ``dot(process.n_monomers, counts)``. Does
    not mutate process state and does not require a ``monomers`` port.

    This is the catalog's declared primary-channel STATISTIC (used below to
    cross-check OC's mass-preserving discretization against Karr's own
    per-tick counts), not the activity signal -- see
    ``first_activity_transition``."""
    return float(np.dot(process.n_monomers, counts))


@dataclass(frozen=True)
class SeedWindowEvidence:
    seed: int
    trace_path: Path
    trace_sha256: str
    tick_start: int
    window_anchor: int
    n_ticks: int
    karr_activity_transition_tick: int | None
    oc_activity_transition_tick: int | None
    monomer_l1_mean: float
    monomer_l1_max: float

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "trace_path": str(self.trace_path),
            "trace_sha256": self.trace_sha256,
            "tick_start": self.tick_start,
            "window_anchor": self.window_anchor,
            "n_ticks": self.n_ticks,
            "karr_activity_transition_tick": self.karr_activity_transition_tick,
            "oc_activity_transition_tick": self.oc_activity_transition_tick,
            "monomer_l1_mean": self.monomer_l1_mean,
            "monomer_l1_max": self.monomer_l1_max,
        }


def compute_seed_evidence(seed: int, grid: WindowGrid) -> SeedWindowEvidence:
    """Honest (no ``trace_hint``) per-tick replay of one validated
    division-anchored window. Reuses the existing L2.2 replay primitives
    (``tests/vivarium/l2_replay_common.py``) rather than reimplementing
    state-template construction or update application; wraps every
    ``next_update`` call in ``forbid_sut_oracle_file_io`` (Rule 8 defense in
    depth) even though production code under ``opencell/vivarium/`` never
    opens the oracle itself."""
    l2 = _import_l2_replay_common()
    from opencell.vivarium.karr_ftsz_polymerization import (  # noqa: PLC0415
        KarrFtsZPolymerizationProcess,
    )

    process = KarrFtsZPolymerizationProcess({"rng_seed": int(seed)})
    state_template = l2.build_state_template(process)

    wids_by_observable: dict[str, list[str]] = {}
    for observable in GATE_CHANNELS:
        karr_before = grid.before(observable, 0)
        wids_by_observable[observable] = l2.infer_wids_for_observable(
            process,
            state_template,
            observable,
            karr_len=int(karr_before.shape[0]),
            explicit_attr={"substrates": "substrate_wids", "enzymes": "enzyme_wids"}[observable],
        )
    if wids_by_observable["enzymes"] != list(process.enzyme_wids):
        raise FtsZWindowContractError(
            f"seed {seed}: enzymes WID order drift between harness inference and "
            "process fixture order -- the monomer projection below would silently "
            "score against the wrong species."
        )

    karr_enzyme_l1_deltas: list[float] = []
    oc_enzyme_l1_deltas: list[float] = []
    monomer_abs_discrepancy: list[float] = []

    for tick in range(grid.n_ticks):
        state = l2.build_state_template(process)
        assert not state.get("trace_hint"), "no-hint contract violated before overlay"

        before_vectors = {obs: grid.before(obs, tick) for obs in GATE_CHANNELS}
        after_vectors = {obs: grid.after(obs, tick) for obs in GATE_CHANNELS}
        for observable in GATE_CHANNELS:
            l2.overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=before_vectors[observable],
                wids=wids_by_observable[observable],
            )
        l2.refresh_allocator_views(process, state)
        assert not state.get("trace_hint"), "no-hint contract violated after overlay"

        with l2.forbid_sut_oracle_file_io():
            update = process.next_update(1.0, state)

        deltas_by_label = dict(l2.collect_count_delta_dicts(update))
        enzyme_delta = deltas_by_label.get("enzymes", {})
        oc_delta_vec = np.asarray(
            [float(enzyme_delta.get(wid, 0.0)) for wid in process.enzyme_wids], dtype=np.float64
        )
        karr_delta_vec = after_vectors["enzymes"] - before_vectors["enzymes"]

        # Activity signal: raw per-species redistribution (see
        # first_activity_transition/enzyme_delta_l1 docstrings for why this
        # -- not the monomer projection below -- is the real "did anything
        # happen this tick" measure).
        oc_enzyme_l1_deltas.append(enzyme_delta_l1(oc_delta_vec))
        karr_enzyme_l1_deltas.append(enzyme_delta_l1(karr_delta_vec))

        # Catalog primary-channel statistic: the mass-preserving-
        # discretization invariant, cross-checked OC vs Karr per tick (both
        # should be individually ~0; a nonzero discrepancy between the two
        # means OC's discretization diverges from Karr's, a real defect).
        oc_monomer_delta = project_monomer_total(process, oc_delta_vec)
        karr_monomer_delta = project_monomer_total(process, karr_delta_vec)
        monomer_abs_discrepancy.append(abs(oc_monomer_delta - karr_monomer_delta))

    return SeedWindowEvidence(
        seed=seed,
        trace_path=grid.trace_path,
        trace_sha256=_sha256_file(grid.trace_path),
        tick_start=int(grid.tick_start),
        window_anchor=int(grid.window_anchor),
        n_ticks=int(grid.n_ticks),
        karr_activity_transition_tick=first_activity_transition(karr_enzyme_l1_deltas),
        oc_activity_transition_tick=first_activity_transition(oc_enzyme_l1_deltas),
        monomer_l1_mean=float(np.mean(monomer_abs_discrepancy)),
        monomer_l1_max=float(np.max(monomer_abs_discrepancy)),
    )


# ---------------------------------------------------------------------------
# Resumable extraction command (surfaced, never silently substituted for
# real data)
# ---------------------------------------------------------------------------


def resumable_extraction_command(missing_seeds: list[int]) -> str:
    if not missing_seeds:
        return ""
    start, end = missing_seeds[0], missing_seeds[-1]
    return (
        "matlab -batch \"addpath(genpath('scripts/matlab')); "
        f'extract_ftsz_pre_division_window_seeds({start}, {end})"'
        f"  # resumable: re-running skips any seed whose "
        f"data/m1_sources/karr_native/{_EVENT_WINDOW_DIR_PREFIX}NNN/{_TRACE_FILENAME} "
        f"already exists. Missing seeds ({len(missing_seeds)}): {missing_seeds}. "
        f"Driver: {_MATLAB_DRIVER_REL}."
    )


# ---------------------------------------------------------------------------
# Top-level audit
# ---------------------------------------------------------------------------


@dataclass
class PreDivisionAuditReport:
    process: str
    required_n_seeds: int
    required_m_ticks: int
    tick_range_from_division: tuple[int, int]
    found_seeds: list[int]
    duplicate_seeds: list[dict[str, Any]] = field(default_factory=list)
    rejected_windows: list[dict[str, Any]] = field(default_factory=list)
    per_seed_evidence: list[SeedWindowEvidence] = field(default_factory=list)
    status: str = "INSUFFICIENT_ENSEMBLE"
    deficit: int = 0
    resumable_extraction_command: str = ""
    monomer_primary_statistic: dict[str, float] | None = None
    activity_summary: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "process": self.process,
            "required_n_seeds": self.required_n_seeds,
            "required_m_ticks": self.required_m_ticks,
            "tick_range_from_division": list(self.tick_range_from_division),
            "found_seeds": self.found_seeds,
            "duplicate_seeds": self.duplicate_seeds,
            "rejected_windows": self.rejected_windows,
            "per_seed_evidence": [e.to_json() for e in self.per_seed_evidence],
            "status": self.status,
            "deficit": self.deficit,
            "resumable_extraction_command": self.resumable_extraction_command,
            "monomer_primary_statistic": self.monomer_primary_statistic,
            "activity_summary": self.activity_summary,
        }


def audit_pre_division_evidence(
    data_roots: tuple[Path, ...] = DEFAULT_DATA_ROOTS,
) -> PreDivisionAuditReport:
    """The single entry point this module exposes: discover, dedupe,
    validate, and replay every real on-disk FtsZ division-window seed, and
    report an honest ensemble-completeness verdict. Never reports
    ``SUFFICIENT_ENSEMBLE`` for ``len(found_seeds) < REQUIRED_N_SEEDS`` --
    there is no partial-credit branch."""
    candidates = discover_candidate_paths(data_roots)

    seen_sha: dict[str, int] = {}
    duplicate_seeds: list[dict[str, Any]] = []
    rejected_windows: list[dict[str, Any]] = []
    per_seed_evidence: list[SeedWindowEvidence] = []
    found_seeds: list[int] = []

    for seed in sorted(candidates):
        path = candidates[seed]
        sha = _sha256_file(path)
        if sha in seen_sha:
            duplicate_seeds.append(
                {
                    "seed": seed,
                    "duplicate_of_seed": seen_sha[sha],
                    "sha256": sha,
                    "path": str(path),
                }
            )
            continue
        seen_sha[sha] = seed

        try:
            grid = validate_seed_window(seed, path)
        except (EventWindowRefused, FtsZWindowContractError) as exc:
            rejected_windows.append({"seed": seed, "path": str(path), "reason": str(exc)})
            continue

        evidence = compute_seed_evidence(seed, grid)
        per_seed_evidence.append(evidence)
        found_seeds.append(seed)

    deficit = max(0, REQUIRED_N_SEEDS - len(found_seeds))
    status = "INSUFFICIENT_ENSEMBLE" if deficit > 0 else "SUFFICIENT_ENSEMBLE"
    missing_seeds = sorted(set(range(REQUIRED_N_SEEDS)) - set(found_seeds))

    monomer_stat: dict[str, float] | None = None
    if per_seed_evidence:
        means = [e.monomer_l1_mean for e in per_seed_evidence]
        maxes = [e.monomer_l1_max for e in per_seed_evidence]
        monomer_stat = {
            "n_seeds": len(per_seed_evidence),
            "monomer_l1_mean_over_seeds": float(np.mean(means)),
            "monomer_l1_max_over_seeds": float(np.max(maxes)),
        }

    activity_summary = {
        "seeds_total": len(per_seed_evidence),
        "seeds_with_karr_activity_transition": sum(
            1 for e in per_seed_evidence if e.karr_activity_transition_tick is not None
        ),
        "seeds_with_oc_activity_transition": sum(
            1 for e in per_seed_evidence if e.oc_activity_transition_tick is not None
        ),
    }

    return PreDivisionAuditReport(
        process=PROCESS_NAME,
        required_n_seeds=REQUIRED_N_SEEDS,
        required_m_ticks=REQUIRED_M_TICKS,
        tick_range_from_division=TICK_RANGE_FROM_DIVISION,
        found_seeds=found_seeds,
        duplicate_seeds=duplicate_seeds,
        rejected_windows=rejected_windows,
        per_seed_evidence=per_seed_evidence,
        status=status,
        deficit=deficit,
        resumable_extraction_command=resumable_extraction_command(missing_seeds),
        monomer_primary_statistic=monomer_stat,
        activity_summary=activity_summary,
    )


def main() -> int:
    report = audit_pre_division_evidence()
    print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    print()
    print(f"status={report.status} deficit={report.deficit}/{report.required_n_seeds}")
    if report.deficit > 0:
        print("Resumable extraction command:")
        print(f"  {report.resumable_extraction_command}")
    return 0 if report.status == "SUFFICIENT_ENSEMBLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
