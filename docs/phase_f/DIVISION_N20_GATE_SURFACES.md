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

### Approval-gated one-seed canary

Do not launch until the orchestrator confirms an available MATLAB host slot.
Seed 36 is the canary because its patched-source completion/onset coordinates
are already independently known and a separate genuine single-process trace
has demonstrated exact 5000-tick OC replay. From PowerShell:

```powershell
.\scripts\tools\run_matlab_slot.ps1 `
  -Worktree "E:\opencell-worktrees\fix-cyt-n20-rng-replay" `
  -Tag "cyt_rng_replay_s036" `
  -Slots <ORCHESTRATOR_APPROVED_CAP> `
  -MatlabCommand "addpath(genpath('scripts/matlab')); extract_dual_division_window(uint32(36));"
```

Then validate without MATLAB:

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

- **Cytokinesis conditional projection**: contraction counts were 147/seed on both Karr and OC
  projection; count W1=0, timing W1=0, next-diameter payload mismatches=0.
  All 12 projected completion clamps reached zero. Karr
  onset-to-completion spans were 3676-3943 ticks. This is a clean pilot
  surface, not a PASS. All 12 files predate the RNG replay projection and
  are ineligible for full authority until re-extracted.
- **FtsZPolymerization**: calibration seeds `0-5`; independent evaluation
  seeds `7,8,9,10,11,13`. All 6 evaluation seeds had Karr and OC activity;
  monomer-projection discrepancy remained exactly 0; no component had a
  zero-vs-nonzero mismatch and sample support was sufficient. The honest
  distributional comparisons exceeded their Karr-only engineering
  thresholds: enzymes 0.581578 > 0.174015, substrates 0.1895 > 0.152667.
  This pilot therefore surfaces a real prospective gate discrepancy; no
  authority verdict is emitted at N=12.
