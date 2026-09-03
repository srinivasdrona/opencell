repo_root = fileparts(fileparts(mfilename('fullpath')));

sim = karr_bootstrap();
sim.applyOptions('seed', uint32(0), 'verbosity', 0);
sim.state('MetabolicReaction').initialGrowthFilterWidth = Inf;

target_name = 'ChromosomeCondensation';
target_wid = ['Process_' target_name];
target_idx = [];
for i = 1:numel(sim.processesInInitOrder)
    proc = sim.processesInInitOrder{i};
    if strcmp(proc.wholeCellModelID, target_wid)
        target_idx = i;
        break;
    end
end
assert(~isempty(target_idx), 'ChromosomeCondensation init-order slot not found');

prior_processes = sim.processesInInitOrder(1:target_idx-1);
prior_idxs = zeros(numel(prior_processes), 1, 'int8');
for i = 1:numel(prior_processes)
    prior_idxs(i) = int8(sim.processIndex(prior_processes{i}.wholeCellModelID));
end
sim.setForTest('processesInInitOrder', prior_processes);
sim.setForTest('processInitOrderIndexs', prior_idxs);
sim.initializeState();

target = sim.process(target_name);
target.simulationStateSideEffects = [];
target.copyFromState();

fprintf('pre randStream.state=%d\n', double(target.randStream.state));
fprintf('pre enzymes=%s\n', mat2str(double(target.enzymes(:)')));
fprintf('pre boundEnzymes=%s\n', mat2str(double(target.boundEnzymes(:)')));

target.initializeState();

smc_adp_global = target.enzymeGlobalIndexs(target.enzymeIndexs_SMC_ADP);
[smc_pos, ~] = find(target.chromosome.complexBoundSites == smc_adp_global);
[all_pos, all_vals] = find(target.chromosome.complexBoundSites);
uniq_vals = unique(all_vals);
fprintf('post randStream.state=%d\n', double(target.randStream.state));
fprintf('post enzymes=%s\n', mat2str(double(target.enzymes(:)')));
fprintf('post boundEnzymes=%s\n', mat2str(double(target.boundEnzymes(:)')));
fprintf('post smc_bound_count=%d\n', size(smc_pos, 1));
for i = 1:numel(uniq_vals)
    fprintf('post complex value %d count=%d\n', double(uniq_vals(i)), nnz(all_vals == uniq_vals(i)));
end
