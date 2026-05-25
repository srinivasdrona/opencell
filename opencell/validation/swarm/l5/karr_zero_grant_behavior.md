# Karr zero-grant behavior (MATLAB)

Source basis: `CovertLab/WholeCell` `master` at `6cdee6b355aa0f5ff2953b1ab356eea049108e07` (fetched 2026-05-25).

## Allocator contract in the simulation loop

From `src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`:

```matlab
requirements = max(0, requirements);
tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));
...
allocation = reshape(allocations(mod.substrateMetaboliteGlobalCompartmentIndexs, processEvalOrderIndexs(i)), ...
    size(mod.substrateMetaboliteGlobalCompartmentIndexs));
...
mod.copyFromState();
mod.substrates(mod.substrateMetaboliteLocalIndexs, :) = allocation;
mod.evolveState();
...
mets.counts(mod.substrateMetaboliteGlobalCompartmentIndexs) = counts + ...
    mod.substrates(mod.substrateMetaboliteLocalIndexs, :) - allocation;
```

Citations: `evolveState.m:35-37`, `evolveState.m:63-64`, `evolveState.m:68-73`.

Interpretation: each process is explicitly overwritten with its allocated substrate vector before `evolveState`. There is no allocator-level fallback path that re-injects global `mets.counts` into `mod.substrates` after allocation.

## Zero grant behavior in process code

The examined processes gate reactions directly on `this.substrates` (the allocated vector) and no-op when substrate limits are zero.

Canonical quotes:

```matlab
maxSteps = floor(min(this.substrates([this.substrateIndexs_atp; this.substrateIndexs_water])) / 2);
...
if uwdLen <= 0
    return;
end
```

`Replication.m:637`, `Replication.m:640-643`.

```matlab
numReactions = max(0, floor(min([
    ...
    this.substrates ./ max(0, -this.reactionSmallMoleculeStoichiometryMatrix(:, reactions(1)))])));
if numReactions == 0; continue; end
```

`DNARepair.m:958-963`.

Examples:

- `ChromosomeSegregation.m:201-203` requires `this.substrates(...gtp) >= this.gtpCost` and `...water >= this.gtpCost` before consuming.
- `Replication.m:637-643` computes `maxSteps` from ATP/H2O in `this.substrates`; if no steps are possible it returns.
- `ReplicationInitiation.m:537-543` uses `nActivations = min(this.substrates(ATP), enzymes)` and returns when `nActivations == 0`.
- `DNARepair.m:958-963` bounds `numReactions` by `this.substrates ./ ...`; if `numReactions == 0` it continues without repair.
- `tRNAAminoacylation.m:395-399` builds `species` using `this.substrates`; `tRNAAminoacylation.m:420-423` breaks when no reaction limits remain.

## Conclusion

For zero grant, MATLAB behavior is **strict/gated**: process available substrate is the granted allocation vector, and observed process logic proceeds only if that allocated pool is sufficient. I found no evidence of a MATLAB pattern equivalent to "if allocation is zero then read global pool" for these paths.
