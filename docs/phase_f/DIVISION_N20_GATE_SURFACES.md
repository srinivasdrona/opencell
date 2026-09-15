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

## Cytokinesis: full stochastic next-update replay

Primary MATLAB source: `Cytokinesis.m`. Projection-v3 dual traces add the Cytokinesis process's private
`randStreamState` immediately before and after its real MATLAB
`evolveState()` call. The stream is owned by `Process_Cytokinesis.randStream`
(`mcg16807`); the simulation scheduler and chromosome state own different
streams and cannot substitute. The gate reconstructs only the OC port shape
using:

- captured per-tick values for every dynamic field;
- fixture-derived FtsZ constants/WIDs;
- source-derived `numEdges = calcNumEdges(pinchedDiameter, filamentLength)`;
- captured process-local substrates as the allocator grant Karr actually
  placed in `this.substrates` before `evolveState`.
- captured process-private RNG state, restored once at the window start and
  checked continuously against every subsequent before/after tap.

The gate runs OC's real `next_update` and compares every meaningful,
non-redundant output exactly:

1. substrate, enzyme, and bound-enzyme vectors;
2. `pinchedDiameter` and all four independent FtsZ-ring counters;
3. process-private RNG exit state;
4. contraction count/timing/payload, including the final zero clamp.

`geometry.pinched`, `ftsZRing.numEdges`, division compatibility fields, and
fixed ring constants are deterministic projections of those values and are
checked as invariants rather than double-counted. Authority additionally
requires `dual_tap_extractor_schema_version=2` plus current LF-normalized
hashes of the dual extractor and actual resolved `Cytokinesis.m`.

Projection-v2 traces lack this state and remain usable only as explicitly
conditional pilots of `calc_next_pinched_diameter` under Karr's observed
ring-hydrolysis schedule. They cannot write authority. Every selected
completed trace used for full N=20 Cytokinesis authority must therefore be
re-extracted through the one-pass dual Cyt/FtsZ extractor; no field is
backfilled or inferred from the initial seed.

The Opus rejection of the `6e7cd84` conditional surface is binding:

- exact payload thresholds are zero, so one mismatch fails;
- conditional projection never supplies an OC count/timing timeline; those
  channels are forced non-green until full replay can detect both missed
  events and overfire across every tick;
- event payloads pair by `(seed, tick)`, never flattened position;
- the preregistered `substrates` primary and `chromosome` output remain in
  the catalog. RNG/ring/geometry fields are additive replay requirements,
  not replacements selected after seeing a pilot result;
- `analytical_check` passes only after evaluating the injected full SUT;
- authority writing receives the selector-owned context seed tuple and
  refuses any result seed/order drift.

The old-format extraction campaign is paused after seed 15 because its output
cannot satisfy either authority surface. Existing pairs remain archived
conditional Cytokinesis diagnostics, but their missing `geometry_volume`
means they are not valid FtsZ gate inputs and they close neither row.

### Live combined seed-36 canary — PASSED

The orchestrator—not this coding-agent run—launched the canary from branch
tip `8b98643` on 2026-09-15. The corrected dual extractor produced:

- Cytokinesis SHA-256
  `d097a48c9c3eebe00594ee67503cf54c693ecc3be5693e05104247b4058d4ec0`;
- FtsZPolymerization SHA-256
  `2a207bacad1b5951720bfaeaf0cacf87e147867a6884100d4c6bf35f501b3882`;
- `full_replay_ready=true`, provider/source identity match, and Cytokinesis
  inclusive onset-to-completion span `4076` ticks.

The actual Cyt full-replay helper then evaluated all 5000 ticks: zero
mismatches in all 13 audit fields, 147/147 contraction events, and 1351/1351
substrate-event ticks. The stored exclusive offset difference is 4075
(`onset_offset=924`, `completion_offset=4999`), consistent with the inclusive
span of 4076.

The FtsZ live-volume helper replayed all 200 ticks with captured volume
`2.1844313724237267e-17` to `2.192708426282513e-17` L. Karr and OC were
active on 200/200 ticks and monomer-projection maximum discrepancy was
exactly 0. Enzymes differed on 1550 elements across 200 ticks
(`max_abs=6`, `L1_total=2383`, single-seed scaled-component W1
`0.0743181818181818`); substrates differed on 280 elements across 165 ticks
(`max_abs=6`, `L1_total=449`, single-seed scaled-component W1
`0.028250000000000008`). These are one-seed diagnostics, not N20 verdicts.

The raw MAT files remain gitignored and are not committed. The reproducible
slot-managed command was:

```powershell
.\scripts\tools\run_matlab_slot.ps1 `
  -Worktree "E:\opencell-worktrees\fix-cyt-n20-rng-replay" `
  -Tag "cyt_rng_replay_s036" `
  -Slots <ORCHESTRATOR_APPROVED_CAP> `
  -MatlabCommand "addpath(genpath('scripts/matlab')); extract_dual_division_window(uint32(36));"
```

Post-run validation:

```powershell
.\bin\oc-py.cmd -m scripts.l2_event.validate_dual_division_canary `
  --seed 36 `
  --karr-native-root data/m1_sources/karr_native `
  --require-cytokinesis-full-replay
```

## FtsZPolymerization: windowed continuous distributions

Primary MATLAB source: `FtsZPolymerization.m`. The catalog now routes this
process to `harness_type: windowed_continuous`, never to a binary event
adapter. The gate replays every real 200-tick pre-division window without
`trace_hint` and compares per-tick:

- enzyme oligomer-state update vectors (primary);
- substrate update vectors (secondary).

The primary MATLAB process also reads live `geometry.volume` for every
count/concentration conversion and for its solver threshold. The dual
extractor now captures that scalar at both FtsZ tap points, and the gate
requires the before value as a replay input while asserting FtsZ did not
change it. Older windows without `geometry_volume` are refused rather than
replayed against the fixture default.

This is a **gate-only source-fidelity claim**. Both chassis topologies expose
the shared `geometry.volume` port, but no source-faithful dynamic volume
producer is currently wired; autonomous chassis runs therefore start and
remain on fitted fixture initialization unless another process explicitly
updates the store. That fallback preserves construction compatibility but is
not Karr live-volume evidence. The gate never uses it and never invents
volume: only captured per-tick trace values are authoritative.

The selector-owned cohort is split before OC scoring: first half Karr-only
calibration, second half independent evaluation (**10 evaluation seeds at
N=20**; 6 in the historical N=12 pilot). Within the calibration half,
circular Karr-vs-Karr
splits produce scaled W1 null distances. For the even calibration cohorts
used here, reversing the two equal halves does not create a new W1 draw, so
only N/2 distinct unordered split pairs are retained: 3 for the N=12 pilot
calibration and **5 distinct splits for N=20 authority calibration**. q95 is multiplied by the
preregistered engineering factor 3. The calibrator API accepts no OC
argument.

Hard guards precede/augment the distance:

- Karr and OC activity must both be present in every selected seed;
- zero-vs-nonzero support mismatches fail;
- every active component must have at least 30 nonzero observations on each
  side; components jointly zero in Karr and OC are excluded from this support
  guard, while asymmetric zero support fails separately;
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
The in-flight old-format seed-15 attempt may finish, but extraction pauses
before seed 16 because those files do not capture `geometry_volume`.

- **Cytokinesis conditional projection**: contraction counts were 147/seed on both Karr and OC
  projection; count W1=0, timing W1=0, next-diameter payload mismatches=0.
  All 12 projected completion clamps reached zero. Karr
  onset-to-completion spans were 3676-3943 ticks. This is a clean pilot
  surface, not a PASS. All 12 files predate the RNG replay projection and
  are ineligible for full authority until re-extracted. They also predate
  the FtsZ live-volume projection.
- **FtsZPolymerization**: the historical candidate run on calibration seeds
  `0-5` and evaluation seeds `7,8,9,10,11,13` produced enzymes
  `0.581578 > 0.174015` and substrates `0.1895 > 0.152667`. Source-first
  review then collapsed complementary split duplicates using Karr data only:
  corrected thresholds are enzymes `0.173409` (distance 3.354x threshold,
  10.061x q95) and substrates `0.151067` (1.254x threshold). The
  preregistered multiplier remains 3.0 and no OC outcome enters calibration.
  The source diagnosis also found that both the OC port and extractor had omitted live
  `geometry.volume`, a required concentration reference frame. After the
  fail-closed repair, the same N=12 files are refused because none contains
  `geometry_volume`; no post-fix distance is fabricated. See
  `docs/phase_f/audits/FTSZ_N12_MISMATCH_DIAGNOSIS.md`.
