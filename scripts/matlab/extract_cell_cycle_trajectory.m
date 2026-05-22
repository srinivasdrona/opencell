% extract_cell_cycle_trajectory.m
% Full Karr WCM cell-cycle reference run.
% Logs state every snapshot_interval ticks for an entire cell cycle.

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
addpath(matlab_dir);

sim = karr_bootstrap();

scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
out_path = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'cell_cycle_trajectory.mat');

if exist(out_path, 'file')
    fprintf('[cell_cycle] output already exists: %s\n', out_path);
    fprintf('[cell_cycle] delete to regenerate\n');
    return;
end

% Use a Logger so we don't have to manually snapshot every tick
% Karr's standard SummaryLogger / ConcentrationsLogger captures all process state
loggers = {};
try
    snap_logger = edu.stanford.covert.cell.sim.util.SummaryLogger(100, 1);  % every 100 ticks, verbosity 1
    loggers{end+1} = snap_logger;
catch err
    fprintf('[cell_cycle] SummaryLogger unavailable: %s\n', err.message);
    fprintf('[cell_cycle] falling back to manual state snapshots\n');
    snap_logger = [];
end

% Manual snapshot fallback
snapshot_interval = 100;
n_total_steps = 32400;  % ~9 hours at dt=1s; Karr's published cell cycle length
snapshots = struct();
snapshots.tick = [];

% Pre-discover state property names we want to capture
state_names = {'Metabolite', 'Rna', 'ProteinMonomer', 'ProteinComplex', 'Mass', 'Geometry', 'Time'};

fprintf('[cell_cycle] starting run: %d ticks at dt=%g s\n', n_total_steps, sim.stepSizeSec);
tic;

try
    for tick_idx = 1:n_total_steps
        sim.evolveState();
        if mod(tick_idx, snapshot_interval) == 0
            snapshots.tick(end+1) = tick_idx;
            for s = 1:numel(state_names)
                sname = state_names{s};
                try
                    sobj = sim.state(sname);
                    fields = properties(sobj);
                    for f = 1:numel(fields)
                        fname = fields{f};
                        try
                            v = sobj.(fname);
                            if isnumeric(v) && numel(v) < 10000
                                key = [sname '_' fname];
                                if ~isfield(snapshots, key)
                                    snapshots.(key) = {};
                                end
                                snapshots.(key){end+1} = v;
                            end
                        catch
                        end
                    end
                catch
                end
            end
            elapsed = toc;
            fprintf('[cell_cycle] tick %d / %d (%.1f%%) elapsed=%.1fs eta=%.1fs\n', ...
                tick_idx, n_total_steps, 100*tick_idx/n_total_steps, elapsed, ...
                elapsed * (n_total_steps - tick_idx) / tick_idx);
        end

        % Early termination if cell has divided
        if sim.state('Geometry').pinched
            fprintf('[cell_cycle] cell pinched/divided at tick %d\n', tick_idx);
            break;
        end
    end
catch err
    fprintf('[cell_cycle] ERROR at tick %d: %s\n', tick_idx, err.message);
    fprintf('[cell_cycle] saving partial trajectory anyway\n');
end

metadata = struct( ...
    'snapshot_interval', snapshot_interval, ...
    'n_total_steps_target', n_total_steps, ...
    'n_snapshots_captured', numel(snapshots.tick), ...
    'rng_seed', uint32(0), ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS') ...
);

save(out_path, 'snapshots', 'metadata', '-v7.3');
fprintf('[cell_cycle] saved: %s\n', out_path);
fprintf('[cell_cycle] DONE\n');
