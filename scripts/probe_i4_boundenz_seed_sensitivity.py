import numpy as np

from tests.vivarium import _l2_2_design_a_runner_helpers as h

o = h.load_karr_oracle("Translation")
p = h._translation_process(0)
state = {
    "substrate_wids": list(p.aa_ids),
    "enzyme_wids": list(p.enzyme_wids),
    "monomer_wids": list(p.protein_ids),
    "mrna_wids": list(p.protein_ids),
    "oracle_before_substrates": np.asarray(o["before_substrates"], dtype=float)[0, 0],
    "oracle_after_substrates": np.asarray(o["after_substrates"], dtype=float)[0, 0],
    "oracle_before_enzymes": np.asarray(o["before_enzymes"], dtype=float)[0, 0],
    "oracle_before_bound_enzymes": np.asarray(o["before_bound_enzymes"], dtype=float)[0, 0],
    "oracle_before_monomers": np.asarray(o["before_monomers"], dtype=float)[0, 0],
    "oracle_before_mrnas": np.asarray(o["before_mrnas"], dtype=float)[0, 0],
    "oracle_after_monomers": np.asarray(o["after_monomers"], dtype=float)[0, 0],
    "oracle_after_bound_enzymes": np.asarray(o["after_bound_enzymes"], dtype=float)[0, 0],
}
rows = [(seed, h._run_translation_tick(seed, 0, state)) for seed in range(5)]
ref = rows[0][1]
for seed, out in rows:
    print(seed, np.array_equal(out["boundEnzymes"], ref["boundEnzymes"]), h.compute_w1(out["boundEnzymes"], ref["boundEnzymes"]), h.compute_w1(out["monomers"], ref["monomers"]))
