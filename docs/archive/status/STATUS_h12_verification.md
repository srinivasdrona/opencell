# STATUS h12 verification

## Beat 1
I confirm (a) **YES**: tick-0 `randperm`, `requirements`, and `allocations` are seed-reproducible across separate extractor invocations with `seed=0` for DNASupercoiling vs ChromosomeCondensation, and deny (b) **NO**: the prior sub-agent's intra-tick contamination channel list is **not exhaustive**.

## Beat 2
### Prior sub-agent verdict (verbatim quote)
> **Verdict: PARTIAL CONFIRMATION — but the hypothesis has the wrong mechanism for substrate values. The structural claim (intra-tick position affects what a process sees) is real, but the specific channel through which it affects `states_before["ATP"]` is not depletion of the live pool. It is proportional allocation. A different property category (enzymes / RNA / proteins) is the true intra-tick signal, and the fix path needs adjustment.**

### Verbatim code citations

`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m:27-37,51,68-73`
```matlab
requirements = zeros([numel(mets.counts) nProcesses]);
for i = 1:nProcesses
    mod = processes{i};
    mod.copyFromState();
    r = mod.calcResourceRequirements_Current();
    requirements(mod.substrateMetaboliteGlobalCompartmentIndexs, i) = ...
        reshape(r(mod.substrateMetaboliteLocalIndexs, :), [], 1);
end
requirements = max(0, requirements);
tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));
...
processEvalOrderIndexs = this.randStream.randperm(nProcesses);
...
mod.copyFromState();
mod.substrates(mod.substrateMetaboliteLocalIndexs, :) = allocation;
...
mets.counts(mod.substrateMetaboliteGlobalCompartmentIndexs) = counts + ...
    mod.substrates(mod.substrateMetaboliteLocalIndexs, :) - allocation;
```

`scripts/matlab/extract_per_process_traces_v2.m:51-52,64-66,75,149-163,172-177,195-204,206-213,295-300`
```matlab
sim = karr_bootstrap();
[target_idx, canonical_name] = find_process_index(sim, requested_name);
...
proc = sim.processes{target_idx};
snapshot_props = pick_snapshot_properties(proc);
...
seed_simulation(sim, seed);
...
for i = 1:nProcesses
    mod = processes{i};
    mod.copyFromState();
    r = mod.calcResourceRequirements_Current();
    gidx = mod.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = mod.substrateMetaboliteLocalIndexs;
    if ~isempty(gidx) && ~isempty(lidx)
        requirements(gidx, i) = reshape(r(lidx, :), [], 1);
    end
end

requirements = max(0, requirements);
tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));
...
while true
    if isempty(rand_stream)
        processEvalOrderIndexs = randperm(nProcesses);
    else
        processEvalOrderIndexs = rand_stream.randperm(nProcesses);
    end
...
mod.copyFromState();
mod.substrates(lidx, :) = allocation;
...
if proc_idx == target_idx
    before_tick = snapshot_from_process(mod, snapshot_props);
end
...
mod.copyToState();
mets.counts(gidx) = counts + mod.substrates(lidx, :) - allocation;
...
if isobject(sim) && ismethod(sim, 'applyOptions') && ismethod(sim, 'seedRandStream')
    sim.applyOptions('seed', seed);
    sim.seedRandStream();
    return;
end
```

`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m:476-483,548-576,611-646,720-750,806-825`
```matlab
function copyFromState(this)
    this.stimuli = this.copyStimuliFromState(...
        this.stimulus.values, this.metabolite.counts, this.rna.counts, this.monomer.counts, this.complex.counts);
    this.substrates = this.copySubstratesFromState(...
        this.stimulus.values, this.metabolite.counts, this.rna.counts, this.monomer.counts, this.complex.counts);
    [this.enzymes, this.boundEnzymes] = this.copyEnzymesFromState(...
        this.stimulus.values, this.metabolite.counts, this.rna.counts, this.monomer.counts, this.complex.counts);
end
...
if ~isempty(this.substrateStimulusGlobalCompartmentIndexs)
    substrates(this.substrateStimulusLocalIndexs, :) = ...
        stimulusValues(this.substrateStimulusGlobalCompartmentIndexs);
end
if ~isempty(this.substrateMetaboliteGlobalCompartmentIndexs)
    substrates(this.substrateMetaboliteLocalIndexs, :) = ...
        metaboliteCounts(this.substrateMetaboliteGlobalCompartmentIndexs);
end
if ~isempty(this.substrateRNAGlobalCompartmentIndexs)
    substrates(this.substrateRNALocalIndexs, :) = ...
        rnaCounts(this.substrateRNAGlobalCompartmentIndexs);
end
if ~isempty(this.substrateMonomerGlobalCompartmentIndexs)
    substrates(this.substrateMonomerLocalIndexs, :) = ...
        monomerCounts(this.substrateMonomerGlobalCompartmentIndexs);
end
if ~isempty(this.substrateComplexGlobalCompartmentIndexs)
    substrates(this.substrateComplexLocalIndexs, :) = ...
        complexCounts(this.substrateComplexGlobalCompartmentIndexs);
end
...
if ~isempty(this.enzymeRNAGlobalCompartmentIndexs)
    enzymes(this.enzymeRNALocalIndexs, :) = ...
        rnaCounts(this.enzymeRNAGlobalCompartmentIndexs);
    boundEnzymes(this.enzymeRNALocalIndexs, :) = ...
        rnaCounts(this.enzymeBoundRNAGlobalCompartmentIndexs);
end
if ~isempty(this.enzymeMonomerGlobalCompartmentIndexs)
    enzymes(this.enzymeMonomerLocalIndexs, :) = ...
        monomerCounts(this.enzymeMonomerGlobalCompartmentIndexs);
    boundEnzymes(this.enzymeMonomerLocalIndexs, :) = ...
        monomerCounts(this.enzymeBoundMonomerGlobalCompartmentIndexs);
end
if ~isempty(this.enzymeComplexGlobalCompartmentIndexs)
    enzymes(this.enzymeComplexLocalIndexs, :) = ...
        complexCounts(this.enzymeComplexGlobalCompartmentIndexs);
    boundEnzymes(this.enzymeComplexLocalIndexs, :) = ...
        complexCounts(this.enzymeBoundComplexGlobalCompartmentIndexs);
end
...
if ~isempty(this.enzymeStimulusGlobalCompartmentIndexs)
    this.stimulus.values(this.enzymeStimulusGlobalCompartmentIndexs) = ...
        this.enzymes(this.enzymeStimulusLocalIndexs, :);
end
if ~isempty(this.enzymeMetaboliteGlobalCompartmentIndexs)
    this.metabolite.counts(this.enzymeMetaboliteGlobalCompartmentIndexs) = ...
        this.enzymes(this.enzymeMetaboliteLocalIndexs, :);
end
if ~isempty(this.enzymeRNAGlobalCompartmentIndexs)
    this.rna.counts(this.enzymeRNAGlobalCompartmentIndexs) = ...
        this.enzymes(this.enzymeRNALocalIndexs, :);
    this.rna.counts(this.enzymeBoundRNAGlobalCompartmentIndexs) = ...
        this.boundEnzymes(this.enzymeRNALocalIndexs, :);
end
...
if ~isempty(this.substrateStimulusGlobalCompartmentIndexs)
    this.stimulus.values(this.substrateStimulusGlobalCompartmentIndexs) = ...
        this.substrates(this.substrateStimulusLocalIndexs, :);
end
if ~isempty(this.substrateMetaboliteGlobalCompartmentIndexs)
    this.metabolite.counts(this.substrateMetaboliteGlobalCompartmentIndexs) = ...
        this.substrates(this.substrateMetaboliteLocalIndexs, :);
end
if ~isempty(this.substrateRNAGlobalCompartmentIndexs)
    this.rna.counts(this.substrateRNAGlobalCompartmentIndexs) = ...
        this.substrates(this.substrateRNALocalIndexs, :);
end
if ~isempty(this.substrateMonomerGlobalCompartmentIndexs)
    this.monomer.counts(this.substrateMonomerGlobalCompartmentIndexs) = ...
        this.substrates(this.substrateMonomerLocalIndexs, :);
end
if ~isempty(this.substrateComplexGlobalCompartmentIndexs)
    this.complex.counts(this.substrateComplexGlobalCompartmentIndexs) = ...
        this.substrates(this.substrateComplexLocalIndexs, :);
end
```

## Beat 3
- Read RNG/bootstrap/seed path in order: `karr_bootstrap.m` -> `seed_simulation` in extractor -> `Simulation.seedRandStream`.
- Read tick loop in extractor (`evolve_state_with_tap`) to place `requirements`, `allocations`, `randperm`, and any `target_idx`-dependent branches on one timeline.
- Read `Simulation/evolveState.m` for canonical Karr ordering and allocator overwrite semantics.
- Read `Process.m` `copyFromState` + `copyToState` helpers and derive complete shared-state read/write surface `(a ∩ b)`.
- Check `DNASupercoiling.m` for direct shared-object reads/writes not represented by the prior three channels.

## Beat 4 (Pre-mortem / inversion)
1. I could miss hidden RNG between bootstrap and tick-0 `randperm`.  
   Confirm/deny section: `extract_per_process_traces_v2.m:51,75,149-177` and `Simulation.m:430-459` (explicit reseed + first visible `randperm` in tap loop).
2. I could miss a fourth contamination channel outside substrate/enzyme/boundEnzyme mappings.  
   Confirm/deny section: `Process.m:476-483,720-859` (full copy surface) plus `DNASupercoiling.m:360-507` (direct chromosome reads and `c.linkingNumbers` write).
3. I could conflate “same seed” with “same RNG draw sequence.”  
   Confirm/deny section: `extract_per_process_traces_v2.m:64-66,149-163,172-183,202-210` (target-specific logic happens after requirement/allocation/order computations).

## Beat 5 (Verification protocol)
1. For Q1(a/b/c), assign explicit verdicts from control-flow and seed-reset code only: `YES` if same seeded state + same pre-target call sequence; `NEEDS_RUNTIME_PROBE` only if target-dependent branch exists before the measured artifact.
2. For Q2, build explicit `(a ∩ b)` table from `Process.copyFromState` reads and `Process.copyToState` writes, then compare against prior 3 named channels.
3. Emit per-question verdict labels from `{YES, NO, PARTIAL, NEEDS_MORE_EVIDENCE}` with line-cited snippets.

## Question 1 (seed reproducibility)

### Q1(a): tick-0 `randperm(nProcesses)` identical across two runs?
**Verdict: YES.**

Evidence:
- Each extractor invocation creates a fresh simulation, then reseeds it before ticking:
  - `sim = karr_bootstrap();` and then `seed_simulation(sim, seed);` (`extract_per_process_traces_v2.m:51,75`).
  - `seed_simulation` calls `sim.applyOptions('seed', seed); sim.seedRandStream();` (`extract_per_process_traces_v2.m:297-300`).
- `Simulation.seedRandStream` deterministically resets the simulation stream and all process/state streams from `this.seed`:
  - `this.randStream.reset(this.seed)` and loops setting each state/process `o.seed = this.seed; o.seedRandStream();` (`Simulation.m:445,448-458`).
- Tick order in the tap loop is drawn from that simulation stream:
  - `rand_stream = sim.getForTest('randStream'); ... processEvalOrderIndexs = rand_stream.randperm(nProcesses);` (`extract_per_process_traces_v2.m:167,176`; `Simulation.m:709-710`).

### Q1(b): tick-0 `requirements` vector identical across two runs?
**Verdict: YES.**

Evidence:
- `requirements` is computed before any `target_idx`-dependent branch:
  - `for i = 1:nProcesses ... mod.copyFromState(); r = mod.calcResourceRequirements_Current(); ... requirements(gidx, i) = ...` (`extract_per_process_traces_v2.m:149-157`).
  - `target_idx` is only used later in `if proc_idx == target_idx` snapshot gates (`extract_per_process_traces_v2.m:202-204,208-210`).
- Both invocations run the same full requirements loop over all processes in index order (`1:nProcesses`) with the same seeded starting state (`extract_per_process_traces_v2.m:75,149-157`; `Simulation.m:445-458`).

### Q1(c): tick-0 `allocations` matrix identical across two runs?
**Verdict: YES.**

Evidence:
- `allocations` is a pure function of `requirements` and `mets.counts` in the same tap location:
  - `tmp = mets.counts(:) ./ max(1, sum(requirements, 2));`
  - `allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));`
  (`extract_per_process_traces_v2.m:161-163`; same formula in canonical `Simulation/evolveState.m:36-37`).
- This computation is completed before any `target_idx`-conditioned logic (`extract_per_process_traces_v2.m:161-163` vs `202-210`).

### Requested checks
- `karr_bootstrap()` RNG use: no RNG calls are present in the function body; it only resolves paths and loads `Simulation_fitted.mat` (`karr_bootstrap.m:16-50`).
- Extractor tap-point/sanitizer RNG use: in `extract_per_process_traces_v2.m`, `rand` usage appears only in order selection (`randperm`/`rand_stream.randperm`) and not in snapshot/sanitize code (`extract_per_process_traces_v2.m:164,167,173-177,224-229,239-293`).
- Per-tick init RNG use: before order draw, tap loop performs deterministic time/stimulus + requirement/allocation arithmetic (`extract_per_process_traces_v2.m:141-163`).
- Target-dependent RNG divergence before (a/b/c): none found; `target_idx` appears only in snapshot gates after order/requirements/allocations (`extract_per_process_traces_v2.m:202-210`).

## Question 2 (exhaustiveness of contamination channels)
**Verdict: NO (not exhaustive).**

### Complete contamination-surface table from `Process.copyFromState`/`copyToState` (a ∩ b)

| PROPERTY_NAME | READ_BY_method:line | WRITTEN_BY_method:line | Prior sub-agent coverage |
|---|---|---|---|
| `stimulus.values` | `copyFromState` args + `copySubstratesFromState` / `copyEnzymesFromState` reads (`Process.m:476-483,557-560,621-624`) | `copyToState` enzyme + substrate writes (`Process.m:725-728,806-809`) | **newly identified** |
| `metabolite.counts` | `copyFromState` args + substrate/enzyme reads (`Process.m:476-483,561-564,625-628`) | `copyToState` enzyme + substrate writes (`Process.m:729-732,810-813`) | named by prior (allocator/metabolite substrate context) |
| `rna.counts` | `copyFromState` args + substrate/enzyme/bound enzyme reads (`Process.m:476-483,565-568,629-634`) | `copyToState` enzyme/bound + substrate writes (`Process.m:733-738,814-817`) | named by prior (RNA/non-metabolite + enzymes/boundEnzymes) |
| `monomer.counts` | `copyFromState` args + substrate/enzyme/bound enzyme reads (`Process.m:476-483,569-572,635-640`) | `copyToState` enzyme/bound + substrate writes (`Process.m:739-744,818-821`) | named by prior (monomer/non-metabolite + enzymes/boundEnzymes) |
| `complex.counts` | `copyFromState` args + substrate/enzyme/bound enzyme reads (`Process.m:476-483,573-576,641-646`) | `copyToState` enzyme/bound + substrate writes (`Process.m:745-750,822-825`) | named by prior (complex/non-metabolite + enzymes/boundEnzymes) |

Property-level deltas from this table:
- `(a ∩ b)` = `{stimulus.values, metabolite.counts, rna.counts, monomer.counts, complex.counts}`.
- `(b - a)` = none at property-object level in base `Process.copyFromState`/`copyToState`.
- `(a - b)` = none at property-object level in base `Process.copyFromState`/`copyToState`.

### DNASupercoiling-specific shared-state reads/writes

`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNASupercoiling.m` does **not** define `copyFromState`/`copyToState` overrides (no such method definitions in file), but directly reads/writes shared objects during `evolveState`:

- Reads chromosome properties including:
  - `c.doubleStrandedRegions`, `c.linkingNumbers`, `c.relaxedBasesPerTurn` (`DNASupercoiling.m:366,371,373`)
  - `c.sequenceLen` (`DNASupercoiling.m:397,405,505`)
  - `c.monomerBoundSites`, `c.complexBoundSites`, `c.damagedSites` (`DNASupercoiling.m:398-399,403,406-407,412,416,427-429`)
  - `c.monomerDNAFootprints`, `c.complexDNAFootprints` (`DNASupercoiling.m:401-402,410-411,414-415,452-453`)
  - `c.equilibriumSuperhelicalDensity`, `c.transcriptionUnitStartCoordinates` (`DNASupercoiling.m:523-524,554,572`)
- Writes chromosome property:
  - `c.linkingNumbers = CircularSparseMat(...)` (`DNASupercoiling.m:503-505`)
- Writes another shared state object:
  - `this.rnaPolymerase.supercoilingBindingProbFoldChange = ...` (`DNASupercoiling.m:507`)

Therefore, chromosome-object mutation/consumption is an additional intra-tick contamination channel beyond the prior three named channels.

## Verdict summary
**Prior sub-agent verdict: PARTIAL.**  
The seed-reproducibility claim for tick-0 order/requirements/allocations is confirmed by code (`seed_simulation` -> `Simulation.seedRandStream` -> tap-loop ordering/allocation timeline), and the allocator-overwrite mechanism is consistent with canonical `Simulation.evolveState`. However, the contamination-channel enumeration is not exhaustive: `Process.copyFromState`/`copyToState` includes `stimulus.values` in the read/write surface, and DNASupercoiling directly reads/writes shared chromosome (notably `c.linkingNumbers`) plus writes RNAPolymerase fold-change state.

## Implications for the fix path
Because exhaustiveness fails, any fix that targets only {allocator-metabolite substrate, enzymes, boundEnzymes, RNA/monomer/complex substrate mappings} is incomplete; it must also account for at least:
- `stimulus.values` as a shared read/write channel in base `Process.copyFromState`/`copyToState`.
- Chromosome-shared-object mutations/reads in DNASupercoiling (e.g., `c.linkingNumbers` write and chromosome occupancy/supercoiling reads).
- DNASupercoiling side-write to `rnaPolymerase.supercoilingBindingProbFoldChange`.
