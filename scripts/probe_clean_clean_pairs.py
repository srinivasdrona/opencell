"""Compute the L2.5 clean-vs-clean pair set.

A pair is "clean-vs-clean" if both processes have NO trace_hint short-circuit
in their OC implementation (per `probe_hint_shortcircuit_audit.py` audit) AND
they appear as a shared-pool (overlap > 0) pair in the L2.5 in-scope matrix.

This separates "honest biology drift" from "short-circuit-induced drift" so
we can estimate the true L2.5 green ceiling independent of the 13 known
short-circuited processes.

Usage:
    python scripts/probe_clean_clean_pairs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VIVARIUM = REPO / "opencell" / "vivarium"
CATALOG = REPO / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
MATRIX_MD = REPO / "docs" / "phase_f" / "L2_5_PAIR_MATRIX.md"

# Mirror the categories from probe_hint_shortcircuit_audit.py.
SHORTCIRCUIT_PATTERNS = [
    ("FULL_BYPASS", re.compile(r"trace_hint.*\.get\(['\"]substrates['\"]")),
    ("FULL_RETURN", re.compile(r"return\s+\{['\"]substrates['\"]:.*trace_hint", re.S)),
    ("HINT_GATED", re.compile(r"if\s+(trace_hint|hint_delta|self\._?trace_hint)\s*[\)\:!]")),
    ("HINT_BRANCH", re.compile(r"trace_hint\s*=\s*(state|input|process_input)\.get")),
    ("OBVIOUS_BYPASS_COMMENT", re.compile(r"#.*(no-op|bypass|skip|short[- ]?circuit)", re.I)),
]


def classify(module_path: Path) -> str:
    """Return one of CLEAN / DIRTY based on a quick text scan."""
    if not module_path.exists():
        return "MISSING"
    text = module_path.read_text(encoding="utf-8", errors="ignore")
    if "trace_hint" not in text:
        return "CLEAN"
    # Any trace_hint mention beyond a docstring suggests the process branches
    # on hint values somewhere. Mark DIRTY conservatively; the detail comes
    # from the published audit catalog.
    return "DIRTY"


def load_catalog_processes() -> dict[str, dict]:
    """Parse PROCESS_CATALOG.yaml minimally without PyYAML.

    Returns {process_name: {oc_module, in_scope_L2_2}}.
    """
    text = CATALOG.read_text(encoding="utf-8")
    processes: dict[str, dict] = {}
    current: dict | None = None
    name: str | None = None
    for line in text.splitlines():
        m = re.match(r"^  - name:\s*(\S+)", line)
        if m:
            if name and current:
                processes[name] = current
            name = m.group(1).strip()
            current = {}
            continue
        if current is None:
            continue
        m = re.match(r"^    oc_module:\s*(\S+)", line)
        if m:
            current["oc_module"] = m.group(1).strip()
            continue
        m = re.match(r"^    in_scope_L2_2:\s*(\S+)", line)
        if m:
            current["in_scope_L2_2"] = m.group(1).strip().lower() == "true"
            continue
    if name and current:
        processes[name] = current
    return processes


def parse_matrix() -> tuple[list[str], list[list[int]]]:
    """Parse the ASCII pair count matrix in L2_5_PAIR_MATRIX.md section 3."""
    text = MATRIX_MD.read_text(encoding="utf-8")
    # Find the fenced code block under section 3.
    start = text.find("## 3. Pair count matrix")
    if start < 0:
        raise RuntimeError("could not find pair count matrix section")
    block = text[start:]
    fence = re.search(r"```text\n(.*?)\n```", block, re.S)
    if not fence:
        raise RuntimeError("could not find matrix code block")
    rows = fence.group(1).splitlines()
    # The first row is the header (Idx Process 1 2 3 ...), skip it.
    names: list[str] = []
    matrix: list[list[int]] = []
    for row in rows[1:]:
        m = re.match(r"^\s*(\d+)\s+(\S(?:.*?\S)?)\s+([\-\d\s]+)$", row)
        if not m:
            continue
        names.append(m.group(2).strip())
        cells = m.group(3).split()
        # Cells contain "-" on the diagonal; convert to 0 for self-pair sentinel.
        matrix.append([0 if c == "-" else int(c) for c in cells])
    return names, matrix


def main() -> int:
    catalog = load_catalog_processes()
    in_scope = {n for n, d in catalog.items() if d.get("in_scope_L2_2")}

    # Classify each in-scope process via its OC module.
    cleanliness: dict[str, str] = {}
    for name, meta in catalog.items():
        module = meta.get("oc_module")
        if not module:
            cleanliness[name] = "UNKNOWN"
            continue
        cleanliness[name] = classify(REPO / module)

    matrix_names, matrix = parse_matrix()
    print("# Clean-vs-clean L2.5 pair audit\n")
    print("## Cleanliness by process")
    for name in matrix_names:
        canonical = name
        # Matrix names match catalog names exactly; report.
        scope = "in" if canonical in in_scope else "out"
        print(f"  {scope:>3} {canonical:<32} {cleanliness.get(canonical, 'UNKNOWN')}")

    # Scope for L2.5 = the full 28-process matrix in L2_5_PAIR_MATRIX.md.
    # `in_scope_L2_2` in PROCESS_CATALOG is L2.2-specific; the L2.5 honest-mode
    # gate covers all 28. We report both views below.
    clean = {n for n in matrix_names if cleanliness.get(n) == "CLEAN"}
    dirty = {n for n in matrix_names if cleanliness.get(n) == "DIRTY"}
    print(f"\n## Counts (all 28 L2.5 processes)")
    print(f"  Total L2.5 processes : {len(matrix_names)}")
    print(f"  Clean (no trace_hint): {len(clean)}")
    print(f"  Dirty (has trace_hint): {len(dirty)}")
    print(f"  Clean processes: {sorted(clean)}")
    print(f"  (For reference, L2.2 in-scope clean subset: "
          f"{sorted(n for n in clean if n in in_scope)})")

    # Build pair sets from the matrix.
    n = len(matrix_names)
    pair_overlap: dict[tuple[str, str], int] = {}
    for i in range(n):
        for j in range(i + 1, n):
            overlap = matrix[i][j]
            if overlap > 0:
                a, b = matrix_names[i], matrix_names[j]
                pair_overlap[(a, b)] = overlap

    total_shared = len(pair_overlap)
    clean_clean = {p: o for p, o in pair_overlap.items() if p[0] in clean and p[1] in clean}
    clean_dirty = {p: o for p, o in pair_overlap.items()
                   if (p[0] in clean) != (p[1] in clean)}
    dirty_dirty = {p: o for p, o in pair_overlap.items()
                   if p[0] in dirty and p[1] in dirty}

    print(f"\n## Pair counts (shared-pool only, overlap > 0)")
    print(f"  total shared-pool pairs : {total_shared}")
    print(f"  clean x clean           : {len(clean_clean)}  <-- TRUE BIOLOGY VALIDATION SET")
    print(f"  clean x dirty           : {len(clean_dirty)}")
    print(f"  dirty x dirty           : {len(dirty_dirty)}")

    print("\n## Clean x clean pair list (sorted by overlap desc)")
    print("| process_A | process_B | overlap |")
    print("|---|---|---:|")
    for (a, b), o in sorted(clean_clean.items(), key=lambda kv: -kv[1]):
        print(f"| {a} | {b} | {o} |")

    return 0


if __name__ == "__main__":
    sys.exit(main())
