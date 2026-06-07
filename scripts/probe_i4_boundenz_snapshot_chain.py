import numpy as np

from tests.vivarium import _l2_2_design_a_runner_helpers as h

o = h.load_karr_oracle("Translation")
before = np.asarray(o["before_bound_enzymes"], dtype=float)[0]
after = np.asarray(o["after_bound_enzymes"], dtype=float)[0]
matches = [np.array_equal(after[t], before[t + 1]) for t in range(after.shape[0] - 1)]
diff = np.abs(after[:-1] - before[1:])
print("adjacent_match_count", int(sum(matches)), "of", len(matches))
print("max_abs_adjacent_diff", float(np.max(diff)))
print("mean_abs_adjacent_diff", float(np.mean(diff)))
