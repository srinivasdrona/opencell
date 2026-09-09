function summary = l22_dnas_chromosome_release_rng_ledger(varargin)
% l22_dnas_chromosome_release_rng_ledger
%
% Standalone, self-contained MATLAB extractor (duplicates only the minimal
% scheduler-loop logic already used by l22_dnas_source_gap_probe.m; does NOT
% modify scripts/matlab/extract_per_process_traces_v2.m or any other shared
% file) that runs the REAL full-process scheduler for a given seed across
% n_ticks, and for every DNASupercoiling tick captures:
%   - chromosome.randStream.state immediately BEFORE DNASupercoiling's
%     evolveState() call (state_before)
%   - chromosome.randStream.state immediately AFTER that same call
%     (state_after)
%
% This is a sidecar ledger: it does not overwrite or alter any existing
% canonical per_process_traces_v2*/DNASupercoiling_100ticks.mat trace file.
%
% The (state_before, state_after) pair for each tick is reconstructed
% in-process (reconstruct_consumed_draws, below) into the exact sequence of
% uniform draws MATLAB's chromosome-owned RNG produced during that tick's
% release decision, using a throwaway RandStream replay -- NOT a
% reverse-engineered/reimplemented mcg16807 formula. This script never needs
% to understand mcg16807's internal algorithm at all.
%
% Example:
%   addpath('scripts/matlab');
%   l22_dnas_chromosome_release_rng_ledger('seed', 0, 'n_ticks', 100, ...
%       'out_path', fullfile(pwd, 'tmp', 'chromosome_release_rng_ledger_s000.json'));

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
ensure_wholecell_runtime_paths(repo_root);

sim = karr_bootstrap();
[target_idx, canonical_name] = find_process_index(sim, 'DNASupercoiling');
if isempty(target_idx)
    error('l22_dnas_chromosome_release_rng_ledger:missingProcess', 'DNASupercoiling not found in simulation');
end
seed_simulation(sim, uint32(opts.seed));

summary = run_ledger(sim, target_idx, canonical_name, opts);

if ~isempty(opts.out_path)
    out_dir = fileparts(opts.out_path);
    if ~isempty(out_dir) && ~exist(out_dir, 'dir')
        mkdir(out_dir);
    end
    fid = fopen(opts.out_path, 'w');
    if fid < 0
        error('l22_dnas_chromosome_release_rng_ledger:writeFailed', 'Could not open output path: %s', opts.out_path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(summary));
    fprintf('[l22_dnas_chromosome_release_rng_ledger] wrote %s\n', opts.out_path);
end
end

function summary = run_ledger(sim, target_idx, canonical_name, opts)
time = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;
processes = sim.processes;
nProcesses = numel(processes);
rna_decay_idx = sim.processIndex('RNADecay');

n_ticks = opts.n_ticks;
ticks = struct('tick_zero_based', {}, 'chromosome_state_before', {}, 'chromosome_state_after', {}, ...
    'process_state_before', {}, 'process_state_after', {}, 'chromosome_release_draws', {}, ...
    'chromosome_release_draws_reconstructed_ok', {}, 'chromosome_release_draws_iterations', {}, ...
    'process_draws', {}, 'process_draws_reconstructed_ok', {}, 'process_draws_iterations', {});

for abs_tick = 1:n_ticks
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

        is_target = (proc_idx == target_idx);
        if is_target
            chrom_state_before = serialize_randstream_state(mod.chromosome.randStream);
            proc_state_before = serialize_randstream_state(mod.randStream);
        end

        mod.evolveState();

        if is_target
            chrom_state_after = serialize_randstream_state(mod.chromosome.randStream);
            proc_state_after = serialize_randstream_state(mod.randStream);
            reconstructed = reconstruct_consumed_draws( ...
                mod.chromosome.randStream, chrom_state_before, chrom_state_after);
            proc_reconstructed = reconstruct_consumed_draws( ...
                mod.randStream, proc_state_before, proc_state_after);
            ticks(end + 1) = struct( ... %#ok<AGROW>
                'tick_zero_based', int32(abs_tick - 1), ...
                'chromosome_state_before', chrom_state_before, ...
                'chromosome_state_after', chrom_state_after, ...
                'process_state_before', proc_state_before, ...
                'process_state_after', proc_state_after, ...
                'chromosome_release_draws', reconstructed.draws, ...
                'chromosome_release_draws_reconstructed_ok', reconstructed.ok, ...
                'chromosome_release_draws_iterations', int32(reconstructed.iterations), ...
                'process_draws', proc_reconstructed.draws, ...
                'process_draws_reconstructed_ok', proc_reconstructed.ok, ...
                'process_draws_iterations', int32(proc_reconstructed.iterations));
        end

        mod.copyToState();
        mets.counts(gidx) = counts + mod.substrates(lidx, :) - allocation;

        if ~isempty(mod.simulationStateSideEffects)
            mod.simulationStateSideEffects.updateSimulationState(sim);
        end
    end

    mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
        mets.counts, mets.setCounts, time.values);
end

summary = struct();
summary.seed = int32(opts.seed);
summary.process_name = canonical_name;
summary.n_ticks = int32(n_ticks);
summary.ticks = ticks;
end

function reconstructed = reconstruct_consumed_draws(live_randStream, state_before, state_after)
% Recover the exact sequence of uniform draws chromosome.randStream produced
% between state_before and state_after by replaying forward from
% state_before on a THROWAWAY RandStream object (never the live production
% stream) until its State matches state_after exactly. This is a black-box
% reconstruction: it needs no knowledge of mcg16807's internal advance
% formula (proven equivalent to the true consumed sequence in
% tmp/probe_mcg16807_reconstruction.m and tmp/probe_mcg16807_vector_draw.m).
max_iterations = 200000;
reconstructed = struct('draws', [], 'ok', false, 'iterations', 0);

if isequal(state_before.values, state_after.values)
    reconstructed.ok = true;
    return;
end

rs_type = 'mcg16807';
try
    rs_type = live_randStream.Type;
catch
end

throwaway = RandStream(rs_type, 'Seed', 1);
throwaway.State = state_before.values;

draws = zeros(0, 1);
for it = 1:max_iterations
    d = rand(throwaway, 1, 1);
    draws(end + 1, 1) = d; %#ok<AGROW>
    if isequal(throwaway.State, state_after.values)
        reconstructed.ok = true;
        reconstructed.iterations = it;
        reconstructed.draws = draws;
        return;
    end
end
reconstructed.iterations = max_iterations;
reconstructed.draws = draws;
end

function state = serialize_randstream_state(randStream)
state = struct();
try
    raw = randStream.state;
catch
    raw = [];
end
state.values = double(raw(:)');
state.length = int32(numel(raw));
end

function opts = parse_inputs(varargin)
opts = struct( ...
    'seed', 0, ...
    'n_ticks', 100, ...
    'out_path', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_chromosome_release_rng_ledger:invalidArgs', 'Arguments must be name/value pairs');
end

for i = 1:2:numel(varargin)
    name = varargin{i};
    value = varargin{i + 1};
    switch lower(char(name))
        case 'seed'
            opts.seed = double(value);
        case 'n_ticks'
            opts.n_ticks = double(value);
        case 'out_path'
            opts.out_path = char(value);
        otherwise
            error('l22_dnas_chromosome_release_rng_ledger:unknownOption', 'Unknown option: %s', char(name));
    end
end

if isempty(opts.out_path)
    opts.out_path = fullfile(infer_repo_root(), 'tmp', sprintf('chromosome_release_rng_ledger_s%03d.json', opts.seed));
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
