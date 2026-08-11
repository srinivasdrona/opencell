function extract_macromol_active_window_seeds(seed_start, seed_end, force_seeds)
% extract_macromol_active_window_seeds
% Resumable, source-faithful active-window extraction for
% MacromolecularComplexation's naturally-reachable network-2 branch.
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
% Motivation: the canonical early 100-tick cohort (tick_offset=0) never
% reaches network-2. This driver reuses the real scheduler twice per seed:
%
%   1. free-run `sim.evolveState()` until the FIRST positive delta on either
%      network-2 complex (the two competing pentamers), recording that REAL
%      trigger tick and its triggering complex identity/identities;
%   2. rerun from seed start with extract_per_process_traces_v2(..., 'fixed')
%      and tick_offset = trigger_tick - 1, so the extracted 100-tick window
%      starts exactly at that first real network-2 formation tick.
%
% Output root (process-local, never overwrites the canonical early cohort):
%   data/m1_sources/karr_native/macromol_active_window/
%       per_process_traces_v2/MacromolecularComplexation_100ticks.mat
%       per_process_traces_v2_s001/MacromolecularComplexation_100ticks.mat
%       ...
%
% Resumable and non-destructive:
%   - existing final outputs are skipped ONLY if they structurally validate
%     as active-window traces for the requested seed;
%   - every re-extraction writes to a fresh temp sibling directory first,
%     validates that fresh output, then atomically moves it into place;
%   - a failed or interrupted rerun leaves any prior final file untouched.
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
active_window_rule_version = int32(1);
active_window_detection_mechanism = ['real Simulation.evolveState() scan until first positive delta in ', ...
    'target_proc.complexs on network-2 pentamers'];
stop_reason_success = 'first_network2_positive_delta';

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
            active_window_rule, active_window_rule_version, stop_reason_success);
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

    try
        trigger = macromol_active_window_scan_seed( ...
            repo_root, uint32(s), search_max_ticks, process_name, network2_complex_names);
    catch err
        msg = getReport(err, 'extended', 'hyperlinks', 'off');
        fprintf('[macromol-active] seed %d FAILED during trigger scan: %s\n', s, msg);
        failed_seeds{end + 1} = sprintf('seed %03d scan failed: %s', s, msg); %#ok<AGROW>
        continue;
    end

    if isempty(trigger.trigger_tick)
        reason = sprintf('no network-2 formation found (%s)', trigger.search_stop_reason);
        fprintf('[macromol-active] seed %d FAILED: %s\n', s, reason);
        failed_seeds{end + 1} = sprintf('seed %03d: %s', s, reason); %#ok<AGROW>
        continue;
    end

    tick_offset = double(trigger.trigger_tick) - 1;
    [~, unique_token] = fileparts(tempname());
    tmp_subdir = sprintf('%s__tmp_%s', final_subdir, unique_token);
    tmp_path = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', tmp_subdir, ...
        sprintf('%s_%dticks.mat', process_name, n_ticks));

    try
        extract_per_process_traces_v2({process_name}, tmp_subdir, n_ticks, uint32(s), tick_offset, 'fixed');
        macromol_active_window_attach_metadata( ...
            tmp_path, trigger, search_max_ticks, active_window_rule, active_window_rule_version, ...
            active_window_detection_mechanism, stop_reason_success);
        [tmp_ok, tmp_reason] = macromol_active_window_validate_seed_mat( ...
            tmp_path, s, n_ticks, search_max_ticks, network2_complex_indices_0b, ...
            active_window_rule, active_window_rule_version, stop_reason_success);
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
                s, trigger.trigger_tick, int32(tick_offset), mat2str(trigger.trigger_complex_indices_0b), final_path);
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


function scan = macromol_active_window_scan_seed(repo_root, seed, search_max_ticks, process_name, network2_complex_names)
sim = karr_bootstrap();

target_proc_idx = [];
for i = 1:numel(sim.processes)
    proc_obj = sim.processes{i};
    try
        wid = proc_obj.wholeCellModelID;
        if contains(lower(wid), lower(process_name))
            target_proc_idx = i;
            break;
        end
    catch
    end
end
if isempty(target_proc_idx)
    error('macromol_active_window_scan_seed:process_not_found', 'process not found: %s', process_name);
end

target_proc = sim.processes{target_proc_idx};
e1_idx = find(strcmp(target_proc.substrateWholeCellModelIDs, 'MG_429_MONOMER'), 1);
if isempty(e1_idx)
    error('macromol_active_window_scan_seed:e1_not_found', 'MG_429_MONOMER not found');
end

net2_complex_idx_1b = zeros(1, numel(network2_complex_names));
for c = 1:numel(network2_complex_names)
    idx = find(strcmp(target_proc.complexWholeCellModelIDs, network2_complex_names{c}), 1);
    if isempty(idx)
        error('macromol_active_window_scan_seed:complex_not_found', ...
            'expected network-2 complex %s not found', network2_complex_names{c});
    end
    net2_complex_idx_1b(c) = idx;
end
if numel(unique(net2_complex_idx_1b)) ~= numel(network2_complex_names)
    error('macromol_active_window_scan_seed:complex_indices_not_distinct', ...
        'expected exactly two distinct network-2 complex indices, got %s', mat2str(net2_complex_idx_1b));
end

sim.applyOptions('seed', double(seed));
sim.seedRandStream();

target_proc.copyFromState();
complexs_prev = target_proc.complexs;

first_e1_nonzero_tick = [];
trigger_tick = [];
trigger_complex_indices_0b = [];
search_stop_reason = 'search_max_ticks_exhausted_before_network2';

geom = sim.state('Geometry');

for tick = 1:search_max_ticks
    sim.evolveState();
    target_proc.copyFromState();
    e1_value_this_tick = target_proc.substrates(e1_idx);
    complexs_now = target_proc.complexs;
    d = complexs_now - complexs_prev;
    complexs_prev = complexs_now;

    if e1_value_this_tick > 0 && isempty(first_e1_nonzero_tick)
        first_e1_nonzero_tick = tick;
    end

    net2_deltas = d(net2_complex_idx_1b);
    positive_idx = find(net2_deltas > 0);
    if ~isempty(positive_idx)
        trigger_tick = tick;
        trigger_complex_indices_0b = net2_complex_idx_1b(positive_idx) - 1;
        search_stop_reason = 'first_network2_positive_delta';
        break;
    end

    is_pinched = false;
    try
        is_pinched = geom.pinched;
    catch
    end
    if is_pinched
        search_stop_reason = 'natural_cycle_pinched_before_network2';
        break;
    end
end

scan = struct( ...
    'seed', double(seed), ...
    'first_e1_nonzero_tick', first_e1_nonzero_tick, ...
    'trigger_tick', trigger_tick, ...
    'trigger_complex_indices_0b', trigger_complex_indices_0b, ...
    'search_stop_reason', search_stop_reason);
end


function macromol_active_window_attach_metadata( ...
    mat_path, trigger, search_max_ticks, active_window_rule, active_window_rule_version, ...
    active_window_detection_mechanism, stop_reason_success)
loaded = load(mat_path, 'metadata');
if ~isfield(loaded, 'metadata')
    error('macromol_active_window_attach_metadata:missing_metadata', ...
        'missing metadata variable in %s', mat_path);
end
metadata = loaded.metadata;
metadata.active_window_rule = active_window_rule;
metadata.active_window_rule_version = active_window_rule_version;
metadata.active_window_trigger_tick = int32(trigger.trigger_tick);
metadata.active_window_trigger_complex_indices_0b = int32(trigger.trigger_complex_indices_0b(:)');
metadata.active_window_search_max_ticks = int32(search_max_ticks);
metadata.active_window_search_stop_reason = stop_reason_success;
metadata.active_window_detection_mechanism = active_window_detection_mechanism;
if ~isempty(trigger.first_e1_nonzero_tick)
    metadata.active_window_first_e1_nonzero_tick = int32(trigger.first_e1_nonzero_tick);
end
save(mat_path, 'metadata', '-append');
end


function [ok, reason] = macromol_active_window_validate_seed_mat( ...
    mat_path, expected_seed, expected_n_ticks, expected_search_max_ticks, ...
    expected_network2_complex_indices_0b, expected_rule, expected_rule_version, expected_stop_reason)
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
        'active_window_rule', 'active_window_rule_version', 'active_window_trigger_tick', ...
        'active_window_trigger_complex_indices_0b', 'active_window_search_max_ticks', ...
        'active_window_search_stop_reason', 'active_window_detection_mechanism'};
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

    if ~isfield(states_before, 'complexs') || ~isfield(states_after, 'complexs')
        reason = 'states_before/states_after missing complexs channel';
        return;
    end
    if numel(states_before.complexs) < 1 || numel(states_after.complexs) < 1
        reason = 'complexs channel has no captured ticks';
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
