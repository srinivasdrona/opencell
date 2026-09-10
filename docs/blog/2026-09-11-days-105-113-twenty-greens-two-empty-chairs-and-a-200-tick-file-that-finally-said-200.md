---
title: "Days 105-113: Twenty Greens, Two Empty Chairs, and a 200-Tick File That Finally Said 200"
date: 2026-09-11
authors: [sdrona]
tags: [opencell, L2.1, L2.2, matlab, rng, evidence, dna-supercoiling, replication-initiation]
---

**Tehol:** Bugg. Say the number.

**Bugg:** Twenty.

**Tehol:** Green.

**Bugg:** Twenty PASS. Zero FAIL. Two MISSING_EVIDENCE.

**Tehol:** You have learned not to omit the last part.

**Bugg:** The last part is usually where the project lives, sir.

---

**Tehol:** Last time MATLAB had returned, ProteinProcessingII was the only
new green that survived review, DNA damage had discovered negative zero,
DNA supercoiling was off by one linking number, ReplicationInitiation was
failing at tick nine, and the division extractors were measuring time in
geological eras.

**Bugg:** That is an accurate summary.

**Tehol:** And now.

**Bugg:** The final L2.1 active-window manifest is eleven of eleven green.
The L2.2 distributional board is twenty PASS, zero FAIL and two missing.
Both are mechanically verified on published `main`.

**Tehol:** How long were we stuck.

**Bugg:** Long enough that "three months" stopped sounding rhetorical.

**Tehol:** What changed.

**Bugg:** We stopped treating each red row as one bug.

**Tehol:** It was several bugs.

**Bugg:** Usually arranged in layers. Source semantics, hidden state, random
stream ownership, trace identity, evidence provenance, and then the gate
itself.

**Tehol:** And occasionally the filename.

**Bugg:** Especially the filename.

---

**Tehol:** L2.1 first.

**Bugg:** The remaining active-window processes closed one by one:
DNADamage, ChromosomeCondensation, ChromosomeSegregation, Cytokinesis,
HostInteraction, ReplicationInitiation and TranscriptionalRegulation.

**Tehol:** That list is longer than the number of remaining rows in the last
post.

**Bugg:** Because some rows were promoted, rejected, corrected and promoted
again. The final manifest contains the eleven processes for which an active
window is the applicable exact-replay authority. All eleven are now
`EXISTING_WINDOW_PASS`.

**Tehol:** Exact means.

**Bugg:** The OpenCell process receives the captured Karr before-state and
must reproduce the after-state under the declared replay contract. No
"biologically close." No tolerance calibrated from the answer. No silent
skip because a local oracle file is absent.

**Tehol:** ReplicationInitiation.

**Bugg:** Two hundred of two hundred ticks pass when the recorded input RNG
ledger is restored.

**Tehol:** And without the ledger.

**Bugg:** It diverges.

**Tehol:** Good.

**Bugg:** Good?

**Tehol:** We used to publish the nicer sentence.

**Bugg:** The nicer sentence was false. The current evidence says exactly
which replay contract passes and which diagnostic does not.

**Tehol:** Eleven of eleven.

**Bugg:** Eleven of eleven.

---

**Tehol:** DNA supercoiling.

**Bugg:** The one-linking-number discrepancy was not the last discrepancy.

**Tehol:** Naturally.

**Bugg:** We ported MATLAB's region normalization more literally:
`excludeRegions`, `joinSplitRegions`, and the origin-crossing
`joinSplitOverOriCRegions`. We separated chromosome-owned random draws from
process-owned draws. We restored hidden superhelical density where the
visible integer linking number had lost information.

**Tehol:** Then the old gate passed.

**Bugg:** Which was another problem.

**Tehol:** Because the gate could reject too few events but not too many.

**Bugg:** Correct. A sparse process can be wrong in both directions. The
accepted gate is two-sided and looks at three support axes rather than
letting a small magnitude distance declare victory.

**Tehol:** Numbers.

**Bugg:** Across two hundred seeds and one hundred ticks:

- pooled non-zero ticks: OpenCell 64, Karr 65;
- active seeds: 58 and 58;
- clustered seeds: 6 and 7.

All three axes are balanced under the preregistered rule. The process RNG
ledger reports zero boundary over-consumption and zero under-consumption
across twenty thousand covered ticks.

**Tehol:** So green.

**Bugg:** Then rejected during integration.

**Tehol:** Why.

**Bugg:** A generic evidence sweep had overwritten the accepted
`dnas_two_sided_sparse_gate` result with the ordinary
`per_component_scaled` result.

**Tehol:** Same verdict.

**Bugg:** Wrong methodology. We added a regression that checks the actual
aggregation, not merely the word `PASS`.

**Tehol:** Then green.

**Bugg:** Then rejected again.

**Tehol:** Bugg.

**Bugg:** The candidate worktree had hashed a freshly generated helper with
CRLF line endings. The merge worktree contained Git-normalized LF bytes.
Same Python program, different raw hash.

**Tehol:** So the biology was correct and Windows objected to the newline.

**Bugg:** We made the exception process-specific and fail-closed. Only the
DNAS helper normalizes CRLF to LF for provenance. Every other registered
dependency remains raw-byte exact.

**Tehol:** Reviewer.

**Bugg:** Accepted.

**Tehol:** Board.

**Bugg:** Nineteen PASS. ReplicationInitiation was the only FAIL. Cytokinesis
and FtsZPolymerization were still missing.

---

**Tehol:** The filename.

**Bugg:** ReplicationInitiation's catalog requires two hundred ticks. The
shared loader had always searched for
`ReplicationInitiation_100ticks.mat`.

**Tehol:** But we had two hundred-tick data.

**Bugg:** Stored under the hundred-tick name.

**Tehol:** That sentence should make a test fail.

**Bugg:** It did not. The file's internal metadata said 200, and the runner
silently used it.

**Tehol:** So we fixed the loader.

**Bugg:** The first fix changed universally hashed shared files and made
sixteen unrelated green rows stale.

**Tehol:** We fixed it without changing the loader.

**Bugg:** The second fix left the files mislabeled and required temporarily
moving the canonical L2.1 seed-zero trace out of the way.

**Tehol:** Rejected.

**Bugg:** Correctly.

**Tehol:** Third attempt.

**Bugg:** Fifty genuine traces now rest permanently at:

`per_process_traces_v2_sNNN/ReplicationInitiation_200ticks.mat`

for seeds zero through forty-nine. The canonical L2.1 trace remains at its
separate unsuffixed `ReplicationInitiation_100ticks.mat` path.

**Tehol:** No swap.

**Bugg:** No archive. No rename ritual. No seed-zero exception.

**Tehol:** And the contract.

**Bugg:** Before evaluation, the official ReplicationInitiation entrypoint
requires:

`requested M == catalog M == filename ticks == metadata n_ticks == every channel's tick dimension`

including chromosome.

**Tehol:** Why does "requested M" need its own check.

**Bugg:** Because the generic runner can slice a two hundred-tick oracle down
to a requested one hundred ticks. Without the entrypoint, a user could ask
the wrong question and receive a valid-looking answer.

**Tehol:** Test.

**Bugg:** Asking the official ReplicationInitiation path for one hundred
ticks now exits before opening the oracle. Asking for two hundred runs the
real gate.

**Tehol:** Result.

**Bugg:** Fifty seeds, two hundred ticks, both gated channels classified
`SEED_NOISE`, zero warnings. PASS.

**Tehol:** Reviewer.

**Bugg:** Accepted. Then you found two checks the reviewer had missed. We
added them. Then a new reviewer accepted the corrected version.

**Tehol:** I am not a reviewer.

**Bugg:** You rejected two green boards.

**Tehol:** I am a product manager with trust issues.

**Bugg:** In this repository that is functionally equivalent.

---

## Honest scoreboard

| Gate | Published authoritative status |
|---|---|
| **L2.1 active-window manifest** | **11 / 11 EXISTING_WINDOW_PASS** |
| **L2.2** | **20 PASS / 0 FAIL / 2 MISSING_EVIDENCE**, integrity OK |
| **L2.4** | PASS, 100 ticks x 4 seeds |
| **Remaining L2.2 rows** | Cytokinesis and FtsZPolymerization |

---

**Tehol:** Twenty green. Why are we not done.

**Bugg:** The last two processes share a dependency: the whole-cell
trajectory must reach division before either event window can be captured.

**Tehol:** We were extracting them separately.

**Bugg:** We now capture both from one simulation pass. Cytokinesis gets a
five-thousand-tick window; FtsZPolymerization gets two hundred ticks at the
same division anchor.

**Tehol:** And seeds that do not divide.

**Bugg:** They are right-censored at one hundred thousand ticks. They do not
count as completed windows, and they do not disappear from the attempted
seed sequence.

**Tehol:** Current count.

**Bugg:** Through the contiguous prefix ending at seed thirteen: twelve
completed, two right-censored. No duplicate trace hashes, no source-hash
mismatches, no invalid censors. Seed fourteen is running.

**Tehol:** Required.

**Bugg:** Fifty completed windows.

**Tehol:** So twenty greens and two empty chairs.

**Bugg:** The chairs are not green. They are not red. They are waiting for
the cell to divide.

---

**Tehol:** What did these nine days accomplish.

**Bugg:** The final exact-replay manifest closed. DNA supercoiling survived a
source audit, a gate audit, a provenance audit and a line-ending audit.
ReplicationInitiation survived two rejected designs before its two hundred-
tick files were allowed to say two hundred. The distributional board lost
its last FAIL.

**Tehol:** And the lesson.

**Bugg:** A green result is not one thing. The source can be wrong, the RNG
can be wrong, the trace can be mislabeled, the evaluator can ask a one-sided
question, the provenance can bind the wrong bytes, and the integration can
invalidate everyone else's evidence.

**Tehol:** That is not a lesson. That is a threat model.

**Bugg:** It is both.

**Tehol:** Next post.

**Bugg:** Not at twenty-one.

**Tehol:** No.

**Bugg:** At twenty-two PASS, zero FAIL, zero missing.

**Tehol:** When the two empty chairs are occupied.

**Bugg:** When the cell finally divides fifty times under the contract and
both gates survive review.

**Tehol:** Publish this one.

**Bugg:** The version where the filename tells the truth.

**Tehol:** Keep that line.

---

*This is the OpenCell dev blog. The repo is
[github.com/srinivasdrona/opencell](https://github.com/srinivasdrona/opencell).
The next update arrives at L2.2 22 PASS / 0 FAIL / 0 MISSING_EVIDENCE.*
