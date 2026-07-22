# The True State of the L-Ladder — 2026-07-22

> ## ⚠️ CORRECTION (2026-07-23) — READ BEFORE TRUSTING §1 / §2
>
> The L2.2 verdicts used below (§1 rung table, §2 per-process matrix) were sourced
> from the pinned `test_l2_2_strict_rubric.py` / `L2_2_STRICT_RUBRIC_BASELINE.md`.
> **Those L2.2 "VERIFIED_GENUINE" labels are NOT reproducible and must not be
> trusted.** Verified live on 2026-07-23:
> - **The L2.2 pin is a tautology.** `test_l2_2_strict_rubric.py` only checks the
>   pin equals a hardcoded `EMPIRICAL_VERDICTS` dict in
>   `scripts/probe_l2_2_strict_audit.py`. No live run happens. The test's own
>   docstring admits: *"Real upper bound on honest L2.2 PASSes: 4 of 22."*
> - **The empirical artifacts are gone.** `tmp/l2_2_audit/` is empty.
> - **ProteinDecay = FAIL on a live re-run** (`l2_2_design_a_runner.py`, 50 seeds ×
>   10 ticks): substrates W1 = 2.09 vs threshold 1.0, ≥30 samples on both sides —
>   a genuine gateable fail. It is pinned `VERIFIED_GENUINE`.
> - **RNAModification is rejected by the runner** as unsupported / out-of-scope —
>   its `VERIFIED_GENUINE` was never runner-obtainable.
>
> **Consequence:** the "11–12 truly CLOSED" count below is **OVERSTATED**. 8 of
> those 11 are stochastic processes resting on the hollow L2.2 pin; only the 3
> deterministic (L2.1-only) rows are potentially safe, and even those rest on an
> L2.1 pin not re-verified live. **True closed count = UNKNOWN** pending a live
> L2.2 re-baseline. The runner also logged `KARR_SINGLE_SEED_REUSED` — the Karr
> "distribution" may be one seed replicated, which would undermine the
> distributional premise itself.
>
> **Caveat (RESOLVED 2026-07-23):** ProteinDecay was disambiguated by running the
> identical runner on `main` (pre-uncap). Result is **byte-identical** to the
> branch (substrates FAIL @ W1=2.086792). So the FAIL is **NOT an uncap regression**
> — the pin was always disconnected from the runner. ProteinDecay's own code
> (`karr_protein_decay*.py`) is unchanged between main and branch, confirming this.
>
> Everything below is retained as originally written (do not delete — it is the
> record of what the ledger *claimed*). Treat §1 L2.2 column and §2 as
> **unverified** until a live re-baseline replaces the pins.

**Purpose.** One honest, grounded snapshot of where every rung and every process
*actually* stands, so we can choose what to drive to *closure* instead of
starting a new half-job. Written in response to the operator question: *"why are
we in such a spaghettified, half-validated state with no sign of closure?"*

**Sourcing discipline.** Each row cites the **live** authority (a CI-pinned test,
a table, or a plan block), NOT the legacy status docs. Where a legacy "source of
truth" doc disagrees with the live authority, that conflict is called out — the
stale docs are themselves part of the problem.

> **Authoritative (live) sources used**
> - L2.1 verdicts → `tests/vivarium/test_l2_1_strict_rubric.py` `EXPECTED_VERDICTS` (CI-pinned)
> - L2.2 verdicts → `docs/phase_f/L2_2_STRICT_RUBRIC_BASELINE.md` (Day-37, 2026-06-23, empirical) + `tests/vivarium/test_l2_2_strict_rubric.py`
> - Ladder definitions → `plan.md` L-ladder block (reconciled 2026-07-02)
> - Gate 0/1/2, L2.4, A1-uncap → `plan.md` operational-handoff block (2026-07-19)
> - Metabolism fix state → `metab_fix_phases` session table
> - L2.5 → `docs/phase_f/L2_5_PAIR_TRACKER.md` (Day-33, 2026-06-19)
>
> **KNOWN-STALE docs (do NOT trust for current state):**
> - `docs/phase_e/L2_STATUS.md` — dated 2026-05-30, says L2.1 = "9 GREEN". Wrong.
> - `docs/phase_f/l2_2_design_a/L2_2_GATE_TRACKER.md` — 2026-06-06, says all 22 L2.2 "MISSING-DATA". Wrong (runner was later built).
> - `docs/phase_e/PROCESS_STATUS_ALL_29.md` — points at the two docs above.

---

## 1. Rung-level status

Legend: 🟢 built + passing · 🟡 built, partial/mixed · 🟠 designed, not built · ⚪ not started

| Rung | What it tests | Gate built? | Honest coverage / verdict | Live source |
|---|---|---|---|---|
| **L1a** | process fires (trace bytes > threshold) | 🟢 | 28/28 GREEN | plan.md ladder |
| **L1b** | wiring conformant (static row-vs-code) | 🟢 | 28/28 PASS (2026-07-01) | plan.md |
| **Gate 0** | fixture ⟺ live MATLAB source | 🟢 CI | 368/368 constants+vocab+stoich, 0 gaps | plan.md handoff |
| **Gate 1** | frozen spec ⟺ fixture (hash-freeze) | 🟢 CI-blocking | 28/28 hash-locked | plan.md |
| **Gate 2** | OC code ⟺ frozen spec | 🟢 CI-blocking | vocab 28/28 CONFORM; stoich 6 CONFORM + 22 N/A; verdict PASS | plan.md |
| **L2.0** | observable schema (static) | 🟢 | 28/28 GREEN *(per legacy headline; not independently re-verified this pass)* | L2_STATUS (stale) |
| **L2.0a** | allocator produces right per-process input | 🟠 | **0 — designed `9c44454`, build blocked on WSL** | plan.md |
| **L2.1** | per-process bit-identity replay | 🟢 CI-pinned | **18 GENUINE / 6 UNINFORMATIVE / 3 COINCIDENTAL / 1 FAIL** | test_l2_1_strict_rubric.py |
| **L2.2** | per-process distributional (ensemble) | 🟡 runner built | **10 VERIFIED_GENUINE / 1 VERIFIED_FAIL / 11 unsupported** | L2_2_STRICT_RUBRIC_BASELINE |
| **L2.4** | chassis autonomous conservation (28 procs ×100t) | 🟢 | A+B PASS on uncapped branch, 100t×4s, non-vacuous | plan.md handoff |
| **L2.5** | shared-pool composition (pairs) | 🟡 PAUSED | **18 PASS / 20 FAIL / 8 SKIP / 210 UNTESTED** of 256 in-scope | L2_5_PAIR_TRACKER |
| **L3** | direct coupling (2 procs, no pool) | ⚪ | not started (framework sketched) | plan.md |
| **L4** | submodel cluster vs Karr oracle | ⚪ | not started | plan.md |
| **L5** | whole-cell phenotype, ~30K ticks | ⚪ | not started | plan.md |

**Load-bearing caveat — the A1 uncap is unmerged.** The uncapped-allocator work
(`adf2d1a` + RNG fix `04d15e1` + txv3 `3fe4bef`) and the L2.4 gate that certifies
it live on branch **`agent/l2-0a-uncap`, NOT merged to main**, pushed only through
`04d15e1`. Everything after is local. So L2.4-green + uncap is a *branch* result,
not a *repo* result.

---

## 2. Per-process matrix (the two per-process rungs)

L2.2 is out-of-scope for the 6 deterministic processes (L2.1 is sufficient for
them). "Net state" is my honest one-word terminal classification.

| # | Process | L2.1 (bit-identity) | L2.2 (distributional) | Net honest state |
|---|---|---|---|---|
| 1 | MacromolecularComplexation | GENUINE | VERIFIED_GENUINE (W1=0.0) | ✅ **CLOSED** |
| 2 | ProteinFolding | GENUINE | VERIFIED_GENUINE (W1=0.0) | ✅ **CLOSED** |
| 3 | ProteinProcessingI | GENUINE | VERIFIED_GENUINE (W1=0.0) | ✅ **CLOSED** |
| 4 | ProteinProcessingII | GENUINE | VERIFIED_GENUINE (W1=0.0) | ✅ **CLOSED** |
| 5 | tRNAAminoacylation | GENUINE | VERIFIED_GENUINE (W1=0.0) | ✅ **CLOSED** |
| 6 | ProteinModification | GENUINE | VERIFIED_GENUINE | ✅ **CLOSED** |
| 7 | RNAProcessing | GENUINE | VERIFIED_GENUINE (≈exact) | ✅ **CLOSED** |
| 8 | RNADecay | GENUINE | VERIFIED_GENUINE (W1=65, in noise) | ✅ **CLOSED** |
| 9 | ProteinDecay | COINCIDENTAL | VERIFIED_GENUINE (W1=9.5) | 🟢 **CLOSE-ABLE** (L2.1 coincidental but L2.2 genuine — pin honestly) |
| 10 | RNAModification | UNINFORMATIVE\* | VERIFIED_GENUINE (W1≈0.09) | 🟢 **CLOSE-ABLE** (\*pin/blog conflict — see §4) |
| 11 | DNASupercoiling | GENUINE | NOT_WIRED | 🟡 needs L2.2 wiring |
| 12 | FtsZPolymerization | GENUINE | NOT_WIRED | 🟡 needs L2.2 wiring |
| 13 | ProteinActivation | GENUINE | (deterministic — n/a) | ✅ **CLOSED** |
| 14 | ReplicationInitiation | GENUINE | NOT_WIRED | 🟡 needs L2.2 wiring |
| 15 | TerminalOrganelleAssembly | GENUINE | (deterministic — n/a) | ✅ **CLOSED** |
| 16 | Transcription | GENUINE | LAUNDERED_VIA_HINT_FEED | 🟠 L2.2 verdict not trustworthy (hint injected) |
| 17 | TranscriptionalRegulation | GENUINE | (deterministic — n/a) | ✅ **CLOSED** |
| 18 | Translation | GENUINE | LAUNDERED_VIA_HINT_FEED | 🟠 L2.2 verdict not trustworthy (hint injected) |
| 19 | Metabolism | GENUINE (shallow) | **VERIFIED_FAIL (W1=171 vs 102)** | 🔴 **OPEN — the hard one** |
| 20 | ProteinTranslocation | GENUINE | CRASH_HARNESS_BUG (shape 482→2892) | 🟠 L2.2 harness broken |
| 21 | DNARepair | COINCIDENTAL | NOT_WIRED | 🟡 real gap both rungs |
| 22 | Replication | COINCIDENTAL | NOT_WIRED | 🟡 real gap both rungs |
| 23 | DNADamage | UNINFORMATIVE | NOT_WIRED | ⚪ quiescent in window (event-class) |
| 24 | ChromosomeSegregation | UNINFORMATIVE | (deterministic — n/a) | ⚪ no-op window (event-class → L5) |
| 25 | Cytokinesis | UNINFORMATIVE | UNVALIDATABLE_EVENT_CLASS | ⚪ event-class → needs L2.event/L5 |
| 26 | HostInteraction | UNINFORMATIVE | (deterministic — n/a) | ⚪ genuinely no-op (N/A) |
| 27 | RibosomeAssembly | UNINFORMATIVE\* | UNVALIDATABLE_EVENT_CLASS | ⚪ event-class (\*pin/blog conflict — see §4) |
| 28 | **ChromosomeCondensation** | **FAIL** | (deterministic — n/a) | 🔴 **OPEN — the only L2.1 FAIL** |

**Tally (net honest state) — sums to 28:**
- ✅ CLOSED (validated at every *per-process* rung that applies): **11**
- 🟢 CLOSE-ABLE with a pin/verdict decision (no new porting): **2** (ProteinDecay, RNAModification)
- 🟡 real gap, bounded work: **5** (DNASupercoiling, FtsZ, ReplicationInitiation, DNARepair, Replication)
- 🟠 harness/laundering blocks the verdict: **3** (Transcription, Translation, ProteinTranslocation)
- ⚪ event-class / genuine no-op, deferred to L2.event/L5 by design: **5** (DNADamage, ChromosomeSegregation, Cytokinesis, HostInteraction, RibosomeAssembly)
- 🔴 genuinely OPEN hard problems: **2** (Metabolism, ChromosomeCondensation)

> **"CLOSED" caveat:** these 11 are validated at every rung defined at the
> *per-process* granularity — L2.1 for deterministic processes; L2.1 **and** L2.2
> for stochastic ones. They are **not** individually validated at the integration
> rungs (L2.5 pairwise / L3+), but neither is anything else — those rungs are
> barely started. "CLOSED" = "done to the highest per-process fidelity bar we
> currently enforce," not "proven correct inside the whole-cell chassis."

---

## 3. Why it *feels* like everything is half-done (root causes)

1. **"Green" was overloaded.** For a long stretch, "28/28 green" meant *strict-rubric
   test-pins match*, not *validated*. A regression guard passing is not a fidelity
   proof. This manufactured false closure — see the Day-22 blog "nine out of
   twenty-eight" and the Day-37 re-audit dropping the honest L2.1 number from
   "28" to "9→18".

2. **No enforced Definition of Done.** Items reach *diagnosed* / *WIP* / *green-ish*
   and attention moves. Nothing forces a declared terminal state before the next
   thing starts, so half-done is the equilibrium.

3. **Delegation deaths leave sediment.** Codex dies at 90k–520k tokens (Azure).
   The commit-immediately guardrail (correct — prevents *losing* work) also
   *manufactures* unvalidated commits (e.g. ChromCond `381ea0e`, still FAIL) and
   17 dead delegations (`dead_swarm` table).

4. **Under-scoped diagnoses.** Work starts on a "small filter tweak" that turns
   out to be a 354-line Chromosome-state port (ChromCond), hits the wall, banks.

5. **The docs lie.** Three "single source of truth" trackers are stale by 6–8
   weeks and mutually contradict the live pins. When the map is wrong, every
   traversal re-discovers the terrain.

**What is *not* dysfunction (genuine hardness):** bit-identity against a 2012
MATLAB whole-cell model (MCG16807 RNG, sparse circular chromosome, LP degeneracy)
is legitimately brutal; the last 5% (exact identity) is often 80% of the work.
Banking at "distributionally validated" is sometimes the *correct* engineering
call. The dysfunction is that we bank **silently and unpinned**, so the ledger
lies about it afterward.

---

## 4. Open conflicts the ledger must reconcile

- **L2.1 pin vs dev blog (RNAModification, RibosomeAssembly).** The CI pin
  (Day-37) says both are `UNINFORMATIVE`. The Day-50–53 blog
  (`2026-07-14-...the-skips-that-werent...`) says both were *fixed to bit-identical*
  via event-window extraction + single-loop port. Most likely reconciliation:
  the fix validated them on an **event-window trace**, while the standing strict
  rubric still runs the **quiet 1–100 tick window** where they no-op. Both can be
  "true" on different traces — but the pin should be updated to reflect the
  event-window PASS, or the conflict documented in the pin. **Unreconciled.**

- **Metabolism L2.2 W1 is stale.** Baseline W1 = 171.39 (Day-37, threshold 102.51).
  Since then `metab_fix_phases.p0` (GLPK discipline) landed (writeback L1
  124551→22412), but **`w1_after` is NULL — the gate was never re-measured.**
  This is the single highest-value unknown number in the whole ladder.

---

## 5. The fossil layer (should be buried, not carried)

- **79 blocked todos.** ~43 are the *original phased roadmap* (`p2-*`×13, `p5-*`×10,
  `p6-*`×8, `p4-*`×7, `p3-*`×5) — the "toy cell" architecture (`models/metabolism.py`,
  `models/transcription.py`, `core/events.py`) that was **superseded** by the
  Karr-replay approach. They are not blocked; they are *abandoned*. Carrying them
  as "blocked" inflates the sense of unfinished work.
- **17 dead delegations** (`dead_swarm`) — codex sessions that died without landing.
- **3 stale trackers** (§Sourcing) presenting 6–8-week-old numbers as truth.
- **Superseded design docs** — multiple `L2_2_METABOLISM_LP_DEGENERATE_DESIGN` v1→v3→V4,
  `L1C_*` (renamed to L2.4). Fine as history; they should sit below an archive divider.

---

## 6. Closure candidates, ranked by effort-to-terminal

| Rank | Item | Effort | Terminal move |
|---|---|---|---|
| A | Bury fossils | ~30 min | Mark ~43 `p2–p6` todos `KILLED`; add archive banners to the 3 stale trackers pointing here |
| B | ProteinDecay + RNAModification pins | ~30 min | Reconcile §4 conflict; flip L2.1 pins to honest verdict (L2.2 GENUINE) |
| C | **Metabolism W1 re-measure** | ~1–2 h (Azure-independent, I can run it) | Run `run_l2_2_metabolism_glpk_audit.py`; record `w1_after` in `metab_fix_phases`. **Turns the biggest unknown into a number.** |
| D | Land the A1 uncap | ~1 h | Push `agent/l2-0a-uncap`, decide merge-to-main (L2.4 already certifies it) |
| E | ChromosomeCondensation → GENUINE | **multi-hour, high-risk** | Resurrect 354-line `getAccessibleRegions` port + debug residual RNG-desync (already ate one 520k-token attempt) |
| F | Metabolism → L2.2 PASS | **multi-day** | Variant-constraint (p1a–p5) vs FVA reframe fork; the genuinely hard research problem |
| G | L2.2 harness repairs | ~half-day | Fix ProteinTranslocation crash; remove Transcription/Translation hint-laundering; re-run |
| H | Wire 5 NOT_WIRED at L2.2 | ~1–2 days | DNASupercoiling, FtsZ, ReplicationInitiation, DNARepair, Replication |

---

## 7. Recommended operating change (for decision, not yet enacted)

**WIP limit = 1.** One item driven to a *declared* terminal state before the next
starts. Terminal state ∈ {**GENUINE-validated** | **DEFERRED** (honest pin + cost
recorded) | **KILLED**}. No fourth "WIP-banked-and-forgotten" option.

Suggested first sequence to build closure momentum: **A → B → C** (all low-effort,
Azure-independent, each ends in a *declared* state), then decide E-vs-F-vs-D with
real numbers in hand.

---

*Generated 2026-07-22. Live sources cited inline. This artifact supersedes the
status claims in the three stale trackers named in §Sourcing until they are
re-baselined or archived.*
