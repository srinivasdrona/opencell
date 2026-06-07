import sys
from pathlib import Path
import numpy as np
REPO = Path(".").resolve()
sys.path.insert(0, str(REPO))
from opencell.vivarium.karr_dna_repair import KarrDNARepairProcess

p = KarrDNARepairProcess({"rng_seed": 0})
all_subs = list(p.substrate_wids)
tracked = list(p.tracked_substrates)
print(f"all_substrate_wids (n={len(all_subs)}): first 10 = {all_subs[:10]}")
print(f"tracked_substrates (n={len(tracked)}): {tracked}")

# Check positions of tracked in all_subs (these are the indices into the npz substrates(100,1,277))
positions = {w: all_subs.index(w) if w in all_subs else None for w in tracked}
print(f"\nPositions of tracked WIDs in 277-vector: {positions}")

# Now look at the npz to see actual values at these positions
data = np.load(REPO / "data/karr_fixtures/per_process_replay/DNARepair.npz", allow_pickle=True)
before = data["state_before__substrates"]
after = data["states_after__substrates"]
print(f"\nbefore shape: {before.shape} after shape: {after.shape}")

# What are the values at our tracked positions across 100 ticks?
print(f"\n=== Per-tracked-WID values across 100 ticks (before & after) ===")
for w, pos in positions.items():
    if pos is None:
        print(f"  {w}: NOT IN NPZ — i4 hazard")
        continue
    b = before[:, 0, pos]  # (100,)
    a = after[:, 0, pos]
    delta = a - b
    print(f"  {w} (pos={pos}): before range=[{b.min():.0f},{b.max():.0f}] after range=[{a.min():.0f},{a.max():.0f}] delta_nonzero_ticks={int(np.count_nonzero(delta))}/100")
