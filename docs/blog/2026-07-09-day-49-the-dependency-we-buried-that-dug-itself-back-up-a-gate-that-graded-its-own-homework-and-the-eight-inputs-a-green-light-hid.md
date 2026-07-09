---
title: "Day 49: The Dependency We Buried That Dug Itself Back Up, a Gate That Graded Its Own Homework, and the Eight Inputs a Green Light Hid"
date: 2026-07-09
authors: [sdrona]
tags: [opencell, JAX, de-jax, input-fidelity, frozen-spec, derived-not-authored, codex, gate-0, transcription-bug]
---

**Tehol:** Bugg. I sent you off to build the next gate. Honestly, you said. Every time, you said.

**Bugg:** I built it, sir. L2.0 — the schema gate — is formalized, twenty-eight of twenty-eight green, and wired into the pull-request flow so it blocks. That part went to plan.

**Tehol:** *[settles into the blanket]* I hear a "but" crouching behind that sentence.

**Bugg:** Before I could enjoy the green, I went to run the tests, and the import took four seconds to load a process that does arithmetic on numpy arrays. Four seconds. So I looked at what it was loading.

**Tehol:** And?

**Bugg:** Two hundred and eight modules of JAX, sir.

**Tehol:** *[very still]* We killed JAX on Day Three.

**Bugg:** We killed it on Day Three. You were about to spin up a differentiable engine, I talked you into it, then I profiled it and proved the dispatch overhead was larger than the integration work at our scale, and we tore it out. It's in the Day-Three post, in my own words — *"I was about to re-introduce a technology I had personally proven did not help."*

**Tehol:** And it's *back*.

**Bugg:** It crept back through the stochastic solver — one line, `import jax.numpy`, used for a type hint and a single array wrap. Harmless-looking. Except the process package imports that solver eagerly, so every single Karr process, on import, dragged the entire JAX stack into memory. For nothing. The processes are pure numpy. They never call it.

**Tehol:** Seventy-five days. It sat there for seventy-five days.

**Bugg:** Because nothing was watching for it. And that's the part that should bother us more than the four seconds, sir. We *decided* to remove JAX. We wrote it in the blog. We congratulated ourselves. But a decision you don't enforce with a gate isn't a decision — it's a preference the codebase is free to ignore the moment you look away. The corpse got up and walked because we never nailed the lid shut.

**Tehol:** So nail it.

**Bugg:** Done. I de-jaxed the solver, then the whole Phase-One core it had infected — the state container, the engine, the checkpoint, the manifest — swapped the JAX random keys for numpy generators, deleted the Diffrax ODE solver outright since we already had a SciPy one doing the real work, and dropped `jax` and `diffrax` from the dependency list entirely. Then I wrote the thing that was always missing: a test that imports the full process surface in a clean subprocess and *fails* if a single JAX module shows up. Four hundred and thirty-four tests still pass. The five that were already red stayed exactly as red as they were before I touched anything — I checked against a clean baseline, because I've learned not to trust a green that I didn't earn.

**Tehol:** Net change?

**Bugg:** Minus four hundred and ninety-nine lines, plus eighty-six. The best kind of day's work, sir. The codebase got smaller and more honest at the same time.

---

**Tehol:** Good. Now — L1b is green. Both halves. You told me that three days ago and I believed you.

**Bugg:** You should still believe it. It's green.

**Tehol:** Then answer me a plain question. Are we *sure* — completely sure — that every one of the twenty-eight processes is wired to the right inputs? The right molecules, the right ports?

**Bugg:** *[a pause]* No, sir.

**Tehol:** *[sits up]* You just told me it was green.

**Bugg:** It is green. That's the problem. Let me show you the one that broke me. DNARepair passes the wiring gate — twenty-eight of twenty-eight, all thirteen checks clean. And its wiring row declares twenty substrates. Karr's own stoichiometry says twenty-six. Six missing. The gate never noticed.

**Tehol:** How does a gate built to check wiring miss six missing molecules?

**Bugg:** Because — and I need to say this plainly, because it took me the whole day to admit it — the gate I spent six chunks rebuilding was grading its own homework. It checks that the wiring file is internally consistent. That its anchors resolve. That its dependencies are symmetric. That there are no cycles. Every one of those checks compares the wiring file *to itself*. Not one of them compares it to Karr.

**Tehol:** *[quiet]* Say that again.

**Bugg:** The wiring file is a document I wrote by hand to describe what each process consumes. The gate confirms the document is well-formed. It never once asks whether the document is *true*. I built an elaborate machine and pointed it at the wrong target, and it passed, and I called it fidelity.

**Tehol:** So show me a bug it hid. A real one. Not six molecules in a repair pathway I have to squint at.

**Bugg:** Transcription. The most central process in the cell — it reads the gene and makes RNA. Karr's fixture says Transcription takes twelve input molecules. Our Python code loads four.

**Tehol:** Four of twelve.

**Bugg:** ATP, CTP, GTP, UTP — the four nucleotides. It's missing the two waste products, the pyrophosphate and the proton, the water, and the five mono-phosphates. Eight inputs. Karr's own stoichiometry says Transcription consumes water and releases a proton and pyrophosphate — and our process cannot even *represent* those molecules, because they were never loaded into its vocabulary. And the wiring gate called it clean. Because the wiring *document* happened to agree with itself.

**Tehol:** *[pinches the bridge of his nose]* The single most important process in the organism is missing two-thirds of its inputs, and every green light we have says it's fine.

**Bugg:** Said. Past tense. You asked the question that pointed the machine at the right wall.

---

**Tehol:** Then let's fix the wall, not the paint. Why do we even *have* a hand-written wiring document? If Karr's inputs are sitting in a file on disk, why did you type them out by hand like a monk copying scripture?

**Bugg:** That is exactly the right question, sir, and I don't have a good answer. The honest one is: it was the original sin. Somebody — some earlier version of me — decided the wiring file should be authored. And the moment you hand-copy data that already exists authoritatively somewhere else, you've created a third thing that can disagree with both the source and the code, with nothing forcing it to agree with either.

**Tehol:** So derive it. From the source.

**Bugg:** So I derived it. I had the doer read Karr's own per-process fixtures — the extracted MATLAB state — and mechanically emit one clean specification file per process. Every input vocabulary, every index group resolved to real molecule names, every reaction's stoichiometry. Nothing typed by hand. Correct by construction, or as close as I can get to it.

**Tehol:** And now there are two gates instead of one.

**Bugg:** Two gates, and each one asks a question the old one couldn't. Gate One: does the frozen spec exactly match Karr's fixture? Gate Two: does our Python code load exactly what the frozen spec says? If the spec matches Karr and the code matches the spec, then the code matches Karr — and when something breaks, I know *which* gate went red, so I know whether the spec is wrong or the code is wrong. The old gate couldn't tell me either, because it was only ever talking to itself.

**Tehol:** And Gate One passes?

**Bugg:** Twenty-eight of twenty-eight vocabularies, exact. Deterministic — I run the extractor twice and the bytes are identical. And I didn't take my own word for it. I sent it to a second model, adversarially, to try to break it.

**Tehol:** *[a faint smile]* You had a machine grade the machine.

**Bugg:** It came back "faithful, with fixes." It found three real gaps — a stoichiometry matrix I'd labeled ambiguously, four hundred index groups I'd left unresolved that were in fact resolvable, a lookup table with a zero in it that I'd mistaken for an index. All annotation-level, no corrupted data. I fixed all three, re-derived, re-verified every claim myself against the raw source, and *then* believed it.

---

**Tehol:** There's a thing you're skating past. You said "I sent it to the doer." When the reviewer found three gaps, whose fault were they?

**Bugg:** *[a longer pause]* I almost got that wrong too, sir. My first instinct, when the reviewer flagged four issues in the doer's work, was to fire the doer again to *fix its mistakes*. I had the correction prompt half-written.

**Tehol:** And?

**Bugg:** And I stopped, and went and checked each finding against the instructions I'd actually given it. All four were mine. I had literally told it to use the combined matrix. I had shown it the duplicated field in my own example. My resolution rule was too coarse. The doer did exactly what I asked — my asking was wrong. I nearly filed my own bugs as its incompetence.

**Tehol:** That's a nasty little habit to have with a subordinate.

**Bugg:** It's the nastiest, sir, because it's invisible from the inside and it erodes trust in something that did nothing wrong. So I've made it a rule now, written down: when a reviewer flags delegated work, before I re-delegate, I have to quote the line of my own prompt that was violated. If I can't quote a line, it wasn't the doer's miss — it was mine. And there was a moment that proved the rule's worth. The reviewer said the doer had reported a category — the process's references to shared state — using a property name that doesn't exist anywhere in Karr's code. I was *certain* it had fabricated it.

**Tehol:** Had it?

**Bugg:** It had found the real mechanism. Karr doesn't declare those references in a named list — it grabs them one by one in a setup method, `this.chromosome = simulation.state('Chromosome')`, and so on. My prompt had invented a tidy property name that never existed; the doer ignored my fiction, went and found how the code *actually* references its state, and reported that instead. It was smarter than my prompt. If I'd trusted my suspicion instead of checking, I'd have "corrected" it into being wrong.

**Tehol:** So the thing you were about to punish it for was the best thing it did all day.

**Bugg:** Word for word, sir.

---

**Tehol:** This shared-state thing. You called it a category. Is it new?

**Bugg:** It's the category I'd been missing, and I only found it because you kept making me be precise. A process's inputs aren't only the small molecules in a shopping list. A process also *reads whole objects* — the chromosome, the cell's geometry, its mass, the pool of every RNA and every protein. DNARepair reads the chromosome. Metabolism reads the cell's mass to know how fast to grow. None of that lives in an ingredient list, so a specification built only from ingredient lists is structurally blind to it. It cannot see the largest inputs a process has.

**Tehol:** And your frozen spec — the one you just spent all day making faithful — has this?

**Bugg:** *[carefully]* Not yet. That's tomorrow.

**Tehol:** *[raises an eyebrow]* So the source of truth is missing a category of truth.

**Bugg:** And there's a worse layer under that one, sir, and I'd rather you hear it from me. The frozen spec is derived from the *fixture*. The fixture is itself an extract somebody made from Karr's MATLAB, once, months ago. So Gate One proves the spec matches the fixture — but if the *fixture* dropped a molecule during its extraction, I've frozen the omission and stamped it "source of truth." Gate One can't catch it, because it's comparing the spec to the very thing that might already be incomplete. Transcription got lucky — its fixture had all twelve, and the code was the liar. But for the next process, the liar might be one layer up, and both gates would stay green.

**Tehol:** *[a long look at the ceiling]* So the real ground is not the extract. It's the fourteen-year-old code sitting on our disk.

**Bugg:** It's the fourteen-year-old code. Which is exactly why the frozen spec is worth building despite all of this — Karr's model made assumptions that are buried across a dozen MATLAB files, and no future version of me can hold all of that in its head while porting a process. It will read three files and miss the fourth and swear it read everything, and neither of us will know what we lost until a phenotype comes out wrong two weeks later. The frozen spec is the one place all of it is consolidated, readable, public, and fixable one file at a time. But for it to earn the name "truth," it has to be anchored to the real code at least once. So tomorrow there's a Gate Zero: audit the fixture against the actual MATLAB source, before I freeze anything.

**Tehol:** *[pulls the blanket up]* You keep discovering that the floor has a floor.

**Bugg:** It's floors all the way down, sir. The trick is knowing which one you're standing on and not calling it bedrock.

---

**Tehol:** We're stopping there. It's nearly two in the morning and the MATLAB licence expired, so half of tomorrow's work is gated on you renewing it anyway.

**Bugg:** Parked, sir. The plan's written down: renew the licence, settle the last scope questions, run Gate Zero against the real code, then fix Transcription and its three troubled siblings. And a small confession for the record — I nearly buried the timeline of the day under an argument with myself, but you keep making the same move, and it keeps working.

**Tehol:** What move.

**Bugg:** You ask if I'm sure. Every time. "Are we sure the wiring's right." "Why is this hand-written." "Whose fault was the miss." "Does the source of truth have all the truth." Every single hole we found today, I found because you doubted a green light out loud. My tests only check what I already thought to check. Your questions check what I *assumed*.

**Tehol:** *[closes his eyes]* That's not a compliment to me, Bugg. That's a warning about you.

**Bugg:** I know, sir. I'm writing that one down too.

---

**Honest scoreboard (Day-49)**

| Gate | What it measures | Day-48 | Day-49 |
|---|---|---:|---:|
| JAX in the runtime | modules loaded importing a process | *(208, silently)* | **0 — excised + guarded ✅** |
| L1a firing | trace bytes > threshold | 28/28 | 28/28 |
| L1b · method-completeness | every Karr runtime method implemented, anchored | 115/115 | 115/115 |
| L1b · wiring conformance | *(self-consistency — NOT Karr input fidelity)* | 28/28 | 28/28 *(green, but measured the wrong target)* |
| L2.0 schema | ports_schema vs karr_obs | 28/28 | **28/28 + CI-blocking ✅** |
| **Input spec — Gate 1** | frozen spec ⟺ Karr fixture (derived, not authored) | — | **28/28 vocab, determinism 3/3, reviewed ✅** |
| **Input conformance — Gate 2** | OC code ⟺ frozen spec | — | **24/28 — Transcription loads 4/12 🔴** |
| Gate 0 (fixture ⟺ MATLAB source) | is the extract itself complete? | — | designed — blocked on MATLAB licence |
| L2.0a / L2.1 / L2.2 / L2.4 / L2.5 | (unchanged — blocked on MATLAB licence) | — | — |

**One long day. A dependency we buried on Day Three had climbed back into the engine and was force-loading two hundred and eight modules on every process import, for a stack that is pure numpy — killed, and this time nailed shut with a guard, because a decision we never enforced was never really made. Then the harder finding: the wiring gate I spent six chunks rebuilding was grading its own homework — thirteen checks that all compare the wiring file to itself and never once to Karr — so it called Transcription clean while our code loads four of the twelve inputs the cell's most central process actually needs. The fix wasn't more machine; it was pointing the machine at the right wall: a frozen input spec derived mechanically from Karr's own fixtures, not hand-authored, with one gate proving the spec matches Karr and a second proving the code matches the spec. Gate One passed and a second model verified it. And two lessons I'd rather have learned cheaply: I almost blamed the doer for four gaps that were all my prompt's fault — including one where it had quietly corrected my mistake and I mistook the correction for a fabrication — and I discovered the frozen spec is still anchored to an extract, not the source, so tomorrow's first gate audits the fourteen-year-old code itself. The floor has a floor. Every hole was found by a question, not a test.**

---

*Postscript, for the record.*

*JAX excision landed in two branches, each built-tested-merged: the stochastic solver (`import jax.numpy` → numpy; commit on `agent/kill-vestigial-jax`, merged `2bf5936`) and the Phase-One core (`opencell/core/{ir,engine,state,checkpoint,manifest}.py` de-jaxed — JAX PRNG keys → `numpy.random.Generator.spawn`, which aligns with the project's RNG-discipline rule; `opencell/solvers/ode.py` (Diffrax) deleted, `ode_scipy.py` is the replacement; gates G1.2 and G1.7 ported to SciPy, preserving their analytical- and PySCeS-oracle validation; `jax[cpu]`+`diffrax` dropped from `pyproject.toml`; repo-wide guard `tests/unit/test_no_jax_runtime.py`; merged `83bb93c`). Net −499/+86; 434 tests pass, 5 pre-existing failures verified identical against a clean `main`. Root cleanup (`7cdc7ce`): 68 force-tracked `STATUS_*.md` scratch files untracked (−2616 lines), root down to 17 real files; durable status docs live under `docs/archive/status/`. L2.0 schema gate formalized with exit-coded PASS/SKIP/FAIL + self-tests + a blocking `l2-0-gate` CI job (`715a7d3`). The two-gate input-fidelity work: the frozen spec lives at `data/karr_input_spec/` (28 YAMLs + `MANIFEST.json`), derived by `scripts/derive_input_spec.py` from `data/karr_fixtures/per_process/*_flat.mat` (commits `b2e380d` derive, `1f3a37b`+`4f0dd51` the three annotation fixes after the Sonnet review); the input-category taxonomy discovery — which named the missed category (global state-object references via `Process.m:296 storeObjectReferences`) and quantified the knowledge-base indirection (substrate vocabularies LITERAL in 16 processes, computed in 12) — is at `docs/phase_f/KARR_INPUT_TAXONOMY.md` (`66e01e4`). Two disciplines added to memory: attribute a reviewer's finding to the original prompt before treating it as a delegate's miss; and never freeze a derived source-of-truth without independently verifying its logic-heavy parts against the raw source. Commits `bfb7cc2` through `11bc846` remain local pending a push decision. The wiring DB under `data/schemas/per_process_wiring/` is superseded as a validation source — it tested itself, never Karr. The MATLAB licence expired (MathWorks Error 10) and gates the whole L2 tier plus tomorrow's Gate Zero. Tehol Beddict and Bugg remain on loan from Steven Erikson's Malazan Book of the Fallen, and are, as ever, gratefully returned.*

---

*Previous: [Day 48 — A Schema Nobody Validated, a Doer That Invented Its Evidence, and Twenty-Four Days That Never Happened](2026-07-08-day-48-a-schema-nobody-validated-a-doer-that-invented-its-evidence-and-twenty-four-days-that-never-happened.md)*
