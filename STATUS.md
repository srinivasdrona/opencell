# Harness child status

## Verification gate
- 9 GREEN tests passed: yes
- log: VERIFICATION_GREEN_GATE.log

## Diagnostic reveal (first-fail signatures, expected to be non-zero)
- DNASupercoiling: <tick=0, obs=enzymes, idx=0, oc=3.0, karr=0.0, diff=3.0>
- FtsZPolymerization: <tick=0, obs=enzymes, idx=3, oc=1.0, karr=0.0, diff=1.0>
- ChromosomeCondensation: <tick=0, obs=enzymes, idx=1, oc=3.0, karr=0.0, diff=3.0>
- Replication: <tick=0, obs=substrates, idx=4, oc=695.0, karr=649.0, diff=46.0>
- ReplicationInitiation: <tick=0, obs=enzymes, idx=1, oc=2.0, karr=0.0, diff=2.0>
- Transcription: <tick=0, obs=substrates, idx=0, oc=13879.0, karr=13906.0, diff=-27.0>
- Translation: <tick=0, obs=enzymes, idx=2, oc=206.0, karr=193.0, diff=13.0>
- TranscriptionalRegulation: <tick=15, obs=enzymes, idx=3, oc=1.0, karr=0.0, diff=1.0>

## Self-attestation
- files_modified: tests/vivarium/l2_replay_common.py, STATUS.md, VERIFICATION_GREEN_GATE.log, DIAGNOSTIC_REVEAL.log
- py_source_files_modified: 0 (process source untouched)
- per_process_test_files_modified: 0
- tests_run: 17 (9 gate + 8 diagnostic)
- commits_made: 1
- agents_spawned: 0