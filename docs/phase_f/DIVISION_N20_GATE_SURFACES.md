# Cytokinesis and FtsZPolymerization L2.2 N=20 gate surfaces

Status: implemented on `build/division-n20-gates`. The engineering cohort is
the first 20 **COMPLETED** windows in the ascending contiguous attempt stream.
N=50 is deferred confirmatory evidence. Pilot runs below N=20 are explicitly
non-authoritative and write only under gitignored `artifacts/`.

## Shared fail-closed cohort contract

Both gates call `scripts/l2_event/division_cohort_selector.py` against an
explicit caller-supplied root. They do not scan sibling worktrees, substitute
later seeds across a gap, count right-censors, accept copied trace hashes, or
mix DNADamage/provider identity. Authority mode requires exactly 20 selected
seeds and writes only the live gitignored L2.2 evidence root. The tracked
portable bundle remains generator-owned and cannot be replaced by an N<20
pilot.

## Cytokinesis: single completion event plus hydrolysis payload

Primary MATLAB source: `Cytokinesis.m`. The dual trace has real flattened
`substrates`, `enzymes`, `boundEnzymes`, `pinchedDiameter`, four FtsZ-ring
edge counters, and `chromosome_segregated`. It does not have a nested geometry
or ring object; the gate never invents one. It reconstructs only the OC port
shape using:

- captured per-tick values for every dynamic field;
- fixture-derived FtsZ constants/WIDs;
- source-derived `numEdges = calcNumEdges(pinchedDiameter, filamentLength)`;
- captured process-local substrates as the allocator grant Karr actually
  placed in `this.substrates` before `evolveState`.

The trace does not capture Cytokinesis's per-tick `randStreamState`, so a
full stochastic `next_update` replay would require fabricated RNG state and
is forbidden. The current gate instead conditions on Karr's real observed
ring-hydrolysis schedule and evaluates OC's real
`calc_next_pinched_diameter` transition for every captured contraction
cycle. It gates:

1. contraction-cycle event count;
2. contraction event timing and onset-to-completion span;
3. the next `pinchedDiameter` payload, including the final zero clamp.

Substrate/enzyme/bound-enzyme deltas are reported diagnostically and marked
non-gateable with the current projection. Their full OC comparison needs the
minimal extractor addition `randStreamState` at both Cytokinesis tap points
(the generic extractor already has the helper); the existing 12 traces are
not modified or backfilled. The bound FtsZ-GTP/GDP hydrolysis component is
also algebraically redundant with substrate extent.

## FtsZPolymerization: windowed continuous distributions

Primary MATLAB source: `FtsZPolymerization.m`. The catalog now routes this
process to `harness_type: windowed_continuous`, never to a binary event
adapter. The gate replays every real 200-tick pre-division window without
`trace_hint` and compares per-tick:

- enzyme oligomer-state update vectors (primary);
- substrate update vectors (secondary).

The selector-owned cohort is split before OC scoring: first half Karr-only
calibration, second half independent evaluation (10/10 at N=20; 6/6 in the
current N=12 pilot). Within the calibration half, circular Karr-vs-Karr
splits produce scaled W1 null distances; q95 is multiplied by the
preregistered engineering factor 3. The calibrator API accepts no OC
argument.

Hard guards precede/augment the distance:

- Karr and OC activity must both be present in every selected seed;
- zero-vs-nonzero support mismatches fail;
- primary nonzero sample count must be at least 30;
- the monomer-equivalent projection discrepancy must remain exactly zero;
- cohort duplicate/source/selection failures are refused upstream.

## Authority integration

The L2.2 generator now routes:

- `event_class` -> `latest_event/`;
- `windowed_continuous` -> `latest_windowed/`;
- `design_a_per_tick` -> `latest/`.

At N=20, each process-specific runner can write the full live mandatory
authority set and the normal generator can mechanically derive PASS/FAIL.
At N<20, neither runner writes any authority file, so the tracked board
remains 20 PASS / 0 FAIL / 2 MISSING_EVIDENCE.

## Current N=12 pilots (2026-09-14, non-authoritative)

Explicit read-only source:
`E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\
dual_division_cohort_current`.

Selected completions: `0-5, 7-11, 13`; censors `6, 12, 14` do not count.

- **Cytokinesis**: contraction counts were 147/seed on both Karr and OC
  projection; count W1=0, timing W1=0, next-diameter payload mismatches=0.
  All 12 projected completion clamps reached zero. Karr
  onset-to-completion spans were 3676-3943 ticks. This is a clean pilot
  surface, not a PASS.
- **FtsZPolymerization**: calibration seeds `0-5`; independent evaluation
  seeds `7,8,9,10,11,13`. All 6 evaluation seeds had Karr and OC activity;
  monomer-projection discrepancy remained exactly 0; no component had a
  zero-vs-nonzero mismatch and sample support was sufficient. The honest
  distributional comparisons exceeded their Karr-only engineering
  thresholds: enzymes 0.581578 > 0.174015, substrates 0.1895 > 0.152667.
  This pilot therefore surfaces a real prospective gate discrepancy; no
  authority verdict is emitted at N=12.
