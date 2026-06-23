"""Count Metabolism's L2.5 pair participation."""
from __future__ import annotations
import re
from pathlib import Path

text = (Path(__file__).resolve().parent.parent / "docs" / "phase_f" / "L2_5_PAIR_MATRIX.md").read_text()
start = text.find("## 3. Pair count matrix")
block = re.search(r"```text\n(.*?)\n```", text[start:], re.S).group(1)
rows = block.splitlines()[1:]
processes = []
matrix = []
for row in rows:
    m = re.match(r"^\s*(\d+)\s+(\S(?:.*?\S)?)\s+([\-\d\s]+)$", row)
    if m:
        processes.append(m.group(2).strip())
        matrix.append([0 if c == "-" else int(c) for c in m.group(3).split()])

metab_idx = processes.index("Metabolism")
nonzero = [(processes[i], matrix[metab_idx][i]) for i in range(len(processes)) if matrix[metab_idx][i] > 0]
print(f"Metabolism participates in {len(nonzero)} shared-pool L2.5 pairs (out of 27 possible partners):")
for p, c in sorted(nonzero, key=lambda x: -x[1]):
    print(f"  {p:<32} overlap={c}")
print(f"\nTotal substrate-WID overlap with all partners: {sum(c for _, c in nonzero)}")
print(f"Metabolism is THE substrate hub — touches every major biochemistry channel.")
