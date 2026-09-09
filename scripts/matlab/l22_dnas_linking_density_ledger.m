function summary = l22_dnas_linking_density_ledger(varargin)
% l22_dnas_linking_density_ledger
%
% Standalone, self-contained MATLAB extractor (duplicates only the minimal
% scheduler-loop logic already used by l22_dnas_chromosome_release_rng_ledger.m
% / l22_dnas_source_gap_probe.m; does NOT modify
% scripts/matlab/extract_per_process_traces_v2.m, l22_dnas_chromosome_
% release_rng_ledger.m, or any other shared file) that runs the REAL
% full-process scheduler for a given seed across n_ticks, and for every
% DNASupercoiling tick captures the EXACT double-precision sigma value for
% every positive dsDNA region -- i.e. DNASupercoiling.m evolveState()'s own
% `sigmas` vector (lines ~363-378), keyed by (position, strand) -- exactly
% as it exists immediately BEFORE DNASupercoiling's evolveState() call this
% tick.
%
% WHY THIS EXISTS: the canonical per_process_traces_v2*/DNASupercoiling_
% 100ticks.mat trace stores chromosome.linkingNumbers as an int32 HDF5
% dataset. For long-established regions this loses no decision-relevant
% precision (linking numbers are large integers there and the true
% fractional part is negligible relative to sigma thresholds). But for a
% BRAND-NEW dsDNA region created by a replication-fork-like split within
% the evaluation window, MATLAB assigns it a linking number equal to
% length/relaxedBasesPerTurn (i.e. torsionally perfectly relaxed, sigma
% EXACTLY 0.0) -- a genuinely fractional value (e.g. 10.5715... for a
% 111bp region). Rounding that to the nearest int32 (11, in this example)
% shifts the reconstructed sigma from exactly 0.0 to +0.04, which flips
% `sigma > topoIVSigmaLimit` (0.0) from false to true -- making topoIV
% falsely "legal" in that region and directly causing extra activity-phase
% RNG draws / topoIV activity events that real MATLAB never has. Confirmed
% via l22_dnas_process_rng_region_probe.m (seed 0, tick 2): real sigma is
% exactly 0.0 for the two newly-split 111bp regions; the canonical trace's
% int32-rounded linkingNumbers value of 11 reconstructs sigma = +0.0405.
%
% Production (opencell/vivarium/karr_dna_supercoiling.py) already has a
% hidden-field oracle input surface for exactly this quantity
% (ChromosomeStore.has_hidden_sparse_field/get_hidden_sparse_field(
% "superhelicalDensity")) -- it is simply never populated for this wave.
% This ledger supplies that missing oracle data as a sidecar file; wiring
% it in is a separate (Python-side) step and does not touch this script.
%
% This is a sidecar ledger: it does not overwrite or alter any existing
% canonical per_process_traces_v2*/DNASupercoiling_100ticks.mat trace file.
%
% Example:
%   addpath('scripts/matlab');
%   l22_dnas_linking_density_ledger('seed', 0, 'n_ticks', 100, ...
%       'out_path', fullfile(pwd, 'tmp', 'linking_density_ledger_s000.json'));

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
ensure_wholecell_runtime_paths(repo_root);

sim = karr_bootstrap();
[target_idx, canonical_name] = find_process_index(sim, 'DNASupercoiling');
if isempty(target_idx)
    error('l22_dnas_linking_density_ledger:missingProcess', 'DNASupercoiling not found in simulation');
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
        error('l22_dnas_linking_density_ledger:writeFailed', 'Could not open output path: %s', opts.out_path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(summary));
    fprintf('[l22_dnas_linking_density_ledger] wrote %s\n', opts.out_path);
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
% Reproduces DNASupercoiling.m evolveState()'s own sigma computation
% (lines ~363-378) exactly, read-only, from the live chromosome state
% immediately before evolveState() executes. Returns one entry per
% POSITIVE-strand dsDNA region (same set DNASupercoiling.m itself iterates
% over), keyed by (position, strand) for downstream lookup.
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
    'seed', 0, ...
    'n_ticks', 100, ...
    'out_path', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_linking_density_ledger:invalidArgs', 'Arguments must be name/value pairs');
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
            error('l22_dnas_linking_density_ledger:unknownOption', 'Unknown option: %s', char(name));
    end
end

if isempty(opts.out_path)
    opts.out_path = fullfile(infer_repo_root(), 'tmp', sprintf('linking_density_ledger_s%03d.json', opts.seed));
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
