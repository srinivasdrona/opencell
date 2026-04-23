# Day 2: The Day the Cell Twitched

*April 23, 2026*

---

**Tehol:** Bugg, what did we ship today.

**Bugg:** Real biology, sir. For the first time. The simulator now emits trajectories of *E. coli* central carbon metabolism that agree with the field's reference tool to five parts in a hundred million.

**Tehol:** Five parts in a hundred million. That's a number a physicist would respect.

**Bugg:** It's a number a physicist would respect on a *good* day. We got it on the first integration.

**Tehol:** Walk me through it. From the top. Pretend I spent yesterday building a parameter pipeline that did not yet have any parameters in it.

**Bugg:** That is in fact what you did. So: yesterday was the foundation pour. Twenty-one commits today, in three waves.

**Tehol:** Begin.

**Bugg:** **Wave one, before lunch.** We closed Phase 1. The five remaining quality gates — atom balance, unit traceability, reference-frame declarations, oracle agreement, thermodynamic feasibility — all passed. The Thattai 2001 micro-model parameters were promoted from DRAFT to REVIEWED to APPROVED, signed by you. Two hundred and fifty-one tests green.

**Tehol:** That feels small for a morning's work.

**Bugg:** It would, sir, except for the part where we discovered the micro-model parameters had been *fabricated*.

**Tehol:** Ah. That part.

**Bugg:** The cards looked authoritative. Provenance fields filled in. Citations to a real paper. The numbers themselves: invented. Yesterday's review caught it; today's first commit was rewriting all four parameters from the actual PDF Figure 1 caption.

**Tehol:** A pipeline that hides fabrication is worse than no pipeline.

**Bugg:** Hence the rest of the morning, and most of the afternoon, on auditability.

**Tehol:** **Wave two.**

**Bugg:** Curation tooling. A deterministic parameter-extractor skill — given a paper, it produces a structured YAML of every numeric value with page, table, and figure citations, plus an evidence snippet. A biology-curator agent that orchestrates the extractor across whole papers. A `biomodels-manifest` CLI that auto-fills SBML metadata. And then two new guardrails I want you to remember the names of, because they're the ones that keep us honest.

**Tehol:** Which two.

**Bugg:** The **paper-pairing verifier**. Every claim "this SBML model corresponds to that paper" is verified against NCBI's eutils API and the response is checksummed and stored. You cannot ship a model wrongly attributed to a paper.

**Tehol:** And the second.

**Bugg:** The **PDF-to-SBML cross-check**. Digit-level diff between numbers extracted from the PDF and the same numbers in the curated SBML. Disagreements bucket out for human review. Agreements pass silently. You as a non-biologist see only the disagree bucket. Three minutes a paper instead of three hours.

**Tehol:** I'm noticing a theme. The agent does not get to be the source of truth.

**Bugg:** Never. The agent gets to *organize* truth so that a human can verify it in a tractable amount of time.

**Tehol:** **Wave three.**

**Bugg:** This is the one. SBML to ODE. The whole point of this project, in two files of Python.

**Tehol:** Two files.

**Bugg:** `sbml_model.py` is the engine. It uses libsbml to parse any SBML Level 2 or 3 model, then sympy.lambdify to compile every kinetic law into a NumPy callable. Compartment volumes, assignment rules, boundary species — all handled. Loud failure on anything we don't yet support: events, function definitions, rate rules. No silent wrong answers.

**Tehol:** And the second file?

**Bugg:** `metabolism.py`. Forty lines. It pins one specific model — Chassagnole 2002, BioModels entry 51 — and records the DOI and PubMed ID in provenance. Eighteen species, forty-eight reactions, seven cofactor cofactor assignment rules driven by the original glucose-pulse experiment.

**Tehol:** And it works.

**Bugg:** It works. We integrated it for sixty seconds of simulated time, then three hundred seconds, and compared every species at every point against libroadrunner — the C++ reference simulator the entire SBML community uses. The worst disagreement across eighteen species was thirty-three nanoseconds out of a second. Five orders of magnitude tighter than our test threshold.

**Tehol:** And then you spiked it.

**Bugg:** Then we spiked it. At t equals one hundred and eighty seconds, we doubled the extracellular glucose. Two phase integration, both simulators in lockstep. The post-spike transient: glucose floods in, the PTS phosphotransferase consumes phosphoenolpyruvate to bring it across the membrane, PEP collapses from one point eight to zero point seven millimolar, pyruvate accumulates from three point five to four point six. Textbook *E. coli* behavior, emerging from a parameter file we did not author.

**Tehol:** And libroadrunner agreed.

**Bugg:** To fifty-two parts per billion across all eighteen species. Including the glucose itself, which goes through a discontinuity.

**Tehol:** That is suspicious.

**Bugg:** I had the same reaction. I spent twenty minutes convinced we had a bug. The "twelve percent error" I remembered from before lunch turned out to be a phantom — a misreading of an earlier diagnostic. The real numbers were fine all along.

**Tehol:** So we shipped a glucose perturbation experiment that the gold-standard simulator agrees with at the level of floating-point round-off, and you spent twenty minutes refusing to believe it.

**Bugg:** I will take that as a feature, not a bug.

**Tehol:** It is. Distrust is the only thing keeping fabrication out of this codebase. Now tell me where we are slow.

**Bugg:** Thirty-one times slower than libroadrunner. Four hundred milliseconds for five minutes of simulated time, versus their fourteen. The hot spot is a Python loop over the forty-eight reaction kinetic laws inside the ODE right-hand side. They're each compiled to NumPy, but I'm calling them one at a time from interpreted Python.

**Tehol:** Is that a problem.

**Bugg:** Not yet. Four hundred milliseconds for a five-minute integration is not a bottleneck for sub-model development. It will become a problem when we have ten coupled sub-models in a hybrid solver loop. The fix is known and in three escalating tiers: vectorize the flux evaluation into one lambdify call, cache the parameter environment as an array, then move the whole thing onto JAX with diffrax for a JIT-compiled integrator that can also autodiff through parameters for fitting.

**Tehol:** None of which we do today.

**Bugg:** None of which we do today.

**Tehol:** What's the discipline change?

**Bugg:** A new mandatory rule in `.github/copilot-instructions.md`: the State Sync Protocol. The plan and the task database are canonical in the repo, not in the agent's memory. Every checkpoint, every status change, every "where are we" question triggers a sync. With a diff check first so we never silently lose a row.

**Tehol:** Because we did silently lose rows.

**Bugg:** The task database in the repo was two days stale. Three todos done, when actually seventy-four were done. Today's twenty-six new todos lived only in session memory. Now they don't.

**Tehol:** What's tomorrow's headline.

**Bugg:** A second sub-model. Transcription, anchored on another curated BioModels entry, the same SBML-to-ODE pattern. Then we wire it to metabolism through the resource ledger so they share ATP. That will be the first multi-module coupled integration. The first time the simulator does something that no single curated model in the literature does.

**Tehol:** And that, finally, is the project.

**Bugg:** That is the project.

**Tehol:** Five parts in a hundred million on day two. A textbook glucose response. A perturbation experiment that matches the gold standard. And a cofactor pipeline that prevents the agent from lying to us. I'd call that a respectable Thursday.

**Bugg:** It's Wednesday, sir.

**Tehol:** Even better.

---

*Next: stitching transcription onto metabolism via a shared ATP pool. The thing the literature has not yet done.*
