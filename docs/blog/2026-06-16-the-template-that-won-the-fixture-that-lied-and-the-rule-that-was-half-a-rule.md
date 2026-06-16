# The template that won, the fixture that lied, and the rule that was half a rule

A controlled experiment comparing ad-hoc vs template-structured design docs, what it found, and the one-sentence patch that closed a showstopper class.

## Origin: the dimer-port experiment and the 3-slot architecture

On June 1, fifteen days ago, we ran a pre-registered A/B/Gold experiment on the dimer-port bug class — a silent failure where 11 of 28 Karr processes read complexes from the wrong store. The experiment compared three prompt strategies: a generic Deliberate Action prefix alone (Arm A), prefix plus a domain-specific Fix Template (Arm B), and a maximum-specificity prompt with all prior critique findings baked in (Gold). The result was a bombshell: Gold — the most specific arm — failed the worst, because it satisfied the literal directive by inventing a biological fiction. The canonical fixture said `MG_205_DIMER = 0`; Gold's chassis builder set it to `1.0` to pass a critique-baked test.

That experiment produced the **3-slot prompt architecture**: Slot 1 (Deliberate Action prefix — structured doubt), Slot 2 (domain-specific template — per-task-class discipline), Slot 3 (case-specific directive — per-task context). The full write-up is at [Three slots, seven rules, and the bug that made us write rule eight](2026-06-01-three-slots-seven-rules-and-the-bug-that-made-us-write-rule-eight.md).

The 3-slot framework shipped as the canonical delegation discipline for codex fix work. For design work, a companion slot-2 template — `DESIGN_TEMPLATE.md` — was authored with nine mandatory sections (contract, inventory, surfaces, facts, decisions, outcomes, questions, scope, migration, risks) and a nine-item acceptance bar. Both templates lived in the repo at `docs/prompts/`.

## The trigger: a spec that wouldn't close

The L2.event gate specification — a new test harness for processes whose events fire too rarely for the per-tick L2.2 gate — went through three rounds of critique without converging:

| Round | Reviewer | Findings |
|---|---|---|
| v0.1 → v0.2 | Rubber-duck (Opus 4.7) | 4 SHOWSTOPPER + 7 MAJOR |
| v0.2 → v0.3 | GPT-5.5 | 4 SHOWSTOPPER + 7 MAJOR |
| v0.3 → (stalled) | GPT-5.5 | 4 SHOWSTOPPER + 6 MAJOR |

Each round fixed what the prior round flagged and introduced new issues the fixes created. The root cause: the spec was ad-hoc. No mandatory structure, no inventory checklist, no acceptance bar. The failure modes were structural (FtsZ treated as binary event when it's gradient; sub-gate 2 letting OC free-run from a single snapshot; degenerate bootstrap; vacuous-PASS aggregation), and the ad-hoc format had no forcing function to prevent them.

A v4 rewrite using `DESIGN_TEMPLATE.md` as the slot-2 skeleton produced zero showstoppers on first critique. The L2.event spec was ratified at v4.1. That was suggestive — but confounded by the fact that v4 had three prior rounds of critique findings to learn from. The template's value couldn't be isolated from the accumulated knowledge.

## The experiment: does the template help on a fresh problem?

To test whether `DESIGN_TEMPLATE` produces a better first draft on a NEW problem where neither arm has prior context, we ran a controlled comparison on the chromosome port design (pc-t7) — porting Karr's full Chromosome state (11 CircularSparseMat properties, 580,076 × 4 sparse matrices) from MATLAB to OpenCell Python.

### Setup

Both arms received identical inputs:
- Same 6 source files with identical skim hints (including specific line ranges for Chromosome.m and CircularSparseMat.m)
- Same bounded read-set instruction ("do NOT grep the repo for additional context")
- Same commit-cadence instruction (3-4 checkpoints: after reading, after writing, after review)
- Same token budget (60k soft, 120k hard)
- Same operational context (worktree, branch, WSL venv)

The only difference: Arm A was told "structure it however you think best — there is no template." Arm B was told "follow DESIGN_TEMPLATE.md structure exactly. Apply the acceptance bar."

### Equalization history

The experiment design went through two corrections before firing:

1. **Read-set leak** (caught by the operator before firing): the original 3-slot prompt had "skim properties block lines 200-320 and key methods" while the ad-hoc prompt just said "skim these 7 files." The line ranges would have fed directly into S6 (source fidelity), making it impossible to distinguish template discipline from prompt-leaked signal. Fix: gave both arms identical skim hints.

2. **Commit-cadence confound** (caught by the operator after initial runs): the first 5 ad-hoc attempts all died from Azure stream disconnects (token burns of 127k–255k, zero artifacts). The 3-slot arm survived on its first solo attempt. The initial interpretation was "the template's beat-cadence commits save progress." The operator's correction: three variables were coupled — template structure, bounded read-set, and commit cadence. The proximate killer was unbounded exploration (ad-hoc was grepping L2.2 plan and convergence docs for ~100k tokens of irrelevant context), not missing checkpoints. Fix: equalized commit cadence and exploration boundary for both arms, re-fired.

After equalization, ad-hoc completed on its first attempt (3 commits, 17 KB, 146k tokens).

### Evaluation protocol

Seven criteria, scored 0–2 each:
- **S1** Completeness, **S2** Decision quality, **S3** Falsifiability, **S4** Actionability, **S5** Self-awareness of gaps (structure-visible criteria — easier to credit when sections are labeled)
- **S6** MATLAB source fidelity, **S7** Anti-pattern avoidance (grounded criteria — template can't flatter the score)

Three independent grading runs per arm (Opus 4.6, separate instances). Median scores used. Pre-registered win condition: total-score gap ≥ 3 points; auto-win if one arm scores ≥12 and the other ≤8.

**Interpretation guard** (operator-imposed): if the 3-slot win concentrates in S1/S2/S5 (structure-visible) but not S6/S7 (grounded), discount it as structure-flattery. A real win must show on the grounded criteria.

### Results

| Criterion | Ad-hoc (median) | 3-slot (median) | Gap |
|---|---|---|---|
| S1 Completeness | 1 | 2 | +1 |
| S2 Decision quality | 1 | 2 | +1 |
| S3 Falsifiability | 1 | 2 | +1 |
| S4 Actionability | 1 | 2 | +1 |
| S5 Self-awareness | 2 | 2 | 0 |
| S6 Source fidelity | **0** | **2** | **+2** |
| S7 Anti-patterns | 2 | 2 | 0 |
| **Total** | **8/14** | **14/14** | **+6** |

Auto-win triggered (14 vs 8). The win shows on **S6** — the grounded criterion where the template can't flatter the score. Both prompts pointed at `CircularSparseMat.m` using a path that doesn't exist in the worktree (`data/m1_sources/WholeCell/.../CircularSparseMat.m`). The ad-hoc arm tried the path, got "file not found," and designed the most critical data structure from inference. The 3-slot arm tried the same path, got the same error, then ran a broader search (`rg --files data | rg CircularSparseMat`), found it at `data/karr_fixtures/m_source/CircularSparseMat.m`, opened it, and cited the modulo wrapping formula, the SparseMat inheritance, and the constructor semantics.

The codex log confirms: the 3-slot arm's broader search happened during the inventory pass. The template's §2 requires machine-checkable artifact entries with concrete resolvable paths. When the prompted path failed, the inventory discipline forced a recovery search. The ad-hoc arm had no such forcing function.

### The critique round — and the SHOWSTOPPER the template shipped

GPT-5.5 critique of each arm:

| Finding | Ad-hoc | 3-slot |
|---|---|---|
| SHOWSTOPPER | 1 (Vivarium store integration completely absent) | 1 (`Chromosome_flat.mat` claimed to contain usable sparse arrays; actual content is `<flatten-error:...>` placeholder strings) |
| MAJOR | 6 | 6 |

The template that won the rubric shipped a showstopper. The inventory section correctly listed the file (A10), correctly described its role ("chromosome seed artifact"), and correctly ran a Beat-4 inversion asking "what critical artifact could still be missing?" But none of those checks caught that the file was present with broken content.

The root cause: the Beat-4 inversion on inventory asked "what's missing?" — which finds absent artifacts. It never asked "what's WRONG in what we listed?" — which would have required a content probe (loading the file and checking the bytes).

## The patch

One sentence added to `DESIGN_TEMPLATE.md` §2, rule 5: "For any artifact claimed as a data source, fixture, or evidence anchor: verify at least one field/record loads correctly via code before claiming it contains usable content."

One expansion to the Beat-4 inversion on inventory: "What could be WRONG in the artifacts we listed? (Presence ≠ correctness. A fixture file can exist and contain placeholder strings instead of data. A schema can list a column that is never populated. For each data-source artifact, state what content check was run — or flag 'content not verified' explicitly.)"

Both the project template (`docs/prompts/DESIGN_TEMPLATE.md`) and the cross-project template (`D:\OneDrive - Microsoft\.pm-os\templates\example-DESIGN_TEMPLATE.md`) were patched.

## Arm C: the hardened template

Same problem, same inputs, same budget. The only change: the patched DESIGN_TEMPLATE with rule 5 and expanded Beat-4.

**Did it catch the broken fixture?** Yes. Arm C's spec, line 43: "Chromosome_flat.mat — probe: `sequenceLen=580076` and `nCompartments=4` load, but all 11 chromosome sparse fields currently load as `<flatten-error:...>` strings, so this fixture is not usable for pc-t7 as-is."

The codex log confirms the probe was rule-driven (line 654: "I'll run code probes against the chromosome artifacts before I write the inventory so the doc only claims content we actually verified").

### 3-arm summary

| | A (ad-hoc) | B (3-slot v1) | C (3-slot v2, hardened) |
|---|---|---|---|
| **S1–S7 median** | 8/14 | 14/14 | 14/14 |
| **Critique SHOWSTOPPERs** | 1 | 1 | **0** |
| **Critique MAJORs** | 6 | 6 | 6 |
| `Chromosome_flat.mat` caught? | N/A (didn't reference it) | ❌ Claimed usable | ✅ Identified as broken |

## What the fix did NOT cover

The operator identified a remaining gap: the hardened rule covers data-fixture verification (`kind=data/trace/schema/fixture`) but NOT source-citation verification (`kind=code`). All three arms echoed Chromosome.m method names (`setRegionPolymerized`, `setRegionUnwound`, etc.) from the prompt's skim hints without opening the file. One of three graders on arm C caught this — scoring S6=1 instead of 2, noting the method names were "prompt-sourced, not code-verified." The principle "verify content of everything you cite" is half-implemented.

## Second-order effect

Arm C had 12 mentions of Vivarium updater-contract semantics versus arm B's 2 and arm A's 0. This wasn't caused by rule 5 (the data-fixture rule); it was caused by the DESIGN_TEMPLATE's mandatory §3 (interaction-surface map) and §5 (decision ledger). When codex read the OC ports' `ports_schema()` during the source-read beat, the Vivarium updater patterns were fresh in context. The mandatory sections pulled that context into explicit design decisions — a decision card for the updater contract (D4) with concrete `_updater: set` schema examples. The template's structural sections and the content-verification rule contributed independently: rule 5 caught the fixture bug, sections 3 and 5 caught the integration gap.

## Decisions logged

- `adopt-design-template-mandatory`: 3-slot framework (Slot 1 = DELIBERATE_ACTION_PREFIX, Slot 2 = DESIGN_TEMPLATE, Slot 3 = case-specific) is the canonical authoring discipline for all future design docs involving architectural forks or cross-surface coupling.
- `design-template-inventory-content-verification`: Beat-4 on inventory must ask "what could be WRONG in what we listed" not just "what's missing." File existence ≠ content correctness.

## What happens next

The chromosome port spec (arm C with 6 MAJORs fixed) is committed to main at `9deb297` as `docs/phase_f/PC_T7_CHROMOSOME_PORT_DESIGN.md`. Implementation is gated on:
1. Operator providing Chromosome.m source or blessing Phase 1 without it (QO1)
2. Refreshed `Chromosome_v2.mat` fixture with numeric sparse triples (QO3)
3. Performance spike after DNASupercoiling and Replication are ported (QO6)

The L2.event gate spec is ratified at v4.1 (`docs/phase_f/L2_EVENT_GATE_SPEC_v4.md`). Implementation is gated on Phase 1 (MATLAB event-window extraction for Cytokinesis + RibosomeAssembly).

Both specs were authored by codex using the 3-slot framework and critiqued by independent GPT-5.5 reviewers. The specs are the deliverables; the experiment that produced them is the methodology lesson.

---

*Previous: [Day 29 — The Cap That Wasn't, the Greens That Split, and the Spec That Spiraled](2026-06-15-the-cap-that-wasnt-the-greens-that-split-and-the-spec-that-spiraled.md)*

*See also: [Three slots, seven rules, and the bug that made us write rule eight](2026-06-01-three-slots-seven-rules-and-the-bug-that-made-us-write-rule-eight.md) — the dimer-port origin story for the 3-slot architecture.*
