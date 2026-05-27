# Fix Template — Dimer/Complex Port Wiring (v6 Karr Processes)

**Status:** domain-specific rules for the dimer-port bug class. Append to the Deliberate Action prefix ONLY when running an Arm-B fix codex. Distilled from TR rounds 1, 2, and 3 plus the dimer-port audit.

**Bug class:** a v6 Karr process declares complex/dimer enzymes (or regulators) but reads them only from `protein.counts`. The v6 chassis seeds those WIDs into `complex.counts`. Result: silent darkness — process runs, math evaluates, the value is zero or one, no error, no test failure.

## Rule 1 — The three-link chain

For every WID a process declares as an input, the chain `chassis seed → port wiring → process read → math` must be verifiable from chassis-built state with no manual injection. Three links, all three must be observable:

1. **Seed:** `build_karr_chassis_v6()["state"][<store>]["counts"][<wid>]` exists and is non-zero (or zero by design — but stated as such).
2. **Port:** the process's `ports_schema()` declares the right store for the right WID class. Monomer WIDs → `protein.counts`. Complex/dimer/tetramer/oligomer WIDs → `complex.counts`. Do not register a WID in a store the chassis does not seed it into; do not pollute irrelevant stores with zero defaults for every WID.
3. **Read:** `next_update` reads from the same store the WID lives in. If a process needs both monomers and complexes, split the lookup by WID class — do not collapse to one store as a "simplification."

## Rule 2 — Tests cannot write to chassis-seeded stores

Integration tests for the process MUST NOT directly write to `protein.counts`, `complex.counts`, `rna.counts`, `metabolite.counts`. If a non-zero value is required:

- Either fix the chassis seed so the value is present in `build_karr_chassis_v6()["state"][...]`,
- Or assert against the chassis-built initial state that the value is non-zero BEFORE invoking `next_update`. If the assertion fails, the chassis seed is wrong — fix that first.

A test that hand-populates the data the chassis is supposed to populate is a tautology, not a check. It will silently pass even when the chassis is broken.

## Rule 3 — Fail fast on missing inputs

If the process declares a WID and the chassis does not seed it (and you cannot fix the seed), raise loudly at construction or first read. Do not default to zero. Do not skip silently. The dimer-port bug class is exactly what "default to zero on missing" creates — silent darkness across a class of 10+ processes.

Specifically:
- A process construction that silently treats an unknown WID as a no-op is wrong.
- A `dict.get(wid, 0)` pattern over a WID list the process owns is wrong unless the zero is intentional and documented.

## Rule 4 — How to classify a WID

Use the canonical fixtures. Do not pattern-match on names (most dimer WIDs end in `_DIMER` but not all complex enzymes do — `RNA_POLYMERASE` and `RIBOSOME_70S` are complex but don't have the suffix).

- The D2 (`KarrComplexationProcess` / fixture loader) complex WID set is the authoritative source.
- The ribosome assembly process maintains its own complex WID set.
- For TR-like cases, the union of those two plus a small fixed set (`RNA_POLYMERASE`, `RIBOSOME_70S`) is the candidate set; a process should only register the subset that its own enzyme/regulator list intersects.

## Rule 5 — Acceptance criteria for "fixed"

Before declaring L1-green:

1. The process's integration test passes a chassis-seed gate: it `assert`s a non-zero value at `build_karr_chassis_v6()["state"]["complex"]["counts"][<wid>]` for at least one named complex WID this process depends on, BEFORE invoking the engine.
2. That same complex WID, present in the chassis-built state, changes a named, measurable output of the process (`tx_rate_fold_change`, reaction flux, gate progression — whichever applies).
3. `pytest -x tests/vivarium/test_<process>.py -q` and `pytest -x tests/integration/test_karr_chassis_v6.py -q` both pass.
4. STATUS file's `## Verification` section names the WID, the chassis-state value, the engine-output value, and the test that proves it.

If any of the four fails, you are not done. Do not declare green.

## Rule 6 — Sibling-builder safety (probe-rigor for Karr topology)

The Karr chassis has multiple builder variants (`build_karr_chassis_v3`, `_v4`, `_v5`, `_v6`) that each instantiate a different overlapping subset of Karr processes. If your fix modifies a process's port schema or read path, EVERY builder that instantiates that process must still construct successfully — not just the one whose tests you ran.

**Procedure:**

1. Before declaring done, enumerate every `build_karr_chassis_v*` function that instantiates the process you changed. Use `grep -n "Karr<Process>Process" opencell/vivarium/karr_composite.py` and read each occurrence in context to confirm.
2. For each one, run a construction smoke test: `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_vN; build_karr_chassis_vN()"` (or the equivalent fixture-loading test). Capture command and exit status.
3. List the result for each builder, by name, in your VERIFICATION block.

**Gate 2 evidence rule for this failure class:**

A VERIFICATION block that names sibling-builder breakage as a Beat 4 failure mode but cites only `v6`'s success is **Weak evidence and fails Gate 2**. Strong evidence requires the construction result for every builder variant the changed process appears in, listed by name with command and exit status. "I ran the integration test suite" is not sufficient unless that suite explicitly exercises every builder.

Rationale: empirical evidence from dna-repair and protein-modification — both wired v5/v6 correctly, both broke v4 silently because the chassis-v6 integration test does not construct v4. Beat 4 inversion declared the failure mode; verification did not probe it. Rule 6 closes that gap.

## What this template does NOT cover

This template is scoped to the dimer-port bug class. It does not handle:
- Allocator-grant integration (separate L3 concern).
- Strict-zero contracts (L5).
- Replay fidelity (L2 — requires per-process MATLAB ground truth).
- Numerical stability for very wide WID sets.

If your process has those issues, surface them in STATUS as out-of-scope follow-ups; do not silently address them.
