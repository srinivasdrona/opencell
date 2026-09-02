function extract_ppii_active_window_seeds(seed_start, seed_end, force_seeds)
% extract_ppii_active_window_seeds
% Resumable, source-faithful extraction of the first regime-valid transferase
% window on the genuine-provider trajectory for each requested seed.
%
% Contract:
%   1. scan the REAL full simulation from cell birth until the FIRST tick whose
%      pre-tick process-local state satisfies the same
%      regime_valid && transferase_demand>0 guard the shared H12 predictor uses;
%   2. rerun extract_per_process_traces_v2(..., 'fixed') with
%      tick_offset = trigger_tick - 1 so the captured 20-tick window begins
%      exactly at that first real transferase-capable tick; and
%   3. attach tracked metadata proving which active-window rule, search bound,
%      driver revision, and genuine Statistics Toolbox provider produced the MAT.
%
% Output root:
%   data/m1_sources/karr_native/ppii_active_window/
%       per_process_traces_v2/ProteinProcessingII_20ticks.mat
%       per_process_traces_v2_s001/ProteinProcessingII_20ticks.mat
%       ...
%
% Usage:
%   matlab -batch "addpath('scripts/matlab'); extract_ppii_active_window_seeds(0,49,[]);"

if nargin < 1 || isempty(seed_start)
    seed_start = 0;
end
if nargin < 2 || isempty(seed_end)
    seed_end = 49;
end
if nargin < 3 || isempty(force_seeds)
    force_seeds = [];
end

this_file = [mfilename('fullpath') '.m'];
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

addpath(fullfile(repo_root, 'scripts', 'matlab'));
ensure_wholecell_runtime_paths(repo_root);

process_name = 'ProteinProcessingII';
n_ticks = 20;
search_max_ticks = 20000;
active_window_rule = 'first_regime_valid_transferase_tick';
active_window_rule_version = int32(1);
active_window_detection_mechanism = [ ...
    'real Simulation.evolveState() scan with pre-tick copyFromState() evaluation of ', ...
    'regime_valid && transferase_demand>0 from ProteinProcessingII.m/H12'];
stop_reason_success = 'first_regime_valid_transferase_tick';

fprintf(['[ppii-active] seeds %d..%d process=%s n_ticks=%d search_max_ticks=%d ', ...
    'force_seeds=[%s]\n'], ...
    seed_start, seed_end, process_name, n_ticks, search_max_ticks, ...
    strjoin(arrayfun(@(x) sprintf('%d', x), force_seeds, 'UniformOutput', false), ', '));

failed_seeds = {};

for s = seed_start:seed_end
    seed_token = seed_subdir_token(s);
    final_subdir = fullfile('ppii_active_window', seed_token);
    final_path = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', final_subdir, ...
        sprintf('%s_%dticks.mat', process_name, n_ticks));
    force_this = ismember(s, force_seeds);

    if exist(final_path, 'file') && ~force_this
        [existing_ok, existing_reason] = ppii_active_window_validate_seed_mat( ...
            final_path, s, n_ticks, search_max_ticks, active_window_rule, active_window_rule_version, ...
            stop_reason_success, this_file);
        if existing_ok
            fprintf('[ppii-active] seed %d: existing validated output already present, skipping: %s\n', ...
                s, final_path);
            continue;
        end
        fprintf(['[ppii-active] seed %d: existing output FAILED validation (%s); ', ...
            're-extracting to temp path and replacing only if the fresh output validates.\n'], ...
            s, existing_reason);
    elseif exist(final_path, 'file') && force_this
        fprintf('[ppii-active] seed %d: force_seeds requested, re-extracting despite existing output: %s\n', ...
            s, final_path);
    end

    try
        trigger = ppii_active_window_scan_seed(uint32(s), search_max_ticks, process_name, stop_reason_success);
    catch err
        msg = getReport(err, 'extended', 'hyperlinks', 'off');
        fprintf('[ppii-active] seed %d FAILED during trigger scan: %s\n', s, msg);
        failed_seeds{end + 1} = sprintf('seed %03d scan failed: %s', s, msg); %#ok<AGROW>
        continue;
    end

    if isempty(trigger.trigger_tick)
        reason = sprintf('no transferase-capable tick found (%s)', trigger.search_stop_reason);
        fprintf('[ppii-active] seed %d FAILED: %s\n', s, reason);
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
        ppii_active_window_attach_metadata( ...
            tmp_path, trigger, search_max_ticks, active_window_rule, active_window_rule_version, ...
            active_window_detection_mechanism, stop_reason_success, this_file);
        [tmp_ok, tmp_reason] = ppii_active_window_validate_seed_mat( ...
            tmp_path, s, n_ticks, search_max_ticks, active_window_rule, active_window_rule_version, ...
            stop_reason_success, this_file);
        if ~tmp_ok
            fprintf('[ppii-active] seed %d FAILED: freshly-extracted output did not validate: %s\n', ...
                s, tmp_reason);
            failed_seeds{end + 1} = sprintf('seed %03d validation failed: %s', s, tmp_reason); %#ok<AGROW>
        else
            final_dir = fileparts(final_path);
            if ~exist(final_dir, 'dir')
                mkdir(final_dir);
            end
            movefile(tmp_path, final_path, 'f');
            fprintf('[ppii-active] seed %d OK: trigger_tick=%d tick_offset=%d -> %s\n', ...
                s, trigger.trigger_tick, int32(tick_offset), final_path);
        end
    catch err
        msg = getReport(err, 'extended', 'hyperlinks', 'off');
        fprintf('[ppii-active] seed %d FAILED during extraction: %s\n', s, msg);
        failed_seeds{end + 1} = sprintf('seed %03d extraction failed: %s', s, msg); %#ok<AGROW>
    end

    tmp_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', tmp_subdir);
    if exist(tmp_root, 'dir')
        rmdir(tmp_root, 's');
    end
end

if ~isempty(failed_seeds)
    error('extract_ppii_active_window_seeds:extraction_failed', ...
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


function scan = ppii_active_window_scan_seed(seed, search_max_ticks, process_name, stop_reason_success)
sim = karr_bootstrap();

target_proc_idx = [];
want = normalize_name_token(process_name);
for i = 1:numel(sim.processes)
    proc_obj = sim.processes{i};
    try
        short = process_short_name(proc_obj);
        tokens = { ...
            normalize_name_token(short), ...
            normalize_name_token(proc_obj.wholeCellModelID) ...
        };
        if isprop(proc_obj, 'name')
            tokens{end + 1} = normalize_name_token(proc_obj.name); %#ok<AGROW>
        end
        if any(strcmp(tokens, want))
            target_proc_idx = i;
            break;
        end
    catch
    end
end
if isempty(target_proc_idx)
    error('ppii_active_window_scan_seed:process_not_found', 'process not found: %s', process_name);
end

target_proc = sim.processes{target_proc_idx};
sim.applyOptions('seed', double(seed));
sim.seedRandStream();

geom = sim.state('Geometry');
trigger_tick = [];
search_stop_reason = 'search_max_ticks_exhausted_before_transferase_tick';
trigger_snapshot = struct();

for tick = 1:search_max_ticks
    target_proc.copyFromState();
    [regime_valid, transferase_demand, peptidase_demand] = ppii_pre_tick_transferase_ready(target_proc);
    if regime_valid && transferase_demand > 0
        trigger_tick = tick;
        search_stop_reason = stop_reason_success;
        trigger_snapshot = struct( ...
            'transferase_demand', transferase_demand, ...
            'peptidase_demand', peptidase_demand ...
        );
        break;
    end

    sim.evolveState();
    is_pinched = false;
    try
        is_pinched = geom.pinched;
    catch
    end
    if is_pinched
        search_stop_reason = 'natural_cycle_pinched_before_transferase_tick';
        break;
    end
end

scan = struct( ...
    'seed', double(seed), ...
    'trigger_tick', trigger_tick, ...
    'search_stop_reason', search_stop_reason, ...
    'trigger_snapshot', trigger_snapshot);
end


function [regime_valid, transferase_demand, peptidase_demand] = ppii_pre_tick_transferase_ready(proc)
peptidase_idx = [proc.lipoproteinMonomerIndexs; proc.secretedMonomerIndexs];
transferase_idx = proc.lipoproteinMonomerIndexs;

unproc = double(proc.unprocessedMonomers(:));
enz = double(proc.enzymes(:));
substrates = double(proc.substrates(:));

peptidase_demand = sum(unproc(peptidase_idx));
transferase_demand = sum(unproc(transferase_idx));
peptidase_limit = enz(proc.enzymeIndexs_signalPeptidase) * ...
    double(proc.lipoproteinSignalPeptidaseSpecificRate) * ...
    double(proc.stepSizeSec);
transferase_limit = enz(proc.enzymeIndexs_diacylglycerylTransferase) * ...
    double(proc.lipoproteinDiacylglycerylTransferaseSpecificRate) * ...
    double(proc.stepSizeSec);
water = substrates(proc.substrateIndexs_water);
pg160 = substrates(proc.substrateIndexs_PG160);

regime_valid = peptidase_limit >= peptidase_demand && ...
    (transferase_demand == 0 || transferase_limit >= transferase_demand) && ...
    water >= peptidase_demand && ...
    (transferase_demand == 0 || pg160 >= transferase_demand);
end


function ppii_active_window_attach_metadata( ...
    mat_path, trigger, search_max_ticks, active_window_rule, active_window_rule_version, ...
    active_window_detection_mechanism, stop_reason_success, driver_path)
loaded = load(mat_path, 'metadata');
if ~isfield(loaded, 'metadata')
    error('ppii_active_window_attach_metadata:missing_metadata', ...
        'missing metadata variable in %s', mat_path);
end
metadata = loaded.metadata;
metadata.active_window_rule = active_window_rule;
metadata.active_window_rule_version = active_window_rule_version;
metadata.active_window_trigger_tick = int32(trigger.trigger_tick);
metadata.active_window_search_max_ticks = int32(search_max_ticks);
metadata.active_window_search_stop_reason = stop_reason_success;
metadata.active_window_detection_mechanism = active_window_detection_mechanism;
metadata.active_window_driver_path = relative_to_repo_root(driver_path);
metadata.active_window_driver_sha256 = sha256_lf_normalized(driver_path);
if isfield(trigger, 'trigger_snapshot') && isfield(trigger.trigger_snapshot, 'transferase_demand')
    metadata.active_window_trigger_transferase_demand = double(trigger.trigger_snapshot.transferase_demand);
end
if isfield(trigger, 'trigger_snapshot') && isfield(trigger.trigger_snapshot, 'peptidase_demand')
    metadata.active_window_trigger_peptidase_demand = double(trigger.trigger_snapshot.peptidase_demand);
end
save(mat_path, 'metadata', '-append');
end


function [ok, reason] = ppii_active_window_validate_seed_mat( ...
    mat_path, expected_seed, expected_n_ticks, expected_search_max_ticks, ...
    expected_rule, expected_rule_version, expected_stop_reason, driver_path)
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

    loaded = load(mat_path, 'metadata');
    metadata = loaded.metadata;
    required_fields = { ...
        'process_name', 'n_ticks', 'rng_seed', 'tick_offset', 'tick_start', 'tick_end', 'stride', ...
        'active_window_rule', 'active_window_rule_version', 'active_window_trigger_tick', ...
        'active_window_search_max_ticks', 'active_window_search_stop_reason', ...
        'active_window_detection_mechanism', 'active_window_driver_path', 'active_window_driver_sha256', ...
        'mnrnd_provider_kind', 'mnrnd_provider_matlab_release', 'mnrnd_provider_toolbox_version', ...
        'mnrnd_provider_path_relative_to_matlabroot', 'mnrnd_provider_sha256', ...
        'statistics_rng_provider_identity_json'};
    for i = 1:numel(required_fields)
        if ~isfield(metadata, required_fields{i})
            reason = sprintf('metadata missing required field %s', required_fields{i});
            return;
        end
    end

    if ~strcmp(metadata.process_name, 'ProteinProcessingII')
        reason = sprintf('metadata.process_name=%s != ProteinProcessingII', metadata.process_name);
        return;
    end
    if double(metadata.rng_seed) ~= double(expected_seed)
        reason = sprintf('metadata.rng_seed=%d != expected %d', double(metadata.rng_seed), double(expected_seed));
        return;
    end
    if double(metadata.n_ticks) ~= double(expected_n_ticks)
        reason = sprintf('metadata.n_ticks=%d != expected %d', double(metadata.n_ticks), double(expected_n_ticks));
        return;
    end
    if double(metadata.stride) ~= 1
        reason = sprintf('metadata.stride=%d != 1', double(metadata.stride));
        return;
    end
    if double(metadata.tick_start) ~= double(metadata.tick_offset) + 1
        reason = sprintf('metadata.tick_start=%d != tick_offset+1 (%d)', ...
            double(metadata.tick_start), double(metadata.tick_offset) + 1);
        return;
    end
    if double(metadata.tick_end) - double(metadata.tick_start) + 1 ~= double(expected_n_ticks)
        reason = sprintf('tick span=%d != expected_n_ticks=%d', ...
            double(metadata.tick_end) - double(metadata.tick_start) + 1, double(expected_n_ticks));
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
    if double(metadata.active_window_trigger_tick) ~= double(metadata.tick_start)
        reason = sprintf('metadata.active_window_trigger_tick=%d != tick_start=%d', ...
            double(metadata.active_window_trigger_tick), double(metadata.tick_start));
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
    if ~strcmp(metadata.active_window_driver_path, relative_to_repo_root(driver_path))
        reason = sprintf('metadata.active_window_driver_path=%s != expected %s', ...
            metadata.active_window_driver_path, relative_to_repo_root(driver_path));
        return;
    end
    if ~strcmp(metadata.active_window_driver_sha256, sha256_lf_normalized(driver_path))
        reason = sprintf('metadata.active_window_driver_sha256=%s != current driver hash', ...
            metadata.active_window_driver_sha256);
        return;
    end

    ok = true;
catch err
    reason = getReport(err, 'basic', 'hyperlinks', 'off');
end
end


function rel = relative_to_repo_root(path_value)
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
prefix = [repo_root filesep];
if strncmpi(path_value, prefix, numel(prefix))
    rel = path_value(numel(prefix) + 1:end);
else
    rel = path_value;
end
rel = strrep(rel, filesep, '/');
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


function hash_hex = sha256_lf_normalized(path_value)
fid = fopen(path_value, 'rb');
if fid < 0
    error('extract_ppii_active_window_seeds:hash_unreadable', 'could not open %s', path_value);
end
raw = fread(fid, Inf, '*uint8')';
fclose(fid);
raw = raw(raw ~= uint8(13));
digest = java.security.MessageDigest.getInstance('SHA-256');
digest_bytes = typecast(digest.digest(raw), 'uint8');
hash_hex = lower(sprintf('%02x', digest_bytes));
end
