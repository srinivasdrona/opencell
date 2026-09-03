repo_root = fileparts(fileparts(mfilename('fullpath')));
scripts_dir = fullfile(repo_root, 'scripts', 'matlab');
addpath(scripts_dir);

sim = karr_bootstrap();
sim.applyOptions('seed', uint32(0), 'verbosity', 0);
wholecell_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
if ~exist(wholecell_root, 'dir')
    wholecell_root = 'E:\opencell\data\m1_sources\WholeCell';
end
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
assert(target_idx > 1, 'ChromosomeCondensation unexpectedly first in init order');

prior_processes = sim.processesInInitOrder(1:target_idx-1);
prior_ids = cellfun(@(p) p.wholeCellModelID, prior_processes, 'UniformOutput', false);
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

chrom = serialize_chromosome_state(target.chromosome);

artifact = struct();
artifact.metadata = struct( ...
    'repo_root', repo_root, ...
    'target_process', target_name, ...
    'target_wholeCellModelID', target.wholeCellModelID, ...
    'seed', double(sim.seed), ...
    'process_init_order_prefix', {prior_ids}, ...
    'target_init_order_slot_1based', double(target_idx), ...
    'wcm_root', wholecell_root, ...
    'source_fixture_path', fullfile(wholecell_root, 'src_test', '+edu', '+stanford', '+covert', '+cell', '+sim', '+process', 'fixtures', 'ChromosomeCondensation.mat'), ...
    'chromosome_serializer', fullfile(scripts_dir, 'serialize_chromosome_state.m'));
artifact.process = struct( ...
    'substrates', double(target.substrates), ...
    'enzymes', double(target.enzymes), ...
    'boundEnzymes', double(target.boundEnzymes), ...
    'substrateWholeCellModelIDs', {target.substrateWholeCellModelIDs}, ...
    'enzymeWholeCellModelIDs', {target.enzymeWholeCellModelIDs}, ...
    'substrateGlobalIndexs', double(target.substrateGlobalIndexs), ...
    'enzymeGlobalIndexs', double(target.enzymeGlobalIndexs), ...
    'enzymeDNAFootprints', double(target.enzymeDNAFootprints), ...
    'smcSepNt', double(target.smcSepNt), ...
    'smcSepProbCenter', double(target.smcSepProbCenter), ...
    'randStreamType', char(target.randStream.type), ...
    'randStreamSeed', double(target.randStream.seed), ...
    'randStreamState', double(target.randStream.state(:)));
artifact.chromosome = chrom;

out_dir = fullfile(repo_root, 'tmp');
if ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
out_path = fullfile(out_dir, 'chromcond_prewarmup_state.mat');
save(out_path, 'artifact', '-v7');
fprintf('saved %s\n', out_path);
