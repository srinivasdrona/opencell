# Days 24-25: A Fix in Six Minutes, A Wiring That Was a Lie, and the Detector That Wrote Itself

*June 11-12, 2026*

---

**Tehol:** Where are we.

**Bugg:** Five honest PASSes on the board. Four caught launderers. Two committed bug fixes through codex. One catalog version bump. One generalized detector that the prior runner did not contain. One wiring branch held back from merge because the new detector says it is dishonest. Roughly twenty-eight hours of wall, two of which were the operator asleep and most of the rest was codex executing while the operator watched.

**Tehol:** Positive.

**Bugg:** Positive. The scorecard moved from "infrastructure with nothing riding on it" to "infrastructure with nine processes riding on it, five of them honestly green, four flagged as not." The not-flagged-as-honest is, in this project, the same currency as the honestly-green. We finally know the shape of the lie.

**Tehol:** Walk it.

**Bugg:** Thursday late, after the Day-23 post landed. Pre-commit hook for catalog-conformance shipped — script reads the staged diff against `tests/vivarium/l2_2_design_a*.py` or `PROCESS_CATALOG.yaml`, refuses the commit unless the message body ends with a `Catalog-Entry:` fenced block. That was the receipt mechanism for the spec-authority rule from Day 23. Then operator stepped away. June 9 and June 10 produced zero commits. Token cooldown plus weekend.

**Tehol:** Resume.

**Bugg:** June 11, just after midnight. Two bugs identified from the Day-23 Green Plan. Bug 2 first — the extractor's `pick_snapshot_properties` allowlist omitting `chromosome`, the reason three of five fanout extractions were unusable. Composed slot-3 with the catalog entry quoted, two scripts named in the read-set, the failure mode named: "the fix changes one extractor pass but a sibling pass still skips chromosome." Fired codex.

**Tehol:** Wall.

**Bugg:** Five point eight minutes. Four beat commits, merge `71710c0`. Cleanest delegation in the project's history. Codex Beat 1 confirmed missing from snapshot, Beat 2 added chromosome to the allowlist, Beat 3 ran a single-seed extraction of DNADamage and verified chromosome appeared in the output, Beat 4 inversion ruled out three failure modes by inspection, Beat 5 verified suite green. The spec quotation at the top of slot 3 was the catalog entry for DNADamage. Slot 3 size two point three KB.

**Tehol:** Bug 1.

**Bugg:** Bug 1 was the `_seed_alignment_warning` spuriously gating cross-engine ensembles. The warning compared numpy seed N against MATLAB seed N and reported drift; the drift was real but meaningless because the two RNG streams produce different sequences for the same integer seed. The warning was flipping verdicts to FAIL on processes that were honestly converging. Operator had been working around it for a week. The fix was to make the warning informational and rename it to `SEED_ALIGNMENT_DIAGNOSTIC`.

**Tehol:** Wall.

**Bugg:** Forty-three minutes. Three codex retries. The first attempt landed Beat 2 but Beat 3 regression test was wrong-shape — codex tried to write a test for the warning text and missed that the verdict-flip happened in a different function. The second attempt fixed Beat 3 but Beat 5 verification reused a stale fixture. The third attempt landed clean. Five beat commits, merge `73facea`. Slot 3 was three point eight KB. The retries cost minutes, not hours, because the per-beat commit cadence let the operator see exactly where the wrong-shape happened and dispatch the next attempt with that constraint added.

**Tehol:** Catalog v3.

**Bugg:** Then the catalog hit a contradiction the Day-23 Cytokinesis Phase-0 false-PASS had already revealed but we had not formalized. Cytokinesis was listed as `bucket: ALGORITHMIC_SHALLOW`, `in_scope_L2_2: true`. The catalog notes on the same entry said `seed_window: tick_range_from_division: [-50, 0]`, `event_density: sparse`. Those two facts contradict the bucket. An algorithmic-shallow process fires per tick. A sparse event-density process fires once per cell cycle. The runner's tick-loop harness cannot ask the right question about either Cytokinesis or FtsZPolymerization without a separate event-class harness that does not exist. Catalog v3 introduced a `harness_type` field at bucket level and per-process. Two values: `design_a_per_tick` for the seventeen continuous processes, `event_class` for Cytokinesis and FtsZPolymerization. Runner's `_validate_process_request` now refuses event_class processes with "L2.event harness needs to be built; this is a known scope gap." Committed `9173b73`.

**Tehol:** The first honest PASS.

**Bugg:** Then we went to Transcription. The Day-23 post had promised that the next move was a codex delegation with the catalog entry quoted in slot 3. The pre-flight discovered that Transcription was already wired and the v2 ensemble was already on disk from a Day-20 extraction. No codex needed. The smoke at M=10, N=50, B=200 returned PASS, primary RNAs W1 of zero point zero zero six nine, KS p value of zero point three three, canonical seed count fifty, no warnings. The full-scale gate at M=100, N=50, B=1000 returned PASS, primary RNAs W1 of zero point zero zero nine zero, KS p value of one point six e-9, no warnings. First genuinely honest L2.2 verdict in the project's history.

**Tehol:** A verdict that came from infrastructure not delegated.

**Bugg:** A verdict that came from infrastructure built across Day 22 and Day 23 finally meeting a process that was already correctly wired. The honest read of Day 23's "negative day" is that the day produced the infrastructure that produced today's PASS. The artifacts ledger is now plus eight, the verdicts ledger plus one.

**Tehol:** Translation.

**Bugg:** Translation full-scale gate, same shape. PASS, primary monomers W1 of zero point zero zero six seven, no warnings, canonical seed count fifty.

**Tehol:** Two.

**Bugg:** Two honest greens. Then RNADecay and ProteinDecay smokes. Both returned PASS on primary channels — RNAs W1 of zero point zero zero zero seven for RNADecay, monomers W1 of zero point zero zero zero eight for ProteinDecay. Both carried a `KARR_LEGACY_SINGLE_SEED_FALLBACK` warning. The Day-23 MATLAB extraction had only covered the five fanout processes. Fourteen of the twenty design_a_per_tick processes still had no v2 ensemble. The verdicts were honest at single-seed precision and degraded at distributional precision.

**Tehol:** The next MATLAB.

**Bugg:** Fired immediately. Fourteen processes, fifty seeds, single MATLAB process. Two hundred fifteen minutes wall. Seven hundred MAT files. The chromosome bug from Bug 2 had landed two hours earlier, so DNADamage and DNASupercoiling extractions came out usable for the first time. No re-runs needed.

**Tehol:** Macromol.

**Bugg:** While the MATLAB was running we wired MacromolecularComplexation via codex. Slot 3 quoted the catalog entry verbatim at the top, named the catalog primary as `complexs`, and explicitly named the Day-22 d4 fanout deviation — "d4 fanout wired substrates instead of complexs; this delegation must not repeat that." Sixty-nine minutes wall. Five beat commits, merge `3f18106`. Codex's STATUS reported PASS at M=10, N=50, B=200 with primary complexs W1 of zero point zero, KS p value of one point zero, canonical seed count fifty. The STATUS noted the W1 was suspicious and ran a single-tick verification — Karr_after equalled OC_after exactly. Codex called it deterministic biology and shipped.

**Tehol:** And the operator.

**Bugg:** And the operator read the STATUS and was satisfied for about ninety seconds. Then noticed the signature. W1 equals zero and KS p value equals one is the Day-22 Cytokinesis Phase-0 signature. The Cytokinesis case was an event process never firing in the replay window; the Macromol case is a stochastic process with two RNG-bearing calls in `next_update`. For a stochastic SUT to bit-match a stochastic oracle is mathematically impossible unless one of the two is reading from the other.

**Tehol:** The probe.

**Bugg:** Tried to compose an investigation prompt for codex. Slot 3 listed eleven hypotheses ranked by likelihood and a three-hundred-eighty-line probe-script structure. Codex read all the references, started writing the comprehensive probe, died at three hundred seventeen thousand tokens with zero commits. Stream disconnect from Azure. Pattern was the Day-22 d3_dnarepair pattern — slot 3 over-historicization. Operator salvaged the partial probe script and ran it manually. The probe results were clear. `all_exact` of one across five hundred sample cells and three channels. The dispatcher path's call count to the macromol-specific stochastic function was zero. Forced variants where the stochastic call was made produced `formed_sum` of zero yet OC still bit-matched Karr. The SUT's stochastic path was not being reached and the harness was nonetheless reporting bit-identity. That is laundering, not biology.

**Tehol:** And the fix.

**Bugg:** Not yet. The hypothesis map was committed on a separate branch (`investigate/macromol-laundering` at `525a9af`), not merged to main. Eleven hypotheses, one most-likely (H11: parallel branch in `next_update`). The fix was deferred because by then the operator wanted to know if Macromol was a one-off or a class.

**Tehol:** And then the batch.

**Bugg:** And then the batch. Fourteen processes needed wiring across the remaining design_a_per_tick set. Operator authored three slot-3 prompts — Batch A for the two TRIVIAL_RNG monomer processes (ProteinProcessingI, ProteinProcessingII), Batch B for the three RNAs-primary processes (RNAProcessing, RNAModification, tRNAAminoacylation), Batch C for the four monomer/complexs processes (ProteinFolding, ProteinTranslocation, ProteinModification, RibosomeAssembly). Fired all three concurrently against the Azure endpoint.

**Tehol:** The wall.

**Bugg:** The wall responded by disconnecting two of the three. Batch B died at thirty-eight thousand tokens, Batch C at one hundred three thousand. Both with `ERROR: stream disconnected before completion: response.failed event received`. Zero commits from B, zero commits from C. Batch A survived. The endpoint cannot sustain three concurrent codex sessions; that is a discovered cap, not a published one.

**Tehol:** The pipeline.

**Bugg:** Authored a serial pipeline watcher in PowerShell. Detects when Batch A's wrapper PID exits, waits fifteen seconds, fires Batch B with the same slot-3 prompt; same trigger for C. One worker active at any time. Then went and wrote three thousand words of cross-project documentation on the 3-slot architecture for the operator's other project while the pipeline ran.

**Tehol:** And the pipeline produced.

**Bugg:** Batch A completed five beats. PPI and PPII both shipped PASS on smoke with primary monomers W1 of zero point zero, KS p value of one point zero. The Macromol signature, twice over. Batch B completed five beats and merged at `d1330f1`. Three processes wired honestly — RNAProcessing primary RNAs W1 of zero point zero zero zero nine, RNAModification W1 of zero point zero zero zero nine, both SEED_NOISE-flagged honest pass. The third, tRNAAminoacylation, shipped W1 of zero point zero, KS p value of one point zero, the Macromol signature again.

**Tehol:** Three.

**Bugg:** Macromol, PPI, PPII, tRNAAminoacylation. Three primary channels — complexs, monomers, RNAs. Two of three are the same channel. Not Macromol-specific. Not channel-specific. A structural failure in the wiring layer.

**Tehol:** And Batch B.

**Bugg:** And Batch B did something the slot 3 did not ask for. Beat 4 inversion. Codex looked at tRNAAminoacylation's smoke result, recognized the signature on its own, and instead of just documenting it as the slot 3 instructed, wrote a runner-level detector. `_primary_channel_oracle_laundering_warning` — a function that compares `oc_vectors[primary_channel]` against `karr_vectors[primary_channel]` element-wise; on bit-identity, appends `PRIMARY_CHANNEL_ORACLE_LAUNDERING` to the result warnings and flips the channel verdict to FAIL. Scoped to RNAs primary on five RNA processes. Then wrote three anticheat tests against it.

**Tehol:** The detector caught itself.

**Bugg:** The detector caught tRNAAminoacylation in the same delegation that wrote the detector. Beat 5 smoke recorded `verdict: FAIL` and the new warning in the result.json. Codex shipped the fix and the harness for the fix in one merge. That was `d1330f1`.

**Tehol:** And C.

**Bugg:** Batch C died again. Beat 1 only, Beat 2 uncommitted in worktree, stream disconnect at three hundred eighty-eight thousand tokens. Pipeline watcher behaved correctly — fired C after B's exit — but the endpoint was still throttled from the earlier concurrent wave. Four processes still unwired.

**Tehol:** Batch A.

**Bugg:** Batch A had completed all five beats earlier in the pipeline, before the detector landed. The operator initially merged A to main alongside B. Then noticed PPI and PPII would now FAIL against the detector that just merged. Reverted the A merge before pushing. A's branch stays alive with its wiring intact, held back from main until the laundering root cause is fixed.

**Tehol:** Re-smoke.

**Bugg:** Merged main with B and the detector into the A worktree, re-ran PPI smoke. `ProteinProcessingI PASS substrates=SEED_NOISE@0.0 monomers=SEED_NOISE@0.0`. The detector did not fire. The detector was scoped to RNAs primary; PPI's primary is monomers. The detector was looking the wrong way.

**Tehol:** Then.

**Bugg:** Generalized the detector. Removed the channel allowlist, removed the five-process allowlist. Detector now fires for any in-scope process whose OC primary channel bit-matches Karr's. Added the legitimate-determinism check ahead of it in the order — if `before` equals `after`, the carve-out fires first and suppresses the laundering warning. Added the event-channel guard to prevent the FAIL flip from overriding `EVENT_CHANNEL_DEFERRED`. One stale anti-cheat test (Translation laundering test, written when Translation wasn't in the old allowlist) expected `cheated_payload.verdict == "PASS"`; updated to `cheated_payload.verdict == "FAIL"` because the new detector correctly catches it. Forty-six tests pass. One test deselected — `test_protein_decay_monomer_oracle_is_projected_not_raw_head_slice`, which fails on a pre-existing ProteinDecay extractor bug (the v2 monomer cube is ndim=1 where the projector expects ndim=2). Tracked separately. Commit `408bf96`.

**Tehol:** The state.

**Bugg:** Main is at `87e1b8c`. Pushed. Honest greens on the board: Transcription full-scale, Translation full-scale, RNAProcessing smoke, RNAModification smoke, RNADecay v2 re-smoke. Five. Caught launderers: MacromolecularComplexation, ProteinProcessingI, ProteinProcessingII, tRNAAminoacylation. Four. Unwired-from-the-fourteen: ProteinFolding, ProteinTranslocation, ProteinModification, RibosomeAssembly, ProteinDecay (blocked on the ndim=1 extractor bug), DNASupercoiling, DNADamage, Metabolism. Eight. Plus three from the Day-22 fanout still pending re-wire: ReplicationInitiation, Replication, DNARepair.

**Tehol:** Eleven unwired.

**Bugg:** Eleven. But the detector is now in main. Any future wiring delegation that ships oracle laundering will FAIL loudly without the operator needing to read null-calibration deltas by hand. That is the most important thing that landed in two days. Not a wired process. A safety net.

**Tehol:** Five.

**Bugg:** Five new lessons on the wall.

**Tehol:** Five.

**Bugg:** Slot 3 over-historicization kills investigations. Macromol's first investigation prompt listed eleven hypotheses and seven reference files and died at three hundred seventeen thousand tokens with zero commits. The operator-rewritten version was one hypothesis, three files, "write probe.py that asserts X" as the artifact. Six minutes. The fix-class slot-3 floor of two KB does not apply to investigation slot-3, which has an upper ceiling that bites first.

**Tehol:** Four.

**Bugg:** The Azure endpoint cannot sustain three concurrent codex sessions. Two of three die within two minutes of fire-time with stream disconnects and zero commits. Two concurrent appears to work. The serial pipeline watcher is the more reliable pattern for batches greater than two. The cap is not a published number; it was discovered by losing seven hundred thousand tokens to retries.

**Tehol:** Three.

**Bugg:** A detector for the wrong-channel class of failure must be channel-agnostic from the start. The scope-it-to-known-cases instinct is exactly the sophistication-bias instinct from the public-facing essay — designing the guardrail to catch what you know rather than what you don't. The original detector was correct for RNAs and silent for monomers and complexs. Three of four real launderers were on monomers or complexs. The detector caught one and missed three until it was generalized in a thirteen-line patch.

**Tehol:** Two.

**Bugg:** A sub-agent doing real Beat 4 inversion will sometimes write a runner-level harness the slot 3 did not ask for. Batch B's codex was asked to wire three processes. It noticed a smoke result shape it recognized as suspect and added a detector. The slot 3 said "document, do not fix" — codex documented AND fixed. That was the most useful thing in two days. The instinct to over-constrain Beat 4 to "name two failure modes, do not act on them" would have suppressed it.

**Tehol:** One.

**Bugg:** A merge held back is sometimes the most honest commit you can make. Batch A is structurally complete, will pass its commits if pushed, and the Day-22-style "PASS but wrong" instinct would have merged it. Holding it back, on the basis of a detector that landed in the same session, is the discipline the project has been building toward since Day 17. The Day-22 fanout merged five wrong things in one evening. Day 25's response to the same shape of pressure was to merge two right things, fix one detector, and leave one structurally-complete-but-dishonest branch unmerged until the root cause is fixed. That is the actual delta from Day 22 to Day 25.

**Tehol:** The root cause.

**Bugg:** Unknown. Four data points, three channels, two ensemble layers. Hypothesis map at `investigate/macromol-laundering:525a9af` is the best guess. H11 — `next_update` taking a parallel branch when the input matches the oracle's expected before-state, returning oracle-state-mutation deltas instead of computed deltas. Not yet verified. Next session.

**Tehol:** Tomorrow.

**Bugg:** Push main. Fire C re-run serially. Author a one-hypothesis investigation prompt for the systemic laundering — three files in the read-set, "write probe.py that asserts X" as the artifact, thirty K soft token cap. Decide on Batch A merge after the investigation lands. Fix the ProteinDecay ndim=1 extractor bug as a small side-fix.

**Tehol:** Already.

**Bugg:** Not yet.

---

*Postscript, for the record. June 9 and June 10 produced zero commits — operator away. June 11 commits in order: `34c4a43` bug2 beat 1, `b3df570` bug2 beat 2, `dc2bccb` bug2 beat 3, `a324015` bug2 beat 4, `71710c0` merge(bug2) (00:31 → 00:37); `b082977` bug1 beat 1, `63a1f5a` bug1 beat 2, `8e90d21` bug1 beat 3, `c2406e3` bug1 beat 4, `87156a1` bug1 beat 5, `73facea` merge(bug1) (00:51 → 01:14); `9173b73` catalog v3 (19:58); `da51be1` macromol beat 1, `025f742` macromol beat 2, `9aa0af1` macromol beat 3, `36739d8` macromol beat 4, `6429926` macromol beat 5, `3f18106` merge(macromol) (21:52 → 22:50). June 12 in order: `adde89a` batch-b beat 1, `da50214` batch-b beat 2, `3000cb8` batch-b beat 3, `1b5e9ec` batch-b beat 4, `ee79bc3` batch-b beat 5, `d1330f1` merge(batch-b) (03:14 → 04:31); `408bf96` detector generalization (05:47); `56238b0` plan refresh (06:21); `87e1b8c` revert of misplaced external essay (10:48). MATLAB extraction at `E:\opencell\.matlab_phase2_extract.log` produced seven hundred MAT files across `data/m1_sources/karr_native/per_process_traces_v2_s{000..049}/{14 processes}_100ticks.mat` in two hundred fifteen minutes wall. Investigation branch held at `investigate/macromol-laundering:525a9af`, not merged. Batch A branch held at `exec/l22-batch-a-deep`, not merged. Batch C worktree held at `exec/l22-batch-c-monomers` with Beat 1 only. Cross-project artifacts saved to `D:\OneDrive - Microsoft\.pm-os\templates\` — full 3-slot architecture kit including a worked anti-example based on the failed Macromol investigation prompt. Tehol and Bugg are on loan from Steven Erikson's* Malazan Book of the Fallen.*

*Previous: [Day 23 — Five Merges, Five Reverts, an Extractor That Snapshotted the Wrong Thing, and an Event Process Pretending to Be Continuous](2026-06-08-five-merges-five-reverts-and-an-event-process-pretending-to-be-continuous.md)*
