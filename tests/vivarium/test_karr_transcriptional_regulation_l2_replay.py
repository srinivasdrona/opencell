from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import chromosome_rand_stream_ledger as _shared_ledger
from l2_replay_common import (
    apply_count_update,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
    resolve_trace_path,
)
from l2_replay_common import (
    assert_delta_integral as _assert_delta_integral_shared,
)
from l2_replay_common import (
    assert_identity_or_tolerance as _assert_identity_or_tolerance_shared,
)
from l2_replay_common import (
    audit_trace_mutated_ticks as _audit_trace_mutated_ticks_shared,
)

from opencell.state.chromosome_store import ChromosomeStore
from opencell.util.txreg_mcg_rand import TxRegChromosomeLedgerRandStream
from opencell.vivarium.karr_transcriptional_regulation import KarrTranscriptionalRegulationProcess

_TRACE_PROCESS_NAME = "TranscriptionalRegulation"

# `tfBoundPromoters` (site x chromosome-copy, 34 elements = 17 sites x 2
# copies) and `boundTFs` (per-TF bound-copy count, 5 elements, column-0
# occupancy only) are the genuine Karr-native surfaces this L2.1 gap closes.
# `substrates` stays pass-through: this process never writes it (Karr's
# TranscriptionalRegulation has no substrate stoichiometry).
#
# The older canonical 100-tick trace
# (`per_process_traces_v2/TranscriptionalRegulation_100ticks.mat`) predates
# the site-level extractor and only carries `substrates`/`enzymes`/
# `boundEnzymes`; the genuine active-window event trace
# (`per_process_traces_v2_event_s000/TranscriptionalRegulation_4000ticks.mat`)
# carries the full set including `tfBoundPromoters`/`boundTFs`/`chromosome`.
# `_observables_for_trace` intersects this superset with whatever the
# specific trace actually exposes, so both traces replay against every
# observable they are capable of proving.
_FULL_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes", "tfBoundPromoters", "boundTFs")

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance). `enzymes`/`boundEnzymes`/`tfBoundPromoters`/`boundTFs` are now
# genuinely mutated observables (real site-level binding decisions), not
# pass-through -- this is the literal fix for the CODE_GAP (previously
# `enzymes`/`boundEnzymes` deltas were fabricated from an oracle hint, and
# `tfBoundPromoters`/`boundTFs` were not tracked at all).
_PASS_THROUGH = frozenset({"substrates"})

# Rule 4b manifest: the process's TxRegMcgRandStream (mcg16807, matching
# Karr's Process.m:283 `this.randStream = RandStream('mcg16807')`) is
# Karr-persistent (the
# MATLAB `this.randStream` advances continuously across ticks; the test must
# NOT reset it between ticks). No other mutable process attribute is written
# by `next_update` or its callees.
_SCRATCH_RESET = {"_rng": "karr-persistent"}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
    "tfBoundPromoters": "tf_bound_promoters_wids",
    "boundTFs": "enzyme_wids",
}


def _observables_for_trace(trace: h5py.File) -> tuple[str, ...]:
    available = set(trace.get("states_before", {}).keys()) & set(trace.get("states_after", {}).keys())
    return tuple(obs for obs in _FULL_OBSERVABLES if obs in available)


# `tfBoundPromoters`/`boundTFs` are new Karr-native ports
# (`tf_bound_promoters`, `bound_tfs`) with no entry in the shared
# `l2_replay_common._OBS_STORE_PATHS` table (that table is shared across
# every process's L2.1 test; adding process-specific names there would
# widen blast radius unnecessarily). Scoped locally instead.
_TR_STORE_PATH_OVERRIDE: dict[str, tuple[str, ...]] = {
    "tfBoundPromoters": ("tf_bound_promoters",),
    "boundTFs": ("bound_tfs",),
}


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _chromosome_store_for_tick(trace: h5py.File, group: str, tick: int) -> ChromosomeStore:
    dataset = trace[f"{group}/chromosome"]
    ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
    return ChromosomeStore.from_hdf5_group(trace[ref])


def _overlay_chromosome_state(state: dict[str, object], store: ChromosomeStore) -> None:
    chrom_state = state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be a dict")
    chrom_state["polymerizedRegions"] = store.get_field("polymerizedRegions").to_state()
    chrom_state["monomerBoundSites"] = store.get_field("monomerBoundSites").to_state()
    chrom_state["complexBoundSites"] = store.get_field("complexBoundSites").to_state()


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    del process  # state is rebuilt per tick; only delta application is needed here.
    for label, deltas in collect_count_delta_dicts(update):
        _assert_delta_integral(label, deltas)
    apply_count_update(state, update)

    # `tf_bound_promoters`: accumulate-latch (site is bound at most once;
    # `next_update` never unbinds).
    tf_bp_delta = update.get("tf_bound_promoters")
    if isinstance(tf_bp_delta, dict) and tf_bp_delta:
        _assert_delta_integral("tf_bound_promoters", {k: float(v) for k, v in tf_bp_delta.items()})
        store = state.setdefault("tf_bound_promoters", {})
        if not isinstance(store, dict):
            raise TypeError("state['tf_bound_promoters'] must be a dict")
        for wid, delta in tf_bp_delta.items():
            store[wid] = float(store.get(wid, 0.0)) + float(delta)

    # `bound_tfs` / `tf_binding` / `tx_rate_fold_change`: "set" updater --
    # recomputed fresh every tick from the just-updated site occupancy
    # (Karr's `boundTFs` and `calcBindingProbabilityFoldChange` are
    # dependent/getter properties, never independently-accumulated state).
    if "bound_tfs" in update:
        state["bound_tfs"] = dict(update["bound_tfs"])
    if "tf_binding" in update:
        state["tf_binding"] = {tf: dict(per_tu) for tf, per_tu in update["tf_binding"].items()}
    if "tx_rate_fold_change" in update:
        state["tx_rate_fold_change"] = dict(update["tx_rate_fold_change"])


def _audit_trace_mutated_ticks(
    trace: h5py.File,
    observables: tuple[str, ...],
    n_ticks: int,
) -> dict[str, int]:
    return _audit_trace_mutated_ticks_shared(trace, observables, n_ticks)


def _assert_identity_or_tolerance(
    *,
    tick: int,
    observable: str,
    oc_after: np.ndarray,
    karr_after: np.ndarray,
) -> None:
    _assert_identity_or_tolerance_shared(
        tick=tick,
        observable=observable,
        oc_after=oc_after,
        karr_after=karr_after,
    )


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_transcriptional_regulation_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        if "metadata" in trace and "rng_seed" in trace["metadata"]:
            recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
            assert int(rng_seed) == recorded_seed

        observables = _observables_for_trace(trace)
        # Quiet-process guard: do not skip. Karr trace may be no-op across all
        # mutated observables, but we still want to assert OC's next_update is
        # also no-op (else OC silently drifting would never be caught).
        mutated_obs = tuple(o for o in observables if o not in _PASS_THROUGH)
        _ = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)

        _run_replay(trace, n_ticks, int(rng_seed))


def _bootstrap_tf_bound_promoters_vector(rng_seed: int) -> np.ndarray | None:
    """Ground-truth initial site occupancy for traces that predate the
    site-level extractor (the canonical 100-tick trace has no
    `tfBoundPromoters` channel at all).

    Karr initializes TF-promoter occupancy once, before the tick loop, via
    `initializeState -> evolveState -> bindTranscriptionFactors` (see the
    class docstring "Initialization" section); this initial occupancy is
    identical across every extraction of the same underlying cell state
    (verified: the canonical 100-tick trace's `enzymes`/`boundEnzymes`
    tick-0 `states_before` values -- [35,0,0,0,8] / [1,0,0,0,2] -- are
    bit-identical to the genuine active-window event trace's tick-0
    `states_before` values for the same seed). Since this process has no
    t=0 pre-binding of its own (disclosed reduction, see module docstring),
    the harness bootstraps the same real, oracle-sourced initial occupancy
    the event trace records, rather than replaying from a fabricated
    all-unbound start that would spuriously "discover" and bind sites Karr
    had already bound before the recorded window began. This is harness-side
    ground truth (real Karr data), not a fabricated shortcut -- the
    production process itself performs no such bootstrap and starts from
    zero occupancy in the actual chassis (see module docstring).
    """
    event_path = _resolve_event_trace_path(rng_seed)
    if not event_path.exists():
        return None
    with h5py.File(event_path, "r") as event_trace:
        if "tfBoundPromoters" not in event_trace.get("states_before", {}):
            return None
        return cell_vector(event_trace, "states_before", "tfBoundPromoters", 0)


def _load_chromosome_rand_stream_ledger(trace_path: Path) -> list[list[float]] | None:
    """Thin, worktree-bound wrapper around the shared
    `chromosome_rand_stream_ledger.load_chromosome_rand_stream_ledger`
    (see that module for the full hash-binding/fail-closed contract and
    the 2026-09-05 corrective-fix history, Opus review point 2: single RAW
    hash convention, fail-closed on unresolved source path/missing hash
    field, portable WSL source resolution). Kept as a same-named local
    wrapper so existing call sites in this file don't all need to thread
    `repo_root=` through individually."""
    return _shared_ledger.load_chromosome_rand_stream_ledger(trace_path, repo_root=_REPO_ROOT)


def _run_replay(
    trace: h5py.File,
    n_ticks: int,
    rng_seed: int,
    *,
    chromosome_rand_stream_ledger: list[list[float]] | None = None,
) -> None:
    """Shared per-tick L2.1 bit-identity replay body (used by the standard and
    event-window tests). Assumes the trace is open and has been audited as active."""
    if chromosome_rand_stream_ledger is not None:
        assert len(chromosome_rand_stream_ledger) == n_ticks, (
            f"chromosome_rand_stream_state ledger has {len(chromosome_rand_stream_ledger)} ticks, "
            f"trace has n_ticks={n_ticks}"
        )

    process = KarrTranscriptionalRegulationProcess({"rng_seed": int(rng_seed)})
    state_template = build_state_template(process)
    observables = _observables_for_trace(trace)

    has_chromosome_trace = (
        "chromosome" in trace.get("states_before", {}) and "chromosome" in trace.get("states_after", {})
    )
    bootstrap_tf_bound_promoters = None
    if "tfBoundPromoters" not in observables:
        bootstrap_tf_bound_promoters = _bootstrap_tf_bound_promoters_vector(rng_seed)

    wids_by_observable: dict[str, list[str]] = {}
    for observable in observables:
        karr_before = cell_vector(trace, "states_before", observable, 0)
        explicit_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable)
        wids_by_observable[observable] = infer_wids_for_observable(
            process,
            state_template,
            observable,
            karr_len=int(karr_before.shape[0]),
            explicit_attr=explicit_attr,
        )
    if bootstrap_tf_bound_promoters is not None:
        wids_by_observable["tfBoundPromoters"] = list(process.tf_bound_promoters_wids)

    for tick in range(n_ticks):
        state = build_state_template(process)
        before_vectors = {
            observable: cell_vector(trace, "states_before", observable, tick)
            for observable in observables
        }
        after_vectors = {
            observable: cell_vector(trace, "states_after", observable, tick)
            for observable in observables
        }

        for observable in observables:
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=before_vectors[observable],
                wids=wids_by_observable[observable],
                store_path_override=_TR_STORE_PATH_OVERRIDE,
            )
        if bootstrap_tf_bound_promoters is not None:
            overlay_observable_into_state(
                process=process,
                state=state,
                observable="tfBoundPromoters",
                vector=bootstrap_tf_bound_promoters,
                wids=wids_by_observable["tfBoundPromoters"],
                store_path_override=_TR_STORE_PATH_OVERRIDE,
            )
        if has_chromosome_trace:
            before_chrom_store = _chromosome_store_for_tick(trace, "states_before", tick)
            _overlay_chromosome_state(state, before_chrom_store)
        refresh_allocator_views(process, state)

        ledger_stream = None
        if chromosome_rand_stream_ledger is not None:
            ledger_stream = TxRegChromosomeLedgerRandStream(
                chromosome_rand_stream_ledger[tick], tick_label=f"tick{tick}"
            )
            # Karr's real site-sampling draws for THIS tick come from the
            # shared Chromosome.randStream at exactly the position
            # captured in states_before/after -- not from a
            # freshly-seeded stand-in carried over from the previous tick
            # (that stream cannot be advanced correctly across ticks
            # anyway, since ~27 OTHER processes' draws happen in between;
            # see STATUS_L21_TXREG_ACTIVE_FIX.md). `_rng` (this process's
            # OWN, genuinely isolated, currently-unused stream) is left
            # untouched.
            process._chromosome_rng = ledger_stream  # noqa: SLF001

        update = process.next_update(1.0, state)
        _apply_update(state, update, process)

        if ledger_stream is not None:
            ledger_stream.assert_fully_consumed()

        for observable in observables:
            karr_after = after_vectors[observable]
            expected_len = len(wids_by_observable[observable])
            if karr_after.shape[0] != expected_len:
                mapped_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable, "<heuristic>")
                pytest.fail(
                    "L2a wid-length drift: "
                    f"tick={tick}, observable={observable}, "
                    f"karr_len={karr_after.shape[0]}, "
                    f"mapped_len={expected_len}, mapped_attr={mapped_attr}"
                )

            oc_after = project_observable_from_state(
                process=process,
                state=state,
                observable=observable,
                wids=wids_by_observable[observable],
                bound_enzymes_before=before_vectors.get("boundEnzymes"),
                store_path_override=_TR_STORE_PATH_OVERRIDE,
            )
            _assert_identity_or_tolerance(
                tick=tick,
                observable=observable,
                oc_after=oc_after,
                karr_after=karr_after,
            )


def _resolve_event_trace_path(seed: int) -> Path:
    """Resolve the event-window trace path for TranscriptionalRegulation (fixed
    4000-tick window; TR is quiescent in the standard 100-tick canonical trace)."""
    rel = Path(
        f"data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/TranscriptionalRegulation_4000ticks.mat"
    )
    candidates = [_REPO_ROOT / rel, Path("E:/opencell") / rel, Path("/mnt/e/opencell") / rel]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


@pytest.mark.parametrize("rng_seed", [0], ids=["event_seed_0"])
def test_karr_transcriptional_regulation_l2_event_replay(rng_seed: int) -> None:
    """L2 replay on the genuine active-window event trace (4000 ticks).
    TranscriptionalRegulation shows no boundTFs/tfBoundPromoters deltas in
    the first 100 ticks of the canonical trace; this fixed 4000-tick window
    gives TF binding kinetics enough simulated time to actually exercise
    binding (56 active ticks observed in the accepted seed-0 trace).

    Loads the companion `chromosome_rand_stream_state` ledger
    (`scripts/matlab/reconstruct_chromosome_draw_ledger.m`) if present and
    passes it through to `_run_replay`, restoring the SHARED
    `Chromosome.randStream`'s exact per-tick input state (see
    STATUS_L21_TXREG_ACTIVE_FIX.md's "shared-chromosome-RNG" finding) --
    falls back to the pre-existing freshly-seeded stand-in stream only if
    the ledger sidecar is absent (an older re-extraction of this trace)."""
    trace_path = _resolve_event_trace_path(rng_seed)
    if not trace_path.exists():
        pytest.skip(f"Event-window trace not found: {trace_path}")

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 4000

        mutated_obs = tuple(o for o in _observables_for_trace(trace) if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                f"Event-window trace seed {rng_seed} has no events. "
                f"Per-observable counts: {mutated_tick_counts}."
            )

        chromosome_rand_stream_ledger = _load_chromosome_rand_stream_ledger(trace_path)
        _run_replay(trace, n_ticks, int(rng_seed), chromosome_rand_stream_ledger=chromosome_rand_stream_ledger)

