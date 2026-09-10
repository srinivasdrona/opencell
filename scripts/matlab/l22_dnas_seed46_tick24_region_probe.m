function summary = l22_dnas_seed46_tick24_region_probe(varargin)
% l22_dnas_seed46_tick24_region_probe
%
% Minimal, safe, non-invasive probe: runs the REAL full-process scheduler
% forward to a target seed/tick (identical scheduler-loop pattern already
% proven in l22_dnas_chromosome_release_rng_ledger.m), then immediately
% BEFORE calling the real, untouched DNASupercoiling.evolveState(), computes
% (READ-ONLY, no side effects, no RNG consumption -- pure queries of live
% chromosome state) the exact same `sigmas`/`legal` arrays DNASupercoiling.m
% computes internally, for ALL positive dsDNA regions (not just the
% longest). This is safe to do BEFORE the real evolveState() call because
% it duplicates only read-only formula application (find(), arithmetic),
% never a mutating or RNG-consuming call -- the real evolveState() that
% follows is completely untouched and produces the authoritative result.
%
% After evolveState() runs for real, captures chromosome.linkingNumbers for
% the target (position, strand) to see what MATLAB's own activity actually
% did there this tick.
%
% Example:
%   addpath('scripts/matlab');
%   l22_dnas_seed46_tick24_region_probe('seed', 46, 'tick_zero_based', 24, ...
%       'target_position_one_based', 578692, 'target_strand_one_based', 3, ...
%       'out_path', fullfile(pwd, 'tmp', 'seed46_tick24_region_probe.json'));

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
ensure_wholecell_runtime_paths(repo_root);

sim = karr_bootstrap();
[target_idx, canonical_name] = find_process_index(sim, 'DNASupercoiling');
if isempty(target_idx)
    error('l22_dnas_seed46_tick24_region_probe:missingProcess', 'DNASupercoiling not found in simulation');
end
seed_simulation(sim, uint32(opts.seed));

summary = run_probe(sim, target_idx, canonical_name, opts);

if ~isempty(opts.out_path)
    out_dir = fileparts(opts.out_path);
    if ~isempty(out_dir) && ~exist(out_dir, 'dir')
        mkdir(out_dir);
    end
    fid = fopen(opts.out_path, 'w');
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(summary));
    fprintf('[l22_dnas_seed46_tick24_region_probe] wrote %s\n', opts.out_path);
end
end

function summary = run_probe(sim, target_idx, canonical_name, opts)
time = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;
processes = sim.processes;
nProcesses = numel(processes);
rna_decay_idx = sim.processIndex('RNADecay');

target_tick_one_based = opts.tick_zero_based + 1;

for abs_tick = 1:target_tick_one_based
    time.values = time.values + sim.stepSizeSec;
    stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
        stim.values, stim.setValues, time.values);

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

        is_target = (proc_idx == target_idx) && (abs_tick == target_tick_one_based);
        if is_target
            summary = capture_region_and_evolve(mod, opts);
            mod.copyToState();
            mets.counts(gidx) = counts + mod.substrates(lidx, :) - allocation;
            if ~isempty(mod.simulationStateSideEffects)
                mod.simulationStateSideEffects.updateSimulationState(sim);
            end
            return;
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

error('l22_dnas_seed46_tick24_region_probe:targetNotReached', 'Failed to reach target tick');
end

function summary = capture_region_and_evolve(mod, opts)
c = mod.chromosome;

% READ-ONLY duplicate of DNASupercoiling.m's sigma/legal computation
% (evolveState.m lines ~360-375) -- no mutation, no RNG draw. Safe to run
% before the real evolveState() call below.
[tmpPosStrands, lengths] = find(c.doubleStrandedRegions);
tmpIdxs = find(builtin('mod', tmpPosStrands(:, 2), 2));
dsPosStrands = tmpPosStrands(tmpIdxs, :);
lengths = lengths(tmpIdxs, 1);

[~, linkingNumbers] = find(c.linkingNumbers);
linkingNumbers = linkingNumbers(tmpIdxs, 1);
sigmas = (linkingNumbers - lengths / c.relaxedBasesPerTurn) ./ (lengths / c.relaxedBasesPerTurn);

legal = [ ...
    sigmas > mod.gyraseSigmaLimit ...
    sigmas > mod.topoIVSigmaLimit ...
    sigmas < mod.topoISigmaLimit];

target_row = find( ...
    dsPosStrands(:, 1) == opts.target_position_one_based & ...
    dsPosStrands(:, 2) == opts.target_strand_one_based, 1);

summary = struct();
summary.seed = int32(opts.seed);
summary.tick_zero_based = int32(opts.tick_zero_based);
summary.target_position_one_based = int32(opts.target_position_one_based);
summary.target_strand_one_based = int32(opts.target_strand_one_based);
summary.target_row_found = ~isempty(target_row);
summary.all_ds_regions = struct( ...
    'dsPosStrands', int32(dsPosStrands), ...
    'lengths', int32(lengths), ...
    'linkingNumbers', double(linkingNumbers), ...
    'sigmas', double(sigmas), ...
    'legal', logical(legal));
summary.gyraseSigmaLimit = double(mod.gyraseSigmaLimit);
summary.topoIVSigmaLimit = double(mod.topoIVSigmaLimit);
summary.topoISigmaLimit = double(mod.topoISigmaLimit);
summary.enzymeIndexs_gyrase = int32(mod.enzymeIndexs_gyrase);
summary.enzymeIndexs_topoIV = int32(mod.enzymeIndexs_topoIV);
summary.enzymeIndexs_topoI = int32(mod.enzymeIndexs_topoI);

if ~isempty(target_row)
    summary.target_region = struct( ...
        'row', int32(target_row), ...
        'length', int32(lengths(target_row)), ...
        'linking_before', double(linkingNumbers(target_row)), ...
        'sigma_before', double(sigmas(target_row)), ...
        'legal_gyrase', logical(legal(target_row, mod.enzymeIndexs_gyrase)), ...
        'legal_topoIV', logical(legal(target_row, mod.enzymeIndexs_topoIV)), ...
        'legal_topoI', logical(legal(target_row, mod.enzymeIndexs_topoI)));
    summary.target_region.free_gyrase_before = double(mod.enzymes(mod.enzymeIndexs_gyrase, 1));
    summary.target_region.free_topoIV_before = double(mod.enzymes(mod.enzymeIndexs_topoIV, 1));
    summary.target_region.free_topoI_before = double(mod.enzymes(mod.enzymeIndexs_topoI, 1));
    summary.target_region.bound_gyrase_before = double(mod.boundEnzymes(mod.enzymeIndexs_gyrase, 1));
    summary.target_region.bound_topoIV_before = double(mod.boundEnzymes(mod.enzymeIndexs_topoIV, 1));
    summary.target_region.bound_topoI_before = double(mod.boundEnzymes(mod.enzymeIndexs_topoI, 1));
end

% Now let the REAL, untouched evolveState() run (this is the only call
% that mutates state or consumes RNG in this function).
mod.evolveState();

[~, linkingNumbersAfter] = find(c.linkingNumbers);
[posStrandsAfter, ~] = find(c.linkingNumbers);
summary.linkingNumbers_after_full = struct( ...
    'posStrands', int32(posStrandsAfter), ...
    'values', double(linkingNumbersAfter));

if ~isempty(target_row)
    target_after_idx = find( ...
        posStrandsAfter(:, 1) == opts.target_position_one_based & ...
        posStrandsAfter(:, 2) == opts.target_strand_one_based, 1);
    if isempty(target_after_idx)
        summary.target_region.linking_after = double(0);
        summary.target_region.linking_after_present = false;
    else
        summary.target_region.linking_after = double(linkingNumbersAfter(target_after_idx));
        summary.target_region.linking_after_present = true;
    end
end
end

function opts = parse_inputs(varargin)
opts = struct( ...
    'seed', 0, ...
    'tick_zero_based', 0, ...
    'target_position_one_based', 1, ...
    'target_strand_one_based', 1, ...
    'out_path', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_seed46_tick24_region_probe:invalidArgs', 'Arguments must be name/value pairs');
end

for i = 1:2:numel(varargin)
    name = varargin{i};
    value = varargin{i + 1};
    switch lower(char(name))
        case 'seed'
            opts.seed = double(value);
        case 'tick_zero_based'
            opts.tick_zero_based = double(value);
        case 'target_position_one_based'
            opts.target_position_one_based = double(value);
        case 'target_strand_one_based'
            opts.target_strand_one_based = double(value);
        case 'out_path'
            opts.out_path = char(value);
        otherwise
            error('l22_dnas_seed46_tick24_region_probe:unknownOption', 'Unknown option: %s', char(name));
    end
end
end

function repo_root = infer_repo_root()
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
end

function seed_simulation(sim, seed)
try
    if isobject(sim) && ismethod(sim, 'applyOptions') && ismethod(sim, 'seedRandStream')
        sim.applyOptions('seed', seed);
        sim.seedRandStream();
        return;
    end
catch
end
try
    if isprop(sim, 'randStream') && ~isempty(sim.randStream)
        sim.randStream.seed = seed;
        return;
    end
catch
end
end

function [idx, canonical_name] = find_process_index(sim, requested_name)
idx = [];
canonical_name = '';
want = normalize_name_token(requested_name);
for i = 1:numel(sim.processes)
    proc = sim.processes{i};
    short = process_short_name(proc);
    tokens = { ...
        normalize_name_token(short), ...
        normalize_name_token(proc.wholeCellModelID)};
    if isprop(proc, 'name')
        tokens{end + 1} = normalize_name_token(proc.name); %#ok<AGROW>
    end
    if any(strcmp(tokens, want))
        idx = i;
        canonical_name = short;
        return;
    end
end
end

function short = process_short_name(proc)
wid = proc.wholeCellModelID;
if strncmp(wid, 'Process_', numel('Process_'))
    short = wid(numel('Process_') + 1:end);
else
    short = wid;
end
end

function token = normalize_name_token(s)
token = lower(regexprep(char(s), '[^a-zA-Z0-9]', ''));
end

function ensure_wholecell_runtime_paths(repo_root)
candidate_roots = { ...
    fullfile(repo_root, 'data', 'm1_sources', 'WholeCell'), ...
    'E:\opencell\data\m1_sources\WholeCell'};

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
            return;
        catch
        end
    end

    addpath(genpath(fullfile(root, 'src')));
    addpath(genpath(fullfile(root, 'lib')));
    return;
end
end
