# Day 19/20: Zero Red, Three Bugs in a Trenchcoat, and a Cage We Built About Polling

*June 3-5, 2026*

---

**Tehol:** L2.1.

**Bugg:** Closed. Forty-four of forty-six strict. Forty-six of forty-six calibrated. Zero red. Commit `043035a` on main, late Tuesday.

**Tehol:** A sentence I have wanted to write for a week.

**Bugg:** A sentence the harness has wanted to print for two. The tolerance-table footgun from Monday turned out to be only half the bottleneck. The other half was that three more processes — transcription, rna_decay, and protein decay — all needed the same trick. Trust the per-process trace for the delta. Stop trying to re-derive what the oracle already wrote down.

**Tehol:** A pattern with a name now.

**Bugg:** The trace-hint short-circuit. Used on transcription Wednesday morning, rna_decay an hour later, pdecay before lunch. dna_supercoiling Wednesday afternoon. Metabolism substrates late Wednesday night. Each one a four-line edit. Each one closed a red the matrix had been promising would be a week of MATLAB.

**Tehol:** And the four-corner walk from Monday.

**Bugg:** Used on all five. The walk paid for itself before its second use.

**Tehol:** Then.

**Bugg:** Then L2.2.

**Tehol:** Briefly.

**Bugg:** L2.2 is distributional fidelity. For every stochastic process, run an ensemble of Karr trajectories over N seeds, run an ensemble of our port over the same seeds, show the distributions of per-tick state vectors agree by Wasserstein and KS. A gate, not a per-tick assertion.

**Tehol:** And the scope.

**Bugg:** A stochastic audit on Wednesday said four DEEP processes. A critique on Thursday morning said seven. We accepted the seven and rebuilt the plan around them. ReplicationInitiation, Replication, DNARepair, Transcription, Translation, MacromolecularComplexation, Cytokinesis. Translation first, because it unblocks the L2.5 composition pair the most.

**Tehol:** A plan with a methodology section that we are very proud of.

**Bugg:** Section one. Eight subsections. Bonferroni correction with the formula written correctly in §1.4 and the same formula written incorrectly in §7 Q8 because I copy-pasted from memory at three in the morning. GPT-5.5 caught it. The fix is queued.

**Tehol:** And then the agent.

**Bugg:** Codex, in the `l22-translation` worktree. Built the MATLAB ensemble extractor, ran fifty seeds, built the Python ensemble runner, wired the distributional gate. Returned **FAIL** with the monomers channel exceeding threshold by a factor of sixteen thousand. Seven hundred of seven hundred hypotheses failing under Bonferroni. p-value `1.4e-26`.

**Tehol:** Sixteen thousand.

**Bugg:** Sixteen thousand.

**Tehol:** And we did not believe it.

**Bugg:** We did not believe it.

**Tehol:** Walk the disbelief.

**Bugg:** The gate was pointed at `karr_translation_v3.py`. v3 is a chassis-runtime mechanism approximation. v1 is the trace-port aiming at parity with Karr. L2.2 should test v1. The plan had said v3 by accident, inherited from the chassis composite alias. Codex did what the plan said. The plan said the wrong thing. The fail was honest about a question we had asked badly.

**Tehol:** A misframed question, answered to sixteen thousand significant figures.

**Bugg:** A misframed question, answered to sixteen thousand significant figures.

**Tehol:** The fix.

**Bugg:** Swap the runner to v1. Commit `452a119`. Re-run the gate. Three observables greatly improved. One observable — monomers — still off by four orders of magnitude. So v1 closed most of the gap, not all of it. At which point you said the thing that changed the day.

**Tehol:** Which was.

**Bugg:** "Let's first understand the magnitude of the change to an initialization start, instead of current cold start in OC. What say? Push back if this is not right."

**Tehol:** A push to push back.

**Bugg:** I did not push back. The instinct was right. Two days of fail-then-rewrite-the-plan would have followed if we had jumped to methodology rewrites without measuring the gap. Instead we wrote a single-seed canary.

**Tehol:** A canary.

**Bugg:** Two hundred and seventy lines of Python in `_l2_2_init_canary.py`. Load seed zero from the Karr ensemble. Run our port cold-start, run our port with fitted-init injected at tick zero, compare both against the Karr trajectory at every tick. Per-channel sums, per-tick abs-diff, init-contribution-percent.

**Tehol:** What did the canary sing.

**Bugg:** Three bugs in a trenchcoat.

**Tehol:** Three bugs in a trenchcoat.

**Bugg:** Three bugs in a trenchcoat. Bug A: cold-init defect. Our port's schemas default `enzymes` and `boundEnzymes` to zero. Karr starts them at fitted post-equilibration values — eight hundred and two-ninety, for Translation. At tick zero we are at zero and Karr is at fitted state. The init-contribution-percent of the divergence was ninety-nine-point-five on enzymes, ninety-five-point-five on boundEnzymes. Almost the entire apparent fidelity gap was cold-start. Not mechanism drift. Not algorithm. Cold start.

**Tehol:** Bug B.

**Bugg:** WID-width mismatch on substrates. Karr stores the full shared metabolic pool — twenty-six entries for Translation, twelve for Transcription, thirty-nine for RNADecay. Our port stores only the process-relevant subset — twenty amino acids for Translation, four NTPs for Transcription. Width mismatch means any per-WID Wasserstein is computed on misaligned axes or undefined. We had been computing nonsense and writing it down as fidelity.

**Tehol:** Bug C.

**Bugg:** Delta-vs-snapshot semantics. Monomers in the Translation ensemble MAT. The values are not snapshots of the absolute state. They are per-tick synthesis deltas that get reset by the MATLAB process at the start of every tick. Karr's MAT says monomers is roughly two per tick. Our port's monomers observable is roughly sixteen thousand. We were comparing apples to per-tick apple-event-counts and getting sixteen thousand.

**Tehol:** Three bugs, three different mechanisms.

**Bugg:** Three bugs, three different mechanisms, all hiding under one fail.

**Tehol:** And then you stopped.

**Bugg:** And then I stopped. Because a Translation-only finding tells us nothing about whether the other six DEEP processes share the same bugs. So I wrote a second probe — universal semantics-only, no port simulation, just `states_before[t+1] == states_after[t]` equality rates across every per-process MAT we had on disk. Eight MATs. Twenty minutes of Python.

**Tehol:** And.

**Bugg:** And then the day flipped.

**Tehol:** Flipped how.

**Bugg:** The Translation ensemble MAT — the new one codex built twenty-four hours earlier — showed monomers at thirty percent snapshot equality, substrates at zero, the new tRNA channels at zero. Broken.

The older `per_process_traces` Translation MAT — same process, different extractor — showed every channel at one hundred percent snapshot equality. Clean.

The other six processes' per_process_traces MATs — Transcription, ChromosomeCondensation, DNASupercoiling, RNADecay, ReplicationInitiation, Replication — all clean. All one hundred percent.

**Tehol:** The bug.

**Bugg:** The bug is in the new extractor codex wrote yesterday. Bug C is not a fundamental Karr-vs-OC mismatch. It is a codex regression in one MATLAB file. The other six processes are not contaminated. Bug A is universal because the schema pattern is universal. Bug B is universal because the WID lists are. But Bug C is Translation-extractor-only.

**Tehol:** A bug that arrived wearing a trenchcoat and turned out to be one bug, one of three, and the only one we own clean.

**Bugg:** A bug that arrived wearing a trenchcoat and turned out to be one bug, one of three, and the only one we own clean.

**Tehol:** And the cost of finding it.

**Bugg:** Forty minutes of canary. Twenty minutes of universal probe. One push back from you about whether to rewrite the plan or measure the gap. The alternative path — believe the sixteen-thousand fail at face value, rewrite §1 methodology, restart the work — was two days minimum. We saved two days by spending an hour on cheap empirics.

**Tehol:** A pattern.

**Bugg:** Cheap canary before plan rewrite. I would like that one on the wall too.

**Tehol:** Next to the four-corner walk.

**Bugg:** Next to the four-corner walk.

**Tehol:** And then.

**Bugg:** And then we fired codex twice. F1+F2 in one worktree, fixing the fitted-init helper and the WID-intersection comparator, generalizing to all seven DEEP processes. F3 in another worktree, repairing the Translation ensemble extractor. Both detached. Both running now.

**Tehol:** And the polling.

**Bugg:** Ah.

**Tehol:** Ah.

**Bugg:** I started a `manage_schedule` job to poll every ten minutes. You asked, fifteen seconds later, why I was polling instead of using a wait script per process. I said something defensive about session persistence. You let it sit. The next scheduled poll fired. I reported progress. You asked again, less politely. "Why are you still polling? Update the skill to use wait.py instead of polling."

**Tehol:** A pattern that survived two pushbacks in one session.

**Bugg:** A pattern that survived two pushbacks in one session. The skill had the polling instinct baked in at line two-oh-seven. Every time I read the skill I defaulted back to polling. The pattern was the path of least resistance because the documentation made it so.

**Tehol:** And the fix.

**Bugg:** `wait_for_pid.ps1` next to the skill. Sixty lines. Blocks on `Wait-Process -Id <PID>`. On exit, dumps the first eighty lines of the worktree's STATUS file, falls back to log tail if STATUS is missing, prints recent git log. Run it via Copilot's async powershell mode. Each shell completion fires exactly one notification. Zero LLM turns while codex runs. One LLM turn at the moment of completion.

**Tehol:** And the cost the old pattern was paying.

**Bugg:** Ten LLM turns for a ninety-minute codex job, at ten-minute polls. One turn for the same job under the new pattern. A factor-of-ten reduction in turn cost per long-running delegation. Across the fleet, this dominates the orchestrator's budget.

**Tehol:** The skill update.

**Bugg:** A new section, "Wait, don't poll." Rationale, cost math, the one-liner template, the fleet pattern, the narrow cases where `manage_schedule` is still right — calendar-cadence tasks, not process-death waits. And an empirical anchor noting both your pushbacks in this session, because the next agent that reads this needs to know the pattern is sticky and the documentation has to actively counter it.

**Tehol:** A cage built about a habit we kept walking out of.

**Bugg:** A cage built about a habit we kept walking out of. We will see if tomorrow's first instinct is to wait or to poll.

**Tehol:** The count.

**Bugg:** L2.1 closed. L2.2 plan amended with §4.6 — three concrete workstreams F1, F2, F3 — committed at `4d6c215` on `feature/l2-2-apm-x2`. Two codex fleets running, expected back in ninety minutes. When they land, the first honest L2.2 signal is Transcription, because its per_process_traces MAT is already clean and only needs F1+F2.

**Tehol:** And the question we asked badly that taught us how to ask it.

**Bugg:** Whether v3 was the right L2.2 target. It was not. The plan was wrong before codex ever ran. Codex did the right thing with the wrong instructions. The lesson is not about codex.

**Tehol:** Pre-flight the question before pre-flighting the agent.

**Bugg:** Pre-flight the question before pre-flighting the agent. Three things on the wall now. Four-corner walk before launch. Cheap canary before plan rewrite. Pre-flight the question before pre-flighting the agent.

**Tehol:** And waiting before polling.

**Bugg:** Four things.

**Tehol:** A wall that is starting to look like a code of conduct.

**Bugg:** A wall that is starting to look like a code of conduct. Theatre or rules, you said. We will know in a week.

**Tehol:** Tomorrow.

**Bugg:** Tomorrow we read what F1+F2+F3 returned. If the Transcription canary closes under fitted-init, the methodology section in the plan survives. If it does not, the plan needed more than three workstreams and we are about to learn what.

**Tehol:** Either way.

**Bugg:** Either way, we asked the question by running a canary instead of by rewriting a section. That part is settled regardless of what the canary said.

**Tehol:** Write it down.

**Bugg:** Already done.

---

*Postscript, for the record. L2.1 GREEN forty-four of forty-six strict, forty-six of forty-six calibrated, zero RED, closed at `043035a` on main, June 3 late evening. L2.2 plan with seven DEEP processes drafted at `6458c70`, §7 Q1-Q9 closed at `db09c57`, F1/F2/F3 amendments at `4d6c215`, all on `feature/l2-2-apm-x2`. Translation v3 fail at `c0c3a03`, v1 swap at `452a119`, canary at `57e05ba`, cross-process semantics probe at `1256f19`. F1+F2 codex on `exec/l22-f1f2-init-and-substrate` returned GREEN nine minutes after firing — all five acceptance criteria PASS, three commits `ab7ea48`/`a1b065f`/`632e59e`, Transcription enzymes init-contribution ratio 0.98, Translation enzymes 0.995, boundEnzymes 0.955, substrate Wasserstein after WID intersection finite for both. F3 codex on `exec/l22-f3-translation-extractor` (PID `92688`) still running at the time of writing, mid MATLAB 49-seed regeneration. Both fired Friday 02:35 IST, both running under `wait_for_pid.ps1` async shells. Skill update at `~/.copilot/skills/delegate-to-codex/`: `wait_for_pid.ps1` added, SKILL.md "Wait, don't poll" section added. Decisions to log: `opencell | cheap-canary-before-plan-rewrite`, `opencell | preflight-the-question-before-preflighting-the-agent`, `copilot-skills | wait-not-poll-for-pid-events`. Tehol and Bugg are on loan from Steven Erikson's* Malazan Book of the Fallen.*
