function extract_per_process_traces_v2(process_names, output_subdir, n_ticks, seed, tick_offset)
% extract_per_process_traces_v2
% Allocator-correct per-process trace extraction with per-tick tap points.
%
% For each named process, this function inlines the Simulation.evolveState
% scheduler/allocation loop each tick and captures:
%   states_before: target process properties after copyFromState + allocation
%   states_after:  target process properties after evolveState (before copyToState)
%
% tick_offset (optional, default 0): number of full-simulation burn-in ticks to
%   advance BEFORE snapshotting begins. Use this to capture an "event window" for
%   processes that are quiescent at cell birth (t=0) but active later -- e.g.
%   RibosomeAssembly's first assembly event is ~tick 238, so tick_offset=200 with
%   n_ticks=100 snapshots ticks 200..299 and captures the firing window. With the
%   default tick_offset=0 the behaviour is identical to the original extractor.
%
% Output file:
%   data/m1_sources/karr_native/<output_subdir>/<Process>_<n_ticks>ticks.mat
% containing states_before, states_after, metadata (-v7.3).

if nargin < 4 || isempty(seed)
    seed = uint32(0);
else
    seed = uint32(seed);
end
if nargin < 5 || isempty(tick_offset)
    tick_offset = 0;
else
    tick_offset = double(tick_offset);
end
if nargin < 2 || isempty(output_subdir)
    if seed == 0
        output_subdir = 'per_process_traces_v2';
    else
        output_subdir = sprintf('per_process_traces_v2_s%03d', seed);
    end
end
if nargin < 3 || isempty(n_ticks)
    n_ticks = 100;
end

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', output_subdir);
if ~exist(out_root, 'dir')
    mkdir(out_root);
end

ensure_wholecell_runtime_paths(repo_root);

if nargin < 1 || isempty(process_names)
    sim_probe = karr_bootstrap();
    process_names = collect_process_ids(sim_probe);
    clear sim_probe;
end

for i = 1:numel(process_names)
    requested_name = process_names{i};
    fprintf('\n[trace_v2] === %s ===\n', requested_name);

    sim = karr_bootstrap();
    [target_idx, canonical_name] = find_process_index(sim, requested_name);
    if isempty(target_idx)
        fprintf('[trace_v2] WARN process not found: %s\n', requested_name);
        continue;
    end

    out_path = fullfile(out_root, sprintf('%s_%dticks.mat', canonical_name, n_ticks));
    if exist(out_path, 'file')
        fprintf('[trace_v2] already exists, skipping: %s\n', out_path);
        continue;
    end

    proc = sim.processes{target_idx};
    snapshot_props = pick_snapshot_properties(proc);
    fprintf('[trace_v2] %s snapshot properties: %s\n', canonical_name, join_props(snapshot_props));

    states_before = struct();
    states_after = struct();
    for p = 1:numel(snapshot_props)
        states_before.(snapshot_props{p}) = cell(n_ticks, 1);
        states_after.(snapshot_props{p}) = cell(n_ticks, 1);
    end

    seed_simulation(sim, seed);

    % Optional event-window burn-in: advance the whole simulation tick_offset
    % ticks without snapshotting, so the subsequent n_ticks capture a window
    % where an otherwise-quiescent-at-birth process is active.
    for bt = 1:tick_offset
        [sim, ~, ~] = evolve_state_with_tap(sim, target_idx, snapshot_props);
    end

    ok = true;
    error_message = '';
    for t = 1:n_ticks
        try
            [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props);
            for p = 1:numel(snapshot_props)
                prop = snapshot_props{p};
                states_before.(prop){t, 1} = before_tick.(prop);
                states_after.(prop){t, 1} = after_tick.(prop);
            end
        catch err
            ok = false;
            error_message = sprintf('tick %d failed:\n%s', t, getReport(err, 'extended', 'hyperlinks', 'off'));
            break;
        end
    end

    if ~ok
        fprintf('[trace_v2] ERROR %s\n', error_message);
        fprintf('[trace_v2] skipped write: %s\n', out_path);
        continue;
    end

    metadata = struct( ...
        'process_name', canonical_name, ...
        'n_ticks', n_ticks, ...
        'rng_seed', seed, ...
        'tick_offset', tick_offset, ...
        'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
        'snapshot_properties', {snapshot_props} ...
    );

    save(out_path, 'states_before', 'states_after', 'metadata', '-v7.3');
    fprintf('[trace_v2] saved: %s\n', out_path);
end

end

function props = pick_snapshot_properties(proc)
props = intersect(properties(proc), { ...
    'substrates', 'enzymes', 'boundEnzymes', 'chromosome', ...
    'freeRNAs', 'aminoacylatedRNAs', ...
    'mRNAs', 'freeTRNAs', 'freeTMRNA', ...
    'aminoacylatedTRNAs', 'aminoacylatedTMRNA', 'boundTMRNA', ...
    'unprocessedRNAs', 'processedRNAs', 'intergenicRNAs', ...
    'unmodifiedRNAs', 'modifiedRNAs', ...
    'unprocessedMonomers', 'processedMonomers', ...
    'signalSequenceMonomers', ...
    'unmodifiedMonomers', 'modifiedMonomers', ...
    'unfoldedMonomers', 'foldedMonomers', ...
    'unfoldedComplexs', 'foldedComplexs', ...
    'inactiveMonomers', 'matureMonomers', ...
    'inactiveComplexs', 'matureComplexs', ...
    'complexs', 'monomers', 'rnas', 'RNAs', ...
});
end

function [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props)
before_tick = empty_snapshot_struct(snapshot_props);
after_tick = empty_snapshot_struct(snapshot_props);

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
        % Guard against negative RNA counts propagating into weighted sampling.
        mod.RNAs = max(0, mod.RNAs);
    end

    if proc_idx == target_idx
        before_tick = snapshot_from_process(mod, snapshot_props);
    end

    mod.evolveState();

    if proc_idx == target_idx
        after_tick = snapshot_from_process(mod, snapshot_props);
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

function out = snapshot_from_process(proc, snapshot_props)
out = struct();
for p = 1:numel(snapshot_props)
    prop = snapshot_props{p};
    out.(prop) = sanitize_snapshot_value(proc.(prop), 0);
end
end

function out = empty_snapshot_struct(snapshot_props)
out = struct();
for p = 1:numel(snapshot_props)
    out.(snapshot_props{p}) = [];
end
end

function out = sanitize_snapshot_value(v, depth)
if depth > 4
    out = '<MAX_DEPTH>';
    return;
end

if isnumeric(v) || islogical(v) || ischar(v) || isstring(v)
    out = v;
    return;
end

if iscell(v)
    out = cell(size(v));
    for i = 1:numel(v)
        out{i} = sanitize_snapshot_value(v{i}, depth + 1);
    end
    return;
end

if isstruct(v)
    out = struct();
    fns = fieldnames(v);
    for i = 1:numel(fns)
        fn = fns{i};
        try
            out.(fn) = sanitize_snapshot_value(v.(fn), depth + 1);
        catch
            out.(fn) = '<field-unreadable>';
        end
    end
    return;
end

if isobject(v)
    cls = class(v);
    % Special-case the Chromosome state object: write a sparse-triple
    % struct of its primary writable properties so chromosome-primary
    % L2.2 distances (Replication / DNARepair / DNASupercoiling /
    % DNADamage / ReplicationInitiation) have real signal instead of
    % the previous '<object:...>' placeholder string.
    if strcmp(cls, 'edu.stanford.covert.cell.sim.state.Chromosome')
        try
            out = serialize_chromosome_state(v);
            return;
        catch err
            out = struct('error', sprintf('serialize_chromosome_state failed: %s', err.message), 'class', cls);
            return;
        end
    end
    out = sprintf('<object:%s>', cls);
    return;
end

out = sprintf('<unsupported:%s>', class(v));
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

function names = collect_process_ids(sim)
names = cell(numel(sim.processes), 1);
for i = 1:numel(sim.processes)
    names{i} = process_short_name(sim.processes{i});
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
        normalize_name_token(proc.wholeCellModelID) ...
    };
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
            return;
        catch
        end
    end

    addpath(genpath(fullfile(root, 'src')));
    addpath(genpath(fullfile(root, 'lib')));
    return;
end
end

function s = join_props(props)
if isempty(props)
    s = '(none)';
    return;
end
s = props{1};
for i = 2:numel(props)
    s = [s ', ' props{i}]; %#ok<AGROW>
end
end
