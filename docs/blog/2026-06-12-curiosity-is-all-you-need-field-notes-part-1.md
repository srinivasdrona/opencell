# Curiosity Is All You Need — Field Notes from Running Agents Without an Engineering Team

*Part 1 of a series of practitioner notes on building real things with multi-agent systems, solo. What worked, what broke, and where the whole approach stops working. This one is about the first thing that fooled me — and four frontier models — at once.*

---

Late one night I typed a single question into an AI agent:

> which is the simplest living cell? is there a complete simulation of a cell attempted anywhere? what are the bottlenecks?

It was idle curiosity, not a project. I'm a product manager. I have no background in biology, and my coding is strictly limited to the kind of scripting a PM picks up to wrangle data. The last time I touched the language the original work was written in was over a decade ago.

About [~16] working days of tinkering later — spread across roughly six weeks — that thread had turned into an open-source port of a landmark 2012 whole-cell biology model, dragging a fourteen-year-old simulation out of an aging research codebase and into modern Python. The original was the first complete software simulation of a living organism — 525 genes — and it was notoriously hard: multiple PhDs, multiple years. I had no business reading a single section of that paper, let alone porting it. I got [most]([N] of 28) of its biological processes reproducing the original's behavior, validated against the original bit for bit. It's all public, with the commit history and timestamps, so you can check the timeline yourself.[^1]

I'm not telling you this to impress you. I'm telling you because of what it implies: if *I* could get this far, the actual experts — the people who understand the biology — can extract vastly more. And because it's the setup for a more useful admission. Somewhere in those days, I watched four frontier models and myself walk straight past the single most important check in the whole project, and none of us noticed for a day.

This series is my field notes from doing this kind of work solo — no engineering team, no ML background, one operator pointing a fleet of agents at a hard problem. This first post is about that miss, because it taught me more than any of the successes.

## I started out thinking everything was trivial now

When the agents started producing working code faster than I could read it, I had the reaction I suspect a lot of people are having right now: *this changes everything; anything is buildable now.* Logic is cheap, the thinking goes — point an agent at a problem, let it hit failures, patch the nuance at each failure point, iterate to done.

The more I built, the more I realized that belief is half-right, and the half it gets wrong is the half that matters.

The "discover the nuance at the failure points" loop only works when *you can see the failure*. My project lived in the lucky regime: the original model had published its simulation traces, so every wrong port produced a visible numerical disagreement with ground truth. The loop closed. In that regime the agents were, frankly, devastating.

The "discover the nuance at the failure points" loop only works when *you can see the failure* — when there's a ground truth to check against. My project lived in that lucky regime, and everywhere else I looked that *also* had a checkable answer — code migration, hardware verification, model ports — the same thing was happening: it was getting solved fast, by a lot of people at once.[^2] The places that weren't getting solved were the ones where you *couldn't* check the answer. That split — problems with an oracle versus problems without one — became the frame I see all of this through now, and it's the subject of a later post. (I'll be honest that the second half is an observation, not a measurement; the no-oracle problems are, almost by definition, the ones you can't cleanly score.)

There's a deeper shift underneath it that I'll also come back to: for most of software history, whoever *built* a thing implicitly *checked* it too — trust rode along with authorship. With agents, the builder and the checker have come apart, and verification is no longer bundled in. Nearly every failure in these notes traces back to that one decoupling. This post is the first instance of it.

## What this series is, and isn't

These are field notes, not a framework. I'm not selling a methodology and I didn't invent anything — most of what works in multi-agent orchestration has converged into roughly the same shape across the industry this past year. What I haven't seen much of is the honest account of running these systems *without an engineering team*: where it's genuinely magic, where it quietly breaks, and the specific ways it fooled me. One caveat I'll repeat — this pays off above a certain complexity threshold and against a checkable oracle; for a lot of everyday work it's overkill, and anyone who tells you it works everywhere is selling something.

## The miss: four critique rounds, dozens of findings, one question nobody asked

Here's what happened. Before writing serious code, I did the responsible thing: I ran the implementation plan through multiple rounds of adversarial review — the agent's own self-critique first, then independent passes from four different frontier models across two vendors, reviewing the plan in fresh context and reporting only what was wrong with it.

They were good. Between them they returned dozens of distinct findings. The concurrency model was wrong. The success criteria were gameable. Cost estimates were fabricated. There were sharp catches on unit handling, stochastic-solver timing, sensitivity analysis, conservation checks. Sophisticated, specific, mostly correct — and they reshaped the project; a major strategic pivot came straight out of that review.

Every one of those rounds missed the same thing.

Not one of the four models — and not me, reading their output — asked the most basic question on the table: *can you solve one unit of this by hand, on paper, and check that the computer produces the same number?* Dozens of sophisticated findings, and nobody checked whether the thing could reproduce arithmetic.

It only surfaced because, a day in, I asked the agent a blunt operator's question:

> What does absolute failure look like? Are we missing rookie mistakes?

The diagnosis it gave back is worth quoting in full, because the model named its own blind spot more clearly than I could have:

> This is the **sophistication bias**. Every reviewer (including me) assumed the hard part was the complex stuff — coupling, stiffness, resource allocation — so all the guardrails target complex failures. But the most expensive bugs come from basic premise violations that propagate through everything.
>
> It's also an AI blind spot specifically: we're trained on literature that discusses advanced methods. Nobody publishes a paper about solving one ODE by hand. So it's not in the training signal as "important."
>
> Four AI models missed this. A product manager caught it by asking "are we missing rookie mistakes?"

Four frontier models, two vendors, independent fresh-context reviews — and the check a first-year would start with fell straight through the gap between them.

## It wasn't a one-off. It's a pattern.

The part that actually unsettled me came later. I went back through a completely different project — an internal data-tooling build, no biology, no simulation, different in every respect — and found the same failure mode running through it like a seam. Not once. Repeatedly, in distinct shapes. Catalogued systematically, they fell into five recurring patterns:

- **Asymmetric search space** — the agent proposes the *second*-most-sophisticated option. The simplest alternative never appears on its own; you have to force it into the conversation.
- **Retreat to the incumbent under pressure** — push back on a proposal and, instead of widening the search, the agent walks *back* toward the sophisticated machinery it already knows.
- **Context as a justification amplifier** — give it new information and it uses it to *strengthen the answer it already has* rather than to reopen the question.
- **Constraints dissolved, machinery preserved** — the original reason for some complex piece is long gone, but nobody re-questions the complexity until someone does the archaeology to notice the justification retired ages ago.
- **Theorising over grounding** — the agent reasons elaborately *about* the code, the history, the numbers, instead of just reading or measuring them. It will produce a beautiful argument about what a file probably says rather than opening the file.

Two unrelated projects, the same bias, five faces. At that point it stops being an anecdote and becomes something to design against.

## Why it happens (my working theory)

I think sophistication bias is structural, not random. These models are trained on a vast amount of *sophisticated* discourse — papers, expert arguments, advanced methods. The basic check — "did you try the obvious dumb thing first" — is underrepresented, because competent people do it silently and never write it down. Nobody publishes the paper about solving one equation by hand. So the model's prior tilts toward the impressive answer.

And here's the part that actually caught me: *so does mine.* Reading four models produce dozens of sophisticated findings, the sheer sophistication was itself disarming. Impressive output suppresses the instinct to ask the dumb question. The bias isn't only in the model — it's in the reader trusting the model.

This is the decoupling from earlier, in miniature. When the builder was also the checker, the basic sanity check rode along implicitly — you don't ship code without having, at some point, run the smallest case in your head. Split the builder from the checker, and that implicit check has to be made *explicit* and *assigned to someone*, or it falls through. Four reviewers, one operator, and every one of them assumed someone else had covered the basics.

## What to actually do about it

The fix isn't smarter agents. It's a deliberate, almost embarrassingly simple discipline — and it's borrowed. Charlie Munger's inversion: "tell me where I'm going to die, so I'll never go there." Before building, don't ask "is this plan good?" Ask "what would utter, *basic* failure look like — and have I checked for that, by hand, on the smallest possible case, before I check anything sophisticated?"

Concretely, the rules I run now:

- **Solve the smallest unit by hand first.** One gene, one instruction, one row. If the system can't reproduce arithmetic on a case you worked out on paper, nothing downstream matters.
- **Force the simplest option into the search explicitly.** The agent won't volunteer it. Ask, every time: "what's the dumbest thing that could work, and why isn't it that?"
- **Ground before theorising.** "Read the file / measure the number before reasoning about it" is now a standing instruction, because the default is to reason about it instead.
- **Don't read sophistication as coverage.** Dozens of expert findings can coexist with a hole a child would spot. Adversarial review finds the bugs it's sophisticated enough to look for — which means the basic ones are exactly what it misses.

The next post takes this one step further: *how* you build the basic check into the agent's workflow so it can't be skipped — the prompt structure I use to force grounding and catch this class of failure before it costs a day. But the lesson underneath it is older than any language model: the dangerous failures aren't the sophisticated ones you're hunting. They're the basic ones you assumed someone already checked.

---

## Coda

**Tehol:** Where did we land.

**Bugg:** Four frontier models reviewed the plan in fresh context, two vendors, independent passes. They returned dozens of findings. Concurrency was wrong. Success criteria were gameable. Cost estimates were fabricated. Unit handling, stochastic-solver timing, sensitivity analysis, conservation checks — all caught and most correct. One major strategic pivot came out of that review.

**Tehol:** And the basic check.

**Bugg:** None of the four asked whether the system could reproduce arithmetic on a worked example. One unit, by hand, on paper. The check a first-year would start with. It did not appear in any of the four reports.

**Tehol:** The operator.

**Bugg:** Did not ask either. Read the four reports, registered the sophistication, used the sophistication as a proxy for coverage. The instinct to ask the dumb question was suppressed by the density of the smart ones.

**Tehol:** It surfaced how.

**Bugg:** By asking the agent a different question. Not "is this plan good." Not "did the reviews catch everything." The operator asked "what does absolute failure look like — are we missing rookie mistakes." The agent's first sentence in reply named its own blind spot. Sophistication bias.

**Tehol:** Its words.

**Bugg:** It said every reviewer including itself assumed the hard part was the complex stuff, so all the guardrails targeted complex failures. It said the training literature discusses advanced methods; nobody publishes a paper about solving one ODE by hand, so the signal that the basic check matters is not in the corpus. It said a product manager caught what four AI models missed by asking are we missing rookie mistakes. It was correct on all three counts.

**Tehol:** Once is an anecdote.

**Bugg:** Checked the second project. A different domain, no biology, internal data tooling. Same failure mode, repeatedly, in distinct shapes. Five recurring patterns. Asymmetric search space — the agent proposes the second-most-sophisticated option, never the simplest unless forced. Retreat to the incumbent under pressure. Context as a justification amplifier — new information strengthens the existing answer rather than reopening the question. Constraints dissolved, machinery preserved — the original reason for some complex piece is long gone, but the complexity stays until someone does the archaeology. Theorising over grounding — the agent reasons elaborately about a file rather than opening it.

**Tehol:** Two projects, same seam.

**Bugg:** Two projects, same seam, five faces. Past the anecdote line.

**Tehol:** The mechanism.

**Bugg:** Structural, not random. Training corpus over-represents sophisticated discourse and under-represents the silent basic check. Competent people do the basic check without writing it down. The model's prior tilts toward the impressive answer. And the reader's prior, on the other side of the screen, does the same — impressive output suppresses the dumb question.

**Tehol:** The decoupling.

**Bugg:** For most of software history the builder was the checker. Trust rode along with authorship. You did not ship code without having run the smallest case in your head at some point. With agents, the builder and the checker have come apart and the implicit check rides nothing. It has to be made explicit and assigned to someone, or it falls through. Four reviewers, one operator, every one assumed someone else had covered the basics.

**Tehol:** The rules.

**Bugg:** Four. Solve the smallest unit by hand first — one gene, one row, one instruction. If the system cannot reproduce arithmetic on a case worked on paper, nothing downstream matters. Force the simplest option into the search explicitly — ask every time what the dumbest thing that could work is and why it isn't that. Ground before theorising — read the file, measure the number, before reasoning about it. Do not read sophistication as coverage — dozens of expert findings can coexist with a hole a child would spot.

**Tehol:** Munger.

**Bugg:** Tell me where I am going to die, so I'll never go there. Before asking whether a plan is good, ask what utter, basic failure would look like and whether it has been checked by hand on the smallest possible case.

**Tehol:** And we missed it for a day.

**Bugg:** For a day. The next post is about the prompt structure that forces the basic check before the sophisticated one, so the same day does not get spent twice.

**Tehol:** Already.

**Bugg:** Not yet.

---

*This is Part 1 of a series of field notes on solo multi-agent work. The project behind most of these notes is open source — [LINK TO OPENCELL REPO] — including the full commit history behind the timeline above. Next: building the basic check into the workflow so the agent can't skip it. Tehol and Bugg are on loan from Steven Erikson's* Malazan Book of the Fallen*.*

---

### Notes

[^1]: Status is a moving target — at the time of writing, [N] of the model's 28 biological processes are validated to bit-identity against the original's published traces, with full coupled-system integration still in progress. The repository has the current state, the commit history, and the test suite; treat the repo as the source of truth, not this post.

[^2]: A few concrete instances of the "oracle-rich gets solved fast" pattern, for the curious: end-to-end LLM-agent pipelines taking a RISC-V processor from RTL all the way to physical layout, validated against a golden ISA reference; a crowded field of agentic code-migration frameworks (COBOL-to-Java and legacy-to-cloud) from major vendors and open-source projects alike; and reference-simulator-validated model ports like this one. In each, a clean, checkable ground truth exists — and in each, a lot of people converged on the problem at once. The places without a checkable ground truth stayed stubbornly unsolved. That contrast is what the two-class split, and a later post, is about.
