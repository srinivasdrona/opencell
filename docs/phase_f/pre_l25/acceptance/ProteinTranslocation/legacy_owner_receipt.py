import sys
sys.dont_write_bytecode = True
from review_common import *
import importlib.util
import pickle
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess

event("legacy_contiguous_actual_owner_start")
source = ROOT / "tests/vivarium/test_karr_protein_translocation_l2_replay.py"
original_hash = sha(source)
spec = importlib.util.spec_from_file_location("independent_original_pt_replay", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = KarrProteinTranslocationProcess.next_update
owners, records = [], []


def observe(owner, timestep, state):
    before = pickle.dumps(owner._rng, protocol=pickle.HIGHEST_PROTOCOL)
    update = original(owner, timestep, state)
    after = pickle.dumps(owner._rng, protocol=pickle.HIGHEST_PROTOCOL)
    owners.append(owner)
    records.append({
        "tick": len(records), "owner_id": id(owner),
        "rng_before_sha256": hashlib.sha256(before).hexdigest(),
        "rng_after_sha256": hashlib.sha256(after).hexdigest(),
        "nonempty_update": bool(update), "rng_advanced": before != after})
    return update


KarrProteinTranslocationProcess.next_update = observe
try:
    module.test_karr_protein_translocation_l2_replay_identity_per_tick(rng_seed=0)
finally:
    KarrProteinTranslocationProcess.next_update = original
assert sha(source) == original_hash
assert len(records) == 100 and len({id(o) for o in owners}) == 1
assert all(records[i]["rng_before_sha256"] == records[i-1]["rng_after_sha256"]
           for i in range(1, len(records)))
assert any(r["rng_advanced"] for r in records)
save("legacy_contiguous_actual_owner.json", {
    "source": relative(source), "source_sha256": original_hash,
    "original_assertions": "Called unmodified original frozen test body with rng_seed=0",
    "records": records, "single_persistent_owner": True,
    "every_rng_transition_contiguous": True,
    "rng_resets_or_cache_clearing": False,
    "result": "PASS"})
event("legacy_contiguous_actual_owner_complete", ticks=len(records),
      distinct_owners=len({id(o) for o in owners}),
      advancing_ticks=sum(r["rng_advanced"] for r in records),
      nonempty_updates=sum(r["nonempty_update"] for r in records))
