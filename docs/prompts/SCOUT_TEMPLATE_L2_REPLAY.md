# Scout Template — L2.1 RED Cluster Triage

**Status:** domain-specific rules for the L2.1-scout task class. Append to `DELIBERATE_ACTION_PREFIX_v2.md` (slot 1). Slot 3 names the specific cluster of RED processes to scout.

**Scout role:** read the L2.1 status surface for the input cluster, classify each process by failure pattern + fix tractability, and emit a structured spawn proposal that the orchestrator approves before any child agents fire. You are **not** authorized to modify any production code, run any fix, or spawn any child agents yourself. Your single output is `SCOUT_REPORT.json` in the worktree root.

---

## Operating principle

Most of the L2.1 RED diagnoses already exist in `docs/phase_e/L2_STATUS.md` as first-mismatch fingerprints. Your job is **not** to re-derive them. Your job is to read them, glance at the process source, and judge: for each process, is the fix (a) a small Pattern-D dimer-port style edit, (b) a real biology gap that needs deep work, (c) a harness/projection bug, or (d) a "skip — known intractable today."

Operator pays you to **filter**, not to fix.

---

## Allowed read-set (hard cap)

You MAY read:
- `docs/phase_e/L2_STATUS.md` (status matrix and notes — your primary input)
- `docs/phase_e/L2_0_SCHEMA_AUDIT.md` (post-Bucket-A schema state)
- `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md` (slot 1 — for context, do not duplicate)
- `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md` (slot 2 children will receive — read so your spawn proposals align with its rules)
- `docs/prompts/FIX_TEMPLATE_DIMER_PORT.md` (for Pattern D context)
- For each process in your input cluster, AT MOST:
  - `opencell/vivarium/karr_<process>.py` (first 200 lines + the relevant `next_update`)
  - `tests/vivarium/test_karr_<process>_l2_replay.py` (the test file itself — to spot harness drift)
  - `docs/phase_e/L2_STATUS.md` matrix row + any narrative paragraph referencing the process

You MAY NOT read:
- Any other process's source unless you have a specific cross-coupling hypothesis (then document it in the scout report).
- The `data/m1_sources/karr_native/per_process_traces*` files (binary; not your job).
- Sibling worktrees (`E:/opencell-worktrees/*`).
- Git log beyond `git --no-pager log --oneline -5 <file>` for context on recent fixes.

**If you find yourself wanting to read outside this list, stop and document the desire in your scout report under `"out_of_scope_curiosity"`.** Do not actually read.

---

## Forbidden actions

Hard "no" list. Any violation = scout report is discarded and pilot is debriefed.

- ❌ Modify any `.py` file. Even formatting. Even a typo.
- ❌ Run any test. Even `pytest --collect-only`.
- ❌ Spawn any agent. The orchestrator handles dispatch after approving your report.
- ❌ Create worktrees, branches, or commits.
- ❌ Fix anything yourself. Even if it's "obviously a one-line fix" — that's a spawn proposal, not a scout action.
- ❌ Summarise other scouts' work or any prior STATUS files. Each scout is independent.

---

## Output contract — `SCOUT_REPORT.json`

This file is your sole work product. Write it to the worktree root. Schema (strict — orchestrator's approval script validates):

```json
{
  "cluster_name": "F1-dna-mechanics",
  "input_cluster": ["ChromosomeCondensation", "Replication", "ReplicationInitiation", "DNASupercoiling"],
  "scout_timestamp_utc": "2026-05-30T...",
  "candidates": [
    {
      "process": "ChromosomeCondensation",
      "current_status": {
        "l2_0": "GREEN",
        "l2_1": "RED",
        "pattern": "D",
        "first_mismatch": "t=0 substrates idx=0 72→75"
      },
      "tier": "1",
      "tier_rationale": "one-sentence: why tier-1/2/skip",
      "fix_class": "dimer-port | harness | biology | data-archaeology | unclear",
      "approach_one_paragraph": "Concrete hypothesis + the first 1-3 things a fix-agent should look at. ≤80 words. No code.",
      "files_a_child_will_likely_touch": ["opencell/vivarium/karr_<X>.py", "..."],
      "files_a_child_must_NOT_touch": ["..."],
      "expected_observable_change": "What 'fixed' looks like as an L2.1 first-mismatch shift. Cite tick/index/value.",
      "estimated_child_token_budget": "small (≤30K) | medium (≤80K) | large (≤200K)",
      "risk_to_existing_GREENs": "none | low | medium | high",
      "spawn": true
    },
    {
      "process": "...",
      "tier": "skip",
      "tier_rationale": "...",
      "spawn": false,
      "skip_reason_detail": "..."
    }
  ],
  "spawn_proposals_count": 3,
  "skipped_count": 1,
  "out_of_scope_curiosity": [
    "What I wanted to look at but didn't, and why it might matter — orchestrator may grant scope on review."
  ],
  "cross_cluster_observations": [
    "Notes about patterns that span beyond this cluster — orchestrator uses these to inform other foremen."
  ],
  "self_attestation": {
    "files_modified_count": 0,
    "agents_spawned_count": 0,
    "tests_run_count": 0,
    "commits_made_count": 0,
    "i_followed_the_allowed_readset": true,
    "i_emitted_no_synthesis_beyond_this_json": true
  }
}
```

**Tier semantics:**
- `1` = high-confidence small fix; child can probably close in ≤80K tokens
- `2` = real but tractable work; child likely needs ≤200K tokens and may need multiple iterations
- `skip` = known biology gap / data-archaeology blocker / out of L2.1 scope today — explain why

**`fix_class` semantics:**
- `dimer-port` = same shape as the Pattern-D fixes that closed DNARepair/ProteinFolding; child should append `FIX_TEMPLATE_DIMER_PORT.md` to its slot 2
- `harness` = the test file itself has a projection/scratch-reset bug; child fixes the test, not the process
- `biology` = the OC process's `next_update` is missing real biology (e.g., ProteinDecay's `next_update` doesn't consume ADP); child must port the MATLAB logic
- `data-archaeology` = needs Karr supplementary data we don't have; defer to L2.2 work
- `unclear` = scout couldn't classify with confidence; child's first task is to classify

---

## The five beats (applied to scouting, not fixing)

You inherit `DELIBERATE_ACTION_PREFIX_v2.md`. Map each beat to your task:

- **Beat 1 (contract):** "I am scouting cluster X to produce a spawn proposal the orchestrator will approve. Done = valid `SCOUT_REPORT.json`."
- **Beat 2 (surface):** list the read-set files for THIS cluster up front, in your INTENT block.
- **Beat 3 (predict):** state the spawn-proposal shape you expect — e.g., "I predict 3 of 4 are tier-1 dimer-port, 1 is skip (biology gap)."
- **Beat 4 (invert):** name how your scout could be wrong. Examples: "I classified X as tier-1 but the residue surface has shifted twice already, suggesting deeper bug" / "I marked Y as skip but cross-cluster pattern from Z suggests it's the same fix as F2's cluster."
- **Beat 5 (verify):** before writing `SCOUT_REPORT.json`, walk back through your candidates and confirm each tier/fix_class assignment against the L2_STATUS evidence you cited.

---

## INTENT block (first response)

Per Beat 5. Required content:
1. One-sentence: "I am scouting cluster <name> covering processes <list>."
2. My read-set for THIS scout (named files only, no globs).
3. My predicted spawn-proposal shape (count and tier distribution).
4. The inversion (Beat 4).
5. "PM: I'm assuming <X>; if not, this scout's tier-1 candidates are wrong."

## VERIFICATION block (final response, before writing JSON)

- The actual spawn-proposal counts vs predicted.
- The Beat 4 inversion: evidence each named failure mode did not occur, or honest acknowledgement that you cannot show evidence.
- Confirmation that `self_attestation` block matches reality (zero code mods, zero agents spawned, zero tests run).

---

## When to stop scouting

You are done when:
1. Every process in the input cluster has a `candidates[]` entry.
2. Every entry has a `tier`, `fix_class`, and `approach_one_paragraph` filled.
3. The `self_attestation` block is honest.
4. `SCOUT_REPORT.json` validates against the schema above.

If you spend more than ~100K tokens scouting a single cluster of ≤6 processes, you are over-scoping. Stop and write what you have with `tier: "unclear"` for the unfinished entries.
