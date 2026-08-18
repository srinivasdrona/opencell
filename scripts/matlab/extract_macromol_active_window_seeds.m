function extract_macromol_active_window_seeds(seed_start, seed_end, force_seeds)
% extract_macromol_active_window_seeds
% Process-local, same-pass active-window extraction for
% MacromolecularComplexation's naturally reachable network-2 branch.
%
% Authoritative contract (quoted from PROCESS_CATALOG.yaml, not edited here):
%   name: MacromolecularComplexation
%   bucket: ALGORITHMIC_SHALLOW
%   M_ticks: 100
%   N_seeds: 50
%   primary_channel: complexs
%   closed_form_dominant: candidate
%   karr_artifact: per_process_traces_v2
%
% Unlike the legacy scan/rerun implementation, this driver detects the first
% network-2 firing tick and captures the 100-tick window from that SAME
% tapped-scheduler trajectory. There is no second replay pass, so the trigger
% source and the captured first tick cannot drift apart.
%
% Output root (process-local, never overwrites the canonical early cohort):
%   data/m1_sources/karr_native/macromol_active_window/
%       per_process_traces_v2/MacromolecularComplexation_100ticks.mat
%       per_process_traces_v2_s001/MacromolecularComplexation_100ticks.mat
%       ...
%
% Usage:
%   matlab -batch "addpath('scripts/matlab'); extract_macromol_active_window_seeds(0, 49, []);"

if nargin < 1 || isempty(seed_start)
    seed_start = 0;
end
if nargin < 2 || isempty(seed_end)
    seed_end = 49;
end
if nargin < 3 || isempty(force_seeds)
    force_seeds = [];
end

this_file = mfilename('fullpath');
if exist([this_file '.m'], 'file') == 2
    this_file = [this_file '.m'];
end
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

addpath(fullfile(repo_root, 'scripts', 'matlab'));

process_name = 'MacromolecularComplexation';
n_ticks = 100;
search_max_ticks = 33000;
network2_complex_names = {'MG_041_062_429_PENTAMER', 'MG_041_069_429_PENTAMER'};
network2_complex_indices_0b = [22 23];
active_window_rule = 'first_network2_formation_tick';
active_window_rule_version = int32(2);
active_window_detection_mechanism = [ ...
    'same-pass tapped scheduler capture via process-local evolve_state_with_tap; ', ...
    'trigger detection and 100-tick window come from one identical trajectory'];
active_window_capture_mode = 'same_pass_tapped_scheduler_trigger_and_capture';
stop_reason_success = 'first_network2_positive_delta';
static_identity = macromol_static_identity(repo_root, this_file);

fprintf(['[macromol-active] seeds %d..%d process=%s n_ticks=%d search_max_ticks=%d ', ...
    'force_seeds=[%s]\n'], ...
    seed_start, seed_end, process_name, n_ticks, search_max_ticks, ...
    strjoin(arrayfun(@(x) sprintf('%d', x), force_seeds, 'UniformOutput', false), ', '));

failed_seeds = {};

for s = seed_start:seed_end
    seed_token = seed_subdir_token(s);
    final_subdir = fullfile('macromol_active_window', seed_token);
    final_path = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', final_subdir, ...
        sprintf('%s_%dticks.mat', process_name, n_ticks));
    force_this = ismember(s, force_seeds);

    if exist(final_path, 'file') && ~force_this
        [existing_ok, existing_reason] = macromol_active_window_validate_seed_mat( ...
            final_path, s, n_ticks, search_max_ticks, network2_complex_indices_0b, ...
            active_window_rule, active_window_rule_version, stop_reason_success, ...
            active_window_capture_mode, static_identity);
        if existing_ok
            fprintf('[macromol-active] seed %d: existing validated output already present, skipping: %s\n', ...
                s, final_path);
            continue;
        end
        fprintf(['[macromol-active] seed %d: existing output FAILED validation (%s); ', ...
            're-extracting to temp path and replacing only if the fresh output validates.\n'], ...
            s, existing_reason);
    elseif exist(final_path, 'file') && force_this
        fprintf('[macromol-active] seed %d: force_seeds requested, re-extracting despite existing output: %s\n', ...
            s, final_path);
    end

    [~, unique_token] = fileparts(tempname());
    tmp_subdir = sprintf('%s__tmp_%s', final_subdir, unique_token);
    tmp_path = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', tmp_subdir, ...
        sprintf('%s_%dticks.mat', process_name, n_ticks));

    try
        capture = macromol_active_window_capture_seed( ...
            repo_root, uint32(s), search_max_ticks, process_name, network2_complex_names, ...
            n_ticks, active_window_rule, active_window_rule_version, ...
            active_window_detection_mechanism, active_window_capture_mode, ...
            stop_reason_success, static_identity);
        if ~capture.ok
            fprintf('[macromol-active] seed %d FAILED: %s\n', s, capture.error_message);
            failed_seeds{end + 1} = sprintf('seed %03d: %s', s, capture.error_message); %#ok<AGROW>
        else
            macromol_active_window_write_mat(tmp_path, capture.states_before, capture.states_after, capture.metadata);
            [tmp_ok, tmp_reason] = macromol_active_window_validate_seed_mat( ...
                tmp_path, s, n_ticks, search_max_ticks, network2_complex_indices_0b, ...
                active_window_rule, active_window_rule_version, stop_reason_success, ...
                active_window_capture_mode, static_identity);
            if ~tmp_ok
                fprintf('[macromol-active] seed %d FAILED: freshly-extracted output did not validate: %s\n', ...
                    s, tmp_reason);
                failed_seeds{end + 1} = sprintf('seed %03d validation failed: %s', s, tmp_reason); %#ok<AGROW>
            else
                final_dir = fileparts(final_path);
                if ~exist(final_dir, 'dir')
                    mkdir(final_dir);
                end
                movefile(tmp_path, final_path, 'f');
                fprintf(['[macromol-active] seed %d OK: trigger_tick=%d tick_offset=%d ', ...
                    'trigger_complex_indices_0b=%s -> %s\n'], ...
                    s, capture.metadata.active_window_trigger_tick, int32(capture.metadata.tick_offset), ...
                    mat2str(capture.metadata.active_window_trigger_complex_indices_0b), final_path);
            end
        end
    catch err
        msg = getReport(err, 'extended', 'hyperlinks', 'off');
        fprintf('[macromol-active] seed %d FAILED during extraction: %s\n', s, msg);
        failed_seeds{end + 1} = sprintf('seed %03d extraction failed: %s', s, msg); %#ok<AGROW>
    end

    tmp_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', tmp_subdir);
    if exist(tmp_root, 'dir')
        rmdir(tmp_root, 's');
    end
end

if ~isempty(failed_seeds)
    error('extract_macromol_active_window_seeds:extraction_failed', ...
        'extraction failed for %d of %d requested seed(s):\n%s', ...
        numel(failed_seeds), seed_end - seed_start + 1, strjoin(failed_seeds, '\n'));
end
end


function token = seed_subdir_token(seed)
if double(seed) == 0
    token = 'per_process_traces_v2';
else
    token = sprintf('per_process_traces_v2_s%03d', double(seed));
end
end


function identity = macromol_static_identity(repo_root, this_file)
fixture_relpath = fullfile('data', 'karr_fixtures', 'per_process', 'MacromolecularComplexation_flat.mat');
fixture_path = fullfile(repo_root, fixture_relpath);
if exist(fixture_path, 'file') ~= 2
    error('extract_macromol_active_window_seeds:missing_fixture', ...
        'fixture file not found: %s', fixture_path);
end

vendored_relpath = fullfile('data', 'karr_vendored_source', 'MacromolecularComplexation.m');
vendored_path = fullfile(repo_root, vendored_relpath);
if exist(vendored_path, 'file') ~= 2
    error('extract_macromol_active_window_seeds:missing_vendored_source', ...
        'vendored source not found: %s', vendored_path);
end

identity = struct( ...
    'driver_relpath', relative_to_repo_root(this_file, repo_root), ...
    'driver_sha256_lf_normalized', sha256_lf_normalized(this_file), ...
    'fixture_relpath', relative_to_repo_root(fixture_path, repo_root), ...
    'fixture_sha256', sha256_file(fixture_path), ...
    'vendored_source_relpath', relative_to_repo_root(vendored_path, repo_root), ...
    'vendored_source_sha256_lf_normalized', sha256_lf_normalized(vendored_path));
end


function rel = relative_to_repo_root(path_value, repo_root)
prefix = [repo_root filesep];
if ~strncmpi(path_value, prefix, numel(prefix))
    rel = path_value;
else
    rel = path_value(numel(prefix) + 1:end);
end
rel = strrep(rel, filesep, '/');
end


function capture = macromol_active_window_capture_seed( ...
    repo_root, seed, search_max_ticks, process_name, network2_complex_names, n_ticks, ...
    active_window_rule, active_window_rule_version, active_window_detection_mechanism, ...
    active_window_capture_mode, stop_reason_success, static_identity)
ensure_wholecell_runtime_paths(repo_root);
[sim, mnrnd_provider] = karr_bootstrap();

[target_idx, canonical_name] = find_process_index(sim, process_name);
if isempty(target_idx)
    error('macromol_active_window_capture_seed:process_not_found', 'process not found: %s', process_name);
end

target_proc = sim.processes{target_idx};
snapshot_props = macromol_pick_snapshot_properties(target_proc);
seed_simulation(sim, seed);

e1_idx = find(strcmp(target_proc.substrateWholeCellModelIDs, 'MG_429_MONOMER'), 1);
if isempty(e1_idx)
    error('macromol_active_window_capture_seed:e1_not_found', 'MG_429_MONOMER not found');
end

net2_complex_idx_1b = zeros(1, numel(network2_complex_names));
for c = 1:numel(network2_complex_names)
    idx = find(strcmp(target_proc.complexWholeCellModelIDs, network2_complex_names{c}), 1);
    if isempty(idx)
        error('macromol_active_window_capture_seed:complex_not_found', ...
            'expected network-2 complex %s not found', network2_complex_names{c});
    end
    net2_complex_idx_1b(c) = idx;
end
if numel(unique(net2_complex_idx_1b)) ~= numel(network2_complex_names)
    error('macromol_active_window_capture_seed:complex_indices_not_distinct', ...
        'expected exactly two distinct network-2 complex indices, got %s', mat2str(net2_complex_idx_1b));
end

states_before = struct('substrates', {cell(n_ticks, 1)}, 'complexs', {cell(n_ticks, 1)});
states_after = struct('substrates', {cell(n_ticks, 1)}, 'complexs', {cell(n_ticks, 1)});

trigger_tick = [];
trigger_complex_indices_0b = [];
first_e1_nonzero_tick = [];
search_stop_reason = 'search_max_ticks_exhausted_before_network2';
captured_ticks = 0;

geom = sim.state('Geometry');

for tick = 1:search_max_ticks
    [sim, before_tick, after_tick] = macromol_evolve_state_with_tap(sim, target_idx, snapshot_props);

    if double(after_tick.substrates(e1_idx)) > 0 && isempty(first_e1_nonzero_tick)
        first_e1_nonzero_tick = tick;
    end

    first_delta = double(after_tick.complexs) - double(before_tick.complexs);
    net2_deltas = first_delta(net2_complex_idx_1b);
    positive_idx = find(net2_deltas > 0);

    if isempty(trigger_tick)
        if ~isempty(positive_idx)
            trigger_tick = tick;
            trigger_complex_indices_0b = net2_complex_idx_1b(positive_idx) - 1;
            search_stop_reason = stop_reason_success;
        else
            is_pinched = false;
            try
                is_pinched = geom.pinched;
            catch
            end
            if is_pinched
                search_stop_reason = 'natural_cycle_pinched_before_network2';
                break;
            end
            continue;
        end
    end

    captured_ticks = captured_ticks + 1;
    states_before.substrates{captured_ticks, 1} = before_tick.substrates;
    states_after.substrates{captured_ticks, 1} = after_tick.substrates;
    states_before.complexs{captured_ticks, 1} = before_tick.complexs;
    states_after.complexs{captured_ticks, 1} = after_tick.complexs;
    if captured_ticks == n_ticks
        break;
    end
end

if isempty(trigger_tick)
    capture = struct( ...
        'ok', false, ...
        'error_message', sprintf('no network-2 formation found (%s)', search_stop_reason), ...
        'states_before', states_before, ...
        'states_after', states_after, ...
        'metadata', struct());
    return;
end

if captured_ticks ~= n_ticks
    capture = struct( ...
        'ok', false, ...
        'error_message', sprintf( ...
            'trigger tick %d found but only %d/%d ticks could be captured from the same trajectory before search stop', ...
            trigger_tick, captured_ticks, n_ticks), ...
        'states_before', states_before, ...
        'states_after', states_after, ...
        'metadata', struct());
    return;
end

metadata = struct( ...
    'process_name', canonical_name, ...
    'n_ticks', n_ticks, ...
    'rng_seed', seed, ...
    'tick_offset', int32(trigger_tick - 1), ...
    'tick_start', int32(trigger_tick), ...
    'tick_end', int32(trigger_tick + n_ticks - 1), ...
    'stride', int32(1), ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
    'mnrnd_provider_kind', mnrnd_provider.kind, ...
    'mnrnd_provider_matlab_release', mnrnd_provider.matlab_release, ...
    'mnrnd_provider_toolbox_version', mnrnd_provider.toolbox_version, ...
    'mnrnd_provider_path_relative_to_matlabroot', mnrnd_provider.provider_path_relative_to_matlabroot, ...
    'mnrnd_provider_sha256', mnrnd_provider.sha256_lf_normalized, ...
    'statistics_rng_provider_identity_json', mnrnd_provider.identity_json, ...
    'active_window_rule', active_window_rule, ...
    'active_window_rule_version', active_window_rule_version, ...
    'active_window_trigger_tick', int32(trigger_tick), ...
    'active_window_trigger_complex_indices_0b', int32(trigger_complex_indices_0b(:)'), ...
    'active_window_search_max_ticks', int32(search_max_ticks), ...
    'active_window_search_stop_reason', search_stop_reason, ...
    'active_window_detection_mechanism', active_window_detection_mechanism, ...
    'active_window_capture_mode', active_window_capture_mode, ...
    'active_window_driver_relpath', static_identity.driver_relpath, ...
    'active_window_driver_sha256_lf_normalized', static_identity.driver_sha256_lf_normalized, ...
    'active_window_fixture_relpath', static_identity.fixture_relpath, ...
    'active_window_fixture_sha256', static_identity.fixture_sha256, ...
    'active_window_vendored_source_relpath', static_identity.vendored_source_relpath, ...
    'active_window_vendored_source_sha256_lf_normalized', static_identity.vendored_source_sha256_lf_normalized);
metadata.snapshot_properties = {'substrates', 'complexs'};
if ~isempty(first_e1_nonzero_tick)
    metadata.active_window_first_e1_nonzero_tick = int32(first_e1_nonzero_tick);
end

capture = struct( ...
    'ok', true, ...
    'error_message', '', ...
    'states_before', states_before, ...
    'states_after', states_after, ...
    'metadata', metadata);
end


function macromol_active_window_write_mat(mat_path, states_before, states_after, metadata)
out_dir = fileparts(mat_path);
if ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
save(mat_path, 'states_before', 'states_after', 'metadata', '-v7.3');
end


function props = macromol_pick_snapshot_properties(proc)
props = intersect(properties(proc), {'substrates', 'complexs'});
end


function [sim, before_tick, after_tick] = macromol_evolve_state_with_tap(sim, target_idx, snapshot_props)
before_tick = struct();
after_tick = struct();

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


function [ok, reason] = macromol_active_window_validate_seed_mat( ...
    mat_path, expected_seed, expected_n_ticks, expected_search_max_ticks, ...
    expected_network2_complex_indices_0b, expected_rule, expected_rule_version, ...
    expected_stop_reason, expected_capture_mode, static_identity)
ok = false;
reason = '';

if ~exist(mat_path, 'file')
    reason = 'file does not exist';
    return;
end

try
    info = whos('-file', mat_path);
    varnames = {info.name};
    required = {'states_before', 'states_after', 'metadata'};
    missing = setdiff(required, varnames);
    if ~isempty(missing)
        reason = sprintf('missing required variable(s): %s', strjoin(missing, ', '));
        return;
    end

    loaded = load(mat_path, 'states_before', 'states_after', 'metadata');
    metadata = loaded.metadata;
    states_before = loaded.states_before;
    states_after = loaded.states_after;

    required_fields = { ...
        'process_name', 'n_ticks', 'rng_seed', 'tick_offset', 'tick_start', 'tick_end', 'stride', ...
        'mnrnd_provider_kind', 'mnrnd_provider_matlab_release', 'mnrnd_provider_toolbox_version', ...
        'mnrnd_provider_path_relative_to_matlabroot', 'mnrnd_provider_sha256', ...
        'statistics_rng_provider_identity_json', ...
        'active_window_rule', 'active_window_rule_version', 'active_window_trigger_tick', ...
        'active_window_trigger_complex_indices_0b', 'active_window_search_max_ticks', ...
        'active_window_search_stop_reason', 'active_window_detection_mechanism', ...
        'active_window_capture_mode', 'active_window_driver_relpath', ...
        'active_window_driver_sha256_lf_normalized', 'active_window_fixture_relpath', ...
        'active_window_fixture_sha256', 'active_window_vendored_source_relpath', ...
        'active_window_vendored_source_sha256_lf_normalized'};
    for i = 1:numel(required_fields)
        if ~isfield(metadata, required_fields{i})
            reason = sprintf('missing required metadata field %s', required_fields{i});
            return;
        end
    end

    if ~strcmp(metadata.process_name, 'MacromolecularComplexation')
        reason = sprintf('metadata.process_name=%s', metadata.process_name);
        return;
    end
    if double(metadata.rng_seed) ~= double(expected_seed)
        reason = sprintf('metadata.rng_seed=%d != expected seed %d', double(metadata.rng_seed), double(expected_seed));
        return;
    end
    if double(metadata.n_ticks) ~= double(expected_n_ticks)
        reason = sprintf('metadata.n_ticks=%d != expected %d', double(metadata.n_ticks), double(expected_n_ticks));
        return;
    end
    if ~strcmp(metadata.active_window_rule, expected_rule)
        reason = sprintf('metadata.active_window_rule=%s != %s', metadata.active_window_rule, expected_rule);
        return;
    end
    if double(metadata.active_window_rule_version) ~= double(expected_rule_version)
        reason = sprintf('metadata.active_window_rule_version=%d != expected %d', ...
            double(metadata.active_window_rule_version), double(expected_rule_version));
        return;
    end
    if double(metadata.active_window_search_max_ticks) ~= double(expected_search_max_ticks)
        reason = sprintf('metadata.active_window_search_max_ticks=%d != expected %d', ...
            double(metadata.active_window_search_max_ticks), double(expected_search_max_ticks));
        return;
    end
    if ~strcmp(metadata.active_window_search_stop_reason, expected_stop_reason)
        reason = sprintf('metadata.active_window_search_stop_reason=%s != %s', ...
            metadata.active_window_search_stop_reason, expected_stop_reason);
        return;
    end
    if ~strcmp(metadata.active_window_capture_mode, expected_capture_mode)
        reason = sprintf('metadata.active_window_capture_mode=%s != %s', ...
            metadata.active_window_capture_mode, expected_capture_mode);
        return;
    end
    if ~strcmp(metadata.mnrnd_provider_kind, 'statistics_toolbox')
        reason = sprintf('mnrnd_provider_kind=%s != statistics_toolbox', metadata.mnrnd_provider_kind);
        return;
    end
    if ~strcmp(metadata.active_window_driver_relpath, static_identity.driver_relpath)
        reason = sprintf('driver_relpath=%s != %s', metadata.active_window_driver_relpath, static_identity.driver_relpath);
        return;
    end
    if ~strcmp(metadata.active_window_driver_sha256_lf_normalized, static_identity.driver_sha256_lf_normalized)
        reason = 'driver hash mismatch';
        return;
    end
    if ~strcmp(metadata.active_window_fixture_relpath, static_identity.fixture_relpath)
        reason = sprintf('fixture_relpath=%s != %s', metadata.active_window_fixture_relpath, static_identity.fixture_relpath);
        return;
    end
    if ~strcmp(metadata.active_window_fixture_sha256, static_identity.fixture_sha256)
        reason = 'fixture hash mismatch';
        return;
    end
    if ~strcmp(metadata.active_window_vendored_source_relpath, static_identity.vendored_source_relpath)
        reason = sprintf('vendored_source_relpath=%s != %s', ...
            metadata.active_window_vendored_source_relpath, static_identity.vendored_source_relpath);
        return;
    end
    if ~strcmp(metadata.active_window_vendored_source_sha256_lf_normalized, static_identity.vendored_source_sha256_lf_normalized)
        reason = 'vendored source hash mismatch';
        return;
    end

    tick_offset = double(metadata.tick_offset);
    tick_start = double(metadata.tick_start);
    tick_end = double(metadata.tick_end);
    trigger_tick = double(metadata.active_window_trigger_tick);
    if double(metadata.stride) ~= 1
        reason = sprintf('metadata.stride=%d != 1', double(metadata.stride));
        return;
    end
    if tick_start ~= tick_offset + 1
        reason = sprintf('tick_start=%d != tick_offset + 1 (%d)', tick_start, tick_offset + 1);
        return;
    end
    if tick_end - tick_start + 1 ~= double(expected_n_ticks)
        reason = sprintf('window span=%d != expected n_ticks=%d', tick_end - tick_start + 1, double(expected_n_ticks));
        return;
    end
    if trigger_tick ~= tick_start
        reason = sprintf('active_window_trigger_tick=%d != tick_start=%d', trigger_tick, tick_start);
        return;
    end

    trigger_complex_indices_0b = double(metadata.active_window_trigger_complex_indices_0b(:)');
    if isempty(trigger_complex_indices_0b)
        reason = 'active_window_trigger_complex_indices_0b is empty';
        return;
    end
    if any(~ismember(trigger_complex_indices_0b, double(expected_network2_complex_indices_0b)))
        reason = sprintf('trigger indices %s include non-network2 members', mat2str(trigger_complex_indices_0b));
        return;
    end

    if isfield(metadata, 'active_window_first_e1_nonzero_tick')
        if double(metadata.active_window_first_e1_nonzero_tick) > trigger_tick
            reason = sprintf('first E1 nonzero tick %d occurs after trigger tick %d', ...
                double(metadata.active_window_first_e1_nonzero_tick), trigger_tick);
            return;
        end
    end

    if ~isfield(states_before, 'substrates') || ~isfield(states_after, 'substrates')
        reason = 'states_before/states_after missing substrates channel';
        return;
    end
    if ~isfield(states_before, 'complexs') || ~isfield(states_after, 'complexs')
        reason = 'states_before/states_after missing complexs channel';
        return;
    end
    if numel(states_before.complexs) ~= expected_n_ticks || numel(states_after.complexs) ~= expected_n_ticks
        reason = 'complexs channel does not contain the full n_ticks capture';
        return;
    end

    first_delta = double(states_after.complexs{1}) - double(states_before.complexs{1});
    positive_network2 = find(first_delta > 0) - 1;
    positive_network2 = positive_network2(ismember(positive_network2, double(expected_network2_complex_indices_0b)));
    if isempty(positive_network2)
        reason = 'first captured tick has no positive network-2 complex delta';
        return;
    end
    if ~isequal(positive_network2(:)', trigger_complex_indices_0b(:)')
        reason = sprintf('metadata trigger indices %s != first delta positive indices %s', ...
            mat2str(trigger_complex_indices_0b), mat2str(positive_network2));
        return;
    end
catch err
    reason = sprintf('file failed validation: %s', err.message);
    return;
end

ok = true;
end


function hash_hex = sha256_lf_normalized(path_value)
fid = fopen(path_value, 'rb');
if fid < 0
    error('extract_macromol_active_window_seeds:hash_unreadable', ...
        'could not open %s to compute LF-normalized SHA-256', path_value);
end
raw = fread(fid, Inf, '*uint8')';
fclose(fid);
raw = raw(raw ~= uint8(13));
digest = java.security.MessageDigest.getInstance('SHA-256');
digest_bytes = typecast(digest.digest(raw), 'uint8');
hash_hex = lower(sprintf('%02x', digest_bytes));
end


function hash_hex = sha256_file(path_value)
fid = fopen(path_value, 'rb');
if fid < 0
    error('extract_macromol_active_window_seeds:hash_unreadable', ...
        'could not open %s to compute SHA-256', path_value);
end
cleaner = onCleanup(@() fclose(fid));
md = java.security.MessageDigest.getInstance('SHA-256');
while true
    chunk = fread(fid, 1024 * 1024, '*uint8');
    if isempty(chunk)
        break;
    end
    md.update(chunk);
end
digest_bytes = typecast(md.digest(), 'uint8');
hash_hex = lower(sprintf('%02x', digest_bytes));
end
