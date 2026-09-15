# FtsZ N=12 window mismatch diagnosis

Status: **root cause localized; current N=12 cohort is not replay-complete**.
No MATLAB was launched. The genuine dual traces were read only from
`E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\
dual_division_cohort_current`.

## Source-first finding

The primary MATLAB process reads the live `CellGeometry.volume` three times
in every active tick:

- `FtsZPolymerization.m:203,436-438`: enzyme counts to concentration;
- `FtsZPolymerization.m:230,436-438`: allocated substrates to concentration;
- `FtsZPolymerization.m:237`: modified-ODE23S absolute threshold;
- `FtsZPolymerization.m:375,441-443`: concentration back to molecule counts.

`Process.m:300` binds `this.geometry` to the simulation's live Geometry state.
The fitted runtime dump and fixture agree on the initial/default volume
(`1.2009482713288303e-17 L`), but that default is not a substitute for the
per-tick state used by MATLAB.

Before this branch, OpenCell loaded that one fixture value into
`self._geometry_volume` and used it for every tick. The dual extractor captured
only `enzymes`, `substrates`, and `boundEnzymes` for FtsZ. All 12 selected trace
files lack the required per-tick `geometry.volume` input.

## Baseline localization

Historical baseline at gate-candidate `6e7cd84`, evaluated on seeds
`7,8,9,10,11,13`:

| channel | OC-vs-Karr distance | Karr-only threshold | result |
|---|---:|---:|---|
| enzymes | 0.581578 | 0.174015 | exceeds |
| substrates | 0.189500 | 0.152667 | exceeds |

Collapsing the duplicated complementary rotations changes only the Karr-only
null calculation, not the OC distances:

| channel | distinct-split q95 | corrected threshold | exceedance |
|---|---:|---:|---:|
| enzymes | 0.057803 | 0.173409 | 3.354x threshold; 10.061x q95 |
| substrates | 0.050356 | 0.151067 | 1.254x threshold |

This makes the primary enzyme finding slightly more conservative-to-reject
than the historical calculation; the multiplier remains the preregistered
3.0 and was not adjusted from OC outcomes.

### Component diagnostics

The enzyme mismatch is concentrated in the GTP-bound activation/polymer
surface, not in WID/index projection.

| enzyme WID | scaled W1 | Karr mean delta | OC mean delta |
|---|---:|---:|---:|
| `MG_224_MONOMER` | 0.058333 | -0.029167 | -0.070833 |
| `MG_224_MONOMER_GDP` | 0.470278 | -4.885833 | -7.707500 |
| `MG_224_MONOMER_GTP` | 2.551667 | -0.006667 | -5.110000 |
| `MG_224_2MER_GTP` | 0.190417 | 0.001667 | -0.379167 |
| `MG_224_3MER_GTP` | 0.267083 | -0.000833 | -0.535000 |
| `MG_224_4MER_GTP` | 0.323750 | 0.003333 | -0.639167 |
| `MG_224_5MER_GTP` | 0.367083 | 0.006667 | -0.727500 |
| `MG_224_6MER_GTP` | 0.410417 | 0.005833 | -0.813333 |
| `MG_224_7MER_GTP` | 0.307917 | 0.014167 | -0.600000 |
| `MG_224_8MER_GTP` | 0.034167 | 0.015000 | 0.051667 |
| `MG_224_9MER_GTP` | 1.416250 | 0.513333 | 3.345833 |

The substrate discrepancy is the exact coupled consequence:

| substrate WID | scaled W1 | Karr mean delta | OC mean delta |
|---|---:|---:|---:|
| `GDP` | 0.470278 | 4.885833 | 7.707500 |
| `GTP` | 0.477222 | -4.915000 | -7.778333 |
| `PI` | 0 | 0 | 0 |
| `H2O` | 0 | 0 | 0 |
| `H` | 0 | 0 | 0 |

No selected evaluation seed exercised the GDP-shortfall hydrolysis branch.

### Seed diagnostics

| seed | enzyme distance | substrate distance |
|---:|---:|---:|
| 7 | 0.562727 | 0.216000 |
| 8 | 0.580303 | 0.181333 |
| 9 | 0.606894 | 0.171667 |
| 10 | 0.587197 | 0.183000 |
| 11 | 0.596667 | 0.206333 |
| 13 | 0.626591 | 0.183333 |

The same direction appears in every seed, so this is not one outlier stream.

### Tick diagnostics

Twenty-tick local-position bins show no onset/end-boundary localization:

| local ticks | enzyme distance | substrate distance |
|---|---:|---:|
| 0-19 | 0.599874 | 0.171111 |
| 20-39 | 0.589394 | 0.195000 |
| 40-59 | 0.605556 | 0.211111 |
| 60-79 | 0.577399 | 0.165278 |
| 80-99 | 0.650000 | 0.281389 |
| 100-119 | 0.587121 | 0.128056 |
| 120-139 | 0.577146 | 0.183333 |
| 140-159 | 0.633460 | 0.240833 |
| 160-179 | 0.608586 | 0.179722 |
| 180-199 | 0.602146 | 0.153056 |

## Ruled-out explanations

### Projection/index alignment

For all 1,200 evaluation ticks:

- monomer-equivalent enzyme delta was exactly zero;
- `GDP_delta == -FtsZ_GDP_delta` exactly;
- `GTP_delta == -dot(n_gtp, enzyme_delta)` exactly;
- the source/fixture enzyme and substrate dimensions and WID order agree;
- zero/nonzero support mismatches were absent.

Thus an index permutation or after/before projection error is not supported.

### ODE solver

Replacing SciPy BDF in a diagnostic-only replica with MATLAB's source
modified-ODE23S algorithm did not improve the fixed-volume result:

| solver | volume input | enzyme distance | substrate distance |
|---|---|---:|---:|
| SciPy BDF | fixture default | 0.581578 | 0.189500 |
| source modified-ODE23S replica | fixture default | 0.587298 | 0.199333 |

Solver choice is therefore not the primary cause.

### Replay RNG initialization

Changing only the OC RNG start by offsets 0, 10,000, and 20,000 left the
fixed-volume enzyme distance at 0.580240-0.581616 and substrate distance at
0.189500-0.191861. The mismatch is insensitive to the replay seed position.

### Threshold validity

The N=12 pilot calibration has only three distinct unordered circular
half-splits. The original implementation evaluated six rotations, but the
last three only swapped left/right halves and therefore duplicated the first
three under symmetric W1. The calibrator now collapses those complements and
reports the true distinct count; at N=20 authority the ten-seed calibration
half yields five distinct unordered split pairs. This correction is Karr-only
and cannot inspect OC outcomes.

Even with only three distinct N=12 calibration draws, the observed enzyme
distance is about ten times the Karr-only q95 and about 3.3 times the
engineering threshold: decisive primary evidence. The substrate exceedance
is smaller and supportive. A source-equation sensitivity probe changed only
the concentration reference frame and moved the comparison well below the
independently calibrated threshold. Therefore calibration small-sample
weakness cannot explain the baseline by itself.

The nonzero-sample guard is now per active component rather than pooled over
all WIDs and ticks. Each component with any support on either side requires
at least 30 nonzero observations in both Karr and OC. Jointly zero components
are excluded from this guard; asymmetric zero support remains a separate hard
failure.

## Diagnostic-only concentration sensitivity

An exploratory volume-multiplier sweep was performed only to localize the
missing reference frame. It was inspected after OC outcomes and is therefore
**not a parameter estimate, fix, authority input, or threshold adjustment**.
No multiplier from this sweep is present in production code.

| fixture-volume multiplier | enzyme distance | substrate distance |
|---:|---:|---:|
| 1.0 | 0.581578 | 0.189500 |
| 1.4 | 0.277500 | 0.080139 |
| 1.5 | 0.211338 | 0.055694 |
| 1.6 | 0.147753 | 0.038806 |
| 1.7 | 0.090253 | 0.019028 |
| 1.8 | 0.038068 | 0.008056 |
| 2.0 | 0.120770 | 0.026833 |
| 2.2 | 0.232677 | 0.048111 |

The same 1.8 sensitivity point under the source solver gave enzyme
`0.045429` and substrate `0.010750`, and remained stable across the RNG
offset ablation. This triangulates the omitted concentration reference frame;
it does not license reconstructing volume from Karr outputs.

## Fix and remaining blocker

This branch:

1. makes OpenCell consume `geometry.volume` per tick for both count/concentration
   conversions and the solver absolute threshold; direct callers missing the
   port now fail instead of silently falling back;
2. exposes the shared FtsZ geometry port in both chassis topologies, while
   explicitly retaining the known limitation that no source-faithful dynamic
   volume producer is wired there (the chassis value remains fitted fixture
   initialization and is not claimed as live-volume fidelity);
3. adds `geometry_volume` to future dual FtsZ snapshots as a scalar, avoiding
   cyclic handle serialization;
4. makes the N=20 gate, non-gating pre-division audit, and combined dual-tap
   canary require that captured input, verify it is finite, positive, scalar,
   and unchanged by FtsZ, then overlay only the **before** value into the SUT;
5. refuses existing traces rather than guessing, fitting, or reading Karr
   after-state to drive OpenCell.

The current N=12 rerun now fails closed:

```text
REFUSED: seed 0: source-faithful replay requires captured 'geometry_volume':
... observable 'geometry_volume' missing from 'states_before'.
```

Exact post-fix N=12 distances are therefore unavailable. Closing the row
requires regenerating the genuine dual windows with the added
`geometry_volume` field; this branch did not launch MATLAB.
