# Substrate-Leak Diagnostic Probe (BLOCK-RELEASE v1.0)

## Mission
Localize the source of the **2.6 million-unit substrate leak** in chassis_v6 over a 100-tick run. This is **diagnostic instrumentation, not a fix**. You produce evidence; humans decide the fix in the next turn.

## Critical context — read before doing anything

The previous diagnostic loop **failed**. Read these in order before writing any code:

1. `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` entry `allocation-bypass-not-cascade-root-cause` (2026-05-23, top of file) — explains why the rna_decay/host_interaction hypothesis was REFUTED by direct evidence.
2. `docs/phase_e/E1_findings_pre_merge.md` — the original symptom report (ATP drains 315 units/tick from tick 100 onward; dNTPs go to zero; mass goes negative).
3. `docs/design/allocation_consumer_enrollment.md` (committed `5fefe4a`) — Bucket A's design doc + the negative result it produced.
4. `opencell/vivarium/karr_allocation_step.py` — the KarrAllocationStep request/grant cycle.
5. `opencell/vivarium/karr_composite.py` — full v6 wiring; identifies who participates in the allocation cycle and who doesn't.

**Empirical evidence from Bucket A's 32400-tick before/after run** (DO NOT re-derive these from theory):
- `atp_pool`: 1.0 → -43,750 by tick 100 → -5.75M by tick 16200 → -10.21M by tick 32400
- `gtp_pool`: 1.0 → -43,749 by tick 100 (mirrors ATP exactly)
- `dntp_pool_total`: 4.0 → 0 by tick 100, never recovers
- `cell_dry_mass_g`: 8.2e-16 → -3.4e-14
- Net substrate delta across shared store after 1000 ticks: **-2,621,067.87 units** (Codex Bucket A measured this directly)
- Allocation integrity: max_overalloc=0.0, no negative allocations, 0 overallocation violations → **the leak is NOT in the allocation cycle itself**

**Implication**: substrate(s) are being consumed (or counted as consumed) **outside** the request/grant cycle, OR there's double-counting, OR a process is writing absolute values instead of deltas, OR a process touches the shared substrate store directly without going through allocation.

## Hard guardrails

1. **NO chassis-process behavioral changes.** You may add instrumentation, logging, debug prints, or a new diagnostic module. You may NOT change any process's actual logic (request amounts, consumption math, FBA bounds, kinetic rates, etc.).
2. **Read-only on production code paths.** Decorate, wrap, or intercept — do not replace.
3. **No new dependencies.** Use stdlib + numpy + what's already in the venv.
4. **Short-tick run only.** Use 100 ticks (leak is visible by tick 100). Do NOT run 32400 ticks. Each diagnostic run should complete in under 2 minutes.
5. **Report findings honestly, including null results.** If you can't localize it, say so with the data you have. Do NOT confabulate a culprit.

## Token budget
**50,000 tokens**. Be ruthless about scope. Skip exploratory tangents.

## Checkpoint structure

### CP1 — Inventory of substrate touch points (no code yet)
Read every `karr_*.py` module. For each process, classify on these axes and write a table to `docs/diagnostics/substrate_touch_inventory.md`:

| Process | Reads substrate store | Writes substrate store | Goes through allocation | Touches shared store directly | Notes |

The four key questions per process:
- (a) Does it read raw `substrates` state, or only `substrates_allocated[process_name]`?
- (b) Does it return updates that touch `substrates` topology, or only `substrates_allocated`?
- (c) Is it enrolled in `KarrAllocationStep.requesters`?
- (d) Does its update arithmetic look like a delta (`-N`) or an absolute assignment (`= N`)?

Commit as **cp1: substrate touch inventory**.

### CP2 — Instrumented short-tick run
Build a diagnostic script `scripts/diagnose_substrate_leak.py` that:
1. Runs chassis_v6 for exactly 100 ticks
2. Before each tick, snapshots the shared `substrates` store
3. After each process's `next_update` (use a wrapper / monkey-patch), records the **delta this process applied to the substrate store**, per-substrate
4. After each tick, also records the **total store delta** (final - initial) and reconciles it against the **sum of per-process deltas** — the difference is the "unattributed delta"

Output: a long-form CSV `data/diagnostics/per_process_substrate_deltas_100t.csv` with columns:
`tick, process_name, substrate, delta`

Plus a pivoted summary `data/diagnostics/per_process_substrate_deltas_pivot.csv`:
`process_name, total_atp_delta_100t, total_gtp_delta_100t, total_dntp_delta_100t, total_h2o_delta_100t`

Commit as **cp2: per-process substrate delta instrumentation**.

### CP3 — Reconciliation analysis
Run the diagnostic. Produce `docs/diagnostics/substrate_leak_report.md` containing:

1. **Top 5 ATP consumers by total delta over 100 ticks** (table, sorted by absolute value)
2. **Top 5 dNTP consumers** (same)
3. **Reconciliation**: for each substrate (ATP, GTP, CTP, UTP, dATP, dGTP, dCTP, dTTP, H2O, AAs):
   - Tick-100 store value (observed)
   - Tick-0 store value
   - Sum of per-process deltas
   - **Unattributed delta** = (observed change) − (sum of per-process deltas)
   - **If unattributed delta is nonzero, that is the leak source** (substrate is being changed outside any process's `next_update`, OR a process is mutating state in-place rather than returning a delta)
4. **Allocation cycle reconciliation**: for each requester, compare `requested_amount` (from KarrAllocationStep) against `actual_consumed_delta` (from your instrumentation). Differences indicate either:
   - Process consuming more than allocated (over-spending)
   - Process consuming via a path that bypasses allocation
5. **Top suspect**: based on the data, name the process(es) most likely responsible. Cite the rows.

Commit as **cp3: substrate leak report**.

### CP4 — Hypothesis test (optional, only if CP3 is inconclusive)
If CP3 identifies a clear culprit, STOP. Write your findings into STATUS.md.

If CP3 is inconclusive (e.g., all per-process deltas sum cleanly to the observed change, meaning the leak is in the integration step itself or in topology setup), then run ONE targeted secondary probe to disambiguate. Examples:
- Per-store-port instrumentation (capture deltas at the port-binding level, not just the process level)
- Pre/post-tick state diff of the FULL state tree (not just substrates) to detect cross-store contamination
- Check whether `substrates_allocated` carries values across ticks when it shouldn't

DO NOT exceed 15k tokens on CP4. Bail and report null result if not productive.

Commit as **cp4: secondary probe (if needed)**.

## Acceptance criteria

You succeed if STATUS.md contains, at minimum:
1. The per-process delta table for ATP and dNTPs
2. The unattributed-delta number per substrate (could be 0 — that's a finding too)
3. A clearly stated **top suspect process(es)** OR an honest "leak source is not in any process's next_update" conclusion
4. A specific actionable next step for the human (e.g., "look at `karr_metabolism.py` line 234 where FBA bounds are applied directly to the substrate port", or "check Vivarium store binding configuration for substrates", or "the leak is in `karr_observability_step.py` because it's the only process that...")

## Forbidden conclusions
- "I added more allocation discipline" (NO — that was Bucket A's failed approach)
- "I fixed the rates" (NO — rates are v1.0-frozen)
- "Tests pass now" (irrelevant — they passed before the leak was diagnosed; tests are not the oracle here)

## Run sequence reminder
Use the WSL venv for any pytest runs (`source .venv-wsl/bin/activate`), but the diagnostic script can run from any Python env that has numpy + vivarium-core (both are in `.venv-wsl`).

## When you're done
Write STATUS.md with the full reconciliation table and your top-suspect call. Commit. Exit.
