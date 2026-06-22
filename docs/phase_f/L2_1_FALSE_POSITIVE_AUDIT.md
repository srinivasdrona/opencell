# L2.1 false-positive audit — Day-36

**Status:** Comprehensive audit confirms **L2.1 has TWO classes of false-positive
passes** beyond the Day-35 trace-hint short-circuit finding.

## Question motivating this audit

After confirming on Day-36 that ProteinTranslocation's L2.1 PASS is
coincidental (it reads the wrong state port, gets zero, happens to match
Karr's expected zero at every tick), the operator asked: *"How did we sign
off on L2.1 green for this process, then? Are there more processes where
such issues exist?"*

The answer is uncomfortable: L2.1 has been signing off on coincidental
zeros, and at least 6 processes have the Translocation-class port-mismatch
bug pattern.

## The two false-positive classes

### Class A: Trace-hint short-circuits (13 processes, catalogued Day-35)

Process reads `state["trace_hint"]` and bypasses biology when hint is present.
Catalogued in `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md`. L2.1 and L2.2 harnesses
inject trace_hint; processes echo back hint-derived values; bit-identity
trivially holds.

Confirmed via direct grep: 13 of 28 processes.

### Class B: Port-mismatch coincidental zeros (6 processes, NEW Day-36)

Process's `next_update` reads state ports that are NOT in its declared
observables list. In isolation, those ports stay at template-default
(zero) because the harness only populates declared observables from Karr's
trace. The biology's rate-limiting check reads zero → early-returns `{}` →
produces 0 delta. Karr's actual delta is also 0 at those ticks (for
different real-model rate-limit reasons). Bit-identity holds coincidentally.

Confirmed via `scripts/probe_port_mismatch_audit.py`: 6 processes have the
Translocation-class signature.

| Process | Suspect reads (not in observables) | Status |
|---|---|---|
| ProteinTranslocation | `protein.enzyme_counts`, `protein.location`, `complex.counts` | Day-36 confirmed via tick-21 instrumentation |
| ProteinProcessingII | `protein.enzyme_counts` | Suspect; runs same pattern |
| ProteinModification | `protein.unmodified_counts`, `complex.counts` | Suspect; runs same pattern |
| RNAProcessing | `protein.counts`, `complex.counts` | Suspect; runs same pattern |
| RNAModification | `protein.counts`, `complex.counts` | Suspect; runs same pattern |
| tRNAAminoacylation | `protein.counts`, `complex.counts` | Suspect; runs same pattern |

## Combined L2.1/L2.2 validation surface

Of 28 processes:

| Category | Count | Notes |
|---|---:|---|
| Class A only (trace-hint short-circuits) | ~8 | Replication, ReplicationInit, RNADecay, ProteinDecayLight, Transcription, TerminalOrg, Translation, TranslationV3 |
| Class B only (port-mismatch) | ~5 | RNAProcessing, RNAModification, tRNAAminoacylation, ProteinModification, ProteinProcessingII |
| Both A and B | ~3 | DNASupercoiling, FtsZ, ChromosomeCondensation (have hint short-circuits AND read ports outside observables) |
| Hidden-read-surface processes | ~5 | Cond, Seg, ReplInit, Repl, HostInt, TermOrg, ChromSeg — read `chromosome.*` / `cell.*` ports that should be injected via `hidden_read_surface` spec entry. Status depends on whether the spec declares the right channels. |
| Clean (no Class A, B, or hidden-port reads) | ~7 | DNADamage, DNARepair, MacromolComplex, ProteinActivation, ProteinFolding, ProteinProcessingI, RibosomeAssembly, possibly Cytokinesis |

**Net: only ~7-10 of 28 processes have unambiguously-honest L2.1 PASSes.**

The other 18-21 processes are passing L2.1 via one of:
- Trace-hint short-circuit (biology bypassed)
- Port-mismatch coincidental zero (biology trivially returns 0)
- Hidden-read-surface coincidental zero (similar to Class B but uses
  hidden ports that may or may not be properly injected)

## How does L2.1 sign-off rubric allow this?

L2.1 acceptance criterion: **bit-identity per tick** between OC's
`next_update` output and Karr's recorded `states_after`. This is the
weakest possible behavioral test:

1. It does NOT check that OC's biology executed correctly. It only checks
   the OUTPUT matches.
2. If OC returns `{}` (empty update) and Karr's tick delta is `[0,...,0]`,
   they match — regardless of whether OC's biology actually ran or was
   short-circuited by a port-read-zero or hint-echo.
3. There's no requirement that OC's RNG advanced, that OC's allocator
   computed budgets, that OC's per-species samplers fired, etc.

The rubric assumes that if OC matches Karr at every tick, the underlying
biology is correct. That assumption fails when the matching is achieved
through degenerate paths.

## Implications for our 22 "L2.2 in-scope GREEN" claim

L2.2 inherits L2.1's bit-identity per-tick check at its core (plus
distributional checks for stochastic processes). If a process's L2.1
PASSes coincidentally, its L2.2 PASS likely also includes the same
coincidence. The 22/22 L2.2 GREEN status is now suspect for any process
in Class A, B, or hidden-port categories.

## What needs to change

The fix is NOT to retroactively unwind 22 PASS claims. The fix is to
strengthen the rubric and add a new check class:

**Proposed L2.1 / L2.2 supplement (call it L2.1+ / L2.2+):**
For each process, in addition to bit-identity:
1. **Read-surface coverage**: every state port the process reads in
   `next_update` must be one of (a) in declared `observables`, (b) in
   declared `hidden_read_surface`, or (c) the canonical `substrates_allocated`
   port. Other reads fail the check.
2. **Non-trivial fire rate**: track the fraction of ticks where the process
   produced a non-empty update across the test run. If 0%, the test passes
   trivially and should be skipped/marked-unproven rather than PASS.

These two checks would expose Class A, Class B, and hidden-port-coincidence
failures without rewriting all 22 process tests.

## Day-36 short-term action

1. **Document this finding** in `plan.md` operational handoff
2. **Add the supplement-rubric checks** to the L2.1 / L2.2 harnesses
3. **Re-run L2.1 / L2.2 with the new rubric** and surface the actual
   honest-pass count (likely closer to 7-10 of 28, not 22 of 22)
4. **For the Class B port-mismatch bugs**: each needs a per-process
   investigation to determine what Karr's MATLAB does that OC is missing.
   These are real biology gaps that L2.1's weak rubric hid.

## Provenance

- Trigger: operator question after Translocation tick-21 binary-search
  probe (Day-36, `scripts/probe_translocation_binary_search.py`).
- Audit: `scripts/probe_port_mismatch_audit.py` (AST-light text scan of
  `karr_*.py` next_update bodies).
- Cross-reference: `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md` (Day-35
  trace-hint catalog).
- The "rubber-duck Sonnet 4.6 B3 critique" (Day-35 EOD) was generally
  correct about the coincidence pattern; we initially audited only L2.5
  PASSes and found them genuine, but L2.1 PASSes are where the coincidence
  pattern actually lives.
