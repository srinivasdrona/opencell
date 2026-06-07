import numpy as np

from tests.vivarium import _l2_2_design_a_runner_helpers as h

o = h.load_karr_oracle("Translation")
p = h._translation_process(0)
s = h.build_state_template(p)
for name, vec in (("substrates", o["before_substrates"][0, 0]), ("enzymes", o["before_enzymes"][0, 0]), ("boundEnzymes", o["before_bound_enzymes"][0, 0]), ("monomers", o["before_monomers"][0, 0]), ("mRNAs", o["before_mrnas"][0, 0])):
    h.overlay_observable_into_state(
        process=p,
        state=s,
        observable=name,
        vector=np.asarray(vec, dtype=float),
        wids=list(getattr(p, "aa_ids", ()) if name == "substrates" else getattr(p, "enzyme_wids", ()) if name in {"enzymes", "boundEnzymes"} else getattr(p, "protein_ids", ())),
        store_path_override=h._TRANSLATION_MRNA_STORE_PATH_OVERRIDE if name == "mRNAs" else None,
    )
h.refresh_allocator_views(p, s)
u = p.next_update(1.0, s)
print("update_keys", sorted(u))
print("writes_boundEnzymes", "boundEnzymes" in u, "writes_enzymes", "enzymes" in u)
print("protein_key", sorted(u.get("protein", {})))
print("substrate_keys", len(u.get("substrates", {})))
