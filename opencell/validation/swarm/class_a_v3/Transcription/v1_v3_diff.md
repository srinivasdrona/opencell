# Transcription v1 vs v3 finding diff

Comparison basis:
- v1 packet: `/mnt/e/opencell-worktrees/swarm-class-a-Transcription/opencell/validation/swarm/class_a/Transcription/findings.json`
- v3 packet: `opencell/validation/swarm/class_a_v3/Transcription/findings.json`

## D1 (activity firing)
**Status:** **resolved** in v3.

- v1 finding said the audited class did not match runtime identity (`KarrTranscriptionProcess` vs v6 `KarrTranscriptionV3Process`).  
  v1 reference: `.../class_a/Transcription/findings.json:13-20`.
- v3 confirms runtime identity now matches audited class and explicitly notes no v1-wrapper import/transitive wrap.  
  v3 reference: `.../class_a_v3/Transcription/findings.json:13-20`.

## D2 (allocator enrollment)
**Status:** **still applies** in v3.

- v1 reported direct `substrates` deltas with allocator bypass and no enrollment.  
  v1 reference: `.../class_a/Transcription/findings.json:28-35`.
- v3 confirms the same defect remains on the runtime class (`mismatch_confirmed`, HIGH, `blocks_b1=true`).  
  v3 reference: `.../class_a_v3/Transcription/findings.json:28-35`.

## D3 (Karr math fidelity)
**Status:** **still applies** in v3 (same mismatch class, different implementation details).

- v1 finding A: deterministic mature-RNA ODE vs Karr RNAP state-machine dynamics.  
  v1 reference: `.../class_a/Transcription/findings.json:43-50`.
- v3 finding A: still not a Karr RNAP state-machine replay; now implemented as calibrated v2 mechanism + ODE integration (`mismatch_confirmed`).  
  v3 reference: `.../class_a_v3/Transcription/findings.json:43-50`.

- v1 finding B: equal 1/4 NTP split and missing substrate side-products.  
  v1 reference: `.../class_a/Transcription/findings.json:58-65`.
- v3 finding B: equal split + missing side-product channels still present on v3 runtime class.  
  v3 reference: `.../class_a_v3/Transcription/findings.json:58-65`.

## D4 (pipeline integrity)
**Status:** **resolved** in v3 runtime path.

- v1 finding described orphan `rna` output in the legacy M1+M2+M3 composition.  
  v1 reference: `.../class_a/Transcription/findings.json:73-80`.
- v3 runtime wiring shows downstream RNA-pathway consumers and upstream regulation feed (`mismatch_absent`).  
  v3 reference: `.../class_a_v3/Transcription/findings.json:73-80`.

## D5 (initial state)
**Status:** **still applies** (fixture-contract limitation remains), with additional partial positive evidence.

- v1 finding: tick-0 parity not verifiable via replay because fixture has no tick I/O channels.  
  v1 reference: `.../class_a/Transcription/findings.json:88-95`.
- v3 finding: same replay limitation remains (`evidence_missing`), while noting mappable substrate channels do align.  
  v3 reference: `.../class_a_v3/Transcription/findings.json:88-95`.

