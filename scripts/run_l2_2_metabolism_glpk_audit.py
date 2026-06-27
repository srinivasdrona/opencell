"""Day-40: re-run L2.2 Metabolism design-A audit with solver='glpk'.

Day-37 baseline (HiGHS): W1=171.39 on substrates -> VERIFIED_FAIL.
Day-40 expectation (GLPK): probe estimated 38% writeback L1 reduction;
W1 should drop substantially. Threshold for PASS depends on bootstrap.

Mirrors the Day-37 audit invocation pattern (probe_l2_2_strict_audit.py).
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from l2_2_design_a_runner import run_design_a

OUT_DIR = REPO / "tmp" / "l2_2_metabolism_glpk"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Match Day-37 baseline: 50 seeds x 10 ticks
SEEDS = list(range(50))
M_TICKS = 10

print(f"Running L2.2 Metabolism audit with solver='glpk' on {len(SEEDS)} seeds x {M_TICKS} ticks")
print(f"Output dir: {OUT_DIR}")
print()

payload = run_design_a(
    process="Metabolism",
    seeds=SEEDS,
    m_ticks=M_TICKS,
    out_dir=OUT_DIR,
    bootstrap_B=128,  # default
)

# Save full payload for inspection
(OUT_DIR / "payload.json").write_text(json.dumps(payload, default=str, indent=2))

result = payload.get("result", {})
verdict = result.get("verdict", "UNKNOWN")
warnings = result.get("warnings", [])
channels = result.get("channels", {})

print("=" * 70)
print("RESULT (Day-40 GLPK run)")
print("=" * 70)
print(f"  verdict: {verdict}")
print()
print("Per-channel summary:")
for ch_name, ch in channels.items():
    ch_verdict = ch.get("verdict", "?")
    w1_max = ch.get("w1_max")
    w1_thresh = ch.get("w1_threshold_max")
    print(f"  {ch_name:20s}  verdict={ch_verdict:6s}  w1_max={w1_max!s:14s}  threshold={w1_thresh!s}")

if warnings:
    print()
    print("Warnings:")
    for w in warnings[:10]:
        print(f"  - {w}")

# Comparison with Day-37 HiGHS baseline (substrates W1=171.39 FAIL)
print()
print("=" * 70)
print("Comparison with Day-37 HiGHS baseline")
print("=" * 70)
print("  HiGHS substrates W1: 171.39 (FAIL)")
substrates = channels.get("substrates", {})
sub_w1 = substrates.get("w1_max")
sub_thresh = substrates.get("w1_threshold_max")
print(f"  GLPK  substrates W1: {sub_w1}  (threshold {sub_thresh})")
if sub_w1 is not None and sub_thresh is not None:
    delta = (171.39 - float(sub_w1)) / 171.39 * 100
    print(f"  Reduction: {delta:.1f}%")
    if float(sub_w1) <= float(sub_thresh):
        print(f"  *** VERDICT: PASS — GLPK fix sufficient for L2.2 ***")
    else:
        gap = float(sub_w1) - float(sub_thresh)
        print(f"  Still over threshold by {gap:.2f} (need {((float(sub_w1)/float(sub_thresh))-1)*100:.1f}% more reduction)")
