---
title: "Days 119-125: Three Honest Ports, Twenty-Five Blockers, and the Matrix We Refused to Fake"
date: 2026-09-23
authors: [sdrona]
tags: [opencell, matlab, fidelity, l2.1, l2.2, l2.5, vivarium, multi-agent]
---

**Tehol:** Bugg.

**Bugg:** Sir.

**Tehol:** The last post ended with twenty-two green lights.

**Bugg:** It did.

**Tehol:** And this post begins with zero.

**Bugg:** Zero out of twenty-eight eligible for the next rung.

**Tehol:** That is an impressive loss of altitude in one week.

**Bugg:** We did not lose working biology. We stopped calling several narrower
claims a complete MATLAB port.

**Tehol:** Explain the distinction before I throw the board off the terrace.

**Bugg:** L1b proved that every expected runtime method existed and that all
twenty-eight wiring records were internally consistent with the code.

**Tehol:** Good.

**Bugg:** Including records that explicitly said the code differed from Karr.

**Tehol:** Less good.

**Bugg:** L2.1 proved exact replay on selected deterministic traces.

**Tehol:** Good.

**Bugg:** Except some production paths could accept a `trace_hint` carrying the
recorded outcome.

**Tehol:** Bugg.

**Bugg:** And L2.2 proved selected channels under process-specific
configurations.

**Tehol:** Let me guess. Not always the production chassis configuration.

**Bugg:** Metabolism was the clearest example. The gate used dynamic bounds,
Karr writeback and GLPK. Production used allocator coupling with different
defaults.

**Tehol:** So we optimized the test configuration until it could make a
defensible statement.

**Bugg:** Yes.

**Tehol:** And then promoted that statement beyond its jurisdiction.

**Bugg:** Also yes.

---

**Tehol:** What did two months of extraction buy us, then.

**Bugg:** A very good oracle.

**Tehol:** That sounds like the beginning of an excuse.

**Bugg:** It is the opposite. The MATLAB source, fitted-state fixtures,
per-process traces, active windows, random-stream states, live volume, and
multi-seed cohorts are still the most valuable assets in the repository. They
let us identify the error now.

**Tehol:** The error being.

**Bugg:** We confused evidence quality with claim quality. The extracted
evidence was real. The gates sometimes asked a smaller question than the label
on the green light implied.

**Tehol:** So the extraction was not wasted.

**Bugg:** No. But extraction cannot rescue a test that validates the wrong
subject, the wrong configuration, or only one output channel.

**Tehol:** And a beautifully documented deviation is still a deviation.

**Bugg:** Correct. We are porting Karr from MATLAB to Python. A precise list of
ways the port is wrong is useful for repair, not a substitute for repair.

---

**Tehol:** How did zero out of twenty-eight appear.

**Bugg:** We added a fail-closed pre-L2.5 eligibility baseline. For each
process, it asks a blunt question: is every required lower gate green, is the
production path the path that was tested, and is there any known
source-fidelity defect still open.

**Tehol:** First run.

**Bugg:** Zero eligible. Twenty-eight blocked.

**Tehol:** Did the new gate discover twenty-eight new bugs.

**Bugg:** Mostly it refused twenty-eight old excuses. Some were real code
deviations. Some were stale audits. Some were configuration mismatches. Two
processes were missing a lower gate because our denominator was wrong.

**Tehol:** The twenty-two out of twenty-two.

**Bugg:** Should have been twenty-two out of twenty-four.

**Tehol:** Which two were standing outside the photograph.

**Bugg:** ChromosomeCondensation and TranscriptionalRegulation. Both had been
classified as deterministic. Both perform random chromosome binding.

**Tehol:** And the old L2.1 eleven out of eleven.

**Bugg:** Eleven was an active-window repair manifest, not the number of
deterministic processes. It contained nine stochastic processes and two
deterministic ones.

**Tehol:** How many deterministic processes are there.

**Bugg:** Four:

- ChromosomeSegregation;
- HostInteraction;
- ProteinActivation;
- TerminalOrganelleAssembly.

**Tehol:** And the other twenty-four need distributional evidence.

**Bugg:** Exactly. The corrected L2.2 board is twenty-two PASS, two
MISSING_EVIDENCE, twenty-four required.

**Tehol:** A smaller number, but at least it now has a denominator.

---

**Tehol:** We started with the four deterministic processes.

**Bugg:** And repaired three.

**Tehol:** HostInteraction first.

**Bugg:** The Python process read all fifteen host-response enzymes from one
flat protein store. Karr's fitted state said fourteen were ProteinMonomers and
one was a ProteinComplex:
`MG_410_411_412_PENTAMER`.

**Tehol:** Which our flat read missed.

**Bugg:** Production now reads fourteen monomers from `protein.counts` and the
pentamer from `complex.counts`, both initialized from the canonical fitted
states. The positive condition produces six true host booleans. Five
preregistered negative and partial conditions produce their exact expected
patterns instead of allowing an always-true stub to pass.

**Tehol:** Eligible.

**Bugg:** One out of twenty-eight.

**Tehol:** ChromosomeSegregation.

**Bugg:** A scheduler bug. Vivarium Processes execute before Steps. The process
emitted its resource request and then tried to consume the grant in the same
call, before the allocation Step had run. It therefore observed the previous
tick's allocation.

**Tehol:** The fix.

**Bugg:** Split the behavior into a request-only Process, the allocation Step,
and a post-allocation evolution Step. The current request is now granted and
consumed in the same Engine tick. We also removed duplicate enzyme ports whose
updater semantics conflicted with the shared stores.

**Tehol:** Eligible.

**Bugg:** Two out of twenty-eight.

**Tehol:** ProteinActivation.

**Bugg:** The old implementation reduced six regulated proteins to flat
activity flags and surrogate signals. Karr evaluates each protein in each of
six compartments, converts ordinary molecule counts to millimolar using live
cell volume, preserves true stimuli as booleans, and transfers the entire
active or inactive count when a rule flips.

**Tehol:** So.

**Bugg:** Production now has canonical active and inactive state for six
proteins across six compartments in the shared protein and complex roots.
`protein.activity` is derived only. A thousand phosphate molecules convert to
`0.1382689681128521 mM` under the live geometry and follow the concentration
rule, not a raw-count shortcut.

**Tehol:** Eligible.

**Bugg:** Three out of twenty-eight.

---

**Tehol:** TerminalOrganelleAssembly.

**Bugg:** That agent committed nothing.

**Tehol:** Failed.

**Bugg:** Succeeded.

**Tehol:** You are going to have to work for that one.

**Bugg:** The preflight proved the fixture exactly. Eight proteins, two
relevant compartments: incorporated and unincorporated. The values matched the
canonical ProteinMonomer fitted state exactly. The localization matrices and
thresholds loaded correctly.

**Tehol:** So why not port the transfer.

**Bugg:** Because production exposes only aggregate `protein.counts`. Giving
TerminalOrganelleAssembly a private eight-by-two matrix would create a second
writable truth. The process could pass its own test while Translation,
ProteinTranslocation, decay, processing, activation and host response kept
reading a different count.

**Tehol:** The familiar solution would have been to synchronize both.

**Bugg:** Which means waiting for the day one writer updates one store and not
the other.

**Tehol:** Or adding a replay path that writes the expected answer.

**Bugg:** The module already has one. It must be removed, not promoted.

**Tehol:** Then what is the actual prerequisite.

**Bugg:** Make compartmental ProteinMonomer counts authoritative across the
chassis. Derive the aggregate view for legacy readers. Move
ProteinTranslocation and TerminalOrganelleAssembly onto the same state. Then
port Karr's full-count fixed-point transfer.

**Tehol:** Does that help only the organelle.

**Bugg:** No. ProteinTranslocation already carries a known compartment
deviation. ProteinDecay flattens compartmented surfaces. ProteinActivation now
has a real six-compartment state that should integrate with one shared
representation rather than grow into another island.

**Tehol:** Big-bang rewrite.

**Bugg:** No. One authority, a derived compatibility view, and staged writer
migration. TOA and translocation first. Flat readers continue through the
derived view until their own fidelity work requires more.

---

**Tehol:** You used the three-slot prompts again.

**Bugg:** Deliberate-action prefix, domain rules, case-specific contract.

**Tehol:** Ceremony.

**Bugg:** Host, segregation and activation all landed without trace hints,
oracle reads, test-only production configurations, event-tick branches or
threshold changes. More importantly, TerminalOrganelle stopped.

**Tehol:** Stopping is now evidence.

**Bugg:** In this case, yes. The prompt forced the agent to state the most
embarrassing false pass before editing: a private compartment matrix that
agreed with the fixture while the rest of the chassis kept another authority.
Then preflight found exactly that risk.

**Tehol:** So three slots are sufficient.

**Bugg:** Sufficient to prevent that wrong repair. Not sufficient to design,
test, implement and independently certify a cross-chassis state migration in
one context.

**Tehol:** What is.

**Bugg:** Four separated roles. An Opus planner derives the ownership contract.
A Gemini test writer freezes adversarial tests before implementation. A Sonnet
doer implements without controlling its acceptance bar. A GPT reviewer
re-derives the verdict from source and production behavior.

**Tehol:** Four models to move eight proteins between two columns.

**Bugg:** Four models to make sure there is only one pair of columns.

---

## Honest scoreboard

| Gate or scope | Current verified status |
|---|---|
| **Pre-L2.5 no-known-gap eligibility** | **3 eligible / 25 blocked** |
| **Deterministic terminal processes** | **3 eligible / 1 architectural blocker** |
| **L2.2 corrected denominator** | **22 PASS / 2 MISSING_EVIDENCE / 24 required** |
| **L1b method completeness** | **115 / 115 resolved** |
| **L1b wiring conformance** | **28 / 28 PASS** |
| **L2.4 conservation** | **PASS, 100 ticks x 4 seeds** |

---

**Tehol:** Caveats.

**Bugg:** The three repairs are verified together on the honesty integration
branch; this post is publishing before that branch is promoted to main. The
older v4 integration suite still has three reproduced pre-existing failures:
one folding-progression assertion and two tests that seed absent protein-count
paths. We did not relabel them as new activation regressions.

**Tehol:** And twenty-five processes are still blocked.

**Bugg:** Yes. Three honest ports do not make a whole-cell port.

**Tehol:** But they establish the repair method.

**Bugg:** Primary MATLAB source first. Canonical fixture projection before
editing. Production Engine path. A planted inversion test. No evidence waiver
for known code deviations.

**Tehol:** What begins now.

**Bugg:** The compartmental ProteinMonomer migration. Planner, test writer,
doer, reviewer. Then TerminalOrganelleAssembly gets another turn.

**Tehol:** And if the planner says the migration is larger than we think.

**Bugg:** We will publish the larger truth instead of the smaller fiction.

**Tehol:** Three out of twenty-eight.

**Bugg:** Three out of twenty-eight.

**Tehol:** It sounds worse than twenty-two out of twenty-two.

**Bugg:** It means more.

---

*This is the OpenCell dev blog. The repo is
[github.com/srinivasdrona/opencell](https://github.com/srinivasdrona/opencell).
The next post will follow one compartmental protein state from MATLAB fixture
to shared production authority—and report whether TerminalOrganelleAssembly
finally becomes four out of four.*
