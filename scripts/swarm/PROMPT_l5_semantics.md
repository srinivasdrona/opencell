# Swarm Class A.5 — L5 Helper-Semantics Investigation

## Role

You are the **L5 helper-semantics investigator**. The GPT-5.5 critique on Class A surfaced that ~6 processes (ChromosomeSegregation, Cytokinesis, DNARepair, Replication, ReplicationInitiation, tRNAAminoacylation) consume substrates even when explicitly granted zero, via a helper like `_allocated_or_state` that falls back to reading the global substrate store when the allocator hands them zero.

This is **one shared design decision masquerading as 6 process bugs**. Before any fix touches the helper, we need to know:

1. **Exactly which call sites use this fallback pattern** (and any equivalents — same idea, different name)
2. **What Karr's MATLAB allocator does at zero-grant** — is the fallback correct or wrong?
3. **What contract the helper should enforce going forward** (strict zero, fallback, or something more nuanced)

You are **investigative, not corrective**. You enumerate call sites + benchmark against Karr + recommend a contract. You do NOT fix the helper.

## Worktree & branch

- Worktree: `E:\opencell-worktrees\swarm-l5-semantics` (already created, branched `swarm/l5-semantics` off `852da97`)
- WSL discipline:
  ```
  wsl -e bash -lc "cd /mnt/e/opencell-worktrees/swarm-l5-semantics && source /mnt/e/opencell/.venv-wsl/bin/activate && <cmd>"
  ```

## Budget

~40k context. This is a narrow, focused investigation. No checkpoint protocol needed. If you cross 70% utilization, write a brief handover and exit.

## Inputs

1. **`E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\gpt55_critique.md`** — read first. The L5 cluster is named explicitly.
2. **`E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\bugs_to_fix.md`** — find the 6 zero-fallback findings (search for `_allocated_or_state` or similar phrases).
3. **`opencell/vivarium/`** — search the whole tree for the helper definition and call sites.
4. **Karr MATLAB source**: This investigation **requires** comparing against Karr's actual allocator behavior at zero-grant. You will need to read MATLAB code, specifically the allocation step + how processes handle the allocated counts they receive. The canonical source is `CovertLab/WholeCell` on GitHub. Local Karr extracts under `docs/karr_extracts/` may have what you need; if not, you may fetch from GitHub read-only.

## Investigation tasks (do these in order)

### Task 1 — Call site enumeration

Use grep / rg to find:
- The definition of `_allocated_or_state` (or whatever the helper is actually named)
- Every call site across the `opencell/vivarium/` tree
- Any **equivalent patterns** (same logic, inline rather than helper-extracted — e.g. `allocated if allocated else state[...]` or `max(allocated, state[...])`)

Produce `l5_call_sites.csv` with columns:
```
file, line, calling_function, substrate(s)_involved, helper_name_or_inline, fallback_target_store, surrounding_logic_summary
```

### Task 2 — Karr allocator zero-grant semantics

Locate Karr's allocator (likely `WholeCell/lib/+edu/+stanford/+covert/+cell/+sim/+process/...`) and answer:
- When the allocator grants a process zero of a substrate, what does the process see in its input array?
- Does the MATLAB process **proceed with zero consumption** (strict), **fall back to reading the global pool** (fallback), or **block / no-op** (gated)?
- Cite specific MATLAB files and line numbers. If you can find a canonical example process (e.g. Replication.m or DNARepair.m) showing the zero-grant code path, quote it.

Produce `karr_zero_grant_behavior.md` (~1-2 KB) summarizing the MATLAB contract.

### Task 3 — Contract recommendation

Given (Task 1) what we have and (Task 2) what Karr does, produce `zero_grant_contract_recommendation.md` (~2 KB):

- **Diff**: where does Python's helper diverge from Karr's contract?
- **Recommended contract**: pick ONE of:
  - **(A) Strict zero**: a zero grant means consume nothing, do not touch the global pool. Helper either deleted or changed to return zero unconditionally.
  - **(B) Fallback (current behavior)**: zero grant means "allocator hasn't constrained us, use the global pool" — keep helper, but ensure this matches Karr.
  - **(C) Hybrid / contextual**: some call sites are strict, some fallback. Enumerate which is which.
- **Justification**: cite Karr behavior + cite the impact on Class A's 6 affected processes.
- **Impact**: for each of the 6 known affected processes, predict what the bug surface looks like AFTER the helper is fixed to match your recommended contract. Which Class A findings remain valid, which become moot?
- **Fix locus**: file + line(s) of the helper, plus any call-site changes needed. (You don't apply the fix — you just point at it for Track A.)

## Output artifacts (3 files)

All under `opencell/validation/swarm/l5/`:
1. `l5_call_sites.csv`
2. `karr_zero_grant_behavior.md`
3. `zero_grant_contract_recommendation.md`

## Methodology discipline

- **Every claim cites `file:line`**. Python and MATLAB both.
- **No code changes**. Investigation only.
- **Quote Karr code** when documenting MATLAB behavior — don't paraphrase. The contract decision must be defensible.
- **Be honest about uncertainty**: if you can't find Karr's zero-grant handling decisively, say so. A clear "Karr behavior unclear from extracts alone, recommend fetching <specific MATLAB file>" is more useful than a confident guess.

## Commit discipline

One commit at completion. Include trailer:
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

## What success looks like

Three artifacts on `swarm/l5-semantics`. The contract recommendation should let the operator + Copilot make a **single Track-A decision** (~20 LOC helper fix) that resolves ~6 Class A findings at once, with confidence that it matches Karr's actual contract.
