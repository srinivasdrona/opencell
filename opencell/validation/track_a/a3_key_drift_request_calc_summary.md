# Track-A3 L4/L6 Summary

## L4 key-rename diffs

1. `opencell/vivarium/karr_allocation_step.py:67`
   - before: `("d2_real", ["ATP", "GTP", "H2O"])`
   - after: `("karr_macromolecular_complexation", ["ATP", "GTP", "H2O"])`
2. `opencell/vivarium/karr_allocation_step.py:68`
   - before: `("protein_decay_light", ["ATP", "H2O"])`
   - after: `("karr_protein_decay_light", ["ATP", "H2O"])`

## L6 MacromolComplex approach and rationale

- Chosen approach: **process-side strict allocation gating** in
  `opencell/vivarium/karr_macromolecular_complexation.py:199-208`.
- Change:
  - reads `allocated_state = states["substrates_allocated"][self.name]`
  - uses only allocated values to build `sub_counts`
  - short-circuits to no-op when allocated budget is all-zero
- Rationale:
  - directly resolves "zero-demand while consuming" by preventing any
    substrate consumption unless allocator grants budget
  - matches the strict-zero allocator contract pattern already used in
    allocator-enrolled processes
  - avoids introducing new D2 request-estimation heuristics in this A3 seam fix

## Tests added/updated

1. `tests/integration/test_allocator_key_consistency.py`
   - `test_allocator_default_keys_match_consumer_process_names`
   - asserts `KarrAllocationStep` default consumer keys equal:
     `karr_macromolecular_complexation`, `karr_protein_decay_light`, `karr_rna_decay`
2. `tests/integration/test_macromol_complex_allocator_path.py`
   - `test_macromol_complex_no_allocation_means_no_substrate_consumption`
   - asserts D2 emits no substrate deltas and no complex formation when allocated budget is zero
   - `test_macromol_complex_consumption_is_bounded_by_allocated_budget`
   - asserts D2 consumption per substrate never exceeds allocated budget
3. Compatibility alignment:
   - `tests/vivarium/test_karr_macromolecular_complexation.py`
   - updated allocation-integration expectation so zero allocation implies zero D2 formation

## Drift sweep (allocator defaults vs process names)

- Sweep scope: allocator default consumer list in
  `opencell/vivarium/karr_allocation_step.py:_default_consumer_processes`.
- Result: **no remaining default-key drifts** in runtime Python code after this patch.
  Current defaults are canonical process keys:
  - `karr_macromolecular_complexation`
  - `karr_protein_decay_light`
  - `karr_rna_decay`
