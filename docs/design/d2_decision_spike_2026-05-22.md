# D.2 Decision Spike — Vivarium Architecture Probe

| Field | Value |
|---|---|
| Purpose | Resolve 5 Vivarium-level architectural questions empirically, so the A-vs-C strategy decision rests on evidence not analysis |
| Target effort | **1 focused day** (8 hours wall). Stop at end-of-day even if incomplete; partial evidence is better than no evidence |
| Branch | `agent/d2-spike` (create from `main`, NOT from `agent/d2-design-v3`) |
| Antecedents | `docs/design/d2_v3_critique_2026-05-22.md`, `docs/design/d2_complex_assembly_v4.md`, the two strategy critiques (Opus 4.6 → A, GPT-5.5 → C) |
| Output | `artifacts/d2_spike_findings.md` (decision matrix mapping spike results to A or C) |
| Decision criterion | After spike, operator picks A or C using the decision matrix in §7 |

---

## 0. What this spike is NOT

- **Not a v5 design.** Do not write design-doc text or modify `d2_complex_assembly_v4.md`.
- **Not an implementation.** Code written during the spike is throwaway, lives only in `experiments/d2_spike/`, and does not need tests or polish.
- **Not a Karr-fidelity decision.** That is a separate operator-level call; see §6 for the framing question, but the spike does NOT resolve it.
- **Not a regression test.** Existing tests must not break, but the spike does not add to the test suite. If something fails accidentally, document and proceed.

---

## 1. The 5 questions (both v4 critique reviewers, independently)

Both Opus 4.6 and GPT-5.5 strategy critiques identified these 5 questions as the real risk regardless of strategy choice. Resolving them empirically eliminates the analysis gap.

| # | Question | Why it matters for A vs C |
|---|---|---|
| Q1 | Does Vivarium's `_updater: accumulate` apply correctly when a process writes signed integer deltas across multiple ticks? | Both strategies depend on accumulate semantics; if it doesn't work as v4 assumed, C must redesign and A's stub avoids the question entirely |
| Q2 | Can a Vivarium `Step` (or `Deriver`) read post-update absolute values, compute corrections, and emit `set` updates that override `accumulate` writers? | The "reconcile_d2" pattern in v4 §5.3 lives or dies on this. If yes, both A and C have a workable chassis pattern. If no, C must invent a new pattern; A's stub doesn't need it |
| Q3 | Within one Vivarium tick, does Process A see Process B's just-emitted updates, or only start-of-tick state? | v4 §5.4 claimed M2/M3 "run first"; GPT-5.5 said this is empirically false. Confirm definitively — affects every chassis-coupling design from here forward |
| Q4 | Can the existing `substrates.{wid}` flat topology be migrated to `substrates.counts.{wid}` nested topology (or vice versa) without breaking M1/M2/M3 tests? | v4 doc drifted into nested; current chassis is flat. Need to know if migration is 1 hour, 1 day, or 1 week before committing to either |
| Q5 | What is the realistic effort to add a third process (e.g., a trivial ProteinDecay stub) to the chassis composer, including ports + topology + smoke test? | Option C assumes "joint chassis composer" — verify the effort scales linearly with process count, not combinatorially |

---

## 2. Spike structure (5 probes, ~90 minutes each)

Each probe is **standalone and self-contained**. If a probe hits an unexpected blocker, document the blocker in `artifacts/d2_spike_findings.md` and move to the next probe. Do not let one probe consume more than 90 minutes.

All code lives under `experiments/d2_spike/`. **No edits to `opencell/`, `tests/`, or any existing file** except `artifacts/d2_spike_findings.md` (the report) and `experiments/d2_spike/*` (new dir).

### Probe 1 — `_updater: accumulate` semantics (90 min)

Goal: Build a 30-line Process that writes signed deltas to a single integer port across 5 ticks. Verify the Counter math actually works the way v4 §3.6 assumes.

```python
# experiments/d2_spike/probe1_accumulate.py
from vivarium.core.process import Process
from vivarium.core.engine import Engine

class SignedAccumulator(Process):
    name = "signed_accumulator"
    defaults = {"deltas_per_tick": []}

    def ports_schema(self):
        return {"store": {"x": {"_default": 100, "_updater": "accumulate", "_emit": True}}}

    def next_update(self, timestep, states):
        step = int(self.parameters.get("_step", 0))
        deltas = self.parameters["deltas_per_tick"]
        d = deltas[step] if step < len(deltas) else 0
        # IMPORTANT: read whether parameters is mutable per-step (Sonnet 4.6 flagged this as a v4 bug)
        self.parameters["_step"] = step + 1  # does this actually persist?
        return {"store": {"x": d}}

# Test: x starts at 100, deltas = [+5, -3, +0, -10, +20], expect x = 112 after 5 ticks
```

**Concrete observations to record:**
- Does `x` end at 112? (Yes/no)
- Does `parameters["_step"]` persist across ticks, or get reset? (This resolves Sonnet 4.6's RNG-bug finding from v4)
- What does Vivarium do if a Process writes `0` — is it elided from the update, or applied as accumulate-by-zero?
- Test with two SignedAccumulator instances writing to the SAME port: do their deltas sum, or does one overwrite?

**Decision implication:**
- If `accumulate` works as v4 assumed → C is structurally viable; A is too
- If `accumulate` does NOT sum correctly across processes → C's joint composer must use a different pattern; A's stub-only approach avoids the question

### Probe 2 — `Step` / `Deriver` for post-update reconciliation (90 min)

Goal: Build a minimal Vivarium Step that reads `protein.counts` after a Process has written to it, computes a correction, and emits a new update. Determine whether the "reconcile_d2 deriver" pattern in v4 §5.3 is implementable at all.

```python
# experiments/d2_spike/probe2_step.py
# Test the actual Vivarium Step semantics (NOT Deriver, which v4 used but project doesn't use)
from vivarium.core.process import Process, Step
from vivarium.core.engine import Engine

class M3StubSet(Process):
    """Mimics M3 — uses _updater: set to write protein counts."""
    name = "m3_stub_set"
    def ports_schema(self):
        return {"protein": {"counts": {"A": {"_default": 100, "_updater": "set"}}}}
    def next_update(self, timestep, states):
        return {"protein": {"counts": {"A": 200}}}  # set to 200 every tick

class D2StubConsumer(Process):
    """Writes consumption to a separate port."""
    name = "d2_stub_consumer"
    def ports_schema(self):
        return {
            "protein": {"counts": {"A": {"_default": 100, "_updater": "set", "_emit": False}}},  # read-only
            "d2_consumed": {"A": {"_default": 0, "_updater": "accumulate"}}
        }
    def next_update(self, timestep, states):
        return {"d2_consumed": {"A": 10}}  # always consume 10

class ReconcileD2(Step):  # or Deriver, test both
    """After M3 + D2 both write, subtract d2_consumed from protein.counts."""
    name = "reconcile_d2"
    def ports_schema(self):
        return {
            "protein": {"counts": {"A": {"_updater": "set"}}},  # final authoritative value
            "d2_consumed": {"A": {"_updater": "set"}}            # reset to 0
        }
    def next_update(self, timestep, states):
        current = states["protein"]["counts"]["A"]
        consumed = states["d2_consumed"]["A"]
        return {
            "protein": {"counts": {"A": current - consumed}},
            "d2_consumed": {"A": 0}
        }
```

**Concrete observations to record:**
- Does the Step see the post-Process state, or start-of-tick? (Critical for v4 §5.4 claim)
- Can a Step override an `accumulate` port with a `set` value? (v4 assumed this works; verify)
- Does the topology need explicit flow declarations between Process and Step, or does Vivarium handle ordering automatically?
- What is the actual sequence: does `M3StubSet.set(200)` happen before or after `D2StubConsumer.accumulate(d2_consumed += 10)`? And where does `ReconcileD2` fit?
- After 5 ticks with d2_consumed += 10 each tick, what is `protein.counts.A`?
  - Expected if reconciliation works: 190 (M3 sets to 200; reconcile subtracts 10)
  - If reconciliation lags by one tick: 200 (M3 sets; reconcile subtracts from previous state)
  - If reconcile cannot override set: 200 (M3 wins)
  - If something weirder: document

**Decision implication:**
- If Step can cleanly reconcile → A's stub design is irrelevant to chassis (any chassis works); C's joint design has a working primitive
- If Step CANNOT cleanly reconcile → A still works (no reconciliation needed for stub); C must redesign the entire chassis-composition pattern

### Probe 3 — Same-tick visibility ordering (60 min)

Goal: Settle the v4 §5.4 dispute. Does Process B see Process A's update within the same tick, or only at t+1?

Use the Process pair from Probe 2 (M3StubSet + D2StubConsumer). Add logging to D2StubConsumer's `next_update`:

```python
class D2StubConsumer(Process):
    def next_update(self, timestep, states):
        observed = states["protein"]["counts"]["A"]
        print(f"  D2 observed protein.counts.A = {observed}")
        return {"d2_consumed": {"A": 10}}
```

**Concrete observations to record:**
- Tick 0: initial value? (100)
- Tick 1: observed value? (100 if start-of-tick semantics; 200 if M3-runs-first semantics)
- Iterate over 5 ticks, log each
- Does process ordering depend on insertion order in the composer? Try both orders.

**Decision implication:**
- If start-of-tick semantics (likely per GPT-5.5) → v4 §5.4 was wrong; both A and C must accept one-tick lag is the only option
- If process-order-dependent → both options have a knob to tune; doc the rules

### Probe 4 — Substrate topology migration cost (90 min)

Goal: Determine whether the chassis can be migrated from flat `substrates.{wid}` to nested `substrates.counts.{wid}` (or whether v4 should align to the existing flat form).

Three sub-tasks:

1. **Measure the migration surface (15 min):**
   ```bash
   wsl -e bash -lc "cd /mnt/e/opencell && grep -rn '\"substrates\"' opencell/ tests/ --include='*.py' | wc -l"
   wsl -e bash -lc "cd /mnt/e/opencell && grep -rn 'substrates\\.' opencell/ tests/ --include='*.py' | wc -l"
   ```
   Record the count of references. A handful = trivial; hundreds = significant.

2. **Probe an alternative path (30 min):** Can a NEW process write to a nested `substrates.counts.{wid}` while existing processes write to flat `substrates.{wid}` IN THE SAME CHASSIS? Build a 20-line test composer with both patterns side-by-side. Does Vivarium accept the mixed topology?

3. **Decision (45 min):** Document the three options:
   - (a) Force-migrate everything to nested (cost: N hours, blocking)
   - (b) Use mixed topology (cost: documentation tax, no migration)
   - (c) Force-align v4 design to flat (cost: doc-only edit, free)

**Decision implication:**
- If (c) is cheap and acceptable → both A and C should just align to flat; topology question dissolves
- If (a) or (b) is required → C must absorb the migration as a phase; A's stub still avoids the question

### Probe 5 — Third-process addition cost (60 min)

Goal: Verify Option C's "joint composer covers 3 processes" assumption by adding one more process to the existing chassis composer.

Steps:
1. Read `opencell/vivarium/karr_composite.py` to map the composer pattern
2. Create a NEW trivial process `experiments/d2_spike/probe5_protein_decay_stub.py` that does literally nothing (`next_update` returns `{}`) but registers a `complex.counts.{wid}` port
3. Add it to a COPY of the composer at `experiments/d2_spike/karr_composite_4process.py`
4. Run the chassis for 5 ticks; verify no errors
5. Record: how many LOC changed in composer? How many new ports? Any topology surprises?

**Decision implication:**
- If adding a 4th process is genuinely linear-cost → C's "joint composer" claim holds
- If adding a 4th process exposes ordering/topology surprises → C's design must absorb them; A's incremental approach gets a real cost penalty too

---

## 3. Out-of-scope safety rules

These rules protect the project state during the spike:

1. **Do not modify** `opencell/`, `tests/`, `data/`, `plan.md`, `SESSION_CONTEXT.md`, or any committed `docs/design/*.md`. The spike is read-only against project state.
2. **Do not run** `pytest tests/` — the existing test suite must not be touched. Smoke-test your spike code with throwaway scripts in `experiments/d2_spike/`.
3. **Do not log to** `data/provenance/llm_interactions.jsonl` from the spike. The spike's outputs are read by the operator; if any LLM-mediated calls happen during the spike (e.g., agent assistance), log those AFTER the spike completes when the decision is being recorded.
4. **Branch discipline:** `git checkout main && git pull && git checkout -b agent/d2-spike`. Single commit on the spike branch. Do NOT merge to main.
5. **No `.venv` reinstall.** Use existing `/mnt/e/opencell/.venv-wsl` per the WSL execution rule in `copilot-instructions.md`.
6. **Stop at 8 hours.** If probes 1-3 are done but 4-5 incomplete at hour 8, write partial findings and stop. Partial findings + honest gap-flags > forced completion with bad data.

---

## 4. Required output — `artifacts/d2_spike_findings.md`

This file is the **only thing the operator reads** after the spike. Make it self-contained.

Required sections:

```markdown
# D.2 Decision Spike — Findings (2026-05-22)

## TL;DR
One paragraph: what did we learn that changes the A-vs-C decision?

## Probe 1 — Accumulate semantics
- Observation 1: ...
- Observation 2: ...
- Decision impact: A favored / C favored / no impact

## Probe 2 — Step reconciliation
(same structure)

## Probe 3 — Same-tick visibility
(same structure)

## Probe 4 — Substrate topology
- Migration surface (LOC count): N references in M files
- Mixed topology test result: works / breaks / partial
- Recommended path: (a) / (b) / (c) with rationale

## Probe 5 — Third-process addition
- Composer LOC diff: N lines
- Topology surprises: none / list them

## Surprises (NOT in the original probe plan)
Anything unexpected found during the spike. These are often the most valuable findings.

## Time accounting
Probe 1: actual minutes
Probe 2: ...
Total: ...
Probes skipped/abandoned: ...

## A-vs-C decision recommendation
**My recommendation (the spike runner):** A / C / cannot decide
**Reasoning** (one paragraph)
**Evidence the operator should review before deciding** (bullet list)
```

---

## 5. After the spike — operator decision flow

When the spike runner returns the findings file, the operator (or next agent session) does:

1. Read `artifacts/d2_spike_findings.md` end-to-end
2. Apply the decision matrix in §7
3. If A: write D.2-stub design (1 day) on a new branch
4. If C: write joint closed-loop design on a new branch
5. Either way: mark this spike todo done; create the next-phase design todo
6. Log the decision via `scripts/log_llm_interaction.py` with `--linked-todo d2-decision-spike` and `--supersedes` linking to the 4 v4 critique entries (this spike supersedes the inconclusive critique state)

---

## 6. The Karr-fidelity question (operator must answer separately)

The spike does NOT decide this. Both Opus 4.6 and GPT-5.5 noted the real strategic decision tree is:

```
Is D.2 a faithful Karr reproduction (greedy assembler + decay loop)?
├── YES → Option C is correct (need ProteinDecay in the loop)
└── NO  → Option A works (D.2 can be a target-clamped controller)
```

The operator should hold this question consciously while reading the spike findings. The spike informs the architectural cost of each option; it does not answer whether Karr-faithfulness is a hard requirement for this project.

---

## 7. Decision matrix (post-spike)

| Probe outcome | Implication for A | Implication for C | Pick |
|---|---|---|---|
| Probe 2: Step CAN reconcile cleanly | A's stub avoids it; C has working primitive | Both viable | Either |
| Probe 2: Step CANNOT reconcile | A's stub avoids the problem | C must redesign chassis pattern | **A** |
| Probe 3: Same-tick visibility = start-of-tick (lag = default) | v4 §5.4 wrong; both options must accept lag | Same | **Either** |
| Probe 4: flat topology is fine | Both can use flat; topology dissolves | Both can use flat | **Either** |
| Probe 4: nested topology required, migration is 1+ day | Stub avoids migration | C absorbs migration as additional cost | **A** |
| Probe 5: 4-process composer adds LOC linearly | A's incremental cost matches C's | C's joint composer cost is real but bounded | **Either** |
| Probe 5: 4-process composer hits topology surprises | A's incremental approach hits same surprises later | C's joint design absorbs surprises early | **C** |
| ANY probe times out and decision is ambiguous | Default to A (lower reversibility cost) | — | **A** |

If multiple rows fire opposite directions, prefer **A** (matches Opus 4.6 recommendation; lower reversibility risk; can pivot to C later if D.2-real reveals architectural issues).

---

## 8. Logistics

- **Branch:** `agent/d2-spike` from `main` (NOT from `agent/d2-design-v3`)
- **Worktree:** `E:\opencell-worktrees\d2-spike` (per project convention)
- **Files allowed to create:**
  - `experiments/d2_spike/probe1_accumulate.py`
  - `experiments/d2_spike/probe2_step.py`
  - `experiments/d2_spike/probe3_visibility.py`
  - `experiments/d2_spike/probe4_substrate_topology.py`
  - `experiments/d2_spike/probe5_third_process.py`
  - `experiments/d2_spike/karr_composite_4process.py` (probe 5 only)
  - `artifacts/d2_spike_findings.md`
- **Files MUST NOT be modified:** anything outside the above list

- **Single commit when done:**
  ```bash
  cd /mnt/e/opencell-worktrees/d2-spike
  git add experiments/d2_spike/ artifacts/d2_spike_findings.md
  git commit -m "spike(d2): empirical probe of 5 Vivarium architecture questions

  Resolves the analysis gap between strategy critique Opus 4.6 (recommends A)
  and GPT-5.5 (recommends C) by testing each unresolved Vivarium question
  with minimal throwaway code. Findings in artifacts/d2_spike_findings.md
  drive the A-vs-C decision per the decision matrix in
  docs/design/d2_decision_spike_2026-05-22.md section 7.

  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
  git push -u origin agent/d2-spike
  ```

- **Do NOT merge to main.** The spike branch is a research artifact; it should remain visible on GitHub for operator review but not pollute main with throwaway probe code.
