function extract_per_process_traces_fix(n_ticks)
% extract_per_process_traces_fix
% Re-extract the five truncated per-process traces with a dedicated path.
%
% Targets:
%   Transcription, Translation, RNADecay, Replication, ReplicationInitiation
%
% Output:
%   data/m1_sources/karr_native/per_process_traces/<Process>_100ticks.mat
%   (plain -v7 MAT, states_before/states_after/metadata)

if nargin < 1 || isempty(n_ticks)
    n_ticks = 100;
end

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

process_names = { ...
    'Transcription', ...
    'Translation', ...
    'RNADecay', ...
    'Replication', ...
    'ReplicationInitiation', ...
};

out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'per_process_traces');
if ~exist(out_root, 'dir')
    mkdir(out_root);
end

fprintf('[trace_fix] repo root: %s\n', repo_root);
fprintf('[trace_fix] output dir: %s\n', out_root);

sim_source = detect_simulation_source(repo_root);
fprintf('[trace_fix] simulation source kind: %s\n', sim_source.kind);
fprintf('[trace_fix] simulation source path: %s\n', sim_source.path);

for i = 1:numel(process_names)
    pname = process_names{i};
    out_path = fullfile(out_root, sprintf('%s_%dticks.mat', pname, n_ticks));
    fprintf('\n[trace_fix] === %s ===\n', pname);

    try
        sim = load_simulation(sim_source);
    catch sim_err
        fprintf('[trace_fix] ERROR loading simulation for %s: %s\n', pname, sim_err.message);
        continue;
    end

    proc = find_process(sim, pname);
    if isempty(proc)
        fprintf('[trace_fix] ERROR process not found: %s\n', pname);
        continue;
    end

    snapshot_props = pick_snapshot_properties(proc, pname);
    if isempty(snapshot_props)
        fprintf('[trace_fix] ERROR no numeric snapshot properties for %s\n', pname);
        continue;
    end
    fprintf('[trace_fix] snapshot properties: %s\n', strjoin(snapshot_props, ', '));

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
            invoke_if_exists(proc, 'copyFromState');
        catch err
            ok = false;
            error_message = sprintf('copyFromState failed at tick %d: %s', t, err.message);
            break;
        end

        for p = 1:numel(snapshot_props)
            prop = snapshot_props{p};
            try
                states_before.(prop){t, 1} = sanitize_snapshot_value(proc.(prop), 0);
            catch err
                ok = false;
                error_message = sprintf('before snapshot failed [%s] tick %d: %s', prop, t, err.message);
                break;
            end
        end
        if ~ok
            break;
        end

        [step_ok, step_err] = evolve_once(proc);
        if ~step_ok
            ok = false;
            error_message = sprintf('evolveState failed at tick %d: %s', t, step_err);
            break;
        end

        for p = 1:numel(snapshot_props)
            prop = snapshot_props{p};
            try
                states_after.(prop){t, 1} = sanitize_snapshot_value(proc.(prop), 0);
            catch err
                ok = false;
                error_message = sprintf('after snapshot failed [%s] tick %d: %s', prop, t, err.message);
                break;
            end
        end
        if ~ok
            break;
        end

        try
            invoke_if_exists(proc, 'copyToState');
        catch err
            ok = false;
            error_message = sprintf('copyToState failed at tick %d: %s', t, err.message);
            break;
        end
    end

    if ~ok
        fprintf('[trace_fix] ERROR %s\n', error_message);
        fprintf('[trace_fix] skipped write (keeping existing file untouched): %s\n', out_path);
        continue;
    end

    metadata = struct( ...
        'process_name', pname, ...
        'n_ticks', n_ticks, ...
        'rng_seed', uint32(0), ...
        'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
        'snapshot_properties', {snapshot_props}, ...
        'source_kind', sim_source.kind, ...
        'source_path', sim_source.path, ...
        'extractor', mfilename ...
    );

    save(out_path, 'states_before', 'states_after', 'metadata', '-v7');
    fprintf('[trace_fix] wrote: %s\n', out_path);
end

fprintf('\n[trace_fix] DONE\n');
end

function sim_source = detect_simulation_source(repo_root)
wholecell_roots = { ...
    fullfile(repo_root, '_tmp_WholeCell'), ...
    fullfile(repo_root, 'data', 'm1_sources', 'WholeCell'), ...
    'E:\opencell\_tmp_WholeCell', ...
    'E:\opencell\data\m1_sources\WholeCell', ...
};

for i = 1:numel(wholecell_roots)
    root = wholecell_roots{i};
    fitted = fullfile(root, 'data', 'Simulation_fitted.mat');
    if exist(root, 'dir') && exist(fitted, 'file')
        sim_source = struct('kind', 'wholecell_simulation_fitted', 'path', root);
        return;
    end
end

saved_snapshots = { ...
    fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'karr_simulation_fitted.mat'), ...
    'E:\opencell\data\m1_sources\karr_native\karr_simulation_fitted.mat', ...
};

for i = 1:numel(saved_snapshots)
    p = saved_snapshots{i};
    if exist(p, 'file')
        sim_source = struct('kind', 'saved_simulation_snapshot', 'path', p);
        return;
    end
end

error(['No simulation source found. Expected either _tmp_WholeCell/data/Simulation_fitted.mat ' ...
    'or data/m1_sources/karr_native/karr_simulation_fitted.mat']);
end

function sim = load_simulation(sim_source)
switch sim_source.kind
    case 'wholecell_simulation_fitted'
        root = sim_source.path;
        old_dir = pwd;
        cleaner = onCleanup(@() cd(old_dir)); %#ok<NASGU>
        cd(root);

        if exist('setWarnings.m', 'file') == 2
            try
                setWarnings();
            catch warn_err
                fprintf('[trace_fix] WARN setWarnings failed: %s\n', warn_err.message);
            end
        end

        if exist('setPath.m', 'file') == 2
            try
                setPath();
            catch path_err
                fprintf('[trace_fix] WARN setPath failed, using src fallback: %s\n', path_err.message);
                addpath(genpath(fullfile(root, 'src')));
            end
        else
            addpath(genpath(fullfile(root, 'src')));
        end

        payload = load(fullfile(root, 'data', 'Simulation_fitted.mat'));
        sim = extract_simulation(payload);

    case 'saved_simulation_snapshot'
        payload = load(sim_source.path);
        sim = extract_simulation(payload);

    otherwise
        error('Unsupported simulation source kind: %s', sim_source.kind);
end
end

function sim = extract_simulation(payload)
if isfield(payload, 'simulation')
    sim = payload.simulation;
    return;
end
if isfield(payload, 'sim')
    sim = payload.sim;
    return;
end
if isfield(payload, 'data')
    d = payload.data;
    if isstruct(d) && isfield(d, 'simulation')
        sim = d.simulation;
        return;
    end
    if isstruct(d) && isfield(d, 'sim')
        sim = d.sim;
        return;
    end
end
error('Could not find simulation object in loaded payload');
end

function proc = find_process(sim, process_name)
proc = [];
target_id = ['Process_' process_name];

if isobject(sim) && ismethod(sim, 'process')
    try
        proc = sim.process(process_name);
        if ~isempty(proc)
            return;
        end
    catch
    end
end

try
    procs = sim.processes;
catch
    procs = {};
end

for i = 1:numel(procs)
    candidate = procs{i};
    try
        wid = candidate.wholeCellModelID;
        if strcmp(wid, target_id) || strcmp(wid, process_name)
            proc = candidate;
            return;
        end
    catch
    end
end
end

function props = pick_snapshot_properties(proc, process_name)
base_candidates = { ...
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
};

extras = {};
switch process_name
    case 'Transcription'
        extras = {'rnas', 'freeRNAs', 'unprocessedRNAs', 'processedRNAs'};
    case 'Translation'
        extras = {'monomers', 'complexs', 'freeRNAs', 'aminoacylatedRNAs'};
    case 'RNADecay'
        extras = {'rnas', 'freeRNAs', 'processedRNAs', 'unprocessedRNAs'};
    case 'Replication'
        extras = {'complexs', 'monomers', 'rnas'};
    case 'ReplicationInitiation'
        extras = {'complexs', 'monomers'};
end

ordered = unique([base_candidates extras], 'stable');
props = {};
for i = 1:numel(ordered)
    prop = ordered{i};
    try
        if ~isprop(proc, prop)
            continue;
        end
        val = proc.(prop);
        if is_snapshot_value_supported(val)
            props{end+1} = prop; %#ok<AGROW>
        end
    catch
    end
end
end

function tf = is_snapshot_value_supported(v)
tf = isnumeric(v) || islogical(v) || ischar(v) || isstring(v) || iscell(v) || isstruct(v);
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

function [ok, err_msg] = evolve_once(proc)
ok = false;
err_msg = '';

try
    proc.evolveState();
    ok = true;
    return;
catch err
    err_msg = err.message;
end

pre_methods = { ...
    'calcResourceRequirements_Current', ...
    'calculateResourceRequirements_Current', ...
    'calcResourceRequirements_LifeCycle', ...
    'calculateResourceRequirements_LifeCycle', ...
    'calcResourceRequirements', ...
};

for i = 1:numel(pre_methods)
    m = pre_methods{i};
    if ~ismethod(proc, m)
        continue;
    end
    try
        invoke_method(proc, m);
        proc.evolveState();
        ok = true;
        err_msg = sprintf('recovered via %s after initial error: %s', m, err_msg);
        return;
    catch retry_err
        err_msg = sprintf('%s | retry(%s): %s', err_msg, m, retry_err.message);
    end
end
end

function invoke_if_exists(obj, method_name)
if ismethod(obj, method_name)
    invoke_method(obj, method_name);
end
end

function invoke_method(obj, method_name)
f = str2func(method_name);
f(obj);
end
