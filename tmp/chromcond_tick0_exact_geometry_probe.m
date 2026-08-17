repo_root = fileparts(fileparts(mfilename('fullpath')));
scripts_dir = fullfile(repo_root, 'scripts', 'matlab');
addpath(scripts_dir);

candidate_roots = { ...
    fullfile(repo_root, 'data', 'm1_sources', 'WholeCell'), ...
    'E:\opencell\data\m1_sources\WholeCell' ...
};
for i = 1:numel(candidate_roots)
    root = candidate_roots{i};
    if ~exist(root, 'dir')
        continue;
    end
    old_dir = pwd;
    cleaner = onCleanup(@() cd(old_dir)); %#ok<NASGU>
    cd(root);
    if exist('setWarnings.m', 'file') == 2
        try
            setWarnings();
        catch
        end
    end
    if exist('setPath.m', 'file') == 2
        try
            setPath();
            break;
        catch
        end
    end
    addpath(genpath(fullfile(root, 'src')));
    addpath(genpath(fullfile(root, 'lib')));
    break;
end

surface_path = fullfile(repo_root, 'tmp', 'chromcond_hidden_tick0_exact_surface.mat');
payload = load(surface_path, 'artifact');
artifact = payload.artifact;

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
target.initializeState();

target.randStream.state = double(artifact.postwarmup.randStreamState);
target.substrates = double(artifact.hidden.substrates(:));
target.enzymes = double(artifact.hidden.enzymes(:));
target.boundEnzymes = double(artifact.hidden.boundEnzymes(:));
apply_chromosome_state(target.chromosome, artifact.hidden.chromosome);

tick0 = struct();
tick0.postwarmupRandStreamState = double(artifact.postwarmup.randStreamState);
tick0.hiddenSubstrates = double(target.substrates(:)');
tick0.hiddenEnzymes = double(target.enzymes(:)');
tick0.hiddenBoundEnzymes = double(target.boundEnzymes(:)');
tick0 = capture_tick0_geometry(tick0, target);

before_smc = find(target.chromosome.complexBoundSites == target.enzymeGlobalIndexs(target.enzymeIndexs_SMC_ADP));
target.evolveState();
after_smc = find(target.chromosome.complexBoundSites == target.enzymeGlobalIndexs(target.enzymeIndexs_SMC_ADP));
tick0.actualAddedSmcPosStrnds = double(setdiff(after_smc, before_smc, 'rows'));
tick0.actualPostRandStreamState = double(target.randStream.state(:)');

out.artifact = artifact;
out.tick0 = tick0;
out_path = fullfile(repo_root, 'tmp', 'chromcond_tick0_exact_geometry_probe.json');
fid = fopen(out_path, 'w');
assert(fid ~= -1, 'Could not open output path: %s', out_path);
cleaner2 = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(out), 'char');

fprintf('saved %s\n', out_path);
fprintf('tick0 exact actual added sites:\n');
disp(tick0.actualAddedSmcPosStrnds);

function apply_chromosome_state(chrom, state)
    props = { ...
        'polymerizedRegions', ...
        'linkingNumbers', ...
        'monomerBoundSites', ...
        'complexBoundSites', ...
        'gapSites', ...
        'abasicSites', ...
        'damagedSugarPhosphates', ...
        'damagedBases', ...
        'intrastrandCrossLinks', ...
        'strandBreaks', ...
        'hollidayJunctions' ...
    };
    logical_props = {'gapSites', 'abasicSites', 'strandBreaks', 'hollidayJunctions'};
    for j = 1:numel(props)
        prop = props{j};
        tri = state.(prop);
        subs = [double(tri.positions(:)) double(tri.strands(:))];
        vals = tri.values(:);
        if ismember(prop, logical_props)
            vals = logical(vals);
        else
            vals = double(vals);
        end
        shape = double(tri.shape(:)');
        chrom.(prop) = edu.stanford.covert.util.CircularSparseMat(subs, vals, shape, 1);
    end
end

function tick0 = capture_tick0_geometry(tick0, proc)
    c = proc.chromosome;
    sequence_len = c.sequenceLen;
    smc_local_idx = proc.enzymeIndexs_SMC_ADP;
    smc_global_idx = proc.enzymeGlobalIndexs(smc_local_idx);
    smc_footprint = proc.enzymeDNAFootprints(smc_local_idx);

    tick0.preRandStreamState = double(proc.randStream.state(:)');
    tick0.preSubstrates = double(proc.substrates(:)');
    tick0.preEnzymes = double(proc.enzymes(:)');
    tick0.preBoundEnzymes = double(proc.boundEnzymes(:)');

    nBindingMax = min([ ...
        proc.substrates(proc.substrateIndexs_atp) ...
        proc.substrates(proc.substrateIndexs_water) ...
        proc.enzymes(proc.enzymeIndexs_SMC) + proc.enzymes(proc.enzymeIndexs_SMC_ADP)]);
    tick0.nBindingMax = double(nBindingMax);

    [poly_pos, poly_lens] = find(c.polymerizedRegions);
    tick0.outerPolymerized = pack_regions(poly_pos, poly_lens, []);

    smc_pos = find(c.complexBoundSites == smc_global_idx);
    shifted_smc = [
        circ1( ...
            smc_pos(:, 1) - proc.smcSepNt / 2 - proc.smcSepProbCenter / 2 + smc_footprint / 2, ...
            sequence_len), ...
        2 * ceil(smc_pos(:, 2) / 2) - 1;
        circ1( ...
            smc_pos(:, 1) - proc.smcSepNt / 2 - proc.smcSepProbCenter / 2 + smc_footprint / 2, ...
            sequence_len), ...
        2 * ceil(smc_pos(:, 2) / 2)
    ];
    tick0.existingSmcSites = double(smc_pos);
    tick0.shiftedSmcSpacingExclusions = double(shifted_smc);

    [outer_excluded_pos, outer_excluded_lens] = c.excludeRegions( ...
        poly_pos, ...
        poly_lens, ...
        shifted_smc, ...
        proc.smcSepNt(ones(size(shifted_smc, 1), 1), 1) + proc.smcSepProbCenter);
    tick0.outerAfterSmcExclusion = pack_regions(outer_excluded_pos, outer_excluded_lens, []);

    [accessible_pos, accessible_lens] = c.getAccessibleRegions([], smc_global_idx);
    tick0.accessibleRegions = pack_regions(accessible_pos, accessible_lens, []);

    [binding_pos, binding_lens] = c.intersectRegions( ...
        accessible_pos, ...
        accessible_lens, ...
        outer_excluded_pos, ...
        outer_excluded_lens);
    binding_weights = max(0, binding_lens - smc_footprint + 1);
    tick0.bindingRegionsInitial = pack_regions(binding_pos, binding_lens, binding_weights);

    pre_sample_state = proc.randStream.state;
    manual_stored = zeros(0, 2);
    samples = repmat(struct( ...
        'randStreamStateBefore', [], ...
        'regionsBefore', struct(), ...
        'regionIndex1Based', [], ...
        'offset0Based', [], ...
        'centroidPosStrand', [], ...
        'storedPosStrand', [], ...
        'randStreamStateAfter', [], ...
        'regionsAfter', struct()), min(3, double(nBindingMax)), 1);

    rgn_pos = binding_pos;
    rgn_lens = binding_lens;
    rgn_probs = binding_weights;
    n_samples = 0;
    for sample_idx = 1:min(3, double(nBindingMax))
        if ~any(rgn_probs)
            break;
        end

        n_samples = n_samples + 1;
        samples(sample_idx).randStreamStateBefore = double(proc.randStream.state(:)');
        samples(sample_idx).regionsBefore = pack_regions(rgn_pos, rgn_lens, rgn_probs);

        rgn_idx = proc.randStream.randsample(numel(rgn_probs), 1, true, rgn_probs);
        offset = ceil(proc.randStream.rand * (rgn_lens(rgn_idx) - smc_footprint + 1)) - 1;
        centroid = [rgn_pos(rgn_idx, 1) + offset, rgn_pos(rgn_idx, 2)];
        stored = centroid;
        if mod(stored(2), 2) == 1
            stored(1) = circ1(stored(1) - proc.enzymeDNAFootprints5Prime(smc_local_idx), sequence_len);
        else
            stored(1) = circ1(stored(1) - proc.enzymeDNAFootprints3Prime(smc_local_idx), sequence_len);
        end

        samples(sample_idx).regionIndex1Based = double(rgn_idx);
        samples(sample_idx).offset0Based = double(offset);
        samples(sample_idx).centroidPosStrand = double(centroid);
        samples(sample_idx).storedPosStrand = double(stored);
        manual_stored(end + 1, :) = stored; %#ok<AGROW>

        [rgn_pos, rgn_lens, rgn_probs] = proc.calcNewRegions( ...
            rgn_pos, ...
            rgn_lens, ...
            rgn_probs, ...
            rgn_idx, ...
            offset);
        samples(sample_idx).randStreamStateAfter = double(proc.randStream.state(:)');
        samples(sample_idx).regionsAfter = pack_regions(rgn_pos, rgn_lens, rgn_probs);
    end

    proc.randStream.state = pre_sample_state;
    tick0.samples = samples(1:n_samples);
    tick0.manualStoredPosStrnds = double(manual_stored);
end

function out = pack_regions(pos_strnds, lens, weights)
    out = struct( ...
        'posStrnds', double(pos_strnds), ...
        'lens', double(lens(:)'));
    if isempty(weights)
        out.weights = double([]);
    else
        out.weights = double(weights(:)');
    end
end

function pos1 = circ1(pos, sequence_len)
    pos1 = mod(pos - 1, sequence_len) + 1;
end
