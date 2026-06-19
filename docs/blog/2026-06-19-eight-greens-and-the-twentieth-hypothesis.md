---
title: "Day 33: Eight Greens and the Twentieth Hypothesis"
date: 2026-06-19
authors: [sdrona]
tags: [opencell, L2.5, validation, harness, inversion, probe-and-redirect]
---

Bugg arrived with two cups instead of one. He set the second across the table and looked at it for a moment before sliding it toward Tehol's place. "I owe you one. I was wrong about something."

Tehol picked up the cup but didn't drink. "Specific?"

"The whole approach to L2.5 yesterday. I called it a 'no-hints channel parity gap' and thought we had seven processes with the same small bug. I was right about the gap and wrong about everything else."

"Walk it back."

---

"Yesterday I said: seven processes have a no-hints branch that silently drops the `enzymes` and `boundEnzymes` channel emissions. The audit confirmed it — channels expected, channels missing, six for six. Fix the emissions, the channels appear, the pair tests turn green. A clean morning's work."

"And?"

"This morning I fired three codex delegations on the smallest group — ReplicationInitiation, Replication, DNASupercoiling. Each got the missing channels wired. Three commits landed clean. L2.1 stayed green for all three. I ran the pair sweep expecting a cascade of greens."

"How many flipped?"

"Zero. Same scoreboard. Seven green pairs in, seven green pairs out. The fixes were necessary — those channels were genuinely missing — but they weren't sufficient. The pair tests had been failing for a reason I hadn't named."

Tehol leaned back. "So what was happening?"

"The channels were being plumbed. The values flowing through were zeros. The no-hints branch was sampling events — gyrase binding, supercoiling activity — but never connecting those sampled events back into the emit dictionaries. The compute was happening; the writeback wasn't."

"Plumbing was a metaphor."

"Plumbing was a misdiagnosis. The bug was deeper. I needed a probe."

---

"Tell me about the probe."

Bugg sketched a small diagram on the napkin. "Run each of the seven processes in isolated no-hints mode at tick zero. Compare what it emits against what Karr's trace says. Six of the seven showed off-by-tiny-N: ATP off by 4, GTP off by 1, AMP off by 1. The seventh — ProteinModification — showed off-by-cumulative at tick fifty-three. Not at tick zero. At fifty-three."

"Cumulative drift."

"Right. Which means tick zero was probably also off by a small number, just below the detection threshold, and it compounded. So I drilled deeper into DNASupercoiling — the cleanest off-by-4. Wrote a full-channel probe that runs the isolated replay and compares every output channel WID by WID at tick zero."

"And?"

"DNA gyrase. Karr's trace has three gyrases moving from free to bound at tick zero. Three free DnA gyrases binding to chromosome regions. Three matching ATP hydrolysis events at one ATP per binding. OC's no-hints DNASupercoiling? Zero binding events. Zero free-to-bound transitions. The sampler was computing 'how many gyrase events should fire' correctly. It just wasn't propagating the resulting transition counts back into the enzyme observable dictionaries."

"So the fix is small."

"Twenty to fifty lines per process. Mirror the hint-path emission shape in the no-hints branch, computing the deltas from the same internal `_free_gyrase` / `_bound_gyrase` arrays the sampler already mutates. I sent a codex delegation. It came back with all-zero diffs across substrates, enzymes, and bound enzymes for DNASupercoiling at tick zero in isolated mode."

Tehol set down his cup. "Pair test?"

"Still failed."

---

"Same scoreboard."

"Same scoreboard. So the isolated bit-identity port was correct and necessary — and the pair test had a different blocker."

"A second layer."

"A second layer. Now I had four hypotheses in mind, but only one I could afford to test at a time. Slot the prompt, three slots tight, hard token cap, one hypothesis per delegation."

"And you started with what?"

"The harness arithmetic. The pair test reports OC's delta as minus-four, Karr's as minus-sixty. I suspected the delta-compare math was wrong. Codex's probe came back in five minutes: arithmetic is fine. `oc_compare = oc_after_step - oc_before_step`, exactly as written, exactly as expected. The numbers match. So whatever is producing the minus-four is upstream of the comparison."

"H8 rejected."

"H8 rejected. But the probe table revealed something else. Between tick start and DNASupercoiling's actual step inside the composition, the shared ATP pool dropped from 907 to 72. Not from 907 to 904 — ChromosomeCondensation, the upstream process, consumes maybe three ATP. From 907 to 72. A drop of 835."

"That's not Cond's emit."

"Definitely not Cond's emit. And 72 happened to be the number I remembered from yesterday's Metabolism probe. ATP at 72 is the value at a much later moment in the cell cycle — after Metabolism has consumed most of the production pool. Cond's reference trace happened to be captured at that later moment. DNASupercoiling's trace was captured earlier, when ATP was still 907."

"They're from different times."

Bugg held up a hand. "I didn't see that yet. I had a more local hypothesis."

---

"H9," Tehol said.

"H9. The harness's pre-step state initialization had two passes: an owner-init pass that seeded the shared state from a single 'owner' process's reference trace, and a per-process overlay pass that injected each process's own view for the observables it cared about. The owner concept made sense in single-process replay — there's only one process, so it owns everything. In a pair, the owner is picked alphabetically. ChromosomeCondensation comes first. So the shared substrate pool got seeded from Cond's trace — ATP equals 72."

"And then DNASupercoiling's per-process overlay should have corrected it."

"Should have. But the overlay only ran for observables where there was an upstream exposer. For substrates, the owner-init had already put down 72, the overlay didn't re-apply DNAS's view of 907, and the state-merge logic for the H6 mutation-preservation fix had a corner where it preserved the 72 instead of DNAS's 907."

"So DNAS started its no-hints sampler against a 72 ATP pool."

"Which is why it produced 4 events instead of 60. The biology port was correct. The harness was feeding it 8% of the ATP it should have seen."

Tehol made a small noise. "That's a hidden global state for the first half of the simulation."

"It had been hidden for the first half of the year. Group A's fixes from this morning had been blocked by it. They'd be silently broken even with the canary biology in place. H9 was the bottleneck."

---

"The fix."

"Drop the owner-init pass entirely. Each process's pre-step view comes from its own reference trace. The H6 mutation-preservation logic stays: when an upstream process has actually written to a shared WID this tick, the downstream process sees the upstream-mutated value, not its own trace baseline."

"Codex did this?"

"Twenty-four minutes. Two passes merged into one, net negative five lines of code. L2.1 stayed green. The two DD pair tests stayed green. The one SS pair test stayed green."

"And the DS sweep?"

"Fifteen passing, twenty failing, eight skipped."

Tehol picked up his cup. "We had seven this morning."

"We have fifteen now."

"Plus the two DD and the one SS."

"Eighteen total. Up from ten yesterday."

---

"Eight unlocks from one harness fix."

"Eight unlocks from one harness fix. The Group A no-hints emit-plumbing work I'd done in the morning had been correct all along. The pair tests had been blocked behind H9. With H9 fixed, all the existing biology-port-and-emit-plumbing work suddenly cleared a cascade of pairs."

"And the canary DNASupercoiling work."

"Still blocked. The pairs that needed both Group A's emit-wiring AND the canary biology compute AND H9 — those are the harder ones. DNASupercoiling didn't unlock with H9 alone."

"H10."

"H10. Could the allocator be squeezing DNAS's budget under composition? In isolation, DNAS sees the full 907 ATP. In composition, maybe the harness gives DNAS a per-process fair-share budget that's small."

"Quick probe."

"Five minutes. Rejected. Both modes — composition and isolation — show 907 ATP, 9 million H2O. The allocator isn't shorting anyone. DNAS sees the full pool both ways. But composition still produces 4 events instead of 60."

"Same input, different output."

"Same input as far as the substrate budget. Different output. So something else in the input state must be different."

---

"H11."

Bugg leaned forward. "I wrote my own probe this time. Captured the entire `states` dict that DNAS sees at the moment of its step, in both modes, and diffed them. The difference came back with two entries. One was a small allocator-key set: composition had Cond's allocator entry, isolation didn't — irrelevant, doesn't change DNAS's read. The other was real."

"What was it?"

"Cond writes three fields into chromosome state: `condensation_level`, `forks_passing`, `smc_bound_count`. They don't exist in DNAS's isolated view because nothing wrote them. In composition, Cond ran first and added them."

"Does DNAS read them?"

"No. I checked. DNAS's no-hints branch reads `polymerizedRegions`, `linkingNumbers`, `complexBoundSites` — none of the three new fields. So the new fields aren't directly the bug."

"Then what is?"

"I went back to first principles. DNAS's reference trace says: at tick zero, ATP is 907. Cond's reference trace says: at tick zero, ATP is 72. These are both labeled tick zero. They cannot both be true at the same moment in Karr's simulation. 907 minus 72 is 835 ATP that Metabolism produces somewhere between the two snapshots. The traces were captured at different moments of the cell cycle."

Tehol said nothing.

"There is no single moment in Karr's actual simulation where DNAS sees 907 ATP and Cond sees 72 ATP. Their tick-zero baselines are from different times. Composing them in a single pair tick using both their tick-zero baselines is not actually well-defined."

"So the L2.5 pair test, as written —"

"Is structurally composing fragments from different cell-cycle phases. The fifteen passing DS pairs work because the per-process baseline differences are small enough to fall within the distributional tolerance. The twenty failing DS pairs have larger baseline mismatches that dominate the comparison."

---

"This is bigger than a bug."

"It's a methodology question. The L2.5 acceptance rubric assumed per-process traces had consistent tick-zero baselines. They don't."

Tehol turned a page in his ledger. "What are the options?"

"Three. One: re-extract all twenty-eight per-process traces from a single canonical Karr run at consistent moments. Each process's tick-zero is captured at the same wall-clock moment. Then composition is principled. Cost: a day or two of MATLAB work plus an extractor revision."

"Two."

"Switch L2.5 to joint-state semantics. Start the pair from a single global tick-start state — probably Metabolism's view, since Metabolism seeds the pool — run both processes, check whether the final joint state matches the expected joint state. Drop the per-process delta comparison. Cost: a harness rewrite plus a rubric document."

"Three."

"Accept eighteen passing pairs as the achievable L2.5 surface. Document the limitation: per-process traces aren't time-aligned, pairs work where baseline differences are small, fail where they're large. Move on to L3."

Tehol set down the quill. "What's your instinct?"

Bugg drank some of his tea before answering. "One is the cleanest. The acceptance rubric I wrote yesterday said all two hundred fifty-six pairs must pass. If the trace baseline mismatch is the reason we can't get there, we should fix the traces."

"And two is the cheapest."

"Two is the cheapest. But it changes what we're measuring. Per-process delta comparison says: 'each process, in isolation, contributes the same delta it does in Karr.' That's a strong statement about per-process fidelity. Joint state comparison says: 'the composed system reaches the same end state Karr does.' That's weaker — two processes could be individually wrong in opposite directions and still produce the same joint state."

"And three is the lazy."

"Three is the lazy. It's also the honest one. We'd be saying: the per-process tick-zero traces have a structural limit. We can't validate composition against them beyond this point. Either accept the limit or invest in better traces. There's no third way."

Tehol marked the page. "Operator's call tomorrow."

"Operator's call tomorrow."

---

"What did you find that was worth saving?"

Bugg considered. "The probe-and-redirect cascade worked. Four hypotheses tested in sequence. H8 rejected in five minutes. H9 confirmed and fixed in twenty-five. H10 rejected in ten. H11 confirmed and elaborated in fifteen. The three-slot prompt mandate held: each delegation had one hypothesis, three files in the read set, a falsifiable verdict expected as output. None of them ran past their token budgets. None produced rambling speculation."

"The biology ports."

"The biology ports work at isolation. DNASupercoiling's canary went from twenty-magnitude diffs to zero. That's the right kind of fix. We just can't validate it at composition until the trace question is settled."

"The repo cleanup."

"Hundred and two files at the repo root, down to twenty-two. Anyone visiting the GitHub landing page can see the README now without scrolling past eighty old status reports. That was a thirty-minute investment with a permanent payoff."

"And the eight unlocks."

"Eight unlocks. Translation plus seven companions on the chromosome side. Segregation plus seven. We went from ten green pairs to eighteen. Forty percent of the day-six gate."

Tehol blew out the candle.

"Tomorrow we decide what L2.5 actually means."

"Tomorrow we decide."

---

**Day 33 by the numbers**

- L2.5 pairs PASS at start of day: **10** (1 SS + 7 DS + 2 DD)
- L2.5 pairs PASS at end of day: **18** (1 SS + 15 DS + 2 DD) — **+8 net unlocks**
- Probe-and-redirect hypotheses tested: 4 (H8 rejected, H9 confirmed+fixed, H10 rejected, H11 confirmed-but-deeper-than-expected)
- 3-slot codex delegations fired: 6 (1 audit, 1 re-diagnosis, 1 Group-A fix, 1 canary, 3 investigation-class). 6 of 6 stayed within token budget.
- Harness bugs found and named: 1 (H9: per-process own-baseline pre-step overlay)
- Harness bugs found and fixed: 1 (H9, commit `07febee`)
- Biology ports landed: 4 (3 Group A emit-plumbing + 1 DNASupercoiling canary biology)
- Probes committed: 4 (`audit_cause5_writeback`, `probe_cause5_values`, `probe_dna_supercoiling_full`, `probe_h8_composition_delta`, `probe_h9_owner_overlay`, `probe_h10_allocator_budget`, `probe_h11_dnas_state_diff`)
- Repo files at root: 102 → 22 (89 historical PROMPT_*.md / STATUS_*.md archived under `docs/archive/`)
- Commits to main: 15, all pushed
- Methodology questions on the table for tomorrow: 1 (per-process trace time-alignment vs joint-state semantics vs accept-and-move-on)
- Beats-4 inversions that fired correctly: every delegation (3-slot mandate held)
- Bugs found by Beat 4 pre-mortem before they could land: at least 3 (counterfactual probe traces, oracle leakage check, double-counting check)

The L-ladder continues to do what it was designed to do. Each rung exposes the rung below. Today we found that the rung we'd been standing on for the L2.5 design — the assumption that per-process traces have consistent tick-zero baselines — is itself shaped wrong. Eighteen pairs pass anyway because the wrongness happens to be small in those cases. Tomorrow we decide whether to re-shape the rung or accept it. Either way, the ladder still climbs.

The probe-and-redirect pattern is now the project's default for any "looks like a process bug" failure. Four times today it told us "the bug is elsewhere, look here instead." Each redirect saved hours that would otherwise have been spent fixing the wrong thing. The 3-slot mandate's investment from Day 22 — token caps, hypothesis discipline, probe-as-artifact — paid for itself again. Six delegations, six clean verdicts, zero runaway investigations.

Eighteen greens. Two hundred and ten untested SS pairs. Twenty failures with one clear methodology question between us and the next round of unlocks. The ladder still climbs.
