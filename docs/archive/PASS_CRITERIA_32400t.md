# Pass Criteria for the 32,400-Tick *M. genitalium* Single-Cell-Cycle Simulation

**Author**: Copilot CLI session 5c51d44b-5a9f-4b23-85ff-0fddaadf2212.
**Date drafted**: 2026-05-24.
**Status**: Draft. To be confirmed once Karr-reference extraction completes; numerical bands may tighten or loosen based on what we find.

## Purpose

Define quantitative success criteria for the opencell whole-cell simulation BEFORE running the 32,400-tick scenario. Without pre-defined criteria, every numerical near-miss becomes rationalizable post-hoc and 10 days of plumbing work fails to convert into a scientific claim.

## Scope

- One simulation run: wild-type *M. genitalium*, single cell, single cell cycle.
- 32,400 ticks at 1-second resolution (some processes step at 2 s; total simulated time = 9 hours = 32,400 s real-time).
- Diagnostic mode (per-process substrate accounting on).
- Compared against Karr et al. 2012 published trajectories for the same scenario.

## Success levels

Three tiers. A run is graded on how many criteria fall in each tier.

- **PASS**: within ±20% of reference (tight, publication-quality match)
- **PARTIAL**: within ±50% of reference (qualitatively right, quantitatively loose — acceptable for a first port)
- **FAIL**: outside ±50%, or wrong sign, or missing the qualitative feature (e.g. cell doesn't divide)

## Pass criteria

### A. Cell growth (highest priority — this is the core claim)

| # | Criterion | PASS | PARTIAL | FAIL |
|---|---|---|---|---|
| A1 | Cell dry mass at tick 32400 / dry mass at tick 0 | 1.8–2.2× (doubles) | 1.5–2.5× | <1.5× or >2.5× |
| A2 | Cell mass growth is monotonic non-decreasing | strictly monotonic | ≤1% reversals | >1% reversals |
| A3 | Total protein count at tick 32400 | within ±20% of Karr | ±50% | outside ±50% |
| A4 | Total RNA count at tick 32400 | within ±20% of Karr | ±50% | outside ±50% |

### B. Energy currency (mid priority — sanity that metabolism is steady)

| # | Criterion | PASS | PARTIAL | FAIL |
|---|---|---|---|---|
| B1 | ATP at tick 32400 within ±25% of tick 0 | yes (steady-state) | within ±50% | growing or shrinking >50% |
| B2 | ATP never < 10% of initial pool | always above | brief excursions <10% (<5% of ticks) | sustained excursion or hits zero |
| B3 | GTP/CTP/UTP follow same pattern as ATP | all three within ±25% drift | within ±50% | any NTP runs away |

### C. DNA replication (high priority — this is the "did the cell actually do biology" check)

| # | Criterion | PASS | PARTIAL | FAIL |
|---|---|---|---|---|
| C1 | Exactly one replication initiation event | exactly 1 | 0 or 2 (off-by-one) | >2 or never |
| C2 | Replication initiation tick | within ±10% of Karr's value (≈ tick 21,000 if Karr's initiation is at ~6 hr) | ±25% | outside ±25% |
| C3 | Replication completes within the cell cycle | yes | yes but late | no |
| C4 | dNTP transient depletion during replication | observed | partial signal | flat dNTPs through replication |

### D. Translation (mid priority — protein synthesis sanity)

| # | Criterion | PASS | PARTIAL | FAIL |
|---|---|---|---|---|
| D1 | Average protein synthesis rate (aa/s) | within ±20% of Karr | ±50% | outside ±50% |
| D2 | AA pool dynamics: no AA goes below 50% of initial | always above 50% | brief excursions | sustained low or hits zero |
| D3 | Ribosome utilization (active ribosomes / total) | qualitative match to Karr's curve | weak match | wrong shape |

### E. Conservation / plumbing (low priority — but a regression FAIL here voids everything else)

| # | Criterion | PASS | PARTIAL | FAIL |
|---|---|---|---|---|
| E1 | `|cum unattributed_delta|` < 100 for ALL cross-process substrates over 32,400 ticks | yes | <1000 | ≥1000 |
| E2 | No substrate outside `KNOWN_OK_DRAINERS` whitelist goes monotonic-negative >100/tick for >100 ticks | clean | minor violations | many violations |
| E3 | Simulation completes 32,400 ticks without exception | yes | crash with diagnostic info | silent corruption |

### F. Performance (informational — not part of pass/fail)

- Wall-clock time
- Memory peak
- CSV output size

Report these but don't grade on them.

## Aggregate scoring

For each tier compute the count: `n_PASS / n_total`, `n_PARTIAL / n_total`, `n_FAIL / n_total` across all criteria (A1..E3, 18 total).

- **OVERALL PASS**: ≥14/18 PASS AND zero FAIL in tier A (growth) or tier E3 (run completion)
- **OVERALL PARTIAL**: at least 12/18 PASS+PARTIAL AND no FAIL in A1/A2/E3
- **OVERALL FAIL**: any FAIL in A1, A2, or E3 — these are catastrophic; or fewer than 12/18 PASS+PARTIAL

## What we publish on OVERALL PASS

Honest framing for an external audience:
> "We have ported Karr et al. 2012's whole-cell simulation of *M. genitalium* to Python (vivarium-core). On a single cell-cycle run we reproduce 14 of 18 quantitative benchmark criteria within ±20% of the original publication. [Link to side-by-side trajectory plots.] The port is open-source at [URL] and runnable on a laptop in [N] hours. Differences from the reference are documented in [section]."

That is a real claim, defensible, and modest. NOT "we built a whole-cell simulator" — that's already done. The claim is "we made it accessible, reproducible, and modular for downstream extensibility."

## What we DON'T publish

- "We have a working simulation" without showing the benchmark grade.
- Trajectories that "look right" without numerical comparison.
- Conservation tables alone — those prove plumbing, not biology.

## Open questions

1. What units does Karr publish in? Need to harmonize with our internal units before grading.
2. Are Karr's trajectories deterministic? If they used stochastic algorithms, we need ±1σ bands not point values.
3. Does Karr's 9-hour cycle map to our 32,400 ticks exactly? Their tick may be 1s but processes run at different rates.

These get answered once the Karr-reference Codex returns.

## Revision plan

After Karr-reference extraction:
- Confirm units / time alignment
- Tighten or loosen the percentage bands based on Karr's reported tick-to-tick variance
- Add any quantity that was easy to extract but we didn't list here
- Drop any quantity that turned out to be unavailable from public artifacts
