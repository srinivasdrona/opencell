# Write Day 14 OpenCell Blog Post

You are writing today's (2026-05-29, Day 14) blog post for the OpenCell whole-cell simulation project. Follow the skill at `C:\Users\sdrona\.copilot\skills\opencell-blog-post\SKILL.md` strictly. The skill governs voice, format, hard rules, and self-check.

## Read FIRST (mandatory)
1. `C:\Users\sdrona\.copilot\skills\opencell-blog-post\SKILL.md` — the contract.
2. `E:\opencell\docs\blog\2026-05-27-the-ladder-and-a-decision-to-slow-down.md` — most recent before yesterday.
3. `E:\opencell\docs\blog\2026-05-28-a-rung-that-was-three-rungs.md` — yesterday (Day 13). The next post must pick up where this ends.
4. `E:\opencell\docs\blog\2026-04-22-4500-lines-before-lunch.md` — Tehol/Bugg ratio archetype.

## Output target
`E:\opencell\docs\blog\2026-05-29-<your-slug>.md`. Day 14. 1000-1200 words dialogue body + postscript.

## Today's material (the beats)

### A. Bucket state (verifiable via `git log` on `audit/l2-1-sweep-v2`)
- Start of day (May 29 morning): L2.1 GREEN = 5, Pattern A = 2, Pattern D = 21, L2.0 RED = 4.
- End of day so far: L2.1 GREEN = 6 (+ProteinTranslocation), A = 0, B = 0, C = 0, D = 22. 8 if the two in-flight agents close.
- L2.0 RED count = 4 (deferred).

### B. The empirical-reclassification finish (Pattern A → 0)
- Pattern A = "wid-length drift": OC observable vector shorter than Karr's.
- Two stale Pattern A residues: Transcription, Translation.
- Closed by **honest-prefix projection** with `np.arange(4)` and `np.arange(20)` in the test files (`d8fa1a5`, `d779951` on `audit/l2-1-sweep-v2`).
- DECISION already logged earlier (`l2-1-empirical-reclassification-over-canonical-projection`): don't chase perfect canonical WID-mapping when OC's first-n WIDs are an honest prefix.

### C. The ProteinTranslocation away-hour win
- Codex agent worked solo for ~50 minutes on `audit/fix-protein-translocation`.
- Found the MATLAB rule: SRP flag derives from `signalSequenceType ∈ {lipoprotein, secretory}` + first-infeasible-halt.
- Commit `426a698`, +25/-18 lines, 100/100 ticks bit-identical. Cherry-picked as `699f1c4`.

### D. The RNAModification chain (this is the day's marquee story)
Three sequential Codex fixes, each commit reduced the gap:
1. `dd91335` — chemistry fix: remove binary per-reaction/per-rna caps. Matches MATLAB lines 327-348.
2. `19d76f2` — harness fix: route `modifiedRNAs → rna.modified_counts` in `tests/vivarium/l2_replay_common.py`. First-fail moved tick=0 → tick=6, gap closed from MG471 -35 to substrates[0] +7.
3. `06595c2` — process fix: shared catalytic-enzyme budget (`1/kcat`) across reactions. First-fail substrates[0] +7 → substrates[2] +1. ~85% gap closure plus an index shift.
A 4th agent is in flight to close the residue.

### E. ProteinProcessingI
- Codex chemistry fix (`2ed4701`, was `90fb670` pre-cherry-pick): H2O `+3` drift closed via deformylation stoichiometry `[-H2O, +FOR, +H]`.
- New first-fail at tick=1, processedMonomers[147] +1: **not chemistry** — observable-routing issue, exact same shape as RNAMod storepath bug. A 5th agent is in flight to fix routing in the harness.

### F. The meta-moment (this should be a Tehol beat, not a sentence)
The operator asked an honest historical-accuracy check: did the dimer-port prompt template unblock us 24 hours ago? The agent's first answer organized everything into a tidy 5-move framework with dimer-port at step 5 (delegation kernel). On honest re-read of the session log:
- Dimer-port template was applied at turn 1133 (~May 28 17:29) AFTER GPT-5.5 critique flipped 2 of 3 verdicts — i.e., when stuck.
- It was applied to **the test prompts themselves first** (Rules 1-7, delta-integrality, no-coerce harness, pre-mortem gates). Not to delegation.
- Pattern A/B/C/D taxonomy emerged ~12 hours LATER (checkpoint 142, May 29 ~06:00), as a *consequence* of the hardened prompts producing clean failure signatures.
- The agent's first retro had the order wrong. Operator caught it. Agent corrected.

Tehol angle: the danger of post-hoc tidying. Bugg angle: the unglamorous truth that the breakthrough was the boring craft step (better prompts) not the framework diagram.

### G. Parallelism that actually paid off
- 3 Codex agents in flight at peak today (RNAMod substrate, ProcessingI chemistry, ProcessingI routing — though the third was sequential after #2 finished).
- Worktree hygiene: removed 5 idle worktrees mid-day (post-translocation), then 2 more after the chain closed. Branches preserved as safety net.
- The orchestrator role this day was triage → delegate → cherry-pick → measure → next-prompt. Very little hand-coded.

## Style notes specific to this post
- The "meta-moment" (F) is the most interesting beat. Don't bury it. Suggested placement: third-to-last beat, before the closing.
- The RNAMod chain (D) is where Bugg gets to deliver a long technical paragraph — the three-commit narrative with the diff progression `-35 → +7 → +1` is concrete and earns the space.
- Tehol naming candidates: "informative failure", "the template that came in twice", "post-hoc tidying", "delegation kernel". Pick one to land, don't use all.
- The previous post (Day 13) ended with the L2.1 sweep just having produced its first taxonomy. Day 14 should pick up: "and then we used the taxonomy to delegate" — but with the honest correction baked in.

## Postscript content (use real data)
- Decisions logged today (slug + scope): none today (`doc-dimer-port-prompt-methodology` is a todo, not a decision yet). The decision `l2-1-empirical-reclassification-over-canonical-projection` was logged earlier this campaign — name it.
- Files touched at canonical level (main branch commit `474c204` was the last status refresh; everything else is on `audit/l2-1-sweep-v2`):
  - `docs/phase_e/L2_STATUS.md` (status refresh on main)
  - `plan.md` (current-status block on main)
  - `tests/vivarium/test_karr_transcription_l2_replay.py`, `test_karr_translation_l2_replay.py` (Pattern A close)
  - `opencell/vivarium/karr_protein_translocation.py` (SRP fix)
  - `opencell/vivarium/karr_rna_modification.py` (chemistry + budget)
  - `tests/vivarium/l2_replay_common.py` (RNAMod storepath)
  - `opencell/vivarium/karr_protein_processing_i.py` (H2O stoich)
- Tehol/Bugg attribution line: borrowed from Steven Erikson's *Malazan Book of the Fallen*.

## Hard constraints (recap from skill)
- 1000-1200 words body
- Tehol ≥ 40% of lines
- No em dashes
- No hype phrases ("breakthrough", "exciting", etc.)
- All numbers exact (cross-check against this prompt)
- Postscript present

## When done
- Commit to `main` in `E:\opencell` with message `docs(blog): day 14 — <your title fragment>`.
- Do NOT push (operator decides).
- Write `STATUS_BLOG_DAY_14.md` in `E:\opencell\` with: file path, word count, Tehol-line %, commit SHA, wall-time.
- Final assistant message: one line.
