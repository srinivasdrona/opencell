"""Corpus/production-path regression for the `joinSplitOverOriCRegions`
fix (Opus's second review of the DNAS audit-boundary-closure wave).

The unit-level tests
(`test_matlab_join_split_over_oric_regions_reproduces_real_matlab_wrap_join`,
`test_accessible_binding_regions_join_split_over_oric_wrapped_fragment`,
`tests/vivarium/test_karr_dna_supercoiling.py`) prove the fix is correct
on hand-constructed, live-MATLAB-verified inputs. This script goes
further: it instruments `_accessible_binding_regions` through the REAL
production driver (`_run_dna_supercoiling_tick`, the persistent per-seed
process pool used by the frozen `N=200` gate itself) across a real,
frozen-trace-driven seed/tick range, capturing every call's
`(enzyme_idx, positive_regions) -> accessible-region output`, plus the
resulting `complexBoundSites` positions at the end of every tick.

It then compares the CURRENT (fixed) code's output against what the code
would have produced WITHOUT the `joinSplitOverOriCRegions` fix (via a
module-level monkeypatch of `_matlab_join_split_over_oric_regions` to the
identity function, matching the prior Session-5 omission at BOTH real
call sites), reporting any accessible-region divergence and any
resulting `complexBoundSites` position divergence.

Default scope (seeds 0-3 x ticks 0-99, 325 accessible-region calls, 400
seed/tick complexBoundSites snapshots) independently reproduces Opus's
own reported instrumentation counts (7/325 accessible-region divergences,
6/400 changed complexBoundSites positions) -- confirming this script's
methodology matches the review's own investigation, not merely opencell's
self-report.

Usage:
    bin\\oc-py.cmd scripts/l22_dnas_oric_join_corpus_regression.py \\
        --seeds 0,1,2,3 --n-ticks 100 \\
        --out-path tmp/l22_dnas_oric_join_corpus_regression.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

import h5py  # noqa: E402

import _l2_2_design_a_runner_helpers as helpers  # noqa: E402
import _l2_2_dnas_runner_helpers as dnas_runner_helpers  # noqa: E402
from opencell.vivarium import karr_dna_supercoiling as dnas_mod  # noqa: E402
from scripts.l22_dnas_sept2_two_sided_n200_eval import (  # noqa: E402
    DEFAULT_TRACE_ROOT,
    _coerce_cli_path,
    _seed_trace_path,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="0,1,2,3", help="Comma-separated seed list.")
    parser.add_argument("--n-ticks", type=int, default=100)
    parser.add_argument(
        "--out-path",
        default="tmp/l22_dnas_oric_join_corpus_regression.json",
    )
    return parser.parse_args(argv)


def _run_pass(
    *,
    seeds: list[int],
    n_ticks: int,
    trace_root: Path,
    accessible_orig,
    accessible_sink: list[dict],
    positions_sink: dict[tuple[int, int], list],
    label: str,
) -> None:
    def capture(self, *, store, enzyme_idx, positive_regions):
        result = accessible_orig(self, store=store, enzyme_idx=enzyme_idx, positive_regions=positive_regions)
        accessible_sink.append(
            {
                "seed": int(self._rng_seed),  # noqa: SLF001
                "tick": int(self._tick_index),  # noqa: SLF001
                "enzyme_idx": int(enzyme_idx),
                "positive_regions": list(positive_regions),
                "result": list(result),
            }
        )
        return result

    dnas_mod.KarrDNASupercoilingProcess._accessible_binding_regions = capture  # noqa: SLF001
    dnas_runner_helpers.reset_dna_supercoiling_persistent_processes()
    try:
        for seed in seeds:
            path = _seed_trace_path(trace_root, seed)
            with h5py.File(path, "r") as trace:
                before_substrates = helpers._matlab_channel_matrix(trace, trace["states_before/substrates"])  # noqa: SLF001
                before_enzymes = helpers._matlab_channel_matrix(trace, trace["states_before/enzymes"])  # noqa: SLF001
                before_bound = helpers._matlab_channel_matrix(trace, trace["states_before/boundEnzymes"])  # noqa: SLF001
                probe_process = helpers._dna_supercoiling_process(seed)  # noqa: SLF001
                substrate_wids = list(probe_process.substrate_wids)
                enzyme_wids = list(probe_process.enzyme_wids)

                for tick in range(n_ticks):
                    before_store = helpers._chromosome_store_at(trace, "states_before", tick)  # noqa: SLF001
                    sample_state = {
                        "substrate_wids": substrate_wids,
                        "enzyme_wids": enzyme_wids,
                        "oracle_before_substrates": before_substrates[tick],
                        "oracle_before_enzymes": before_enzymes[tick],
                        "oracle_before_bound_enzymes": before_bound[tick],
                        "oracle_before_chromosome_store": before_store,
                    }
                    oc_result = dnas_runner_helpers.run_dna_supercoiling_tick(seed, tick, sample_state)
                    after_store = oc_result["chromosome_after_store"]
                    triplet = after_store.get_field("complexBoundSites")
                    positions_sink[(seed, tick)] = sorted(
                        zip(triplet.positions.tolist(), triplet.strands.tolist(), triplet.values.tolist())
                    )
            print(f"[{label} pass] seed {seed} done")
    finally:
        dnas_mod.KarrDNASupercoilingProcess._accessible_binding_regions = accessible_orig  # noqa: SLF001


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    trace_root = _coerce_cli_path(DEFAULT_TRACE_ROOT).resolve()

    accessible_orig = dnas_mod.KarrDNASupercoilingProcess._accessible_binding_regions  # noqa: SLF001

    accessible_fixed: list[dict] = []
    positions_fixed: dict[tuple[int, int], list] = {}
    _run_pass(
        seeds=seeds,
        n_ticks=args.n_ticks,
        trace_root=trace_root,
        accessible_orig=accessible_orig,
        accessible_sink=accessible_fixed,
        positions_sink=positions_fixed,
        label="fixed",
    )
    print(
        f"Fixed pass: {len(accessible_fixed)} accessible-region calls captured "
        f"across {len(seeds)} seeds x {args.n_ticks} ticks"
    )

    # Reverted (pre-fix) pass: monkeypatch `_matlab_join_split_over_oric_regions`
    # to the identity function, matching the Session-5 omission at BOTH real
    # call sites inside `_matlab_exclude_regions`.
    orig_oric_join = dnas_mod._matlab_join_split_over_oric_regions  # noqa: SLF001
    dnas_mod._matlab_join_split_over_oric_regions = lambda regions, *, chromosome_length: list(regions)  # noqa: SLF001

    accessible_reverted: list[dict] = []
    positions_reverted: dict[tuple[int, int], list] = {}
    try:
        _run_pass(
            seeds=seeds,
            n_ticks=args.n_ticks,
            trace_root=trace_root,
            accessible_orig=accessible_orig,
            accessible_sink=accessible_reverted,
            positions_sink=positions_reverted,
            label="reverted",
        )
    finally:
        dnas_mod._matlab_join_split_over_oric_regions = orig_oric_join  # noqa: SLF001
    print(f"Reverted pass: {len(accessible_reverted)} accessible-region calls captured")

    accessible_divergences = [
        {
            "seed": fixed["seed"],
            "tick": fixed["tick"],
            "enzyme_idx": fixed["enzyme_idx"],
            "positive_regions": fixed["positive_regions"],
            "fixed_result": fixed["result"],
            "reverted_result": reverted["result"],
        }
        for fixed, reverted in zip(accessible_fixed, accessible_reverted, strict=True)
        if fixed["result"] != reverted["result"]
    ]

    position_divergences = [
        {
            "seed": key[0],
            "tick": key[1],
            "fixed_positions": positions_fixed[key],
            "reverted_positions": positions_reverted.get(key),
        }
        for key in positions_fixed
        if positions_fixed[key] != positions_reverted.get(key)
    ]

    print(f"\nTOTAL accessible-region calls compared: {len(accessible_fixed)}")
    print(f"Accessible-region divergences (fixed vs reverted): {len(accessible_divergences)}")
    print(f"complexBoundSites position divergences (fixed vs reverted): {len(position_divergences)}")

    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "seeds": seeds,
                "n_ticks": args.n_ticks,
                "n_accessible_calls": len(accessible_fixed),
                "n_accessible_divergences": len(accessible_divergences),
                "n_position_divergences": len(position_divergences),
                "accessible_divergences": accessible_divergences,
                "position_divergences": position_divergences,
            },
            indent=2,
        )
    )
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
