"""Diagnostic probe: ProteinFolding + ProteinTranslocation tick-21 divergence.

The L2.5 honest sweep flagged this pair with CAUSE_4 + 14 extra ATP hydrolyses
at tick 21, while:
  - isolated_replay_result: matches_oracle (Translocation alone is correct)
  - oc_counterfactual_compare: zeros (Translocation matches with Karr-injected state)

This probe runs the composition harness up to tick 21 with explicit state
dumps to identify which sub-state Translocation sees differently in
composition vs. counterfactual / isolated.

Usage:
    python scripts/probe_translocation_composition.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests" / "vivarium"))

from l2_2_replay_common_v2 import (  # type: ignore
    _PROCESS_SPECS,
    _build_context,
    _build_shared_state_template,
    _trace_hints_enabled,
    _project_trace_vector,
    overlay_observable_into_state,
    overlay_trace_after_hint,
    refresh_allocator_views,
    project_observable_from_state,
    resolve_trace_path,
)
from l2_replay_common import build_state_template, _OBS_STORE_PATHS  # type: ignore


PAIR = ["ProteinFolding", "ProteinTranslocation"]
TICK = 21
RNG_SEED = 0


def _project(name: str, trace_handle):
    """Resolve the per-process h5 trace handle and ctx for `name`."""
    spec = _PROCESS_SPECS[name]
    ctx = _build_context(name=name, rng_seed=RNG_SEED, handle=trace_handle)
    return ctx


def _peek(state: dict, *path: str):
    cur = state
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _summarize_dict(label: str, d, max_show: int = 6) -> None:
    if not isinstance(d, dict):
        print(f"  {label}: <not a dict, type={type(d).__name__}>")
        return
    nonzero = {k: v for k, v in d.items() if isinstance(v, (int, float)) and v != 0}
    print(f"  {label}: n_keys={len(d)}, n_nonzero={len(nonzero)}, "
          f"sum_nonzero={sum(nonzero.values()):.1f}")
    if nonzero:
        items = sorted(nonzero.items(), key=lambda kv: -abs(kv[1]))[:max_show]
        for k, v in items:
            print(f"    {k}: {v}")


def main() -> int:
    # The trace handle for each process is per-process; the composition
    # harness opens one handle per process.
    traces = {}
    for name in PAIR:
        spec = _PROCESS_SPECS[name]
        trace_path = resolve_trace_path(name)
        traces[name] = h5py.File(trace_path, "r")

    contexts = {name: _build_context(name=name, rng_seed=RNG_SEED, handle=traces[name])
                for name in PAIR}

    # Mirror harness ordering. Lookup based on _COMPOSITION_ORDER_V2.
    from l2_2_replay_common_v2 import _COMPOSITION_ORDER_V2
    under_test_set = set(PAIR)
    ordered = [n for n in _COMPOSITION_ORDER_V2 if n in under_test_set]
    print(f"Composition order: {ordered}")

    shared_state = _build_shared_state_template(ordered=ordered, contexts=contexts)

    print(f"\n=== TICK {TICK} pre-overlay shared state ===")
    print("Translocation reads from:")
    _summarize_dict("protein.counts", _peek(shared_state, "protein", "counts"))
    _summarize_dict("protein.unprocessed_counts", _peek(shared_state, "protein", "unprocessed_counts"))
    _summarize_dict("protein.enzyme_counts", _peek(shared_state, "protein", "enzyme_counts"))
    _summarize_dict("protein.location", _peek(shared_state, "protein", "location"))
    _summarize_dict("complex.counts", _peek(shared_state, "complex", "counts"))

    # Apply per-process overlays at TICK
    print(f"\n=== TICK {TICK} per-process overlay phase ===")
    before_vectors: dict[str, dict[str, np.ndarray]] = {}
    for name in ordered:
        ctx = contexts[name]
        bv = {obs: _project_trace_vector(ctx, "states_before", obs, TICK)
              for obs in ctx.spec.observables}
        before_vectors[name] = bv
        print(f"\n-- {name} states_before at tick {TICK} --")
        for obs, vec in bv.items():
            nonzero = np.count_nonzero(vec)
            print(f"  {obs}: shape={vec.shape}, nonzero={nonzero}, sum={vec.sum():.1f}")

    # Overlay each in order
    for name in ordered:
        ctx = contexts[name]
        for obs in ctx.spec.observables:
            overlay_observable_into_state(
                process=ctx.process,
                state=shared_state,
                observable=obs,
                vector=before_vectors[name][obs],
                wids=ctx.wids_by_observable[obs],
                store_path_override=ctx.spec.store_path_override,
            )

        print(f"\n=== After {name} overlay (before its next_update) ===")
        if name == "ProteinTranslocation":
            _summarize_dict("protein.counts", _peek(shared_state, "protein", "counts"))
            _summarize_dict("protein.unprocessed_counts",
                            _peek(shared_state, "protein", "unprocessed_counts"))
            _summarize_dict("protein.enzyme_counts",
                            _peek(shared_state, "protein", "enzyme_counts"))
            _summarize_dict("protein.location", _peek(shared_state, "protein", "location"))
            _summarize_dict("complex.counts", _peek(shared_state, "complex", "counts"))
            substrates = _peek(shared_state, "substrates_allocated", "karr_protein_translocation")
            _summarize_dict("substrates_allocated[translocation]", substrates)

        refresh_allocator_views(ctx.process, shared_state)
        update = ctx.process.next_update(1.0, shared_state)

        print(f"\n=== {name}.next_update output at tick {TICK} ===")
        if isinstance(update, dict):
            for k, v in update.items():
                if isinstance(v, dict):
                    sub_summary = {kk: vv for kk, vv in v.items()
                                   if isinstance(vv, (int, float)) and vv}
                    if isinstance(list(v.values())[0] if v else None, dict):
                        # nested
                        for kk, vv in v.items():
                            if isinstance(vv, dict):
                                nonzero_inner = {kkk: vvv for kkk, vvv in vv.items()
                                                 if isinstance(vvv, (int, float)) and vvv}
                                print(f"  {k}.{kk}: nonzero={len(nonzero_inner)} items, "
                                      f"sum={sum(nonzero_inner.values()):.1f}")
                                if 0 < len(nonzero_inner) <= 12:
                                    for kkk, vvv in nonzero_inner.items():
                                        print(f"    {kkk}: {vvv}")
                            else:
                                print(f"  {k}.{kk}: {vv}")
                    else:
                        print(f"  {k}: nonzero={len(sub_summary)} items, "
                              f"sum={sum(sub_summary.values()):.1f}")
                        if 0 < len(sub_summary) <= 12:
                            for kk, vv in sub_summary.items():
                                print(f"    {kk}: {vv}")
                else:
                    print(f"  {k}: {v}")

        # Apply the update (manually mirror the harness)
        from l2_2_replay_common_v2 import _apply_update
        _apply_update(shared_state, update)

    # Now compare what Karr expected
    print(f"\n=== Karr expected deltas at tick {TICK} ===")
    for name in ordered:
        ctx = contexts[name]
        print(f"\n-- {name} --")
        for obs in ctx.spec.observables:
            before = _project_trace_vector(ctx, "states_before", obs, TICK)
            after = _project_trace_vector(ctx, "states_after", obs, TICK)
            delta = after - before
            nz = np.count_nonzero(delta)
            print(f"  {obs}: delta nonzero={nz}, sum_delta={delta.sum():.1f}, "
                  f"max_abs={np.abs(delta).max():.1f}")
            if 0 < nz <= 10:
                wids = ctx.wids_by_observable[obs]
                for i in np.flatnonzero(delta).tolist():
                    print(f"    {wids[i]}: {delta[i]:+.0f}")

    for h in traces.values():
        h.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
