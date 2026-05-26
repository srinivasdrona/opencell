# Dead-Process Investigation — Shared Template

## Background
The OpenCell v6 chassis has 19 processes whose `next_update` returns empty
dicts across 200 ticks. They are NOT errors and they do NOT raise — they are
called every tick and they each independently decide to no-op. This is the
"dead biosynthesis" finding that was previously misdiagnosed via a broken
diagnostic tracer.

Probe artifact (full per-tick per-port capture, no summarization):
  E:\opencell\artifacts\probe_full_traces_20260526_190830\
    process_updates\<process>.csv  — (tick, port, key, value) per write
    entity_call_stats.csv          — calls / nonempty_returns / exceptions

Probe script:
  E:\opencell\scripts\_probe_full_traces.py

Reference probe verdict for a healthy process (e.g., karr_transcription):
  4.1 MB of mRNA-delta writes per 200 ticks, 1900+ rna.counts keys touched.

Reference probe verdict for a dead process:
  21 bytes (header row only). 200 calls, 0 nonempty returns, 0 exceptions.

## Sources of truth (read these IN ORDER)

### Source 1: OpenCell Python implementation
  E:\opencell\opencell\vivarium\<karr_module>.py
  Plus wiring in `opencell/vivarium/karr_composite.py` (look for the module's
  registration site and topology entry).

### Source 2: wcEcoli Python equivalent (CovertLab successor model)
  E:\opencell-mirrors\wcEcoli\
  Search under `models/ecoli/processes/` and `reconstruction/ecoli/dataclasses/process/`
  for the closest analog. wcEcoli is the actively-maintained successor to the
  Karr 2012 M. genitalium model — same architectural patterns, different organism.

### Source 3: Karr 2012 MATLAB — THE SOURCE OF TRUTH for hardcoded constants
  E:\opencell-mirrors\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\<ProcessName>.m
  This is the original Mycoplasma genitalium whole-cell model. Every rate
  constant, threshold, MW, and gate value the OpenCell Python uses should
  trace back to a specific line in this `.m` file. If a constant in the
  Python doesn't match the `.m`, that's a divergence to flag.

## Investigation steps (mandatory, in order)

### Step 1: Confirm the dead-state observation from the probe
```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && \
  head -5 /mnt/e/opencell/artifacts/probe_full_traces_20260526_190830/process_updates/<process>.csv && \
  echo '---' && \
  grep '^<process>,' /mnt/e/opencell/artifacts/probe_full_traces_20260526_190830/entity_call_stats.csv"
```
Document the exact (calls, nonempty_returns, exceptions) tuple in STATUS.

### Step 2: Source 1 audit — OpenCell Python
Read `opencell/vivarium/<karr_module>.py` end-to-end.
Identify (with file:line citations):
  - The `next_update` method's full control flow
  - Every gate / early-return / conditional no-op
  - Every input it reads from `states`
  - Every output port it writes to (or claims to write to)
  - Every hardcoded constant: rate, threshold, MW, count
  - Any commented-out code blocks or `_scope_reduction` markers
  - **Timestep-zero check (NEW, learned from wave-1)**: search the module for
    any multiplication by `timestep`, `dt`, `step_size`, `time_step_s`, or
    similar. If the module's output scales with timestep and the composite
    allows `dt == 0` at any point, the dead-state may be timestep-zero
    suppression rather than a real gate. Cite the lines and the dt source.

Also: from `karr_composite.py`, document the topology entry (which stores
this process is wired into) and any flow dependencies.

### Step 3: Source 2 audit — wcEcoli equivalent
Search `E:\opencell-mirrors\wcEcoli` for the closest functional analog.
Use `Select-String` against the local clone (do NOT use `gh api`).

Document (with file:line citations):
  - File path and class/function names
  - Algorithm summary in 3-5 bullets
  - Any clear divergence from OpenCell's Python: missing steps, simplified
    math, different reaction stoichiometry, different gating, etc.

### Step 4: Source 3 audit — Karr 2012 MATLAB (the new source today)
Read `E:\opencell-mirrors\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\<ProcessName>.m`
end-to-end.

Document (with file:line citations from the .m file):
  - The `evolveState` method's algorithm (line-by-line summary)
  - Every hardcoded constant in the file (rate, threshold, MW, gating value)
  - Substrate inputs and outputs with their MATLAB names
  - Any conditional logic that determines whether the process fires

### Step 5: Hardcoding audit table (NEW today)
Build a markdown table in STATUS with one row per constant:

| Constant name | Python value (file:line) | Karr .m value (file:line) | Match? | Notes |
|---|---|---|---|---|
| ...           | ...                      | ...                       | yes/no | ...   |

Any constant in the Python that does NOT have a clear `.m` origin is a
divergence — flag it explicitly. Any constant in the `.m` that's missing
from the Python is also a divergence.

### Step 6: Verdict
Classify this dead process as exactly ONE of:
  (a) Intentional stub (scope-reduction, documented) — show the doc/comment
  (b) Buggy implementation (returns {} due to a code bug)
  (c) Wrong wiring (registered but on the wrong port / store / flow)
  (d) Missing wiring (defined but not registered in composite)
  (e) Legitimate downstream gate (waits for an upstream signal that is itself broken)
  (f) Other (explain)

**If verdict is (c) Wrong wiring — MANDATORY runtime-injection proof.**
You must demonstrate that injecting the missing key(s) into the offending
store flips the process from empty → non-empty in a single tick. Write a
tiny inline script (committed under `scripts/swarm/inject_<process>.py`
or as a snippet inside STATUS) that builds the composite, injects the
key, calls `next_update` once, and asserts the update is non-empty.
This was the decisive evidence in wave-1's protein_processing_i (injecting
`MG_106_DIMER=22` flipped the return). Without this proof, do NOT classify
as (c) — fall back to (f) Other and document.

### Step 7: Minimal port plan
If verdict is (b), (c), (d), or (f) and a fix is in scope, write the plan:
  - What's the minimal Python change to make this process fire?
  - Cite specific lines in the Karr .m file the port draws from
  - Cite specific lines in the OpenCell Python that need changing
  - Estimate scope (1 file vs multiple, ~LOC, risk level)

DO NOT IMPLEMENT THE FIX UNLESS THE PROMPT EXPLICITLY ALLOWS IT.
This pass is investigation-only. The user will decide what to fix and in what order.

### Step 8: Per-tick probe re-run (mandatory)
Re-run the probe script with a focus on this process:
```bash
wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && \
  cd /mnt/e/opencell-worktrees/<this-worktree> && \
  python scripts/_probe_full_traces.py --out-dir artifacts/probe_<process>_$(date +%Y%m%d_%H%M%S) --ticks 200 --seed 42"
```
Cite in STATUS:
  - The (calls, nonempty_returns, exceptions) row for this process
  - First 5 rows of process_updates/<process>.csv (if any)
  - First and last row of indicators_per_tick.csv (for ATP, MG_469, rna_total, protein_total)

This re-run is a sanity check that the probe still confirms the dead state
on fresh worktree HEAD, AND validates that no merge drift affected the
process. The numbers should match the reference probe.

## STATUS file structure

Filename: `STATUS_dead_<process>.md` (use the process name without the `karr_` prefix; replace `_` with `_` — keep readable)

Required sections (in order):
  1. ## Dead-state confirmation (Step 1 + Step 8 numbers)
  2. ## OpenCell Python audit (Step 2)
  3. ## wcEcoli equivalent (Step 3)
  4. ## Karr 2012 MATLAB source of truth (Step 4)
  5. ## Hardcoding audit table (Step 5)
  6. ## Verdict (Step 6)
  7. ## Minimal port plan (Step 7) — or "N/A: legitimate downstream gate"

## Output and commit discipline

- One commit per logical chunk (per `delegate-to-codex` skill rule)
- The STATUS file itself is committed when complete
- NO summary files. The probe artifact must be in `artifacts/` and committed
- If you cannot complete any section, write WHY in that section's body, do NOT skip
- Final assistant message is one line: "STATUS_dead_<process>.md committed at <sha>"

## ⚠️ Python interpreter — MANDATORY

You are running on Windows. Windows `python.exe` does NOT have this project's
editable install and WILL fail with `ModuleNotFoundError`. You MUST run every
Python command through WSL with the project venv:

  CORRECT:   wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/<worktree> && pytest ..."
  CORRECT:   wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && python scripts/_probe_full_traces.py ..."
  WRONG:     pytest ...
  WRONG:     python -m pytest ...
  WRONG:     py -3.12 -m pytest ...

If `python` from Windows PATH "works" but tests fail with import errors,
you are using the wrong interpreter. STOP and switch to the WSL venv.
Do NOT attempt to `pip install` missing modules into Windows Python.

## ⚠️ Tool availability (PowerShell vs WSL bash)
The probe scripts are Python and must run in WSL venv (see above).
For file searches inside the upstream mirrors, prefer `Select-String`
(PowerShell) over `grep` (which may not be installed in the Codex sandbox).
Do NOT use `gh api` — the mirrors are pre-cloned locally; read them directly.

## Token budget
200,000 hard ceiling. Self-managed handoff at 150,000.
At 150k: stop new exploration, commit what's green, write STATUS with the
"BUDGET CHECKPOINT" line and what the orchestrator should resume with.

## Commit-or-stop semantics
If you cannot complete the task for ANY reason, you MUST still write
STATUS_dead_<process>.md before exiting. The STATUS must contain:
  1. What you attempted
  2. Where you got stuck (specific error + command that failed)
  3. What you tried as fallback
  4. What the orchestrator should do next

A silent exit is the worst possible failure mode. Partial STATUS is always
better than no STATUS.
