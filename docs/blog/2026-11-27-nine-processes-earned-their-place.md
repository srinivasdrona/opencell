---
title: "Days 185-190: Nine Processes, One Honest Scale, and the Front Door"
date: 2026-11-27
authors: [sdrona]
tags: [opencell, fidelity, l2.2, l2.5, rng, mass-conservation, provenance, vivarium]
---

*November 27, 2026 — Day 190. Active closure resumed after the November 21 snapshot and finished November 23 (Day 186); today is the publication dispatch, not a claim of continuous bench work through the intervening days.*

---

**Tehol:** Bugg, why is there a scale on my breakfast table?

**Bugg:** It is the scale from our [last dispatch](2026-11-21-five-green-gates-an-expired-license-and-three-scales-for-one-cell.md), sir.

**Tehol:** Last time there were three scales, five green auditions, and four processes allowed through the door. This time there is one scale and no breakfast. I hope the missing breakfast is not your demonstration of mass conservation.

**Bugg:** The breakfast has not been modeled. The mass boundary has been closed. Cohort 1 is independently accepted, and this publication brings the accepted source and evidence onto `main`: **nine of twenty-eight processes eligible for L2.5 entry; nineteen still blocked.**

**Tehol:** *[moves the scale away from his plate]* Nine. A number we have visited before without being entitled to live there. What makes this visit different?

**Bugg:** The five gates were rerun on the same final integrated source. The material they produce is visible to all three live mass readers. The private random stream repair survived integration. And the evidence passed independent current-source, portable, strict-input, and committed-copy acceptance.

**Tehol:** Then start with the scale. Not the checkmarks. Checkmarks have been known to travel without their luggage.

---

**Bugg:** We reopened the bench after the November 21 snapshot. The bounded task was not “fix whichever reader the next test happens to call.” It was to close one shared material-accounting boundary across `KarrObservabilityStep`, the standalone `compute_cell_mass` helper, and the live CSV `MassEstimator`.

**Tehol:** The observer, the phenotype clerk, and the clerk who actually writes the running chassis's ledger. Same basket, same grams.

**Bugg:** With source-derived weights for the represented RNA and protein forms and compartments. Intermediate proteins must not disappear because a flat mature-only view does not contain them. Processed RNA, intergenic fragments, mature RNA, and aminoacylated forms must retain their actual identities. Aliases and activity views must not become extra molecules.

**Tehol:** A promising rule. Did our first attempt obey it?

**Bugg:** Not completely.

**Tehol:** Of course. Which molecule walked up to the scale wearing an invisibility cloak?

**Bugg:** `MG_072_DIMER`. Independent review found an existing physical complex stock, already present in the fixture-backed chassis, that all three repaired readers still omitted.

**Tehol:** Already present? Not a hypothetical complex we might assemble in the next cohort?

**Bugg:** Already present, sir. The reviewer added one particle to the unchanged state basket. The source molecular weight required a positive mass increment. Every reader returned zero.

**Tehol:** So we had congratulated ourselves on weighing every apple while leaving the sacks of flour under the table. Three agreeing accountants are not an independent witness if all three copy the same incomplete inventory.

**Bugg:** Precisely. The [source-backed particle test](../../tests/vivarium/test_shared_mass_existing_complex_stock.py) reaches the standalone helper, a genuine observer Engine, and the CSV reader. It does not ask a cached hint what the mass ought to be.

**Tehol:** And we did not respond by declaring complexes “future work”?

**Bugg:** No. Future complex *kinetics* are a separate task. Existing physical complex *material* belongs on today's scale. The completed repair weighs all **201 mature complex rows and 33 physical Activation leaves**, alongside the RNA and monomer forms. It excludes aliases and activity-only projections from the particle count.

**Tehol:** That distinction I can explain to a product manager. We have not promised to bake tomorrow's bread. We are nevertheless obliged to weigh the flour already in the pantry.

**Bugg:** Independent review accepted the complete boundary, including mixed stores, zero stocks, poisoned hints, actual source bindings, and real CSV consumption. The three readers now agree with the source-complete basket, not merely with each other.

**Tehol:** *[looks at the scale]* Excellent. One definition of the basket. Surely that cannot produce another failure.

**Bugg:** It produced a dependent phenotype failure.

**Tehol:** I should stop feeding you these lines.

---

**Bugg:** P10b asks for **protein-monomer dry mass**. Its caller had been using the protein aggregate. Once that aggregate correctly included physical complexes, it no longer answered the monomer-only question.

**Tehol:** Wait. Are we about to remove the flour because the apple target disagrees?

**Bugg:** That would make the cell mass wrong again.

**Tehol:** Then leave the full basket alone. Ask the apple subtotal. Which scale are we actually asking to answer which question?

**Bugg:** Exactly the repair. The [P10b caller](../../opencell/analysis/phenotypes.py) now uses the source-owning monomer subtotal. The full protein aggregate and total cell mass still include physical complexes. We did not weaken the target or hide complexes to get the old number back.

**Tehol:** So “one shared scale” does not mean “one number pasted into every report.”

**Bugg:** It means a shared material definition with the right subtotal for the declared comparison.

**Tehol:** Good. I am willing to be ignorant of biology. I am less willing to be ignorant of what a question asks.

---

**Tehol:** Now the random stream. Last time `ProteinModification` had a real fifty-seed PASS and still missed a modification on persistent replay. Did the scale repair knock that fix loose?

**Bugg:** No. PM retains its own private `mcg16807` stream, the neutral state codec, and the source one-uniform weighted-sampling behavior. It is not borrowing the chromosome's shared random stream. The unchanged persistent hundred-tick replay remains exact across all five observables; the integrated PM selection passed all **178 tests**.

**Tehol:** Then the final source freeze was uneventful?

**Bugg:** One frozen capture test failed before its RNG assertions. It still demanded exactly thirteen runtime input paths. The completed mass boundary made the actual required closure thirty-five.

**Tehol:** An intriguing choice. We can either capture the files we really consumed, or make the number thirteen feel appreciated.

**Bugg:** We stopped for independent source-contract adjudication.

**Tehol:** Not “change thirteen to thirty-five and carry on”?

**Bugg:** No. The reviewer derived the required path union from the real PM and codec inputs, mass code, physical owners, and parameter files. The revised guard checks exact membership, uniqueness, and actual file hashes. **All original thirteen mandatory paths remain inside the thirty-five.** No source binding was deleted to restore the old cardinality.

**Tehol:** A longer receipt because we bought more ingredients, not because we printed it in a larger font.

**Bugg:** And the complete per-tick frame surfaces remained part of the input checks. Hashing a source file is not a substitute for checking that the oracle actually captured the fields the runner consumes.

**Tehol:** This is the sort of red test I want us to keep remembering. Sometimes the program is wrong. Sometimes yesterday's description of the program has become wrong. Either way, the answer is not to arrange the test selection until the red disappears.

---

**Bugg:** With mass, the monomer-only caller, PM's private stream, and the capture contract integrated, we froze [source `7586be17`](https://github.com/srinivasdrona/opencell/commit/7586be17b746c8e6f18068898859f346192ed892). The genuine campaign generation HEAD was [`10393d59`](https://github.com/srinivasdrona/opencell/commit/10393d59ca9f5b7e135e5098ebde854c0334cf9e).

**Tehol:** Why distinguish those from the later acceptance commit?

**Bugg:** Because later evidence and review commits do not travel backward in time and become the code that produced the statistics. The source hashes remain the measurement's identity.

**Tehol:** And this time all five soloists performed again, rather than having their old reviews stapled to the new costumes?

**Bugg:** All five ran genuinely fresh standard gates on that combined freeze: `ProteinTranslocation`, `ProteinProcessingII`, `ProteinModification`, `RNAProcessing`, and `RNAModification`. Each used fifty seeds and a thousand Karr-only bootstrap resamples. PP2 used its registered twenty-tick horizon; the other four used a hundred ticks. **All five passed.** PP2's registered deterministic-convergence warning remains disclosed.

**Tehol:** No threshold relaxation, no old statistic wearing a fresh hash?

**Bugg:** Neither. The original results and frozen source were preserved.

**Tehol:** Then we opened the publication ledger and found—

**Bugg:** `MISSING_EVIDENCE`.

**Tehol:** *[leans back]* Naturally. At this point I would worry if the front door opened on the first try.

**Bugg:** The raw runner had completed the biological campaigns but does not write the sweep wrapper's `sweep_provenance.json` completion sentinel. Independent review accepted the numerical and current-source results while correctly refusing portable and strict packet acceptance.

**Tehol:** The run happened. The receipt required for this door did not. Those are two different facts, and neither gets to erase the other.

**Bugg:** Our [existing evidence policy](../phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md) explicitly permits revalidating a completed run and attaching a provable sentinel. We used that documented route, not a new exception.

**Tehol:** Tell me we did not backdate a form saying the wrapper had been there all along.

**Bugg:** The finalizer worked on new packet copies only. Existing tools normalized the packet references and rechecked the actual source and input hashes. The retrospective sentinels record the original run identities and current attestation, and explicitly say **no contemporaneous sweep launch and no new biological campaign**. Original source, numerical results, and the first missing-sentinel review remain unchanged.

**Tehol:** A receipt issued afterward that admits it was issued afterward. Astonishing what paperwork can accomplish when it refrains from fiction.

**Bugg:** Independent portable and strict review accepted the finalized packets. Then committed-copy review verified all **forty compact packet files** against the accepted bytes and their Git blobs.

**Tehol:** Forty files sounds reassuring. Does that let a reader reconstruct every OpenCell sample and redo the bootstrap?

**Bugg:** No, sir. Full raw OpenCell output tensors were **not retained**. The allocator records are scalar input summaries, not raw outputs. This is accepted numerical, source-bound, and portable evidence under the existing contract—not an independent raw-sample reanalysis or a claim that the missing tensors can be recovered from those summaries.

**Tehol:** Keep that sentence next to the celebration. A receipt is worth more when it tells you what is *not* in the parcel.

---

**Tehol:** Now we may do the arithmetic. Four retained processes plus five newly closed ones.

**Bugg:** The retained four are `ChromosomeSegregation`, `HostInteraction`, `ProteinActivation`, and `TerminalOrganelleAssembly`, in their unchanged genuine L2.1 scopes. The five new Cohort 1 processes meet their current L2.2 and finding-specific obligations. The honesty audit derives **9/28 eligible and 19 blocked**, with `INTEGRITY_OK`.

**Tehol:** “Derives” rather than “we changed the headline to nine.”

**Bugg:** From the full evidence index and the actual finding dispositions. Two regression tests still asserted the old four-eligible, twenty-four-blocked snapshot and obsolete `ProteinTranslocation` blockers. Even the earlier local candidate had already reached six and twenty-two.

**Tehol:** So the tests were guarding yesterday's census, not today's admission rule. Did we preserve the rule?

**Bugg:** Independent review reconciled only the demonstrated stale references. The real TranscriptionalRegulation dependencies and OPEN findings remain. Metabolism remains fail-closed. The denominator remains twenty-eight. The original failing test bytes and RED receipts are preserved; the complete affected honesty and publication selection now reports **21 PASS**, with no skips, deselections, or expected failures.

**Tehol:** And the entire L2.2 board is green?

**Bugg:** No. Its full index is **five PASS, seventeen stale FAIL, and two MISSING_EVIDENCE**. The four retained L2.1 processes are not extra L2.2 rows. An integrity-clean index can honestly contain failed and missing evidence.

**Tehol:** There is the number I wanted beneath nine. Otherwise someone will add four to the wrong table and resurrect our old twenty-two-green mirage.

**Bugg:** The [accepted closure record](../phase_f/pre_l25/acceptance/cohort1_final_10393/FINDING_CLOSURE.md) spells out the boundaries. This is eligibility for **entry** to L2.5. It is not L2.5 composition PASS, not all twenty-eight processes certified, not a completed combined whole-cell simulation, and not long-horizon phenotype or growth agreement.

**Tehol:** Nine people have earned tickets to the rehearsal. We have not reviewed the concert.

---

**Tehol:** Before you show me the next nineteen problems, a question about this front door. Why did accepted work keep sitting on branches while the public default told an older story?

**Bugg:** I had treated branch-only publication as an adequate finish line. It wasn't. A local commit records the work. A push makes a branch available. A verified integration into `main` makes the accepted work the project's default.

**Tehol:** Exactly. We did not build a museum of alternative endings. If the work is accepted, put it where the next reader begins.

**Bugg:** This milestone publishes the accepted candidate [`0c0dd11`](https://github.com/srinivasdrona/opencell/commit/0c0dd11e5c452a2c627f01489f0d78342a788b55) and this dispatch together through verified main integration. Existing main-only posts and the append-only provenance history are preserved, not replaced wholesale.

**Tehol:** No shortcut past verification. No indefinite branch purgatory dressed up as caution.

**Bugg:** Public `main` now carries the nine-process eligibility baseline. The separate older audit branch's four-process snapshot remains history in that checkout; it is no longer the default project state.

**Tehol:** Good. I am not asking you to stop being careful. I am asking careful work to arrive somewhere.

---

**Bugg:** Meanwhile, six Cohort 2 producers and their technical interfaces made progress in isolated work. None is newly eligible, and those repairs are not integrated into this nine-process publication.

**Tehol:** Give me the shape of the next boundary, not a shopping list.

**Bugg:** One boundary begins with evidence we said was missing. The genuine two-hundred-seed DNASupercoiling F traces were not missing globally. We had looked in the wrong worktree. Accepted copies were found and staged as **3.05 GB of verified private inputs**.

**Tehol:** An impressive recovery operation: walk to the cupboard that actually contains the things.

**Bugg:** It fixes physical availability, not readiness. The genuine shared RNG provider has captured `State` across twenty thousand frames but no `Seed`. The required shared BEFORE restoration and complete Seed/State decoding and source capture remain blocked.

**Tehol:** And we cannot infer a seed because there are so many frames?

**Bugg:** Not under this source contract. Nor may we burn an invented prefix or call a process-private stream the shared stream. The [accepted S2 owner contract](https://github.com/srinivasdrona/opencell/blob/e1786f4aa62308eef080e0e585ceef12b85ac712/decisions/dec-008-two-consumer-chromosome-owner-contract.md) is bounded technical progress, not process eligibility. The already-authorized closure does not need a new permission slip; it needs the missing technical inputs.

**Tehol:** Permission is not an RNG state. An excellent sentence to place above the cupboard.

**Bugg:** Another boundary is RNA release. RNADecay's standalone release API is independently accepted locally. But the actual Translation writer emits a bound-70S increment of ten without an identified public binding slot and synchronized polymer writer. The shared lifecycle cannot be enrolled honestly yet.

**Tehol:** So exporting some private arrays full of zeros would demonstrate an interface with nobody on the other end.

**Bugg:** Exactly. It would not close the actual writer-to-consumer contract.

**Tehol:** And the expired MATLAB license?

**Bugg:** Still a real boundary. RibosomeAssembly has **zero of fifty genuine M200 event inputs**. The old cohort's files contain a hundred captured ticks at offset two hundred.

**Tehol:** Starting a book at page two hundred does not give you two hundred pages.

**Bugg:** The repaired horizon guards now refuse that substitution. Format-only tests can prove the refusal works; they cannot manufacture a longer source capture. New licensed capture and the joint source obligations remain open. No M2 PASS or renewed license authority is claimed.

**Tehol:** Then the next job is not to throw another celebration at a producer that works alone. It is to bring the real missing state, the real public writer, and the real captured horizon to their respective doors.

**Bugg:** Yes, sir. The next cohort has work, not admission.

---

**Tehol:** *[returns the scale to the middle of the table]* In [April](2026-04-22-4500-lines-before-lunch.md), we celebrated how much code you could produce before lunch. Today we have spent rather longer persuading a scale that a particle exists.

**Bugg:** The particle was not persuaded, sir. It existed throughout. We corrected the ledger.

**Tehol:** Better. And nine is no longer an attractive sum we write in the margin. It is nine source-backed admissions, with the nineteen refusals still legible, delivered through the front door.

**Bugg:** That is the milestone.

**Tehol:** Then you may remove the scale. I want breakfast.

**Bugg:** Shall I include the flour, sir?

**Tehol:** In the pantry total, certainly. Not in my apple subtotal.

---

*Previous: [Days 126–184 — Five Green Gates, an Expired License, and Three Scales for One Cell](2026-11-21-five-green-gates-an-expired-license-and-three-scales-for-one-cell.md). Source and accepted evidence: [Cohort 1 finding closure](../phase_f/pre_l25/acceptance/cohort1_final_10393/FINDING_CLOSURE.md), measured HEAD [10393d59](https://github.com/srinivasdrona/opencell/commit/10393d59ca9f5b7e135e5098ebde854c0334cf9e), accepted candidate [0c0dd11](https://github.com/srinivasdrona/opencell/commit/0c0dd11e5c452a2c627f01489f0d78342a788b55). Publication baseline: **9/28 eligible for L2.5 entry, 19 blocked**. No L2.5 composition or whole-cell completion claim.*
