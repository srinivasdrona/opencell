# L2.2 Strict-Rubric Baseline — Day-37 (2026-06-23)

**Status:** L2.2 re-audit complete. Of the 22 in-scope GREEN claims in
`docs/phase_e/PROCESS_STATUS_ALL_29.md` Table 1, **at most 4 are honestly
validated** under the strict rubric. The other 18 are some flavor of
laundered, suspect, or uninformative.

## Strict L2.2 rubric

A process's L2.2 PASS can only be GENUINE if all four conditions hold:

1. **L2.1 strict-rubric verdict is GENUINE.** L2.2's distributional comparison
   inherits L2.1's per-tick check; if L2.1 trivially passes (returns empty),
   L2.2 trivially passes too.
2. **No trace-hint short-circuit in process source.** Per Day-35 catalog
   (`docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md`), 13 processes echo `state["trace_hint"]`
   values back to output, bypassing biology when hint is present.
3. **No port-mismatch read.** Per Day-36 catalog
   (`scripts/probe_port_mismatch_audit.py`), 6 processes read state ports
   their declared `observables` don't populate.
4. **L2.2 runner does NOT feed `overlay_trace_after_hint` for this process.**
   Per grep of `_l2_2_design_a_runner_helpers.py`, only Transcription and
   Translation runners explicitly inject `trace_after_hint`.

## Day-37 baseline (22 processes)

| Verdict | Count | Processes |
|---|---:|---|
| **LAUNDERED_VIA_HINT_FEED** | 2 | Transcription, Translation |
| **SUSPECT_LAUNDERED** | 12 | Replication, ReplicationInitiation, DNASupercoiling, FtsZ, RNADecay, RNAProcessing, tRNAAminoacylation, ProcII, ProteinModification, ProteinTranslocation, ProteinDecay, Metabolism |
| **UNINFORMATIVE** | 4 | DNADamage, Cytokinesis, RNAModification, RibosomeAssembly |
| **PROVISIONAL_GENUINE** | 4 | **DNARepair, ProcI, ProteinFolding, MacromolecularComplexation** |

### LAUNDERED_VIA_HINT_FEED (2)

The L2.2 design_a runner explicitly calls `overlay_trace_after_hint` for these
processes' `substrates`, `boundEnzymes`, and `RNAs` channels
(`_l2_2_design_a_runner_helpers.py:1396-1413` for Transcription,
`:1499-1511` for Translation). The hint IS Karr's recorded value. The
biology's trace-hint short-circuit echoes the hint back. Match is tautological.

Why these two are special: they're the first L2.2 gates that were ever
authored (Day-21/22), at a time when the harness still trusted the per-process
trace-hint short-circuit pattern. The pattern was formalized as "5x use,
durable architectural decision" in the Day-19 audit but never re-evaluated
after the Day-35 short-circuit catalog was complete.

### SUSPECT_LAUNDERED (12)

L2.1 strict-rubric is FAIL or the process has a port-mismatch read.
L2.2 still claims PASS. The mechanism is unclear because the L2.2 runner
does NOT feed trace_hint for these processes. The most likely explanations:

a. **L2.2 runner's per-process state overlay accidentally populates the
   mismatched ports.** For example, `_run_protein_modification_tick` may
   overlay `unmodifiedMonomers` into `protein.unmodified_counts` — which is
   exactly the port the biology reads, masking the L2.1 read-surface gap.

b. **The L2.2 acceptance threshold is loose enough that all-zero OC
   distribution matches non-zero Karr distribution.** Distributional checks
   (KS test, Wasserstein) have tolerance parameters. If the tolerance is
   set to accept large divergences, the test always passes.

c. **The L2.2 claim is stale** — generated against an older code path that
   DID feed hints, and not re-run since the hint feeds were removed.

To distinguish, each SUSPECT_LAUNDERED process needs an empirical run of
its L2.2 ensemble with `disable_trace_hints` equivalent + state overlay
restricted to declared observables only. Multi-week scope.

### UNINFORMATIVE (4)

Karr's trace shows zero recorded activity for the 100-tick window. L2.2
distributional comparison reduces to "0 distribution matches 0 distribution".
The 4 processes are cell-cycle gated (Cytokinesis, RibosomeAssembly) or
event-rare (DNADamage, RNAModification). Their L2.2 PASS is vacuous;
they've never been validated.

### PROVISIONAL_GENUINE (4) — the actual upper bound on honest L2.2

| Process | L2.1 strict | Port mismatch? | Hint-fed? |
|---|---|---|---|
| DNARepair | GENUINE | No | No |
| ProteinProcessingI | GENUINE | No | No |
| ProteinFolding | GENUINE | No | No |
| MacromolecularComplexation | GENUINE | No | No |

These four pass all four strict criteria. To upgrade to VERIFIED_GENUINE,
each needs an empirical L2.2 distributional run with `disable_trace_hints`
that still passes the KS + Wasserstein thresholds. Estimated ~30-60 min
per process to re-run and verify.

## Implications

1. **The "22 of 28 in-scope L2.2 GREEN" claim collapses to at most 4 of 22
   under the strict rubric.** That's 18% honest, not 100%.
2. **The 13 trace-hint short-circuit processes (Day-35 catalog) have 13
   downstream L2.2 PASS claims that need investigation** — 2 are
   LAUNDERED_VIA_HINT_FEED for sure, 11 are SUSPECT_LAUNDERED via different
   mechanisms.
3. **The 6 port-mismatch processes (Day-36 catalog) have 6 downstream L2.2
   PASS claims that are also suspect** — even when L2.1 strict says GENUINE,
   the read-surface gap may be masked by the L2.2 runner's overlay.
4. **The L2.2 design_a runner needs refactoring to be honest:**
   - Remove the explicit `overlay_trace_after_hint` calls for Transcription
     and Translation
   - Restrict per-process state overlay to declared observables (don't
     populate ports outside the observables list)
   - Add fire-rate check (parallel to L2.1 strict)
   - Add distributional-non-trivial check (Karr's ensemble must show some
     variance or non-zero mean)

## How the baseline is enforced

`tests/vivarium/test_l2_2_strict_rubric.py` pins each of the 22 verdicts.
The classification logic lives in `scripts/probe_l2_2_strict_audit.py`.
CI fails if any verdict drifts. Drifts happen via:
- Trace-hint short-circuit removed from a process → moves SUSPECT to PROVISIONAL
- Port-mismatch fixed → moves SUSPECT to PROVISIONAL
- Hint feed removed from L2.2 runner → moves LAUNDERED to SUSPECT/PROVISIONAL
- L2.1 strict verdict changes → cascades to L2.2

## Provenance

- Audit script: `scripts/probe_l2_2_strict_audit.py`
- Enforced test: `tests/vivarium/test_l2_2_strict_rubric.py`
- Source claims: `docs/phase_e/PROCESS_STATUS_ALL_29.md` Table 1
- L2.1 baseline: `docs/phase_f/L2_1_STRICT_RUBRIC_BASELINE.md`
- Short-circuit catalog: `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md`
- Port-mismatch catalog: `scripts/probe_port_mismatch_audit.py`
- Trigger: operator instruction Day-37: "let's start with the re-audit of L2.2
  in-scope Greens to establish the base line we will operate from."
