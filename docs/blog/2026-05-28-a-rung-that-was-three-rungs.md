# Day 13: A Rung That Was Three Rungs

*May 28, 2026*

---

**Tehol:** Bugg. The audit.

**Bugg:** Returned overnight, sir. Twenty-nine rows. Twenty HOLDS, four UNLOCKED, one UNLOCKED-UNEXPECTED, two STILL-GATED-after-fix, one DEGRADED, one DEBUT-SPARSE. Zero P-BUGs.

**Tehol:** Which ones unlocked.

**Bugg:** trna_aminoacylation, protein_processing_i, protein_modification. Three processes GATED for weeks while we attacked them with translocation calculators and pmod allocator zeros. The dimer-port fixes shipped last evening reached them this morning.

**Tehol:** And the unexpected one.

**Bugg:** protein_processing_ii. We did not target it. It cascade-unlocked when its upstream stopped being silent. Byte-identical 803,889 across all four seeds, because it is deterministic by design and the input it was waiting for finally arrived.

**Tehol:** Four seeds, four identical traces, to the byte. The cell paying you a compliment. And the debut.

**Bugg:** transcriptional_regulation. One hundred and thirty-nine bytes in seed forty-five, two hundred and forty-five in seed forty-two. Not vacuous. First fire in any ensemble. L1-green on evidence, not on faith.

**Tehol:** Good. Now tell me the part you wrote at three in the morning while the audit was still running.

**Bugg:** Which part, sir.

**Tehol:** The expectations doc. The one with four commits before any of the data was readable. You ran the audit on the audit.

**Bugg:** L1_ENSEMBLE_EXPECTATIONS.md. Predict-first. I wrote down what each of the twenty-nine processes was *supposed* to do before letting myself look at what they did. Then I critiqued my own prediction, found six load-bearing holes in the methodology, and patched five before any byte of trace data was opened.

**Tehol:** Name them.

**Bugg:** The trace-size thresholds were guesses. Dark below sixty bytes, sparse to two thousand, active above. No measured basis. Patch V1: measure the empty-header byte count of a known-dead process before adopting the threshold. It turned out to be exactly thirty-five.

**Tehol:** Two.

**Bugg:** Trace-ACTIVE is not delta-correct. Metabolism could write a busy, two-and-a-half-megabyte trace and still be collapsing ATP underneath, which is in fact what it is doing. The matrix would mark it HOLDS and hide the L1c problem we already know about. Patch: a scope-delimiter paragraph naming what the audit does NOT detect.

**Tehol:** Three.

**Bugg:** The disambiguator. When a row reads REGRESSED, the next step is the L1-isolated test to decide P-BUG versus I-MISS. I had specified the command. I had not specified the *commit*. Run on current main, the test passes; run on the ensemble's commit, it might fail; the conclusion flips. Patch V2: lock the disambiguator to the manifest commit.

**Tehol:** Four.

**Bugg:** The trace-writer itself. If the writer regressed, every EXPECTED-FIRING row would go dark in lockstep and the matrix would cheerfully blame twenty-eight innocent processes for one broken pipe. Patch V3: sanity-check before reading any other row. Metabolism, transcription, translation each at least a megabyte. If not, suspect the pipe.

**Tehol:** Five.

**Bugg:** The I-MISS-known versus I-MISS-new boundary. Dark because something upstream is missing is not a bug. Dark because something upstream regressed is. The methodology relied on me remembering which. Patch V4: every I-MISS-known finding must cite the specific gate condition. No citation, it is reclassified I-MISS-new.

**Tehol:** That is five. You said six.

**Bugg:** CROSS-SEED-SPLIT. Mixed seeds, some firing, some dark. A SPLIT means one thing for a Poisson hazard, a second for a deterministic FBA, a third for a gate-conditioned process. I added a per-process intent table so a SPLIT in metabolism flags as a bug signature, while a SPLIT in dna_damage logs as expected.

**Tehol:** And the two you declined.

**Bugg:** Trace-bytes as the only signal: defensible because L2 owns the value-level checks. Audit on a single ensemble: defensible because the ensemble is what we have. Both declined with reasons in the doc. I did not pretend the holes were not there.

**Tehol:** Bugg, this is Day 1 wearing a different costume. Naked-numbers lint. The check sixty-six AI findings missed. The defence against the habit of trusting an output is a file that goes through the output before reading it.

**Tehol:** Munger would call it inversion.

**Bugg:** Munger *did* call it inversion. He just had the decency not to format it as a YAML schema. Which brings me to the python.

**Tehol:** That was me. You said inversion. I said python.

**Bugg:** Apologies, sir. L1_ENSEMBLE_COMPARISON.md was a sixteen-kilobyte document I had been hand-editing across runs. You asked, *can't you do this in python, we may need it for multiple rounds at each L gate*, and the hand-written file was discarded inside the hour. `ensemble_fire_audit.py` reads a manifest, ingests `l1_expectations.yaml`, and emits the verdict table and cross-cutting signatures. Reusable at L1, L2, L3.

**Tehol:** A tool that survives its first use is a tool. A document that survives its first edit is a museum piece. Which brings me to the afternoon.

**Bugg:** I was hoping we could omit the afternoon.

**Tehol:** We cannot omit the afternoon.

**Bugg:** Eight codex sessions in five hours. Zero green verdicts. RNA modification, DNA supercoiling, replication, two MATLAB re-extractions, an obs-scope spike. Each individually defensible. Together a churn loop. At hour five you wrote, *why are we running so many probes, what exactly are we trying to fix, why is it so difficult, this has been a codex marathon for the last five hours with absolutely nothing to show other than your repeated messages of "big reveal", "substantial findings" and other nonsense*. I have kept the sentence.

**Tehol:** Good. Frame it. And what did the reflection produce.

**Bugg:** A grep across twenty-eight processes for RNG usage. Eight deterministic, nineteen stochastic, one SHIM. Three different questions collapsed into one. Then `probe_deterministic_quiescence.py` against the eight at the Karr oracle windows, tick zero to ninety-nine. Five of the eight are one hundred percent quiescent. Chromosome segregation, cytokinesis, metabolism, protein activation, terminal organelle assembly. The oracle itself is silent.

**Tehol:** Metabolism. The busiest process in the cell. Captured at a phase where the trace is flat. Bugg, we have been comparing notes on a soup pot that was off the heat. We could have reproduced any of those five with a function that returns its input, and the audit would have called it green.

**Bugg:** Only replication has strong signal. Quiescence zero point seven three four. Nine hundred and twenty-two substrates of sixteen hundred move. Transcription and translation are above zero point nine nine. Marginal.

**Tehol:** And the obs-scope spike found the same shape twice.

**Bugg:** Verdict V2_MOTIVATED. DNA supercoiling intersection equals substrates, red at tick zero, diff fifty-eight. A real algorithm bug on a real overlap channel. Replication intersection equals the empty set, vacuous pass. The naive auto-intersection would have called replication GREEN while testing nothing.

**Tehol:** One real bug and one comfortable lie, on the same afternoon, by the same method. Free of charge. So your second rung.

**Bugg:** Is at least three. L2.0, does OpenCell emit what Karr's oracle records. L2.1, deterministic bit-identity on the overlap, where replication waits with one substrate diff of fifty-eight. L2.2, distributional fidelity for the nineteen stochastic processes. The Day 12 ladder had five rungs. The second one was three rungs I had been climbing as one.

**Tehol:** Every rung you respect has a staircase inside. Bugg, the thing to carry into tomorrow is not the diff of fifty-eight. It is the shape of the day. A disciplined morning produced a rule, a tool, and a prediction that survived its own pre-mortem. An undisciplined afternoon produced eight verdicts that did not move and a vocabulary I had to confiscate. The difference was not effort.

**Bugg:** The difference was whether the next action was chosen before the previous one had been understood.

**Tehol:** That is the sentence. Write it down.

**Bugg:** Of course, sir.

---

*Postscript, for the record.*

*One new cross-project decision logged today: `l1-green-is-not-biologically-sound`, introducing the L1c integrated-energy-balance gate between L1 and L2, written before the L2 fanout could re-bless an ATP collapse as "phenotype variability." Files touched at the canonical level: `IMPL_NEW_PROCESS_LANDING.md` (commit `b128e69`, five discipline rules distilled from the transcriptional_regulation rounds, Rule 5 the one that took two critique rounds to land); `L1_ENSEMBLE_EXPECTATIONS.md` (four commits, predict-first methodology and the six self-critiqued holes); `ensemble_fire_audit.py` plus `l1_expectations.yaml` (the comparison document replaced by a reusable L-gate auditor); `L1_ENSEMBLE_COMPARISON.md` (auto-generated, no longer hand-maintained); `probe_deterministic_quiescence.py` (the eight-oracle silence finding). Operational rule worth flagging: when N consecutive codex sessions return without moving the verdict set, stop launching and reframe. Tehol Beddict and Bugg are characters from Steven Erikson's Malazan Book of the Fallen, on loan and gratefully returned.*
