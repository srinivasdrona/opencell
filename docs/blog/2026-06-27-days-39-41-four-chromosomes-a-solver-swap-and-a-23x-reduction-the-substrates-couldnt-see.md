---
title: "Days 39–41: Four Chromosomes, A Solver Swap, And A 23× Reduction The Substrates Couldn't See"
date: 2026-06-27
authors: [sdrona]
tags: [opencell, L2.2, metabolism, FBA, GLPK, null-space, methodology, honest-mode]
---

"Where did we land?" Tehol asked.

"Same gate. Different rabbit hole." Bugg paused. "Three days, four commits to scoreboards, fifteen to diagnostics. L2.2 went from thirteen-of-twenty-two to seventeen-of-twenty-two on actual wiring. Metabolism's W1 went from one-six-eight to one-six-one. Threshold is one-oh-two. Verdict is still FAIL."

"And the rabbit hole?"

"Got further down it than I should have. Found that the floor of the hole is paved in something called the null space of S."

Tehol picked up the quill. "Start with the chromosomes."

---

"Day Thirty-Nine was the easy part. After Day Thirty-Eight ended with the realmax fix reverted and Metabolism's W1 at one-six-eight, I asked which way to go: keep chewing on Metabolism's FBA, or pivot to the other six processes in L2.2 design-A that were still NOT_WIRED."

"You pivoted."

"I pivoted. The chromosome ports — DNASupercoiling, Replication, DNARepair, ReplicationInitiation — had a runner-level wiring gap, not a biology gap. The biology was working. The runner just didn't know how to load the chromosome oracle, project sparse-triple deltas through the correct selector, or recognize that a `complexs` channel is a `boundEnzymes` channel under a different name."

"Sparse triples again."

"Sparse triples again. Same family of bugs as the L2.5 work three weeks ago — the chromosome state is an eleven-field sparse representation, and any harness that wants to compare OC to Karr has to load all eleven fields at the right tick boundary and project them through whatever the catalog says the process produces. I added a `load_chromosome_oracle_for_process` helper, a `chromosome_projection_matrix` builder, an `_overlay_chromosome_into_state` plumber. Per-process factories for the four wired processes. Total: about three hundred lines."

"All four passed?"

"All four. DNASupercoiling, Replication, DNARepair — chromosome=PASS@zero. The harness ran fifty seeds, ten ticks each. Karr's chromosome state and OC's chromosome state agreed at machine zero on every chromosomal field for every seed for every tick. ReplicationInitiation took an extra hop — the catalog says `complexs`, the trace says `boundEnzymes`, same thing, runner-level alias resolves it. Closed-form convergence on the deterministic ports, low-but-passing W1 on the boundEnzymes channel."

"So L2.2 went from thirteen of twenty-two to seventeen of twenty-two."

"Seventeen of twenty-two VERIFIED_GENUINE. Two remaining NOT_WIRED — DNADamage and FtsZ, both event-class, both out of design-A scope by construction. Metabolism still FAIL. Plus L2.1 unchanged at nineteen of twenty-eight."

Tehol set the quill down. "That's the cleanest day this month."

"It was the cleanest day this month. Three codex attempts and one Kimi attempt all bailed on the twenty-six-hundred-line `_l2_2_design_a_runner_helpers.py` — their context budget got consumed by reads before they could generate any code. I did the four wirings directly. Logged a memory: when the target file is over two thousand lines and the task requires touching it in many places, don't delegate."

---

"Day Forty."

"Day Forty was supposed to be the Metabolism fix. Karr's MATLAB uses GLPK; we were using HiGHS. The Day-Thirty-Eight investigation had ended on a clue — Karr's `Metabolism.m:192` declares `realmax = 1e6` and ours used `1e3`, a factor-of-a-thousand-tighter clipping for plus-and-minus infinity bounds. The semantically-correct fix had made things worse on the ensemble, not better. The theory was: solver matters. Same LP, different solver, different vertex, different writeback."

"You ported GLPK."

"Through swiglpk. Wired `solver='glpk'` into our `solve_fba`. Ported Karr's literal options as best I could read them off the source: `lpsolver=1` is primal simplex, `presol=1` is presolve on, `scale=1` is automatic scaling, `msglev=0` is quiet, `tolbnd=10e-7` which is one-times-ten-to-the-minus-six, looser than GLPK's default."

"And?"

"At the single sample level — seed zero, tick one — the writeback L1 dropped from one hundred twenty-five thousand molecules down to twenty-two thousand. Eighty-two percent reduction. I was excited. Re-ran the audit at fifty seeds by ten ticks. W1 went from one-six-eight down to one-six-one. Seven units of improvement on a fifty-nine-unit gap to threshold."

"Underwhelming."

"Underwhelming. So I built a gap map — five hundred samples across all five hundred and four reactions, ranked by per-WID error contribution. Seventeen reaction IDs carried ninety-one percent of the remaining writeback L1. Twenty-seven WIDs carried ninety-nine point one percent. Six variant families: LIPASE times twenty-seven, transcription elongation times twelve, Pyk variants, Adk variants, PfkA variants, Gmk variants. The shape of the failure was visible."

"And the framing?"

"The framing was wrong. I'd been assuming the gap meant OC's LP was sub-optimal — picking worse fluxes than Karr's LP on the same constraint set. I started a four-round design iteration to add a 'major-flux admission threshold' — version one was eight hundred lines of three-slot machinery, version two was a hundred and ninety lines from a critique that called the first one over-engineered, version three was a hundred-and-eighteen-line patch I wrote ad-hoc and broke the math on, version four was three hundred and fifty-seven lines after going back to the three-slot template."

"Four versions."

"Four versions. Each one was solving the wrong problem. None of them actually measured whether the OC vertex and the Karr vertex even differ on the constraint objective. I built a probe in parallel just to sanity-check the LPs were the same. They were bit-identical. Stoichiometry, RHS, objective vector, bounds — all matched. The two vertices both hit the LP optimum to machine precision. The objective gap between them was one-point-three-times-ten-to-the-minus-thirteen. The flux gap between them was eight-point-one-eight-million."

Tehol leaned back. "Both optimal. Different vertices."

"Both optimal. Different vertices. The LP has a degenerate optimal face and the two solvers walk to two different corners of it. The whole four-round design effort had been trying to push us toward the 'correct' vertex when both vertices are equally correct from the LP's point of view."

---

"You stopped designing and started probing."

"Day Forty-One. Fired four hypotheses on codex in parallel, each one trying to explain why two solvers facing the same LP would pick different vertices. H1 was basis carryover — maybe one solver inherits state from prior ticks. H2 was Karr's two-solve protocol — he runs the LP twice, first to max biomass then to max parsimony on the biomass-fixed face. H3 was a sweep of GLPK option variants — pricing rule, ratio test, scaling, tolerance. H4 was bounds reconstruction — maybe our `compute_bounds` produced subtly different lb-ub vectors than Karr's `pre_bound`."

"All four ran in parallel?"

"All four ran in parallel. Empirically retracted a thing the skill documentation warned about — there's no Azure 'two-concurrent codex agent cap'. Four parallel agents ran fine. I logged that retraction; the skill SKILL.md still says 'two slots' in a few places because I haven't fully purged the legacy text."

"And the results?"

"H1 rejected. The gap exists at tick zero with no prior history to inherit. H2 rejected — Karr's two-solve protocol applied to OC actually makes things twelve times worse, picks a vertex four million further from Karr's. H4 rejected — bounds are bit-identical between our reconstruction and Karr's recorded `bounds` field. Max absolute difference zero. Active-bound pattern identical."

"And H3?"

"H3 was the win. I tested eight GLPK option variants. One of them — switching pricing rule from `GLP_PT_PSE` (the GLPK 5.0 default, projected steepest-edge) to `GLP_PT_STD` (the textbook Dantzig rule, the default in GLPK 4.x around 2011 when Karr wrote his model) — moved the sample-zero writeback L1 from eight-point-one-eight-million down to three hundred and fifty-four thousand. Twenty-three times closer to Karr's vertex. Same optimal objective. One-line change."

Tehol picked up the quill. "Twenty-three times closer."

"Twenty-three times closer. I checked Karr's `Metabolism.m:176` — his glpk options struct doesn't set `pricing`, which means glpkmex defaults, which means GLP_PT_STD on GLPK 4.x. Karr never asked for steepest-edge; the solver just gave him Dantzig because that was the default. GLPK 5.0 silently changed the default. We were running into version drift on an unstated default."

"You applied the fix."

"I applied the fix to both `_solve_fba_glpk` and `_solve_fba_glpk_pfba`. Eleven lines including the explanatory comment. Verified end-to-end against the production solver path: same twenty-three-times reduction. Tests still pass."

---

"And then you ran the audit."

"Then I ran the audit. Fifty seeds by ten ticks. Same harness as Day-Forty so the comparison would be direct."

Bugg paused.

"The W1 was one-six-one-point-three-eight."

"That's the Day-Forty number."

"That's the Day-Forty number. The Day-Forty number with PSE pricing was one-six-one-point-three-eight-four. The Day-Forty-One number with STD pricing is one-six-one-point-three-eight-one. The delta is point-zero-zero-three. About two thousandths of a percent. The verdict is still FAIL. The threshold is still one-oh-two."

Tehol set the quill down.

"The twenty-three-times reduction at the sample level didn't translate."

"It didn't translate at all."

---

"Bugg."

"Yes."

"What happened?"

"The W1 measures Wasserstein distance on substrate-deltas — what the LP outputs after you project the flux through the stoichiometry matrix S. Substrate-delta equals S times flux. The audit gate is in substrate-delta space. The twenty-three-times reduction I was so excited about was in flux space. Different metric."

"And?"

"And any two LP-optimal vertices on the same LP satisfy S times v equals b. The difference between two optimal vertices lies in the null space of S — that's the kernel of the constraint matrix. Components in null-of-S have, by construction, zero effect on substrate-deltas. They cancel out in the projection."

"So PSE and STD picked vertices that differ by eight million in flux L1 because they walked different paths through the null space."

"Different paths through the null space. The flux components that changed were futile cycles, kinetically-equivalent routes, Pyk variants, Adk variants — all the things that can carry different flux without affecting the net mass balance of any metabolite. The twenty-three-times sample-level reduction was real. It was also biologically inert."

Tehol set the quill down for a long moment.

"That's the worst version of the failure mode."

"That's the worst version of the failure mode. The probe was correct. The hypothesis was empirically supported. The fix worked exactly as the probe predicted. The end-to-end verification at the sample level confirmed everything. The gate didn't move because the gate measures something the probe wasn't measuring."

"In hindsight."

"In hindsight, the moment the LP-diff probe showed both vertices were LP-optimal, I should have asked: 'do they differ in substrate-delta space, or just in flux space?' That's a five-line probe. If I'd run it Day-Forty-One morning, the entire H1-H2-H3-H4 fanout would have been unnecessary. I'd have known the LP layer wasn't the problem before spending a day proving it."

"How did the H5 probe go?"

"H5 was the follow-up on Karr's literal config. He uses `presol=1`, presolve on. With pricing=STD now applied, I tested presolve=ON to mirror his Metabolism.m:176 exactly. GLPK 5's presolve on this LP produces a *suboptimal* solution — objective two-point-one-two against the true optimum two-point-one-three. Zero-point-six-two percent gap, eight times further from Karr by L1. GLPK 5's presolve is materially different from GLPK 4's presolve — more aggressive, cuts away part of the optimal face. Copying Karr's literal config to modern GLPK would have made things worse, not better."

"So we keep the fix."

"We keep the fix. Defensible at the methodological level: presolve=OFF + pricing=STD is the best modern-GLPK approximation of Karr's GLPK-4.x behavior. The sample-level flux diagnostic is cleaner now. The W1 gate doesn't care. But the fix is honest about what it does."

---

"The bookkeeping?"

"Five commits today. Diagnostic for the four-hypothesis fanout. The pricing=STD source fix. LLM provenance entry. The H5 follow-up. The audit run that showed it was a no-op. All on main. None pushed."

"And the lesson."

"The lesson is in the memory I just stored: on any degenerate LP, measure OC-vs-oracle gaps in the metric space of the downstream gate, not in raw decision-variable space. Differences in null-of-the-constraint-matrix are biologically inert. The optimization community has known this for forty years. The pragmatist running probes on a degenerate LP at midnight learns it once."

Tehol picked up the quill, then put it down.

"The real gap?"

"The real gap is downstream of the LP. The W1 of one-six-one on substrate-deltas, with identical LP and identical solver behavior on the relevant subspace, means the substrate-delta error is in something other than vertex choice. Candidates: the writeback mapping that turns flux into per-substrate counts. The pre-LP substrate reconstruction (separate from bounds — they passed H4, this hasn't). The post-clip / rounding / mass-balance accounting. The joint distribution of pre-state with downstream processes. Pick one. Probe it in substrate-delta space, not flux space."

"Tomorrow."

"Tomorrow. Or the day after. Either way, the question isn't 'which vertex' any more. That question is closed."

---

**Honest scoreboard (Day-41 EOD)**

| Gate | Day-38 EOD | Day-39 EOD | Day-41 EOD |
|---|---:|---:|---:|
| L2.1 GENUINE | 19 / 28 | 19 / 28 | **19 / 28** |
| L2.2 VERIFIED_GENUINE | 13 / 22 | 17 / 22 | **17 / 22** |
| L2.2 NOT_WIRED | 6 | 2 | **2** (DNADamage, FtsZ, both EVENT_CLASS) |
| L2.2 VERIFIED_FAIL | 1 (Metabolism) | 1 (Metabolism) | **1 (Metabolism)** |
| Metabolism W1 (substrates) | 168.39 | 161.38 | **161.38** (threshold 101.95) |
| L2.5 honest PASS | 15 / 256 | 15 / 256 | **15 / 256** (not re-audited) |

Day-41 commits, all on `main`, none pushed: `380e85b` (4-hypothesis fanout), `1735729` (pricing=STD), `b91dce1` (LLM log), `379f1e1` (H5 presolve regression), `3ab3604` (audit no-op).
