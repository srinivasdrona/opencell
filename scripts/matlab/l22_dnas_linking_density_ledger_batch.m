function l22_dnas_linking_density_ledger_batch(varargin)
% l22_dnas_linking_density_ledger_batch
%
% Batched driver around the same per-tick region-sigma capture logic as
% l22_dnas_linking_density_ledger.m (duplicated here, not called -- MATLAB
% cannot import another script file's local functions; mirrors the
% existing repo convention of self-contained diagnostic/extraction
% scripts, and also mirrors l22_dnas_chromosome_release_rng_ledger_batch.m
% exactly, including its CORRECTNESS NOTE fix).
%
% CORRECTNESS: karr_bootstrap() runs INSIDE the seed loop -- a fresh
% simulation object is loaded from Simulation_fitted.mat for every seed.
% seed_simulation()/sim.seedRandStream() only resets RNG streams, not the
% chromosome's physical bound-site/state; reusing one `sim` across seeds
% would silently leak seed N's fully-evolved chromosome state into seed
% N+1's ledger (this exact bug was found and fixed for the sibling
% chromosome-release-RNG ledger batch script; same fix applied here
% proactively).
%
% WHY THIS EXISTS: see l22_dnas_linking_density_ledger.m's docstring (int32
% linkingNumbers precision loss in the canonical per-process trace).  This
% batch driver regenerates the sidecar ledger across the FULL evaluated
% corpus (200 seeds x 100 ticks, matching the frozen N=200 gate's base
% checkpoint tensor shape) so the superhelicalDensity hidden-field oracle
% can be wired into scripts/l22_dnas_sept2_two_sided_n200_eval.py for every
% (seed, tick) it evaluates, not just the small predeclared diagnostic
% subset.
%
% Usage:
%   addpath('scripts/matlab');
%   l22_dnas_linking_density_ledger_batch('seeds', [0 1 2], ...
%       'n_ticks', 100, 'out_dir', fullfile(pwd, 'data', ...
%       'l22_dnas_rare_event', 'linking_density_ledger'));

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
ensure_wholecell_runtime_paths(repo_root);

if ~exist(opts.out_dir, 'dir')
    mkdir(opts.out_dir);
end

for si = 1:numel(opts.seeds)
    seed = opts.seeds(si);
    out_path = fullfile(opts.out_dir, sprintf('seed_%03d.json', seed));

    % Fresh simulation object per seed -- see CORRECTNESS note above.
    sim = karr_bootstrap();
    [target_idx, canonical_name] = find_process_index(sim, 'DNASupercoiling');
    if isempty(target_idx)
        error('l22_dnas_linking_density_ledger_batch:missingProcess', 'DNASupercoiling not found in simulation');
    end

    seed_simulation(sim, uint32(seed));
    tick_opts = struct('n_ticks', opts.n_ticks, 'seed', seed);
    summary = run_ledger(sim, target_idx, canonical_name, tick_opts);

    fid = fopen(out_path, 'w');
    if fid < 0
        error('l22_dnas_linking_density_ledger_batch:writeFailed', 'Could not open output path: %s', out_path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(summary));
    clear cleaner;
    fprintf('[l22_dnas_linking_density_ledger_batch] seed=%d wrote %s\n', seed, out_path);
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
ticks = struct('tick_zero_based', {}, 'positions', {}, 'strands', {}, 'lengths', {}, 'sigmas', {});

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
            [positions, strands, lengths, sigmas] = compute_region_sigmas(mod);
            ticks(end + 1) = struct( ... %#ok<AGROW>
                'tick_zero_based', int32(abs_tick - 1), ...
                'positions', positions(:)', ...
                'strands', strands(:)', ...
                'lengths', lengths(:)', ...
                'sigmas', sigmas(:)');
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

summary = struct();
summary.seed = int32(opts.seed);
summary.process_name = canonical_name;
summary.n_ticks = int32(n_ticks);
summary.ticks = ticks;
end

function [positions, strands, lengths, sigmas] = compute_region_sigmas(this)
c = this.chromosome;
[tmpPosStrands, lens] = find(c.doubleStrandedRegions);
tmpIdxs = find(mod(tmpPosStrands(:, 2), 2));
lengths = lens(tmpIdxs, 1);
positions = tmpPosStrands(tmpIdxs, 1);
strands = tmpPosStrands(tmpIdxs, 2);

[~, linkingNumbers] = find(c.linkingNumbers);
linkingNumbers = linkingNumbers(tmpIdxs, 1);
sigmas = (linkingNumbers - lengths / c.relaxedBasesPerTurn) ./ (lengths / c.relaxedBasesPerTurn);
end

function opts = parse_inputs(varargin)
opts = struct( ...
    'seeds', 0, ...
    'n_ticks', 100, ...
    'out_dir', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_linking_density_ledger_batch:invalidArgs', 'Arguments must be name/value pairs');
end

for i = 1:2:numel(varargin)
    name = varargin{i};
    value = varargin{i + 1};
    switch lower(char(name))
        case 'seeds'
            opts.seeds = double(value);
        case 'n_ticks'
            opts.n_ticks = double(value);
        case 'out_dir'
            opts.out_dir = char(value);
        otherwise
            error('l22_dnas_linking_density_ledger_batch:unknownOption', 'Unknown option: %s', char(name));
    end
end

if isempty(opts.out_dir)
    opts.out_dir = fullfile(infer_repo_root(), 'data', 'l22_dnas_rare_event', 'linking_density_ledger');
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
