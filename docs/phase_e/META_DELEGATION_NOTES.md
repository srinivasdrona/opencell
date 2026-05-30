# Meta-Delegation Experiment: A vs B vs C

**Context**: L2.2 data archaeology task (find published Karr ensemble data sources + characterise observable coverage and σ availability). Task is small enough (~10 min for orchestrator-with-web_search) to afford running 3 delegation patterns in parallel as a controlled experiment.

**Goal**: surface reusable insights about multi-agent delegation patterns, analogous to how the dimer-port investigation surfaced the 3-slot prompt architecture.

## The three variants

### A — Chunked map + orchestrator-reduce (baseline)
- **Topology**: 3 codex children in flat parallel (d1/d2/d3), orchestrator reduces.
- **Coordination locus**: orchestrator-side (me).
- **Decomposition**: by source (data registries / open archives / paper supplements).
- **Hypothesis**: predictable, simple, but orchestrator pays context cost for the reduce.

### B — Codex Foreman
- **Topology**: 1 foreman + 3 grandchildren spawned by foreman.
- **Coordination locus**: foreman codex agent (off-orchestrator).
- **Decomposition**: same as A.
- **Hypothesis**: tests whether nested `codex exec` works cleanly; if so, this scales orchestration off the operator entirely.
- **Risks**: nested auth/env, foreman polling complexity, double-compaction surface.

### C — Scout + Synthesizer (heterogeneous)
- **Topology**: orchestrator (me) as cheap scout via `web_search`; 1 codex agent as expensive deep-reader.
- **Coordination locus**: split (scout = me, synthesis = codex).
- **Decomposition**: by phase (discover → validate → extract).
- **Hypothesis**: most token-efficient for research tasks where most URLs are dead-ends and only a few warrant deep reads.

## Measurement axes
| Axis | A (chunked-map) | B (foreman) | C (scout-synth) |
|---|---|---|---|
| Wall time (fire → final doc) | 11 min (longest = d3 at t+651s) | 5.5 min (foreman wrapped at t+330s after 3 grandkids) | ≤30s (synth had exited before first `wait` poll) |
| Codex tokens (sum) | **699K** (d1=118K + d2=355K + d3=226K) | **42K** foreman + 3 grandkids (per-grandkid not separately metered; STATUS sizes ~5-9 KB each) | **187K** (single synth agent) |
| Orchestrator context cost | High — 3 STATUS files to read + reduce | Low — 1 STATUS_b1/b2/b3 to skim, foreman did reduce | Medium — wrote `SHORTLIST.md` from web_search pre-validation, then single doc to consume |
| Sources covered | 3 distinct buckets (WCDB+SimTK+Wayback / Zenodo+Figshare+GitHub / Karr supplements) | Same 3 buckets, but b1/b2/b3 produced narrower per-bucket dumps than A's children | 6 Tier-1 + 2 Tier-2 + 2 confirmed dead-ends (pre-classified) |
| σ values extracted | **8 numeric μ/σ pairs** (d3 pulled real numbers from Karr Tables S1/S2A — unique to A) | 0 (b1/b2/b3 produced source catalogs, no σ extraction) | 0 numeric pairs extracted at this stage (synth scored each source as σ-extractable yes/partial/no, deferred extraction) |
| Final doc quality | Raw — 3 STATUS files, no synthesis (the reduce is orchestrator's job) | Raw — STATUS_b1/b2/b3 are dense markdown tables, no foreman synthesis layer landed | **Polished single artifact** — `L2_2_DATA_INVENTORY_C.md` (15KB) structured by Tier-1/2/dead-end, σ-extractability column, downstream PASS_CRITERIA already drafted |
| Failure modes | d2 spent 3× d1's tokens for arguably less unique output (variance per chunk); d3's σ-extraction tactic was a happy accident, not designed | foreman successfully spawned 3 grandkids and exited cleanly — validates nested `codex exec` capability. But no synthesis pass = same reduce cost still on orchestrator | Scout's pre-validation prevented the synth from chasing the 2 dead ends (WCDB live URL, Cell.com paywall) — the savings show up as 187K vs A's 699K |
| Re-fires needed | 0 | 0 | 0 |

## Findings

**C wins on token efficiency** by ~3.7× over A (187K vs 699K) and on artifact quality (single polished doc vs 3 raw STATUS files). The reason is structural, not random: the scout pre-validation phase (operator's `web_search`, ~free) removed the dead-end-chasing tax that A and B each paid silently inside their codex children.

**A wins on unique-evidence yield**. d3 was the only one of the three patterns that actually opened the Karr Tables S1/S2A and pulled 8 concrete μ/σ pairs. Neither B nor C did this. This was not a designed advantage of A — d3 chose the tactic independently because its scope ("paper supplements") made it the obvious move. If the same instruction had been given to B's b3 or C's synth, they would likely have done it too.

**B validated the foreman capability** (nested `codex exec` works cleanly with `--dangerously-bypass-approvals-and-sandbox`; grandkids inherited env correctly via the launcher). But it did not deliver a quality dividend for this task size. The foreman acted as a job-scheduler, not a synthesizer — it spawned, polled, exited. No reduction layer materialised. For tasks small enough to fit in one codex context, B is overhead.

**Orchestrator-context cost ranking**: B < C < A. B was cheapest because the operator only had to read 3 short STATUS files + the foreman's exit. C cost a single 15KB doc + the upfront web_search pass. A required reading 3 STATUS files of different shapes + assembling a reduced inventory manually (this task is still pending).

**Variance within A is the silent cost**. d1=118K, d2=355K, d3=226K. The 3× spread between d1 and d2 wasn't predictable from the prompt. Chunked-map looks neat from outside but actually has high per-chunk variance because each child decides independently how deep to go.

## Reusable patterns surfaced

1. **Scout-then-deep-read is the default for research tasks** where most candidates are dead ends or paywalled. Operator's `web_search` is essentially free compared to a codex agent; using it to pre-classify Tier-1/Tier-2/dead-end before any codex fire saves 3-4× tokens. Rule of thumb: if >25% of candidate sources are expected to be dead, prefer C.

2. **Chunked-map is justified when sub-areas need genuinely different probing strategies** — not when they're just "divide the URL list in three." A worked because d1 needed Wayback Machine, d2 needed Zenodo API patterns, d3 needed PDF table extraction. Those are different tools. If all three children would have used the same approach, A degenerates into "same agent, run thrice."

3. **Foreman scales only when the foreman has a synthesizer role**. A bare foreman that just spawns + waits + reports back is overhead with no compensating dividend. The foreman pattern starts paying off when the task is large enough that the foreman itself runs out of context and *its* synthesis becomes a meaningful unit of work (think: foreman summarises 8 grandkid outputs into 1 page, orchestrator reads the page). Single-page tasks like this one don't reach that threshold.

4. **`codex_fire.py wait` makes parallel experiments cheap**. Cost of running A+B+C in parallel was ~1 hour wall + ~930K total codex tokens, with auto-notify on completion. This made the meta-experiment itself a low-risk move. Future architectural choices should similarly be A/B-tested when the parallel cost is < 1.5× the single-best estimate.

5. **σ-extraction is its own task and should be a separate phase**, not bundled into "find sources." None of the three patterns reliably produced σ values — only A's d3 did, and only because its scope happened to force PDF reading. The right pattern is probably: scout → triage (C) → extract σ from each Tier-1 (small fanout of specialised extractors, one per source).

## Working inventory

The de-facto working inventory is `meta-l2-2-c/L2_2_DATA_INVENTORY_C.md` (15KB). It will be promoted to `docs/phase_e/L2_2_DATA_INVENTORY.md` (no suffix) once L2.2 work resumes; A's STATUS_d3 numeric μ/σ table will be merged into the Tier-3 column at that time. A's STATUS_d1/d2 and B's STATUS_b1/b2/b3 are kept on their meta-worktrees as raw evidence and do not need promotion.

## Operational lesson for L2.1 fanout

The user is choosing the L2.1 closure pattern next. The clean takeaway from this experiment is **A/B/C are composable, not mutually exclusive**:
- Use **C-style scouting** (operator pre-classifies which RED processes are likely fixable by which pattern) before firing.
- Use **A-style chunked-map** for the deep work (one codex per process), where the sub-areas (each process) truly need independent probing.
- Use **B-style foreman** only if a process's fix is large enough to need its own sub-decomposition (e.g., Metabolism, which is genuinely a multi-day codex task and could justify a foreman that spawns specialists for FBA / mass balance / exchange constraints).
