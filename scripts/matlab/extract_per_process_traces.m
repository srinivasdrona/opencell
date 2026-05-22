function extract_per_process_traces(process_names, output_subdir, n_ticks)
% extract_per_process_traces  Bit-identical evolveState traces per process.
%
% For each process named in PROCESS_NAMES, freeze inputs, run N_TICKS of
% evolveState, capture (states_before, evolveState_emitted, states_after)
% on every tick.
%
% Args:
%   process_names: cell array of strings, e.g. {'Metabolism', 'tRNAAminoacylation'}
%   output_subdir: relative dir under data/m1_sources/karr_native/per_process_traces/
%                  (typically just 'per_process_traces')
%   n_ticks: how many ticks to run per process (default 100)
%
% Each output file:
%   data/m1_sources/karr_native/<output_subdir>/<process_name>_100ticks.mat
% contains:
%   states_before          struct of per-property snapshots, each (n_ticks, ...)
%   evolveState_emitted    struct of per-property post-evolveState deltas
%   metadata               struct: n_ticks, rng_seed, process_name, timestamp

if nargin < 2 || isempty(output_subdir)
    output_subdir = 'per_process_traces';
end
if nargin < 3 || isempty(n_ticks)
    n_ticks = 100;
end

sim = karr_bootstrap();

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', output_subdir);
if ~exist(out_root, 'dir')
    mkdir(out_root);
end

for i = 1:numel(process_names)
    pname = process_names{i};
    fprintf('\n[trace] === %s ===\n', pname);
    out_path = fullfile(out_root, [pname '_' num2str(n_ticks) 'ticks.mat']);

    if exist(out_path, 'file')
        fprintf('[trace] already exists, skipping: %s\n', out_path);
        continue;
    end

    % Look up process by iterating cell array (sim is a loaded struct, not a class instance)
    target_id = ['Process_' pname];
    proc = [];
    for k = 1:numel(sim.processes)
        if strcmp(sim.processes{k}.wholeCellModelID, target_id)
            proc = sim.processes{k};
            break;
        end
    end
    if isempty(proc)
        fprintf('[trace] WARN process %s not found in sim\n', pname);
        continue;
    end

    % Properties we'll snapshot before and after each evolveState
    snapshot_props = intersect(properties(proc), { ...
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

    fprintf('[trace] %s snapshot properties: %s\n', pname, strjoin(snapshot_props, ', '));

    states_before = struct();
    states_after  = struct();
    for p = 1:numel(snapshot_props)
        states_before.(snapshot_props{p}) = {};
        states_after.(snapshot_props{p})  = {};
    end

    % Run n_ticks of evolveState on this process
    sim.randStream.seed = uint32(0);  % deterministic
    for t = 1:n_ticks
        % Snapshot before
        proc.copyFromState();
        for p = 1:numel(snapshot_props)
            v = proc.(snapshot_props{p});
            states_before.(snapshot_props{p}){end+1} = v;
        end

        % Run evolveState
        try
            proc.evolveState();
        catch err
            fprintf('[trace] ERROR evolving %s at tick %d: %s\n', pname, t, err.message);
            break;
        end

        % Snapshot after
        for p = 1:numel(snapshot_props)
            v = proc.(snapshot_props{p});
            states_after.(snapshot_props{p}){end+1} = v;
        end

        % Apply back to global state so subsequent ticks see consistent state
        proc.copyToState();
    end

    metadata = struct( ...
        'process_name', pname, ...
        'n_ticks', n_ticks, ...
        'rng_seed', uint32(0), ...
        'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
        'snapshot_properties', {snapshot_props} ...
    );

    save(out_path, 'states_before', 'states_after', 'metadata', '-v7.3');
    fprintf('[trace] saved: %s\n', out_path);
end

end
