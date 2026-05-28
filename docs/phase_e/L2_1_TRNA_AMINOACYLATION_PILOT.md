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

## Critique-driven re-classification (2026-05-28 ~22:50 IST)

A GPT-5.5 critique under `docs/prompts/CRITIQUE_L2_REPLAY.md` audited
the three pilot tests against the 5 gates. Findings flipped two of the
three verdicts:

| Process | Pre-critique | Post-critique | Reason |
|---|---|---|---|
| tRNAAminoacylation | 🔴 RED (AMP-37) | 🔴 **RED stands**, HIGH confidence | Hardening per FIX_TEMPLATE_L2_REPLAY reproduces the mismatch with integer-exact compare and full observable coverage. |
| MacromolecularComplexation | 🟢 GREEN | 🟡 **GREEN on mutated ports only** | `enzymes` and `boundEnzymes` are not process ports (not in schema, not in topology); those assertions were pass-through and inflated apparent coverage. GREEN on `substrates` and `complexs` is HIGH confidence. |
| RNAModification | 🟢 GREEN | ⚪ **L2.1 N/A — no-op trace** | Trace has `unmodifiedRNAs` all zero, production hits `return {}` at karr_rna_modification.py:225-226, flux machinery never exercised. Process also reconstructed every tick, resetting RNG. Not a real verdict; needs an adversarial trace or extended `.mat`. |

The critique anchors are codified as Rules 1-7 in
`docs/prompts/FIX_TEMPLATE_L2_REPLAY.md` and Gates 1-5 in
`docs/prompts/CRITIQUE_L2_REPLAY.md`.

## Scoreboard after critique

| Rung | Status | Real coverage |
|---|---|---|
| L2.0 | Done | 28/28 audited, 0 G / 24 A / 4 R |
| L2.1 | Pilot validated | 1 hard RED (tRNAAA, AMP-37), 1 partial GREEN (MacromolComplex substrates+complexs), 1 N/A (RNAMod no-op); 7 N/A by empty-after; 18 pending |
| L2.2 | Not started | Framework defined |
