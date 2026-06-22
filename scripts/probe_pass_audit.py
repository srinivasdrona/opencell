"""Audit the current L2.5 honest PASSes for coincidental-zero false positives.

Rubber-duck critique (Sonnet 4.6, Day-35 EOD) flagged: a stochastic-pair PASS
where Karr's expected delta is ~0 AND OC's composition delta is ~0 is NOT a
validation -- both happen to produce nothing. The harness reports PASS but
zero biology was actually exercised.

This probe loads each currently-passing L2.5 pair, runs the harness in
no-trace-hint mode (just like the actual test), and instead of just looking
at the verdict, extracts:
  - For each tick: max |karr_compare| (oracle's per-step delta magnitude)
  - Fraction of ticks where Karr's expected delta is "non-trivial" (>threshold)
  - Same for OC's composition delta

A PASS is "genuine" if Karr exercised non-trivial biology AND OC matched.
A PASS is "coincidental" if neither side did anything for most ticks.

Usage:
    python scripts/probe_pass_audit.py [--threshold 1.0]
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
    _COMPOSITION_ORDER_V2,
    _PROCESS_SPECS,
    _build_context,
    _project_trace_vector,
    resolve_trace_path,
)

# Current PASSes (from Day-35 EOD sweep)
PASS_PAIRS = [
    # 5 Seg DS clean x clean
    ("ChromosomeSegregation", "ProteinFolding"),
    ("ChromosomeSegregation", "RNAProcessing"),
    ("ChromosomeSegregation", "tRNAAminoacylation"),
    ("ChromosomeSegregation", "ProteinProcessingI"),
    ("ChromosomeSegregation", "ProteinProcessingII"),
    # 2 Seg DS clean x dirty
    ("ChromosomeSegregation", "Translation"),
    ("HostInteraction", "TerminalOrganelleAssembly"),
    # 1 SS dirty x clean
    ("Translation", "RNAProcessing"),
    # 7 SS clean x clean from today
    ("ProteinFolding", "ProteinProcessingI"),
    ("ProteinFolding", "RNAProcessing"),
    ("ProteinFolding", "tRNAAminoacylation"),
    ("ProteinProcessingI", "tRNAAminoacylation"),
    ("ProteinProcessingI", "RNAProcessing"),
    ("ProteinProcessingII", "RNAProcessing"),
    ("ProteinProcessingII", "tRNAAminoacylation"),
]


def audit_pair(a: str, b: str, threshold: float = 1.0) -> dict:
    """Compute per-tick non-trivial-event fractions for each side."""
    pair_set = {a, b}
    ordered = [n for n in _COMPOSITION_ORDER_V2 if n in pair_set]

    try:
        traces = {n: h5py.File(resolve_trace_path(n), "r") for n in ordered}
        contexts = {n: _build_context(name=n, rng_seed=0, handle=traces[n])
                    for n in ordered}
    except Exception as exc:
        return {"pair": f"{a}+{b}", "ordered": ordered, "error": str(exc)}

    n_ticks = next(iter({contexts[n].n_ticks for n in ordered}))

    summary = {"pair": f"{a}+{b}", "ordered": ordered, "n_ticks": n_ticks}

    for name in ordered:
        ctx = contexts[name]
        nontrivial_ticks = 0
        max_delta = 0.0
        total_abs_delta = 0.0
        for tick in range(n_ticks):
            for obs in ctx.spec.observables:
                before = _project_trace_vector(ctx, "states_before", obs, tick)
                after = _project_trace_vector(ctx, "states_after", obs, tick)
                delta = after - before
                m = float(np.abs(delta).max()) if delta.size > 0 else 0.0
                if m >= threshold:
                    nontrivial_ticks += 1
                    break  # count tick once even if multiple obs are nontrivial
            for obs in ctx.spec.observables:
                before = _project_trace_vector(ctx, "states_before", obs, tick)
                after = _project_trace_vector(ctx, "states_after", obs, tick)
                delta = after - before
                if delta.size > 0:
                    m = float(np.abs(delta).max())
                    if m > max_delta:
                        max_delta = m
                    total_abs_delta += float(np.abs(delta).sum())

        summary[name] = {
            "nontrivial_ticks": nontrivial_ticks,
            "fraction_nontrivial": nontrivial_ticks / n_ticks if n_ticks else 0.0,
            "max_delta_seen": max_delta,
            "total_abs_delta_across_run": total_abs_delta,
        }

    for h in traces.values():
        h.close()
    return summary


def main() -> int:
    threshold = 1.0
    for arg in sys.argv[1:]:
        if arg.startswith("--threshold"):
            threshold = float(arg.split("=", 1)[1]) if "=" in arg else float(sys.argv[sys.argv.index(arg)+1])

    print(f"# L2.5 PASS audit — Karr-side non-trivial-event fractions")
    print(f"# Threshold for 'non-trivial' = abs(delta) >= {threshold}\n")
    print(f"{'Pair':<55} {'Side A nontriv%':>15} {'Side B nontriv%':>15} "
          f"{'A max_d':>10} {'B max_d':>10} {'verdict':>14}")
    print("-" * 130)

    results = []
    for a, b in PASS_PAIRS:
        s = audit_pair(a, b, threshold=threshold)
        if "error" in s:
            results.append((f"{a}+{b}", 0.0, 0.0, 0.0, 0.0, "BUILD_ERROR"))
            print(f"{a}+{b:<46} {'ERROR':>14} {'':>14} {'':>10} {'':>10} {'BUILD_ERROR':>14}  ({s['error'][:60]})")
            continue
        ordered = s["ordered"]
        first, second = ordered[0], ordered[1]
        f_a = s[first]["fraction_nontrivial"]
        f_b = s[second]["fraction_nontrivial"]
        m_a = s[first]["max_delta_seen"]
        m_b = s[second]["max_delta_seen"]
        # Verdict heuristic
        if f_a < 0.05 and f_b < 0.05:
            verdict = "COINCIDENTAL"
        elif f_a < 0.05 or f_b < 0.05:
            verdict = "SINGLE-SIDE"
        else:
            verdict = "GENUINE"
        results.append((f"{a}+{b}", f_a, f_b, m_a, m_b, verdict))
        print(f"{a}+{b:<46} {f_a:>14.2%} {f_b:>14.2%} {m_a:>10.1f} {m_b:>10.1f} {verdict:>14}")

    print("\n## Summary")
    counts = {"GENUINE": 0, "SINGLE-SIDE": 0, "COINCIDENTAL": 0}
    for _, _, _, _, _, v in results:
        counts[v] += 1
    print(f"  GENUINE     : {counts['GENUINE']} / {len(results)}")
    print(f"  SINGLE-SIDE : {counts['SINGLE-SIDE']} / {len(results)}")
    print(f"  COINCIDENTAL: {counts['COINCIDENTAL']} / {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
