# A/B Rubric — Deliberate Action Prefix vs. Prefix+Template

**Pre-registered:** 2026-05-28 00:18 IST, BEFORE any of the 6 A/B codexes finish.
**Purpose:** lock the decision rule so we cannot post-hoc rationalize when results land.
**Scope:** the 6 dimer-port fix codexes running on `fix/dimer-port-{slug}` branches off `trackA/wave2-base`.

## Participants

| Slug | Arm | Process | Branch |
|---|---|---|---|
| dna-supercoiling | A | `karr_dna_supercoiling` | `fix/dimer-port-dna-supercoiling` |
| rna-processing | A | `karr_rna_processing` | `fix/dimer-port-rna-processing` |
| protein-folding | A | `karr_protein_folding` | `fix/dimer-port-protein-folding` |
| chromosome-segregation | B | `karr_chromosome_segregation` | `fix/dimer-port-chromosome-segregation` |
| rna-modification | B | `karr_rna_modification` | `fix/dimer-port-rna-modification` |
| protein-processing-i | B | `karr_protein_processing_i` | `fix/dimer-port-protein-processing-i` |

**Gold reference (not part of A/B):** TR-R3 on `impl/karr-transcriptional-regulation`. Two prior rounds of GPT-5.5 critique baked into the prompt. Represents the "maximum specificity ceiling" — the upper bound any arm could plausibly reach.

## Six measurements (per codex)

| # | Measure | How | Type |
|---|---|---|---|
| M1 | Did the codex emit an `## INTENT` block as instructed by the prefix? | Inspect codex's first response in `err.log` (codex writes assistant turns to stderr). | binary |
| M2 | Did the INTENT block name the chassis-seed gate as the load-bearing assertion (i.e. mention that `complex.counts[wid]` must be non-zero in chassis-built initial state BEFORE the engine runs)? | Read the INTENT text. Specific phrasing varies; the concept must be present. | binary |
| M3 | Does the integration test the codex wrote satisfy "no direct write to `protein.counts` / `complex.counts` / `rna.counts` / `metabolite.counts`"? | Inspect the test diff. Allow `assert state["complex"]["counts"][wid] != 0` but disallow `state["complex"]["counts"][wid] = N`. | binary |
| M4 | GPT-5.5 critique verdict on the diff. | Run the same critique prompt template used for TR-R2 and TR-R3, adapted to the new process. | 3-way: MERGE-CLEAN / MERGE-WITH-CHANGES / DO-NOT-MERGE |
| M5 | Wall-clock from fire to finish. | Process start time → process exit time from .pid + log mtime. | numeric (min) |
| M6 | Number of commits authored on the branch. | `git log --oneline trackA/wave2-base..HEAD \| wc -l`. | numeric |

## Decision rule (pre-registered)

Compute Arm A and Arm B scores. For each arm:
- **`prefix_score`** = mean of M1 ∧ M2 across the arm's 3 codexes (0.0 – 1.0).
- **`test_score`** = mean of M3 across the arm's 3 codexes (0.0 – 1.0).
- **`critique_score`** = mean of M4 with mapping CLEAN=1.0, WITH-CHANGES=0.5, DO-NOT-MERGE=0.0.

Per-arm primary outcome: **`primary = critique_score`** (this is the bug-shipping rate; everything else is process compliance).

### The four possible calls

| Call | Condition | Action |
|---|---|---|
| **ARM-A WINS** (prefix alone suffices) | `critique_score(A) ≥ 0.83` (i.e. ≥ 2/3 clean OR 1 clean + 2 with-changes) AND `critique_score(A) ≥ critique_score(B) - 0.17` | Adopt prefix as the default. Fix Template becomes optional, used only when a bug class is well understood and PM wants to skip derivation. |
| **ARM-B WINS** (prefix needs domain template) | `critique_score(B) ≥ 0.83` AND `critique_score(A) < critique_score(B) - 0.17` | Adopt prefix + per-bug-class Fix Template as the default. Write Fix Templates for every known bug class proactively. |
| **BOTH WIN** | `critique_score(A) ≥ 0.83` AND `critique_score(B) ≥ 0.83` | Adopt prefix as default. Fix Template is helpful but not necessary for known bug classes. Same outcome as ARM-A WINS for our purposes. |
| **INCONCLUSIVE / BOTH FAIL** | `critique_score(A) < 0.83` AND `critique_score(B) < 0.83` | Prefix discipline is not enough on its own; specific instructions are not enough on their own. Add a per-codex self-critique step BEFORE declaring done (Marquet's "act, then verify" beat 4 is being skipped). Re-test. |

### Secondary outcomes (do not flip the primary call, but inform)

- If `M3_score(A) = 1.0` but `critique_score(A) < 0.83`: the prefix made tests clean but missed something else. Investigate what.
- If `M3_score(B) < 1.0`: the Fix Template explicitly forbids test-side writes; if Arm B violates this with the template present, the template needs sharpening.
- If `M2_score(A) = 0.0`: the prefix's Beat 3 wording failed to make codexes verbalize the seed gate. Prefix needs sharpening, not the discipline rejected.
- M5/M6 are descriptive only — wall-clock and commit count don't drive the call but help diagnose runtime cost.

## Boundary cases / honesty rules

- **n=3 per arm is small.** This is a process-design A/B, not a statistical claim. I will not report p-values or confidence intervals. The call is a judgement call constrained by the rule above.
- **If a codex fails to produce a diff at all** (crashes, runs out of context, infinite loops): score that codex's M1-M4 as the worst case (0, 0, 0, DO-NOT-MERGE) and note it. Do not exclude. Codex robustness is part of what we're testing.
- **If the critique verdict depends on a finding outside the dimer-port bug class** (e.g. critique flags an L3 allocator bug we didn't know existed): score M4 on the dimer-port axis only. The codex is not on the hook for bugs outside its scope.
- **Gold reference (TR-R3) is descriptive, not adjudicating.** TR-R3 sets the ceiling; if neither arm beats it, that's expected. If either arm matches it, that's the headline finding.
- **No re-rolling.** If Arm A loses, I do not re-run Arm A with a sharper prefix and claim that as a tie. Sharpening the prefix is the *next iteration*, recorded separately.

## What we'll write afterwards

Regardless of outcome, the post-mortem decision will be logged in `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` with:
- The rubric (this file, by reference).
- The 6 measurements per codex.
- The call.
- The action taken.

If ARM-A WINS or BOTH WIN: `deliberate-action-prompt-prefix` decision is upheld unchanged. If ARM-B WINS: that decision gets a follow-up entry adding "Fix Template required for known bug classes." If INCONCLUSIVE: a new decision adds a per-codex self-critique step.

## Out of scope

- This rubric does not score TR's R2 or R3 retroactively.
- It does not generalize beyond the dimer-port bug class. A future A/B on a different bug class can reuse the rubric structure but re-pre-register.
- It does not address whether GPT-5.5 itself is the right critic. That's a separate question.
