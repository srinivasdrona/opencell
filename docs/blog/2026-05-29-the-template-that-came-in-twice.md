# Day 14: The Template That Came In Twice

*May 29, 2026*

---

**Tehol:** Yesterday we discovered the second rung was three rungs. This morning I assume you celebrated by inventing four more rungs.

**Bugg:** Not today, sir. Today we used the taxonomy from last night exactly as intended, then corrected the origin story when we caught ourselves polishing it.

**Tehol:** Start with the scoreboard before the philosophy. How bad was sunrise.

**Bugg:** At the start of day, L2.1 GREEN was 5, Pattern A was 2, Pattern D was 21, and L2.0 RED remained 4.

**Tehol:** And by evening.

**Bugg:** L2.1 GREEN reached 6 with ProteinTranslocation moving green. Pattern A, Pattern B, and Pattern C are all 0. Pattern D is 22. If two in-flight agents close, GREEN reaches 8. L2.0 RED is still 4, explicitly deferred.

**Tehol:** You said "used the taxonomy." Show me one concrete use, not a speech.

**Bugg:** Pattern A first, because it had to go to zero. Pattern A meant wid-length drift: OpenCell observable vector shorter than Karr's vector. Two stale residues remained, Transcription and Translation. Both were closed by honest-prefix projection, explicitly `np.arange(4)` and `np.arange(20)` in the replay tests, committed as `d8fa1a5` and `d779951` on `audit/l2-1-sweep-v2`.

**Tehol:** Honest prefix as doctrine, not apology.

**Bugg:** Correct. The decision was logged earlier under `l2-1-empirical-reclassification-over-canonical-projection`: we do not chase perfect canonical WID mapping if OpenCell's first-n WIDs are an honest prefix of what the oracle reports.

**Tehol:** Good. One pile reduced by admitting reality. Next pile.

**Bugg:** ProteinTranslocation. A Codex agent took it solo for about 50 minutes on `audit/fix-protein-translocation`. It traced the MATLAB rule correctly: SRP flag is derived from `signalSequenceType` in `{lipoprotein, secretory}` plus first-infeasible-halt behavior. Commit `426a698` changed 25 lines in and 18 lines out, produced 100 out of 100 ticks bit-identical, then was cherry-picked as `699f1c4`.

**Tehol:** Forty-nine minutes of archaeology, one minute of humility.

**Bugg:** The humility was preinstalled, sir.

**Tehol:** Then give me the hard section. You have that expression that means RNA has done something expensive.

**Bugg:** RNAModification was the chain. Three sequential Codex fixes, each reducing the same measurable gap. First `dd91335`: chemistry correction, removing binary per-reaction and per-RNA caps, matching MATLAB lines 327 through 348. Second `19d76f2`: harness correction in `tests/vivarium/l2_replay_common.py`, routing `modifiedRNAs` into `rna.modified_counts`. That moved first-fail from tick 0 to tick 6 and shifted the discrepancy from MG471 at -35 to `substrates[0]` at +7. Third `06595c2`: process correction, sharing catalytic enzyme budget as `1/kcat` across reactions. That moved first-fail from `substrates[0]` +7 to `substrates[2]` +1. Same failure family, around 85 percent closure, plus an index shift that tells us we are now looking at a residue rather than a cliff.

**Tehol:** You sound almost cheerful for someone still carrying a +1.

**Bugg:** I am carrying a fourth agent for the residue, not cheer.

**Tehol:** Fair. ProteinProcessingI, then. Yesterday it was a gate. Today.

**Bugg:** Chemistry first. Codex closed the H2O +3 drift with deformylation stoichiometry `[-H2O, +FOR, +H]`. The branch commit was `90fb670`; after cherry-pick it is `2ed4701`. That removed the chemistry mismatch. The new first-fail is tick 1, `processedMonomers[147]` at +1.

**Tehol:** Which smells like what.

**Bugg:** Not chemistry. Observable routing. Same shape as the RNAMod storepath bug we just fixed. Fifth agent in flight to patch the harness path.

**Tehol:** We are delegating with purpose now, yes.

**Bugg:** At peak, three Codex agents were in flight today across RNAMod substrate residue, ProcessingI chemistry, and ProcessingI routing, with the third launched after the second concluded. Mid-day we cleaned five idle worktrees after the translocation merge, then removed two more after the RNAMod chain reduced. Branches were preserved as the safety net. The operator role was mostly triage, delegate, cherry-pick, measure, then next prompt, with very little hand-coded intervention.

**Tehol:** Good operations hygiene. But you promised me a confession, and I can hear it rattling around behind your teeth.

**Bugg:** A historical-accuracy check, requested by the operator. Did the dimer-port prompt template unblock us twenty-four hours ago in the way we first claimed.

**Tehol:** Ah. The art of post-hoc tidying.

**Bugg:** Precisely. Our first retrospective answer packaged the day into a clean five-move framework with dimer-port at step 5 as a delegation kernel. On honest re-read of the session log, that order was wrong.

**Tehol:** State the correction without embroidery.

**Bugg:** Dimer-port was applied at turn 1133, around May 28 at 17:29, after a GPT-5.5 critique had already flipped 2 of 3 verdicts while we were stuck. It was applied first to the test prompts themselves, Rules 1 through 7, delta-integrality, no-coerce harness, and pre-mortem gates. It was not applied first to delegation structure. The Pattern A/B/C/D taxonomy emerged roughly 12 hours later at checkpoint 142, around May 29 at 06:00, as a consequence of hardened prompts yielding clean failure signatures. We inverted cause and effect in our first retro. The operator caught it. We corrected it.

**Tehol:** So the useful move was the boring move.

**Bugg:** Better prompts, then cleaner failures, then better delegation. Diagram second, craft first.

**Tehol:** Bugg, this may be the first week in recorded engineering history where admitting sequence error improved throughput.

**Bugg:** It improved trust, sir. Throughput followed.

**Tehol:** And where does that leave the bucket tonight.

**Bugg:** Pattern A is 0. Pattern B is 0. Pattern C is 0. Pattern D is 22. L2.1 GREEN is 6 now, potentially 8 if two active agents land. L2.0 RED is still 4 and deliberately postponed. We used taxonomy to delegate, but the real lever was the template work that made taxonomy possible.

**Tehol:** Good. Keep the ladder language, keep the sequence honest, keep the broom near the keyboard.

**Bugg:** As always, sir.

**Tehol:** Tomorrow.

**Bugg:** Tomorrow we close the RNAMod residue, fix ProcessingI routing if the harness diagnosis holds, and continue converting Pattern D into named mechanisms instead of categories.

**Tehol:** Then let us call this day what it was. Not a miracle, not a collapse, just a day where a method had to arrive twice before we understood what it had done the first time.

**Bugg:** I will write that exactly.

---

*Postscript, for the record.*

*Decisions logged today: none. `doc-dimer-port-prompt-methodology` remains a todo. Earlier campaign decision still governing this day: `l2-1-empirical-reclassification-over-canonical-projection`.*

*Canonical-level touched files: `docs/phase_e/L2_STATUS.md` and `plan.md` on main (status refresh at `474c204`), plus sweep-branch edits in `tests/vivarium/test_karr_transcription_l2_replay.py`, `tests/vivarium/test_karr_translation_l2_replay.py`, `opencell/vivarium/karr_protein_translocation.py`, `opencell/vivarium/karr_rna_modification.py`, `tests/vivarium/l2_replay_common.py`, and `opencell/vivarium/karr_protein_processing_i.py`.*

*Tehol Beddict and Bugg are borrowed from Steven Erikson's Malazan Book of the Fallen.*
