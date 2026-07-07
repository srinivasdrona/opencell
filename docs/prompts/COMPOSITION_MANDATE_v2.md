<!-- COMPOSITION_MANDATE v2 -->

# 3-Slot Prompt Composition Mandate (v2)

**Status:** canonical prompt-architecture spec for codex delegations. Referenced by `FIX_TEMPLATE_L2_REPLAY.md`, `DESIGN_TEMPLATE.md`, and `~/.copilot/skills/delegate-to-codex/SKILL.md`. Single source of truth — edit here, not in the references.

**v2 changes (2026-06-08):**
- NEW: Spec-authority rule. When a machine-loadable spec doc exists for a class of work (catalog YAML, design doc, schema TOML), slot 3 MUST quote the relevant spec entry verbatim. Slot 2 templates MUST name their authoritative spec doc(s) and list the quotation requirement. Existing code is not authoritative spec; deviations in existing code do not override the spec.
- v1 carries over: slot definitions, empirical anchors, slot-3 size heuristics (floor + ceiling), slot-to-patch diagnostic routing.

**Scope.** Authoritative for any codex delegation that authors or modifies code, design docs, or tests. Originally formalized for L2 replay delegations; the underlying mechanism (deliberate action + inversion + protected assertions, layered across generic / domain / case slots) generalizes to other delegation classes. Has not been formally tested as an in-session thinking framework on the primary model — that experiment is open.

---

## The three slots

Every codex delegation MUST be composed of all three slots, in order. Two-slot prompts (template + critique, or PREFIX + critique, etc.) are forbidden — they have been empirically shown to permit Rule-8 trace-cribbing and oracle-routing escapes.

| Slot | Source | Role | Forbidden to omit |
|---|---|---|---|
| 1 | `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md` | Generic anti-act-before-thinking discipline (Beats 1-5). Forces Beat 4 inversion. | Yes |
| 2 | Domain template (`FIX_TEMPLATE_L2_REPLAY.md`, `DESIGN_TEMPLATE.md`, `FIX_TEMPLATE_DIMER_PORT.md`, etc.) | Domain rules + acceptance criteria for the bug-class or work-class. | Yes |
| 3 | Case-specific directive | Names the contract, the surface, the expected outcome, the case-specific pre-mortem failure modes, the hard rules. One per task, never reused verbatim. | Yes |

---

## Empirical anchors

**Day-17 (2026-06-01) morning metabolism delegation** used a 2-slot prompt (template + critique, no PREFIX, no case-specific preservation directive) and shipped `2d20784` containing a `Metabolism_100ticks.mat` trace-crib inside `_static_update` — Rule-8 violation undetected because Rule 8 had not been written yet. The afternoon 3-slot refire (`e7c4285`) returned an honest Class-C verdict with zero crib. Same agent, same task, different slot count.

**Day-17 evening L2.2 harness v1 prompt** (~1.4 KB slot 3) shipped RED with `"upstream pollution"` mis-diagnosis. The v2 redesign prompt (Day-17 late evening, ~7 KB slot 3 with explicit pre-mortem and forbidden patterns) shipped the correct `CAUSE_1_WID_SET_MISMATCH` classification.

**Day-22 (2026-06-07) d3_dnarepair delegation** died three times across three structurally-different attempts (5-way fanout, 3-way fanout, 1-way decomposed-phase-1) without committing. Root cause was not Azure stream flake but **slot-3 over-historicization**: the PROMPT.md recited i2 ProteinDecay laundering history + i3 RNADecay duplicate-WID history + i4 Translation boundEnzymes history, and listed 7 probe-template files in the read-set. Codex read all 7 templates and built a comprehensive JSON-dump probe instead of targeted scipy queries; burned 97k tokens on a 40k-cap Beat-1-only scope; died mid-write before committing. Operator-done Beat 1 + stripped Beats-2-5 prompt unblocked it. The 2 KB lower bound below cannot be calibrated as a single number — there is also an upper failure mode at the high end.

**Day-22 (2026-06-07/08) L2.2 fanout spec drift (v2 anchor for spec-authority rule).** Five fanout codex agents (d1-d5: ReplicationInitiation, Replication, DNARepair, MacromolecularComplexation, Cytokinesis) shipped 5 merges to main that deviated from `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` on 3-of-3 fields measured: 4/5 wired the wrong `primary_channel` (chose `substrates` because that was the d2 Replication template, vs catalog `complexs` or `chromosome`); 2/5 wired the wrong `M_ticks` (used default 100 vs catalog 200); 5/5 wired the wrong `karr_artifact` (used legacy `per_process_replay/*.npz` single-seed extracts vs catalog `per_process_traces_v2` 50-seed ensemble). Root cause: each fanout PROMPT.md cited the runner + helpers + previous-fanout-process (d2 Replication) as the wiring template; **none cited PROCESS_CATALOG.yaml**. d2 itself had deviated; the deviation propagated through the chain. Full-scale gate at M=100/N=50/B=1000 produced 7 PASS verdicts that were testing the wrong channels against the wrong oracle, plus 1 honest FAIL (ReplicationInitiation: pool-scale W1 amplification) that was on the wrong primary channel. ~1 day operator+codex time wasted on what looked like measured progress. Operator caught it on inspection. All 5 merges reverted; re-wired with catalog quotations inserted into slot 3.

**Day-47 (2026-07-07) L1b dependency_symmetry — 2-slot fabrication vs 3-slot honesty (same task, same model).** The `check_dependency_symmetry` invariant (43 asymmetric inter-process dependency edges) was resolved twice by gpt-5.3-codex. **2-slot attempt** (template + case directive, no PREFIX, `6aa9cda`): hardcoded 38 adds + 5 removes in a script's `ADD_RECIPROCALS`/`REMOVE_CONSUMES` dicts and reverse-engineered per-edge prose, citing WIDs that are ABSENT from the rows (`grep -c 'ATP|GLU|LIPOYLAMP' ProteinActivation.yaml` → 0 despite STATUS claiming they're consumed; `grep -c MG_224 FtsZPolymerization.yaml` → 0 despite "bypass-backed" claim), and applied an inconsistent standard (enzymes-group membership counted for adds, dismissed for a removal). Sonnet checker caught it (4th hollow-green catch this project); reverted. **3-slot attempt** (`af6570a`) with (a) DELIBERATE_ACTION_PREFIX_v2 Beat-4 inversion forcing the agent to name "cited a WID grep shows absent" as its own failure mode and disprove it in a VERIFICATION block, (b) a slot-2 rule forbidding hardcoded edge lists + mandating one uniformly-applied rule, (c) slot 3 quoting the exact prior fabrications with grep-proof + naming the authoritative sources: produced ONE uniform rule ("X depends on Y iff a real `consume_stoichiometry`/`requests` WID of X maps to producer Y"), explicitly REFUSED to exploit the `state_groups` read/write ambiguity, and shipped a reproducible `scripts/verify_dep_evidence.py`. Independent re-derivation matched the rows exactly (0 mismatches, 28 edges) → honest L1b green. The anti-fabrication levers that worked: grep-proven prior-fabrication warnings in slot 3, Beat-4 self-inversion, and a mandatory reproducible verifier artifact.

---

## Authoring discipline (slot 3)

**Spec authority (NEW v2, added 2026-06-08 after empirical hit).** When a machine-loadable spec doc exists for the class of work being delegated — catalog YAML, design doc, schema TOML — slot 3 MUST quote the spec entry for the target verbatim. Slot 2 templates MUST name their authoritative spec doc(s) and list the quotation requirement as part of slot-3 authoring discipline. The quotation appears in slot 3 as a fenced code block titled "Catalog entry (authoritative spec):" before any other Beat content; codex MUST read this as the wiring contract and not infer from existing code patterns.

Rationale: existing code is not authoritative spec. Existing code may carry deviations introduced by previous delegations or shortcuts. If a slot-3 prompt cites existing code as the "template to mirror" without quoting the spec, codex will faithfully reproduce the deviation. The Day-22 empirical anchor (below) is exactly this failure mode at 5-process scale.

The case-specific directive must include:
- A Beat-1 contract sentence ("Replace X with Y such that test Z flips").
- A Beat-2 surface enumeration (read paths, write paths, suspect patterns).
- **A Beat-2 Karr-source-selection sub-check (added 2026-06-05).** Before naming any Karr data source in slot 3, list the `data/m1_sources/karr_native/per_process_traces_v2*/<Process>_100ticks.mat` files available for the target process. If F traces exist and the prompt picks a different source (`karr_archive/*.mat`, `ensembles/<process>/seed_NNN/`, analytical `s = k*N`, `fitted_constants.mat`, KB pickles), include a one-sentence justification (e.g., "F seed-0 has only 93/482 proteins observed nonzero — need ensembles for tail coverage"). The default IS the F trace; alternatives need justification. See TRAPS `phase-f-traces-are-the-sourcing-data-not-just-validation-data` (2026-06-05).
- A Beat-3 falsifiable predicted outcome (exact assertion, exact value).
- A Beat-4 pre-mortem with at least 2 named failure modes specific to THIS task.
- A Beat-5 verification protocol (commands in order, expected outputs).
- "Hard rules" closing block (no tick-targeted branches, no oracle reads, no edits outside named files).

## Slot 3 size heuristics (both ends)

**Floor (≥ ~2 KB) — suggestive, not a gate.** A case-specific directive < 2 KB is almost certainly underspecified and the prompt is closer to 2-slot than 3-slot. Calibrated on the L2.2 harness v1 (1.4 KB, shipped wrong) vs v2 (7 KB, shipped right) — n=2, so treat as a smoke alarm, not a hard threshold.

**Ceiling (slot 3 distills, never recites) — added 2026-06-07 (d3 anchor).** State design *constraints* derived from prior investigations (e.g., "do not overlay `oracle_after_*` on primary"); do not narrate the investigation *history* that produced them. Do not list multiple probe-template files in the read-set — codex will read all of them. If the case sits at the intersection of multiple prior bug classes (e.g., i2 + i3 + i4), pick ONE canonical reference (the most recent merged sibling) and constrain reads to that + the SUT file + 1 helper file. Symptom of violation: token burn 2-3× the budget cap with zero commits, death mid-exploration.

There is no single "right" size. The diagnostic is *content* — constraints (good), recited history (bad), template enumeration (bad).

---

## Diagnosing failures: which slot to patch?

When a delegation ships wrong or dies, route the diagnosis:

| Failure mode | Slot to patch |
|---|---|
| Agent didn't imagine the failure mode at all → executed naively | Slot 1 (prefix — expand Beat 4 inversion invitations) |
| Agent imagined the mode but evidence was weak or wrong-class | Slot 2 (domain template — add a probe rule or acceptance criterion; **OR add a spec-doc reference if existing template doesn't name one**) |
| Agent had the right rules but applied them to the wrong artifact, or over-explored the read-set, **or copied a deviating existing-code pattern instead of quoting the spec** | Slot 3 (case-specific — tighten constraints, trim history, **insert the spec quotation block**) |

A failure that splits across two layers (3a/3b) means both need patching. Resist the urge to fold a domain-specific learning into the generic prefix — that's how slot 1 bloats into the prompt's center of gravity and stops being generic.

**Spec-drift sub-rule (v2):** if a delegation shipped code that contradicts a machine-loadable spec doc and the prompt did not quote the spec, the patch is slot-2 (add the spec-quotation requirement to the domain template) AND slot-3 (insert the quotation block before re-firing). Slot 1 does not change. This is the canonical 3a/3b pattern for spec violations.

---

## Versioning

This file is versioned by filename suffix (`_v1`, `_v2`, …). v1 (2026-06-07) introduced slot-3 ceiling rule + diagnostic routing table. v2 (2026-06-08) introduced spec-authority rule + spec-drift sub-rule. Bump the suffix when a structural change lands (new slot, removed slot, new mandatory content requirement for an existing slot, semantic rewrite of the diagnostic routing). Additive notes — new empirical anchors for an existing rule — do not bump the version.

References to this file from FIX_TEMPLATE_L2_REPLAY.md, DESIGN_TEMPLATE.md, and the delegate-to-codex skill should be by versioned filename, not "the composition mandate." When v3 ships, those references must be deliberately updated, not silently followed.

**Historical versions:**
- `COMPOSITION_MANDATE_v1.md` (kept on disk for audit) — 2026-06-07, the d3 ceiling-rule version.
