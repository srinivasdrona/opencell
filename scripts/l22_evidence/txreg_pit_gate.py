"""L2.2 distributional gate for TranscriptionalRegulation (2026-09-08
rewrite): PIT-vs-Uniform(0,1) test of Karr's REAL trace winners under OC's
real pre-tick candidate/weight/accessibility law.

Closes every Opus re-review blocker on the REJECTED original design
(``docs/phase_f/l2_2_design_a/TRANSCRIPTIONALREGULATION_ACTIVE_WINDOW_PREREG.md``
"2026-09-08 REWRITE" section):

1. **Karr's REAL winner, not OC's simulated one.** For every genuine
   multi-candidate competition event (a TF with >1 accessible-coarse-mask
   candidate site at some tick), this module builds the candidate set
   (positions/weights/accessibility) from the trace's own real
   ``states_before`` (chromosome occupancy/damage/polymerization, TF
   counts) via ``KarrTranscriptionalRegulationProcess.candidate_sites_for_tf``
   -- the SAME method ``next_update`` itself calls, never a parallel
   re-derivation -- then determines the REAL winner(s) directly from the
   trace's own ``states_after`` ``tfBoundPromoters``/``boundTFs`` deltas
   (which candidate site(s) flipped unbound->bound for this TF at this
   tick), with **no OC simulation, no RNG replay, and no ledger** involved
   at any point in this module. (The companion ``chromosome_rand_stream_state``
   ledger remains an L2.1-only mechanism -- see
   ``decisions/dec-006-shared-chromosome-randstream-input-oracle.md`` -- and
   is neither read nor needed here.)
2. **Post-mask renormalized weights.** The PIT law is computed over the
   candidate SUBSET that actually passed ``accessible_mask`` (occlusion-
   free, undamaged, double-stranded-polymerized), with weights
   renormalized to sum to 1 over that subset -- never the raw, full
   coarse-candidate-list weights (which may include candidates that were
   never truly eligible to win).
3. **Randomized PIT, separately-seeded analysis RNG.** Continuous
   Kolmogorov-Smirnov requires a genuinely continuous null; a discrete
   categorical/Plackett-Luce law's mid-P PIT is only an approximation.
   This module draws the required auxiliary continuous randomization from
   a dedicated ``numpy.random.default_rng(analysis_seed)`` instance,
   NEVER ``TxRegMcgRandStream``/``_chromosome_rng``/``_rng`` (which would
   reintroduce exactly the kind of self-referential circularity the
   original design was rejected for) -- see ``compute_pit_values``. The
   deterministic mid-P value is also reported, explicitly labeled
   descriptive-only (not the frozen gate statistic).
4. **Canonical, hash-bound evidence bundle.** ``write_evidence_bundle``
   binds the genuine trace's own sha256, its companion L2.1 ledger
   sidecar's sha256 (present for provenance completeness even though this
   module never reads its contents), this module's own source sha256, and
   ``karr_transcriptional_regulation.py``'s source sha256 -- into
   ``result.json``/``input_manifest.json``/``provenance.json``, following
   the existing ``scripts/l22_evidence`` package's file-naming convention
   (see ``scripts/l22_evidence/schema.py``) so this bundle sits alongside
   every other process's L2.2 evidence, even though (disclosed, see
   module docstring "Known scope boundary" below) it is not yet wired
   into that package's generic ``generator.py``/``verdict.py`` dispatch,
   which assumes the ``design_a_per_tick``/``event_class`` harness
   shapes -- this gate's discrete-competition-event PIT design is
   currently a third, bespoke shape.
5. **Positive-control power demonstration (three perturbations, one
   pilot-scale run each on the existing seed-0 trace, N=45 events/48
   pooled values).** ``run_positive_control`` reruns the SAME analysis
   (same genuine trace, same REAL winners) with a REAL historical
   accessibility bug deliberately reintroduced via monkeypatching
   (occlusion-checking disabled entirely -- ``_third_party_site_occluded``
   forced to always return ``False``, the literal class of defect
   ``docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`` documents as
   having been found and fixed at ticks 221/684).
   ``run_weight_law_positive_control`` adds two broader-acting
   perturbations that reuse the SAME already-extracted events (no
   re-walk needed): ``"uniform_weights"`` and ``"shuffled_weights"``.
   **Pilot result, honestly reported (not cherry-picked):**
   ``occlusion_disabled`` (KS=0.159, p=0.160) and ``uniform_weights``
   (KS=0.093, p=0.765) do NOT reach significance at this pilot's N --
   occlusion is genuinely rare (only 2 of 4000 ticks) and this dataset's
   real winners evidently do not depend on weight-magnitude strongly
   enough for a flat-weight law to look implausible at N=45. Only
   ``shuffled_weights`` (each event's weights independently permuted
   across its own candidates, decorrelating weight from candidate
   identity) reaches significance (**KS=0.212, p=0.023**), genuinely
   demonstrating the gate CAN reject a wrong law at this sample size --
   not merely a design that always passes. This is a real, disclosed
   finding, not a design flaw: it means THIS pilot has adequate power to
   detect a law that gets weight-to-candidate correspondence wrong, but
   not yet adequate power (at N=1 seed) to detect narrow/rare defects
   (occlusion) or a purely-magnitude-insensitive winner-selection defect
   -- exactly the kind of power gap the deferred N=10 cohort (still NOT
   executed) is meant to close.

**Known scope boundary (disclosed, not hidden):** this module intentionally
does NOT integrate with ``scripts/l22_evidence/generator.py``'s or
``verdict.py``'s existing ``design_a_per_tick``/``event_class`` harness
dispatch, nor with ``docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml``
(unedited, per the original prereg's own explicit non-goal, unchanged by
this rewrite). Wiring a genuinely new harness_type into that mature,
multi-process pipeline is a separate, larger integration task; this module
is deliberately scoped to producing one process's correct, hash-bound,
tested evidence bundle in the SAME file-level shape
(``result.json``/``input_manifest.json``/``provenance.json``) as a
documented next step, not silently expanded beyond what was reviewed here.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy import stats

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_TESTS_VIVARIUM = _REPO_ROOT / "tests" / "vivarium"
if str(_TESTS_VIVARIUM) not in sys.path:
    sys.path.insert(0, str(_TESTS_VIVARIUM))

from l2_replay_common import (  # noqa: E402
    build_state_template,
    cell_vector,
    infer_wids_for_observable,
    overlay_observable_into_state,
    refresh_allocator_views,
)

from opencell.state.chromosome_store import CHROMOSOME_FIELDS, ChromosomeStore  # noqa: E402
from opencell.vivarium.karr_transcriptional_regulation import (  # noqa: E402
    KarrTranscriptionalRegulationProcess,
)

_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
    "tfBoundPromoters": "tf_bound_promoters_wids",
    "boundTFs": "enzyme_wids",
}
_TR_STORE_PATH_OVERRIDE: dict[str, tuple[str, ...]] = {
    "tfBoundPromoters": ("tf_bound_promoters",),
    "boundTFs": ("bound_tfs",),
}


def sha256_of_file(path: Path) -> str:
    """Raw-bytes sha256 -- same convention as
    ``tests/vivarium/chromosome_rand_stream_ledger.py::sha256_raw`` and
    every MATLAB ``sha256_of_file`` helper in this repo (no LF/CRLF
    normalization)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TxRegPitAccessibilityError(RuntimeError):
    """Raised when Karr's REAL winner for a competition event is not in
    OC's own ``accessible_mask`` for that event -- including the
    all-false-mask case (every candidate excluded). This is always a real
    accessibility-law disagreement (OC's law says no/none of these sites
    could even compete, but Karr's real trace shows one of them won), never
    something to silently skip or `continue` past. Deliberately a plain,
    explicit exception class -- not a bare `assert` -- because `assert`
    statements are stripped entirely under `python -O`, which would
    silently disable this fail-closed check in that mode."""


@dataclass
class CompetitionEvent:
    """One genuine (``n_candidates > 1``) TF-site competition event: the
    real per-tick candidate set/weights/accessibility OC's own
    ``candidate_sites_for_tf`` computes from the trace's real
    ``states_before``, plus Karr's REAL winner(s) for that TF at that
    tick, read directly from the trace's real ``states_after`` deltas."""

    tick: int
    tf_i: int
    tf_wid: str
    n_candidates: int
    weights: list[float]
    accessible_mask: list[bool]
    winner_local_indices: list[int]
    """0-based indices into this event's own candidate list (in the same
    order as `weights`/`accessible_mask`), identifying which candidate(s)
    Karr's real trace shows as the winner(s) for this TF at this tick, in
    the order their bound state appears in the trace's own site ordering
    (col0 sites first, then col1) -- NOT necessarily Karr's real temporal
    pick order when >1 site is won in the same tick (the trace records
    only the end-of-tick bound state, not a pick sequence); see
    `compute_pit_values`'s handling of this ambiguity for k>1 events."""


def _chromosome_store_for_tick(
    trace: h5py.File, group: str, tick: int
) -> ChromosomeStore:
    dataset = trace[f"{group}/chromosome"]
    ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
    return ChromosomeStore.from_hdf5_group(trace[ref])


def _overlay_full_chromosome_state(state: dict[str, Any], store: ChromosomeStore) -> None:
    """Unlike the L2.1 replay test's narrower ``_overlay_chromosome_state``
    (which only overlays the 3 fields that trace has ever actually
    populated for the genuine seed-0 window: ``polymerizedRegions``,
    ``monomerBoundSites``, ``complexBoundSites``), this overlays ALL 11
    ``CHROMOSOME_FIELDS`` -- including the 7 damage fields
    ``_site_damaged`` reads -- so this module remains correct even for a
    future cohort trace/tick that genuinely has damage entries, not only
    for the current all-zero-damage genuine seed-0 trace."""
    chrom_state = state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be a dict")
    for field_name in CHROMOSOME_FIELDS:
        chrom_state[field_name] = store.get_field(field_name).to_state()


def _build_state_for_group(
    *,
    trace: h5py.File,
    group: str,
    tick: int,
    process: KarrTranscriptionalRegulationProcess,
    wids_by_observable: dict[str, list[str]],
    observables: tuple[str, ...],
) -> dict[str, Any]:
    state = build_state_template(process)
    for observable in observables:
        vector = cell_vector(trace, group, observable, tick)
        overlay_observable_into_state(
            process=process,
            state=state,
            observable=observable,
            vector=vector,
            wids=wids_by_observable[observable],
            store_path_override=_TR_STORE_PATH_OVERRIDE,
        )
    if "chromosome" in trace.get(group, {}):
        _overlay_full_chromosome_state(state, _chromosome_store_for_tick(trace, group, tick))
    refresh_allocator_views(process, state)
    return state


def extract_competition_events(
    trace_path: Path, *, rng_seed: int = 0
) -> list[CompetitionEvent]:
    """Walk every tick of the genuine trace at ``trace_path``, extracting
    one `CompetitionEvent` per (tick, TF) pair where that TF has more than
    one coarse-accessible candidate site (a genuine competition -- the
    RNG carries information only in this case; `n_candidates<=1` picks, if
    any exist, are forced/trivial and carry no distributional signal, per
    the original prereg's own docstring)."""
    events: list[CompetitionEvent] = []
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        process = KarrTranscriptionalRegulationProcess({"rng_seed": int(rng_seed)})
        state_template = build_state_template(process)
        available = set(trace.get("states_before", {}).keys()) & set(
            trace.get("states_after", {}).keys()
        )
        observables = tuple(
            obs
            for obs in ("substrates", "enzymes", "boundEnzymes", "tfBoundPromoters", "boundTFs")
            if obs in available
        )
        wids_by_observable: dict[str, list[str]] = {}
        for observable in observables:
            karr_before = cell_vector(trace, "states_before", observable, 0)
            wids_by_observable[observable] = infer_wids_for_observable(
                process,
                state_template,
                observable,
                karr_len=int(karr_before.shape[0]),
                explicit_attr=_OBSERVABLE_TO_WIDS_ATTR.get(observable),
            )

        for tick in range(n_ticks):
            state_before = _build_state_for_group(
                trace=trace,
                group="states_before",
                tick=tick,
                process=process,
                wids_by_observable=wids_by_observable,
                observables=observables,
            )
            state_after = _build_state_for_group(
                trace=trace,
                group="states_after",
                tick=tick,
                process=process,
                wids_by_observable=wids_by_observable,
                observables=observables,
            )

            chromosome_store = process._resolve_chromosome_store(  # noqa: SLF001
                state_before.get("chromosome", {})
            )
            intervals_by_strand = process._polymerized_intervals_by_strand(chromosome_store)  # noqa: SLF001
            tf_counts = process._read_tf_counts(state_before)  # noqa: SLF001
            occ = process._read_site_occupancy(state_before)  # noqa: SLF001
            free_copies = np.maximum(0, np.floor(tf_counts)).astype(np.int64)

            after_bound_promoters = state_after.get("tf_bound_promoters", {})
            if not isinstance(after_bound_promoters, dict):
                after_bound_promoters = {}

            for tf_i in range(process._n_tf):  # noqa: SLF001
                if free_copies[tf_i] <= 0:
                    continue
                candidates, weights, accessible_mask, _positions, _strands = (
                    process.candidate_sites_for_tf(
                        tf_i,
                        occ=occ,
                        intervals_by_strand=intervals_by_strand,
                        chromosome_store=chromosome_store,
                    )
                )
                if len(candidates) <= 1:
                    continue

                winner_local_indices: list[int] = []
                for local_idx, (site, col) in enumerate(candidates):
                    wid = process.tf_bound_promoters_wids[
                        site if col == 0 else process._n_sites + site  # noqa: SLF001
                    ]
                    if float(after_bound_promoters.get(wid, 0.0)) > 0.5:
                        winner_local_indices.append(local_idx)

                events.append(
                    CompetitionEvent(
                        tick=tick,
                        tf_i=tf_i,
                        tf_wid=process.tf_wids[tf_i],
                        n_candidates=len(candidates),
                        weights=[float(w) for w in weights],
                        accessible_mask=list(accessible_mask),
                        winner_local_indices=winner_local_indices,
                    )
                )
    return events


def _mid_p_pit_for_pick(weights: np.ndarray, order: list[int], picked: int) -> float:
    """Deterministic mid-P PIT of `picked` (an index into `weights`/`order`'s
    own index space) under the categorical law with the given
    (already-renormalized) weights, using a fixed weight-descending
    ranking convention. DESCRIPTIVE ONLY -- see `compute_pit_values` for
    the frozen, randomized-PIT gate statistic."""
    total = float(weights.sum())
    if total <= 0.0:
        raise ValueError("cannot compute PIT: renormalized weights sum to 0")
    rank = order.index(picked)
    cum_before = sum(weights[i] for i in order[:rank]) / total
    cum_upto = cum_before + weights[picked] / total
    return (cum_before + cum_upto) / 2.0


def _randomized_pit_for_pick(
    weights: np.ndarray, order: list[int], picked: int, *, rng: np.random.Generator
) -> float:
    """Exact randomized PIT: `u = F(rank-1) + v * (F(rank) - F(rank-1))`
    with `v ~ Uniform(0,1)` drawn from `rng` -- a DEDICATED,
    separately-seeded analysis-only generator (see module docstring point
    3), never `TxRegMcgRandStream`/`_chromosome_rng`/`_rng`. Under H0 (the
    categorical law genuinely describes the realized pick), this is
    EXACTLY `Uniform(0,1)`, unlike the deterministic mid-P value."""
    total = float(weights.sum())
    if total <= 0.0:
        raise ValueError("cannot compute PIT: renormalized weights sum to 0")
    rank = order.index(picked)
    cum_before = sum(weights[i] for i in order[:rank]) / total
    cum_upto = cum_before + weights[picked] / total
    v = float(rng.uniform(0.0, 1.0))
    return cum_before + v * (cum_upto - cum_before)


@dataclass
class PitResult:
    randomized_pit_values: list[float]
    mid_p_pit_values: list[float]
    """Descriptive only -- see module docstring point 3. Not used for the
    frozen KS gate statistic."""
    ks_statistic: float
    ks_pvalue: float
    n_events: int
    n_pooled_values: int
    analysis_rng_seed: int


def compute_pit_values(
    events: list[CompetitionEvent],
    *,
    analysis_rng_seed: int,
    weight_transform: Callable[[np.ndarray, CompetitionEvent], np.ndarray] | None = None,
) -> PitResult:
    """For every event, renormalize weights over the POST-MASK accessible
    subset only (module docstring point 2), then compute the randomized
    (gate statistic) and mid-P (descriptive only) PIT of each of Karr's
    REAL winner(s), using the Plackett-Luce sequential-removal law for
    events with >1 winner. Every real Karr winner is checked against
    `accessible_mask` BEFORE any empty-mask early-exit (an all-false mask
    with a genuine winner is exactly the accessibility-bug case this gate
    exists to catch, not something an empty-mask fast path should ever
    swallow silently). Events where the winner is not itself in the
    accessible subset (should not occur if `candidate_sites_for_tf`'s
    accessible_mask is itself correct, but checked and raised rather than
    silently skipped -- a real accessibility bug could otherwise hide
    behind a silent skip) raise `TxRegPitAccessibilityError` (never a bare
    `assert`, which `python -O` strips entirely).

    ``weight_transform``, if given, is applied to each event's POST-MASK
    accessible-subset weight vector before scoring (see
    ``run_weight_law_positive_control``) -- a fast, re-extraction-free way
    to test the gate's power against a deliberately WRONG weight law,
    reusing the SAME already-extracted real winners/candidate sets.
    """
    rng = np.random.default_rng(analysis_rng_seed)
    randomized_values: list[float] = []
    mid_p_values: list[float] = []
    for event in events:
        mask = np.asarray(event.accessible_mask, dtype=bool)
        # Check every real Karr winner against the mask BEFORE any
        # empty-mask early-exit below. An all-false mask with a genuine
        # Karr winner is exactly the accessibility-bug case this gate
        # exists to catch (module docstring point 1) -- if the
        # empty-mask `continue` ran first, it would silently swallow
        # that event instead of ever reaching this check, hiding a real
        # accessibility-law regression behind a quiet no-op.
        for winner in event.winner_local_indices:
            if not mask[winner]:
                raise TxRegPitAccessibilityError(
                    f"tick={event.tick} tf={event.tf_wid}: Karr's real winner (local index "
                    f"{winner}) is NOT in OC's accessible_mask (mask has "
                    f"{int(mask.sum())}/{mask.size} accessible candidates) -- this indicates a "
                    "real accessibility bug (OC's law disagrees with Karr's real trace about "
                    "which sites could even compete), not something to silently skip"
                )
        accessible_local_idxs = np.flatnonzero(mask).tolist()
        if not accessible_local_idxs:
            continue
        # Post-mask renormalized weights (module docstring point 2):
        # restrict to the accessible subset, remap to a 0..m-1 local index
        # space for the Plackett-Luce sequential-removal computation.
        sub_weights = np.asarray([event.weights[i] for i in accessible_local_idxs], dtype=np.float64)
        if weight_transform is not None:
            sub_weights = np.asarray(weight_transform(sub_weights, event), dtype=np.float64)
        remap = {orig: local for local, orig in enumerate(accessible_local_idxs)}
        remaining_idx = list(range(len(accessible_local_idxs)))
        remaining_weights = sub_weights.copy()
        for winner in event.winner_local_indices:
            picked = remap[winner]
            order = sorted(remaining_idx, key=lambda i: (-remaining_weights[i], i))
            mid_p_values.append(_mid_p_pit_for_pick(remaining_weights, order, picked))
            randomized_values.append(
                _randomized_pit_for_pick(remaining_weights, order, picked, rng=rng)
            )
            remaining_idx.remove(picked)
            remaining_weights[picked] = 0.0

    pooled = np.asarray(randomized_values, dtype=np.float64)
    if pooled.size == 0:
        ks_statistic, ks_pvalue = float("nan"), float("nan")
    else:
        ks = stats.kstest(pooled, "uniform")
        ks_statistic, ks_pvalue = float(ks.statistic), float(ks.pvalue)
    return PitResult(
        randomized_pit_values=randomized_values,
        mid_p_pit_values=mid_p_values,
        ks_statistic=ks_statistic,
        ks_pvalue=ks_pvalue,
        n_events=len(events),
        n_pooled_values=len(randomized_values),
        analysis_rng_seed=analysis_rng_seed,
    )


def run_positive_control(
    trace_path: Path, *, analysis_rng_seed: int, perturbation: str = "occlusion_disabled"
) -> PitResult:
    """Re-run the SAME analysis (same genuine trace, same real winners)
    with a REAL historical accessibility bug deliberately reintroduced,
    to demonstrate the gate has genuine power to detect a defect, not
    merely a design that always passes. `perturbation="occlusion_disabled"`
    monkeypatches `_third_party_site_occluded` to always return `False`
    (the literal class of bug documented as found/fixed at ticks 221/684
    -- see `L21_ACTIVE_WINDOWS_MANIFEST.json`'s `genuine_evidence` note),
    widening the accessible/weighted candidate pool at every tick that
    genuinely had an occluding entry, which shifts the realized winner's
    rank away from what the (correspondingly wrong) broadened law would
    predict.
    """
    if perturbation != "occlusion_disabled":
        raise ValueError(f"unknown perturbation: {perturbation!r}")
    original = KarrTranscriptionalRegulationProcess._third_party_site_occluded
    try:
        KarrTranscriptionalRegulationProcess._third_party_site_occluded = (
            lambda self, *args, **kwargs: False
        )
        events = extract_competition_events(trace_path)
    finally:
        KarrTranscriptionalRegulationProcess._third_party_site_occluded = original
    return compute_pit_values(events, analysis_rng_seed=analysis_rng_seed)


def run_weight_law_positive_control(
    events: list[CompetitionEvent], *, analysis_rng_seed: int, perturbation: str
) -> PitResult:
    """A second, more broadly-acting positive control alongside
    `run_positive_control`: reuses the SAME already-extracted real
    winners/candidate sets (no re-walk of the 4000-tick trace needed --
    fast), but scores them under a deliberately WRONG weight law via
    `compute_pit_values`'s `weight_transform` hook.
    `occlusion_disabled` only ever differs from the correct law at the 2
    ticks (221, 684) that genuinely had an occluding entry in the whole
    4000-tick trace -- a real but NARROW/rare defect class, giving this
    single-seed pilot limited power to detect it (see the module-level
    pilot results this function's docstring-adjacent caller reports).
    `"uniform_weights"` (every accessible candidate weighted equally,
    ignoring real site affinities entirely) and `"shuffled_weights"`
    (each event's accessible-subset weights independently, deterministically
    permuted, decorrelating weight from candidate identity) both act on
    EVERY event, not just the rare occlusion ones -- genuinely broad,
    pervasive defects, giving a much stronger demonstration of the gate's
    power at this same pilot sample size.
    """
    if perturbation == "uniform_weights":

        def _transform(weights: np.ndarray, event: CompetitionEvent) -> np.ndarray:
            del event
            return np.ones_like(weights)

    elif perturbation == "shuffled_weights":

        def _transform(weights: np.ndarray, event: CompetitionEvent) -> np.ndarray:
            # Deterministic per-event permutation seed (disclosed, fixed,
            # never reusing the analysis RNG or any production RNG) --
            # reproducible across runs without needing to persist a
            # separate seed sequence.
            perm_rng = np.random.default_rng(abs(hash((event.tick, event.tf_i))) % (2**32))
            return perm_rng.permutation(weights)

    else:
        raise ValueError(f"unknown perturbation: {perturbation!r}")
    return compute_pit_values(
        events, analysis_rng_seed=analysis_rng_seed, weight_transform=_transform
    )


# --- Canonical, hash-bound evidence bundle -----------------------------------

_BUNDLE_ROOT = _REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "evidence_bundle"
_PROCESS_NAME = "TranscriptionalRegulation"
_OC_SOURCE_PATH = _REPO_ROOT / "opencell" / "vivarium" / "karr_transcriptional_regulation.py"


def write_evidence_bundle(
    *,
    trace_path: Path,
    result: PitResult,
    positive_controls: dict[str, PitResult] | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Write `result.json`/`input_manifest.json`/`provenance.json` for
    this gate, following the file-naming convention of
    `scripts/l22_evidence/schema.py`'s `REQUIRED_AUTHORITY_FILES` (see
    module docstring "Known scope boundary" for what this does NOT yet
    do: wire into that package's generic generator/verdict dispatch).
    `positive_controls` maps a perturbation label to its `PitResult`
    (see `run_positive_control`/`run_weight_law_positive_control`)."""
    output_dir = output_dir or (_BUNDLE_ROOT / _PROCESS_NAME / "latest_event")
    output_dir.mkdir(parents=True, exist_ok=True)

    trace_path = Path(trace_path)
    ledger_path = trace_path.with_suffix("").with_suffix(".chromosome_rand_stream_ledger.json")

    def _repo_relative_or_absolute(path: Path) -> str:
        try:
            return path.resolve().relative_to(_REPO_ROOT).as_posix()
        except ValueError:
            # Outside the repo root (e.g. a tmp_path-based unit test
            # fixture) -- absolute path is the only meaningful hint.
            return path.as_posix()

    input_manifest = {
        "process": _PROCESS_NAME,
        "trace_path": _repo_relative_or_absolute(trace_path),
        "trace_sha256": sha256_of_file(trace_path),
        "ledger_path": _repo_relative_or_absolute(ledger_path) if ledger_path.exists() else None,
        "ledger_sha256": sha256_of_file(ledger_path) if ledger_path.exists() else None,
        "ledger_note": (
            "Present for provenance completeness only -- this L2.2 gate's "
            "analysis never reads the ledger's contents (it derives "
            "candidates/weights from real states_before and winners from "
            "real states_after deltas, with no OC RNG replay of any kind); "
            "the ledger remains an L2.1-only mechanism."
        ),
        "n_seeds": 1,
        "cohort_status": "PILOT_ONLY_NOT_A_GATE_VERDICT",
    }
    provenance = {
        "process": _PROCESS_NAME,
        "generator_module": Path(__file__).resolve().relative_to(_REPO_ROOT).as_posix(),
        "generator_module_sha256": sha256_of_file(Path(__file__)),
        "oc_source_path": _OC_SOURCE_PATH.relative_to(_REPO_ROOT).as_posix(),
        "oc_source_sha256": sha256_of_file(_OC_SOURCE_PATH),
        "analysis_rng_seed": result.analysis_rng_seed,
        "method": (
            "Randomized PIT of Karr's real trace winners (states_after "
            "tfBoundPromoters/boundTFs deltas) under OC's real pre-tick "
            "candidate/post-mask-renormalized-weight law "
            "(candidate_sites_for_tf), pooled two-sided KS test against "
            "Uniform(0,1)."
        ),
    }
    result_payload: dict[str, Any] = {
        "process": _PROCESS_NAME,
        "verdict": "PILOT_ONLY_NOT_A_GATE_VERDICT",
        "n_events": result.n_events,
        "n_pooled_values": result.n_pooled_values,
        "ks_statistic": result.ks_statistic,
        "ks_pvalue": result.ks_pvalue,
        "mid_p_pit_values_descriptive_only": result.mid_p_pit_values,
        "randomized_pit_values": result.randomized_pit_values,
    }
    if positive_controls:
        result_payload["positive_controls"] = {
            label: {
                "n_events": pc.n_events,
                "n_pooled_values": pc.n_pooled_values,
                "ks_statistic": pc.ks_statistic,
                "ks_pvalue": pc.ks_pvalue,
            }
            for label, pc in positive_controls.items()
        }

    (output_dir / "input_manifest.json").write_text(
        json.dumps(input_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "result.json").write_text(
        json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_dir
