# Translation v1 vs v3 Audit Diff

Scope:
- v1 audit target: `opencell/vivarium/karr_translation.py`
- v3 runtime/audit target: `opencell/vivarium/karr_translation_v3.py`

## D1 (activity firing)
- Verdict: **resolved in v3**
- Why: the first audit targeted a class that canonical v6 does not execute (`karr_translation.py`), while v3 is the class remapped to runtime key `karr_translation`.
- v1 refs: `opencell/vivarium/karr_translation.py:13,42`
- v3 refs: `opencell/vivarium/karr_translation_v3.py:31-34,107-145`; `opencell/vivarium/karr_composite.py:1885-1890`

## D2 (allocator enrollment)
- Verdict: **still applies**
- Why: both paths write direct substrate deltas and remain outside allocator `consumer_processes` enrollment for Translation.
- v1 refs: `opencell/vivarium/karr_translation.py:137-140`
- v3 refs: `opencell/vivarium/karr_translation_v3.py:140-145`; `opencell/vivarium/karr_composite.py:1380-1409,1510-1514`

## D3 (Karr math fidelity)
- Verdict: **different in v3 (new finding shape)**
- Why: v1 used fixed fitted synthesis (`step_analytical` with prescribed rates), while v3 uses ribosome/mRNA mean-field synthesis (`predict_synthesis_per_s`) and dynamic active-ribosome input. This resolves part of v1’s rigidity but still does not implement Karr’s stochastic ribosome-state algorithm and still emits only 20-AA substrate bookkeeping.
- v1 refs: `opencell/vivarium/karr_translation.py:128-133,138-139`; `opencell/m3/translation.py:148-179`
- v3 refs: `opencell/vivarium/karr_translation_v3.py:118-129,141-145`; `opencell/m3/translation_v2.py:97-114`; `docs/karr_extracts/process/15_Translation.md:152-169`

## D4 (pipeline integrity)
- Verdict: **still applies** (clean in both audits)
- Why: v3 read/write ports are connected (`complex.counts` producer in chassis, `protein.unprocessed_counts` consumer in processing-I path); no missing endpoint was found.
- v1 refs: `opencell/vivarium/karr_translation.py:80-83,136-140`
- v3 refs: `opencell/vivarium/karr_translation_v3.py:118-136`; `opencell/vivarium/karr_composite.py:1487-1490,1510-1514`; `opencell/vivarium/karr_protein_processing_i.py:133-137`

## D5 (initial state)
- Verdict: **still applies**
- Why: the v1 t=0 monomer mismatch persists. Fixture monomers are zero at tick 0, while v3 defaults/chassis initialization seed non-zero protein counts.
- v1 refs: `opencell/vivarium/karr_translation.py:63-67`; `E:/opencell-worktrees/swarm-class-a-Translation/opencell/validation/swarm/class_a/Translation/findings.json` (D5 entry)
- v3 refs: `opencell/vivarium/karr_translation_v3.py:67-70`; `opencell/vivarium/karr_composite.py:1468-1470`

Note on wrapping/imports:
- v3 does **not** wrap/import `KarrTranslationProcess`; it imports `opencell.m3.translation` and `opencell.m3.translation_v2` directly. (`opencell/vivarium/karr_translation_v3.py:25-27`)
