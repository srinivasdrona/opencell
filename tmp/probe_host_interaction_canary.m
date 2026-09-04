% probe_host_interaction_canary.m
%
% Smallest empirical canary (per task mandate: "run the smallest empirical
% canary; only then launch additional disjoint seeds") to determine whether
% host.isBacteriumAdherent is reachable as a false->true TRANSITION in a
% genuine full-Simulation seed-0 run, or whether it is already TRUE from
% the first tick (in which case a transition-anchor search can never
% succeed and is the wrong extraction strategy -- not a "never fires" bug).
%
% Loads the SAME genuine fitted Simulation (karr_bootstrap) and the SAME
% allocator-correct scheduler loop as extract_per_process_traces_v2.m's
% evolve_state_with_tap (copied verbatim below as my_evolve_state_with_tap,
% since that function is private to that file), seeds with seed=0, and
% prints host.isBacteriumAdherent / isTLRActivated / isNFkBActivated /
% isInflammatoryResponseActivated plus the raw enzyme copy numbers for the
% terminalOrganelle/adhesin/tlr-ligand/antigen index sets at ticks
% 0 (pre-evolve), 1, 2, 5, 10, 20, 50, 100.
repo_root = fileparts(fileparts(mfilename('fullpath')));
cd(repo_root);
addpath(fullfile(repo_root, 'scripts', 'matlab'));

[sim, ~, ~] = karr_bootstrap();

target_idx = [];
for i = 1:numel(sim.processes)
    proc_i = sim.processes{i};
    wid = proc_i.wholeCellModelID;
    if strcmp(wid, 'Process_HostInteraction')
        target_idx = i;
        break;
    end
end
if isempty(target_idx)
    error('HostInteraction process not found in sim.processes');
end
fprintf('target_idx=%d\n', target_idx);

if isobject(sim) && ismethod(sim, 'applyOptions') && ismethod(sim, 'seedRandStream')
    sim.applyOptions('seed', uint32(0));
    sim.seedRandStream();
end

proc = sim.processes{target_idx};
h = proc.host;

report_ticks = [1, 2, 5, 10, 20, 50, 100];
fprintf('--- tick 0 (pre-evolve, post-initializeState) ---\n');
print_host_state(h, proc);

next_report_i = 1;
for t = 1:max(report_ticks)
    sim = my_evolve_state_with_tap(sim, target_idx);
    proc = sim.processes{target_idx};
    h = proc.host;
    if next_report_i <= numel(report_ticks) && t == report_ticks(next_report_i)
        fprintf('--- tick %d ---\n', t);
        print_host_state(h, proc);
        next_report_i = next_report_i + 1;
    end
end

function print_host_state(h, proc)
fprintf('  isBacteriumAdherent = %d\n', h.isBacteriumAdherent);
fprintf('  isTLRActivated = [%s]\n', num2str(h.isTLRActivated(:)'));
fprintf('  isNFkBActivated = %d\n', h.isNFkBActivated);
fprintf('  isInflammatoryResponseActivated = %d\n', h.isInflammatoryResponseActivated);
terminal_idx = proc.enzymeIndexs_terminalOrganelle;
adhesin_idx = proc.enzymeIndexs_adhesin;
fprintf('  enzymes(terminalOrganelle) = [%s]\n', num2str(proc.enzymes(terminal_idx)'));
fprintf('  enzymes(adhesin) = [%s]\n', num2str(proc.enzymes(adhesin_idx)'));
fprintf('  enzymes(tlr12Ligand) = [%s]\n', num2str(proc.enzymes(proc.enzymeIndexs_tlr12Ligand)'));
fprintf('  enzymes(tlr26Ligand) = [%s]\n', num2str(proc.enzymes(proc.enzymeIndexs_tlr26Ligand)'));
fprintf('  enzymes(antigen) = [%s]\n', num2str(proc.enzymes(proc.enzymeIndexs_antigen)'));
end

function sim = my_evolve_state_with_tap(sim, target_idx)
% Verbatim copy of extract_per_process_traces_v2.m's evolve_state_with_tap
% scheduler body (the allocator-correct one-tick loop), trimmed of the
% snapshot-tap bookkeeping this probe does not need -- the scheduler
% mechanics (allocation, process order, evolveState calls) are byte-for-
% byte identical, never a simplified/alternate scheduler.
time = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;

time.values = time.values + sim.stepSizeSec;
stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    stim.values, stim.setValues, time.values);

processes = sim.processes;
nProcesses = numel(processes);
rna_decay_idx = sim.processIndex('RNADecay');
requirements = zeros([numel(mets.counts) nProcesses]);
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

rand_stream = [];
if isobject(sim) && ismethod(sim, 'getForTest')
    try
        rand_stream = sim.getForTest('randStream');
    catch
    end
end

while true
    if isempty(rand_stream)
        processEvalOrderIndexs = randperm(nProcesses);
    else
        processEvalOrderIndexs = rand_stream.randperm(nProcesses);
    end
    idx1 = find(processEvalOrderIndexs == sim.processIndex_tRNAAminoacylation, 1);
    idx2 = find(processEvalOrderIndexs == sim.processIndex_translation, 1);
    if isempty(idx1) || isempty(idx2) || idx1 < idx2
        break;
    end
end

for i = 1:nProcesses
    proc_idx = processEvalOrderIndexs(i);
    mod = processes{proc_idx};

    gidx = mod.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = mod.substrateMetaboliteLocalIndexs;
    allocation = reshape(allocations(gidx, proc_idx), size(gidx));
    counts = mets.counts(gidx);

    mod.simulationStateSideEffects = [];
    mod.copyFromState();
    mod.substrates(lidx, :) = allocation;
    if proc_idx == rna_decay_idx && isprop(mod, 'RNAs')
        mod.RNAs = max(0, mod.RNAs);
    end

    mod.evolveState();

    mod.copyToState();
    mets.counts(gidx) = counts + mod.substrates(lidx, :) - allocation;

    if ~isempty(mod.simulationStateSideEffects)
        mod.simulationStateSideEffects.updateSimulationState(sim);
    end
end

mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    mets.counts, mets.setCounts, time.values);
end
