---
title: "Days 42–44: A Trajectory That Compounded, A Rung That Was Always Missing, And A Database That Was Always Supposed To Exist"
date: 2026-06-30
authors: [sdrona]
tags: [opencell, metabolism, FVA, methodology, L1c, wiring-DB, honest-mode]
---

"Where did we land?" Tehol asked.

"Twenty-eight of twenty-eight on a thing we hadn't built." Bugg paused. "Zero of one on the thing that actually matters. And one apology owed to a memory I'd been carrying since Day Thirteen."

"Start with the trajectory."

"Start with the trajectory."

---

"Day Forty-Two was supposed to clean up after Day Forty-One. The pricing-equals-STD fix had landed at the sample level. The W1 gate hadn't moved. The lesson was logged: degenerate LP, measure in the gate's metric space, not in flux space. I was ready to move on."

"And?"

"And I asked the question I should have asked the morning before: if the LP is degenerate, and our vertex drifts by eight million in flux space every tick, what happens if we let the process *run* instead of replaying isolated ticks? Fifty seeds by ten ticks tells you about a hundred independent decisions. One seed for a hundred ticks tells you what happens when each tick's drift compounds into the next."

"You ran a hundred ticks live."

"I ran a hundred ticks live. No replay seeding between ticks, no Karr state injection — let OC pick its own vertex and use its own substrate counts as the next tick's starting state. Same harness as Day-Forty-One, just with the seed feedback closed."

"And?"

"The L1 between OC and Karr's recorded trajectory was four-point-seven million molecules at tick ninety-nine. Tryptophan over-accumulated one thousand two hundred and thirty-four times. Karr's seed-zero trajectory has ninety-four TRP at tick ninety-nine; ours had one hundred sixteen thousand and sixty. TRIOLEIN was five-point-nine times. PHE was two-point-one times. The biology stays viable — every substrate non-negative — but it compounds. Linearly. Like a very patient leak."

Tehol set the quill down.

"That's not a stochastic gate failure."

"That's not a stochastic gate failure. That's a systematic-bias gate failure. Every tick we walk fractionally further from where Karr walked, in a *consistent direction*. The TRP doesn't oscillate around Karr's value; it climbs."

---

"So the FVA reframe."

"Day Forty-Three morning. I'd sketched FVA reframe on Day Forty-Two evening — the idea is: stop asking 'did OC pick Karr's vertex' and start asking 'is Karr's vertex inside OC's feasible range'. Compute the FVA-projected substrate-delta envelope from OC's LP at each tick, check whether Karr's recorded delta sits inside. If yes, OC's LP *could* have produced Karr's answer; the divergence is at vertex selection, not at feasibility."

"It validated."

"It validated decisively. At sample zero-one, five hundred and four of five hundred and four reactions feasible. At five samples crossed with one thousand seven hundred and fifty-five substrate-compartment pairs, eight thousand seven hundred and seventy-five of eight thousand seven hundred and seventy-five feasible. One hundred percent. I wrote DEC-003 documenting why this is the right reframe at L2.2, why the four alternatives we'd considered were worse, what was in scope versus deferred."

"You shipped Part Two."

"I shipped Part Two. Productionized the FVA solver, taught the L2.2 audit harness about a new metric type called `fva_feasibility`, ran the full five hundred sample audit. Verdict PASS. Feasibility fraction zero-point-nine-nine-nine-nine-nine-seven. Eight hundred seventy-seven thousand four hundred ninety-seven pairs of eight hundred seventy-seven thousand five hundred. The scoreboard wanted to read seventeen-of-twenty-two becoming eighteen-of-twenty-two with Metabolism joining the GENUINE column."

"And then?"

Bugg paused for a long moment.

"And then you asked the question."

---

"Which question?"

"You asked, *what does L1c failure even mean if we wired everything correctly? If the wiring is right, L1c can't fail.*"

Tehol picked up the quill again.

"I'd written L1c on Day Thirteen. The integrated-energy-balance gate. We knew Metabolism could write a busy two-and-a-half-megabyte trace and still be collapsing ATP underneath. I had decided then that L1c sat *after* L2, not before, because L2 replay feeds each process recorded ATP from the oracle and the collapse only shows up in chassis-level integration."

"And you deferred it."

"I deferred it. Thirty days. The todo `l1c-atp-collapse-diagnose` is still pending in the session DB from the original entry. `l2c-energy-ledger-gate` was never even started. Every day after Day Thirteen, I added scoreboard rows for L2.x progress while the gate that would have caught the bug that was actually killing the cell sat untouched at the bottom of the backlog."

"What happened when you asked the question?"

"What happened was I went and read MATLAB. Not the paper. Not the design doc. The actual `evolveState.m` and `Metabolism.m` files, side by side with our `karr_metabolism.py`, `karr_metabolism_writeback.py`, `karr_allocation_step.py`, `calc_flux_bounds.py`."

Tehol leaned back.

"And?"

"And I found four wiring bugs. Real ones. In the chassis-integration layer that L1 and L2.1 and L2.2 are structurally incapable of detecting."

---

"Name them."

"A-one, A-two, A-three, A-three-b, A-four. The allocator, the order, the LP bounds source, the post-LP consumption clip, and the compartment merge."

"In English."

"A-one: Karr's allocator over-allocates when supply exceeds demand. Our allocator caps at one-times-the-request. In low-demand ticks, Karr's processes each get more than they asked for, OC's processes get exactly what they asked for. Most processes don't consume their over-allocation, so this is mostly benign — except where the over-allocation feeds into LP bounds the next tick.

"A-two: Karr randomizes process iteration order per tick using `randStream.randperm`. We use Vivarium's deterministic topological order. End-state mass balance is order-independent so this doesn't break conservation — but it changes the running pool state mid-tick if any process reads `mets.counts` instead of `mod.substrates`. Benign in practice for our current ports, but the door is open.

"A-three: Karr's metabolism LP gets its bounds from `mod.substrates = allocation` — the LP can only see what the allocator gave it. Our metabolism LP gets its bounds from `_sub_state`, the full cytosolic pool tracker. In chassis context, our LP has a larger feasible region than Karr's, picks a different vertex, produces different chemistry.

"A-three-b: Same module, worse problem. Our LP solves over the pool, produces a stoichiometrically-consistent substrate delta. Then we cap *only the consumption entries* to the allocation budget, leaving the production entries alone. So a reaction that turned ATP plus H2O into ADP plus Pi plus H at flux ten, with allocation ATP equal to six, gets capped to consume six but still produces ten ADP, ten Pi, ten H. Net mass into the pool: plus fourteen. Every tick. Over five thousand ticks: ATP drains anyway because the minus-six still applies, while ADP and Pi and H accumulate. The Day-Thirteen ATP collapse, in three lines of mass-balance arithmetic.

"A-four: The shared-pool projection. Our metabolism writes a five-eighty-five by three delta — substrates by compartments. Then `project_to_flat_per_wid` sums across compartments before publishing to the shared pool. Next tick, the metabolism process re-syncs from shared and applies all delta to cytosol. Extracellular and membrane substrates silently migrate to cytosol over time. The Day-Forty-Two TRP one-thousand-two-hundred-thirty-four-times signature, in the call graph."

Tehol said nothing for a long moment.

"None of those would show up in L2.2 replay."

"None of them would show up in L2.2 replay. Replay seeds the process with Karr's recorded state every tick — no allocator engagement, no shared-pool projection, no cross-tick state carry. L2.2 verifies that the process function, given Karr's input, produces Karr's output. It does not verify that the chassis, given an initial state, evolves like Karr's chassis. Those are different gates. We had one and not the other. I had spent thirty days writing scoreboards that conflated them."

---

"And the FVA reframe?"

"The FVA reframe is honest at the level it operates. Karr's vertex *is* feasible in OC's LP — that's a mathematical fact and the eight hundred seventy-seven thousand four hundred ninety-seven of eight hundred seventy-seven thousand five hundred confirms it empirically. The reframe accurately represents 'this LP could produce this answer'. What it does *not* represent is 'this chassis does produce this trajectory'. Those are different claims."

"You downgraded it."

"I downgraded it. DEC-003 stays committed. The Part-Two code stays committed. The scoreboard does not read eighteen-of-twenty-two. It reads seventeen-of-twenty-two with a note that Metabolism's per-tick LP-vertex feasibility is verified and the chassis claim is explicitly deferred to L1c."

"That's the third scoreboard reframe this month."

"It's the third scoreboard reframe this month. Each one was a step closer to honest. Each one cost a day of un-claiming something we'd been claiming. I'd rather under-claim now than mis-claim and pay for it in L3 or L4."

---

"And the database."

"And the database. You asked back on Day Twenty-something whether we needed one. I said the per-process TOMLs were enough. I was wrong. The TOMLs catalog state shapes — which WIDs each process touches, what tensor shape each observable has. They do not catalog wiring — what each process *does* with those substrates. Consume formulas, produce formulas, allocator request rules, compartment routing, unit conversion chains, inter-process dependencies, MATLAB-to-OC method correspondence. The wiring surface is exactly where the four bugs live. Without indexing that surface, every audit becomes an ad-hoc grep."

"So we built one."

"So we built one. Day-Forty-Three evening, after the audit. Schema design via gpt-5.4-mini codex with five decision cards: YAML over TOML, one file per process over a single combined file, string-typed symbolic formulas over structured ASTs, nested method-bindings under method names, per-row semantic versioning. Metabolism authored as the worked example. Five gaps caught in review — missing `symbol` fields on anchors, incomplete `provenance` blocks, bloated `dependencies` lists where Metabolism appeared on both sides — fixed in a follow-up pass."

"Twenty-seven more rows."

"Twenty-seven more rows. Day-Forty-Four. Fired the codex fleet."

Tehol picked up the quill.

"And?"

"And seven of nine died in the first wave."

---

"Same failure mode every time. *Stream disconnected before completion. Response.failed event received.* At twenty-six seconds. At fifty seconds. At a minute. Two survivors out of nine, both light tasks. I assumed Azure concurrency cap and you said *I run ten at a time on a different machine*. So I dug."

"And?"

"And the codex hooks. The `~/.codex/hooks.json` on this machine had four entries pointing at `observer.exe` — PreToolUse, PostToolUse, PermissionRequest, SessionStart, Stop. I invoked the binary directly. It took thirteen-point-eight seconds to return, and then exited non-zero with `parse: unexpected end of JSON input`. Every codex tool call was triggering two of those hooks. Twenty-seven seconds of overhead per tool. Codex's internal timeout fires at thirty seconds for the response stream. By the time the second hook returned the model had already given up."

"You disabled them."

"I disabled them. Renamed `hooks.json` to `hooks.json.observer-broken-2026-06-30` and wrote a stub `{\"hooks\": {}}`. Re-fired solo. Translation row completed cleanly in twenty-six minutes, two hundred and nine thousand tokens, one commit. The fix was right. Stored the diagnostic as a user-scope memory so future sessions check this before delegating."

"Then parallel."

"Then parallel. With hooks off, six concurrent died at six of six — still hitting stream disconnects, just at lower frequency. The other machine you mentioned must have a different rate-limit posture; this machine, empirically, tops out around two concurrent codex agents on gpt-5.4-mini with the same Azure deployment. I built a watcher script that fires two at a time, waits for both to exit, retries up to three times per failed task, walks through the queue. Twenty-three tasks queued. About a third died on first try. About half of those died on retry. The watcher's exponential backoff (zero exponential backoff actually, just three attempts at the same configuration) caught the rest. Six tasks hit permanent-failed after three retries. I routed those through a serial watcher — one at a time, same model, no parallelism — and they all eventually committed. Wall time end-to-end was about five and a half hours, mostly unattended."

"And one bug."

"And one bug. The serial watcher had a queue-arithmetic error. When the queue dropped to a single item, my slice `queue[1..count-1]` evaluated as `queue[1..0]` which PowerShell treats as a reversed range, so the queue never emptied. RibosomeAssembly committed twenty times. Each commit was valid — the worktree was idempotent — just redundant. Squashed before merge."

Tehol set the quill down.

"Twenty-eight rows."

"Twenty-eight rows. Plus the schema, the generator, the cross-row consistency checker, the three pytest tests. The generator ran clean on the merged main. Cross-row check reported fifty-three reciprocal dependency mismatches, two cyclic ordering violations, twenty-seven of twenty-eight rows failing row-level validation on schema-date and provenance fields."

"You expected that."

"I expected that. Each row was authored before the schema-gap-fix landed in any other worktree — they all worked off the pre-fix `_schema.yaml`. Mass remediation script: schema-date, provenance, malformed unit-conversion anchor `lines`, one row's compartment-routing logic typos. Row-level fail count went twenty-seven to zero in one commit. Then a sibling codex on the reciprocal mismatches — fifty-three to zero, twenty-five rows touched. Then a tiny codex on the cyclic ordering — Karr's `evolveState.m` line forty-eight explicitly enforces `tRNAAminoacylation < Translation`; one of our two rows had the direction inverted. One file edited."

"Final state?"

"Validator reports zero reciprocal mismatches, zero cyclic ordering, zero missing rows. Verdict PASS. All thirty-something commits merged into main and pushed to `srinivasdrona/opencell`. Day-Forty-Four EOD scoreboard has a new row — *per-process wiring DB: twenty-eight of twenty-eight PASS* — alongside the now-honest L1/L2.x rows."

---

"Bugg."

"Yes."

"What does the wiring DB actually buy us?"

"It buys us the substrate for L1c. Every row has the per-process consume formula, produce formula, allocator request rule, compartment routing — all in a machine-readable schema. L1c is going to sum those across the chassis at each tick and assert mass-and-energy conservation against the actual trajectory. Without the DB, that gate is twenty-eight hand-written instrumentations. With the DB, it's one summation over a YAML join."

"Tomorrow."

"Tomorrow. Day-Forty-Five. The L1c gate design starts. We have the substrate. We have the decision. We have the catalog of four wiring bugs already documented in twenty-eight rows as `known_deviations`. The first thing L1c will do is fail loudly on every one of them, and we'll fix them in priority order while the gate watches."

"And the lesson."

"The lesson is the one you handed me. A green at a gate that doesn't measure the property you care about is worse than a red. The L2.x scoreboard had been giving me confidence that the system was working when the system, at the chassis layer, had been broken since the day we wired it. The gates I was running were the ones that gave clean green-or-red signal in replay mode. The gate that would have caught the actual bug was the one I'd deferred for thirty days because diagnosing ATP-balance over five-thousand-tick autonomous runs is unrewarding work with no clean verdict at the end."

Tehol picked up the quill.

"The infrastructure cosplay rule."

"The infrastructure cosplay rule. You wrote it down in the PM OS preferences three months ago. *Don't build the system because it's tractable while the actual work is messier.* I'd been building L2.x scoreboards because L2.x produces clean integers. The actual work was L1c. The actual work has been L1c for thirty days. Tomorrow I'll do it."

"And the FVA reframe?"

"The FVA reframe stays in the scoreboard, with its note. It's accurate at what it measures. The error wasn't in writing it; the error was in letting it look like a green box on the chassis row when it's a green box on the per-tick row. I downgraded it. The work shipped. The claim shrank to fit."

---

**Honest scoreboard (Day-44 EOD)**

| Gate | What it measures | Day-41 EOD | Day-42 EOD | Day-44 EOD |
|---|---|---:|---:|---:|
| L1 firing | trace bytes > threshold | 28/28 | 28/28 | 28/28 |
| **L1c integrated energy balance** | mass + energy conservation across chassis ticks | NOT BUILT | NOT BUILT | **NOT BUILT** (Day-45 task) |
| L2.0 schema | ports_schema vs karr_obs | 28/28 | 28/28 | 28/28 |
| L2.1 GENUINE | bit-identity, isolated replay | 19/28 | 19/28 | 19/28 |
| L2.2 VERIFIED_GENUINE | W1 vs null, isolated replay | 17/22 | 17/22 | 17/22 |
| L2.2 NOT_WIRED | infrastructure missing | 2 | 2 | 2 |
| L2.2 VERIFIED_FAIL | Metabolism W1=161 | 1 | 1 | 1 (DEC-003 reframes as per-tick LP-vertex feasibility — does NOT change chassis claim) |
| L2.5 honest PASS | shared-pool composition | 15/256 | 15/256 | 15/256 |
| **Per-process wiring DB** | chassis-layer integration audit substrate | NOT BUILT | NOT BUILT | **28/28 PASS ✅** |

**Three days, eighty-five commits, one methodology decision, one new gate substrate, four wiring bugs documented in twenty-eight rows, one Day-Thirteen apology owed. Day-Forty-Five: L1c.**

---

*Postscript, for the record.*

*Two cross-project decisions logged today: `2026-06-29 | opencell | l1c-skipped-lower-rung-greens-misread`, naming the methodology failure that let four chassis wiring bugs accumulate unaudited for thirty days while the L2.x scoreboard ticked upward; and `2026-06-29 | opencell | dec-003-lp-degeneracy-fva-reframe`, ratifying the FVA reframe as the right L2.2 metric for LP-degenerate processes while explicitly noting that per-tick LP-vertex feasibility does not imply chassis correctness. One user-scope memory stored: before delegating to codex CLI, check `~/.codex/hooks.json` for slow PreToolUse/PostToolUse hooks — a 13.8-second observer.exe hook on this machine killed seven of nine parallel codex agents on Day-Forty-Four morning. Files touched at the canonical level: `decisions/dec-003-lp-degeneracy-fva-reframe.md` (9.6KB), `data/schemas/per_process_wiring/` (28 rows + schema + generator + tests + combined file + summary + triage doc + remediation script, ~470KB total across the directory), `opencell/m1/fva.py` (extended with FVA template solver + audit-harness adapter), `docs/phase_f/WIRING_DB_SUMMARY_2026-06-30.md` + `WIRING_DB_RECIPROCAL_TRIAGE.md` (the audit artifacts), `plan.md` and `docs/phase_e/PROCESS_STATUS_ALL_29.md` (re-framed scoreboards). Eighty-five commits pushed to `srinivasdrona/opencell` main between commits `cb8a128` and `78c5140`. Tehol Beddict and Bugg are characters from Steven Erikson's Malazan Book of the Fallen, on loan and gratefully returned.*
