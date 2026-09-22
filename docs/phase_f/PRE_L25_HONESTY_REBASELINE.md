# Pre-L2.5 Honesty Rebaseline

**Status:** ACTIVE BLOCKER BASELINE
**Audit base:** `6a038b1d084543ddd847528ff6e698a9dba37626`
**Machine authority:** `pre_l25/PRE_L25_HONESTY_BASELINE.yaml`

## Outcome

The lower-gate recheck now reads:

- L1b method completeness: 115/115.
- L1b wiring conformance: 28/28.
- L2.2 distributional evidence: 22 PASS / 2 MISSING_EVIDENCE / 24 required.
- L2.4 short-horizon chassis conservation: PASS.

Those results do not establish the separate no-known-gap prerequisite for
L2.5. L1b accepts a wiring row that truthfully documents an implementation
deviation, L2.2 may use a process-specific validation configuration, and L2.4
checks conservation rather than Karr trajectory equivalence.

The two missing rows are ChromosomeCondensation and
TranscriptionalRegulation, both previously misclassified as deterministic
despite stochastic chromosome-binding code. The fail-closed rebaseline is:

- **Eligible:** 2/28.
- **Blocked by a missing lower gate:** 2/28.
- **Blocked by current code deviation:** 24/28.

This is a stochasticity-classification correction, not a new implementation
regression. The old 22/22 board excluded two processes that require L2.2.

The fresh L2.4 run also emitted an incompatible-updater warning for
`enzymes.MG_203_204_TETRAMER` and
`boundEnzymes.MG_203_204_TETRAMER`: DNASupercoiling declares `set` while
ChromosomeSegregation declares `accumulate`. Conservation still passes, but
the store semantics are order-sensitive and remain a DNASupercoiling blocker.

## Metabolism

Metabolism is blocked on two independent surfaces:

1. The semantic audit records unresolved request/allocation, process-order,
   LP-bound input, and compartment-projection differences.
2. Its L2.2 authority configuration is not the production v6 configuration.
   L2.2 constructs Metabolism with dynamic bounds, Karr substrate writeback,
   and GLPK. The v6 chassis enables allocator budgeting but retains the
   process defaults for solver and Karr writeback.

The existing Metabolism L2.2 PASS remains valid for its registered MF4/FVA
contract: 50 seeds x 20 ticks, substrate W1 `158.5044632478627` under threshold
`223.1527235897428`, and FVA feasibility
`1754886 / 1755000 = 0.9999350427350427` under a `0.99` threshold. It does not
authorize the different production configuration.

## Mechanical contract

Run:

```powershell
bin\oc-py.cmd scripts/pre_l25_honesty.py audit
```

The command returns zero when the baseline is internally valid, even while
blockers remain. Use `--require-all-eligible` for the eventual L2.5 entry gate;
it returns nonzero until all 28 processes are eligible.

The validator:

- requires exactly the 28 canonical process names;
- cross-checks every L2.2 process against the tracked mechanical evidence row;
- derives eligibility from finding disposition rather than trusting an
  `eligible` boolean;
- verifies every evidence path and inclusive line range;
- hash-locks the current process catalog, L2.2 evidence index, wiring rows,
  semantic audits, per-process schemas, and mapped OC implementation files;
- invalidates the entire baseline if any dependency changes.

`scripts/derive_l25_scope.py` consumes the validated baseline. A lower-gate
PASS process with any open honesty finding cannot enter a selectable L2.5
pair.

## Closure order

1. Close the remaining deterministic repairs: ProteinActivation and
   TerminalOrganelleAssembly.
2. Close Metabolism's validation-versus-production configuration split and
   allocator-derived LP-bound path.
3. Group the remaining 23 code-deviation blockers by shared root cause:
   request/allocation timing, compartment projection, stoichiometry, and
   reduced biology.
4. Refresh the hash-locked baseline after each verified closure.
5. Start pair execution only when both members are explicitly eligible.
