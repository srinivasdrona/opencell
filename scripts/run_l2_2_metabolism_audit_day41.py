"""Day-41: re-run L2.2 Metabolism design-A audit after pricing=STD fix.

Day-40 baseline (GLPK): W1=161.38 on substrates -> VERIFIED_FAIL.
Day-41 expectation: pricing=STD reduced sample writeback L1 substantially;
aggregate W1 should drop. Threshold for PASS depends on bootstrap.

Mirrors the Day-40 audit invocation pattern.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from l2_2_design_a_runner import run_design_a

OUT_DIR = REPO / "tmp" / "l2_2_metabolism_audit_day41"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Match Day-40 baseline: 50 seeds x 10 ticks
SEEDS = list(range(50))
M_TICKS = 10

print(f"Running L2.2 Metabolism audit (Day-41) on {len(SEEDS)} seeds x {M_TICKS} ticks")
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
print("RESULT (Day-41 GLPK run)")
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
