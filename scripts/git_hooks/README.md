# scripts/git_hooks/

Repo-managed git hooks. These are version-controlled so any clone of the repo can install the same enforcement.

## What's here

| File | Purpose |
|---|---|
| `pre-commit-l2-catalog-conformance.sh` | Refuses to commit changes touching L2.2 Design-A runner / helpers / catalog files unless the commit message body contains a `Catalog-Entry:` trailer with a fenced YAML block (or an explicit `N/A` justification). Enforces COMPOSITION_MANDATE v2 spec-authority rule at the only chokepoint that matters — commit landing. |
| `install.sh` | Installs the hooks into `.git/hooks/` via thin shims that exec back into this directory. Idempotent. Refuses to overwrite non-managed hooks unless `--force`. |

## Why

Documented in `docs/prompts/COMPOSITION_MANDATE_v2.md`. The 2026-06-07/08 fanout drift saw 5 codex merges land against the wrong catalog primary_channel because no PROMPT and no commit cited the catalog. Document-level rules drift. The hook makes the rule executable.

## Install

```bash
bash scripts/git_hooks/install.sh
```

From PowerShell:

```powershell
& bash scripts/git_hooks/install.sh
```

## Commit format

If your change touches any of these files:
- `tests/vivarium/l2_2_design_a_runner.py`
- `tests/vivarium/_l2_2_design_a_runner_helpers.py`
- `tests/vivarium/_l2_2_design_a_projections.py`
- `tests/vivarium/test_l2_2_design_a*.py`
- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`

Your commit message body MUST include one of:

**Catalog-Entry form (preferred for process-specific changes):**

```
<subject line>

<body explaining what changed and why>

Catalog-Entry:
  ```yaml
    - name: Cytokinesis
      bucket: ALGORITHMIC_SHALLOW
      primary_channel: substrates
      M_ticks: 100
      karr_artifact: per_process_traces_v2
      event_density: sparse
      seed_window:
        tick_range_from_division: [-50, 0]
  ```
```

**N/A form (for non-process-specific infra changes — refactors, runner-wide bug fixes, schema additions):**

```
<subject line>

<body>

Catalog-Entry: N/A (justification: refactor of catalog loader; no process-specific behavior change)
```

## Bypass

```bash
git commit --no-verify -m "..."
```

`--no-verify` is logged implicitly in git's reflog. Use only when the hook is genuinely wrong (e.g. emergency revert of an L2 file that touched no spec). When you bypass, follow up in plan.md with one-line note.
