function extract_per_process_traces_v2(process_names, output_subdir, n_ticks)
% extract_per_process_traces_v2
% Allocator-correct per-process trace extraction with per-tick tap points.
%
% For each named process, this function inlines the Simulation.evolveState
% scheduler/allocation loop each tick and captures:
%   states_before: target process properties after copyFromState + allocation
%   states_after:  target process properties after evolveState (before copyToState)
%
% Output file:
%   data/m1_sources/karr_native/<output_subdir>/<Process>_<n_ticks>ticks.mat
% containing states_before, states_after, metadata (-v7.3).

if nargin < 2 || isempty(output_subdir)
    output_subdir = 'per_process_traces_v2';
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
    [snapshot_props, snapshot_paths] = pick_snapshot_properties(proc, canonical_name);
    fprintf('[trace_v2] %s snapshot properties: %s\n', canonical_name, join_props(snapshot_props));

    states_before = struct();
    states_after = struct();
    for p = 1:numel(snapshot_props)
        states_before.(snapshot_props{p}) = cell(n_ticks, 1);
        states_after.(snapshot_props{p}) = cell(n_ticks, 1);
    end

    seed_simulation(sim, uint32(0));

    ok = true;
    error_message = '';
    for t = 1:n_ticks
        try
            [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, snapshot_paths);
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
        'rng_seed', uint32(0), ...
        'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
        'snapshot_properties', {snapshot_props} ...
    );

    save(out_path, 'states_before', 'states_after', 'metadata', '-v7.3');
    fprintf('[trace_v2] saved: %s\n', out_path);
end

end

function [props, paths] = pick_snapshot_properties(proc, canonical_name)
props = intersect(properties(proc), { ...
    'substrates', 'enzymes', 'boundEnzymes', ...
    'freeRNAs', 'aminoacylatedRNAs', ...
    'unprocessedRNAs', 'processedRNAs', ...
    'unmodifiedRNAs', 'modifiedRNAs', ...
    'unprocessedMonomers', 'processedMonomers', ...
    'unmodifiedMonomers', 'modifiedMonomers', ...
    'unfoldedMonomers', 'foldedMonomers', ...
    'inactiveMonomers', 'matureMonomers', ...
    'inactiveComplexs', 'matureComplexs', ...
    'complexs', 'monomers', 'rnas', ...
});
% Build out_field -> dotted access-path map (identity for plain properties).
paths = struct();
for k = 1:numel(props)
    paths.(props{k}) = props{k};
end
% Splice in per-process sibling-state extras (e.g. proc.polypeptide.xxx).
extras = pick_extra_specs(canonical_name);
for k = 1:size(extras, 1)
    out_field = extras{k, 1};
    expr = extras{k, 2};
    if ~resolves(proc, expr)
        continue;
    end
    if ~ismember(out_field, props)
        props{end+1, 1} = out_field;
    end
    paths.(out_field) = expr;
end
end

function specs = pick_extra_specs(canonical_name)
% Per-process sibling-state extras. Each row: {out_field, dotted_proc_path}.
% The path is resolved as proc.<path> via subsref. Only added if the path
% resolves cleanly at extraction time.
switch canonical_name
    case 'ProteinDecay'
        specs = { ...
            'abortedPolypeptides',     'polypeptide.abortedPolypeptides'; ...
            'abortedSequenceLengths',  'polypeptide.abortedSequenceLengths'; ...
        };
    otherwise
        specs = cell(0, 2);
end
end

function tf = resolves(proc, expr)
tf = false;
try
    val = eval_dotted(proc, expr); %#ok<NASGU>
    tf = true;
catch
end
end

function val = eval_dotted(root, expr)
% Avoid relying on strsplit (a name potentially shadowed by the WCM
% compatibility shims on the path); walk the dotted expression manually.
val = root;
remaining = expr;
while ~isempty(remaining)
    dot_pos = find(remaining == '.', 1, 'first');
    if isempty(dot_pos)
        field = remaining;
        remaining = '';
    else
        field = remaining(1:dot_pos - 1);
        remaining = remaining(dot_pos + 1:end);
    end
    val = val.(field);
end
end

function [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, snapshot_paths)
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
        before_tick = snapshot_from_process(mod, snapshot_props, snapshot_paths);
    end

    mod.evolveState();

    if proc_idx == target_idx
        after_tick = snapshot_from_process(mod, snapshot_props, snapshot_paths);
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

function out = snapshot_from_process(proc, snapshot_props, snapshot_paths)
out = struct();
for p = 1:numel(snapshot_props)
    prop = snapshot_props{p};
    if nargin >= 3 && isfield(snapshot_paths, prop)
        expr = snapshot_paths.(prop);
    else
        expr = prop;
    end
    try
        raw = eval_dotted(proc, expr);
    catch
        raw = [];
    end
    out.(prop) = sanitize_snapshot_value(raw, 0);
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
    out = sprintf('<object:%s>', class(v));
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
