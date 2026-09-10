function l22_dnas_chromosome_release_rng_ledger_batch(varargin)
% l22_dnas_chromosome_release_rng_ledger_batch
%
% Batched driver around the same per-tick chromosome-owned release RNG
% capture logic as l22_dnas_chromosome_release_rng_ledger.m (duplicated
% here, not called, since MATLAB cannot import another script file's local
% functions -- this mirrors the existing repo convention of self-contained
% diagnostic/extraction scripts).
%
% CORRECTNESS NOTE (2026-09-03, corrective fix): this script previously
% called karr_bootstrap() ONCE per MATLAB process and reused the live
% simulation object across every seed in -seeds "to amortize startup
% cost". That was a real, proven bug, not a safe optimization:
% seed_simulation()/sim.seedRandStream() only resets RNG STREAMS -- it
% does not reset the chromosome's physical bound-site state (or any other
% state/process's physical state) back to the pristine
% Simulation_fitted.mat initial condition. Reusing one `sim` across many
% seeds therefore let each seed after the first inherit the PREVIOUS
% seed's fully-evolved (100-tick) physical chromosome state instead of a
% fresh initial condition -- silently corrupting seed_001..seed_199's
% ledgers (seed_000, generated separately before this batch script
% existed, was unaffected). Confirmed by: (1) a from-scratch MATLAB probe
% (scripts/matlab/l22_dnas_release_call_probe.m) that reproduces itself
% bit-exactly across repeated invocations but disagrees with the old
% seed_003 ledger even at tick 0; (2) a fresh single-seed regeneration of
% seed 3 and seed 0 via l22_dnas_chromosome_release_rng_ledger.m matching
% the probe exactly (seed 3) or the old file exactly (seed 0, proving seed
% 0 was never contaminated). See STATUS_L22_DNAS_SEPT2.md for the full
% investigation. The fix: karr_bootstrap() now runs INSIDE the seed loop,
% so every seed gets its own fresh simulation object loaded straight from
% Simulation_fitted.mat, exactly like the single-seed script -- this
% script no longer amortizes bootstrap cost across seeds; it exists only
% as a convenience wrapper that loops the single-seed procedure and writes
% each seed's ledger file, with no correctness difference from invoking
% l22_dnas_chromosome_release_rng_ledger.m N times.
%
% Usage:
%   addpath('scripts/matlab');
%   l22_dnas_chromosome_release_rng_ledger_batch('seeds', [1 2 3], ...
%       'n_ticks', 100, 'out_dir', fullfile(pwd, 'data', ...
%       'l22_dnas_rare_event', 'chromosome_release_rng_ledger'));

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
ensure_wholecell_runtime_paths(repo_root);

if ~exist(opts.out_dir, 'dir')
    mkdir(opts.out_dir);
end

for si = 1:numel(opts.seeds)
    seed = opts.seeds(si);
    out_path = fullfile(opts.out_dir, sprintf('seed_%03d.json', seed));

    % Fresh simulation object per seed -- see CORRECTNESS NOTE above. This
    % re-pays karr_bootstrap()'s load cost every seed (no longer
    % amortized), which is the price of correctness: it is the only way to
    % guarantee every seed starts from the pristine Simulation_fitted.mat
    % physical state, not a previous seed's evolved leftovers.
    sim = karr_bootstrap();
    [target_idx, canonical_name] = find_process_index(sim, 'DNASupercoiling');
    if isempty(target_idx)
        error('l22_dnas_chromosome_release_rng_ledger_batch:missingProcess', 'DNASupercoiling not found in simulation');
    end

    seed_simulation(sim, uint32(seed));
    tick_opts = struct('n_ticks', opts.n_ticks, 'seed', seed);
    summary = run_ledger(sim, target_idx, canonical_name, tick_opts);

    fid = fopen(out_path, 'w');
    if fid < 0
        error('l22_dnas_chromosome_release_rng_ledger_batch:writeFailed', 'Could not open output path: %s', out_path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(summary));
    clear cleaner;
    fprintf('[l22_dnas_chromosome_release_rng_ledger_batch] seed=%d wrote %s\n', seed, out_path);
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
    'seeds', 0, ...
    'n_ticks', 100, ...
    'out_dir', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_chromosome_release_rng_ledger_batch:invalidArgs', 'Arguments must be name/value pairs');
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
            error('l22_dnas_chromosome_release_rng_ledger_batch:unknownOption', 'Unknown option: %s', char(name));
    end
end

if isempty(opts.out_dir)
    opts.out_dir = fullfile(infer_repo_root(), 'data', 'l22_dnas_rare_event', 'chromosome_release_rng_ledger');
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
