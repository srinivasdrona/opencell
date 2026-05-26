# OpenCell — Shared Codex Session Context (2026-05-23)

## Project at a glance
Python whole-cell simulation of *Mycoplasma genitalium* — a port of Karr 2012's
MATLAB whole-cell model onto `vivarium-core`. Repo: `E:\opencell` (main).

## Today's mission (2026-05-23)
**Ship Phase C (10 Karr processes covering DNA replication + cell cycle), then
start Phase D (HostInteraction → chassis_v6 = all 28 processes integrated).**
Phases A3.3 + B already shipped yesterday (17 of 28 processes). pc-t1
ReplicationInitiation already shipped on main at `karr_replication_initiation.py`.

## Hard rules (non-negotiable)

### 1. Karr-fidelity is the prime directive
Every algorithm choice must trace to:
- Karr 2012 MATLAB source at `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/<Process>.m`
- Karr extract at `docs/karr_extracts/process/<NN>_<Process>.md` (verbatim docstring + mapping notes — trust the verbatim section, spot-check the mapping notes)
- Per-process bit-identical trace at `data/m1_sources/karr_native/per_process_traces/<Process>_100ticks.mat` (gold-standard validation data)
Do NOT invent biology. If a docstring is silent, document the gap, don't guess.

### 2. WSL venv ONLY for Python
The repo uses an editable install in `.venv-wsl`. All Python commands MUST be:
```
wsl -e bash -lc "/mnt/e/opencell/.venv-wsl/bin/python ..."
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest ..."
```
Windows-side `py -3.12` or `python` will fail with ModuleNotFoundError on the
project's own package. Do NOT try to "fix" this — switch interpreters.

### 3. Vivarium accumulate-only rule
Every per-tick writer in OpenCell chassis MUST use `_updater: "accumulate"` and
emit DELTAS (not absolute values). Mixed `set`+`accumulate` on the same leaf is
broken (order-sensitive — last-declared updater wins, probe-tested 2026-05-22).
Decision logged as `vivarium-all-accumulate-no-set`.
Exception: long-lived discrete state machines (e.g., `replication_state` = "idle"/"elongating"/"complete") may use `_updater: "set"` because no other writer
touches them. When in doubt, prefer accumulate.

### 4. KarrAllocationStep contract
If your process consumes shared substrates (ATP, GTP, NTPs, AAs, etc.):
- Write a `requests.<process_name>.<substrate_id>` value at tick start
- Read your `substrates_allocated.<process_name>.<substrate_id>` allocation
- Apply your action bounded by what was allocated
- Emit your accumulate-delta on `substrates.<substrate_id>` (negative for consumption)
See `opencell/vivarium/karr_allocation_step.py` + `karr_protein_decay_light.py`
for the pattern. The pc-t1 file `karr_replication_initiation.py` shows the full
shape for a Phase C process.

### 5. Commit-or-STATUS on every exit
NEVER exit without writing STATUS.md. If you got stuck — say so, with the
specific error and what you tried. A partial STATUS is always better than none.

### 6. No regressions, but narrow first
Inner-loop verify: NARROW pytest only (`pytest -x tests/vivarium/test_<your_file>.py -W error::UserWarning`). Iterate fast.
Final pre-commit smoke: run the targeted directory you touched (e.g., `pytest -x tests/vivarium/`), NOT the full suite. The orchestrator runs the full suite on main after merge.
Baseline as of 2026-05-23: 864 pass / 0 fail / 9 skip / 4 xfail. Do not regress.

### 7. Token budget + checkpoint commits
Most prompts should declare an explicit budget (most ≤60k tokens; integration sessions up to 150k). If you cross the budget, STOP and append to STATUS.md.
Commit aggressively at meaningful checkpoints — do NOT batch all work into a single commit at the end. Azure remote-compaction throttles silently around 150-200k tokens; an uncommitted session looks like a silent exit even when real work survives on disk.

### 8. STATUS.md is a live log
Append a one-line progress entry to STATUS.md (with UTC timestamp) at each meaningful step (read complete, design drafted, narrow tests green, commit pushed). Don't wait until the end. The orchestrator polls this file to spot stalled sessions.

### 9. Merge conflict resolution: rm + merge --continue
When `git merge` hits a conflict on a file you do not own (or that another branch already deleted/moved), the resolution is `git rm <path>` (or `git checkout --theirs <path>` if you want the incoming version) followed by `git merge --continue`. Do NOT manually `git add` a hand-edited copy of the conflicted file — that's how content silently gets dropped from the merge (single-parent merge artifact). Lesson encoded after `41809db` lost HostInteraction content; recovered as `8dd146d` via clean re-merge.

### 10. Rename-before-wire
Always canonicalize module / class / file names BEFORE final composite wiring lands. If you discover a naming inconsistency partway through (e.g., `karr_m1` vs `karr_metabolism`), STOP and finish the rename first, then wire. Renaming after a 28-process composite is wired forces double-touch on every consumer file and inflates the diff 3-5×. The naming-drift rename today (commit `cf6a1ad`) was the right pattern: 14-min focused Codex rename across 80 files, then wiring afterwards landed cleanly.

### 11. Estimation anchor
Anchor time estimates to observed Codex throughput, NOT human-developer intuition. Reference points from this codebase:
- Focused rename (≤80 files, mechanical): ~10-15 min
- Single-process Karr port + narrow tests: ~20-30 min
- Integration turn (chassis-vN + smoke + regression tests): ~40-60 min, 100-150k tokens
- Pure design document (no code): ~5-10 min
Copilot-side strategy/design work defaults to 5-10 min for a single artifact. Calendar-week estimates for AI-orchestrated work erode trust and are almost always wrong by 10-20×.

### 12. Verify source-physics constraints at EVERY clamping layer
When a constraint exists in the source physics (e.g., NGAM ATP-maintenance floor in Karr's
FBA LP), do not assume that enforcing it at the canonical layer is sufficient. Trace the
flow end-to-end and verify the constraint is enforced at every layer that can clamp the
quantity to zero. In v5+ chassis the ATP flow has TWO gates:
- `RequestCalculatorMetabolism.next_update` → tells the allocator how much ATP M1 wants
- `karr_metabolism.py` LP solve → uses the allocated budget

A constraint applied only at the LP is silently zeroed by the request layer if the request
is zero. The 2026-05-26 NGAM audit (commit `613d36c`) caught the LP gap but the deferral
reasoning ("dynamic_bounds will implicitly enforce NGAM") covered only the LP layer and
missed that `use_allocator_budget=True` interposes an earlier gate. Decision:
`ngam-explicit-floor-in-allocator-request` (2026-05-26).

**Worked example — 5 gates on M1's ATP flow (in tick order):**
1. `RequestCalculatorMetabolism.next_update` → returns 0 unless explicit floor is added.
2. `KarrAllocationStep` request-clamp (`karr_allocation_step.py:154`) → `max(0, request)`.
3. `KarrAllocationStep` pool-scale + floor (`:160-163`) → if `total_demand > pool`,
   scales proportionally; `np.floor` zeros any sub-1-molecule request.
4. `KarrMetabolismProcess._dynamic_update` "Bug 6b" clamp (`karr_metabolism.py:394-418`) →
   silently clamps infeasible reactions; increments `bug6b_clamped_reactions_total` without
   surfacing to the chassis.
5. LP `lb`/`ub` arrays (`m1/karr_metabolism.py`) → no explicit ATPM lower bound; the LP
   can solve to zero ATPM flux even when the chassis "wants" maintenance.

A constraint enforced only at one of these gates is silently nullified by the others.
The same 5-gate structure applies (with gates 4/5 absent) to all 9 allocator-coupled
processes: D2, PD, RibAsm, TRNA, RNAPathway, ProteinPathway, Transcription, Translation,
Metabolism. Each maintenance-class or always-on flux must be audited at gate 1.

**Population-driven vs system-level constraints (Track-N3 finding, 2026-05-26):** Most
process-level requests are naturally self-floored because their formula has the shape
`sum(active_population_i × rate_i × dt)` — whenever a population (RNAPs, ribosomes,
decaying complexes) is non-empty, the request is non-zero. Track-N3 audited the 8
sibling RequestCalculators (D2, PD, RibAsm, TRNA, RNAPathway, ProteinPathway,
Transcription, Translation) and found **none** of them was missing a floor of the NGAM
class. They divide cleanly into `FLOOR_PRESENT` (population-driven: PD, Transcription,
Translation) and `NO_FLOOR_NEEDED` (event-driven: D2, RibAsm, TRNA, RNAPathway,
ProteinPathway). **Metabolism is uniquely vulnerable** because NGAM is a system-level
constant tied to cell mass, with no population carrier. Lesson: when adding a new
process to the chassis, classify its consumption pattern. Population-driven = safe by
construction. Event-driven = safe. System-level = explicit floor needed at gate 1
(request) AND gate 5 (LP lb) AND any other downstream constraint surface.

### 13. Invariant-delta block on architectural changes
Any PR or task that adds a new layer of indirection (a new mediator, a new config flag
that changes the active code path, a new composer/wrapper, a new request/grant gate)
must include a one-paragraph **invariant-delta block** before the work lands:

```
Invariant delta:
- Prior architecture guaranteed: <list 3-5 invariants the old code held>
- This change preserves: <which ones survive>
- This change weakens / removes: <which ones do not — and why>
- Deferred gap (if any): <named issue + owner + intended close>
```

This is cheap (~3 min) and catches the class of failure where the new layer silently
nullifies a prior guarantee. Examples we missed and would have caught:
- `use_allocator_budget=True` introduction: should have flagged "LP-layer NGAM
  enforcement is now conditional on allocator handing through enough ATP" — exactly
  the Track-N/N2 root cause.
- Phase C chassis composer assembly (Day 10): should have flagged "individual process
  tests assert shape but composer can produce a wired-and-silent chassis" — exactly
  the Day-10 silent-chassis failure.

### 14. Pre-mortem before any multi-agent fanout
Before launching a swarm of >3 parallel agents on related work, write a 5-line
**pre-mortem**: "if the integration of these N agents' outputs is broken, what are
the top 3 most likely silent failure modes?" Log answers as expected-checks the
integration smoke test must explicitly assert. This is the discipline whose absence
caused Day 10 (13 agents in parallel, no integration-flow assertion ever written).

### 15. Symmetry-break awareness
Whenever you find one component that is structurally different from its siblings
(e.g., system-level vs population-driven, single-instance vs many-instance,
externally-driven vs self-driven), **the asymmetric one is the most likely site of
a class-of-bug-that-doesn't-affect-the-others.** Audit it first, separately, with
its own checklist. Track-N3 demonstrated this: Metabolism is the only system-level
process in a sea of population-driven processes; it was the only one with the NGAM-
class miss.

### 16. End-to-end smoke before declaring a layer "done"
A new layer is not done when its unit tests pass. It is done when an end-to-end
run through the layer produces output that an outside observer would call sensible.
For OpenCell that means: substrate pool deltas non-zero, transcription log non-empty,
ATP balance within tolerance over a multi-tick window. Wire that smoke before
declaring a layer ready for downstream consumers.

## Reference files to read FIRST (every session)
1. `opencell/vivarium/karr_replication_initiation.py` — Phase C v1 pattern (DNA state, allocation, accumulate)
2. `opencell/vivarium/karr_allocation_step.py` — request/allocate protocol
3. `opencell/vivarium/karr_composite.py` — chassis_v4 wiring (search for `build_karr_chassis_v4`)
4. `opencell/vivarium/karr_protein_decay_light.py` — minimal scope, allocation consumer
5. `.github/copilot-instructions.md` — Primary-Source Discipline rule
6. `docs/design/pc_turn1_replication_initiation.md` — Phase C T1 design (your template)
7. `docs/design/phase_c_overview.md` — Phase C scope + new stores plan

## What "Karr-light" means
For Phase C processes too complex to port fully in one Codex turn, scope to:
- Per-tick rates (counts, deltas) matching Karr's per-process trace data
- Bulk state changes (e.g., fork advancement counter) NOT per-nucleotide mechanics
- Document the deferred mechanism explicitly as "v2 scope" in the file docstring
The chassis must still close mass balance — light scope ≠ fictional biology.

## Files NOT to modify
- Any file under `data/karr_archive/`, `data/m1_sources/`, `docs/karr_extracts/`
- `plan.md` (orchestrator owns it)
- `opencell_tasks.db` (orchestrator owns it)

## Branch policy
You are working in a dedicated worktree on branch `agent/<task-name>`. Commit
your work locally to that branch; the orchestrator will merge to `main` after review.

## Definition of done (per turn)
1. New file(s) created per the prompt
2. Tests pass via WSL pytest (`pytest tests/vivarium/test_karr_<process>.py -v`)
3. Full suite still green: `pytest -x -q` (must end in 0 failures, no new xfails)
4. One commit with message `pc-tN: <Process> (one-line scope summary)`
5. STATUS.md final block: files changed, test results, any blockers
