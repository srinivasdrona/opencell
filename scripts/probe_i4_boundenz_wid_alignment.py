import numpy as np

from tests.vivarium import _l2_2_design_a_runner_helpers as h

p = h._translation_process(0)
o = h.load_karr_oracle("Translation")
wids = list(p.enzyme_wids)
fixture_wids = tuple(h.load_fixture_channel_wids("Translation", "boundEnzymes"))
s = h.build_state_template(p)
b = np.asarray(o["before_bound_enzymes"], dtype=float)[0, 0]
h.overlay_observable_into_state(process=p, state=s, observable="boundEnzymes", vector=b, wids=wids)
proj = np.asarray(h.project_observable_from_state(process=p, state=s, observable="boundEnzymes", wids=wids, bound_enzymes_before=b), dtype=float)
print("wid_order_match", fixture_wids == tuple(wids))
print("roundtrip_equal", np.array_equal(proj, b))
print("first4_fixture", fixture_wids[:4], "first4_process", tuple(wids[:4]))
