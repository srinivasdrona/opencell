# L2.2 Laundering vs Deterministic Convergence — Design Note

**Status:** authoritative design note for the L2.2 distributional gate's
`PRIMARY_CHANNEL_ORACLE_LAUNDERING` detector. Anchored to the Day-25
(2026-06-12) H12 confirmation probe.

**Provenance:** session `5c51d44b-5a9f-4b23-85ff-0fddaadf2212`. Hypothesis
map authored after the H11 (parallel branch in `next_update`) probe ruled
out the original laundering hypothesis. H12 confirmation probe at commit
hash TBD (one-off `.probe_h12.py`, not retained as a permanent script).

---

## TL;DR

The `PRIMARY_CHANNEL_ORACLE_LAUNDERING` detector — added to the runner on
2026-06-12 (`d1330f1`, generalized in `408bf96`) — flags any case where
`oc_after == karr_after` exactly on the primary channel as oracle
laundering and flips the channel verdict to FAIL. This is **necessary
but not sufficient** for catching real laundering.

The H12 probe confirmed that for **MacromolecularComplexation**, OC's
`_closed_form_bounds(sub_avail, stoich)` returns bit-identical results to
Karr's stochastic `_per_cluster_mc` on **100% of sampled ticks (50/50)
including all 7 nontrivial ticks where Karr actually formed complexes**.
The match is not oracle laundering — it is **deterministic algorithm
convergence at the biology's bounded limit**: when substrate is the
binding constraint, the stochastic algorithm produces the same integer
answer as the deterministic upper-bound algorithm on every sample.

Therefore the 5 currently-flagged "launderers"
(MacromolecularComplexation, ProteinProcessingI, ProteinProcessingII,
tRNAAminoacylation, ProteinFolding) are likely all **false positives of
the same kind** — their OC implementations use closed-form paths that
converge to Karr's stochastic result by biology, not by oracle leakage.

## What the H11 + H12 probes told us together

**H11 probe (failed first attempt at 317k tokens, salvaged at 6 min; ran
again 2026-06-12):**

- `next_update` has no oracle-detecting branch.
- `_per_cluster_mc` breaks early on `ub <= 0` for the sampled ticks.
- Yet OC's after-vector matches Karr's after-vector exactly on those ticks.

The probe instrumented **RNG calls**, not **return-value content**. It
established that no stochastic call fires, but did not establish what
`next_update` returns.

**H12 probe (in-session manual, 2026-06-12 19:30 IST):**

- Computed `_closed_form_bounds(sub_avail, stoich)` directly for the same
  per-seed inputs the SUT would see.
- Compared closed-form output against `(oracle_after - oracle_before)`
  per (seed, tick) sample.
- 50/50 overall match, 7/7 nontrivial-tick match.

Together: the SUT's closed-form deterministic path produces the answer
Karr's stochastic algorithm produced, for the same per-seed input,
without using the RNG. The "laundering" is biology convergence.

## Why this happens (mechanism)

`_closed_form_bounds` (line 80, `karr_macromolecular_complexation.py`)
computes the maximum number of each complex that can be assembled given
available substrate:

```python
out[cidx] = int(np.min(sub_avail[active] // col[active]))
```

This is the **integer-stoichiometric upper bound**. For one cluster of
the complexation network it gives "how many complete units of each
complex can the substrate pool support."

Karr's MATLAB `evolveState_Complexation` uses a stochastic Monte Carlo
algorithm bounded by the same constraint. When substrate is non-limiting
relative to the assembly rate (the typical regime for established
cellular pools), the stochastic samples converge to the upper bound on
every tick. Two algorithms, same per-seed input, same per-seed output —
not because they share data, but because the biology has a single
deterministic answer at the operating point.

The H12 probe confirmed this at 100% match on the sampled (seed, tick)
window for MacromolecularComplexation cluster 1.

## Why the legitimate-determinism carve-out doesn't fire

The existing carve-out
`_primary_channel_oracle_determinism_legitimate_warning` requires
**`before == after`** for ALL samples (i.e., Karr did nothing in any
tick of the smoke window). For Macromol, Karr does form complexes on
some ticks (7 of 50 in the probe sample), so `before != after` on those
ticks, so the carve-out's second check fails, so the laundering detector
fires.

The carve-out is correct for cases where the SUT genuinely did nothing
because the biology had nothing to do. It does not cover the H12 case
where the SUT did something and got the same answer Karr got because the
biology has one answer.

## What the fix is

Three components:

### 1. Catalog field: `closed_form_dominant`

Per-process flag in `PROCESS_CATALOG.yaml`. Three values:

- `confirmed` — the process's primary channel update is computed via a
  deterministic closed-form path that has been empirically shown
  (via an H12-style probe) to match Karr's stochastic output on every
  nontrivial tick of a sampled window. The L2.2 laundering detector
  treats this as a legitimate-convergence case, not a FAIL.

- `candidate` — the process has a closed-form path in its SUT but the
  H12-style probe has not been run. The L2.2 laundering detector still
  flips the channel verdict to FAIL but appends a `LIKELY_CONVERGENCE`
  qualifier. Operator action: run the probe; promote to `confirmed` if
  the match rate is 100% on nontrivial ticks.

- `false` (default) — no closed-form path, or the closed-form path has
  been shown not to converge to Karr's stochastic output. Laundering
  detector behaves as it does today (FAIL on exact match).

### 2. Runner update: detector consults the catalog

`_primary_channel_oracle_laundering_warning` returns the existing string
unchanged but the call site in `run_design_a` checks the catalog:

```python
if primary_oracle_laundering_warning is not None:
    closed_form_state = catalog_entry.get("closed_form_dominant", "false")
    if closed_form_state == "confirmed":
        # Demote to informational; this is biology convergence, not laundering.
        warnings.append(
            "PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched the Karr "
            f"oracle exactly on primary channel={primary_channel}; per catalog "
            "this process has a closed_form_dominant path that converges to "
            "Karr's stochastic output. See docs/phase_f/l2_2_design_a/"
            "LAUNDERING_VS_CONVERGENCE.md for the H12 anchor."
        )
        # Do NOT flip the verdict to FAIL.
    else:
        warnings.append(primary_oracle_laundering_warning)
        if closed_form_state == "candidate":
            warnings.append(
                "LIKELY_CONVERGENCE: this process is flagged closed_form_dominant: "
                "candidate but has not been H12-probed. Run a probe before "
                "interpreting the laundering FAIL as a real wiring issue."
            )
        if not channel_payloads[primary_channel].get("is_event_channel", False):
            channel_payloads[primary_channel]["verdict"] = "FAIL"
```

### 3. Per-process classification

Based on code inspection of each SUT's `next_update`, the initial
classification is:

| Process | `closed_form_dominant` | Rationale |
|---|---|---|
| MacromolecularComplexation | `confirmed` | H12 probe 2026-06-12: 50/50, 7/7 nontrivial. |
| ProteinProcessingI | `candidate` | SUT uses bounded-by-water cleavage; mathematically deterministic upper bound likely converges. Probe to confirm. |
| ProteinProcessingII | `candidate` | Same pattern as PPI. |
| tRNAAminoacylation | `candidate` | aaRS rate-limited synthesis; deterministic upper bound likely converges at established pool levels. |
| ProteinFolding | `candidate` | Folding rate-limited by chaperone availability; closed-form likely converges. |
| All other in-scope processes | `false` | Either no closed-form path in SUT, or empirical L2.2 PASS verdict already shows non-trivial W1 (e.g., Transcription, Translation, RNADecay, etc.) |

## What this means for the L2.2 honest scoreboard

Pre-H12 (2026-06-12 18:25):
- 5 honest greens
- 5 caught launderers (held back from merge)
- 4 unwired (or wiring bugs)
- 3 Day-22 fanout to re-do

Post-H12 if `candidate` cases probe-out as `confirmed`:
- 10 honest greens (5 prior + 5 promoted from "caught launderers")
- 0 caught launderers (all 5 reclassified as legitimate convergence)
- 4 unwired (unchanged)
- 3 Day-22 fanout to re-do (unchanged)

If even some `candidate` cases probe-out, the bottom number improves.

## What this does NOT do

This design note does not change the L2.1 bit-identity gate. L2.1 already
tests per-tick exact match; processes that are `closed_form_dominant`
pass L2.1 trivially. The L2.2 distributional gate was attempting to add
distributional evidence on top of L2.1; for closed-form-dominant
processes, **L2.2 does not add evidence over L2.1** because the
distributional comparison reduces to the deterministic comparison.

This is a limitation of Design A's per-tick replay structure, not a flaw
in the H12 probe finding. A future L2.2 design (B or later) that does
NOT seed-couple OC's input to Karr's per-tick before-state would be able
to distinguish OC's distribution from Karr's at the macroscopic level
for these processes. That is out of scope for this design note.

## What gate this opens for operator action

After this patch lands:

1. Run an H12-style probe on PPI, PPII, tRNAAA, PFolding (4 processes,
   ~5 minutes each via reused probe template).
2. For each `confirmed`, update the catalog; merge the corresponding
   batch branch (held back as of 2026-06-12 13:00 IST).
3. For each that doesn't confirm, investigate the actual leakage path
   (which would then be a real bug, not biology convergence).

## Caveats

- The H12 probe used 50 samples (5 seeds × 10 ticks) on Macromol. A
  fuller probe across all 50 seeds × all 100 ticks would harden the
  "100%" claim, but the 7/7 nontrivial-tick match is already strong
  evidence that the convergence holds across the operating regime.
- The closed-form path in Macromol applies to **cluster 1 only**;
  cluster 2+ always runs `_per_cluster_mc`. If Karr's stochastic
  cluster-2 differs from OC's stochastic cluster-2 by RNG-stream choice,
  cluster-2 complexes would show non-zero W1 in the smoke. They didn't.
  Most likely cluster 2 has very few complexes (sparse formation), so
  zero formation on both sides matches trivially. A follow-up probe
  could measure cluster-2 formation rate explicitly.

## Cross-link

- `docs/prompts/COMPOSITION_MANDATE_v2.md` — slot 3 spec-quotation rule
  was the discipline that forced operator to read the catalog and
  notice the closed-form-dominant pattern in the SUT.
- `~/.copilot/skills/delegate-to-codex/GOTCHAS.md` — investigation-class
  slot 3 ceiling lesson came from the failed H11 first attempt.
- `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` —
  `runner-level-laundering-detector-as-safety-net` decision (2026-06-12)
  notes the detector was the safety net; this design note updates the
  semantics from "FAIL on exact match" to "FAIL on exact match unless
  catalog flags closed-form convergence."
