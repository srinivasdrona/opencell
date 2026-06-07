if ~exist('seed_list', 'var') || isempty(seed_list)
    seed_list = 0:49;
end
if ~exist('n_ticks', 'var') || isempty(n_ticks)
    n_ticks = 100;
end
if ~exist('output_root', 'var') || isempty(output_root)
    this_file = mfilename('fullpath');
    matlab_dir = fileparts(this_file);
    scripts_dir = fileparts(matlab_dir);
    repo_root = fileparts(scripts_dir);
    output_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'ensembles', 'transcription');
end
if ~exist('force_overwrite', 'var') || isempty(force_overwrite)
    force_overwrite = false;
end

extract_transcription_ensemble_impl(seed_list, n_ticks, output_root, force_overwrite);

function extract_transcription_ensemble_impl(seed_list, n_ticks, output_root, force_overwrite)
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

if ~exist(output_root, 'dir')
    mkdir(output_root);
end

ensure_wholecell_runtime_paths(repo_root);

seed_vec = reshape(double(seed_list), 1, []);
fprintf('[transcription_ensemble] output_root: %s\n', output_root);
fprintf('[transcription_ensemble] n_ticks=%d, n_seeds=%d\n', n_ticks, numel(seed_vec));

entries = struct( ...
    'seed', {}, ...
    'path', {}, ...
    'size_bytes', {}, ...
    'n_ticks', {}, ...
    'rng_seed', {}, ...
    'n_observables', {}, ...
    'observables', {}, ...
    'status', {}, ...
    'elapsed_seconds', {} ...
);

for seed_index = 1:numel(seed_vec)
    seed = seed_vec(seed_index);
    seed_dir = fullfile(output_root, sprintf('seed_%03d', seed));
    if ~exist(seed_dir, 'dir')
        mkdir(seed_dir);
    end

    out_path = fullfile(seed_dir, sprintf('Transcription_%dticks.mat', n_ticks));
    if exist(out_path, 'file') && ~force_overwrite
        fprintf('[transcription_ensemble] seed=%d exists, skipping: %s\n', seed, out_path);
        file_info = dir(out_path);
        entries(end + 1) = struct( ... %#ok<AGROW>
            'seed', seed, ...
            'path', make_relative_path(out_path, repo_root), ...
            'size_bytes', double(file_info.bytes), ...
            'n_ticks', n_ticks, ...
            'rng_seed', uint32(seed), ...
            'n_observables', 4, ...
            'observables', {{'substrates', 'enzymes', 'boundEnzymes', 'RNAs'}}, ...
            'status', 'reused', ...
            'elapsed_seconds', 0.0 ...
        );
        continue;
    end

    fprintf('\n[transcription_ensemble] === seed=%d (%d/%d) ===\n', seed, seed_index, numel(seed_vec));
    seed_tic = tic;
    sim = karr_bootstrap();
    [target_idx, canonical_name] = find_process_index(sim, 'Transcription');
    if isempty(target_idx)
        error('Transcription process not found in simulation.');
    end
    proc = sim.processes{target_idx};

    snapshot_props = pick_transcription_snapshot_properties(proc);
    summary_fields = transcription_summary_field_names();
    all_fields = [snapshot_props, summary_fields];

    states_before = struct();
    states_after = struct();
    for i = 1:numel(all_fields)
        f = all_fields{i};
        states_before.(f) = cell(n_ticks, 1);
        states_after.(f) = cell(n_ticks, 1);
    end

    seed_simulation(sim, uint32(seed));

    ok = true;
    err_msg = '';
    for t = 1:n_ticks
        try
            [sim, before_tick, after_tick, before_summary, after_summary] = evolve_state_with_tap_transcription(sim, target_idx, snapshot_props); %#ok<ASGLU>
        catch err
            ok = false;
            err_msg = sprintf('tick %d failed:\n%s', t, getReport(err, 'extended', 'hyperlinks', 'off'));
            break;
        end

        for i = 1:numel(snapshot_props)
            f = snapshot_props{i};
            states_before.(f){t, 1} = before_tick.(f);
            states_after.(f){t, 1} = after_tick.(f);
        end
        for i = 1:numel(summary_fields)
            f = summary_fields{i};
            states_before.(f){t, 1} = before_summary.(f);
            states_after.(f){t, 1} = after_summary.(f);
        end
    end

    if ~ok
        fprintf('[transcription_ensemble] ERROR seed=%d\n%s\n', seed, err_msg);
        fprintf('[transcription_ensemble] skipped write: %s\n', out_path);
        entries(end + 1) = struct( ... %#ok<AGROW>
            'seed', seed, ...
            'path', make_relative_path(out_path, repo_root), ...
            'size_bytes', 0, ...
            'n_ticks', n_ticks, ...
            'rng_seed', uint32(seed), ...
            'n_observables', numel(all_fields), ...
            'observables', {all_fields}, ...
            'status', 'error', ...
            'elapsed_seconds', toc(seed_tic) ...
        );
        continue;
    end

    metadata = struct( ...
        'process_name', canonical_name, ...
        'n_ticks', n_ticks, ...
        'rng_seed', uint32(seed), ...
        'seed_index', seed_index - 1, ...
        'n_seeds_total', numel(seed_vec), ...
        'seed_list', uint32(seed_vec), ...
        'schema_version', 'transcription_ensemble_v1', ...
        'snapshot_properties', {snapshot_props}, ...
        'summary_fields', {summary_fields}, ...
        'snapshot_semantics', 'global_tick_boundaries_copyFromState', ...
        'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
        'extractor', mfilename ...
    );

    save(out_path, 'states_before', 'states_after', 'metadata', '-v7.3');
    fprintf('[transcription_ensemble] saved: %s\n', out_path);

    file_info = dir(out_path);
    entries(end + 1) = struct( ... %#ok<AGROW>
        'seed', seed, ...
        'path', make_relative_path(out_path, repo_root), ...
        'size_bytes', double(file_info.bytes), ...
        'n_ticks', n_ticks, ...
        'rng_seed', uint32(seed), ...
        'n_observables', numel(all_fields), ...
        'observables', {all_fields}, ...
        'status', 'generated', ...
        'elapsed_seconds', toc(seed_tic) ...
    );
end

write_manifest(output_root, repo_root, seed_vec, n_ticks, entries);
end

function props = pick_transcription_snapshot_properties(proc)
candidates = { ...
    'substrates', ...
    'enzymes', ...
    'boundEnzymes', ...
    'RNAs', ...
};

props = {};
for i = 1:numel(candidates)
    p = candidates{i};
    if ~isprop(proc, p)
        continue;
    end
    try
        val = proc.(p);
    catch
        continue;
    end
    if is_snapshot_value_supported(val)
        props{end + 1} = p; %#ok<AGROW>
    end
end
end

function tf = is_snapshot_value_supported(v)
tf = isnumeric(v) || islogical(v) || ischar(v) || isstring(v) || iscell(v) || isstruct(v);
end

function fields = transcription_summary_field_names()
fields = {};
end

function out = transcription_summary_from_process(proc)
out = struct();
summary_fields = transcription_summary_field_names();
for i = 1:numel(summary_fields)
    out.(summary_fields{i}) = 0;
end
end

function [sim, before_tick, after_tick, before_summary, after_summary] = evolve_state_with_tap_transcription(sim, target_idx, snapshot_props)
before_tick = empty_snapshot_struct(snapshot_props);
after_tick = empty_snapshot_struct(snapshot_props);
before_summary = struct();
after_summary = struct();

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

% Capture boundary snapshot for tick start before any process-local evolve.
target_proc = processes{target_idx};
before_tick = snapshot_from_process(target_proc, snapshot_props);
before_summary = transcription_summary_from_process(target_proc);

rand_stream = [];
if isobject(sim) && ismethod(sim, 'getForTest')
    try
        rand_stream = sim.getForTest('randStream');
    catch
    end
end

while true
    if isempty(rand_stream)
        processEvalOrderIndexs = randperm(nProcesses); %#ok<RANDPERM>
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

    mod.evolveState();

    mod.copyToState();
    mets.counts(gidx) = counts + mod.substrates(lidx, :) - allocation;

    if ~isempty(mod.simulationStateSideEffects)
        mod.simulationStateSideEffects.updateSimulationState(sim);
    end
end

mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    mets.counts, mets.setCounts, time.values);

% Capture boundary snapshot for tick end after all process writes are applied.
target_proc = processes{target_idx};
target_proc.copyFromState();
after_tick = snapshot_from_process(target_proc, snapshot_props);
after_summary = transcription_summary_from_process(target_proc);
end

function out = snapshot_from_process(proc, snapshot_props)
out = struct();
for i = 1:numel(snapshot_props)
    prop = snapshot_props{i};
    out.(prop) = sanitize_snapshot_value(proc.(prop), 0);
end
end

function out = empty_snapshot_struct(snapshot_props)
out = struct();
for i = 1:numel(snapshot_props)
    out.(snapshot_props{i}) = [];
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

function write_manifest(output_root, repo_root, seed_vec, n_ticks, entries)
missing_seeds = setdiff(seed_vec, [entries.seed]);
n_ticks_set = unique([entries.n_ticks]);
all_observables = {};
total_size_bytes = 0;
all_metadata_seed_match = true;

for i = 1:numel(entries)
    total_size_bytes = total_size_bytes + double(entries(i).size_bytes);
    if entries(i).rng_seed ~= uint32(entries(i).seed)
        all_metadata_seed_match = false;
    end
    obs = entries(i).observables;
    for j = 1:numel(obs)
        all_observables{end + 1} = obs{j}; %#ok<AGROW>
    end
end

observable_schema_set = unique(all_observables);

manifest = struct( ...
    'process', 'Transcription', ...
    'seed_range', [min(seed_vec), max(seed_vec)], ...
    'expected_seed_count', numel(seed_vec), ...
    'present_seed_count', numel(entries), ...
    'missing_seeds', missing_seeds, ...
    'all_metadata_seed_match', all_metadata_seed_match, ...
    'n_ticks_set', n_ticks_set, ...
    'observable_schema_set', {observable_schema_set}, ...
    'total_size_bytes', total_size_bytes, ...
    'entries', entries, ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
    'n_ticks_expected', n_ticks ...
);

manifest_path = fullfile(output_root, 'MANIFEST.json');
json_txt = jsonencode(manifest, 'PrettyPrint', true);
fid = fopen(manifest_path, 'w');
if fid < 0
    error('Failed to open manifest path for write: %s', manifest_path);
end
cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, json_txt, 'char');
fprintf('[transcription_ensemble] manifest: %s\n', make_relative_path(manifest_path, repo_root));
end

function rel = make_relative_path(abs_path, repo_root)
prefix = [repo_root filesep];
if strncmpi(abs_path, prefix, numel(prefix))
    rel = abs_path(numel(prefix) + 1:end);
else
    rel = abs_path;
end
rel = strrep(rel, '\', '/');
end
