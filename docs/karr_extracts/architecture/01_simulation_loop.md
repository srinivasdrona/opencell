# Karr Architecture - Simulation Loop

**Primary sources:**
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/run.m`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`

---

## Verbatim extract - `run.m` header

```
Runs the simulation, and optionally logs results. varargin optionally
contains two input arguments:
- adf
- single instance of SimulationLogger or cell array of a SimulationLogger instances

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 3/24/2011
```

## Verbatim extract - `run.m` execution loop and logger integration

```
%Runs the simulation, and optionally logs results. varargin optionally
%contains two input arguments:
%- adf
%- single instance of SimulationLogger or cell array of a SimulationLogger instances
%
% Author: Jonathan Karr, jkarr@stanford.edu
% Affilitation: Covert Lab, Department of Bioengineering, Stanford University
% Last updated: 3/24/2011
function [this, loggers] = run(this, varargin)

%process options
loggers = {};
ic = struct();
for i = 1:numel(varargin)
    if isa(varargin{i}, 'edu.stanford.covert.cell.sim.util.Logger') || ...
            (iscell(varargin{i}) && isa(varargin{i}{1}, 'edu.stanford.covert.cell.sim.util.Logger'))
        loggers = varargin{i};
        if ~iscell(loggers)
            loggers = {loggers};
        end
    else
        ic = varargin{i};
    end
end

%references
g = this.state('Geometry');
met = this.state('Metabolite');

%allocate memory
this.allocateMemoryForState(1);

%initialize state
this.initializeState();
if ~isempty(ic) && numel(fieldnames(ic)) > 0
    %override default initial conditions
    fields = fieldnames(ic);
    for i = 1:numel(fields)
        s = this.state(regexprep(fields{i}, '^Process_', ''));
        
        subfields = fieldnames(ic.(fields{i}));
        for j = 1:numel(subfields)
            tmp = ic.(fields{i}).(subfields{j});
            if isnumeric(tmp)
                s.(subfields{j})(~isnan(tmp)) = tmp(~isnan(tmp));
            else
                s.(subfields{j}) = tmp;
            end
        end
    end
    
    %synchronize calculated state
    this.state('Time').values = 0;
    this.state('Mass').initialize();
    this.state('Geometry').initialize();
   
    %synchronize processes
    for i = 1:numel(this.processes)
        proc = this.processes{i};
        proc.copyFromState();
    end
end

%apply perturbations
this.applyPerturbations();

%evolve state
for j = 1:numel(loggers)
    loggers{j}.initialize(this);
end

try    
    for i = 1:this.getNumSteps
        [~, requirements, allocations, usages] = this.evolveState();
        met.processRequirements = edu.stanford.covert.util.SparseMat(requirements);
        met.processAllocations = edu.stanford.covert.util.SparseMat(allocations);
        met.processUsages = edu.stanford.covert.util.SparseMat(usages);
        
        for j = 1:numel(loggers)
            loggers{j}.append(this);
        end
        if ~isempty(g) && g.pinched
            break;
        end
    end
catch exception
    for j = 1:numel(loggers)
        loggers{j}.finalize(this);
    end
    exception.rethrow();
end

for j = 1:numel(loggers)
    loggers{j}.finalize(this);
end
```

## Verbatim extract - `evolveState.m` per-tick algorithm

```
function [this, requirements, allocations, usages] = evolveState(this)
% Evolves state of organism:
% 1. Increments time
% 2. Evaluates stimuli
% 3. Evaluates processes
% 4. Applies media conditions
%
% Author: Jonathan Karr, jkarr@stanford.edu
% Author: Jared Jacobs, jmjacobs@stanfod.edu
% Affiliation: Covert Lab, Department of Bioengineering, Stanford University
% Last updated: 9/15/2010

import edu.stanford.covert.cell.sim.constant.Condition;

time = this.state_time;
mets = this.state_metabolite;
stim = this.state_stimulus;

time.values = time.values + this.stepSizeSec;

%% evaluate/apply stimuli
stim.values = Condition.applyConditions(stim.values, stim.setValues, time.values);

%% estimate metabolic requirements of processes
processes = this.processes;
nProcesses = length(processes);
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
if nargout >= 4
    usages = zeros(size(allocations));
end

%% run cell processes (a.k.a. processes):
% - update them with latest state
% - allocate metabolites fairly
% - run the cell processes
% - update simulation with latest state

%determine order of evaluation with constraint that tRNA aminoacylation
%always occurs in same order with respect to translation
while true
    processEvalOrderIndexs = this.randStream.randperm(nProcesses);
    idx1 = find(processEvalOrderIndexs == this.processIndex_tRNAAminoacylation, 1);
    idx2 = find(processEvalOrderIndexs == this.processIndex_translation, 1);
    if isempty(idx1) || isempty(idx2) || idx1 < idx2
        break;
    end
end

%simulate processes
for i = 1:nProcesses
    mod = processes{processEvalOrderIndexs(i)};
    
    allocation = reshape(allocations(mod.substrateMetaboliteGlobalCompartmentIndexs, processEvalOrderIndexs(i)), ...
        size(mod.substrateMetaboliteGlobalCompartmentIndexs));
    counts = mets.counts(mod.substrateMetaboliteGlobalCompartmentIndexs);
    
    mod.simulationStateSideEffects = [];
    mod.copyFromState();
    mod.substrates(mod.substrateMetaboliteLocalIndexs, :) = allocation;
    mod.evolveState();
    mod.copyToState();
    mets.counts(mod.substrateMetaboliteGlobalCompartmentIndexs) = counts + ...
        mod.substrates(mod.substrateMetaboliteLocalIndexs, :) - allocation;
    if nargout >= 4
        usages(mod.substrateMetaboliteGlobalCompartmentIndexs, processEvalOrderIndexs(i)) = ...
            reshape(allocation - mod.substrates(mod.substrateMetaboliteLocalIndexs, :), [], 1);
    end
    if ~isempty(mod.simulationStateSideEffects)
        mod.simulationStateSideEffects.updateSimulationState(this);
    end
end

%% apply media conditions
mets.counts = Condition.applyConditions(mets.counts, mets.setCounts, time.values);

```
