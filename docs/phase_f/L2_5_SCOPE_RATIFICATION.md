# L2.5 Scope Ratification

Status: RATIFIED (REVISION-class scope-derivation; supersedes the Day-33
`l2_5_gate:` snapshot in `PROCESS_CATALOG.yaml` and all prose pair-count
claims below, without deleting them).

Companion artifacts:
- `docs/phase_f/l2_5/L2_5_SCOPE_CATALOG.yaml` — machine-readable, regenerable
  eligibility + pair catalog (this doc's evidentiary backing).
- `scripts/derive_l25_scope.py` — deterministic deriver/validator that
  produces the catalog above from tracked/live inputs, never from stored
  verdict strings.
- `tests/scripts/test_derive_l25_scope.py` — 14 focused tests (synthetic
  algorithm tests + real-data regenerability tests).

## DAP Intent

1. **Contract (Beat 1):** Replace the ambiguous L2.5 pair denominator with
   one mechanically-derivable eligible-process set and minimal covering pair
   set, such that a reviewer can regenerate both from tracked inputs alone.
2. **Surface inventory intent (Beat 2):** Evidence comes from
   `PROCESS_CATALOG.yaml` (28-process denominator + per-side oracle policy),
   `scripts/probe_l2_1_strict_rubric.py` (live L2.1 honest-mode rerun),
   `scripts/l22_evidence/generator.py` (live L2.2 mechanical rebuild, not the
   tracked `evidence_index.json`), and a live grep of each process's
   `oc_module` source for `trace_hint` (cf. `L2_5_SHORTCIRCUIT_AUDIT.md`).
3. **Falsifiable expectation (Beat 3):** Running `scripts/derive_l25_scope.py`
   twice produces byte-identical YAML and prints one unambiguous
   denominator/pair-count summary; it exits nonzero today because the fresh
   eligible set cannot cover every required class without touching a
   known-gap process.
4. **Inversion (Beat 4):** The most embarrassing way this could look right
   while being wrong is if the deriver silently fell back to a
   "looks-plausible" default (e.g. treating `in_scope_L2_2` as "L2.2 passed",
   as `derive_l25_pair_matrix.py`'s `l2_2_passed` field already does) instead
   of failing closed. Falsifier: any process whose eligibility flips to
   `true` without a fresh GENUINE/PASS verdict actually being recomputed this
   run — checked by `test_no_selected_pair_ever_includes_an_ineligible_or_gapped_process`
   and by the fact this script never reads `evidence_index.json` or the
   catalog's `l2_5_gate.pass_list`.
5. **Sanity-check sentence:** Today's honest answer is **0 selectable L2.5
   pairs** — this is the correct, disciplined, no-waiver outcome, not a
   failed deliverable; see "Current honest result" below.

## 1) Design contract

- **Required behavior:** the L2.5 pair denominator and eligible/selected pair
  set must be re-derivable byte-for-byte from tracked inputs by anyone,
  without trusting any stored PASS/FAIL string.
- **Why this matters:** every prior L2.5 pair-count claim in this repo
  (Day-19 through Day-63) has drifted from what re-running the actual gates
  produces — see "Superseded stale claims" below. Ambiguity here silently
  license waived/known-gap pairs into the "honest" count.
- **Done =** `bin\oc-py scripts/derive_l25_scope.py` prints a single
  denominator and pair count, exits nonzero iff a selected process is
  ineligible/known-gap or a required coverage class is uncovered, and two
  consecutive runs produce byte-identical `L2_5_SCOPE_CATALOG.yaml`.
- **Beat-4 inversion:** most plausible "looks right, is wrong" failure — a
  future edit re-introduces a stored-verdict shortcut (e.g. reading
  `mechanical_verdict` from the tracked JSON instead of calling
  `build_evidence_index()` fresh). Falsified by
  `test_two_independent_builds_are_byte_stable` plus the explicit code
  comment/docstring in `derive_l25_scope.py` naming this exact anti-pattern.

## Spec-authority quotes (verbatim, per COMPOSITION_MANDATE_v2 slot-3 rule)

Case-directive authoritative definitions (preserved verbatim as given):

```text
L2.5 shared-pool composition (k processes, single trace, allocator-mediated; CAUSE_1-7 taxonomy)
L2.5 starts only after L2.2 is all-green for every stochastic process that participates in any planned L2.5 pair.
L2.5 tests state-update wiring between processes via the shared substrates pool, owner manifest, write-conflict resolution, composition order, and shared WID-space alignment; not within-process biology and not direct hand-off.
```

`plan.md` (L-ladder canonical, 2026-07-02) restates the same sequencing rule:

```text
**Sequencing decision (2026-06-04, still in force for L2.5):** L2.5 starts
only after L2.2 is all-green for every stochastic process intended to
participate in any planned L2.5 pair. Reason: L2.5 currently absorbs
stochastic divergence via L2.1's calibrated-tolerance shortcut; without
L2.2 closing that gap first, L2.5 silently rides on calibrated tolerances
and can pass while distributional behavior is wrong.
```

`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` (`l2_5_gate.per_side_oracle_policy` + `scope`, schema v5):

```yaml
per_side_oracle_policy:
  deterministic: "L2.1 trace, per-tick bit-identity (rtol=0, atol=0)"
  stochastic:    "L2.2 trace, per-tick distributional + CAUSE_1-7 taxonomy"
  both_must_pass: true
scope:
  total_pairs_28_choose_2: 378
  disjoint_out_of_scope: 122
  honest_required_shared_pool: 256
  breakdown_by_oracle_complexity:
    stochastic_stochastic: 211
    deterministic_stochastic: 43
    deterministic_deterministic: 2
```

These structural numbers (378/256/122, and the SS/DS/DD split) are
**reconfirmed unchanged** by the fresh derivation below — the ambiguity this
ratification fixes is entirely in the *eligibility* side (which processes'
gate verdicts are actually green today), not the structural WID-overlap
side.

## Canonical denominator (ratified)

**28 canonical Karr processes** (`PROCESS_CATALOG.yaml`'s `processes` list
length) is the denominator. `C(28,2) = 378` total ordered-unique pairs, of
which **256 are structurally shared-pool** (nonzero WID overlap on at least
one state group — the actual L2.5 gate surface) and **122 are structurally
disjoint** (no allocator contention possible, permanently out of scope).

## Eligibility rule (ratified, replaces all prior ad hoc rules)

A process is **eligible** for L2.5 pair selection iff, on a fresh run:

- `bucket == DETERMINISTIC` (6 processes): `scripts/probe_l2_1_strict_rubric.audit_one_process(name)["verdict"] == "GENUINE"`.
  `PARTIAL`/`COINCIDENTAL`/`UNINFORMATIVE`/`FAIL`/`ERROR` are **not** eligible
  — only GENUINE means the biology actually fired and bit-identity held; the
  others are known-gap-adjacent per the strict-rubric taxonomy and would be a
  silent waiver if counted.
- all other (`in_scope_L2_2: true`, 22 processes): a fresh
  `scripts.l22_evidence.generator.build_evidence_index()` row has
  `mechanical_verdict == "PASS"`. The tracked `evidence_index.json` is never
  read for this determination — this project's own `audit()` tooling
  currently reports `STALE_VS_TREE` against it (the composition-harness
  runner source changed since it was generated), so trusting the stored file
  would itself be a no-waiver violation.
- Any exception/import failure during re-derivation fails **closed** (not
  eligible), never defaults to eligible.

A process additionally carries a **known short-circuit gap** flag if its
`oc_module` source still contains a live `trace_hint` token (mechanical grep,
re-verified every run, cross-referenced against
`docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md` but not trusted as a static list).
A gap-flagged process is never eligible for *selection* into the minimal
covering set, regardless of its gate verdict, per the "no known-gap waiver"
hard rule.

## Coverage obligations (ratified)

Required coverage classes are themselves derived — not hand-chosen — from
what is structurally present among the 256 shared-pool pairs:

1. **oracle_complexity** ∈ {stochastic_stochastic, deterministic_stochastic, deterministic_deterministic}
2. **contention_tier** ∈ {1, 2, 3} (WID-overlap-derived contention tier from `derive_l25_pair_matrix._classify_pair`)
3. **shared_wid_channel** ∈ {substrates, enzymes, monomers, complexs, rnas} (whichever channels have nonzero overlap in at least one shared-pool pair)

Owner-manifest / write-conflict-resolution / composition-order coverage
(named in the case-directive's third quoted line) is **not** operationalized
as a per-pair selection predicate: `data/schemas/owner_manifest.toml` does
not exist yet (D1.2 of `L2_5_HARNESS_DESIGN.md` was designed but never
implemented), and composition-order/write-conflict-resolution are harness-level
policies (`L2_5_HARNESS_DESIGN.md` D2/D3) applied uniformly to whichever
pairs are executed, not properties that vary per selected pair. These remain
tracked as **blockers** (below), not silently-passed coverage classes.

## Current honest result (as of this ratification)

Running `bin\oc-py scripts/derive_l25_scope.py`:

- **Eligible processes: 2/28** (ProteinActivation, TerminalOrganelleAssembly — both `DETERMINISTIC`/L2.1-GENUINE).
- **Gap-free eligible: 1/28** (ProteinActivation only — TerminalOrganelleAssembly
  still carries a live `trace_hint` reference in
  `opencell/vivarium/karr_terminal_organelle_assembly.py`).
- **Known-gap processes: 15/28** (ChromosomeCondensation, DNARepair,
  DNASupercoiling, FtsZPolymerization, Metabolism, ProteinDecay,
  ProteinModification, RNADecay, RNAModification, Replication,
  ReplicationInitiation, TerminalOrganelleAssembly, Transcription,
  TranscriptionalRegulation, Translation).
- **Eligible pairs (within the 256-pair shared-pool surface): 0.** The 2
  eligible processes *do* form one pair (ProteinActivation ×
  TerminalOrganelleAssembly), but that pair is **structurally disjoint**
  (zero WID overlap on every state group — confirmed via
  `derive_l25_pair_matrix._compute_pairs`), i.e. it is one of the 122
  structurally-out-of-scope pairs, not one of the 256 shared-pool pairs L2.5
  actually gates. It is therefore correctly excluded from the eligible-pair
  count regardless of eligibility. Separately, only 1 of the 2 eligible
  processes is gap-free (TerminalOrganelleAssembly is not), so even if this
  pair *had* been shared-pool it would still not qualify as gap-free-eligible.
- **Selected pairs: 0. All 11 required coverage classes are UNCOVERED**
  (`UNCOVERED_NO_ELIGIBLE_PAIR`).
- **Validator exit code: 1** (correct — see Beat 3 above).

This is the disciplined outcome required by the spec-authority quote: *"L2.5
starts only after L2.2 is all-green for every stochastic process that
participates in any planned L2.5 pair"* — today, **zero** stochastic
processes have a fresh, non-stale L2.2 PASS, so no stochastic-participating
pair (211 SS + 43 DS = 254 of the 256 shared-pool pairs) can be selected
without a waiver. The 2 DD shared-pool pairs
(ChromosomeCondensation+ChromosomeSegregation, HostInteraction+TerminalOrganelleAssembly
per the stale Day-33 `l2_5_gate.pass_list`) each require a *different* pair
of eligible deterministic processes than the one pair that actually is
eligible today, and neither of those two structurally-shared-pool DD pairs
has both members eligible.

## Superseded stale claims (explicit)

The following prior claims are **superseded** by this ratification's live
re-derivation and must not be cited as current status going forward (they
are left in place in `plan.md`/`PROCESS_CATALOG.yaml` as historical record,
not deleted):

1. `plan.md` "strict rubric 28/28" (2026-07-13) — **contradicted**. A fresh
   rerun of the exact same `scripts/probe_l2_1_strict_rubric.py` today gives
   GENUINE=16, PARTIAL not tracked separately here, UNINFORMATIVE=6,
   COINCIDENTAL=5, FAIL=1 (28 total). The "28/28" claim was either measuring
   bit-identity pass rate alone (which conflates COINCIDENTAL/UNINFORMATIVE
   with GENUINE) or is simply stale.
2. `PROCESS_CATALOG.yaml`'s `l2_5_gate.status_2026_06_19_eod` /
   `pass_list` (Day-33 snapshot, 18 pairs marked pass) — **superseded**. It
   predates the current eligibility rule and was never refreshed despite its
   own `refresh_discipline` note ("update ... after every L2.5 pair sweep").
   Left in place per "no edits to shared L2.2 evidence indexes"; this
   ratification's `L2_5_SCOPE_CATALOG.yaml` is the current source of truth.
3. Tracked `docs/phase_f/l2_2_design_a/evidence_index.json` — **stale**.
   `python -m scripts.l22_evidence.generator audit` reports integrity FAIL:
   all 14 previously-PASS rows are `STALE_VS_TREE` (the
   `tests/vivarium/l2_2_design_a_runner.py` / `_l2_2_design_a_runner_helpers.py`
   source changed since the evidence was generated). This ratification's
   eligibility rule never reads this file for that reason.
4. `docs/phase_e/PROCESS_STATUS_ALL_29.md` (Day-19, 2026-06-03) — **stale**,
   predates the 28-process reconciliation and the L2.4 ladder rename; not
   used as an input here.
5. **`plan.md` Day-40 priority option F** ("Process-source cleanup for L2.5
   unlock — Remove `trace_hint` from DNASupercoiling/Replication/RI source")
   — **subsumed, not completed**. Fresh grep confirms `trace_hint` is still
   live in all three named modules (plus 12 others). Option F's 3-process
   scope is a strict subset of this ratification's mechanically-derived
   15-process known-gap list; the actionable successor to option F is the
   `known_short_circuit_gap` column in `L2_5_SCOPE_CATALOG.yaml`, which
   self-updates as trace_hint references are removed. `plan.md`'s Day-40
   entry is left unedited as historical record.
6. `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md`'s hand-curated Day-35 process
   list — **stale/incomplete**. Its 14-name list (Replication,
   ReplicationInitiation, Metabolism, RNADecay, ProteinDecayLight,
   Transcription, TerminalOrganelleAssembly, ChromosomeCondensation,
   DNASupercoiling, FtsZPolymerization, ProteinModification,
   TranscriptionalRegulation, Translation, TranslationV3) omits DNARepair
   and RNAModification, both of which the live mechanical grep in
   `_grep_known_short_circuit_gap` (the authoritative method per this
   ratification's eligibility rule) correctly flags as still carrying a
   `trace_hint` reference today. The static document is not edited (kept as
   historical record of the Day-35 sweep); `L2_5_SCOPE_CATALOG.yaml`'s
   `known_short_circuit_gap` column, mechanically re-derived on every run,
   is the current source of truth and supersedes any hand-curated list.

## 5) Decision ledger

**Decision D1 — Denominator source**
- Question: what fixes the "28" in "28 canonical Karr processes"?
- Options: (1) count `PROCESS_CATALOG.yaml` `processes` list length live; (2) hardcode 28 as a constant; (3) trust `tallies.total_canonical_karr_processes`.
- Chosen: (1), live count, cross-checked equal to 28 by an assertion in tests.
- Rationale: (2) drifts silently if the catalog ever changes; (3) is itself a stored field, same anti-pattern this task fixes elsewhere.
- Tradeoffs: if the catalog gains/loses a row without operator review, the denominator silently changes too — acceptable since the catalog itself is the authoritative process registry.
- Beat-4 inversion: a bad catalog edit silently changes "28" to something else without anyone noticing. Falsifier: `test_denominator_is_28_canonical_processes_with_378_total_pairs` fails loudly if the count drifts.
- Operator escalation: no.

**Decision D2 — Eligibility gate per bucket**
- Question: how does "L2.2 is all-green" / L2.1-equivalent get checked without trusting stored strings?
- Options: (1) live rerun via existing honest-mode scripts (`probe_l2_1_strict_rubric`, `l22_evidence.generator`); (2) build a new independent oracle-comparison harness; (3) trust `PROCESS_CATALOG.yaml`'s per-process status fields.
- Chosen: (1).
- Rationale: both scripts already exist, are honest-mode by construction (verified: `probe_l2_1_strict_rubric` never populates `trace_hint`; `l22_evidence.generator` has its own STALE_VS_TREE tamper-detection), and reusing them avoids "no new infrastructure beyond a simple tracked YAML + validator" violation. (3) is exactly the stale/ambiguous denominator this task must fix.
- Tradeoffs: eligibility now requires local oracle trace files (`.h5`) and evidence-sweep artifacts to be present (both gitignored, not committed) — the deriver fails closed (not eligible) rather than open if they are missing. Documented as a blocker below.
- Beat-4 inversion: a future change makes `build_evidence_index()`/`audit_one_process` silently degrade to a cached/stale result. Falsifier: rerun with a modified runner source file and confirm verdicts change (already demonstrated live: 14 stored PASS rows became FAIL under fresh rebuild).
- Operator escalation: no.

**Decision D3 — Known-gap overlay policy**
- Question: how should live `trace_hint` short-circuits interact with an otherwise-green gate verdict?
- Options: (1) exclude gap-flagged processes from eligibility entirely; (2) mark eligible but exclude from *selection* only (a distinct `eligible_gap_free` flag), leaving affected coverage classes UNCOVERED rather than silently waived; (3) ignore gaps (rely solely on L2.1/L2.2 gate verdicts).
- Chosen: (2).
- Rationale: (1) conflates two different facts (gate honesty vs. known code gap) and would make the eligibility table harder to audit; (3) is exactly the waiver the hard rules forbid. (2) keeps both facts visible and makes the "no waiver" outcome explicit and auditable (UNCOVERED_ONLY_VIA_KNOWN_GAP vs UNCOVERED_NO_ELIGIBLE_PAIR are reported as distinct reasons).
- Tradeoffs: today this produces 0 selectable pairs even though 2 processes gate-pass, because only 1 is gap-free — this is intended, not a bug.
- Beat-4 inversion: the grep heuristic could false-negative (miss a differently-named short-circuit) or false-positive (a benign comment mentioning `trace_hint`). Falsifier: manual review of `L2_5_SHORTCIRCUIT_AUDIT.md`'s process list against grep results (checked: all 12-14 Day-35-listed processes are a subset of the live 15-process grep result).
- Operator escalation: **yes** — QO1 below.

**Decision D4 — Coverage-class definition**
- Question: what does "minimal covering set" have to cover?
- Options: (1) cross-product of all 5 dimensions in the case directive (substrates/owner-manifest/write-conflict/composition-order/WID-alignment); (2) only the 3 dimensions that are mechanically derivable per-pair today (oracle_complexity, contention_tier, shared_wid_channel); (3) a single flat "≥1 pair" requirement.
- Chosen: (2), with owner-manifest/write-conflict/composition-order explicitly carried forward as **blockers**, not fabricated coverage classes.
- Rationale: (1) would require inventing a stand-in for `owner_manifest.toml`, which doesn't exist — that is new infrastructure beyond what this task authorizes ("no new infrastructure beyond a simple tracked YAML + validator unless concrete pain proves it necessary"), and would silently claim coverage of something not actually tested. (3) is too weak to catch the pre-mortem (a) failure mode (a small hand-picked pair list missing a real contention edge).
- Tradeoffs: the ratification is honest that 2 of the 5 named test dimensions are not yet operationalizable as selection predicates.
- Beat-4 inversion: someone reads "coverage obligations" and assumes owner-manifest wiring is covered. Falsifier: this doc's explicit "Coverage obligations" section and the blockers list both name the gap.
- Operator escalation: no (self-resolved by "no new infrastructure" hard rule).

**Decision D5 — Selection algorithm**
- Question: how to pick a *minimal* covering set deterministically?
- Options: (1) deterministic greedy set-cover over gap-free eligible pairs, iterating coverage classes in a fixed sorted order, reusing `derive_l25_pair_matrix`'s existing deterministic pair ordering as tie-break; (2) exhaustive optimal set-cover (NP-hard in general, unnecessary at this scale); (3) manual hand-picked list.
- Chosen: (1).
- Rationale: greedy set-cover is a standard, simple, well-understood algorithm; determinism comes from reusing the already-deterministic pair ordering, not from a new sort. (3) is exactly pre-mortem failure mode (a).
- Tradeoffs: greedy is not guaranteed globally minimal, only locally minimal per class in processing order — acceptable given the goal is "a reviewer can regenerate the pairs," not "the provably smallest possible set."
- Beat-4 inversion: greedy could pick a pair that blocks a smaller solution for a later class. Falsifier: with today's data this is moot (0 eligible pairs); `test_selection_covers_a_class_with_a_gap_free_eligible_pair` and `test_selection_never_uses_a_known_gap_process_even_if_it_would_cover_a_class` exercise the logic on synthetic data where it matters.
- Operator escalation: no.

**Decision D6 — Registry/pair-universe drift hardening (added after Opus review)**
- Question: can `ok=True` ever be reported when the *inputs* to the derivation
  have silently drifted (a per-process TOML deleted, a catalog row lost) even
  though the *coverage arithmetic* on the shrunk inputs happens to look
  satisfied?
- Options: (1) trust `len(verdicts) == 28` alone (the pre-review state); (2)
  add an explicit `_check_registry_integrity()` gate asserting
  `{catalog names} == {schema names}`, `len(catalog) == 28`,
  `total_pairs == 378`, `shared_pool == 256`, `disjoint == 122`, wired into
  `ok` as a hard AND; (3) re-derive the 28-count from a third independent
  source as a triple-check.
- Chosen: (2).
- Rationale: (1) is unsound because `verdicts` is always computed from the
  full catalog (`_load_raw_catalog_rows`) independently of whether the
  *separate* schema-loading path (`pairmat._load_process_schemas`, reading
  `data/schemas/per_process/*.toml`) still reflects all 28 processes — if a
  TOML goes missing, `all_pairs`/`shared_pool_pairs` silently shrink,
  `_required_coverage_classes` (computed only from the pairs it is given)
  shrinks correspondingly, and a degenerate near-empty coverage requirement
  can be trivially "satisfied" while `len(verdicts) == 28` remains true and
  masks the drift. (3) is unnecessary new infrastructure for a problem (2)
  already closes cheaply.
- Tradeoffs: none identified; the check is pure arithmetic over data already
  loaded, adds no new files or schemas.
- Beat-4 inversion: exactly the failure `test_registry_integrity_catches_drastic_schema_shrink_that_would_otherwise_look_covered`
  demonstrates directly — shrinking the live schema set to the 2 eligible
  processes alone (whose only pair is structurally disjoint) drives
  `structural_shared_pool_pairs` and `n_uncovered_classes` both to 0, which
  the pre-review `ok` formula would have read as passing. Falsifier: that
  test asserts `registry_integrity.ok is False` and `ok is False` under this
  exact mutation.
- Operator escalation: no.

**Decision D7 — Fail-closed default for unverifiable `oc_module` in the short-circuit grep (added after Opus review)**
- Question: what should `_grep_known_short_circuit_gap` return when a
  process's `oc_module` is missing/`None` or its declared path does not
  exist on disk (i.e. the live grep itself cannot run)?
- Options: (1) fail open — treat "cannot verify" as "not a gap" (the
  pre-review behavior); (2) fail closed — treat "cannot verify" as "is a
  gap" (`known_short_circuit_gap=True`), which is the *safe* direction since
  a `True` gap only ever narrows gap-free eligibility, never widens it; (3)
  raise a hard error and abort the whole derivation.
- Chosen: (2).
- Rationale: `known_short_circuit_gap=True` is what excludes a process from
  gap-free selection; defaulting an unverifiable module to `False` would
  silently let a process whose short-circuit status literally cannot be
  checked become gap-free-eligible — precisely the "waiver by omission"
  failure mode this task's hard rules forbid. (3) is disproportionate: today
  this branch is dead code (all 28 catalog rows declare an existing
  `oc_module`), so aborting the whole run over a currently-unreachable path
  would be over-engineering ahead of concrete pain.
- Tradeoffs: none observed today (branch is currently unreachable, confirmed
  by grep over the generated catalog); this is purely defensive for a future
  catalog regression.
- Beat-4 inversion: a future catalog edit drops a process's `oc_module`
  field. Falsifier: `test_grep_known_short_circuit_gap_missing_module_fails_closed`
  and `test_grep_known_short_circuit_gap_none_module_fails_closed` assert
  `gap is True` for both cases.
- Operator escalation: no.

## Critique self-audit

| Pre-mortem / hard rule | Addressed by |
|---|---|
| (a) small hand-picked pair list misses a real contention edge | D5: deterministic greedy set-cover over mechanically-derived coverage classes, not a hand list; today's answer is 0 pairs so the risk is moot but the algorithm is tested (`test_selection_*`) |
| (b) stale 29-process or old L2.1-calibrated claims leak into eligibility | D1 (live 28-count), superseded-claims §5 names `PROCESS_STATUS_ALL_29.md` and the 28/28 strict-rubric claim explicitly as not used |
| (c) validator reads stored verdict strings instead of rederiving | D2: both gates are live-rerun; `evidence_index.json` and `l2_5_gate.pass_list` are never read by `derive_l25_scope.py` (grep-verifiable: neither filename appears in the script) |
| (d) lane accidentally starts pair execution before process closure | No allocator/harness code touched; `derive_l25_scope.py` only reads/reports, never invokes the composition harness; "no pair execution" hard rule respected |
| No known-gap waiver | D3: `eligible_gap_free` flag; selection algorithm structurally cannot pick a gap-flagged process (`test_selection_never_uses_a_known_gap_process_even_if_it_would_cover_a_class`) |
| 28 Karr processes is the denominator | D1 |
| No new infrastructure beyond simple tracked YAML + validator | D4; one new script + one new YAML + one new test file; no new schema family, no new harness |
| Registry/pair-universe drift cannot silently flip `ok` to True | D6: `_check_registry_integrity()` hard-gates `ok`; `test_registry_integrity_*` mutation tests prove missing-TOML/catalog drift cannot shrink required coverage and pass anyway |
| Unverifiable short-circuit status must not silently clear a gap | D7: fail-closed default; `test_grep_known_short_circuit_gap_missing_module_fails_closed` / `_none_module_fails_closed` |

## 10) Risks and residual unknowns

**R1. Local-only dependency on gitignored oracle data**
- Likelihood: certain (already true today).
- Impact: medium — the deriver cannot run (fails closed) in an environment without `.h5` oracle traces or evidence-sweep artifacts.
- Detection: `_l2_1_verdict`/`_l2_2_verdicts` return `ERROR` verdicts, which are never eligible.
- Mitigation: none needed for this task's scope (execution environments are expected to have this data, same as the rest of the L2.1/L2.2 test suite); documented here so it isn't mistaken for a bug.
- Owner: whichever lane next re-runs the derivation.

**R2. `trace_hint` grep heuristic is not a certified gate**
- Likelihood: low-medium (heuristic, not semantic analysis).
- Impact: medium — could under- or over-flag a process.
- Detection: cross-checked against `L2_5_SHORTCIRCUIT_AUDIT.md`'s Day-35 list; all named processes are covered by the live grep result.
- Mitigation: documented as a heuristic in both the code docstring and this doc; a future lane could replace it with an AST-based check if the heuristic proves wrong in practice.
- Owner: whichever lane implements the actual short-circuit removal (subsumes Day-40 option F).

**R3. Owner-manifest / write-conflict-resolution / composition-order coverage is unoperationalized**
- Likelihood: certain (already true — `owner_manifest.toml` doesn't exist).
- Impact: high for eventual pair *execution* (not this task's scope), low for this ratification (explicitly called a blocker, not silently passed).
- Detection: `Test-Path data/schemas/owner_manifest.toml` → False (verified).
- Mitigation: none in this lane; flagged as a blocker for whichever lane implements D1.2 of `L2_5_HARNESS_DESIGN.md`.
- Owner: allocator/harness implementation lane (explicitly out of scope here per "no allocator implementation").

**R4. Eligible-pair count may remain 0 for a long time**
- Likelihood: medium — closing even one more coverage class requires fixing an L2.2 STALE_VS_TREE regeneration for ≥2 processes AND removing their `trace_hint` gap, or getting a second DETERMINISTIC process to GENUINE+gap-free.
- Impact: low for this task (the ratification's job is to state the honest number, not to unblock it) — high for the overall L2.5 workstream's momentum.
- Detection: rerun `scripts/derive_l25_scope.py` after any L2.1/L2.2/gap-removal work lands.
- Mitigation: none required here; this is the expected, disciplined state of the project per the hard rules.
- Owner: N/A (not this task's scope).

## Open question for operator

QO1. Should the `trace_hint` known-gap overlay be widened from a substring
grep to an AST-based check (e.g. detecting the specific `states.get("trace_hint", ...)` call pattern) to reduce false-positive/negative risk (R2)?
- Why unresolved: today's grep matches every process `L2_5_SHORTCIRCUIT_AUDIT.md` already lists, so there's no empirical evidence of a false result yet.
- Options: (1) keep the simple grep (current); (2) build an AST check now.
- Recommended default: (1) — "no new infrastructure ... unless concrete pain proves it necessary"; revisit if a grep false-positive/negative is ever found.
- Risk if wrong: a process could be wrongly excluded (safe direction) or wrongly cleared (unsafe direction, e.g. if `trace_hint` is renamed to something else that still short-circuits) — the latter is the real risk to watch for.

## Scope boundary

In scope:
1. Denominator, eligibility rule, known-gap overlay, coverage-class
   definition, minimal-covering-set selection, and their machine-readable
   catalog + validator + tests.
2. Reconciling the Day-40 "source cleanup" prose item and other stale claims
   (pointer-only, no deletion).

Out of scope (explicitly, per hard rules):
1. Pair execution (running the actual L2.5 composition harness on selected pairs).
2. Allocator / owner-manifest implementation.
3. Regenerating the 14 STALE_VS_TREE L2.2 evidence rows or fixing any `trace_hint` short-circuit.
4. Editing `PROCESS_CATALOG.yaml`'s `l2_5_gate` block or `evidence_index.json` (shared L2.2 evidence indexes).

Deferred follow-ups:
1. Removing `trace_hint` short-circuits (subsumes Day-40 option F; 15 processes now precisely identified).
2. Implementing `data/schemas/owner_manifest.toml` (D1.2 of `L2_5_HARNESS_DESIGN.md`).
3. Regenerating fresh L2.2 evidence for the 14 STALE_VS_TREE processes.
4. Building the L2.2 harness for the 4 EVENT_CLASS processes currently MISSING_EVIDENCE (Cytokinesis, DNADamage, FtsZPolymerization, RibosomeAssembly).
