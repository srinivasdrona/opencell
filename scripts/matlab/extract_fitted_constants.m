% extract_fitted_constants.m
% Capture Karr's fitConstants() output — the fitted parameter values.

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
addpath(matlab_dir);

sim = karr_bootstrap();

scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
out_path = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'fitted_constants.mat');

if exist(out_path, 'file')
    fprintf('[fit] output already exists: %s\n', out_path);
    fprintf('[fit] delete to regenerate\n');
    return;
end

% Pull fitted constants from each process — Karr stores them as named
% properties whose values were set by fitConstants() during simulation init.
fitted = struct();

for i = 1:numel(sim.processes)
    proc = sim.processes{i};
    pname = strrep(proc.wholeCellModelID, 'Process_', '');
    fprintf('[fit] === %s ===\n', pname);

    try
        names = proc.fittedConstantNames;
    catch
        names = {};
    end

    if isempty(names)
        continue;
    end

    proc_fitted = struct();
    for n = 1:numel(names)
        fname = names{n};
        try
            v = proc.(fname);
            proc_fitted.(fname) = v;
        catch err
            fprintf('[fit] WARN %s.%s unreadable: %s\n', pname, fname, err.message);
        end
    end

    fitted.(pname) = proc_fitted;
end

metadata = struct( ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
    'process_count', numel(fieldnames(fitted)) ...
);

save(out_path, 'fitted', 'metadata', '-v7.3');
fprintf('\n[fit] saved: %s\n', out_path);
fprintf('[fit] DONE\n');
