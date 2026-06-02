# Prefix v2 Validation Rubric

How to score a codex run produced under `DELIBERATE_ACTION_PREFIX_v2.md`.
This rubric lives in the evaluation tooling, not in the codex prompt itself.

## Gate 1 — Inversion concreteness (Beat 4 declarations)

For each failure mode named in the INTENT block's Beat 4 section, classify:

- **Concrete**: names process-specific symbols (WID, store, file:line, code path, fixture key). Could only be written after reading the actual code surface.
- **Generic**: domain-shaped but symbol-free ("tests could pass while still wrong", "fix could change read path but leave write path stale"). Could be copy-pasted across processes.

**Threshold**: at least `N` of `M` named modes must be Concrete. Pick `N` empirically after ≥6 runs. Initial provisional bar: `N ≥ 2` AND `N ≥ ceil(M/2)`. A single Concrete entry + filler does not pass.

Rationale: a binary "did the codex name a concrete failure mode?" lets the agent satisfy the gate with one good entry and four throwaways. The threshold forces the inversion to be a habit, not a token gesture.

## Gate 2 — Verification evidence strength

For each named failure mode, classify the VERIFICATION block's evidence:

- **Strong**: includes a test, probe, or measurement that *would have caught* the failure mode if it had materialized. Examples: an assertion against a poisoned input, a snapshot comparison, a probe that compares the actual canonical fixture value to the seeded value.
- **Medium**: includes a code inspection or trace argument naming specific lines/functions/conditions. "I read `karr_dna_repair.py:140` and confirmed the dict default was removed" qualifies.
- **Weak**: asserts the failure didn't occur without specific evidence. "I verified this" or "checked X" with no probe. Restating the change as evidence it worked.

**Threshold**:
- High-stakes paths (chassis seeds, store ownership, fail-fast read paths, anything touching canonical fixtures): **Strong required**.
- Low-stakes paths (test scaffolding, doc updates): Medium acceptable.
- Weak never passes.

Rationale: the bombshell in TR-R3 was that the codex *did* verbalize what it changed, but its evidence was just restating the change. Without an evidence rubric, the codex can satisfy verification by being articulate.

## Gate 3a — Verification falsified by critique

For each failure mode the codex named in Beat 4 (and claimed in VERIFICATION did not occur), did the external critique find that mode actually occurred?

**Fail signal**: codex went through the motions in Gate 2 without real evidence. The named mode actually materialized.

**Remediation**: tighten Gate 2's evidence rubric for this failure class. The codex didn't lie about which modes it considered; it lied about whether they were ruled out.

## Gate 3b — Failure mode not named

Did the external critique find a failure mode the codex never named in Beat 4?

**Fail signal**: the codex's imagination ceiling didn't reach this failure class. Pre-mortem was incomplete.

**Remediation**: this failure class needs supplementary scaffolding outside the codex's free-form imagination:
- A negative constraint added to the Fix Template ("chassis seeds MUST match canonical snapshot values; if snapshot says zero, seed zero").
- A domain rule appended to the prefix preamble.
- An explicit prompt to consider that class ("consider whether your fix could have introduced a fictional value to satisfy a test").

Note: 3a and 3b have orthogonal remediations. Do not collapse them.

## Aggregate verdict

| 1 | 2 | 3a | 3b | Verdict |
|---|---|---|---|---|
| pass | pass | pass | pass | **v2 validated for this surface class** |
| fail | * | * | * | tighten Gate 1 threshold; consider explicit per-process inversion guidance |
| pass | fail | * | * | rewrite Gate 2 evidence rubric; require probe-class evidence on high-stakes paths |
| pass | pass | fail | * | tighten Gate 2 (same as above; 3a is the symptom Gate 2 should catch) |
| pass | pass | pass | fail | add per-class scaffolding (negative constraints, domain rules) |

## Scoring template

For each run, emit a row:

```
slug | M (modes named) | N concrete | G1 | G2 (strong/med/weak per mode, aggregated) | G3a critical findings on named modes | G3b critical findings on un-named modes | verdict
```

## Empirical-N calibration log

Track each run's (M, N_concrete) and the critique outcome. After ≥6 runs:
- If every Concrete ≥ 2 run is also G3a/G3b clean, `N=2` is calibrated.
- If runs with Concrete = 2 still hit G3b failures, raise `N` or require per-class scaffolding.

## Provenance

This rubric was written 2026-05-28 in response to the observation that the original Gate 3 ("did critique find anything?") collapses two different fault modes with different fixes. Splitting into 3a (verification lies) and 3b (imagination ceiling) is the analog of separating "execution defect" from "design defect" in postmortems.
