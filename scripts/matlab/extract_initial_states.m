% extract_initial_states.m
% Capture fresh initializeState() output per process.

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
addpath(matlab_dir);

sim = karr_bootstrap();

scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'initial_states');
if ~exist(out_root, 'dir')
    mkdir(out_root);
end

process_names = arrayfun(@(i) sim.processes{i}.wholeCellModelID, 1:numel(sim.processes), 'UniformOutput', false);
process_names = strrep(process_names, 'Process_', '');

for i = 1:numel(process_names)
    pname = process_names{i};
    out_path = fullfile(out_root, [pname '_init.mat']);
    if exist(out_path, 'file')
        fprintf('[init] already exists, skipping: %s\n', pname);
        continue;
    end

    try
        proc = sim.process(pname);
    catch err
        fprintf('[init] WARN process %s not loadable: %s\n', pname, err.message);
        continue;
    end

    try
        proc.initializeState();
    catch err
        fprintf('[init] WARN %s.initializeState failed: %s\n', pname, err.message);
        continue;
    end

    init_state = struct();
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

    for p = 1:numel(snapshot_props)
        init_state.(snapshot_props{p}) = proc.(snapshot_props{p});
    end

    metadata = struct( ...
        'process_name', pname, ...
        'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
        'snapshot_properties', {snapshot_props} ...
    );

    save(out_path, 'init_state', 'metadata', '-v7.3');
    fprintf('[init] saved: %s\n', pname);
end

fprintf('\n[init] DONE\n');
