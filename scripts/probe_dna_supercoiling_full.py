"""DNASupercoiling tick-0 full-channel deep probe (using harness primitives)."""
from __future__ import annotations

import h5py
import numpy as np

from tests.vivarium.l2_2_replay_common_v2 import (
    _build_context,
    _build_counterfactual_step_vector,
    _project_trace_vector,
    resolve_trace_path,
)

PROCESS = "DNASupercoiling"
RNG_SEED = 0


def main() -> None:
    trace_path = resolve_trace_path(PROCESS)
    with h5py.File(str(trace_path), "r") as handle:
        ctx = _build_context(PROCESS, RNG_SEED, handle)
        spec = ctx.spec
        wids_by_obs = ctx.wids_by_observable

        print(f"=== {PROCESS} tick-0 full-channel deep probe (no-hints isolated) ===\n")
        print(f"observables: {spec.observables}")
        print(f"oracle_type: {spec.oracle_type}\n")

        for observable in spec.observables:
            wids = wids_by_obs.get(observable, [])
            karr_before = _project_trace_vector(ctx, "states_before", observable, 0)
            karr_after = _project_trace_vector(ctx, "states_after", observable, 0)
            karr_delta = karr_after - karr_before

            try:
                oc_after = _build_counterfactual_step_vector(
                    ctx=ctx,
                    tick=0,
                    observable=observable,
                    disable_trace_hints=True,
                    oracle_type=spec.oracle_type,
                )
            except Exception as e:
                print(f"\n--- {observable} ---")
                print(f"  ERROR building counterfactual: {type(e).__name__}: {e}")
                continue

            oc_delta = oc_after - karr_before
            diffs = oc_after - karr_after
            nz = np.where(np.abs(diffs) > 0.5)[0]

            print(f"\n--- {observable}  ({len(wids)} wids) ---")
            print(f"  karr sum:  before={karr_before.sum():.0f}  after={karr_after.sum():.0f}  delta={karr_delta.sum():+.0f}")
            print(f"  oc   sum:  before={karr_before.sum():.0f}  after={oc_after.sum():.0f}    delta={oc_delta.sum():+.0f}")
            print(f"  total |diff| = {abs(diffs).sum():.0f}, nonzero count = {len(nz)}")
            if len(nz) == 0:
                print(f"  -> CHANNEL MATCHES KARR")
                continue
            print(f"  top {min(15, len(nz))} diffs by |diff|:")
            for idx in sorted(nz, key=lambda i: -abs(diffs[i]))[:15]:
                w = wids[idx] if idx < len(wids) else f"<idx={idx}>"
                print(f"    [{idx:4d}]  {w:30s}  before={karr_before[idx]:8.0f}  karr_after={karr_after[idx]:8.0f}  oc_after={oc_after[idx]:8.0f}  diff={diffs[idx]:+.0f}  karr_delta={karr_delta[idx]:+.0f}  oc_delta={oc_delta[idx]:+.0f}")


if __name__ == "__main__":
    main()
