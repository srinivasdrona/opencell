# STATUS: dimer fix trna-aminoacylation

## Verdict
L1-GREEN

## Files changed
- opencell/vivarium/karr_trna_aminoacylation.py
- opencell/vivarium/karr_composite.py
- tests/vivarium/test_karr_trna_aminoacylation.py
- tests/integration/test_karr_chassis_v6.py
- tests/unit/test_karr_trna_aminoacylation_strict_zero.py

## Test results
- `py -3.12 -m pytest -x tests/vivarium/test_karr_trna_aminoacylation.py -q` -> 10 passed
- `py -3.12 -m pytest -x tests/integration/test_karr_chassis_v6.py -q` -> 7 passed

## Beat 3 expected outcome and evidence
Expected outcome (Beat 3):
- A chassis-built v6 state should contain at least one nonzero complex enzyme WID used by `karr_trna_aminoacylation`.
- `karr_trna_aminoacylation` should have `complex` topology wiring and read complex enzymes from `complex.counts` while reading monomer enzymes from `protein.counts`.
- With chassis-built state (no manual writes to chassis-owned stores), that seeded complex enzyme should be observable in the process enzyme vector and support positive flux in at least one catalyzed reaction.

Evidence:
- `tests/integration/test_karr_chassis_v6.py::test_v6_trna_aminoacylation_complex_chain_seed_port_read` asserts:
  - `topology["karr_trna_aminoacylation"]["complex"] == ("complex",)`
  - at least one `trna_proc.complex_enzyme_wids` has nonzero `composite["state"]["complex"]["counts"][wid]`
  - process read path (`_enzyme_vector_from_split_stores`) returns the exact seeded complex value.
- `tests/vivarium/test_karr_trna_aminoacylation.py::test_v6_chassis_seeded_complex_enzyme_is_flux_active_without_manual_store_writes` asserts:
  - same nonzero seeded complex WID exists in chassis-built state
  - enzyme vector uses that complex store value
  - at least one reaction catalyzed by that same complex WID has positive computed flux.

Outcome: matched.

## Beat 4 inversion and evidence
Inversion failure mode named before edits:
- Tests could pass while still wrong if the process still effectively depended on `protein.counts` or manual test injections, making the new `complex` port non-load-bearing.

Evidence inversion did not occur:
- Process schema now splits catalytic enzyme WIDs by canonical class:
  - monomer catalytic WIDs only in `protein.counts`
  - complex catalytic WIDs only in `complex.counts`
- Process read path now fails fast on missing required catalytic WIDs in the wrong/missing store (`KeyError`), removing silent `dict.get(..., 0.0)` darkness for declared catalytic inputs.
- v5/v6 chassis topology includes `complex` port mapping for `karr_trna_aminoacylation`.
- v5 seed path injects canonical snapshot defaults for the process' complex catalytic WIDs into `complex.counts` (used by v6 since v6 composes from v5).
- Regression tests validate chain from chassis-built state without writing to `protein.counts` / `complex.counts` / `rna.counts` in setup.

Outcome: inversion did not occur.

## Notes for PM
- `build_karr_chassis_v6` composes from `build_karr_chassis_v5`, so the seed+topology fix is implemented in v5 (and mirrored in v4 for compatibility with existing process behavior).
- Read-path strictness is enforced for catalytic enzyme WIDs (the 21 WIDs used by `reactionCatalysis`), which aligns fail-fast behavior with actual flux-driving inputs.
