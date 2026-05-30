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
| Axis | A | B | C |
|---|---|---|---|
| Wall time (fire → final doc) | TBD | TBD | TBD |
| Orchestrator context cost (tokens) | TBD | TBD | TBD |
| Codex token cost (sum across all agents) | TBD | TBD | TBD |
| Final doc quality (subjective) | TBD | TBD | TBD |
| Sources found (count) | TBD | TBD | TBD |
| σ values extracted (count) | TBD | TBD | TBD |
| Failure modes encountered | TBD | TBD | TBD |
| Re-fires needed | TBD | TBD | TBD |

## Outputs
- `docs/phase_e/L2_2_DATA_INVENTORY_A.md` (from variant A, assembled by me)
- `docs/phase_e/L2_2_DATA_INVENTORY_B.md` (from variant B, assembled by foreman)
- `docs/phase_e/L2_2_DATA_INVENTORY_C.md` (from variant C, assembled by synthesizer)
- Diff the three; the union is the working inventory; disagreements flag gaps.

## Findings
*(populated after all three complete)*

## Reusable patterns surfaced
*(populated after analysis)*
