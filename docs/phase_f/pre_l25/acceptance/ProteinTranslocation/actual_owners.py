import sys
sys.dont_write_bytecode = True
from review_common import *
import copy
import pickle
import numpy as np
import _l2_2_design_a_runner_helpers as helpers
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.util.matlab_rng import MatlabRandStream

event("active_actual_owner_controls_start")
arrays = np.load(OUT / "independent_karr_only_arrays.npz")
factory = helpers._protein_translocation_process
metadata = factory(0)
active = np.any(arrays["before_monomers"] != arrays["after_monomers"], axis=2)
samples = [(s, int(np.flatnonzero(active[s])[0])) for s in (0, 1)]
records, owners, outputs = [], [], []
original = KarrProteinTranslocationProcess.next_update
current = {}


def observe(owner, timestep, state):
    assert not any("oracle" in key or "hint" in key for key in state)
    pre = pickle.dumps(owner._rng, protocol=pickle.HIGHEST_PROTOCOL)
    seed = helpers._sample_seed(current["seed"], current["tick"])
    expected = pickle.dumps(MatlabRandStream(seed), protocol=pickle.HIGHEST_PROTOCOL)
    assert pre == expected and owner is not metadata
    owners.append(owner)
    update = original(owner, timestep, state)
    post = pickle.dumps(owner._rng, protocol=pickle.HIGHEST_PROTOCOL)
    assert update and post != pre
    records.append({**current, "owner_id": id(owner), "sample_seed": seed,
                    "rng_initial_sha256": hashlib.sha256(pre).hexdigest(),
                    "rng_after_sha256": hashlib.sha256(post).hexdigest(),
                    "rng_advanced": True, "nonempty_update": True,
                    "runtime_root_keys": list(state)})
    return update


KarrProteinTranslocationProcess.next_update = observe
try:
    for i, pair in enumerate([samples[0], samples[0], samples[1],
                              samples[0], samples[1], samples[0]]):
        seed, tick = pair
        current = {"sequence": i, "seed": seed, "tick": tick, "poison_after": i >= 3}
        payload = {
            "substrate_wids": list(metadata.substrate_wids),
            "enzyme_wids": list(metadata.enzyme_wids),
            "monomer_wids": list(metadata.monomer_wids),
        }
        for channel in ("substrates", "enzymes", "bound_enzymes", "monomers"):
            payload["oracle_before_" + channel] = arrays["before_" + channel][seed, tick].copy()
        if i >= 3:
            metadata._rng.rand()
            same_key_metadata = factory(helpers._sample_seed(seed, tick))
            same_key_metadata._rng.rand()
            payload["oracle_after_substrates"] = np.full(7, -999999.0)
            payload["oracle_after_monomers"] = np.full(2892, -999999.0)
            payload["oracle_after_all"] = {"POISON": -999999.0}
            payload["oracle_after_by_channel"] = {"POISON": -999999.0}
            payload["trace_hint"] = {"POISON": -999999.0}
        unchanged = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        result = helpers.run_oc_tick("ProteinTranslocation", seed, tick, payload)
        assert pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL) == unchanged
        assert result["monomers"].shape == (2892,)
        delta = result["monomers"] - payload["oracle_before_monomers"]
        assert np.count_nonzero(delta) > 0
        records[-1]["changed_monomer_coordinates"] = int(np.count_nonzero(delta))
        records[-1]["full_projected_width"] = result["monomers"].size
        outputs.append(result)
finally:
    KarrProteinTranslocationProcess.next_update = original
assert len({id(o) for o in owners}) == 6
for indices in ([0, 1, 3, 5], [2, 4]):
    for i in indices[1:]:
        for channel in ("substrates", "monomers"):
            np.testing.assert_array_equal(outputs[indices[0]][channel], outputs[i][channel])
np.savez_compressed(OUT / "actual_owner_outputs.npz", **{
    f"call_{i}_{channel}": value[channel] for i, value in enumerate(outputs)
    for channel in ("substrates", "monomers")})
save("actual_owner_controls.json", {
    "samples": samples, "sequence_records": records,
    "six_distinct_execution_owners": True, "same_key_repeat_interleave_exact": True,
    "metadata_advanced_without_execution_effect": True,
    "poisoned_after_and_hint_ignored": True, "inputs_unchanged": True,
    "cache_cleared_or_execution_rng_reset": False,
    "public_entrypoint": "helpers.run_oc_tick -> real class.next_update (observed, unchanged delegation)",
    "original_class_next_update_restored": True})
event("active_actual_owner_controls_complete", calls=len(records), samples=samples,
      distinct_actual_owners=len({id(o) for o in owners}),
      changed_coordinates=[r["changed_monomer_coordinates"] for r in records])
