# SESSION_CONTEXT — project rules for delegated (codex) execution

You are executing a task inside **OpenCell**, a Python port of the Karr 2012
M. genitalium whole-cell simulation. These rules are non-negotiable.

## Execution environment (WSL is the source of truth)
- Python/pytest run **only** through the WSL venv `/mnt/e/opencell/.venv-wsl`.
- Prefer the wrappers: `bin\oc-pytest <path> <opts>` for tests.
- Arbitrary Python: `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python <...>"`.
- Never run Windows `python`/`py` directly — the editable install is WSL-only,
  and a passing pytest summary with `skipped > 5` means you used the wrong env.
- File edits may use Windows paths (`E:\opencell\...`) — same filesystem. The
  WSL rule is about **execution**, not editing. Note a 5–15s fs-sync lag after a
  Windows-side edit before WSL sees it.

## Commit cadence
- Commit each green chunk BEFORE the next. Never leave >1 chunk uncommitted.
- Codex sessions can die mid-run; uncommitted work is unrecoverable.
- Commit message trailer: `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- Do NOT push. The orchestrator pushes after review.

## STATUS file
- Write `STATUS_<task-tag>.md` in the repo root using your own file tools as you
  go (NOT via `-o`). Even on failure, write a partial STATUS: what you attempted,
  where you're stuck, next step. Final assistant message: one line.

## Fidelity rules (this is a scientific port)
- **Faithful structural port from the Karr `.m` source.** The MATLAB method named
  in your task is the specification. Mirror its logic, state reads/writes, and
  stoichiometry.
- **No naked biology numbers.** Every biological constant must come from a
  fixture/parameter (loaded from the `.mat` fixtures or an existing OC constant),
  never a hardcoded literal. Literals allowed only for 0, 1, tolerances, shapes.
- **Follow existing OC patterns** in the target process file (how it reads
  `states`, builds the update dict, loads fixtures). Do not invent new frameworks.
- **Scope discipline:** touch ONLY the files named in your task. Do not refactor
  unrelated code, do not touch other processes.

## L-ladder context (where this work sits)
- We are at **L1b** (wiring-conformant + method-complete), which is **oracle-free**.
- Your job is a **structural port** so the OC code implements the Karr method.
  Do NOT attempt bit-for-bit output validation against a Karr trace — that is
  L2.1, done later. "Done" for you = the code exists, follows the source, imports
  cleanly, and existing tests for the process still pass (or you note expected
  changes).
- After implementing, update the method map entry (the orchestrator will point
  you at it) from `gap` to `confirmed`/`inlined` with a resolving
  `file:symbol:line` anchor.

## What you do NOT have
- Copilot's planning context, skills, or conversation history. Your task prompt
  is self-contained; if something's missing, note it in STATUS rather than guess.
