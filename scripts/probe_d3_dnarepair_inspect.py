"""Beat 1 inspection probe for DNARepair (operator-authored).

Compares:
  - DNARepair.npz contents (replay export — the actual oracle our harness uses)
  - KarrDNARepairProcess.next_update() write surface (from karr_dna_repair.py:299-360)

Goal: determine PRIMARY channel + bucket + duplicate-WID status in 1 script.
"""
import json
import numpy as np
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NPZ = REPO / "data" / "karr_fixtures" / "per_process_replay" / "DNARepair.npz"
JSON_P = REPO / "data" / "karr_fixtures" / "per_process_replay" / "DNARepair.json"

print("=== MANIFEST ===")
print(JSON_P.read_text())

data = np.load(NPZ, allow_pickle=True)
print("\n=== NPZ KEYS ===")
for k in sorted(data.files):
    arr = data[k]
    print(f"  {k}: shape={arr.shape} dtype={arr.dtype}")

print("\n=== BEFORE vs AFTER per channel (is replay a no-op?) ===")
chans = sorted({k.split("__")[-1] for k in data.files if "__" in k})
for ch in chans:
    # try both naming conventions (singular state_ and plural states_)
    bkey = next((f"{p}before__{ch}" for p in ("state_", "states_") if f"{p}before__{ch}" in data.files), None)
    akey = next((f"{p}after__{ch}" for p in ("state_", "states_") if f"{p}after__{ch}" in data.files), None)
    if not (bkey and akey):
        print(f"  {ch}: missing pair (before={bkey} after={akey})")
        continue
    before, after = data[bkey], data[akey]
    n_ticks = before.shape[0] if before.ndim else 0
    n_diff = 0
    sample_diffs = []
    for t in range(n_ticks):
        if not np.array_equal(before[t], after[t]):
            n_diff += 1
            if len(sample_diffs) < 3:
                d = after[t] - before[t]
                sample_diffs.append((t, int(np.count_nonzero(d)), float(np.abs(d).sum())))
    print(f"  {ch}: shape={before.shape} bkey={bkey} akey={akey}")
    print(f"    ticks_with_diff={n_diff}/{n_ticks} sample_diffs={sample_diffs}")
    # also: how many nonzero in before/after total?
    nz_b = sum(int(np.count_nonzero(before[t])) for t in range(n_ticks))
    nz_a = sum(int(np.count_nonzero(after[t])) for t in range(n_ticks))
    print(f"    nonzero entries total: before={nz_b} after={nz_a}")

print("\n=== WID ENUMS (duplicate-WID check, i3 class) ===")
for k in sorted(data.files):
    if "wid" in k.lower():
        arr = data[k]
        if arr.dtype.kind in ("O", "U"):
            wids = [str(w) for w in arr.ravel().tolist()]
            n_total, n_unique = len(wids), len(set(wids))
            dup_flag = "DUPLICATE!" if n_total != n_unique else "unique-ok"
            print(f"  {k}: n_total={n_total} n_unique={n_unique} {dup_flag} sample={wids[:5]}")
