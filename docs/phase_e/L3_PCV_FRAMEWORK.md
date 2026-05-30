# L3 Producer-Consumer-Validator (PCV) framework

**Status**: deferred until L2 is fully GREEN (per operator discipline: never start the next rung before the previous is closed).

**Date**: 2026-05-30. **Session**: 5c51d44b-5a9f-4b23-85ff-0fddaadf2212.

## Why L3 exists

L2.1 verifies each process in isolation: `OC_process.next_update(state_t) == Karr_process.state_after`. L2.2 verifies distributional fidelity per process. Neither catches **integration bugs** — cases where two processes individually pass against their oracle trace but disagree about the *meaning* of shared state when wired together inside the same cell.

### What L3 catches that L2 cannot

- **Index/WID drift between producer and consumer.** Transcription writes `rna_counts[X]`, RNAProcessing reads `rna_counts[Y]` for what should be the same species. Each passes its own L2.1 because its oracle trace happens to be internally consistent. Wired together, they diverge.
- **Orphan deltas.** Process A writes a state change nothing else consumes.
- **Missing exchange contracts.** Process A implicitly assumes process B subtracted a substrate B doesn't actually subtract.
- **Mass / charge / atom balance violations across multi-step chains.** NTPs consumed by Transcription should equal NMPs released by RNADecay (steady state), to within reabsorption.
- **Stoichiometric coupling violations.** ATP turnover across all consumers should match Metabolism's production within FBA tolerance.

## PCV set definition

A PCV set is a closed integration loop with three roles:

- **Producer(s)** — process(es) that generate a state delta into a shared pool.
- **Consumer(s)** — process(es) that read / transform / dispose of that delta.
- **Validator** — a *conservation law* checked across the loop boundary. Validators are not processes; they are invariants (mass balance, charge balance, integer-count closure, FBA exchange contract).

L3 GREEN for a PCV set = (a) all member processes are L2.1 GREEN AND (b) the validator invariant holds within tolerance over an N-tick joint simulation.

## Candidate PCV sets (8)

Ranked by L2.1-GREEN-coverage readiness as of 2026-05-30 (9/28 GREEN). Coverage will change as L2.1 progresses — re-rank when L2 closes.

### PCV-4 · DNA maintenance · **2/2 GREEN, ready first**
- **Producer**: DNADamage
- **Consumer**: DNARepair
- **Validator**: lesion count steady-state (production = repair); dNTP cost balance per repair event
- **Smallest possible L3 loop. Recommended L3 pilot.**

### PCV-2 · Protein lifecycle · 5/7 GREEN (largest near-ready)
- **Producer**: Translation
- **Consumers**: ProteinProcessingI, ProteinProcessingII, ProteinModification, ProteinFolding, ProteinTranslocation, ProteinActivation, ProteinDecay
- **Validator**: AA balance — ProteinDecay's released AAs ≈ Translation's consumed AAs at steady state; tRNAAminoacylation charging rate ≈ Translation's tRNA consumption rate
- **Currently RED**: ProteinProcessingI, ProteinProcessingII (WIP), ProteinActivation

### PCV-1 · RNA lifecycle · 1/4 GREEN
- **Producer**: Transcription
- **Consumers**: RNAProcessing → RNAModification → RNADecay
- **Validator**: NTP-in / NMP-out closure; processed RNA pool serves Translation correctly
- **Cross-link**: feeds PCV-2 (Translation consumes mature RNAs)

### PCV-3 · DNA replication · 1/4 GREEN (DNA-side coverage low)
- **Producer**: ReplicationInitiation → Replication
- **Consumers**: ChromosomeCondensation, ChromosomeSegregation, Cytokinesis
- **Validator**: dNTP balance; integer chromosome count at division event; genome doubling exactly once per cycle

### PCV-5 · DNA topology · 0/1 GREEN
- **Producer/Consumer (self-loop)**: DNASupercoiling (gyrase + topoisomerase introduce/relax twist)
- **Validator**: linking number conservation; supercoiling density within physiological band
- **Edge case**: not a clean PCV — one process is both source and sink

### PCV-6 · Energy backbone · 1/1 producer GREEN, ~everything consumes
- **Producer**: Metabolism (FBA solves for all NTP / dNTP / AA / ATP fluxes)
- **Consumers**: every other process
- **Validator**: ATP turnover within FBA tolerance; no metabolite pool drifts unboundedly
- **This is the cross-cutting validator more than a discrete PCV set.** Run it across ALL other PCV sets as a meta-check.

### PCV-7 · Division · 0/2 GREEN
- **Producer**: FtsZPolymerization (divisome assembly)
- **Consumer**: Cytokinesis (uses assembled divisome)
- **Validator**: divisome stoichiometry at division time; single division event per cell cycle

### PCV-8 · Regulation · 0/3 GREEN
- **Producer**: HostInteraction → TranscriptionalRegulation (TF binding determined by environmental signals)
- **Consumer**: Transcription (rates modulated by TF occupancy)
- **Validator**: TF binding occupancy correlates with transcription rate per regulated gene
- **Cross-link**: feeds PCV-1 (modulates RNA production)

## Cross-cutting validators

These are not PCV sets but invariants the L3 harness should check **across** any wired-together simulation:

1. **Atom balance** (C, H, N, O, P, S) globally — mass-in ≈ mass-out + biomass accumulation.
2. **Charge balance** — net charge conservation.
3. **ATP turnover ceiling** — total ATP consumption ≤ Metabolism's ATP production rate.
4. **Integer closure** — no fractional counts in any pool after `next_update`.
5. **Pool non-negativity** — no state variable goes below zero.

## Sequencing when L2 fully GREEN

1. **L3 harness design** — extend the L2.1 replay harness to run N processes per tick, sharing state. ~1-2 weeks.
2. **L3 pilot on PCV-4** (DNADamage + DNARepair) — proves harness; 2 processes is the simplest non-trivial loop.
3. **L3 pilot on PCV-1** (RNA lifecycle) — proves the multi-step chain pattern.
4. **L3 sequential coverage**: PCV-1, 2, 3, 4, 7, 8 in order of readiness.
5. **PCV-5 (DNASupercoiling self-loop)** — special case, may need bespoke check rather than producer-consumer format.
6. **PCV-6 (Energy)** runs as a *meta-validator* over every PCV set, not as a discrete L3 closure.

## Decision discipline (operator rule)

**Do not start L3 work — design, harness, pilot, anything — before L2 is fully GREEN.**

Rationale: building an integration layer on a shifting per-process foundation invites debugging two layers of bugs simultaneously. Every per-process patch that lands after L3 starts will potentially invalidate L3 results. Keep the foundation stable, then build up.

## Open questions for L3 design (defer answers until close to L3 start)

- What N (joint-simulation tick count) is enough to surface mass-balance violations? Per-tick check vs N-tick aggregate?
- Does L3 use Karr's full cell-cycle trajectory as the joint-oracle, or just run OC processes wired together and validate invariants without a Karr-side reference?
- Tolerance for atom balance — exact integer vs ε-fraction? (Probably integer for counts, ε for fluxes.)
- Should we re-rank PCV sets by L2.2 closure too, not just L2.1?
- Does PCV-6 (Energy meta-validator) need its own pre-registered tolerance bands?

---

**Pointer**: this framework was sketched live during the L2.1 sweep when 9/28 GREEN. Re-validate the ranking at the moment L2 closes — process status may have shifted.
