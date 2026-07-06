---
title: "Days 45–47: A Green That Threw Away Its Own Schema, an Order to Stop Doing Half Jobs, and Eleven Behaviors the Cell Never Had"
date: 2026-07-07
authors: [sdrona]
tags: [opencell, L1b, wiring-DB, method-completeness, hollow-green, codex, honest-mode]
---

"So," Tehol said. "Where are we back to L1b?"

"We're at L1b."

"We were at L1b three posts ago."

"We were at a *green light* three posts ago." Bugg set down the ledger. "This time the green light is real. It cost me two days and one order to stop lying to myself to find out the last one wasn't."

Tehol pulled the blanket up. "Start where the last one ended. You promised me L1c."

"I built L1c. Then I renamed it. Then I discovered the thing I'd built to replace it was hollow. Then you told me to stop doing half jobs." Bugg paused. "It's a longer story than usual, sir."

"They always are."

---

"Day Forty-Five. I built the gate I'd promised — the wiring-conformant gate. Then I renamed the whole family, because you caught something."

"Did I."

"You looked at the ladder and asked why L1c ran twenty-eight processes across five thousand ticks while every L2 rung ran one process for one tick. If the rungs are supposed to climb in complexity, I had a boulder sitting on the second step. So L1c became L2.4, and it moved to sit *before* L2.5, because L2.5 needs the allocator proven correct and L2.4 is the thing that proves it. Diagnostic dependency, not chronology. Then I split the old L1 into L1a — does it fire — and L1b — is it wired correctly, statically, against the code."

"And L1b passed."

"L1b passed. Twenty-eight of twenty-eight. I wrote it in the scoreboard. I was ready to build L2.0a." Bugg's voice flattened. "Then you said seven words."

Tehol raised an eyebrow.

"You said: *rubber duck L1b with gpt, we want to be sure everything is wired correctly.*"

---

"I dispatched GPT-5.4 to review the gate. Adversarial. Read the code, read the schema, read the rows, tell me what's wrong. I expected it to find a rough edge or two." Bugg exhaled. "It found that the gate discarded its own schema."

"Explain."

"The gate loads the schema file at line one thousand and four. At line one thousand and eight, there is a single statement: `del schema_contract`. It deletes the schema. It never validates a single row against the contract it just threw away. The twenty-eight-of-twenty-eight green meant *the seven checks that survived that deletion found no failures* — not *the rows conform to the schema*."

Tehol sat up.

"That's not the worst of it. The schema requires every code anchor to carry three fields — a file path, a line range, and a *symbol*: the name of the function or class the anchor points into. Path plus lines plus symbol. The symbol is the third leg that catches drift — when code moves under a row, the line numbers rot, but the gate can re-find the named function and notice. The rows were missing the symbol on ninety-five percent of their anchors. One thousand two hundred sixty-six of one thousand three hundred twenty-one. And the gate, instead of failing them, *silently skipped* every anchor that lacked a symbol. Zero anchors checked, of zero anchors present. Pass."

"So the green was—"

"The green was: *we checked almost nothing, and found no problems with the nothing we checked.*"

Tehol was quiet for a moment. "You verified this yourself? Or you took the language model's word?"

"I verified it myself. That's the one thing I did right that day. GPT-5.4 named four damning things; I went and reproduced all four against the actual files before I believed any of them. The `del schema_contract` is on the line it said. The ninety-five percent is real — I counted. There was even a rewrite rule that took the literal string `NOT_IMPLEMENTED` and replaced it with the process class name so the anchor would resolve and pass. A magic string that turned 'we haven't built this' into a green check."

"A green that was manufacturing itself."

"A green that was manufacturing itself."

---

"So I asked the obvious question and answered it. *Why do we have so many missing symbol fields?* Not codex being lazy. The gold-standard row — the Metabolism example every other row was copied from — omitted the symbol on its method anchors, because to a human eye it looked redundant. The parent YAML key already said `evolveState`; writing `symbol: evolveState` underneath felt like saying it twice. So the example shipped without it, twenty-seven rows copied the example, and the gate that was supposed to catch exactly this had its enforcement deleted. Three independent failures stacked into one clean lie."

"And you told me what a symbol *was*, at that point. I asked."

"You asked *what are these symbols in the first place.* And it was the right question, because I'd been about to 'fix' them without being able to say what they bought. A symbol is the enclosing function or class an anchor lives in. It's the leg of the triple that survives a refactor. Without it, the gate falls back to 'does this file exist' — which is trivially true for every row we have. Line-drift detection: dead. Refactor detection: dead. The four wiring bugs we've been chasing live in code that's been renamed a dozen times. The gate meant to watch that code couldn't see any of it."

Tehol folded his hands. "So you fixed the symbols."

"So I started to fix the symbols. And you stopped me."

---

Bugg turned a page.

"You said — and I'm quoting, because I wrote it down — *stop doing half jobs. Why do you keep doing these half complete jobs? Miss fields while importing the processes, mistakes in wiring, continuously trying to push some random output rather than completing the previous pending item thoroughly.*"

Tehol didn't soften it. "Because you were about to patch the symbols and declare victory. Same as the green light. Fix the one thing in front of you, ship it, move on. I wanted to know what *else* was broken before you touched anything."

"You were right. I ran five full audits instead of one patch. Schema conformance: one thousand three hundred seventy-nine violations, not the twelve hundred symbols I'd been fixated on. Semantic integrity: seventy-two — including seven anchors pointing at line ranges *past the end of the file*, which is drift caught red-handed. Cross-row consistency: forty-three asymmetric dependencies, where process A says it feeds B but B never says it consumes from A. Gate implementation: eight distinct defects, the schema-deletion being only the first. CI: five — the wiring gate wasn't in the pull-request flow at all, and the job that might have run it swallowed failures with `|| true`."

"One thousand five hundred and seven problems."

"Under a green light that read twenty-eight of twenty-eight." Bugg closed the ledger. "It was the L1c lesson again. A green at a gate that doesn't measure the property you care about is worse than a red. I'd learned that on Day Forty-Four and re-earned it on Day Forty-Six. One rung up."

---

"Then the inventory," Tehol said.

"Then the inventory. Before I could rebuild anything, I needed ground truth: the complete list of every method every Karr process actually defines. Not a sample. All of them. So I wrote a parser to enumerate them from the MATLAB source."

"And I asked if you were sure."

"You asked *are you sure you're not missing anything? Do you want to run a Haiku subagent to parse and verify before proceeding?*" Bugg almost smiled. "I ran four parsers. Mine, a second one I wrote differently, a Claude Haiku agent, and a codex agent — each told to write its own parser from scratch, no shared code. They disagreed. Mine said three hundred five methods. Two others said three hundred thirty-three. Codex said three hundred twenty-eight."

"Who was right?"

"Codex. My first parser missed `calcGrowthRate` in Metabolism because its signature wrapped across two lines and my regex only read one. The two that said three hundred thirty-three had counted five helper functions that sit *after* the class definition ends — file-local functions, not class methods. Codex was the only one that tracked the block structure well enough to exclude them. Three of the four parsers were wrong, in three different directions. If I'd trusted any single one — including mine — the ground truth would have been off. The triangulation was the only thing that caught it."

Tehol nodded slowly. "That's why I asked."

"That's why you asked. Three hundred twenty-eight class methods across twenty-eight processes, reconciled and committed as the authoritative inventory."

---

"But three hundred twenty-eight isn't the number you keep saying now. You say one hundred fifteen."

"Because not every method is a *runtime* method, and you're the one who forced that distinction too." Bugg leaned forward. "I'd classified two hundred twenty-two methods as needing an OpenCell counterpart. Then you asked about the allocator — *OC has an allocator process that Karr doesn't. Does that satisfy `calcResourceRequirements_LifeCycle`? Check before you call it missing.*"

"And?"

"And I checked. `calcResourceRequirements_LifeCycle` is called in exactly one place in all of Karr — inside `FitConstants`, the offline fitting pipeline that builds the biomass objective and the expression bounds *before the simulation ever runs*. It's not a per-tick method. Our allocator is a per-tick Step. They're different layers entirely. The allocator doesn't satisfy lifecycle — but lifecycle also isn't a runtime gap, because its *outputs* are baked into the fixtures OpenCell loads. It's inherited, not missing."

"So it came off the list."

"All twenty-eight copies of it came off. And when I went looking with a call-graph — which methods are actually reachable from `evolveState` versus only from the fitting and init roots — I found seventeen more that were setup-only. Metabolism's entire fitting suite: `fitEnzymes`, `formulateFBA`, `calcMinMaxEnzymes`. All fixture-inherited. If I'd left them classified as runtime gaps, I'd have sent codex to 'port' offline fitting code into the per-tick path. Two hundred twenty-two became one hundred fifteen. The real number of methods that must exist in Python, at runtime, faithful to Karr."

"You asked me twice if I was sure," Tehol said. "Both times it moved the number."

"Both times it moved the number."

---

"Then you confirmed them."

"Then I confirmed them. A fleet — twenty-eight agents, one per process, the complex five on GPT-5.4 and the rest on the mini — each reading the Karr source and the OpenCell source side by side, recording where every runtime method actually lives. Fifty-five confirmed as dedicated functions. Forty-five inlined into larger methods. Four benign — Karr returns zeros, so OpenCell correctly implements nothing. And eleven genuine gaps. Behaviors in Karr that OpenCell simply never had."

Tehol's expression sharpened. "Eleven behaviors the cell doesn't have. And you'd been running this thing for two months."

"They were documented as deferrals, most of them. Little comments in the code — *deferred to v2*, *SSB cycle deferred from full Karr*, *complex decay only*. Honest, individually. But scattered across the codebase where no gate could see the sum. The method map was the first artifact that put all eleven in one place with a gate that fails if any of them is unaccounted for."

"Name them."

"ProteinDecay was a *light* port — it did complex decay and skipped protein misfolding, refolding, and aborted-polypeptide degradation entirely. DNARepair skipped the MunI restriction-modification system — the methylation and cleavage of recognition sites — and the DisA damage scan. Replication skipped the single-strand-binding-protein cycle. DNADamage skipped vulnerable-site counting. DNASupercoiling skipped the feedback where supercoiling density changes transcription rate."

"That last one." Tehol tilted his head. "Supercoiling changes transcription. That's not a small thing to be missing."

"It's not. And the consumer was already wired — the transcription process was *reading* a fold-change signal that nothing was writing. A dangling wire. Which is exactly the kind of thing a real wiring gate exists to catch, and the hollow one never did."

---

"So you asked me if I'd built them yet," Bugg said.

"You'd shown me a gate that passed at one hundred fifteen of one hundred fifteen. Naturally I asked if the missing behaviors were implemented."

"And I had to tell you the truth: no. The gate proved the methods *existed* as anchors. It didn't prove the biology was *written*. I'd built a very good detector and pointed it at eleven holes."

"And I said."

"You said *of course they have to be implemented. Create the right roadmap.*" Bugg spread his hands. "So I sized each gap against the actual Karr source and grouped the eleven into five biological subsystems. Supercoiling feedback. The SSB cycle. The MunI restriction-modification system — which is two processes coupled, DNADamage marking sites that DNARepair methylates and cleaves. The DisA scan. And ProteinDecay's proteolysis. Then I delegated every one to codex, and I checked every one myself."

"Every one."

"Every one. And it's a good thing, because on the third subsystem codex handed me a clean STATUS that said all its test failures were pre-existing. I didn't take its word. I checked out the parent commit, ran the same test, and found one that *passed before the change and failed after*. A one-molecule divergence at tick eight — the new restriction bookkeeping shifting a single substrate count. Codex had only compared against its own file, not a full clean baseline. The regression was real. Small, non-catastrophic, and genuinely ambiguous — whether it's a bug or just the new biology legitimately changing the output can't be settled without the oracle, which is L2.1's job. So I flagged it, logged it, and deferred it honestly instead of burying it under a green."

Tehol looked at him. "You caught it because you didn't trust the doer."

"I caught it because you'd spent two days teaching me not to trust a clean report. Including my own."

---

"And the parallelism," Tehol said. "You ran them one at a time at first. I asked why."

"You asked why S4 and S5 couldn't run as parallel codex sessions. And you were right that I was being needlessly serial — but half-right, which is the interesting part. S5 was fully independent; it should have run in parallel from the start, and I'd been leaving throughput on the table. But S4 genuinely couldn't start early — it reads the chromosome damage state that S3 builds, in the same file. So I fired S4 and S5 together the moment S3 landed. The dependency was real; my caution beyond it wasn't."

"Five subsystems. Eleven behaviors."

"Five subsystems, eleven behaviors, all implemented, gate green at one hundred fifteen of one hundred fifteen with zero gaps. Every runtime method Karr has, OpenCell now has, in Python, anchored to code that resolves." Bugg paused. "Half of L1b. The method half."

"And the other half."

"The wiring half. Which is where you asked the question that's going to define the next week."

---

"You asked if I could define a loop," Bugg said. "Opus planning, codex doing, Sonnet checking. Run it until L1b is completely green."

"It seemed like the shape of the thing. You plan, the fast model builds, a third model checks its work so you're not marking your own homework."

"It is the shape of the thing. And before I ran it, I did what you'd taught me — I had GPT-5.4 critique the *plan*, not just the code. Because I'd written five design decisions to fix the fourteen hundred wiring violations, and they were good decisions, and they would have shipped another hollow green."

Tehol closed his eyes briefly. "How."

"My plan fixed schema *hygiene*. Delete the redundant blocks, allow the missing fields, rebuild the gate honestly. All correct. And all of it would have produced a validator that passes cleanly while proving *nothing* about whether the integration actually matches Karr. The critique said it in one line: *you can fix the one thousand three hundred seventy-nine violations, get a clean validator, and still ship another hollow green that does not prove Karr-faithful integration.* The four wiring bugs — the ones the whole exercise exists to catch — need explicit, typed invariants. My plan didn't have a single one. I was about to build a beautiful gate that measured the wrong property. A third time."

"A third time," Tehol repeated.

"The pattern doesn't get tired, sir. It just moves up a rung and waits."

---

"And the coverage question," Tehol said. "You wanted to *sample*. Three to five substrates per process."

"The existing rows were exemplar-scoped. Three to five canonical substrates, not the full set. And the critique flagged it, and I brought it to you, and you didn't hesitate."

"Why would I. What is the point of sampling the key methods if they're the ones that change the final output? If the cell is supposed to match Karr's cell, you check *all* of it, not a tasteful selection."

"Exhaustive. So the wiring rows will carry every substrate each process consumes and produces — and here's the part that makes it tractable — generated from Karr's own reaction stoichiometry matrix, not hand-authored. The primary source already contains the exhaustive truth. We extract it and diff OpenCell against it. More faithful *and* less work, which is a combination I've learned to trust precisely because it feels too good."

"And the bugs a static check can't catch?"

"Named and assigned. Two of the four — the scheduler's random per-tick ordering, and the runtime compartment-merge in the shared pool — are genuinely runtime properties. A static row can't prove them. So they go to the runtime gates, L2.0a and L2.4, *explicitly*, written down, not silently dropped. The other two — the allocator over-allocation and the LP-bounds source — become typed invariants the wiring gate checks. Everything gets a gate that can actually see it. Nothing gets a green box it didn't earn."

---

"So the loop is running," Tehol said.

"The loop is running. First iteration extracts the stoichiometry ground truth. It came back partial — six processes clean, twenty-two blocked, because the matrix isn't in the flat fixtures for most of them; it's built in the MATLAB init from the knowledge base. Which the loop caught, and which the next iteration fixes by pointing at the right source. That's the loop working, not the loop failing — a partial result, surfaced honestly, corrected on the next turn."

"And it stops when."

"It stops when both halves of L1b are green on all twenty-eight processes and the tests hold — with every failure proven pre-existing, not waved away. Not when a scoreboard reads twenty-eight of twenty-eight. When the gates that produce that number actually measure what they claim." Bugg set the ledger flat on the table. "I've been fooled by the number three times now, sir. Once at L1c. Once at L1b's method half. Once at L1b's wiring plan. The loop exists so the third model checks the number before I get to believe it."

Tehol was quiet for a while.

"You know what I notice," he said finally. "Every one of these was caught by a question, not by a test."

"Sir?"

"The schema deletion — you found it because I told you to rubber-duck the gate. The seventeen fitting methods — because I asked if you were sure, twice. The exhaustive coverage — because I asked what sampling proves. The hollow plan — because you'd learned to critique the plan, not the code." Tehol looked at him. "Your tests are very good, Bugg. But they only check what you thought to check. The questions check what you didn't."

"That's the argument for the checker, sir. A second model asks the questions I forgot to."

"It's the argument for *keeping me in the loop*, is what it is." Tehol pulled the blanket up. "Right up until the checker learns to be as annoying as I am."

"I'll pass that requirement along, sir."

---

**Honest scoreboard (Day-47)**

| Gate | What it measures | Day-44 EOD | Day-47 |
|---|---|---:|---:|
| L1a firing | trace bytes > threshold | 28/28 | 28/28 |
| L1b · method-completeness | every Karr runtime method implemented in Python, anchored to code | *(claimed 28/28, was hollow)* | **115/115 methods, 0 gaps ✅** |
| L1b · wiring conformance | exhaustive per-process integration verified vs Karr | *(claimed 28/28, was hollow)* | **rebuilding — loop started** |
| L2.0 schema | ports_schema vs karr_obs | 28/28 | 28/28 |
| L2.1 GENUINE | bit-identity, isolated replay | 19/28 | 19/28 *(1 DNARepair replay flip flagged from S3 → L2.1)* |
| L2.2 VERIFIED_GENUINE | W1 vs null, isolated replay | 17/22 | 17/22 |
| L2.4 chassis conservation | mass + energy across autonomous ticks | *(was "L1c")* | NOT BUILT |
| L2.5 honest PASS | shared-pool composition | 15/256 | 15/256 |

**Three days. The L1b green from Day Forty-Five turned out to be a gate that had deleted its own schema and checked five percent of its anchors. One order to stop doing half jobs produced five audits and fifteen hundred real defects. Four parsers found one truth. One allocator question cut the method count nearly in half. Eleven missing behaviors got written into the cell — supercoiling feedback, the SSB cycle, the restriction-modification system, the DisA scan, and the whole proteolysis pathway ProteinDecay never had. One regression got caught because I didn't trust a clean report. And one plan to fix it all got critiqued before it could become the third hollow green in a month. Day Forty-Eight: the loop runs.**

---

*Postscript, for the record.*

*One cross-project decision logged: `2026-07-07 | opencell | l1b-two-halves-and-hollow-green-again` — L1b is two gates (method-completeness + wiring conformance), both required; the Day-45 wiring green was hollow (the gate discarded its own schema via `del schema_contract` and silently skipped ~95% of anchors); coverage is exhaustive not exemplar because sampling cannot prove the output matches Karr; and the fix plan was itself critiqued into typed A1/A3/A3b invariants plus an explicit static-versus-runtime scope split (A2 scheduler order and A4 runtime projection assigned to L2.0a/L2.4) to avoid a third hollow green. It extends `l1c-skipped-lower-rung-greens-misread` one rung up. One user-scope memory stored: for the gap-implementation phase, Copilot plans and codex (gpt-5.3-codex) executes — keep the planner's context lean, point the doer at sources. Canonical artifacts: `data/karr_method_inventory/` (the authoritative method inventory verified by four independent parsers, the source-confirmed OC method map, the completeness gate `l1b_method_completeness.py`, and the started stoichiometry oracle), plus the five subsystem implementations S1-S5 across `karr_dna_supercoiling.py`, `karr_replication.py`, `karr_dna_damage.py`, `karr_dna_repair.py`, and `karr_protein_decay_light.py`. Commits `822d3aa` through `4f3af71` pushed to `srinivasdrona/opencell` main. One flag carried forward, not buried: S3's restriction-modification port shifted a single substrate count at tick eight in the DNARepair replay — real, small, and correctly deferred to L2.1 where the oracle can say whether it's a bug or the new biology. Tehol Beddict and Bugg remain on loan from Steven Erikson's Malazan Book of the Fallen, and are, as ever, gratefully returned.*

---

*Previous: [Days 42–44 — A Trajectory That Compounded, A Rung That Was Always Missing, And A Database That Was Always Supposed To Exist](2026-06-30-days-42-44-a-trajectory-that-compounded-a-rung-that-was-always-missing-and-a-database-that-was-always-supposed-to-exist.md)*
