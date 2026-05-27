# RNAProcessing Defer (Wave2 / Option 4)

## Current state

`karr_rna_processing` is wired into the chassis and called each tick, but it is an intentional no-op today.

What runs now:
- `karr_transcription` (runtime class `KarrTranscriptionV3Process`) emits mature gene-keyed RNA IDs into `rna.counts`.
- Those IDs are in the `MG_*` namespace (for example, `MG_469`).
- `karr_rna_processing` reads only unprocessed TU-keyed IDs (`TU_*`) from `rna.counts`.
- Runtime intersection of these ID spaces is empty, so the unprocessed-pool gate returns `{}` every tick.

Why this happens:
- The current v5 chassis collapsed Karr's multi-stage RNA path into a single TX-emits-mature step.
- RNAProcessing remains registered for topology continuity and future restoration, not because it currently contributes deltas.

## Karr reference chain

Karr's RNA pathway is explicitly staged:
1. Transcription produces nascent TU-linked transcripts.
2. RNAProcessing consumes those precursor transcripts.
3. RNAProcessing produces mature mRNA/rRNA/sRNA/tRNA outputs via composition mappings.

Primary reference:
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNAProcessing.m:414-458`
- Mature-output composition handling is visible at `RNAProcessing.m:457-458`.

## Why we defer

Wave2 focus is stabilization and parity hardening, not a central-dogma architecture rewrite.

The full fix requires touching transcription output semantics plus downstream readers and is estimated at roughly 150-300 LOC across multiple modules, plus fixture-mapping risk and multi-day integration/debug time.

Alternatives considered and rejected:
1. Gene-to-TU shim in RNAProcessing.
Reason rejected: fabricates a mapping at runtime and risks biologically incorrect cleavage/composition behavior.
2. Dual emission from transcription (emit both MG and TU pools).
Reason rejected: introduces double-accounting and ambiguity about authoritative RNA state.
3. Ignore/silence without explicit documentation.
Reason rejected: leaves a process that appears dead/buggy with no architectural context for reviewers.

## Wave3 Option 1 fix plan

If/when we restore Karr-faithful behavior, implement this in order:

1. Update `karr_transcription` to emit TU-keyed nascent RNA into `rna.counts` instead of directly writing mature gene-keyed pool values.
2. Update `karr_rna_processing` to consume TU-keyed nascent pool and emit mature mRNA/rRNA/sRNA/tRNA using the composition-matrix logic aligned with `RNAProcessing.m:457-458`.
3. Update downstream consumers (notably translation and RNA decay) so they read from the mature output pool and preserve mass/accounting invariants.
4. Use `data/m1_sources/WholeCell/data/Rna.mat` as the mapping source for TU/gene relationships and composition matrix data.

## Test gate for restoration

A dedicated regression test was added in Wave2 (`tests/unit/test_rna_processing_defer_is_intentional.py`) to assert that the TX-written RNA ID space and RNAProcessing unprocessed ID space have intersection size `0` under current architecture.

When Wave3 Option 1 is implemented, that assertion should fail by design.

That failure is the restoration signal:
- invert/update the intersection assertion,
- remove the DEFER sentinel in `karr_rna_processing.py`, and
- replace this defer document with an implementation note for the restored path.
