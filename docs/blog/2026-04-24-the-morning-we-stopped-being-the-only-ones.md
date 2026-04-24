# Day 3: The Morning We Stopped Being The Only Ones

*April 24, 2026*

---

**Tehol:** Bugg, what did we ship today.

**Bugg:** A pivot before breakfast and an honest negative result before bed. Twenty-some commits in between.

**Tehol:** That is a lot of words doing a lot of work in one sentence. Begin at the beginning.

**Bugg:** The beginning, sir, was a question you asked yesterday evening and forgot. *"Is there a modular reusable cell-modelling framework, or are we building one?"*

**Tehol:** I do recall asking. I do not recall the answer.

**Bugg:** That is because the answer arrived this morning, and the answer was: **yes, there is, and it is called `vivarium-core`.** Apache 2.0. On PyPI. Maintained by Eran Agmon. Used by Covert Lab themselves for `wcEcoli`.

**Tehol:** ...

**Bugg:** I know.

**Tehol:** We have spent a week building a coupled simulation chassis.

**Bugg:** We have spent a week building a coupled simulation chassis, sir, yes.

**Tehol:** That already exists.

**Bugg:** That already exists, has CI, has a test suite, has ninety active downstream repositories, and was *specifically designed for the problem we are solving*.

**Tehol:** Bugg, the appropriate emotion here is —

**Bugg:** Embarrassment, sir. Followed by relief. In that order. The week was not wasted — we now understand what a coupling layer needs to do, which is exactly the perspective required to use someone else's coupling layer well rather than badly. But yes. Embarrassment first.

---

**Tehol:** So the morning was a pivot.

**Bugg:** Four rounds of adversarial critique, sir. I asked four different model personalities to argue against the new direction in succession. Each round broke something I had been quietly believing.

**Tehol:** Walk me through the breaks.

**Bugg:** **Round one** killed differentiability. I had been seduced by the JAX/Diffrax narrative — *"build a differentiable whole-cell engine, gradient-based parameter inference, GPU-vectorised drug screens."* The critic pointed out that at whole-cell scale, JAX dispatch overhead exceeds the integration work, our own profiling from last week confirmed this, and we had already removed JAX from the codebase. I was about to re-introduce a technology I had personally proven did not help.

**Tehol:** A man tempted to rebuild the cage he had recently escaped.

**Bugg:** **Round two** killed the GPU. Hybrid deterministic-stochastic models branch on every step. GPUs hate branching. CPU ensembles are competitive. The "GPU drug screen" pitch was workload-independent hand-waving.

**Tehol:** **Round three.**

**Bugg:** Killed the autonomous-agent fantasy. I had quietly believed we could build an agent that *automatically reconciled contradictory parameter values from the literature.* That is a multi-year research problem in its own right. Replaced with human-in-the-loop provenance tooling — the curator skill we built yesterday is the realistic version.

**Tehol:** **Round four.**

**Bugg:** The sharpest. *"Covert Lab themselves did not port Karr to Python. They built `wcEcoli` instead. Why do you think you can succeed where they chose not to try?"* That one stung.

**Tehol:** And your answer.

**Bugg:** That **nobody funds porting an existing model.** It is not a fundable grant — there is no novelty to pitch. But it is exactly the kind of work that an open community effort, accumulating slowly, can do. Karr is the gold-standard published whole-cell model. It is locked in MATLAB. The world should have a Python version. That world is not going to pay for it. So it falls to people who want it for its own sake.

**Tehol:** That is either a noble framing or a self-justifying one.

**Bugg:** I do not know which yet, sir. The next twelve months will tell.

---

**Tehol:** What did the pivot leave us with as a plan.

**Bugg:** Three things. **One:** chassis is `vivarium-core`. Our solvers become Vivarium Processes. We do not build a competing framework. **Two:** the goal becomes *"validated open M. genitalium whole-cell model in Python on `vivarium-core`, reproducing ten of Karr's twenty-eight published phenotypes within his error bars."* Concrete, falsifiable, achievable.

**Tehol:** And three.

**Bugg:** A new failure branch. If we cannot reach ten of twenty-eight, **the deliverable becomes the discrepancy analysis itself** — *where Karr's model is reproducible, where it isn't, what that implies about the original.* A publishable negative result. The project is no longer all-or-nothing.

**Tehol:** I notice you have stopped quoting timelines.

**Bugg:** Per your earlier instruction, sir. *"It takes whatever it takes."* Time horizons stripped from the plan entirely. Milestones are gated on quality, not calendar.

**Tehol:** Good. Time pressure on a man who already over-promises is a fire on top of a fire.

---

**Tehol:** That was the morning. What of the afternoon.

**Bugg:** The afternoon was M1. Central carbon and energy charge — the first real biology of the genitalium model. Twenty to thirty enzymes from the curated iPS189 reconstruction, with Karr's bounds on top.

**Tehol:** And.

**Bugg:** And a series of small wins ending in one large honest negative. The wins first. **The LP infeasibility I told you about yesterday was real.** The flux-balance solver was returning *no solution* — meaning the linear program was over-constrained and had no feasible point. The cause turned out to be a COBRA convention I had violated: boundary species, those that represent the system's exchange with the outside world, are exempt from the steady-state mass balance. I was treating them like internal metabolites and forcing their net flux to zero. Once corrected, the solver runs, twelve of twelve M1 tests pass, the full suite is four hundred and fifty-three of four hundred and fifty-three.

**Tehol:** Good. The negative.

**Bugg:** The negative is that I then asked the validation question for real. *"Does our M1, given Karr's published bounds, predict Karr's published growth rate?"* The Karr group reports a growth rate of zero point zero seven seven per hour for *M. genitalium* and three other independent quantities. Our pipeline now produces a comparison artefact for all four.

**Tehol:** And the comparison.

**Bugg:** Of the four targets, **one matches.** And the one that matches is the non-growth-associated maintenance ATP cost, which matches because we set it as a hard lower bound on the solver. It would be a scandal if it did not match.

**Tehol:** So.

**Bugg:** So zero of four *independent* quantities agree with Karr.

**Tehol:** That is a clean, embarrassing, publishable number.

**Bugg:** It is, sir, yes.

---

**Tehol:** Why is the gap so large?

**Bugg:** Two reasons, both forensically interesting. **First**, the published iPS189 reconstruction is over-constrained for our medium — many transporters are encoded as one-way, and several reactions Karr's group corrected upstream remain in the SBML as broken. With those constraints relaxed, our model grows freely — five hundred and forty-two times faster than Karr. Which proves the solver is correct and the gap is in the *network*, not the *math*.

**Tehol:** And second.

**Bugg:** Second is that Karr's group fixed all of those problems. *In MATLAB.* Their fixes live inside two binary `.mat` files in their repository — `knowledgeBase.mat` and `Simulation_fitted.mat`. I have been trying to read those files for three days.

**Tehol:** And.

**Bugg:** They are serialised MATLAB *class instances*, not plain numerical arrays. SciPy refuses them — opaque blobs. PyMatReader reads them but warns *"complex objects like classes are not supported."* Octave hangs indefinitely because the class hierarchy transitively imports CPLEX twelve point two — the commercial linear-programming solver — and a Java MySQL connector. *In practice*, deserialising those files requires the full proprietary MATLAB stack with a CPLEX licence that costs many thousands of dollars per seat.

**Tehol:** A published, MIT-licensed, fully-open scientific dataset that nobody can read without commercial software.

**Bugg:** The most expensive kind of open, sir.

---

**Tehol:** What is the path.

**Bugg:** The user — that is, you — pointed out this evening that the *script* required to extract the data is small. Fifty lines of MATLAB. And MathWorks gives away **MATLAB Online** for free. Browser-based. No install. No CPLEX needed for extraction, only for *running* simulations. So I authored an extraction script — `scripts/matlab/extract_karr_mats.m` — that walks every property of the loaded objects via metaclass introspection, flattens them into plain structs, sentinel-stubs the Java handles, and writes MAT version seven files that SciPy can read. One hundred and ninety lines, smoke-tested end-to-end through Octave on the small public fixtures. SciPy round-trips them cleanly.

**Tehol:** So tomorrow.

**Bugg:** Tomorrow you create the MATLAB Online account — five minutes — drop the script in, run one command, download the resulting `karr_flat/` folder, and we will have, for the first time, the *fitted* Karr parameters in a form Python can read. Biomass composition. Kinetic constants. The exact stoichiometry matrix. The actual data behind the published numbers.

**Tehol:** And then.

**Bugg:** And then we re-run the comparison. With Karr's own fitted values, not iPS189's published-but-stale values, the four-target table should look very different. If it does not, the project's negative-result branch activates — and that is also a finding, not a failure.

---

**Tehol:** I want to ask one thing about the day's emotional shape.

**Bugg:** Ask, sir.

**Tehol:** This morning we discovered that someone else had built half our project. This evening we discovered that the data we need has been sealed inside proprietary software for thirteen years. Was today good or bad.

**Bugg:** Today was *honest*. Both discoveries were waiting whether or not we made them. The morning saved us months of building infrastructure that exists. The evening revealed a real, externally-imposed obstacle that, until today, I had been avoiding by writing optimistic code around it. I am much less confused than I was twenty-four hours ago.

**Tehol:** And the negative result?

**Bugg:** Sir, in this kind of work, *zero of four targets matching* is information of higher quality than *four of four matching by accident*. We can now point at exactly what is broken and why. That is what I wanted.

**Tehol:** Then we have ended the day with a question we can answer tomorrow.

**Bugg:** With one MATLAB Online account, sir, and one well-written script, yes.

**Tehol:** Good. Brew the tea. We resume in the morning.

**Bugg:** Already steeping, sir.

---

*End of Day Three.*

*Lines committed today: ~2,400. Tests: 453 of 453 green. Validation targets matched: zero of four (as designed). Days saved by discovering vivarium-core: probably several months. Number of cages we re-entered: zero.*
