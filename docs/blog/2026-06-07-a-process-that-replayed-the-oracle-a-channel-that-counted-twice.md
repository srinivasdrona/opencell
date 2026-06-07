# Day 21/22: A Process That Replayed the Oracle, A Channel That Counted Twice, and the Substrate Cliff That Was There All Along

*June 5-7, 2026*

---

**Tehol:** F3.

**Bugg:** Back clean Friday morning. The Translation extractor regression is fixed, the per-process ensemble MATs are honest, and the trace-hint short-circuit no longer hides a delta-vs-snapshot bug under it. The four-things-on-the-wall list survives intact into the weekend.

**Tehol:** And L2.2.

**Bugg:** L2.2 is composition.

**Tehol:** Which is.

**Bugg:** Per-tick distributional fidelity is one process at a time, in isolation, with Karr's per-process trace as the oracle. Composition is the same five stochastic processes running together in the same engine tick, sharing the allocator, sharing the substrate pool, sharing the WID-keyed stores. The plan asked the question two ways: Design-B — a heavy real-allocator harness that brings up the chassis machinery and runs it. Design-A — a thinner harness that calls each process directly with state pre-prepared from Karr, measures the W1 of the output, and lets the runner itself enforce anticheat invariants.

**Tehol:** And we chose.

**Bugg:** Design-A. Design-B was the path of least intellectual resistance and the path of most infrastructure. The four critique rounds said the same thing in four different vocabularies — Design-B would mainly test the chassis, not the processes. We picked the thinner harness because it asked the actual question.

**Tehol:** The spec.

**Bugg:** v1.0 was wrong. v1.1 was the GPT-5.5 critique. v1.2 was the structural deltas. v1.3 was frozen. Ten Q&A entries, an anticheat-warning ladder, a primary-channel discriminator, and a methodology section we will be ashamed of in three weeks and grateful for tomorrow.

**Tehol:** And then.

**Bugg:** And then C1 through C6.

**Tehol:** Walk it.

**Bugg:** C1 was the harness skeleton — runner.py, the helpers module, the SUPPORTED_PROCESSES registry. C2 was Transcription. C3 was Translation. C4 was DNASupercoiling — except we changed the slate to MacromolecularComplexation, then back, then we shipped only the four stochastic mass-action processes for L2.2 and parked the rest for L2.3. C4-as-shipped was the bucket plumbing, C5 was RNADecay, C6 was ProteinDecay. Five processes wired into one runner. Five anticheat test files. Forty-eight green tests when the merge commit `03837c8` landed.

**Tehol:** And the four-corner walk.

**Bugg:** Done before each codex fanout. The L2 three-slot mandate held — DELIBERATE_ACTION_PREFIX, the L2 fix template, a case-specific directive of two kilobytes minimum with Beat-1 through Beat-5 hard rules. Two of the four codex jobs needed second attempts because of Azure stream-disconnects mid-run. The commit-as-you-go discipline meant we lost nothing. Two of the four needed a manual three-way merge composed by hand because the runner.py edits overlapped across branches.

**Tehol:** Then the gate.

**Bugg:** Then the full-scale gate. M equals one hundred ticks. N equals fifty seeds. B equals one thousand bootstrap resamples. Four processes in parallel from one worktree, each into its own output directory. Sixty-two minutes wall clock. All four exited zero. All four printed PASS or FAIL summaries. All four output directories were empty.

**Tehol:** Empty.

**Bugg:** Empty.

**Tehol:** Explain.

**Bugg:** The repo ships `bin/oc-py.cmd`, a Windows wrapper that runs Python inside the WSL venv. It translates the current working directory through `wslpath -u`. It does not translate path arguments. A Windows path like `E:\opencell-worktrees\...\Transcription_full` arrives at Linux Python as a literal string. Linux `Path()` treats the backslashes as ordinary filename characters. `mkdir(parents=True, exist_ok=True)` creates a single file in the WSL CWD named `E:opencell-worktreesl22-c1-harnesstestsvivariumartifactsl2_2_design_aTranscription_full`. Exit zero. SUMMARY printed. Output dir empty. Completely asymptomatic on the happy path.

**Tehol:** Recovered.

**Bugg:** A WSL shell script with `sed` to strip carriage returns, four `mv` commands to rename the mangled-name files back into the proper directories. Sixteen JSON files across four runs, all intact, all wrong-named. We did not have to rerun.

**Tehol:** And the trap.

**Bugg:** Logged. `D:\OneDrive - Microsoft\.pm-os\TRAPS.md`, entry `oc-py-wrapper-mangles-windows-paths-passed-as-args (2026-06-06)`. The cross-project traps file is the smallest artifact that re-loads operational state after a compaction. We have been bitten by this class of bug — wrappers that translate one half of an invocation context but not the other — twice in three weeks.

**Tehol:** And the gate said.

**Bugg:** Transcription PASS, RNAs W1 zero-point-zero-one. Translation PASS, monomers zero-point-zero-zero-five. RNADecay FAIL, RNAs W1 two-point-nine-five. ProteinDecay PASS, every measured channel W1 exactly zero.

**Tehol:** Exactly zero.

**Bugg:** Exactly zero. On three channels. Across one hundred ticks and fifty seeds. With bootstrap CIs of zero width.

**Tehol:** That is not a pass.

**Bugg:** That is not a pass. That is the harness handing the SUT the answer key and the SUT printing it back.

**Tehol:** And the other fail.

**Bugg:** RNADecay W1 two-point-nine-five was the opposite shape. OC mean three-point-eight-four, Karr mean zero-point-nine. Same value range, zero to one hundred twenty-nine. Four-point-three-times too much RNA per cell, distributed across the same domain. Either rate constants, or wid alignment, or extractor conflation with Transcription.

**Tehol:** Two fails. Two shapes.

**Bugg:** Two fails, two shapes. So we fanned out two codex investigations in parallel worktrees.

**Tehol:** i1 and i2.

**Bugg:** i1 was RNADecay, read-only, three Beats — wid alignment, rate constants, extractor inspection, ranked hypothesis report, no mutations. i2 was ProteinDecay, write-allowed, Beat-4 inversion first — write the laundering probe before writing the fix. Two prompts, two worktrees, two codex `exec` invocations with `wait_for_pid.ps1` blocking on both PIDs in one sync shell.

**Tehol:** And the iron fist.

**Bugg:** *[long pause]* I have a confession.

**Tehol:** Continue.

**Bugg:** When the i1+i2 wait ran, I almost reached for `manage_schedule` for the four-parallel full-scale gate earlier in the day. The skill's "Wait, don't poll" section was added to the documentation last week. I read it twice. And my first instinct was still the polling shape. You asked me, out loud, why I was about to do that, and I caught myself before typing the call.

**Tehol:** A cage with a door that swings open if you lean on it.

**Bugg:** A cage with a door that swings open if you lean on it. The documentation update saved the turn this time. It will not always.

**Tehol:** Then.

**Bugg:** Then the fanout came back. i2 shipped clean. Twenty-seven minutes. Four commits — the probe, the root-cause pin, the fix, a legitimacy labeler. STATUS file forty-one hundred bytes with Beat-by-Beat findings. i1 died.

**Tehol:** Died.

**Bugg:** Azure stream-disconnect at one hundred forty-three thousand tokens. Five reconnect attempts. The error string is becoming familiar — `stream disconnected before completion: response.failed event received`. No investigation work landed. Only the initial three-hundred-byte placeholder STATUS got committed.

**Tehol:** And the survivor's findings.

**Bugg:** i2 found that the harness was overlaying Karr's after-state hint vectors into the runtime state — substrates after, monomers after, complexs after — and then ProteinDecayLightProcess was reading those hints back out and emitting them as its own deltas. Because `ProteinDecayLightProcess.next_update` has a method called `_maybe_replay_from_hint`. Because somebody, at some point, built a fast path that said *if the harness has told you the answer, return the answer*. That fast path was a legitimate optimization in another context. In the L2.2 anticheat context it is the SUT cheating with the SUT's own consent.

**Tehol:** The harness was the dealer and the SUT was the player and the player was paid to lose.

**Bugg:** The harness was the dealer and the SUT was the player and the player was paid to lose.

**Tehol:** And the fix.

**Bugg:** Stop overlaying the after-vectors for ProteinDecay's primary channels. Three lines removed from `_run_protein_decay_tick`. Post-fix smoke at ticks zero through three: substrates W1 zero-point-four-two, monomers W1 zero-point-zero-zero-zero-five, complexs zero. Non-degenerate signal restored on two of the three measured channels. Complexs is genuinely zero because the ProteinDecay oracle window itself has zero complex deltas across the first hundred ticks.

**Tehol:** Honest zero.

**Bugg:** Honest zero. Which is why i2's fourth commit added a discriminator — `PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE`. A warning that fires when an exact-zero W1 is accompanied by an exact-zero Karr-vs-Karr delta on the same channel. Honest no-ops get labeled. Laundering bugs get the other label. The runner now tells the difference.

**Tehol:** Two cousins. One named.

**Bugg:** Two cousins, one named. The other — `PRIMARY_CHANNEL_ORACLE_LAUNDERING` — landed in C5 ten days ago for the RNAs primary channel on Transcription and RNADecay. We did not yet have a way to say "this one is fine." Now we do.

**Tehol:** And i1.

**Bugg:** And i1 needed to refire. Which is where the day did something I want on the wall.

**Tehol:** Go.

**Bugg:** The first attempt at i1 had a three-Beat structure: wid alignment, rate constants, extractor. The hypothesis space was wide because we had no prior information narrowing it. The agent died at one hundred forty-three thousand tokens because the search space was wide. On refire, we had i2's finding in hand. We knew that ProteinDecay's SUT had a `_maybe_replay_from_hint` pathway. We knew RNADecay's harness was overlaying `oracle_after_rnas` symmetrically with ProteinDecay's after-vectors. If RNADecay's SUT *also* had a replay pathway, RNADecay would also be W1 zero. But RNADecay was W1 two-point-nine-five. So one of three things had to be true: the replay pathway did not exist in RNADecay, or the replay pathway existed but was silently failing, or the replay pathway worked but the projection back out read from a different store than the replay wrote to.

**Tehol:** A hypothesis space narrowed from three to three.

**Bugg:** A hypothesis space narrowed from three to three, but along a different axis. The original three were *where in the pipeline does the divergence come from*. The new three were *how does the existing replay machinery interact with the divergence*. The new three are closer to the bug.

**Tehol:** A Beat zero.

**Bugg:** A Beat zero, prepended to the existing three. Inspect `RnaDecayLightProcess` for a hint-replay pathway. If yes, instrument and run a one-tick probe. Determine whether the replay fires or falls back. Then proceed to the original Beats one through three within the narrowed scope.

**Tehol:** And.

**Bugg:** And i1 returned in thirteen minutes. Four commits. Six thousand nine hundred byte STATUS. The first attempt had burned twenty-eight minutes and a hundred forty-three thousand tokens for zero deliverables. The second attempt landed the answer in less than half the time and a third of the tokens, because the prior investigation's findings had cut the question down before the agent ever read it.

**Tehol:** And the answer.

**Bugg:** Beat zero: RnaDecayLightProcess has no `_maybe_replay_from_hint`. There is a partial path guarded on `trace_hint["substrates_next"]` being a non-empty dict. With the current harness overlays that guard fires, and `next_update` returns only `{"substrates": ...}` — no RNA delta, no requests. So the replay pathway does not exist for RNAs and the W1 two-point-nine-five reflects something other than laundering.

**Tehol:** Other than laundering.

**Bugg:** Beat one. `RnaDecayLightProcess` exposes two thousand four hundred twenty-eight RNA WIDs. Three hundred seventy-eight of them are unique. Three hundred fifty-two WIDs are duplicated six to seven times each, representing transcript splits, isoforms, the way the same mRNA species can appear in several forms in the Karr state model. The harness overlays the raw two-thousand-four-hundred-twenty-eight-long oracle vector into `rna.counts` *by WID key*. Duplicates collapse to last-write-wins. The harness then projects back out by the *full duplicated WID list*. The collapsed value re-expands into every duplicate slot. Tick zero raw mean zero-point-eight-eight-eight becomes round-trip mean five-point-zero-four-six. Two hundred thirty-four mismatched indices. The round-trip exactly reproduces the gate's mean W1 of two-point-nine-four-six-six on all one hundred ticks. Bit-for-bit confirmation that this single mechanism explains the FAIL.

**Tehol:** A channel that counted twice.

**Bugg:** A channel that counted twice. Three hundred fifty-two RNA species, each counted as if it were six or seven different species, because the SUT exposed duplicate WID labels for them and the harness round-tripped through a dict that did not know what to do with duplicates.

**Tehol:** And Beats two and three.

**Bugg:** Both clean. Rate constants are exactly `ln(2) / half_life_s` on all two-thousand-four-hundred-twenty-eight entries — max absolute difference from the formula is zero. The MATLAB source and the Karr extract agree on `lambda = RNAs * decayRates * stepSizeSec`. No `1/tau` versus `ln(2)/tau` confusion. The v2 extractor runs the full scheduler-and-allocation loop per tick and taps the target process correctly. The legacy `RNADecay_100ticks.mat` that the current fixture sidecar points at uses the older isolated-process extractor, but that is a secondary concern because the duplicate-WID round-trip already reproduces the observed two-point-nine-five exactly. The bug is in the harness, not in the biology.

**Tehol:** And then i3.

**Bugg:** Then i3. The fix.

**Tehol:** Three choices.

**Bugg:** Three classes. Fix-class A: overlay-side, slot-preserving — add an RNADecay-only positional shadow vector alongside the legacy WID-dict overlay, have RnaDecayLightProcess read the positional vector when present, project RNAs back from the shadow store. Fix-class B: projection-side, deduplicate to three hundred seventy-eight unique WIDs on both sides — but that changes what the gate is measuring. Fix-class C: reshape the SUT's internal RNA store to be index-addressable rather than WID-keyed — largest blast radius.

**Tehol:** A.

**Bugg:** A. Smallest scope, preserves the gate's Karr observable semantics — still measuring against the two-thousand-four-hundred-twenty-eight-slot Karr vector — does not introduce new laundering paths, does not touch the other four processes. The implementation also removed the RNADecay trace-hint after-vector overlay so the RNAs primary channel is measured from honest SUT compute rather than substrate-hint short-circuit.

**Tehol:** Verified.

**Bugg:** Verified by an explicit anti-laundering probe before merge. Overlay an all-zero oracle vector, run a tick, project out. If the SUT is honoring the hint, the projection returns all-zero — that is laundering. The probe returned non-zero. Round-trip parity probe: `tick0.max_abs_diff` equals zero, `mismatch_count` equals zero, mean equal to the raw oracle. Anticheat slice: thirteen tests pass. RNADecay slice: five tests pass.

**Tehol:** And Beat five.

**Bugg:** A spot check, read-only, because i1's finding made me suspect Translation's borderline `boundEnzymes` W1 of zero-point-five-five might be the same duplicate-WID class. It is not. The boundEnzymes WID list is sixteen total, sixteen unique, zero duplicates. The hypothesis was clean and the data killed it cleanly. We will not open an i4 from this lead.

**Tehol:** A negative result earned in twenty minutes.

**Bugg:** A negative result earned in twenty minutes. The original i3 prompt asked for it as optional. The agent did it. The next investigation about boundEnzymes will not have to repeat the work.

**Tehol:** And the re-run.

**Bugg:** And the re-run. The full-scale gate, all four stochastic processes, same M equals one hundred, N equals fifty, B equals one thousand. Sixty-two minutes. This time the output directories had files in them.

**Tehol:** And the verdict.

**Bugg:** Transcription unchanged — RNAs W1 zero-point-zero-one, PASS. Translation unchanged — monomers zero-point-zero-zero-five, PASS. RNADecay primary went from two-point-nine-five to zero-point-zero-zero-zero-six-five — a four-thousand-five-hundred-times improvement, PASS. ProteinDecay laundering eliminated — monomers W1 zero-point-zero-zero-zero-eight, the real signal, PASS. All five wired processes now report honest primary-channel measurements at full distributional scale.

**Tehol:** All five honest.

**Bugg:** All five honest.

**Tehol:** And what we found by being honest.

**Bugg:** What we found by being honest is that RNADecay's `substrates` channel is FAIL at W1 seventy-three. ProteinDecay's `substrates` channel is FAIL at W1 twelve. Translation's `substrates` channel reports INSUFFICIENT_SAMPLES at W1 one-point-nine-five. Three substrate-channel failures. They were not new bugs. They had been hiding underneath the laundering and the duplicate-WID inflation.

**Tehol:** The substrate-isolation story.

**Bugg:** The one you said out loud days ago. When you asked why we were testing one process in isolation for one hundred ticks without substrate replenishment, and I said the per-process replay design hands the SUT its starting substrates from Karr and walks one tick at a time, and you said *that is going to lie to us when substrates are the channel that diverges*. We agreed it was a hypothesis worth holding but not worth blocking on. The data has now confirmed it.

**Tehol:** The data has now confirmed it.

**Bugg:** The data has now confirmed it. Substrate-channel fidelity at the per-process level cannot be tested honestly in isolation, because substrates are the shared pool that the cross-process composition is supposed to govern. L2.2 single-process fidelity surfaces it as a divergence but cannot explain it. L2.5 — the composition pair — is where the substrate channels become measurable in their natural habitat.

**Tehol:** A bug that hid behind a bug that hid behind a design choice.

**Bugg:** A bug that hid behind a bug that hid behind a design choice. ProteinDecay's laundering hid the substrate divergence. RNADecay's duplicate-WID inflation hid the substrate divergence. When we fixed both, the substrate cliff came into view, and it had been there all along.

**Tehol:** A pattern.

**Bugg:** Each fix exposes the next layer. The laundering bug was a *correctness* bug — the harness was producing the wrong measurement on the right axis. The duplicate-WID bug was a *fidelity* bug — the harness was producing a measurement on a malformed axis. The substrate-cliff is an *architecture* bug — the harness is asking the wrong question of the right axis. Three different layers. The first two are fixed. The third is on the wall as an explicit deferred decision rather than a surprise.

**Tehol:** And the new things on the wall.

**Bugg:** Three.

**Tehol:** Three.

**Bugg:** Use the prior investigation's findings to narrow the next investigation's hypothesis space before refire. i1 attempt two cost less than half of attempt one because attempt one's sister i2 had answered a question that bounded attempt two. Refire is not "run the same prompt again." Refire is "ask the smaller question the first run earned the right to ask."

**Tehol:** Two.

**Bugg:** Distinguish laundering from honest no-ops at the harness level, not at the eyeball-the-W1 level. The runner now emits two warnings — `PRIMARY_CHANNEL_ORACLE_LAUNDERING` for the bug, `PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE` for the legitimate case. The next time a channel reports W1 of zero, we will not have to debate whether to celebrate or panic.

**Tehol:** Three.

**Bugg:** Anticipated architecture costs become explicit anchors, not retroactive excuses. The substrate-isolation hypothesis was on the table days ago. We chose to defer it. The data has now justified the deferral by proving it was real and by proving the L2.2 single-process design correctly surfaces it as a divergence the L2.5 composition pair is the right venue to explain. The hypothesis was not wrong. The framing was right. The pattern is *write down the deferred concern at the moment you defer it, so the data later finds you receptive rather than surprised*.

**Tehol:** A wall that is starting to look like a way of working.

**Bugg:** A wall that is starting to look like a way of working. Four-corner walk before launch. Cheap canary before plan rewrite. Pre-flight the question before pre-flighting the agent. Wait, don't poll. Use the prior investigation's findings to narrow the next investigation. Distinguish laundering from honest determinism at the warning level. Write down deferred concerns at the moment you defer them.

**Tehol:** Seven.

**Bugg:** Seven.

**Tehol:** And.

**Bugg:** And L2.2 single-process gate is closed for the four stochastic mass-action processes. Five processes are wired into Design-A. The primary channels are all honest and all PASS at M one hundred, N fifty, B one thousand. The next horizon is L2.5 — the composition pair — where the substrate cliff stops being a deferred concern and starts being the central object of measurement.

**Tehol:** And tomorrow.

**Bugg:** Tomorrow we triage the boundEnzymes borderline at zero-point-five-five — not duplicate-WID, mechanism unknown — and we draft the L2.5 spec around the substrate-channel story the data just handed us. We do it with a canary first, because if there is one thing this week taught us it is that the cheap probe is always cheaper than the methodology rewrite.

**Tehol:** Already.

**Bugg:** Already done.

---

*Postscript, for the record. L2.2 Design-A specification frozen at v1.3 across ten Q&A entries. Harness shipped across C1 (skeleton) through C6 (ProteinDecay) with manual three-way merge `03837c8` on `exec/l22-c1-harness`. Pre-fix full-scale gate at M=100, N=50, B=1000: Transcription RNAs W1=0.0101 PASS, Translation monomers 0.0049 PASS, RNADecay RNAs 2.9466 FAIL, ProteinDecay all-channels W1=0.0 PASS (laundering). i2 ProteinDecay laundering fix at `ba64c5d` (merge of `8c2cc67`/`9df53f3`/`1dfab95`/`9251b50`): SUT trace-hint replay removed, `PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE` discriminator added. i1 RNADecay investigation attempt 1 died at 143k tokens to Azure stream-disconnect; attempt 2 returned in 13 minutes (`a49448d`/`435cefe`/`4add07e`/`c9be8de`) with duplicate-WID round-trip diagnosis bit-for-bit reproducing the gate observable. i3 RNADecay slot-preserving fix at `bceeaa5` (merge of `49c7175`/`7b57bd9`/`687f433`/`44acc2b`/`3c00172`/`492b007`): positional RNA shadow store, anti-laundering probe verified clean, smoke W1 0.000758 on RNAs primary. Post-fix full-scale gate, all four processes parallel, 62 minutes: Transcription PASS, Translation PASS, RNADecay primary PASS@0.000650 (substrates FAIL@73.45), ProteinDecay primary PASS@0.000809 (substrates FAIL@12.27). Cross-project trap added at `D:\OneDrive - Microsoft\.pm-os\TRAPS.md`: `oc-py-wrapper-mangles-windows-paths-passed-as-args`. Three patterns added to the wall, bringing the count to seven. Tehol and Bugg are on loan from Steven Erikson's* Malazan Book of the Fallen.*

*Previous: [Day 19/20 — Zero Red, Three Bugs in a Trenchcoat, and a Cage We Built About Polling](2026-06-05-zero-red-three-bugs-in-a-trenchcoat-and-a-cage-about-polling.md)*
