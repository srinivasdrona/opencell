# Stoichiometry Fidelity Gate — Design (v2, rework)

**Status:** DRAFT v2 (2026-07-09, post gpt-5.4 rubber-duck NEEDS-REWORK).
Static, MATLAB-free. Strengthens the L1b wiring gate's stoichiometry check from
*metadata-only* to *species-set equivalence per side*. v1 was reworked after the
review found 4 blocking flaws (oracle shape, `none` class, coefficient semantics,
deviation enforceability) — all reproduced and confirmed below.

## DAP Intent (Slot 1)

Deliberately build a gate that **fails closed** when a process's ported
consume/produce species set does not match Karr's extracted stoichiometry oracle,
compared on the correct key (WID, and compartment where the oracle carries one)
and the correct membership rule (side presence, not net sign). Every difference
is either a fix or an explicit, typed, ratcheted `known_deviation`. The gate
proves the **species set**; it makes **no** claim about coefficient magnitudes —
those are L2.1's job. Overclaiming coefficient fidelity would itself be a new
hollow green, so it is explicitly out of scope.

## Spec Authority Quote Block

Authoritative spec = the extracted Karr stoichiometry oracle, one JSON per
process: `data/karr_method_inventory/karr_stoichiometry/<Process>.json`.

Verified shape facts (probed 2026-07-09, drive the whole design):

- **`role` has THREE values, not two:** `consume`, `produce`, **`both`**.
  221 `both` entries exist (e.g. `FtsZPolymerization` GTP/GDP with
  `net_coefficient = 0.0`). ⇒ **net sign cannot be used** to decide the side; a
  `both`/net-0 species consumed-and-produced would be invisible to a sign proxy.
- **Membership is coefficient-total, not role string:** each substrate carries
  `consume_coefficient_total` and `produce_coefficient_total`. Use these:
  `expected_consume = {wid : consume_coefficient_total > 0}`,
  `expected_produce = {wid : produce_coefficient_total > 0}`. A `both` WID lands
  in both expected sets automatically.
- **Some oracles carry a compartment axis.** `Metabolism.json` has 792 substrate
  entries but only 585 unique WIDs (207 WIDs duplicated across compartments) and
  each entry has a `compartment`. ⇒ WID-only set equality would collapse distinct
  compartmental rows; the comparison key must be `(wid, compartment)` whenever the
  oracle entries carry a compartment.
- **`class ∈ {matrix (10), inline (13), none (5)}`.** `class == none` means **no
  small-molecule metabolite oracle exists for this process** (it operates on the
  protein/complex/chromosome state layer), NOT "the process consumes nothing."
  Confirmed: MacromolecularComplexation (`none`) row has 4 consume / 4 produce;
  ProteinActivation (`none`) 4/4; TerminalOrganelleAssembly (`none`) 8/8 — all
  legitimate state-layer transfers with no metabolite oracle to diff against.

Ported artifact under test = the per-process wiring row
`data/schemas/per_process_wiring/<Process>.yaml` (schema v2,
`data/schemas/per_process_wiring/_schema.yaml`): `consume_stoichiometry[]` /
`produce_stoichiometry[]` entries `{wid, compartment, formula_or_constant, kind}`.

**Coefficient literals are NOT net totals.** RNAModification's `AMET` entry is
`kind: constant, formula_or_constant: '-1'` and the row note calls it a
"representative per-reaction coefficient," while the oracle stores the
process-level net `AMET net_coefficient = -29.0`. ⇒ a static `row-literal ==
oracle-net` check is semantically wrong and would mass-false-fail. Coefficient
magnitude is therefore **out of scope** for this gate (→ L2.1).

Existing code is not the spec. `check_stoichiometry_oracle_matches`
(`scripts/l1b_verify_wiring.py:736`) only compares the oracle file's
`class`/`substrate_count`/`sha256`; it reads `oracle["substrates"]` (line 790)
but uses only `len()`, never diffing the row's species. That is the hole.

## 1) Design Contract

**Property proven (GREEN):** For every process **with a metabolite oracle**
(`class ∈ {matrix, inline}`), the set of species the OC row declares it
consumes/produces equals the oracle's expected sets, compared per side and per
`(wid[, compartment])` key, modulo typed `known_deviations`. The gate proves the
*species set*, not the numbers.

**Inputs:** 28 oracle JSONs + 28 wiring rows (both in-repo). No `.mat`, no MATLAB,
no runtime.

**Checks (per process, `class ∈ {matrix, inline}`):**

1. **Consume coverage** — `keys(row.consume_stoichiometry)` ==
   `{key(s) : s.consume_coefficient_total > 0}`, where `key = (wid, compartment)`
   if the oracle entries carry compartments else `wid`.
2. **Produce coverage** — symmetric on `produce_coefficient_total > 0`.
3. **No phantom species** — every row key appears somewhere in the oracle's WID
   (or `(wid, compartment)`) set. Catches typos / cross-process copy-paste.

`both`-role species are handled implicitly by checks 1+2 (present on both sides).
There is **no** role/sign check and **no** coefficient check — both were unsound
(review findings 1 and 3).

**Class handling:**
- `class == none` ⇒ **NOT_APPLICABLE** for coverage (no metabolite oracle to diff).
  The verdict records N/A with the reason; it does not FAIL and does not force an
  empty row. State-layer transfer fidelity for these processes is out of this
  gate's scope (it is a protein/complex-layer concern, not a metabolite one).
- **Metabolism** (`matrix`, compartment axis, 585 WIDs, FBA) is handled with the
  `(wid, compartment)` key AND reuses the existing external-exchange boundary set
  already encoded for `check_orphan_consume_wids` (the 124-WID Metabolism open
  boundary from `Metabolism_flat.mat`). Boundary WIDs are expected-optional, not
  failures. If compartment-keyed reconciliation proves noisy for FBA, Metabolism
  may be explicitly deferred to its L2.2 FBA validation with a documented reason
  (decided during build-step 2, from data, not assumed now).

**Verdict:** all applicable checks pass for every non-N/A process. **Fail-closed**:
missing oracle, unreadable row, unhandled `class`, or unrecognised key shape ⇒
FAIL, never silent SKIP.

**Output:** per-process diff (oracle-only keys, row-only keys, per side) + a
machine-readable JSON, in the L1b gate reporting style.

## 2) Inventory of Existing Artifacts

- Oracle JSONs (spec): `data/karr_method_inventory/karr_stoichiometry/*.json`
  (28 + `index.json`). Built HB1 (`b8a2714`..`4208d89`); MMC → `none` (`2c3c67e`).
- Wiring rows (under test): `data/schemas/per_process_wiring/*.yaml` (v2).
- Weak incumbent: `check_stoichiometry_oracle_matches`
  (`scripts/l1b_verify_wiring.py:736`) — metadata-only; kept for oracle-file
  integrity (hash/count), augmented by the new coverage check.
- Reusable boundary classifier: the 124-WID external-exchange allowlist already
  used by `check_orphan_consume_wids` (Metabolism open boundary).
- Host gate: `scripts/l1b_verify_wiring.py` (28/28, CI-blocking `l1b-gates`).
- First real gap (regression fixture): DNARepair (`class=matrix`) row declares 20
  species; oracle expected-produce includes 6 undeclared BER excision products
  (`FAPyAD, FAPyGN, URA, ho5URA, oxo8AD, oxo8GN`), all with
  `produce_coefficient_total > 0`. `known_deviations` empty. This is exactly a
  produce-coverage FAIL under check 2.

## 5) Decision Ledger

- **D1 — Home: a new L1b wiring check.** `check_stoichiometry_coverage`, plugged
  into the existing CI-blocking gate; complements (not replaces)
  `check_stoichiometry_oracle_matches` (file-integrity) — the two prove different
  things (file intact vs row matches file).
- **D2 — Membership by coefficient-total side presence, keyed by
  `(wid[, compartment])`.** Replaces v1's net-sign proxy and WID-only equality
  (review finding 1). `consume_coefficient_total > 0` ⇒ expected-consume;
  `produce_coefficient_total > 0` ⇒ expected-produce; `both` lands in both.
- **D3 — NO coefficient check.** Row literals are per-reaction representatives,
  oracle stores net totals; they are not statically comparable (review finding
  3). Coefficient/magnitude fidelity is L2.1's. The gate's honest ceiling is the
  species set. (A future v2 row-schema field distinguishing `net_total` vs
  `per_reaction_unit` literals could re-enable a coefficient check; out of scope.)
- **D4 — `class == none` ⇒ NOT_APPLICABLE, never forced-empty.** `none` = no
  metabolite oracle, not "no transfers" (review finding 2). The 5 `none` processes
  keep their state-layer rows; this gate simply has nothing to diff for them.
- **D5 — `known_deviations` becomes typed + ratcheted (schema migration is
  build-step 0).** Migrate `_schema.yaml` `known_deviations` from `array[string]`
  to `array[object]` `{wid, compartment?, side (consume|produce), direction
  (missing|extra), reason, source_anchor}`. The gate matches each coverage
  difference to a deviation by `(wid[,compartment], side, direction)`. Anti-abuse
  (since a static gate cannot enforce human approval): a **committed deviation
  baseline + non-increasing ratchet** — CI FAILs if the total deviation count
  rises above the baseline unless the baseline file is updated in the same commit
  (a visible, reviewable diff). This converts "silent omission" into an explicit,
  diffable, count-bounded decision.
- **D6 — Metabolism special-cased, decided from data in build-step 2.** Either
  `(wid, compartment)` reconciliation with the 124-WID boundary allowlist, or an
  explicit documented deferral to L2.2 FBA validation. Not pre-judged here.
- **D7 — Rollout: build + unit-test the semantics FIRST, then sweep, then merge.**
  Before the 28-process sweep, unit tests must cover the shapes that broke v1:
  `role=both` (FtsZ GTP net=0, RNAModification H2O, tRNAAminoacylation GLU,
  ProteinDecay ATP/H), Metabolism compartment duplicates, and `none`-class rows.
  Only after the gate is green on those fixtures do we enumerate real gaps,
  reconcile all applicable processes (fix or typed deviation), and merge behind
  `l1b-gates`. No report-only mode (that is the hollow-green pattern).

## 10) Self-Audit (slot-3 mapping)

| Risk / review finding | How this v2 kills it |
|---|---|
| Row omits oracle species (DNARepair 6) | check 2 produce-coverage set-equality |
| Row invents a species not in Karr | check 3 no-phantom |
| `both`/net-0 species mis-sided (finding 1) | D2 coefficient-total side presence (no sign proxy) |
| Compartment-distinct rows collapsed (finding 1) | D2 `(wid, compartment)` key |
| `none` process false-failed (finding 2) | D4 NOT_APPLICABLE, no forced-empty |
| Wrong constant-vs-net compare (finding 3) | D3 coefficient check removed; species-set only |
| Deviations re-create silent omission (finding 4) | D5 typed + baseline ratchet + diffable |
| Metabolism FBA noise | D6 compartment-keyed + boundary allowlist, or documented defer |
| Contaminated mass-sweep | D7 semantics unit-tested on the breaking shapes first |
| Gate passes by checking metadata | D1/D2 diff actual species sets, not counts/hashes |
| Overclaiming magnitude fidelity | D3 explicit scope: species set here, numbers → L2.1 |
| Missing oracle / unhandled class silent-skips | fail-closed verdict |

## Build sequence

0. **Schema migration (D5):** `known_deviations` → typed object array in
   `_schema.yaml`; migrate the (currently empty) existing entries; add a
   `data/schemas/per_process_wiring/deviation_baseline.json` (count ratchet).
1. Implement `check_stoichiometry_coverage(row, oracle)` (checks 1–3, D2 keying,
   D4 none-handling, D5 deviation matching + ratchet, D6 Metabolism path).
2. Unit tests FIRST (D7 fixtures: role=both, Metabolism compartments, none-class),
   asserting no false pos/neg on each, plus a DNARepair produce-coverage FAIL and
   a documented-deviation PASS.
3. Run across all 28 → coverage-gap manifest. Decide the Metabolism path (D6) from
   the actual diff.
4. Reconcile every applicable gap (fix the row/code, or add a typed deviation).
   DNARepair's 6 BER products first: adjudicate **emit-the-freed-base (fix)** vs
   **documented deviation** against `DNARepair.m` glycosylase product handling —
   from the MATLAB source, not the summary.
5. Merge behind the blocking `l1b-gates` job once green on all applicable processes.

## Design review log

- **2026-07-09 (gpt-5.4 rubber-duck, v1 → NEEDS-REWORK):** four blocking findings,
  all reproduced and confirmed against the artifacts: (1) oracle has `role=both`
  (221 entries) + a compartment axis (Metabolism 792/585) → net-sign proxy and
  WID-only equality are both wrong; fixed by D2 (coefficient-total side presence,
  `(wid,compartment)` key). (2) `class=none` ≠ empty row (MMC/PA/TOA have real
  state-layer transfers) → fixed by D4 (NOT_APPLICABLE). (3) `kind=constant`
  literals are per-reaction, not net totals (RNAModification AMET row `-1` vs
  oracle `-29`) → fixed by D3 (coefficient check removed; species-set only,
  magnitudes → L2.1). (4) `known_deviations` was `array[string]` and
  "reviewer-approved" is not gate-enforceable → fixed by D5 (typed entries +
  committed baseline ratchet). Rollout hardened (D7) to unit-test the breaking
  shapes before any sweep.
