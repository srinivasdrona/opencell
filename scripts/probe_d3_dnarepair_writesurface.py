"""Beat 1 SUT write-surface probe for DNARepair (operator-authored)."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from opencell.vivarium.karr_dna_repair import KarrDNARepairProcess

p = KarrDNARepairProcess({"rng_seed": 0})

print("=== SUT write-surface (from karr_dna_repair.py:299-360 inspection) ===")
print(f"  tracked_substrates ({len(p.tracked_substrates)}): {list(p.tracked_substrates)}")
print(f"  enzyme_wids ({len(p.enzyme_wids)}): {list(p.enzyme_wids)}")
print(f"  protein_enzyme_wids ({len(p.protein_enzyme_wids)}): {list(p.protein_enzyme_wids)}")
print(f"  complex_enzyme_wids ({len(p.complex_enzyme_wids)}): {list(p.complex_enzyme_wids)}")

print()
print("=== write surface from next_update (read from source) ===")
print("  ALWAYS WRITES: requests.DNARepair.<wid in tracked_substrates>")
print("  CONDITIONALLY WRITES (when consumption > 0): substrates.<wid in tracked_substrates>")
print("    + AMET/AHCYS/H on rm_methylation event (rare; needs AMET >= 1.0 + dimer + rng < threshold)")
print("  CONDITIONALLY WRITES (when consumed_total > 0): chromosome.repair_events_cumulative + counts")
print("  NEVER WRITES: enzymes (read-only input)")
print("  NEVER WRITES: boundEnzymes (read-only input)")
print("  NEVER WRITES: protein.counts (read-only input)")
print("  NEVER WRITES: complex.counts (read-only input)")

# Compare to replay export channels
print()
print("=== Channel comparison ===")
print("  Replay export has: substrates(277), enzymes(15), boundEnzymes(15)")
print("  SUT writes:        substrates(subset of tracked_substrates) — NOT enzymes, NOT boundEnzymes")
print()
print(f"  tracked_substrates count: {len(p.tracked_substrates)} (vs npz substrates width 277)")
print()
print("=== Trace-vs-SUT substrate WID match (the i4 / projection question) ===")
# tracked_substrates are the WIDs the SUT writes to in the substrates port
# replay npz substrates is 277-wide (full Karr substrate set)
# Need to know: which 277 WIDs are in the npz? (no WID metadata in npz, must come from elsewhere)

# Check the per_process fixture for WID list
import scipy.io as sio
fixture = REPO / "data" / "karr_fixtures" / "per_process" / "DNARepair_flat.mat"
if fixture.exists():
    mat = sio.loadmat(str(fixture), squeeze_me=True, struct_as_record=False)
    print(f"  fixture keys: {sorted(k for k in mat.keys() if not k.startswith('__'))}")
    if "substrate_wids" in mat:
        sub_wids = [str(w) for w in mat["substrate_wids"]]
        print(f"  substrate_wids (n={len(sub_wids)}): first 10 = {sub_wids[:10]}")
        # check overlap with tracked_substrates
        sut_set = set(str(w) for w in p.tracked_substrates)
        npz_set = set(sub_wids)
        overlap = sut_set & npz_set
        print(f"  overlap SUT vs npz: {len(overlap)} / SUT={len(sut_set)} npz={len(npz_set)}")
        print(f"  SUT WIDs not in npz: {sorted(sut_set - npz_set)}")
        print(f"  npz WIDs that match SUT: {sorted(overlap)}")
else:
    print(f"  fixture not found: {fixture}")
