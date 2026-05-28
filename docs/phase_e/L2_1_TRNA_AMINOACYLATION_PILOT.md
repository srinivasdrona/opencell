# L2.1 Bit-Identity Pilot — tRNAAminoacylation

First L2.1 (deterministic bit-identity) probe under the three-rung L2-green framework.

## Framework

- **L2.0** observable-schema audit (static): karr ⊆ oc.
- **L2.1** deterministic bit-identity (dynamic): per-tick `next_update` vs `states_after`.
- **L2.2** distributional fidelity (stochastic): pre-registered σ bands.

L2.1 is only meaningful where the per-process trace `.mat` has a populated
`states_after`. Audit of 28 `_100ticks.mat` files (see L2.0 audit) found
**7 with empty `states_after`** (ChromosomeCondensation, DNASupercoiling,
RNADecay, ReplicationInitiation, Replication, Transcription, Translation).
Those processes are L2.1 N/A until the oracle is re-extracted.
The remaining 21 are L2.1-viable.

## Pilot target

**tRNAAminoacylation** (KarrTRNAAminoacylationProcess).
Chosen because:
- `states_after` populated for all 4 observables.
- Polished L2 replay test already shipped under `l2-trna-aminoacylation`
  worktree (`tests/vivarium/test_karr_trna_aminoacylation_l2_replay.py`).
- Known Tier-0 ontological-failure candidate from ensemble work
  ("gates AA recycling"), so a non-trivial finding is expected.
- Substrate footprint is small (30 substrates), so a first-tick mismatch
  is unambiguously interpretable.

## Verdict

🔴 **RED at tick 0, observable=substrates, index=2 (AMP).**

| Field | Value |
|---|---|
| Tick | 0 |
| Observable | `substrates` |
| Substrate index | 2 |
| Substrate WID | **AMP** |
| OC `next_update` after | 2080.0 |
| Karr `states_after` | 2117.0 |
| Diff (OC − Karr) | **−37** |

Test invocation (rng_seed=0 parametrisation, fails on the first assertion):

```bash
cd /mnt/e/opencell-worktrees/l2-trna-aminoacylation
python -m pytest tests/vivarium/test_karr_trna_aminoacylation_l2_replay.py -x
```

**Hardened-test status (post-critique):** the test was hardened per
`docs/prompts/FIX_TEMPLATE_L2_REPLAY.md` (added `freeRNAs` and
`aminoacylatedRNAs` observables, integer-exact compare, WID-length
guard). The RED reproduces identically at tick 0 substrates[2]=AMP with
diff=−37. Confidence in the AMP-37 finding: **HIGH**. The hardening
also narrows the per-tick search space so any downstream RNA mismatch
will now surface instead of being silently skipped.

## Biological interpretation

tRNA aminoacylation stoichiometry is `aa + ATP + tRNA → aa-tRNA + AMP + PPi`.
Each successful charging event produces exactly one AMP. The −37 AMP
shortfall at tick 0 implies OC executes ~37 fewer charging events than
Karr during the first tick, despite consuming the same `states_before`.

Because tick 0 happens before any cumulative drift, this is a
**first-update bug**, not a drift bug. Candidate root causes:
- AA-availability gating cutoff (e.g., a `>` vs `>=` boundary on the
  amino-acid request vector).
- Off-by-one in the per-amino-acid synthetase loop.
- Different rounding convention in count integralisation.
- A single AA bucket that OC declares "no ATP available" where Karr
  proceeds.

The other 36 substrates and the 21-element enzyme/boundEnzyme observables
were not yet evaluated (test halts on first mismatch).

## What this proves about the framework

- L2.0 alone is silent on this kind of bug (the schema audit returns
  AMBER for tRNAAminoacylation — karr ⊆ oc holds).
- L2.1 surfaces it deterministically at tick 0, with a specific
  substrate WID and a signed magnitude. No statistical machinery needed.
- L2.2 (distributional) would have masked it inside the noise floor.

This is the rung-design payoff: L2.1 produces a debugging lead, not a
verdict-only signal.

## Next steps

- Triage the AMP-37 mismatch against the M1 per-reaction oracle.
- Run a second L2.1 probe (MacromolecularComplexation) to validate the
  methodology generalises.
- Sweep the remaining 19 populated-after processes; collate the
  first-mismatch table.

## Second probe (same session): MacromolecularComplexation

To verify L2.1 is not trivially red on every process, ran the
`l2-macromolecular-complexation` worktree's polished replay test
immediately after the tRNAAminoacylation finding:

```bash
cd /mnt/e/opencell-worktrees/l2-macromolecular-complexation
python -m pytest tests/vivarium/test_karr_macromolecular_complexation_l2_replay.py -x
```

Result: **🟢 GREEN, 1 passed in 59.56s, 100 ticks × all observables, bit-identical.**

This is the first L2.1 GREEN process. The contrast (tRNAAminoacylation
RED at tick 0 substrate AMP, MacromolecularComplexation GREEN through
all 100 ticks) confirms the L2.1 rung does what it's designed to do:
distinguish processes that fully agree with the Karr oracle from those
that don't, with concrete first-mismatch coordinates when they disagree.

## Mutated-tick audit (2026-05-29, post template-meta-critique + Codex dry-run)

A GPT-5.5 meta-critique of the templates (10 probes) found 5 load-bearing
gaps, which were closed. A Codex executable dry-run of the templates
against the hardened tRNAAA test then surfaced a separate, harder finding:
**none of the three pilot traces was being audited for whether ticks
actually exercised the process.**

The script `scripts/audit_l2_trace_mutation.py` counts per-observable how
many of the 100 ticks have a nonzero `states_after - states_before` delta.
Result, exact:

```
=== tRNAAminoacylation ===
  substrates                    1/100 nonzero ticks
  enzymes                       0/100
  boundEnzymes                  0/100
  freeRNAs                      1/100
  aminoacylatedRNAs             1/100

=== MacromolecularComplexation ===
  substrates                    0/100
  enzymes                       0/100
  boundEnzymes                  0/100
  complexs                      0/100

=== RNAModification ===
  substrates                    0/100
  enzymes                       0/100
  boundEnzymes                  0/100
  modifiedRNAs                  0/100
  unmodifiedRNAs                0/100
```

This collapses two prior verdicts to N/A and re-grades tRNAAA's
confidence:

| Process | Pre-audit | Post-audit | Reason |
|---|---|---|---|
| tRNAAminoacylation | 🔴 RED HIGH (100 ticks integer-exact) | 🔴 **RED, real but 1-tick coverage** | Only tick 0 is mutated; ticks 1-99 are no-op for every observable. The AMP-37 finding is genuine but rests on a single tick, not 100. |
| MacromolecularComplexation | 🟡 GREEN on mutated ports | ⚪ **L2.1 N/A — 100-tick no-op trace** | Every observable's `states_after == states_before` for all 100 ticks. The earlier "GREEN" was vacuous — any test that doesn't actively misbehave would pass. |
| RNAModification | ⚪ L2.1 N/A (no-op `unmodifiedRNAs`) | ⚪ **L2.1 N/A confirmed across all 5 observables** | No observable mutates in any tick. |

### Exemplar hardening applied (worktree `audit/l2-trna-aminoacylation`)

The tRNAAA test was hardened per the Codex dry-run findings:

1. **`_PASS_THROUGH` + `_SCRATCH_RESET` manifests** at module scope
   (machine-readable; replaces comment-only labels).
2. **Delta-integrality assertion** (`_assert_delta_integral`) on every
   emitted delta dict before `_apply_update` mutates state (Rule 2 clause 4).
3. **Pre-loop non-triviality probe** (`_audit_trace_mutated_ticks`) with
   `pytest.skip` on a 0/100 trace and a printed trace-coverage annotation
   on every run (Rule 6 / Gate 5).

Reran: RED reproduces identically (tick=0, substrates idx=2, AMP, diff=−37).
The test now prints `L2.1 trace coverage (mutated ticks per observable,
100 total): {'substrates': 1, 'freeRNAs': 1, 'aminoacylatedRNAs': 1}` so
the verdict is paired with the actual trace coverage, not asserted as
"100-tick HIGH" on a 1-tick-active trace.

### Mechanical lint shipped

`scripts/lint_l2_replay.py` enforces 6 mechanical checks (Rules 1, 2, 4b,
6, 7 + `_PASS_THROUGH` provenance taint via AST walk). Result on the 3
pilot tests:

- tRNAAminoacylation (hardened): **PASS** all 6.
- MacromolecularComplexation: FAIL on Rules 1, 2, 4b, 6.
- RNAModification: FAIL on Rules 1, 2, 4b, 6.

## Scoreboard after mutated-tick audit

| Rung | Status | Real coverage |
|---|---|---|
| L2.0 | Done | 28/28 audited, 0 G / 24 A / 4 R |
| L2.1 | Pilot validated on 1 process, 1 tick | 1 hard RED with 1-tick coverage (tRNAAA, AMP-37); 2 prior verdicts collapsed to N/A (MacromolComplex + RNAMod, 100-tick no-op traces); 7 N/A by empty-after; 18 untested |
| L2.2 | Not started | Framework defined |
