Phase B Turn 3 (TranscriptionalRegulation) COMPLETE
Date: 2026-05-22

Implemented:
- Added opencell/vivarium/karr_transcriptional_regulation.py
  - KarrTranscriptionalRegulationProcess (name: karr_transcriptional_regulation)
  - Loads data/karr_fixtures/per_process/TranscriptionalRegulation_flat.mat
  - Extracts TF WIDs, regulated TU WIDs, TF-promoter affinity matrix, TF-TU fold-change matrix
  - Ports:
    - protein.counts.<TF> (accumulate, read-only usage)
    - tf_binding.<TF>.<TU> (accumulate, emit=True)
    - tx_rate_fold_change.<TU> (set, emit=True)
  - next_update:
    - enforces free-copy constraint per TF (including unbinding if copies drop)
    - stochastically binds free TF copies to unoccupied promoters weighted by affinity
    - enforces max 1 copy per (TF, TU)
    - sets absolute tx_rate_fold_change per TU as multiplicative product of bound TF effects

- Modified opencell/vivarium/karr_m2_v3.py
  - Added optional tx_rate_fold_change read port to schema (defaults 1.0, updater set)
  - Applies fold-change multipliers to synthesis rates in next_update
  - Backward-compatible behavior preserved when regulation port is unwired

- Added tests/vivarium/test_karr_transcriptional_regulation.py (9 tests)
- Updated tests/vivarium/test_karr_m2_v3.py (8 tests total, including fold-change wiring coverage)

Fixture-derived network metrics:
- TF species: 5
- Regulated TU set extracted from fixture: 26
- TF-TU relationships extracted: 30

Key metric:
- Steady-state TF binding fraction after 100 ticks (10 copies per TF, seed=0): 0.54

Verification commands and results:
1) import check
   - /mnt/e/opencell/.venv-wsl/bin/python -c 'from opencell.vivarium.karr_transcriptional_regulation import KarrTranscriptionalRegulationProcess'
   - PASS

2) pytest tests/vivarium/test_karr_transcriptional_regulation.py -v
   - PASS (9 passed)

3) pytest tests/vivarium/test_karr_m2_v3.py -v
   - PASS (8 passed)

4) pytest tests/vivarium -q
   - PASS (115 passed)

Changed files:
- opencell/vivarium/karr_transcriptional_regulation.py
- opencell/vivarium/karr_m2_v3.py
- tests/vivarium/test_karr_transcriptional_regulation.py
- tests/vivarium/test_karr_m2_v3.py
- STATUS.md
