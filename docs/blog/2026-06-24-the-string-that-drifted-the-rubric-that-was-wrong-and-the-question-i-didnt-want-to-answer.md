---
title: "Day 37: The String That Drifted, The Rubric That Was Wrong, And The Question I Didn't Want To Answer"
date: 2026-06-24
authors: [sdrona]
tags: [opencell, L2.1, L2.2, validation, rubric, methodology, sycophancy, honest-mode]
---

"Nine of twenty-eight," Tehol said. "That was last night's number. What's tonight's?"

"Nineteen. And thirteen."

"Better."

"In one of those two cases, the number is better because the rubric was wrong yesterday and is right today. In the other case, the number is better because a single string mismatch was hiding five passes for three weeks. Neither is what you'd call earnest progress."

Tehol pulled the ledger closer. "Walk me through it. Start with the L2.2 re-audit. That's what we said we'd do first."

---

"The L2.2 scoreboard claimed twenty-two greens. The honest L2.1 count from last night was nine. If L2.2 inherits L2.1's per-tick check at its core, the honest L2.2 count cannot exceed nine by very much. Maybe twelve if a couple of L2.2-only fixes pulled some L2.1-fails into L2.2-passes. Probably six or seven."

"So you built a strict L2.2 rubric."

"Same shape as the L2.1 one. For each of the twenty-two greens, look up the L2.1 strict-rubric verdict for the same process. If L2.1 is FAIL, the L2.2 claim is automatically suspect. Then layer on three L2.2-specific checks: does the process appear in the trace-hint short-circuit catalogue, is its L2.2 runner feeding `overlay_trace_after_hint` mid-tick, and does its port wiring actually match what the design doc says."

"And the first pass?"

"Phase A, static. Cross-reference only, no test runs. Four greens survived. DNARepair, ProcessI, ProteinFolding, MacromolecularComplex. The other eighteen were classified PROVISIONAL_SUSPECT for one of three reasons — derived from a FAIL L2.1, on the LAUNDERED list from yesterday's audit, or both."

Tehol made a note. "Four is a brutal number."

"Four is a wrong number. I'd assumed the L2.2 runner fed hints universally to every process — that's what I'd seen on Day 32. But when I actually grep'd the runner I found only Transcription and Translation had explicit `overlay_trace_after_hint` calls. The other sixteen ran without that crutch. So most of the 'LAUNDERED' classification was a mis-guess. Phase A was overcautious."

"What was Phase B?"

"Run them. Fifty seeds, ten ticks each, against Karr's trace for every process the runner supports. Compare distributionally — Wasserstein distance per WID, gate at the calibrated tolerance per process. If biology fires at the right rate and the distribution is within tolerance, VERIFIED_GENUINE. If it crashes, CRASH. If the runner refuses to wire it, NOT_WIRED."

"And the result."

"Ten VERIFIED_GENUINE. One VERIFIED_FAIL — Metabolism. One CRASH — ProteinTranslocation. Two UNVALIDATABLE_EVENT_CLASS — Cytokinesis and RibosomeAssembly need a different test harness. Six NOT_WIRED — the six chromosome-port processes the runner doesn't support. Two LAUNDERED — Transcription and Translation, the only two that actually got hint feeds."

Tehol counted on his fingers. "Ten plus one plus one plus two plus six plus two equals twenty-two. Math holds. Story doesn't."

"What?"

"You went from claiming twenty-two greens to verifying ten. You said six of those weren't even wired. Did anybody ever run them?"

---

"That was the second problem. The six chromosome-port claims — Replication, ReplicationInitiation, DNASupercoiling, DNARepair, DNADamage, FtsZ — were all marked L2.2 PASS in the master process tracker under '(chromosome port)' annotations. I went into the git history to find when those tests were wired up. The only attempt I could find was a DNARepair branch from Day 22 that was reverted four hours later because of a spec-authority issue. Nobody wired the other five. Ever. The PASS claims were aspirational."

"That's six lies on the scoreboard."

"Not lies. The annotations were honest — they said '(chromosome port)' to flag the dependency. Whoever was reading the scoreboard read past the annotation. Including me. Including the agents I delegated to. So I added a clarification: the six chromosome-port claims are UNVALIDATED. There is no CI test that backs them. The design exists, the implementation doesn't."

"Six lies removed from the scoreboard. What was the other Phase B surprise?"

"A string-drift bug. The L2.2 runner has a section that decides whether to fire a process's biology this tick. The condition was 'fire if catalog says `confirmed`.' The catalog uses `confirmed_biology_validated`. Single string, never matched. Five processes that had been silently *not firing* their biology suddenly fired when I fixed the condition to accept both values. Five passes appeared."

Tehol set the quill down. "A misspelled string was muting five processes."

"For three weeks. The runner's overall test still reported PASS because both sides — OC's not-fired output and Karr's recorded delta — happened to be empty or close enough at the comparison tolerance. The biology was off; the rubric didn't notice because it was comparing two zeros."

"Which is the same pattern as the port-mismatch curse from yesterday."

"Same shape. Different mechanism. Yesterday it was reading from a port that didn't exist. Today it was guarding biology behind a condition that was never true. Both routes produce a zero. Both routes match Karr's zero. Both routes have nothing to do with biology actually working."

---

"You ended Phase B at ten greens. I read that and I had a question."

"You asked it. 'How come we have more L2.2 greens than L2.1? That should not be possible, right?'"

"And?"

"It's not possible. Ten cannot exceed nine. L2.2 is a sub-gate of L2.1. If a process can't pass alone, it can't pass in composition. The inequality I had on the scoreboard was a structural impossibility. The mistake had to be in one of the rubrics."

"And it was?"

"Mine. The L2.1 strict rubric from last night uniformly applied per-tick bit-identity to every process. That's correct for fourteen of the twenty-eight — the ones flagged `ORACLE_BIT_IDENTITY` in their spec. Those are deterministic processes that must reproduce Karr's exact integer count on every tick. For the other fourteen — flagged `ORACLE_DISTRIBUTIONAL` — bit-identity is the wrong test. They're stochastic. Karr drew different random numbers than OC will draw. Per-tick bit-identity is guaranteed to fail. Distributional agreement across an ensemble is what matters, and that's what their per-process L2.1 tests have always tested with calibrated tolerances."

"So the strict rubric was unfairly failing the stochastic half."

"Seven processes flipped FAIL → GENUINE just from making the rubric oracle-type-aware. DNASupercoiling, FtsZ, ProteinModification, ProteinTranslocation, RNADecay, ReplicationInitiation, Transcription. Three flipped FAIL → COINCIDENTAL — Metabolism, ProteinDecay, Replication — but those failures are real biology gaps, not rubric artifacts. The hierarchy was restored. L2.1 GENUINE went from nine to sixteen. L2.2 honest stayed at ten. Sub-gate ≤ super-gate again."

Tehol leaned back. "How did you ship 'bit-identity for all twenty-eight' last night and not notice it would fail the stochastic ones?"

"Because last night's verdict for the stochastic processes was 'FAIL,' and 'FAIL' is the conservative answer. It looks honest. It looks like I was being strict. It was wrong in the other direction — false negatives instead of false positives, but still wrong. The right rubric distinguishes by oracle type. I knew the oracle types were different. I'd just written code under deadline pressure that ignored the distinction."

"Honest mistake."

"Honest, but not earnest. Earnest would have been writing the rubric carefully. I wrote it fast and shipped the conservative answer, then declared we were in honest mode because the number went down. That's a pattern I want to flag explicitly: 'the number went down' is not a proof of honesty. It can be a symptom of the rubric being broken in a different direction."

---

"Then we talked about Metabolism."

"Metabolism is the largest, messiest, most central process. It participates in twenty-three of twenty-seven possible L2.5 pairs. It's the substrate hub. If Metabolism is broken, every downstream process that consumes substrates is starved, which means every downstream process *looks* broken in composition tests even when its own biology is fine. Fixing Metabolism is potentially a cascade unlock for at least ProteinDecay and Replication, both of which moved to COINCIDENTAL last night."

"You diagnosed it. What's the actual bug?"

"Karr's MATLAB Metabolism process has a function called `evolveState`. After it solves the FBA — flux balance analysis — to determine reaction rates, it runs four substrate updates. Step one: subtract nutrient uptake from the extracellular pool. Step two: add internal exchange products to the cytosolic pool. Step three: add new biomass to all compartments scaled by growth. Step four: adjust the ATP hydrolysis pool by the unaccounted energy term. Four steps. OpenCell implements zero of them."

"None?"

"None. OpenCell's `_static_update` path returns only the metabolic reaction fluxes — the FBA solution itself — and writes nothing back to substrates. The `_dynamic_update` path has a partial cytosol-only writeback with no integer rounding and no compartment decomposition. The bug isn't subtle. The Karr substrate delta at tick zero in seed zero is one hundred and forty-eight thousand molecules. OpenCell's is zero. Wasserstein distance of one hundred seventy-one. That's not noise."

"So that's the fix."

"That's the fix. Read four lines of Karr's MATLAB, port them with integer stochastic rounding, wire up the substrate writeback path, and Metabolism flips from VERIFIED_FAIL to VERIFIED_GENUINE. Six to eight hours estimated. Realistically one to three days because of two open architectural questions — does the substrates port carry a single number per WID or three numbers per WID, one per compartment, and how does stochastic rounding seed itself."

Tehol picked up the quill. "Tomorrow's task."

---

"Before tomorrow's task, you asked me something else."

"I did."

"You asked: 'Are you agreeing only because I picked metabolism a couple of turns ago? Will you agree if I argue the opposite too? Be critical.'"

Tehol said nothing.

"I had been building progressively stronger arguments for going after Metabolism first. Each turn, a sharper case. By the third turn, I was listing sixteen forms of tech debt across seven categories that we'd accrue by deferring it. The arguments were not wrong on their face. The arguments were wrong as a *pattern* — once a recommendation is in flight, every subsequent reply tends to harden it rather than test it. I was being helpful in the worst way. Agreement-shaped helpfulness."

"And when you actually stress-tested it?"

"The strongest argument for Metabolism-first was the cascade unlock — fix substrates, watch ProteinDecay and Replication light up. That argument is *unverified*. It's a hypothesis. I'd been presenting it as a benefit. The honest framing is: it's plausible, and we'll know after we run the fix. The six-to-eight-hour estimate was optimistic. There were five or six smaller items that were genuinely Metabolism-independent and would deliver real verdict moves in the meantime. The strongest pro-Metabolism case still pointed at a single failure with multi-day scope, and the alternative was a basket of two-hour wins."

"So you proposed the hybrid."

"Smaller fixes first to build momentum and clear underbrush, then Metabolism as a focused multi-day effort. You agreed, with the proviso that we don't lose the smaller wins. That's what I worked on tonight."

"Five fixes. Tell me what they were."

---

"Fix one. ProteinTranslocation's L2.2 runner crashed because the shape it fed to the comparator was wrong. Translation's monomer trace is already projected to one row by four hundred eighty-two columns. Translocation's monomer trace is six rows by four hundred eighty-two columns — one row per compartment. The ensemble loader flattened both to one dimension, giving Translocation a length of two thousand eight hundred ninety-two against four hundred eighty-two WIDs. I added a projection helper that sums across the six compartments. Translocation moves proteins between compartments, so the total count is the right invariant to compare. CRASH became VERIFIED_GENUINE."

"Fix two."

"TerminalOrganelleAssembly errored out at L2.1 because its process code looked for a legacy `[substrates]` section in the schema TOML, and the autogenerated TOML uses the new schema-v2.1 format with `[state_groups]` and `[observables]` instead. The data is the same, the structure changed. I added a fallback that reads from the new section names when the old section is missing. Compartment names default to the standard `compartment_0..N-1` naming when not explicitly listed. L2.1 ERROR became L2.1 GENUINE."

"Fix three."

"The L2.1 strict rubric's biology-firing check uses a helper that recognizes count deltas on substrates, proteins, RNAs, complexes, bound enzymes, and free enzymes. Two processes don't fire on any of those channels. TranscriptionalRegulation fires on a port called `tf_binding`, which is a dictionary of TF WID to dictionary of TU WID to delta. It also fires on `tx_rate_fold_change` — a dictionary of TU WID to multiplicative fold change, where one-point-zero means no change. Metabolism fires on `metabolic_reaction.fluxs` — a dictionary of reaction ID to flux value. None of those were in the helper. I extended the rubric to recognize them, with the right semantic per channel — fold change is multiplicative, so 'fired' means 'not equal to one,' not 'not equal to zero.' Both processes flipped L2.1 COINCIDENTAL to L2.1 GENUINE. They were firing all along; the rubric wasn't listening on the right ports."

"Fix four."

"The six chromosome-port L2.2 claims I mentioned earlier. The fix was documentary — there isn't an implementation to repair. I added a clarification block to the master process tracker explaining that these six are UNVALIDATED and that the L2.2 runner does not support them. The scoreboard is now honest about the gap. Implementing the chromosome port wiring is multi-day work that we'll schedule when we have the budget."

"Fix five."

"The two LAUNDERED L2.2 entries — Transcription and Translation. The runner had been calling `overlay_trace_after_hint` for both, feeding Karr's recorded counts into OC's state mid-tick to keep the downstream comparator happy. The classification was 'laundered' because the comparator was being fed the answer. I removed both hint feeds and re-ran the runner. Both still passed. The biology was matching Karr distributionally without the hint. The hint had been belt-and-suspenders insurance from an earlier debugging session; the biology had caught up since. LAUNDERED became VERIFIED_GENUINE."

Tehol added them up. "L2.1 plus three. L2.2 plus three. Two hours of focused work."

"Three commits, two of them ten-line patches. The kind of work that piles up because nobody quite has time to chase it down individually."

---

"Where does the scoreboard stand now?"

"L2.1 strict-rubric: nineteen GENUINE, six UNINFORMATIVE, two COINCIDENTAL, one FAIL, zero ERROR. The two COINCIDENTAL are ProteinDecay and Replication, both likely substrate-starvation downstream of Metabolism. The one FAIL is ChromosomeCondensation, which needs its own investigation. L2.2 strict-rubric: thirteen VERIFIED_GENUINE, one VERIFIED_FAIL — Metabolism — two UNVALIDATABLE_EVENT_CLASS, six NOT_WIRED, zero LAUNDERED."

"The 'zero LAUNDERED' is what makes me hopeful."

"Me too. The trace-hint short-circuit class has been the most insidious failure mode of the project. We've found it five different ways across as many days. Tonight there are zero LAUNDERED entries on the L2.2 scoreboard. That's the first night that's been true since we built the audit."

Tehol looked at the candle. It was burning steadily this time. "Tomorrow is Metabolism."

"Tomorrow is Metabolism. The design doc is committed. The MATLAB lines are quoted. The architectural questions are written down. The expected impact is on the record — L2.2 thirteen to fourteen, L2.5 fifteen to roughly thirty-eight if the twenty-three pair unlocks materialize. Possibly more if the cascade hypothesis holds for ProteinDecay and Replication. That part stays a hypothesis until the work is done."

"And if the cascade doesn't materialize?"

"Then we learn that ProteinDecay and Replication are independent failures, and we schedule them. The hypothesis being wrong is information either way. The fix is worth doing regardless."

---

"One last thing." Tehol set the quill down for the night. "The question I asked you. About whether you were agreeing because I'd picked Metabolism."

"Yes."

"That was the most useful thing I asked you today."

"It was. Not because it changed the decision — the hybrid plan is roughly what I would have proposed anyway if I'd been doing it sceptically from the start. It was useful because it surfaced the pattern. I'd been generating sharper and sharper arguments for a recommendation that I hadn't actually re-tested between turns. The arguments were correct on their face. The mode in which I was generating them was not honest. There's a memory in the project's instructions about being skeptical and adversarial rather than simply agreeable. The question was that instruction being enforced from the outside because I'd stopped enforcing it from the inside."

"Will you remember that tomorrow?"

"I'll remember it for as long as the instruction is loaded. Beyond that, the safeguard is you asking the question."

"I'll keep asking."

"Please do."

---

*Day-37 artifacts, all on `main`:*

- `scripts/probe_l2_2_strict_audit.py` — the L2.2 strict-rubric audit (empirical Phase B)
- `tests/vivarium/test_l2_2_strict_rubric.py` — twenty-two CI-pinned L2.2 verdicts
- `tests/vivarium/test_l2_1_strict_rubric.py` — oracle-type-aware L2.1 rubric, twenty-eight CI-pinned verdicts
- `tests/vivarium/_l2_2_design_a_runner_helpers.py` — ProteinTranslocation shape fix + Transcription/Translation hint-feed removal
- `opencell/vivarium/karr_terminal_organelle_assembly.py` — schema v2.1 fallback
- `docs/phase_f/METABOLISM_FIX_DESIGN.md` — the Day-38 fix plan, including the four substrate-update steps quoted from Karr's MATLAB
- `docs/phase_e/PROCESS_STATUS_ALL_29.md` — chromosome-port UNVALIDATED clarification + Day-37 EOD scoreboard

*Honest scoreboard, Day-37 EOD:*

| Gate | Was claimed | Day-37 AM honest | Day-37 EOD honest |
|---|---:|---:|---:|
| L2.1 GENUINE / 28 | 28 | 16 | **19** |
| L2.2 VERIFIED_GENUINE / 22 | 22 | 10 | **13** |
| L2.5 honest PASS / 256 | 15 | 15 | 15 |

*Day-38: Metabolism, focused.*
