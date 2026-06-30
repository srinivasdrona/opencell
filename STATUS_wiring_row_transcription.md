# STATUS: wiring row for Transcription

- Authored `data/schemas/per_process_wiring/Transcription.yaml`.
- The row covers the MATLAB `Transcription` class, the current OC transcription wrapper, the legacy analytical wrapper, and the transcription request calculator.
- I marked `calcFluxBounds` as `not_implemented` because the MATLAB process does not define that method and neither OC transcription wrapper exposes a flux-bounds analog.

Uncertainties / deliberate notes:

- The current OC surface is `mixed` rather than purely one mode because `KarrTranscriptionV3Process` supports allocator-budget requests while `KarrTranscriptionProcess` still has a direct substrate-delta path.
- MATLAB requests water in `calcResourceRequirements_Current`; the current OC request calculator only requests ATP/CTP/GTP/UTP.
- OC initialization is split across constructor fixture loads, ports-schema defaults, and composite wiring instead of a single `initializeState` method.

Observed divergence notes:

- MATLAB `evolveState` is a detailed RNAP state machine with explicit binding, elongation, termination, and writeback.
- Current OC transcription is a mechanism-based approximation and is not a bit-identical port of that state machine.
- The row records `karr_native_m2__v4` as the main KB version and includes the additional M2 v2 fixture files loaded by the current OC transcription stack.
