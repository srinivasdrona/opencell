"""Detect hint-driven short-circuits across all karr_*.py processes.

For each file using trace_hint, scan for any branch shape that:
- reads `trace_hint.*_next` keys
- returns/emits hint-derived values without running the underlying biology sampler

Categories:
A. EXPLICIT_SHORTCIRCUIT - named `_*_from_trace_hint` / `_substrate_deltas_from_hint` method called inside next_update with early-return
B. HINT_DRIVEN_BRANCH - inline `if trace_hint.get(...): ...emit hint deltas directly...`
C. HINT_GATED_BIOLOGY - biology computation requires hint to fire (e.g., n_bound = hint_value; if n_bound > 0: do chemistry)
D. NO_SHORTCIRCUIT - reads trace_hint only for cross-checks, biology always runs
"""
from __future__ import annotations
import re
from pathlib import Path

VIV = Path("opencell/vivarium")
FILES = sorted(VIV.glob("karr_*.py"))

PATTERNS = {
    "explicit_method": re.compile(r"(def\s+_\w*(from_trace_hint|from_hint|_replay_from_hint))", re.I),
    "hint_next_read": re.compile(r'trace_hint\.get\(["\']\w+_next["\']\)|hint\.get\(["\']\w+_next["\']\)|hint\[["\']\w+_next["\']\]'),
    "early_return_from_hint": re.compile(r"return\s+self\._(\w*from_trace_hint|\w*from_hint|\w*replay_from_hint)"),
    "hint_to_delta_inline": re.compile(r'(\w+)_next.*nxt - now|nxt = .*hint.*get|delta = nxt - now'),
    "comment_shortcircuit": re.compile(r"(short-circuit|trust the trace|ground truth|bypass.*sampler|L2\.1 replay)", re.I),
    "if_n_bound_zero_skip": re.compile(r"if n_bound\s*>\s*0|if nBound\s*>\s*0|if n_bound == 0|if nBound == 0"),
}

def scan(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    findings = {}
    for name, rx in PATTERNS.items():
        hits = rx.findall(text)
        findings[name] = len(hits)
    findings["bytes"] = len(text)
    findings["uses_trace_hint"] = "trace_hint" in text
    # Try to classify
    if findings["early_return_from_hint"] > 0:
        findings["category"] = "A_EXPLICIT_FULL_BYPASS"
    elif findings["comment_shortcircuit"] > 0 and findings["hint_to_delta_inline"] > 0:
        findings["category"] = "A_EXPLICIT_PARTIAL_BYPASS (chemistry-only)"
    elif findings["hint_next_read"] > 0 and findings["if_n_bound_zero_skip"] > 0:
        findings["category"] = "C_HINT_GATED_BIOLOGY (biology runs only if hint -> non-zero)"
    elif findings["hint_next_read"] > 0:
        findings["category"] = "B_HINT_DRIVEN_BRANCH"
    elif findings["uses_trace_hint"]:
        findings["category"] = "D_TRACE_HINT_USED_BUT_NO_OBVIOUS_SHORTCIRCUIT"
    else:
        findings["category"] = "E_NO_TRACE_HINT"
    return findings

print(f"{'file':50s} {'category':50s} hint_read returns method comment biology_gated")
print("-" * 200)
for f in FILES:
    r = scan(f)
    print(f"{f.name:50s} {r['category']:50s} {r['hint_next_read']:>9d} {r['early_return_from_hint']:>7d} {r['explicit_method']:>6d} {r['comment_shortcircuit']:>7d} {r['if_n_bound_zero_skip']:>13d}")
