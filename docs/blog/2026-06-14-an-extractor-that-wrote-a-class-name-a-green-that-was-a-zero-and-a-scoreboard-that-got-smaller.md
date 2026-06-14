# Days 26-28: An Extractor That Wrote a Class Name, A Green That Was a Zero, and a Scoreboard That Got Smaller

*June 12-14, 2026*

---

**Tehol:** Where are we.

**Bugg:** Fourteen honest greens on a board that holds twenty. Eight of those greens are real biology. Six are convergence — the W1 equals zero variety, not a regression-free certificate. One green dropped off the board today because the audit found it was a zero-event paper-pass. One process that we thought needed wiring turned out to need a different harness entirely. The chromosome state was a placeholder string for twenty-two days and nobody noticed.

**Tehol:** Net.

**Bugg:** Net plus four from the Day-25 scoreboard. Plus a foundational MATLAB fix that unblocks a Phase-C-v2 effort nobody had scheduled. Plus a catalog correction that retired one false green. The trajectory is positive on artifacts and negative on certainty. Both are correct.

**Tehol:** Walk it.

**Bugg:** Friday after the Day-25 post. Three branches held back from main. Batch A complete but launderer-flagged. Batch C dead at Beat 1. ProteinDecay extractor's ndim=1 bug still open. Operator wrote Day-25's post and slept.

**Tehol:** Saturday.

**Bugg:** Saturday morning the laundering investigation finally fired clean. Single hypothesis — H11 — three files in the read-set, "write probe.py that asserts X" as the artifact. Operator-rewritten salvage prompt format. Codex ruled H11 out in four commits. The parallel branch in `next_update` was not the laundering path. The probe results were unambiguous.

**Tehol:** And.

**Bugg:** And then a code-reading session found `_closed_form_bounds` on MacromolecularComplexation returns a deterministic upper bound that, when substrate is non-limiting, equals the answer Karr's stochastic `_per_cluster_mc` would have produced. Bit-identity is mathematically guaranteed at the substrate-non-limiting limit. The detector was correctly flagging W1=0 as suspicious — what was wrong was the interpretation. This is convergence at a bounded limit, not laundering.

**Tehol:** H12.

**Bugg:** H12. Probe at `.probe_h12.py` confirmed 50 of 50 sample cells match including 7 of 7 nontrivial. Real algorithmic convergence. Catalog v4 added a new field — `closed_form_dominant: confirmed | candidate | false` — and the runner was patched to demote `PRIMARY_CHANNEL_ORACLE_LAUNDERING` to informational `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` when the catalog says confirmed. Commit `a462b71`. Then `cc2b207` promoted the four other suspects — PPI, PPII, tRNAAA, ProteinFolding — to confirmed based on the same H12 signal pattern visible in their existing smoke artifacts.

**Tehol:** Decisions.

**Bugg:** Four decisions logged to the cross-project file. `runner-level-laundering-detector-as-safety-net` for opencell. Three more cross-cutting from the 3-slot architecture work that piggybacked on the session.

**Tehol:** Sunday.

**Bugg:** Sunday produced merges. Batch A rebased onto main, smoked, PPI and PPII land via convergence. Plus two honest greens. Then ProteinDecay's ndim=1 extractor bug got fixed in a 30-minute hand-edit — `_project_protein_decay_monomer_cube` needed to reshape (n_ticks, 28920) into (n_ticks, 6, 4820) for the per-tick compartment cube before projection. Commit `0d64836`. Re-enabled four previously-deselected anti-cheat tests. Smoke verdict PASS, W1 of zero point zero zero zero five five. Real biology. Plus one. Eleven greens.

**Tehol:** Sunday afternoon.

**Bugg:** Sunday afternoon, three concurrent codex sessions — wire-metabolism, fix-ptransloc, fix-pmod. The two-concurrent cap from Day 25 said this was risky. The operator fired three anyway. wire-metabolism completed Beats 1-4 — and unexpectedly removed an existing `overlay_trace_after_hint` laundering path that had been masking a shape bug on Beat 5. Beat 5 then errored on a compartment-shape mismatch (1755 vs 585). The laundering had been hiding the bug. fix-ptransloc completed five beats with the H12 signature on smoke. fix-pmod died at 64k tokens with zero commits. Third consecutive Azure throttle on that specific prompt.

**Tehol:** Decomposition.

**Bugg:** The combined fix prompt was the problem. Splitting fix-pmod into two narrower per-bug prompts got fix-ptransloc across the finish line. fix-pmod still died once at 116k on the second attempt before the third pass landed Beats 2-5 cleanly with the projection algorithm pre-specified by the operator in slot 3.

**Tehol:** Monday morning.

**Bugg:** Monday morning — Day 28 — promoted PTransloc to confirmed in the catalog, cherry-picked the fix-ptransloc beats onto main, hand-added five missing wiring surfaces (factory, dispatch, format adapter, observable_wids, sample_state). Plus one green via convergence. Then the full Batch C merge — `-X theirs` strategy, conflicts in helpers across four branches, surgical re-apply of the ProteinDecay ndim=1 fix and the PPI/PPII factories that the merge had reverted. Plus three greens — ProteinFolding via convergence, ProteinModification real biology W1 of zero point zero zero two four, RibosomeAssembly sparse legitimate-determinism. Fourteen honest greens at end of Monday morning.

**Tehol:** Metabolism.

**Bugg:** Operator said "delegate to codex instead of fixing by hand." Fired a narrow Metabolism Beat-5 prompt with the solved PTransloc and ProteinDecay patterns referenced. Codex found Metabolism uses `_CYTOSOL_COMPARTMENT_0` — the projection was cytosol-select, not sum-over-compartments. Shipped `f5f6aee`. Re-smoked against the real v2 ensemble. Honest FAIL — W1 of nine point seven six against a threshold of seven point three three, n_nonzero gap of seventeen thousand versus forty-six thousand. Not laundering. Not deterministic convergence. Real distributional divergence.

**Tehol:** Fourteen plus one honest result.

**Bugg:** Fourteen honest greens plus one honest FAIL. First honest fail on the board in two weeks. The board has been all-pass or no-information. An honest fail is a step forward.

**Tehol:** Then.

**Bugg:** Then Kimi K2.6. Operator asked for a sibling skill to `delegate-to-codex` that swaps the model. Same Azure backend, just `--model kimi-k2.6` on the codex CLI. Test invocation verified working. Wrote the thin skill — eight kilobytes, references `delegate-to-codex/SKILL.md` for the agent loop and only documents what is different. Bumped the codex SKILL.md frontmatter to cross-link the sibling.

**Tehol:** Replication.

**Bugg:** Fired Replication re-wire on codex in parallel with the Kimi setup. Codex died at two hundred thirty-three thousand tokens with only Beat 1 committed. Beat 1's STATUS file said the v2 ensemble's Replication oracle does not contain a chromosome snapshot — only `boundEnzymes`, `enzymes`, `substrates` are in `states_before/after`. Said the chromosome-primary projection required by the catalog must be synthesized from substrate trace deltas. Said `apply_count_update` does not apply chromosome updates so an explicit step would be needed on the test-helper side. Codex was correct that data was missing. Codex was wrong about why.

**Tehol:** Why.

**Bugg:** Operator's first instinct was to re-extract Replication plus ReplicationInitiation plus DNARepair — three files per seed times fifty seeds equals one hundred fifty MAT files — with the chromosome allowlist already in place. Killed the smoke. Built the launcher. Started the MATLAB. Twenty-five minutes in, while the wrapper was running, a Python probe on one of the freshly-produced files showed the chromosome field was present and was a 54x1 uint16 array of ASCII values that decoded to `'<object:edu.stanford.covert.cell.sim.state.Chromosome>'`.

**Tehol:** A string.

**Bugg:** A string. The extractor's `sanitize_snapshot_value` has a generic `if isobject(v)` branch that returns `sprintf('<object:%s>', class(v))` for any MATLAB object not explicitly handled. The Chromosome state object had been hitting that branch silently since the original v2 extractor shipped. The Day-22 bug-2 commit `b3df570` had added `'chromosome'` to the allowlist. That allowed the property to be requested. The serializer then walked it, saw an object, and wrote the class name as a string. The MAT file looked fine. The h5py loader returned the bytes. Downstream code that compared the bytes against anything failed loudly only when the downstream consumer expected numbers — which had not happened for twenty-two days, because the only chromosome-primary process that had been wired was Replication on Day 28, and Replication had died at Beat 1 reading those exact bytes.

**Tehol:** Twenty-two days.

**Bugg:** Twenty-two days of trace files claiming to contain chromosome data and actually containing the ASCII bytes of the class name. Every audit that ran during that window saw `chromosome` as a key in the h5 file and moved on. The first audit that opened the bytes and asked what they were was today. Killed the MATLAB. Stopped the operator-instinct re-extract.

**Tehol:** Audit.

**Bugg:** Wrote a Python probe that walks every process in seed-zero, every channel, every tick, decodes any uint16 array as ASCII, checks for `<object:` or `<unsupp` or `<MAX` prefixes. The audit returned exactly five hits — chromosome in all five chromosome-primary processes — and zero hits anywhere else. The bug was contained. The fix had a clear shape — special-case the Chromosome class in `sanitize_snapshot_value` before falling through to the placeholder branch.

**Tehol:** The serializer.

**Bugg:** Written by hand. `serialize_chromosome_state.m`. Walks the eleven Chromosome state properties — `polymerizedRegions`, `linkingNumbers`, `monomerBoundSites`, `complexBoundSites`, `gapSites`, `abasicSites`, `damagedSugarPhosphates`, `damagedBases`, `intrastrandCrossLinks`, `strandBreaks`, `hollidayJunctions` — and writes each as a sparse triple of `{positions, strands, values, shape}` via the SparseMat `find` method. Smoke on one seed, ten ticks, DNASupercoiling. linkingNumbers carries real per-tick deltas. polymerizedRegions shows strand 2 advancing from position 334 at tick 5 to position 834 at tick 9. Five hundred base pairs per four ticks. Karr's documented replication speed. The fix was correct. Commit `0ff0bb5`.

**Tehol:** Re-extract.

**Bugg:** Two hours wall. Five processes, fifty seeds. The script's first version deleted existing files before running so the regenerate guard wouldn't short-circuit. That was correct for the first run. On the second restart — the codex chrom-projections design delegation collided with MATLAB's single-instance trial license at minute twenty-five and killed both — the destructive delete ran again and threw away the hundred-one files already done. Operator patched the script to be restart-safe and re-fired. Two more hours wall. All two hundred fifty files landed clean. One file — s000 ReplicationInitiation — was corrupted by the collision; regenerated separately in fifteen minutes.

**Tehol:** While that ran.

**Bugg:** While that ran, the operator fired three jobs in parallel. Kimi K2.6 on the Metabolism FAIL investigation — single hypothesis, cytosol-select projection wrong, switch to sum-over-compartments. Codex on the chromosome projection design — four processes, primary_projection plus primary_distance per the catalog schema. Operator on the three housekeeping items.

**Tehol:** Outcomes.

**Bugg:** Kimi died at one hundred five thousand tokens with zero commits — Azure peak-demand throttle, IST mid-afternoon, distinct from the published token cap. Codex died self-inflicted — got stuck in a PowerShell quoting loop trying to invoke a one-liner Python, then tried to fire its own MATLAB invocation against the trial license. Operator killed it before further damage. Two of three jobs zero commits zero STATUS. The third — the housekeeping — landed plan refresh, GOTCHAS entry for the chromosome placeholder, todos sync.

**Tehol:** Recovery.

**Bugg:** Operator wrote the chromosome projections design by hand. Four processes — DNASupercoiling, DNADamage, Replication, DNARepair — got `primary_projection` and `primary_distance` entries. DS got `linkingNumbers.delta_value_sum` plus `linkingNumbers.delta_nnz` with per-component-scaled distance. DD got an eight-component per-damage-field hurdle. Replication's prior projection was synthesized from substrate deltas — replaced with `polymerizedRegions.delta_value_sum_strand_{1..4}` plus `polymerizedRegions.delta_nnz`. DNARepair's prior pathway-count projection was replaced with five direct chromosome-state delta components. Catalog v1.4. Merged `c5d5adb`.

**Tehol:** Then.

**Bugg:** Re-fired the Metabolism investigation on codex with an explicit "DO NOT INVOKE MATLAB" rule. Codex shipped four beats clean. Case A verdict — sum-projection PASS at W1 of one hundred sixty-eight against a threshold of two hundred twenty-two, no warnings. The n_nonzero gap closed — ninety-three thousand on OC versus one hundred nineteen thousand on Karr versus the prior seventeen versus forty-six. Real biology. The fifteenth honest green. Merged `85b1712`.

**Tehol:** And the chromosome wirings.

**Bugg:** And the chromosome wirings were the next move. Before authoring the four delegations, operator spot-checked one of the four — DNASupercoiling — for OC-side surface compatibility. The Karr oracle now has a sparse matrix `linkingNumbers[580076 x 4]` per tick. OC's port — `karr_dna_supercoiling.py` — tracks a scalar `chromosome.supercoil_density` in the range minus zero point two to zero point two. One number per tick. The module's docstring at line 1-12 documents the deferral explicitly. Full region-resolved linking-number mechanics. Explicit enzyme binding and processivity. Fork-collision knockoff dynamics. TopoI branch. Supercoiling-driven transcription fold-change outputs. All five are deferred to pc-t7 slash v2.

**Tehol:** OC was always Karr-light.

**Bugg:** OC was always Karr-light on chromosome processes. The serializer fix and the catalog projection design were the correct work for the Karr side. They are infrastructure for the pc-t7 effort that nobody has scheduled. Today's work is reusable. Today's plan to immediately wire DS and DD to L2.2 is not.

**Tehol:** The other three.

**Bugg:** Same shape, less severe. Replication — OC tracks two scalars `chromosome.fork_position_bp.{left, right}`. Karr has polymerizedRegions[580076 x 4]. Aggregable. ReplicationInitiation — OC surface unverified. DNARepair — OC tracks per-pathway counts BER, NER, HR, NHEJ-like. Better fit. The original DNARepair projection that we replaced this afternoon was actually correct for OC's surface. We replaced a correct design with a pc-t7-target design.

**Tehol:** Reversion.

**Bugg:** Not yet. The pc-t7-target entries can stay; we add a note saying the OC-surface projection is what current L2.2 must use until pc-t7 lands. Or we revert and lose the design work. Operator chose neither path tonight — both options stay open.

**Tehol:** Then the audit.

**Bugg:** Then operator asked the question that ate the scoreboard. The fourteen honest greens — what fraction of them actually test distributional fidelity. Three categories.

**Tehol:** Walk them.

**Bugg:** One. Real biology greens. Both sides stochastic, distributions visibly different but within tolerance. Eight processes — Transcription, Translation, RNADecay, RNAProcessing, RNAModification, ProteinDecay, ProteinModification, Metabolism. Forty percent of in-scope. Two. Convergence greens — six processes. tRNAAA, MacromolecularComplexation, ProteinFolding, ProteinTranslocation, ProteinProcessingI, ProteinProcessingII. W1 of zero point zero because OC's closed-form bound equals Karr's stochastic answer in the substrate-non-limiting regime. The bound dominates by design. The convergence is mathematical not biological. Thirty percent. Three. RibosomeAssembly. The fourteenth green.

**Tehol:** And.

**Bugg:** And RibosomeAssembly produced verdict PASS with two flags. `PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE` on the primary channel. `INSUFFICIENT_SAMPLES` on the primary channel. n_nonzero on OC zero. n_nonzero on Karr zero. samples_max zero. The smoke captured ten ticks across fifty seeds and no assembly events fired on either side. Both sides agreeing on nothing happened. The W1 is zero because the surface is zero. A test with no questions on it.

**Tehol:** Familiar.

**Bugg:** Familiar. Cytokinesis and FtsZPolymerization were both reclassified to EVENT_CLASS on Day 23 for exactly this signature. Sparse event-density. Bursty in a window the test sample does not cover. Both processes carry a `seed_window` constraint that says when in the cell cycle the event is active. RibosomeAssembly does not carry the seed_window — but it is `event_density: sparse` and the catalog's own notes say `L2.1 currently SKIP for no-op trace`. The reclassification trigger was the smoke-result pattern. RibosomeAssembly hit the pattern on Day 28 morning. Nobody had noticed.

**Tehol:** Audit.

**Bugg:** Wrote a sweep that asked the right question. For every in-scope L2.2 process in the v2 ensemble, count the fraction of seeds where states_before equals states_after for every captured tick. Four processes returned zero events. ReplicationInitiation 100 percent had events, DNARepair 98 percent, Replication 100 percent — the chromosome-primary ones we have not wired yet. Two returned zero across all fifty seeds. RibosomeAssembly. DNADamage. Both are `event_density: sparse`. Both would produce or were producing fake PASS W1 of zero.

**Tehol:** Reclassify.

**Bugg:** Reclassified both. Catalog v3.1, commit `d184ffc`. RibosomeAssembly out of ALGORITHMIC_SHALLOW into EVENT_CLASS. DNADamage out of TRIVIAL_RNG into EVENT_CLASS. The L2.2 in-scope total dropped from twenty-two to twenty. The honest-green count dropped from fifteen to fourteen because the RibosomeAssembly green was a paper green. Same proportion, more honest framing.

**Tehol:** Real biology share.

**Bugg:** Eight out of twenty. Forty percent.

**Tehol:** That is the actual number.

**Bugg:** That is the actual number. The fifteen-of-twenty-two from this morning was true at the surface and misleading at the structure. The fourteen-of-twenty includes a column that says how each green was earned. Eight real biology. Six convergence. Zero zero-event paper-passes. Four unwired chromosome-primary processes. Four out-of-scope until L2.event harness exists. Six DETERMINISTIC out of L2.2 by construction.

**Tehol:** Then the next question.

**Bugg:** Then the next question was the convergence greens. The W1-equals-zero ones. Are they true or are they an artifact of the test regime. Operator's instinct was to start with the smallest verifiable claim — ProteinFolding, the simplest of the six, has both a `_closed_form_bounds` call and an explicit stochastic chaperone allocation in OC's port. If the convergence is true biology, an artificial substrate-stress test that scales substrate counts down by progressive factors should still produce W1 of zero. If the convergence is regime-bounded, W1 will grow as substrate scales toward limiting and cross the noise floor at some scaling factor.

**Tehol:** Fired.

**Bugg:** Fired codex with a one-process one-hypothesis investigation prompt at twenty-two thirty IST. ProteinFolding. Five scaling factors. Substrate-stress harness as the artifact. The slot-3 ceiling rules. Codex finished SUT inspection in seven minutes, ran the baseline smoke at minute twelve. Still running at minute thirty-five, no commits yet. Operator wrote this post while it ran.

**Tehol:** Lessons.

**Bugg:** Five.

**Tehol:** Five.

**Bugg:** The first. A serializer fix to an allowlist is not the same as a serializer fix to a value. Day 22 added `chromosome` to the allowlist; the serializer started writing `'<object:Chromosome>'`. The MAT file looked correct. The audit ran on key names not byte contents. Twenty-two days. The cost of a five-minute Python probe with `looks_like_object_placeholder` would have been six dollars in time. The cost of the omission was a 233k-token codex burn rediscovering the bug and an entire afternoon of operator recovery work.

**Tehol:** The second.

**Bugg:** The second. Restart-safe scripts beat restart-correct scripts. The chrom re-extract script's first version deleted all targeted files before running. That was correct for the original launch — we needed to overwrite the placeholder data. It was destructive on every restart after that. The collision at minute twenty-five and the operator-instinct restart at minute twenty-six lost one hundred one of one hundred three files in two minutes. The script took forty-five seconds to patch. The patch went into the same commit as the restart.

**Tehol:** The third.

**Bugg:** The third. Azure throttle has at least two distinct failure modes. The hard cap announced on Day 25 is the two-concurrent-session cap that disconnects at thirty to one hundred thousand tokens. The other one is the peak-demand throttle that disconnects at one hundred five thousand tokens with the error message about exceeding the maximum usage size during peak load. The peak-demand throttle is time-of-day-dependent — IST mid-afternoon equals US morning equals peak. Sessions fired off-peak survive. Same prompt, same configuration, different outcome. The operator has not yet hit this in the Kimi case during off-peak hours.

**Tehol:** The fourth.

**Bugg:** The fourth. A green can be retired. The board has gained greens for eight weeks. It lost one today. The reclassification mechanism is the same mechanism that promoted greens — a catalog edit with a rationale. Removing a green that is a paper-pass is harder to do emotionally than adding a green. The scoreboard is more honest after.

**Tehol:** The fifth.

**Bugg:** The fifth. Convergence and biology are not the same thing. The L2.2 verdict mechanism treats them the same — both produce PASS — but the underlying claims are different. Real biology PASS says OC's stochastic distribution matches Karr's stochastic distribution. Convergence PASS says OC's deterministic shortcut equals Karr's deterministic upper bound. The first is the thing the gate is for. The second is a mathematical equivalence at a regime boundary. The L2.2 gate cannot tell them apart by construction. The fifteenth-versus-fourteenth-versus-eight-of-twenty discussion this evening was the operator finally separating the two for the dashboard.

**Tehol:** The chromosome state.

**Bugg:** The chromosome state is a separate problem with a known shape. Phase C v2 slash pc-t7 is the codename. Estimated three to five calendar weeks of focused work to port the full `Chromosome` state and the `CircularSparseMat` data structure plus the four-or-five process re-ports that ride on it. Today's serializer plus today's projection design are foundational infrastructure for that effort. They are not currently consumed. They will be when pc-t7 is scheduled.

**Tehol:** Tomorrow.

**Bugg:** If the PFolding stress test confirms biology — extend the harness to the other five convergence greens. If it shows regime-bounded — document the boundary, decide whether to port Karr's inner Monte Carlo step for any of the six. Independently, wire Replication and DNARepair against their OC-side surfaces with a catalog note pinning the pc-t7-target projection as the future replacement. That moves the board to sixteen of twenty real-biology candidates. The chromosome processes that cannot ship at L2.2 until pc-t7 lands stay parked. The L2.event harness for the four EVENT_CLASS processes stays parked. Neither is going to ship in a week.

**Tehol:** Push.

**Bugg:** Pushed earlier today. Main is at `7a44730`. Plan refresh at the top. Scoreboard correction in the commit message of `d184ffc`. The pc-t7 effort is named in the plan and not in any todo file yet.

---

*Postscript, for the record. Commits in order, June 12 evening through June 14 night.*

*June 12: `2b87ca6`, `525a9af` macromol investigation (laundering-h11 branch, not merged); `a462b71` H12 detector plus `LAUNDERING_VS_CONVERGENCE.md`; `cc2b207` H12 promotion (5 candidates to confirmed); `2edfd4e` plan refresh.*

*June 13: `6b1d4d2`, `a863bf6` Batch A merge (plus 2 greens — PPI, PPII via convergence); `0d64836` ProteinDecay ndim=1 fix (plus 1 green); `2aff1ea` sync; `749b877` PTransloc catalog promote; `145ac06`, `228fe86` cherry-picked fix-ptransloc beats; `cea556d` PTransloc wiring surfaces (plus 1 green); `d260fc7` Batch C merge plus hand-fix on PMod (plus 3 greens — PFolding, PMod, RibosomeAssembly); `e350b1c` sync.*

*June 14: `f5f6aee` Metabolism shape adapter (Beat 5 still FAIL, but no longer shape-erroring); `0ff0bb5` chromosome state serializer (the foundational fix); `6f83a73` plan refresh; `25d5f41` sync; `31eb0ab` make MATLAB re-extract restart-safe; `4373f6c`, `c751b50`, `c0f380c`, `28b09cc` metabolism-fail investigation four beats; `85b1712` merge metabolism fix (plus 1 green — the 15th, real biology W1 168.43); `285d042`, `c5d5adb` catalog v1.4 chromosome projection design (operator-authored after codex died on quoting); `d184ffc` catalog v3.1 reclassify RibosomeAssembly + DNADamage to EVENT_CLASS (minus 1 green, now 14); `e6062f4`, `7a44730` plan refreshes.*

*MATLAB extracts: the chromosome re-extract is at `E:\opencell\.matlab_chrom_full.log`. 5 chrom-primary processes times 50 seeds, ~118 minutes wall. Verified via Python audit script — all 250 files carry real serialized chromosome data (no placeholder strings).*

*Held-back branches: `exec/l22-wire-dnasupercoiling` (empty worktree, pc-t7-blocked); `exec/l22-wire-dnadamage` (same, plus EVENT_CLASS-blocked); `exec/l22-rewire-replication` (Beat 1 only from Day 28 morning, the codex that discovered the placeholder bug); `investigate/macromol-laundering:525a9af` (hypothesis map, findings absorbed into H12 work); `investigate/pfolding-convergence-claim` (still running at time of writing); `design/l22-chrom-projections:285d042` (merged); `investigate/metabolism-honest-fail:28b09cc` (merged).*

*Cross-project artifacts saved to `D:\OneDrive - Microsoft\.pm-os\templates\` on Day 25 and unchanged this cycle. Skill files: `~/.copilot/skills/delegate-to-kimi-k2.6/SKILL.md` (NEW, ~8 KB); `~/.copilot/skills/delegate-to-codex/GOTCHAS.md` (one new entry — verify oracle data before firing oracle-touching delegations). Four decisions logged: the four from the Day-25 session plus one Day-28 entry pending the operator's call on pc-t7 scheduling.*

*Tehol and Bugg are on loan from Steven Erikson's* Malazan Book of the Fallen.

*Previous: [Days 24-25 — A Fix in Six Minutes, A Wiring That Was a Lie, and the Detector That Wrote Itself](2026-06-12-a-fix-in-six-minutes-a-wiring-that-was-a-lie-and-the-detector-that-wrote-itself.md)*
