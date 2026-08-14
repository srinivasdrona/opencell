# STATUS - fix_extractor_schemas_8

## Scope

Wave-2 scorecard triage for blocked extractors against existing artifact:
`/mnt/e/opencell/artifacts/ensemble_wave2_20260527_023611/seed_43/trajectory.pkl`

## Per-KP Bucket Assignment

| KP | Bucket | Rationale |
|---|---|---|
| KP03 | B (exists in trajectory sidecars) | `process_traces/karr_metabolism.csv` provides flux stream; Karr oracle fixture provides reference fluxs for comparator. |
| KP04 | B (exists in trajectory sidecars) | `TX_GLCPTS` appears in `process_traces/karr_metabolism.csv`. |
| KP15 | C (needs emitter) | No `chromosome.complex_bound_sites` in snapshot state or sibling CSVs. |
| KP21 | B (exists in trajectory sidecars) | `conservation.csv` exposes ATP/GTP process deltas and unattributed deltas for balance metric. |
| KP25 | A (designed deferral) | Explicitly deferred by design: multi-run KO sweep required. |
| KP26 | A (designed deferral) | Explicitly deferred by design: multi-run KO sweep required. |
| KP27 | C (needs emitter) | No emitted host adhesion boolean (`host.is_bacterium_adherent`) in wave-2 outputs. |
| KP28 | C (needs emitter) | No emitted host immune activation booleans in wave-2 outputs. |

## Before -> After State

| KP | Transition |
|---|---|
| KP03 | `BLOCKED -> FAIL` |
| KP04 | `BLOCKED -> FAIL` |
| KP15 | `BLOCKED -> NEEDS_EMITTER` |
| KP21 | `BLOCKED -> PASS` |
| KP25 | `BLOCKED -> DEFERRED` |
| KP26 | `BLOCKED -> DEFERRED` |
| KP27 | `BLOCKED -> NEEDS_EMITTER` |
| KP28 | `BLOCKED -> NEEDS_EMITTER` |

## Tally

`6 PASS / 14 FAIL / 8 BLOCKED` -> `7 PASS / 16 FAIL / 0 BLOCKED / 2 DEFERRED / 3 NEEDS_EMITTER`

## Commits (full SHAs)

- 91735d3feb73a57b825410a8ca83fe7945673304 `fix(scorecard): KP03 extractor reads from metabolism flux oracle`
- 4f9d5a00b7af1196326f944c4220940bcbd688fd `fix(scorecard): KP04 extractor reads from process_traces.karr_metabolism.TX_GLCPTS`
- 5719bf7a1297085e4c7d4a99e98b3d7f28f09454 `fix(scorecard): KP21 extractor reads from conservation ATP/GTP balance`
- ce69fb94688b92643a0dafb8c8a3280d995d0095 `docs(scorecard): mark KP25/KP26 as DEFERRED, not BLOCKED`
- db6bd45a4e64b08244df7363da181e187ce52a8c `docs(scorecard): KP15 requires emitter extension`
- 4b0e86f432067a84e4b658fd2671a878b967be00 `docs(scorecard): KP27 requires emitter extension`
- 1177cc11b1310f0a9b641cc3c4648e093bbe0f57 `docs(scorecard): KP28 requires emitter extension`
- (this status refresh commit)
