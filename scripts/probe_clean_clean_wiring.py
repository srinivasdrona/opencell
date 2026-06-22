"""Cross-reference clean-vs-clean pairs against existing test wiring.

For each of the 67 clean-vs-clean L2.5 pairs:
  - Is it in the data-driven l25_pair_list.toml (i.e., reachable via the
    existing DS/SS parametrized harnesses)?
  - Is there a dedicated test file?
  - What's its complexity class (DD / DS / SS)?

This tells us how many of the 67 can be run TODAY vs. how many need
new test file authoring.
"""

from __future__ import annotations

import re
import sys
import tomllib
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAIR_LIST = REPO / "data" / "schemas" / "l25_pair_list.toml"
VIVARIUM = REPO / "opencell" / "vivarium"
MATRIX_MD = REPO / "docs" / "phase_f" / "L2_5_PAIR_MATRIX.md"
TESTS_DIR = REPO / "tests" / "vivarium"


def classify(module_path: Path) -> str:
    if not module_path.exists():
        return "MISSING"
    text = module_path.read_text(encoding="utf-8", errors="ignore")
    return "DIRTY" if "trace_hint" in text else "CLEAN"


def load_module_map() -> dict[str, str]:
    catalog = REPO / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
    text = catalog.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    current_name = None
    for line in text.splitlines():
        m = re.match(r"^  - name:\s*(\S+)", line)
        if m:
            current_name = m.group(1).strip()
            continue
        if current_name:
            m = re.match(r"^    oc_module:\s*(\S+)", line)
            if m:
                out[current_name] = m.group(1).strip()
                current_name = None
    return out


def parse_matrix() -> tuple[list[str], list[list[int]]]:
    text = MATRIX_MD.read_text(encoding="utf-8")
    start = text.find("## 3. Pair count matrix")
    block = text[start:]
    fence = re.search(r"```text\n(.*?)\n```", block, re.S)
    rows = fence.group(1).splitlines()
    names: list[str] = []
    matrix: list[list[int]] = []
    for row in rows[1:]:
        m = re.match(r"^\s*(\d+)\s+(\S(?:.*?\S)?)\s+([\-\d\s]+)$", row)
        if not m:
            continue
        names.append(m.group(2).strip())
        cells = m.group(3).split()
        matrix.append([0 if c == "-" else int(c) for c in cells])
    return names, matrix


def main() -> int:
    module_map = load_module_map()
    cleanliness = {name: classify(REPO / path) for name, path in module_map.items()}
    matrix_names, matrix = parse_matrix()

    clean = {n for n in matrix_names if cleanliness.get(n) == "CLEAN"}

    n = len(matrix_names)
    clean_clean_pairs: list[tuple[str, str, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if matrix[i][j] > 0:
                a, b = matrix_names[i], matrix_names[j]
                if a in clean and b in clean:
                    clean_clean_pairs.append((a, b, matrix[i][j]))

    with PAIR_LIST.open("rb") as fh:
        data = tomllib.load(fh)
    pair_meta: dict[frozenset, dict] = {
        frozenset({p["process_a"], p["process_b"]}): p for p in data["pairs"]
    }

    # Existing test files (per-pair dedicated)
    test_files = list(TESTS_DIR.glob("test_l*.py"))
    wired_by_dedicated: set[frozenset] = set()
    for tf in test_files:
        text = tf.read_text(encoding="utf-8", errors="ignore").lower()
        for a, b, _ in clean_clean_pairs:
            if a.lower() in text and b.lower() in text:
                wired_by_dedicated.add(frozenset({a, b}))

    print("# Clean-vs-clean pair wiring inventory\n")
    rows = []
    for a, b, overlap in sorted(clean_clean_pairs, key=lambda t: -t[2]):
        key = frozenset({a, b})
        meta = pair_meta.get(key, {})
        complexity = meta.get("pair_oracle_complexity", "?")
        in_toml = bool(meta)
        honest_required = bool(meta.get("l25_honest_required"))
        dedicated = key in wired_by_dedicated
        rows.append((a, b, overlap, complexity, in_toml, honest_required, dedicated))

    print(f"Total clean-vs-clean pairs: {len(clean_clean_pairs)}\n")

    print("## By complexity")
    c = Counter(r[3] for r in rows)
    for k, v in c.most_common():
        print(f"  {k:<35} {v}")

    print(f"\n## In l25_pair_list.toml          : {sum(1 for r in rows if r[4])}")
    print(f"## With l25_honest_required=true  : {sum(1 for r in rows if r[5])}")
    print(f"## Has dedicated test file        : {sum(1 for r in rows if r[6])}")

    # The data-driven harness covers DS pairs that pass l25_honest_required;
    # the SS harness currently only covers Translation+RNAProcessing.
    runnable_today = sum(
        1 for r in rows if r[5] and r[3] == "deterministic_stochastic"
    )
    print(f"\n## Runnable today via DS parametrized harness: {runnable_today}")
    print("   (SS pairs need either new wiring or extending an SS parametrized harness.)")

    print("\n## Full table")
    print("| process_A | process_B | overlap | complexity | in_toml | honest_req | dedicated_test |")
    print("|---|---|---:|---|:---:|:---:|:---:|")
    for a, b, overlap, complexity, in_toml, hr, dt in rows:
        print(f"| {a} | {b} | {overlap} | {complexity} | "
              f"{'✓' if in_toml else '✗'} | {'✓' if hr else '✗'} | {'✓' if dt else '✗'} |")

    return 0


if __name__ == "__main__":
    sys.exit(main())
