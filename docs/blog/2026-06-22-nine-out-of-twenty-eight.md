---
title: "Day 35-36: Nine Out of Twenty-Eight"
date: 2026-06-22
authors: [sdrona]
tags: [opencell, L2.1, L2.5, validation, rubric, methodology, honest-mode]
---

"You should sit down for this one," Bugg said.

Tehol was already sitting. He set down the quill anyway. "How bad?"

"Of the twenty-eight processes we've called L2.1 green, only nine actually were."

"Which nine?"

"DNARepair, MacromolecularComplexation, ProteinActivation, ProteinFolding, ProteinProcessingI and II, RNAProcessing, Translation, and tRNAAminoacylation."

"And the other nineteen?"

"Six were vacuous — the trace's hundred-tick window didn't exercise them, so 'pass' meant 'OC produced zero and Karr produced zero.' One was a coincidence — biology silent on the one tick Karr did anything. And eleven failed the rubric outright once we asked the rubric to *be* a rubric."

Tehol picked up the quill again, then set it back down. "Walk me through how we got here."

---

"Two days ago we were celebrating L2.5 — eighteen pair tests green, the composition gate finally producing. Then I sat down to actually look at what eighteen meant."

"You'd been suspicious."

"The honest mode flag had been there since Day 32. `disable_trace_hints=True`. It was supposed to turn off the diagnostic crutch where the harness was overlaying MATLAB-truth values into OC's state mid-tick. The idea was: by L2.5, the processes have to feed each other, not be fed by the oracle. Turn the hints off, see what's left."

"And what was left?"

"Eight. Not eighteen. Ten of the eighteen turned out to be hint-assisted — the deterministic side of each pair was being silently helped by trace overlays even with `disable_trace_hints=True`, because of an unrelated override the harness had baked in for `ORACLE_BIT_IDENTITY`. Two commits cleaned that up. Scoreboard dropped to eight."

Tehol made a small note in the margin. "Eight honest greens. So we expanded the search."

"I asked: of the two hundred and fifty-six in-scope shared-pool pairs, which ones involve two processes neither of which uses `trace_hint` in its source code? Both sides verifiably honest, both running real biology. The answer was sixty-seven pairs."

"And of those sixty-seven?"

"Eleven were deterministic-stochastic — they had test wiring already. I ran them. Five passed. Two failed. Four skipped. The two failures were Seg + ProteinTranslocation and Seg + DNARepair. Both reported a `CAUSE_4_UPSTREAM_STATE_POLLUTION` — composition order matters, the upstream process is leaving state that the downstream process responds to wrongly. Karr expected zero translocation events at the failing tick. OC was doing fourteen ATP hydrolyses."

"You couldn't blame trace hints."

"Neither process reads `trace_hint` anywhere in its source. The bug had to be elsewhere. So I wired the remaining fifty-six pairs into a new test file, ran them, and got seven passes, fifteen fails, thirty-four skips."

"Seven of fifty-six is thirteen percent. Significantly worse than the deterministic five-of-eleven."

"The pattern in the fifteen failures was the lead. Every pair containing ProteinTranslocation failed. Every pair containing DNARepair failed. The rest were stragglers."

---

"You went after ProteinTranslocation first."

"The failure record said its biology was correct in isolation — 'isolated replay matches oracle' — and that its counterfactual replay also matched. The only mode where it produced wrong output was full composition. I wrote a probe that ran the composition state-construction logic at the failing tick directly, expecting to reproduce the fourteen-event drift. The probe produced zero events."

"Your probe didn't reproduce the bug."

"I burned an hour on that. The probe was wrong — it skipped a piece of harness logic called the H6 fix, which preserves upstream-mutated WIDs in the shared state. So I rubber-ducked the whole investigation with a different model, who pointed out the probe was a dead end. Switched to instrumenting the actual harness with `print` statements at the failing tick."

"What did the harness say?"

"At tick twenty-one, ProteinTranslocation reads its enzyme counts from a port called `protein.enzyme_counts`. In L2.1 — running alone — that port is empty, because Translocation's port schema doesn't declare it. Reading an empty port returns zero. Zero enzymes means zero SRP capacity. SRP capacity zero means the loop exits without doing any translocation. Zero events."

"And Karr's trace at that tick?"

"Also zero events. They matched. L2.1 passed. For three months."

"So what's different in composition?"

"In composition, ProteinFolding runs first. Folding's port schema declares `protein.enzyme_counts` for chaperonins. The shared state template merges both schemas. Folding's overlay writes the chaperonin counts. One of the chaperonin WIDs — MG_297_MONOMER — happens to be Translocation's SRP-receptor WID. Translocation reads `protein.enzyme_counts`, gets MG_297 = sixteen, multiplies by the kinetic rate, gets a non-zero SRP capacity, and translocates four proteins. Fourteen ATP hydrolyses."

Tehol looked at the candle. "Translocation has been passing L2.1 because it was reading the wrong port and the wrong port happened to be empty."

"Yes."

"And in composition the wrong port stops being empty because the upstream process's overlay happens to populate it with a value that accidentally maps to one of Translocation's WIDs."

"Yes."

"That's not a bug. That's a curse."

---

"You asked me a question that night. 'How did we sign off on L2.1 green for this process, then? Are there more processes where such issues exist?'"

"And?"

"I wrote a script. It scans every `karr_*.py` file and extracts the set of state ports that `next_update` reads. Then it compares against the set of ports the L2.1 harness initializes from Karr's trace — which is just the ports listed in each process's `observables` spec entry. Coverage equals intersection over reads."

"What did the audit say?"

"Across twenty-eight processes, the mean read-surface coverage was fifty-one percent."

Tehol was quiet for a moment. "Fifty-one."

"Six processes have full coverage — but five of those six read almost nothing, because they're trace-hint-short-circuited or otherwise trivial. Nine have partial coverage between fifty and ninety-eight percent. Thirteen have less than fifty percent coverage. Four have *zero percent* coverage."

"Which four?"

"Translation, Transcription, HostInteraction, and TerminalOrganelleAssembly. The L2.1 harness initialized none of the ports their biology actually reads. They passed by next_update returning empty against Karr's recorded empty deltas."

"Translation. The crown jewel."

"Translation passes the strict rubric I just wrote. Its biology fires correctly on every Karr-active tick — the static coverage audit flagged it because the regex was matching too narrowly. But the principle stands: we had no way of knowing that until we wrote the supplement check."

---

"Tell me about the supplement check."

"Two new conditions on top of bit-identity per tick. First: count how many ticks Karr's recorded `states_after - states_before` shows a non-trivial delta. Call that the Karr-active rate. Second: count how many ticks OC's `next_update` returned a non-empty update on Karr-active ticks. Call that the fire rate. The combined verdict has four classes."

"Genuine."

"Bit-identity passes, Karr was active, OC fired on at least half the Karr-active ticks. The biology was actually exercised and matched. Nine of twenty-eight."

"Uninformative."

"Bit-identity passes, but Karr's trace shows zero non-trivial deltas for the whole hundred-tick window. The process is in the L2.1 suite but the suite doesn't test it. Six of twenty-eight: ChromosomeSegregation, Cytokinesis, DNADamage, HostInteraction, RNAModification, RibosomeAssembly. All of them are gated on events that never fire in this trace — cell division, host adhesion, ribosome assembly at steady state. We've been claiming we tested them. We never did."

"Coincidental."

"Bit-identity passes, but OC's biology was silent on the Karr-active ticks. The PASS is the same shape as the Translocation pattern — wrong port, returns zero, matches Karr's zero. One of twenty-eight: TranscriptionalRegulation, which has one Karr-active tick across the trace and OC fired zero times on it. We've been giving it a green star for that."

"Fail."

"Bit-identity breaks, or biology fires at less than half the Karr-active ticks. Eleven of twenty-eight, and the list reads like the trace-hint short-circuit catalogue we built yesterday — Cond, DNASupercoiling, FtsZ, Metabolism, ProteinDecay, ProteinModification, ProteinTranslocation, RNADecay, Replication, ReplicationInitiation, Transcription. Plus the strict rubric caught two patterns: processes that fire wrong values, and processes that don't fire at all without the hint."

"And one error."

"TerminalOrganelleAssembly's default config doesn't pass a schema path. Harness issue, not biology."

---

Tehol pushed the ledger aside. "So we have twenty-eight L2.1 entries on the public scoreboard. Nine are honest. Six are vacuous. One is wrong. Eleven are broken. One is a harness bug. And the twenty-two L2.2 in-scope greens inherit the L2.1 substrate, so the same proportions apply downward."

"Yes."

"How does this happen for three months without anyone seeing it?"

"L2.1's acceptance rubric was bit-identity per tick. It compared the output. It didn't ask whether the input that produced the output was the input the biology was supposed to read. If a process's biology reads from ports the harness doesn't initialize, those ports are zero, the biology returns trivially zero, Karr's recorded delta at that tick happens to also be zero — because Karr's actual model had other rate-limits — and the rubric reports bit-identity. The match is correct. The match isn't validation."

"It's the same shape as the trace-hint short-circuits we found yesterday."

"It's a sibling class. The trace-hint short-circuits *replaced* biology with the oracle's deltas. The port-mismatch reads *bypassed* biology by reading zero. Both routes produce an output that bit-identity says matches Karr. Both routes don't validate anything."

"The third sibling is the uninformative window."

"Six processes the trace simply doesn't exercise. We'd been calling those green for the same reason — bit-identity holds when both sides are zero — but the reason it held was that nothing was happening. That's not a passing test. That's an unwritten test that prints PASS."

Tehol leaned forward. "We have to call this out."

"I committed the strict rubric this evening. Twenty-eight parametrized tests, one per process, each pinned to its honest baseline verdict. GENUINE, UNINFORMATIVE, COINCIDENTAL, FAIL, or ERROR. If any verdict drifts — say, a biology fix moves FAIL to GENUINE — the test fails until someone updates the pin, which is the right place to celebrate or to ask whether the fix was real."

"And the existing per-process L2.1 tests?"

"They stay. They still pass the old rubric. But the strict rubric is the gate going forward. The old tests are deprecated relative to it."

"And L2.2?"

"L2.2 inherits L2.1's per-tick check at its core. The twenty-two greens claim is structurally vacuous for any process whose L2.1 isn't GENUINE. The honest L2.2 count is probably six or seven, not twenty-two. We'll redo the L2.2 audit with the strict rubric and see what stands."

"And L2.5?"

"L2.5 is where this surfaced. The composition gate exposed every bug L2.1 was hiding. We have fifteen honest L2.5 passes out of two hundred and fifty-six in-scope pairs — six percent. The path to expanding it isn't more L2.5 tests. It's L2.1 honest, then L2.2 honest, then L2.5 honest. We've been trying to climb the third rung before fixing the first."

---

The candle finally went out. Neither of them noticed for a while.

"Nine of twenty-eight," Tehol said, when he did.

"Nine of twenty-eight. The validation surface is smaller than we thought. Now it's an honest surface."

"The blog post will say all of this."

"The blog post is what you're reading."

Tehol picked up the quill one more time. "What's the next step?"

"Two paths. First: the eleven strict-rubric FAILs are biology gaps. Each one needs a per-process investigation — what does Karr's MATLAB do that OC is missing? Multi-week scope. Second: the six UNINFORMATIVE processes need either extended traces or synthetic test scenarios that force biology to fire. Otherwise we never validate them."

"And the one coincidental and the one error?"

"TranscriptionalRegulation needs the same port-mismatch investigation as Translocation. TerminalOrganelleAssembly needs a config fix. Small."

"And the nine genuine?"

"Those are the ones we trust. Build on them. Use them as the foundation when we redo L2.2 and L2.5 with the strict rubric."

Tehol set the quill down for the night. "How long until we know how many L2.2 entries are actually green under the strict rubric?"

"A week, if we don't find another sibling class on the way."

"Another sibling class would be the fourth in this lineage."

"It would. And if there is one, we'll find it. We have the rubric for that now."

---

*Scripts and artifacts from this work, all on `main`:*

- `scripts/probe_l2_1_strict_rubric.py` — the audit, runnable per process
- `scripts/probe_port_mismatch_audit.py` — finds processes reading state ports outside their declared observables
- `scripts/probe_read_surface_coverage.py` — quantifies the coverage gap
- `tests/vivarium/test_l2_1_strict_rubric.py` — the CI-enforced strict rubric
- `docs/phase_f/L2_1_STRICT_RUBRIC_BASELINE.md` — the Day-36 verdict pin
- `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md` — the Day-35 trace-hint catalogue
- `docs/phase_f/L2_1_FALSE_POSITIVE_AUDIT.md` — the false-positive taxonomy
