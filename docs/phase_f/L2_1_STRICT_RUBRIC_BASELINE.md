# L2.1 Strict-Rubric Baseline — Day-36 (2026-06-22)

**Status:** L2.1 acceptance rubric extended with two supplement checks
beyond bit-identity per-tick. This document records the Day-36 baseline
verdict for each of the 28 processes under the strict rubric.

## The two supplement checks (added Day-36)

1. **Karr-active rate**: For each tick, compute `max(|states_after - states_before|)`
   across all of the process's declared observables. If this exceeds threshold
   (1.0 = at least one integer-count change), the tick is "Karr-active".
2. **OC-fire-on-Karr-active rate**: On each Karr-active tick, did OC's
   `next_update` return a non-empty update? Verdict combines:
   - `GENUINE`: bit-identity PASS + OC fired on >=50% of Karr-active ticks
   - `UNINFORMATIVE`: bit-identity PASS + zero Karr-active ticks (nothing
     to validate; the trace's 100-tick window doesn't exercise this process)
   - `COINCIDENTAL`: bit-identity PASS + OC fired on <5% of Karr-active ticks
     (biology dodges comparison via empty returns)
   - `PARTIAL`: bit-identity PASS + OC fired on 5-50% of Karr-active ticks
   - `FAIL`: bit-identity FAIL OR partial fire rate
   - `ERROR`: harness/config issue, not biology

## Day-36 baseline (28 processes)

### GENUINE (9) — honestly validated

| Process | Karr-active ticks | OC-fire rate |
|---|---:|---:|
| DNARepair | 2/100 | 100% |
| MacromolecularComplexation | 18/100 | 100% |
| ProteinActivation | 2/100 | 100% |
| ProteinFolding | 61/100 | 100% |
| ProteinProcessingI | 69/100 | 100% |
| ProteinProcessingII | 67/100 | 100% |
| RNAProcessing | 30/100 | 100% |
| **Translation** | 100/100 | 100% |
| tRNAAminoacylation | 100/100 | 100% |

Notes:
- Translation passes despite being classified DIRTY in the Day-35
  short-circuit audit. Reason: its REPLAY_GUARD is hint-gated, transparent
  when no hint is present. In strict-rubric mode (no hint), Translation
  computes real biology. Day-35 audit classification was overconservative.
- DNARepair active for only 2 of 100 ticks — narrow validation window
  but biology fired correctly on those ticks.

### UNINFORMATIVE (6) — Karr trace shows no activity

| Process | Reason |
|---|---|
| ChromosomeSegregation | Cell-cycle gated; no segregation event in 100 ticks |
| Cytokinesis | Cell-cycle gated; no division in 100 ticks |
| DNADamage | Stochastic damage; rare events; none in 100 ticks |
| HostInteraction | Mycoplasma+host pathway; default config has no host |
| RNAModification | All RNAs already modified at t=0 in fixture? Verify. |
| RibosomeAssembly | Steady-state ribosome pool; no assembly events in window |

These processes' L2.1 PASS verdicts are vacuous in the 100-tick window
used by the L2.1 traces. To validate biology, either:
- Extend the trace window
- Construct synthetic test scenarios where biology must fire
- Accept that L2.1 doesn't validate these and rely on L2.5 composition tests

### COINCIDENTAL (1) — biology dodges Karr-active ticks

| Process | Karr-active | OC fired | Reason |
|---|---:|---:|---|
| TranscriptionalRegulation | 1/100 | 0/100 | Karr had 1 regulation event; OC's port-mismatched read returned 0 budget; biology returned {} |

### FAIL (11) — strict rubric exposes the hidden bugs

| Process | bit-identity | Karr-active | OC-fire | Bug class |
|---|---|---:|---:|---|
| ChromosomeCondensation | FAIL | 72/100 | 79% | Trace-hint short-circuit (GATED_BIOLOGY) |
| DNASupercoiling | FAIL | 100/100 | 100% | Short-circuit (CHANNEL_OVERLAY) |
| FtsZPolymerization | FAIL | 100/100 | 100% | Short-circuit (CHEMISTRY_BYPASS) |
| Metabolism | FAIL | 100/100 | 0% | Full FBA bypass via trace_hint |
| ProteinDecay | FAIL | 42/100 | 0% | Chemistry bypass via trace_hint |
| ProteinModification | FAIL | 20/100 | 80% | Hint-gated biology |
| ProteinTranslocation | FAIL | 13/100 | 100% | Port-mismatch (Day-36 NEW finding) |
| RNADecay | FAIL | 65/100 | 54% | Poisson sampler hint-gated |
| Replication | FAIL | 99/100 | 0% | FULL_BYPASS via trace_hint |
| ReplicationInitiation | FAIL | 61/100 | 51% | FULL_BYPASS via trace_hint |
| Transcription | FAIL | 100/100 | 100% | Polymerase-slot hint-gated |

The "OC-fire 100%" cases (Cond, DNASupercoiling, FtsZ, Transcription, Translocation)
are processes whose biology DOES fire on Karr-active ticks but produces
wrong outputs (bit-identity fails). The "OC-fire 0%" cases (Metabolism,
ProteinDecay, Replication) are processes whose biology REQUIRES the
trace_hint to fire at all; without it, they return {}.

### ERROR (1)

| Process | Issue |
|---|---|
| TerminalOrganelleAssembly | Default config doesn't pass `schema_path`; needs MA fixture |

## Implications

1. **The real L2.1 validation surface is 9 of 28 processes (32%)**, not 28 of 28
   (100%) as the legacy "all green" claim implied. The 19 other processes pass
   the legacy bit-identity check by some combination of:
   - Trace-hint short-circuits echoing the oracle (11 processes)
   - Inactive trace windows (6 processes)
   - Port-mismatch returning trivial zeros (1 process + overlap with the 11)
2. **The 22-of-28 L2.2 in-scope GREEN claim** is structurally vacuous for any
   process whose L2.1 verdict isn't GENUINE. L2.2 inherits L2.1's
   bit-identity check; if L2.1 passes by trivially returning zero, L2.2
   passes the same way under distributional comparison (zero matches zero).
3. The Day-35 catalogue of 13 trace-hint short-circuits maps cleanly onto
   the 11 strict-rubric FAILs (plus 2 hidden in UNINFORMATIVE — Seg and
   HostInteraction declare hidden_read_surface but never fire in trace).
4. **L2.5 honest-mode FAILs are now explained**: composition exposes biology
   gaps that L2.1 couldn't catch. The path forward is biology-port-by-biology-port
   fixes for the 11 FAIL processes (multi-week scope) plus rubric supplements
   for the UNINFORMATIVE 6 (synthetic test scenarios or extended traces).

## How the rubric is enforced going forward

`tests/vivarium/test_l2_1_strict_rubric.py` parametrizes across all 28
processes and pins each to its Day-36 baseline verdict. CI fails if any
process's verdict drifts. Drifts can occur via:

- Biology improvement (e.g. removing a trace-hint short-circuit) → moves
  FAIL → GENUINE. Engineer must update the pin AND celebrate.
- Biology regression → moves GENUINE → FAIL. CI catches and blocks merge.
- Trace data change → moves UNINFORMATIVE → GENUINE (or vice versa).
  Engineer reviews whether the trace extension is intentional.

The legacy per-process L2.1 tests (`test_karr_*_l2_replay.py`) remain in
place but are deprecated relative to the strict rubric. They should be
either retired or updated to invoke the strict rubric internally.

## Provenance

- Audit script: `scripts/probe_l2_1_strict_rubric.py`
- Enforced test: `tests/vivarium/test_l2_1_strict_rubric.py`
- Related: `docs/phase_f/L2_1_FALSE_POSITIVE_AUDIT.md`,
  `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md`,
  `scripts/probe_port_mismatch_audit.py`,
  `scripts/probe_read_surface_coverage.py`
- Trigger: operator question on Day-36: "how did we sign off on L2.1 green
  for this process, then? are there more processes where such issues exist?"
