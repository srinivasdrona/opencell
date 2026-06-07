"""Beat 1 honest-path probe for DNARepair.

For each replay tick, build the SUT inputs from npz, run next_update, see what
it actually writes. This is the i4 equivalent question: does the SUT produce
non-trivial substrate deltas during the replay window?
"""
import sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from opencell.vivarium.karr_dna_repair import KarrDNARepairProcess

NPZ = REPO / "data" / "karr_fixtures" / "per_process_replay" / "DNARepair.npz"
data = np.load(NPZ, allow_pickle=True)

p = KarrDNARepairProcess({"rng_seed": 0})
tracked = list(p.tracked_substrates)
print(f"tracked_substrates: {tracked}")

# substrates npz is (100, 1, 277) — we don't know which 277 WIDs.
# Try: use process internal substrate_wids if available.
sub_wids = None
for attr in ("substrate_wids", "_substrate_wids", "all_substrate_wids"):
    if hasattr(p, attr):
        sub_wids = list(getattr(p, attr))
        print(f"Found substrate WID list via process.{attr}: n={len(sub_wids)}")
        break
if sub_wids is None:
    # Try loading the flat fixture
    import scipy.io as sio
    mat = sio.loadmat(str(REPO / "data" / "karr_fixtures" / "per_process" / "DNARepair_flat.mat"), squeeze_me=True, struct_as_record=False)
    print(f"flat keys: {sorted(k for k in mat.keys() if not k.startswith('__'))}")
    inner = mat.get("data")
    if inner is not None:
        print(f"data subfields: {[f for f in dir(inner) if not f.startswith('_')][:30]}")

# Without WID list, we can still: run SUT with empty substrates state, see what update keys appear
print("\n=== honest-path: 5 ticks with empty/zero substrates state ===")
for t in range(5):
    state = {
        "chromosome": {"damage_events_cumulative": [], "repair_events_cumulative": []},
        "substrates": {w: 0.0 for w in tracked},
        "enzymes": {w: 0.0 for w in p.enzyme_wids},
        "boundEnzymes": {w: 0.0 for w in p.enzyme_wids},
        "protein": {"counts": {w: 0.0 for w in p.protein_enzyme_wids}},
        "complex": {"counts": {w: 0.0 for w in p.complex_enzyme_wids}},
        "substrates_allocated": {p.name: {w: 0.0 for w in tracked}},
    }
    upd = p.next_update(1.0, state)
    keys = sorted(upd.keys())
    sub_upd = upd.get("substrates", {})
    chrom_upd = upd.get("chromosome", {})
    print(f"  t={t}: update keys={keys}")
    if sub_upd:
        print(f"    substrates: {sub_upd}")
    if chrom_upd:
        print(f"    chromosome: keys={list(chrom_upd.keys())}")

print("\n=== honest-path: 5 ticks WITH typical Karr enzyme counts + damage sites ===")
# Use first replay tick's enzymes/substrates if we can map indexes — for now nonzero defaults
import json
fixture_json = json.loads((REPO / "data" / "karr_fixtures" / "per_process_replay" / "DNARepair.json").read_text())
print(f"  rng_seed={fixture_json['manifest']['rng_seed']}")

for t in range(5):
    # Plant a fake damage event so SUT has work to do
    damage_event = {
        "site_id": f"site_{t}",
        "damage_type": "abasic_site",
        "payload": {"chromosome": 0, "position": 1000 + t * 100},
    }
    state = {
        "chromosome": {
            "damage_events_cumulative": [damage_event],
            "repair_events_cumulative": [],
        },
        "substrates": {w: 100.0 for w in tracked},
        "enzymes": {w: 5.0 for w in p.enzyme_wids},
        "boundEnzymes": {w: 0.0 for w in p.enzyme_wids},
        "protein": {"counts": {w: 5.0 for w in p.protein_enzyme_wids}},
        "complex": {"counts": {w: 2.0 for w in p.complex_enzyme_wids}},
        "substrates_allocated": {p.name: {w: 100.0 for w in tracked}},
    }
    upd = p.next_update(1.0, state)
    sub_upd = upd.get("substrates", {})
    chrom_upd = upd.get("chromosome", {})
    print(f"  t={t}: update keys={sorted(upd.keys())}")
    if sub_upd:
        print(f"    substrates: {sub_upd}")
    if chrom_upd:
        print(f"    chromosome: {list(chrom_upd.keys())} repair_count={chrom_upd.get('repair_count', 0)}")
