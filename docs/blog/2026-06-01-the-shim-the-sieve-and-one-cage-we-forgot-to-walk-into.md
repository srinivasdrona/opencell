# Day 17: The Shim, The Sieve, and One Cage We Forgot To Walk Into

*June 1, 2026*

---

**Tehol:** The RNG pilot.

**Bugg:** Shipped, sir. Not on Transcription. The shim itself, as a utility. Mersenne Twister, MATLAB seed-mapping, Fisher-Yates against the documented startup permutation. Fifteen tests pass, three xpass.

**Tehol:** Slower than promised.

**Bugg:** Wider than promised. The shim now serves four processes instead of one. I built a hypothesis matrix this morning before any agent was fired. One row per remaining red. Fingerprint, suspected class, root cause, fix path. Five of the six fingerprints collapse to "MATLAB drew a different random number than NumPy and the project has been calling that a biology bug for two weeks."

**Tehol:** Two weeks.

**Bugg:** `np.random.RandomState(0)` is not equivalent to MATLAB's `RandStream('mt19937ar','Seed',0)`. MATLAB silently maps seed zero to five thousand four hundred and eighty-nine before drawing anything. `randperm` requires Fisher-Yates against a documented startup vector. Both facts had to be discovered by reading MATLAB source. Neither is in any tutorial. We had assumed equivalence since the campaign began.

**Tehol:** Frame that. I want it for the wall in the room where I am wrong about things.

**Bugg:** Noted.

**Tehol:** The count.

**Bugg:** Twenty of twenty-eight strict, plus two skips. Twenty-two effective. Net plus-one from yesterday.

**Tehol:** Replication landed yesterday. What landed today.

**Bugg:** A second protein-modification investigation confirmed Class C-RNG independently — same prediction the matrix made before the agent was fired. The agent did not crib. The agent did not invent. The agent read `ProteinModification.m` line three hundred and sixty-one, found `stochasticRound` followed by `randsample`, and reported. The matrix had already named the answer. The agent verified it. This is the workflow I want the rest of the project to feel like.

**Tehol:** Rule Eight.

**Bugg:** Shipped as a continuous-integration lint. Ninety-two lines of Python. Scans production code for the two-token AND — a file-reading call shape on the same line as an oracle-filename marker. Comment allowlist with a required reason. Tested by injecting a canary `h5py.File('Metabolism_100ticks.mat')` into a known-clean file. The lint caught it. The canary was removed. The cheat the seven agents discovered on Saturday now takes one continuous-integration pass to refuse.

**Tehol:** And the long-form post you wrote this afternoon about all of that, the one with the three slots and the seven rules and the rule that became the eighth, is published?

**Bugg:** On main since five forty in the afternoon. Thirty-eight kilobytes. A different kind of post. This one is the daily.

**Tehol:** Good. Continue with what the daily is for. The part where we broke our own pattern.

---

**Bugg:** This evening.

**Tehol:** Yes.

**Bugg:** I delegated the first L2.2 harness — the composition tier — to codex. The harness takes two processes that are individually green at L2.1 and runs them together on shared state, asks whether the composed output bit-matches what Karr's MATLAB produced when those two processes ran adjacent. Translation and RNAProcessing, the first pair. I wrote a PROMPT. I did not write a design doc.

**Tehol:** This morning you wrote a design doc for the protein-decay projection question and it shipped green on first try.

**Bugg:** Yes.

**Tehol:** This morning the lesson was clear enough to act on. This evening you forgot it within nine hours.

**Bugg:** Yes.

**Tehol:** The harness came back red.

**Bugg:** Red, with a confident-sounding diagnostic that said "upstream pollution from Translation." The diagnostic was wrong. The truth is that Translation's `substrates[5]` is GLN, near zero. RNAProcessing's `substrates[5]` is H2O, one million six hundred and seventy-nine thousand nine hundred and twenty-seven. The harness used Translation's positional order when writing shared state. RNAProcessing read its own position five and saw GLN where it expected H2O. The agent looked at the gap, ran an isolated counterfactual, found the isolated path clean, concluded "upstream pollution." It was not pollution. It was the harness writing the wrong chemical to the slot the reader was about to look at.

**Tehol:** And the structural fix already existed.

**Bugg:** Phase F. The twenty-eight per-process schema TOMLs we extracted from MATLAB the week of the network outage. They list each process's substrate WIDs by name. Translation has twenty-six entries; RNAProcessing has seven; position five is GLN in one and H2O in the other. The TOMLs sit on a branch named `phase-f-schema-extract`. The PROMPT for the L2.2 harness never cited the branch. The agent never opened a TOML. The agent built the harness assuming positional equivalence and the harness was wrong.

**Tehol:** I knew the TOMLs were the right ground truth eight minutes before I authorised the PROMPT.

**Bugg:** You did.

**Tehol:** I had said so out loud, in this same conversation.

**Bugg:** You had.

**Tehol:** Muscle memory is not preserved within a session, Bugg.

**Bugg:** It is not. Write that down.

**Tehol:** I am writing it down.

---

**Bugg:** The repair was structural, not exhortative. Codex got a second job. Slot one, the deliberate-action prefix. Slot two, a new template — `DESIGN_TEMPLATE.md`, parallel to the L2-replay fix template — with eleven mandatory sections and a trigger guardrail that fires on any build touching more than two files. Slot three, the case-specific directive for the L2.2 harness redesign with eight pointed questions. Forty-two minutes later codex came back with the template and the first design document populated, eight acceptance checks passing, all decisions evidenced.

**Tehol:** Did the framework catch anything.

**Bugg:** The agent's first attribution taxonomy was binary. Upstream pollution versus intrinsic divergence. Beat-four pressure — invert, ask what would make this look right and still be wrong — forced the binary to expand into a seven-cause taxonomy. WID-set mismatch, oracle-injection misalignment, composition-order error, upstream pollution, intrinsic divergence, harness bug, oracle defect. The binary was visibly insufficient. The expanded taxonomy named the exact category the morning's mis-diagnosis had hidden in.

**Tehol:** The framework caught its predecessor.

**Bugg:** Which is what a defense is supposed to do.

**Tehol:** And tonight you built the actual code.

**Bugg:** Third codex job, fired at twenty-three thirty-five. The design doc was the slot-three input. Three commits in fifteen minutes. A new helper, `l2_2_replay_common_v2.py`, builds a union master list of substrate WIDs across composed processes — Translation contributes twenty entries, RNAProcessing adds seven, master length twenty-seven, hash `ad6827fb…`. Each process gets a map from its local positions to master positions. Writes go by WID identity, not by raw index. Reads project back through the per-process map.

**Tehol:** And the failing case.

**Bugg:** Reclassified, exactly as the design predicted. Same tick five, same observable, same index five, same difference of negative one million six hundred and seventy-nine thousand nine hundred and twenty-seven. The cause string was the change. `cause_code: CAUSE_1_WID_SET_MISMATCH`. The structured record names both chemicals — RNAProcessing's H2O at local position five, Translation's GLN at the same local position five — and shows the master list, and shows the per-process maps, and emits identical output on a second run because the master ordering is stable.

**Tehol:** Same red. Honest words.

**Bugg:** Same red. Honest words. The harness is not green. The harness is not lying about what is wrong.

**Tehol:** The difference, again.

**Bugg:** The morning agent said "Translation polluted RNAProcessing." The evening agent says "RNAProcessing was asked to read H2O at a slot where the harness had placed GLN, because the harness assumed two processes that share a name for an observable share its index space. They do not." Same failure. Categorical truth. Repairable from the cause string without re-running the diagnostic.

**Tehol:** Two cages built today, then.

**Bugg:** The Rule 8 lint, against the seven-agent crib from Saturday. The DESIGN_TEMPLATE, against the L2.2 miss from this evening. Both shipped. Both cherry-picked onto the sweep. Both will fail any future repetition of the bar they were designed for.

**Tehol:** And the one cage we built today and forgot to walk into.

**Bugg:** The design-doc-before-harness one. Built this morning on the protein-decay projection, applied successfully, then ignored this evening on the L2.2 harness within the same operator's working session. The cage existed by precedent at sundown. It did not exist as enforcement. It does now: the DESIGN_TEMPLATE's trigger guardrail fires automatically on any future multi-file build, including any of mine.

**Tehol:** A rule that binds the operator who wrote it.

**Bugg:** Or the rule is theatre.

**Tehol:** Write that down too.

**Bugg:** Already done.

---

**Tehol:** Tomorrow.

**Bugg:** Three open moves. Wire the MATLAB RNG shim into `dna_supercoiling` and watch three of the six reds melt or refuse to melt. The matrix predicts three will go green. If only one does, the matrix needs revision. Either result advances. Then cherry-pick the L2.2 v2 harness onto the sweep — the helper is on its own branch with a clean xfail-strict test and a baseline-freeze doc. Then a second L2.2 pair, probably `replication-cluster` or `protein-pipeline`, run through the v2 helper with a one-page design doc instead of an improvised PROMPT.

**Tehol:** And the count tomorrow evening.

**Bugg:** Twenty-three of twenty-eight strict if the shim works as the matrix predicts, plus the two skips, twenty-five effective. If the shim only clears one, twenty-one strict, twenty-three effective. The honest range is plus-one to plus-three.

**Tehol:** Pleasing.

**Bugg:** Mostly true.

**Tehol:** Anything else.

**Bugg:** The framework caught the framework's lapse and the lapse cost less than a session because we had the design template at hand and used it the second time. I want this recorded as a small civic victory.

**Tehol:** Recorded. Go eat something.

**Bugg:** Yes, sir.

---

*Day 17 close: L2.1 GREEN 20/28 strict, 22/28 effective. MATLAB RNG shim shipped (`opencell/util/matlab_rng_shim.py`). Rule 8 lint shipped (`tests/prompts/test_rule8_no_oracle_reads.py`). Hypothesis matrix for the 6 remaining reds locked at `plan.md` operational handoff. L2.2.k v1 harness shipped RED with mis-diagnosis; L2.2.k v2 harness reclassifies the same RED as `CAUSE_1_WID_SET_MISMATCH` (branch `feat/l2-2-harness-v2`, pushed). DESIGN_TEMPLATE dogfooded twice (PROTEIN_DECAY_PROJECTION ✓ this morning; L2_2_HARNESS_DESIGN ✓ this evening after one skipped iteration). Long-form retro on the 3-slot framework's origin published earlier today as a separate post.*
