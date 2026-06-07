import numpy as np
from collections import Counter

from tests.vivarium import _l2_2_design_a_runner_helpers as h

oracle = h.load_karr_oracle("Translation")
before = np.asarray(oracle["before_bound_enzymes"], dtype=float)[0]
after = np.asarray(oracle["after_bound_enzymes"], dtype=float)[0]
w1 = [h.compute_w1(before[t], after[t]) for t in range(after.shape[0])]
deltas = np.rint(after - before).astype(int).reshape(-1)
hist = dict(sorted(Counter(int(x) for x in deltas).items()))

print("ticks", after.shape[0], "mean_w1_before_after", float(np.mean(w1)))
print("min_w1", float(np.min(w1)), "max_w1", float(np.max(w1)))
print("delta_hist", hist)
print("nonzero_delta_frac", float(np.count_nonzero(deltas) / deltas.size))
