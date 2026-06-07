import numpy as np

from tests.vivarium import _l2_2_design_a_runner_helpers as h

o = h.load_karr_oracle("Translation")
p = h._translation_process(0)
base = {
    "substrate_wids": list(p.aa_ids),
    "enzyme_wids": list(p.enzyme_wids),
    "monomer_wids": list(p.protein_ids),
    "mrna_wids": list(p.protein_ids),
}
for tick in range(5):
    state = dict(base)
    for key in ("substrates", "enzymes", "bound_enzymes", "monomers", "mrnas"):
        state[f"oracle_before_{key}"] = np.asarray(o[f"before_{key}"], dtype=float)[0, tick]
    for key in ("substrates", "bound_enzymes", "monomers"):
        state[f"oracle_after_{key}"] = np.asarray(o[f"after_{key}"], dtype=float)[0, tick]
    oc = np.asarray(h._run_translation_tick(0, tick, state)["boundEnzymes"], dtype=float)
    print(tick, np.array_equal(oc, state["oracle_before_bound_enzymes"]), np.array_equal(oc, state["oracle_after_bound_enzymes"]), h.compute_w1(oc, state["oracle_after_bound_enzymes"]))
