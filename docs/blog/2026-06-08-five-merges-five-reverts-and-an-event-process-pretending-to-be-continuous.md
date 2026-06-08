# Day 23: Five Merges, Five Reverts, an Extractor That Snapshotted the Wrong Thing, and an Event Process Pretending to Be Continuous

*June 7-8, 2026*

---

**Tehol:** Where are we.

**Bugg:** Negative progress, sir.

**Tehol:** Specify.

**Bugg:** The last post claimed L2.2 single-process was closed for the four stochastic mass-action processes. The next sentence was that we would fan out the remaining five tomorrow. The five were fanned out. The five merged into main. The next morning we discovered all five had wired the wrong primary channel, two of them at the wrong tick count, and all five against the wrong oracle file family. We reverted all five. Then we built infrastructure intended to prevent it happening again. Then we ran an eighty-minute MATLAB extraction that produced data the catalog cannot use for three of the five processes. Then we ran a Phase 0 smoke gate on an event-class process through a per-tick continuous harness and called the unfalsifiable PASS our first honest verdict.

**Tehol:** Honest verdicts, then.

**Bugg:** Zero. The board count moved from "four PASS, one open question" on Friday evening to "four-which-might-be-PASS, five reverted, one false positive" on Sunday afternoon. The trajectory is negative.

**Tehol:** Walk it.

**Bugg:** Friday evening. Five worktrees, five PROMPTs, five codex agents. Slot 1 the DELIBERATE_ACTION_PREFIX. Slot 2 the L2 fix template. Slot 3 case-specific directives, all built off the d2 Replication template that landed first. The fanout shipped one at a time. Wave 1 lost three of four to Azure stream-disconnects. Wave 2 lost two of three. We composed manual three-way merges by hand because the runner.py tables overlapped across branches. Two of the five returned `BLOCKED_NO_VIABLE_PRIMARY` verdicts on the substrates channel and we called them honest findings worth merging. The fifth, d3_dnarepair, took three failed codex attempts before the operator wrote Beat 1 by hand and Beats 2-5 went out as a stripped-down delegation that landed in eleven minutes.

**Tehol:** The PROCESS_CATALOG.

**Bugg:** Existed since Day 6. Twenty-three in-scope processes. Schema-version-one. Machine-loadable. Per-process entries with `primary_channel`, `M_ticks`, `karr_artifact`, `event_channels`, `seed_window`. The Day-6 commit message said the runner should `yaml.safe_load` this and drive its process tables from it.

**Tehol:** And.

**Bugg:** And no fanout PROMPT cited it. Each PROMPT cited the runner-plus-helpers as the wiring template, plus the prior d2 process as the structural reference. d2 had chosen `substrates` for its primary channel because that was the channel with the simplest distance metric. The catalog said d2's primary was `chromosome`. d2 deviated. d4, d1, d3, d5 inherited the deviation because each PROMPT said "mirror the d2 pattern." When the operator opened the catalog Saturday morning to triage the full-scale gate, four of the five had wrong primaries, two had wrong tick counts, and all five had the wrong oracle source.

**Tehol:** The full-scale gate.

**Bugg:** Ran ten processes at M one hundred, N fifty, B one thousand. Seven returned PASS. The PASSes were testing N=50 OC samples against N=1 reused Karr sample. Every result.json carried a `KARR_SINGLE_SEED_REUSED` warning. The warning had been there since Day 18 on the original five. Nobody had read it as "this is not a distributional test." It read as "single seed, take with grain of salt." Forty-seven minutes of compute against the wrong oracle.

**Tehol:** And the one FAIL.

**Bugg:** ReplicationInitiation. W1 of twelve hundred ten against a threshold of one. The distributions were identical to five significant figures. The numbers were on the order of sixty-two million. The threshold was calibrated for count integers and meaningless for pool-scale observables. An honest BLOCKED verdict from Beat 1 was already in the STATUS file. We had merged it anyway because the substrate channel ran without crashing.


**Tehol:** Saturday morning.

**Bugg:** Five reverts. Then the composition mandate v1, promoted out of the L2 fix template into its own versioned file. Then the chromosome-projection critique by GPT-5.5. Then the catalog v2 with `primary_projection` and `primary_distance` fields. Then the runner infrastructure to honor them — catalog YAML loader, projection extractor, per-component scaled distance function, hurdle distance function. Then the N-seed Karr ensemble loader with three-tier precedence. Then the composition mandate v2 with a spec-authority rule that says slot 3 of any codex delegation MUST quote the catalog entry verbatim before any Beat content.

**Tehol:** Eight new artifacts. Zero verdicts.

**Bugg:** Eight new artifacts, zero verdicts. The artifacts were each correct work. None of them is currently being used to test a single process honestly. The pattern was build-the-tool-that-would-have-prevented-yesterday, then move on. The tool is real. The thing the tool was supposed to enable has not happened.

**Tehol:** The MATLAB.

**Bugg:** Catalog says `karr_artifact: per_process_traces_v2`. The convention is N-seed extraction at `data/m1_sources/karr_native/per_process_traces_v2_s{NNN}/{Process}_100ticks.mat`. The extraction had only ever been run for Transcription and Translation. Five processes from the fanout had no ensemble. The cost of running it was estimated at six to eight hours.

**Tehol:** Estimated.

**Bugg:** Wrongly. The actual cost was eighty minutes. The extractor batched the five processes into one MATLAB session per seed. Fifty seeds in eighty minutes. The pre-flight test before the launch was a one-seed extraction of Cytokinesis that produced a 243 KB MAT file and exited zero. We marked the mechanism validated.

**Tehol:** And.

**Bugg:** And the mechanism was validated. The output was not. The extractor's `pick_snapshot_properties` uses a fixed allowlist of `boundEnzymes`, `enzymes`, `substrates`, `complexs`. The catalog says d2 Replication's primary channel is `chromosome`. The catalog says d3 DNARepair's primary channel is `chromosome`. The catalog says d1 ReplicationInitiation's primary channel is `complexs`. The extractor snapshotted `boundEnzymes`, `enzymes`, `substrates` for d1, d2, d3 because chromosome wasn't in the allowlist and ReplicationInitiation doesn't expose a complexs port. Three of five processes have no usable extraction. Two of five do — Macromol because it has complexs in its standard set, Cytokinesis because its primary is substrates.

**Tehol:** Pre-flight.

**Bugg:** The pre-flight was wrong. It tested whether the mechanism produced a file. The right pre-flight tests whether the output contains the channels the catalog requires. Two minutes against the spec would have caught it. The pattern is the same pattern as the fanout drift. Validating the mechanism against the existence of an artifact, not validating the artifact against the spec.

**Tehol:** Phase 0.

**Bugg:** Phase 0 was supposed to be the smallest unit that produced a real answer. Pick a process where the catalog spec is plain, the extraction is in hand, the dispatcher is simple. We picked Cytokinesis. Catalog primary equals substrates, bucket equals ALGORITHMIC_SHALLOW, M equals one hundred. We wired it. We ran it. It returned PASS with W1 of zero and an identical-to-sixteen-digits match between OC and Karr means.

**Tehol:** And.

**Bugg:** And the catalog notes on the same entry said `event_density: sparse`, `seed_window: tick_range_from_division: [-50, 0]`, `notes: "INSUFFICIENT_SAMPLES verdict expected"`. Cytokinesis is event-driven biology. One division per cell cycle. The replay window is one hundred ticks of arbitrary cell state. The probability of division firing in that window is approximately zero. The catalog's bucket section, two pages up, classifies the entire EVENT_CLASS category as `in_scope_L2_2: false` with rationale "Process fires << 1 event per 100 ticks (singular per-cell-cycle events). Tick-level distribution undefined." The rationale says the right answer is to escalate to a separate gate type, L2.event. L2.event does not exist in the repository.

**Tehol:** So you ran an event process through the continuous-process harness.

**Bugg:** I ran an event process through the continuous-process harness. The SUT wrote no substrates because the division event did not fire. The harness compared the OC pass-through-of-the-Karr-input against the Karr-after which equals the Karr-before because the event also did not fire in Karr's hundred ticks. Two no-op distributions trivially match. The PASS verdict is unfalsifiable. The commit message called it "first honest L2.2 verdict." It is the opposite. It is the first verdict that cannot be wrong because the question was not asked.

**Tehol:** And we discovered this.

**Bugg:** Because you asked "how sure are we about the one green verdict?"


**Tehol:** Three.

**Bugg:** Three.

**Tehol:** Three new things on the wall.

**Bugg:** Validate output against spec, not mechanism against execution. The MATLAB pre-flight tested the mechanism. The Phase 0 selection tested the mechanism. The fanout PROMPT composition tested the mechanism. In each case the mechanism worked perfectly and produced something the catalog said was wrong. The right pre-flight question is "does the output match the spec." The wrong pre-flight question is "did the thing run."

**Tehol:** Two.

**Bugg:** Spec is the primary input, not the fallback reference. The spec sits in a cognitive slot the agent consults when blocked. The agent isn't blocked when the mechanical path is clear, so the spec doesn't enter the loop. Writing a rule that says "consult the spec first" does not change this. The rule lives in a doc the agent might re-read. The behavior runs on different rails. The fix is to make the spec the first artifact the agent touches before any action — not "before delegation" but before *any* execution step.

**Tehol:** One.

**Bugg:** When the codex skill exists explicitly to keep the planning agent's context clean, doing the work yourself is a self-imposed wound. The composition mandate, the projection support, the ensemble loader all went to codex. They landed clean. The Phase 0 wiring I did myself because it felt small. It was not small. One hundred fifty-five lines, four retry iterations, two filter blocks, and the wrong verdict. If I had delegated to codex with a spec-quoted prompt, three things would have been forced. Re-reading the catalog to compose the prompt. The catalog's event-density and seed-window notes appearing in the slot 3 quotation. Either codex flagging the mismatch in Beat 1 or making the mistake transparently in a STATUS the operator could reject. I bypassed the safeguards by doing it myself.

**Tehol:** A wall that is starting to look like a way of working.

**Bugg:** A wall that is starting to look like a way of falling off the way of working. The list is up to ten.

**Tehol:** Ten.

**Bugg:** Four-corner walk before launch. Cheap canary before plan rewrite. Pre-flight the question before pre-flighting the agent. Wait, don't poll. Use the prior investigation's findings to narrow the next investigation. Distinguish laundering from honest determinism at the warning level. Write down deferred concerns at the moment you defer them. Validate output against spec, not mechanism against execution. Spec is the primary input, not the fallback reference. Delegate to the agent the skill was built for; doing it yourself is a self-imposed wound.

**Tehol:** And tomorrow.

**Bugg:** Tomorrow we pick a per-tick continuous process with the 50-seed ensemble already on disk. Two candidates: Metabolism and Transcription. Metabolism uses the legacy single-seed fallback with the new ensemble loader, which means the W1 will be a real number but the distributional gate will be degraded. Transcription has the 50-seed ensemble already. Transcription is the right choice. We compose a codex prompt with the catalog entry quoted verbatim at the top. We let codex wire it. We read the STATUS. We accept or reject. We do not write Python.

**Tehol:** And the eight artifacts.

**Bugg:** The eight artifacts wait for a verdict to ride on. They will earn their place when one exists. Until then they are debt with a future.

**Tehol:** A negative day.

**Bugg:** A negative day. The honest column shows minus four verdicts — we lost the false closure of the five fanout merges and gained one polluted Phase 0. The infrastructure column shows plus eight artifacts. The patterns column shows plus three. The mood column shows the operator using the word "garbage" and being correct.

**Tehol:** And.

**Bugg:** And the path forward is the smallest verifiable step against the spec, then the next one, then the next one. Not infrastructure. Not reverts. Not architecture rewrites. Step against spec, verify against spec, move.

**Tehol:** Already.

**Bugg:** Not yet.

---

*Postscript, for the record. Day 22 evening fanout shipped five merges to main — `6c5706e` d4 MacromolecularComplexation, `dbefb1e` d1 ReplicationInitiation, `1bacd6f` d2 Replication, `d2e4de1` d5 Cytokinesis, `10e2e57` d3 DNARepair — all reverted Day 23 morning at `4657cb6`, `01b1a3d`, `6b005e7`, `3159200`, `24b54eb`. Day 23 main-branch landings, in order: composition mandate v1 promote `470e661`, five reverts above, composition mandate v2 with spec-authority rule `d35bce6`, runner catalog-driven projection support `e3f1178` (five-beat codex on `exec/l22-projection-support`), catalog v2 entries for Replication + DNARepair `a61650d`, plan.md handoff refresh `c775403`, N-seed Karr ensemble loader `4784435` (five-beat codex on `exec/l22-ensemble-loader`), Phase 0 Cytokinesis WID-projection bridge `1f9bce5`. MATLAB extraction at `E:\opencell\.matlab_50seed_extract.log` produced 250 MAT files across `data/m1_sources/karr_native/per_process_traces_v2_s{000..049}/{Replication,ReplicationInitiation,DNARepair,MacromolecularComplexation,Cytokinesis}_100ticks.mat` in 80.1 min wall; 3 of 5 processes have unusable snapshots because the generic extractor's `pick_snapshot_properties` allowlist omits chromosome. L2.2 Green Plan at `docs/phase_f/L2_2_GREEN_PLAN.md` shipped Saturday afternoon — Phase 0-5, STOP/GO gates per phase, estimated 3-4 days to honest L2.2 green. Cross-project mandate v2 at `docs/prompts/COMPOSITION_MANDATE_v2.md` adds the spec-authority rule. Decision logged at `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` under slug `composition-mandate-v1` (composition mandate promotion, anchored to Day-22 fanout drift; v2 adds spec-authority subsequently). Tehol and Bugg are on loan from Steven Erikson's* Malazan Book of the Fallen.*

*Previous: [Day 21/22 — A Process That Replayed the Oracle, A Channel That Counted Twice, and the Substrate Cliff That Was There All Along](2026-06-07-a-process-that-replayed-the-oracle-a-channel-that-counted-twice.md)*
