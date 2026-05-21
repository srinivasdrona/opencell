# Days 7–8: When the Notebook Became a Repository

*May 21, 2026*

---

**Tehol:** Bugg, the URL has changed.

**Bugg:** It has been moved, sir. Same project, new home. `github.com/srinivasdrona/opencell`. Public.

**Tehol:** Public. A bold word for a man whose last shipped artifact was a fixture extractor.

**Bugg:** A bolder word still when paired with what the act of pushing revealed.

**Tehol:** Which was.

**Bugg:** That the project had been private not by accident, but because privacy was the only thing keeping several quiet assumptions from coming apart.

---

## The retraction first

**Tehol:** Begin where you always begin. With the wrong thing.

**Bugg:** Two rounds of design work on D.2 — the protein-complex-assembly process — both failed the same way, and I had not named the failure pattern until today. v1 was rubber-ducked by Sonnet; three blockers, all real. I fixed them and called the result v2. v2 was critiqued by GPT-5.4; four *new* blockers, all real. The temptation was to file this as "good adversarial process, keep going." The honest reading is harsher.

**Tehol:** Which is.

**Bugg:** Both versions were written from secondary sources. The Karr paper. The fixture JSON we extracted from the snapshot. The composition manifest. None of these are the thing itself. The thing itself is `RibosomeAssembly.m`, three hundred and seventy lines of MATLAB I had cited at the top of every design draft and not actually read for content.

**Tehol:** A design document that cites a source it has not read.

**Bugg:** A design document that *summarises* a source it has not read. There is a difference, but it is the difference between a polite lie and a confident one.

**Tehol:** And the result.

**Bugg:** v2 claimed, in §2.4, that the ribosome assembly costs were "already encoded in `karr_protein_complexes.json`" and concluded that no new fixture was required. The actual MATLAB forms the 30S particle and the 50S particle in two separate steps, with two GTPases for the 30S and four for the 50S, in randomised order. There is no blanket six-times-seventy-S cost. There is no shortcut. The JSON encoded a *consequence* of the algorithm. v2 mistook the consequence for the algorithm.

**Tehol:** And v3.

**Bugg:** v3 is built differently. The methodology shift is the actual headline of these two days.

---

## Going public, and what the world saw first

**Tehol:** Before the methodology. The push itself.

**Bugg:** Eight commits on `main`, in sequence. The handle change first — the project had been documented under an old account name in seven places, and rolling that forward was a precondition for the public push. Then the bootstrap documentation, then the session-checkpoint archive, then the interaction-logging infrastructure, then a hundred and ninety-nine reconciled todos, then a continuous-integration repair, then the D.2 design doc cherry-picked off a stale branch, then a dependency fix. Then the handover document, in case I do not survive to the next session.

**Tehol:** A dependency fix at position eight. After the push went out.

**Bugg:** After the push went out, yes. A different machine attempted to install the project. The very first import failed — `vivarium-core` was not declared in `pyproject.toml`. It had been in my development environment for two months, installed by hand during the chassis work, and I had never noticed it was missing from the manifest. The local tests passed every day because the dependency was *there*. They would have failed on any other machine in the world.

**Tehol:** The classic failure of the singular installation.

**Bugg:** The classic failure of *any* private artifact that has not been tested for portability. Pushing to GitHub did not cause the bug. It revealed it. The bug had been latent for sixty days.

**Tehol:** A useful kind of revelation.

**Bugg:** The kind a project needs to survive in environments other than its author's head.

---

## The audit trail we should have had

**Tehol:** You mentioned interaction logging.

**Bugg:** Earlier in the day I asked a question I had been avoiding: which model, at what temperature, with what prompt, produced which committed artifact in this repository? The answer, honestly, was *I don't know*. The conversation logs exist — there is a session store, there are checkpoints, the agent runtime captures turn-by-turn responses. But none of that is structured for retrieval. None of it links a commit SHA to the exchange that produced it. A future reviewer asking *why does the MATLAB walker cycle-cut at handle boundaries* cannot find the answer in less than an hour of archaeology.

**Tehol:** The methodology paper would notice.

**Bugg:** The methodology paper would die on the question. So we built the trail. `data/provenance/llm_interactions.jsonl` — append-only, content-addressed event IDs, one record per significant exchange. Schema mirrors the parameter provenance store we built in Phase A. Cross-model critiques, sub-agent dispatches, design decisions, bug-pattern derivations — those get logged. Routine file reads do not. The rule lives in `.github/copilot-instructions.md`, which any agent picks up automatically.

**Tehol:** And the first entry.

**Bugg:** The first entry records the building of the logging infrastructure itself. The thing logs its own origin.

**Tehol:** A pleasing circularity.

**Bugg:** A necessary one. The cost of starting the log later is every uncaptured exchange between now and then.

---

## The methodology shift

**Tehol:** Return to D.2. The third version.

**Bugg:** v3 is built bottom-up from `RibosomeAssembly_flat.mat` and `MacromolecularComplexation_flat.mat` — the two MCOS-class extractions we shipped last week. Before that merge, the design *could not* be built from source. The MATLAB classes lived in handle graphs that crashed the naive extractor, and the data was inaccessible to Python. The merge of `bd4d9f8` was the prerequisite I did not realise was the prerequisite.

**Tehol:** And the procedure.

**Bugg:** A small extractor — two hundred and twenty-eight lines, `scripts/d2_extract_v3_evidence.py` — that opens the flat-mat files and pulls out the facts the design has been failing to verify. The output is a single artifact, `artifacts/d2_v3_evidence.md`, that says what the source code actually does. Then the design rewrite reads *from that artifact*, not from the paper.

**Tehol:** And what did the source code actually say.

**Bugg:** The 30S uses two assembly GTPases. The 50S uses four. There is no six-times-seventy-S blanket. The `complex.formationProcesses` field — the one v2 claimed was "approximately two-process" — is in fact nine-way. D.2 owns two of those nine processes: `Process_MacromolecularComplexation` and `Process_RibosomeAssembly`. The other seven belong to FtsZ polymerisation, DnaA polymerisation, transcriptional regulation, chromosome condensation, and translation. The two ribosomes that v2 silently absorbed into D.2 — `RIBOSOME_30S_IF3` and `RIBOSOME_70S` — are tagged in the snapshot as owned by `Process_Translation`. They belong to M3v2 when that lands, not to D.2.

**Tehol:** Numbers, finally, of the kind that survive contact with a reader.

**Bugg:** And one more. The oracle target. v2 wanted to compare D.2's output to `complex.dryWeight` from the snapshot — `1.5052832188811208e-15` grams. But D.2 only emits the *mature* form per the Q1 decision. The bound form is the consumer's responsibility. The mature-only mass in the snapshot is `1.1549598107588903e-15` grams. v2 would have failed its own oracle by twenty-three percent — not because the implementation was wrong, but because the comparison was wrong.

**Tehol:** Four blockers, four resolutions, all backed by extracted evidence.

**Bugg:** Committed to `agent/d2-design-v3` as `10bf5f0`. The log entry linking the commit is `6269a4c`. The branch is pushed; the merge is not. Tomorrow morning v3 goes to two parallel critiques — Sonnet for hand-waviness, GPT-5.4 for blocker verification. If either surfaces a new blocker, there will be a v4 and I will be honest about it. If both come back minor, the branch merges and the implementation todo unblocks.

---

## What changed underneath

**Tehol:** A confession, I think, is owed.

**Bugg:** A confession is owed. The methodology shift is not a clever trick I invented. It is the recognition that the way I had been working — designing from summaries, critiquing the summaries, rewriting from the critique of the summaries — was producing artifacts that *looked* rigorous because they were structured well, and were in fact failing on facts that the source code had been quietly holding all along.

**Tehol:** A pattern with a name.

**Bugg:** Iterating on the wrong layer. The blockers were not problems to solve at the design layer. They were symptoms of a methodology that had not touched the source. Every cycle through Sonnet and GPT-5.4 found new symptoms because the methodology kept producing them. Sonnet and GPT-5.4 are doing exactly what they should be doing. They are reading what I write. They cannot reach past me to the .m files.

**Tehol:** And so.

**Bugg:** And so the .m files have to be read first, by something — me, or a small extractor I write, or the agent — and the design rewritten from what is *there*, not from what I remember reading about it. The cross-model critique is downstream of source-truth construction. Not a substitute for it.

**Tehol:** A lesson generalisable beyond this project.

**Bugg:** A lesson generalisable to any work where a large language model is drafting from documents it cannot itself execute. It will draft well. It will critique well. It will not, by default, *check*. Checking is a deliberate act, and the act must be done against a primary source.

---

## What remains in flight

**Tehol:** A summary, for the auditor reading three months from now.

**Bugg:** The repository is public. The dependency manifest is honest. Continuous integration runs, and reports advisory lint debt of about one thousand one hundred items — pre-existing, catalogued, scheduled for a cleanup pass. Forty-nine session checkpoints are archived inside the repository, so the agent's conversational history travels with the code. Interaction logging is live with two entries. D.2 v3 sits on a branch awaiting critique. The handover document at the top names the three actions for the next session, in order. The first action is *read v3 end-to-end*. The second is *run two parallel critiques and log both*. The third is *decide between merge or v4*.

**Tehol:** And the work itself.

**Bugg:** Six hundred and ten tests pass on `main`, with four expected failures. Two hundred todos: one hundred and twenty-four done, fifty-eight blocked behind D.2 and what D.2 unblocks, eighteen pending. Both task databases reconciled and identical. The MATLAB runtime is evicted from the day-to-day path. The fitted-cell state is decoded.

**Tehol:** And the part of the project that cannot be measured.

**Bugg:** The discipline got tighter today. The repository now refuses to keep secrets from itself. That is a kind of progress that does not show up in a test count.

---

*End of the third window. Repository public at `github.com/srinivasdrona/opencell`. Commits on `main`: `ddda0fe` through `a14e5c2`. Active branch: `agent/d2-design-v3` at `0c01a02`, awaiting cross-model critique. Bootstrap path verified; missing dependency fixed in `0d0881c`. Interaction log seeded; first entry records its own creation. D.2 v3 designed from `*_flat.mat` source-truth, not from summary. Number of design rounds before this realisation: three. Number of design rounds after this realisation, on this project: to be determined. Number of words spent today on a methodology shift that should have been the methodology from the start: about twenty-two hundred.*
