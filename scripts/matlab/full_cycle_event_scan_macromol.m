% full_cycle_event_scan_macromol.m
% Lifecycle-reachability probe for MacromolecularComplexation network 2
% (the competitive Monte Carlo cluster gated on MG_429_MONOMER / PTS
% system E1). Answers a narrow, falsifiable question: across a full
% natural Karr cell cycle (birth to division, real scheduler order, no
% conditioning), does E1's free-monomer pool ever leave zero, and does
% network 2 (or any network >= 2) ever actually form a complex?
%
% This mirrors full_cycle_event_scan_v2.m's Part-1 mechanism exactly (same
% per-tick resource-allocation + evolveState scheduler loop, same
% process-order/rand-perm handling) but targets MacromolecularComplexation
% specifically and adds an explicit E1-pool time series plus a natural
% cell-division stop (Geometry.pinched), matching
% extract_cell_cycle_trajectory.m's stopping condition so we never treat
% post-division ticks as "natural".
%
% Usage: matlab -batch "run('scripts/matlab/full_cycle_event_scan_macromol.m')"

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

%% Setup WholeCell paths (same fallback pattern as karr_bootstrap.m)
wc_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
if ~exist(wc_root, 'dir')
    wc_root = 'E:\opencell\data\m1_sources\WholeCell';
end
old_dir = pwd;
cd(wc_root);
if exist('setPath.m', 'file') == 2
    try; setPath(); catch; end
else
    addpath(genpath(fullfile(wc_root, 'src')));
    addpath(genpath(fullfile(wc_root, 'lib')));
end
cd(old_dir);
addpath(fullfile(repo_root, 'scripts', 'matlab'));

out_dir = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'event_scan');
if ~exist(out_dir, 'dir'); mkdir(out_dir); end

%% Bootstrap
seed = uint32(0);
n_ticks_max = 33000; % ~9.2h at dt=1s; covers Karr's published ~32400-tick cycle plus margin
requested_name = 'MacromolecularComplexation';

fprintf('\n[macromol-scan] === %s (seed=%d, up to %d ticks, natural cycle, pinch-stop) ===\n', ...
    requested_name, seed, n_ticks_max);

sim = karr_bootstrap();

%% Find process index
target_proc_idx = [];
for i = 1:numel(sim.processes)
    proc_obj = sim.processes{i};
    try
        wid = proc_obj.wholeCellModelID;
        if contains(lower(wid), lower(requested_name))
            target_proc_idx = i;
            break;
        end
    catch
    end
end
if isempty(target_proc_idx)
    error('[macromol-scan] process not found: %s', requested_name);
end
fprintf('[macromol-scan] found %s at index %d\n', requested_name, target_proc_idx);

target_proc = sim.processes{target_proc_idx};
e1_idx = find(strcmp(target_proc.substrateWholeCellModelIDs, 'MG_429_MONOMER'), 1);
if isempty(e1_idx)
    error('[macromol-scan] MG_429_MONOMER not found in substrateWholeCellModelIDs');
end
net2_complex_names = {'MG_041_062_429_PENTAMER', 'MG_041_069_429_PENTAMER'};
net2_complex_idx = [];
for c = 1:numel(net2_complex_names)
    idx = find(strcmp(target_proc.complexWholeCellModelIDs, net2_complex_names{c}), 1);
    if ~isempty(idx)
        net2_complex_idx(end+1) = idx; %#ok<AGROW>
    end
end
fprintf('[macromol-scan] E1 local substrate index = %d; network-2 complex indices = %s\n', ...
    e1_idx, mat2str(net2_complex_idx));

%% Seed
try
    sim.applyOptions('seed', double(seed));
    sim.seedRandStream();
catch
end

%% Scan
csv_path = fullfile(out_dir, sprintf('MacromolecularComplexation_e1_lifecycle_seed%03d.csv', seed));
fid = fopen(csv_path, 'w');
fprintf(fid, 'tick,e1_pool,any_complex_delta,net2_complex_delta_sum,pinched\n');

time_obj = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;
processes = sim.processes;
nProcs = numel(processes);
geom = sim.state('Geometry');

first_e1_nonzero_tick = -1;
first_net2_event_tick = -1;
max_e1_pool = 0;
n_any_complex_events = 0;
n_net2_events = 0;

tic;
last_tick = 0;
for tick = 1:n_ticks_max
    last_tick = tick;
    if mod(tick, 1000) == 0
        elapsed = toc;
        fprintf('[macromol-scan] tick %d/%d (%.1f min) max_e1=%g net2_events=%d\n', ...
            tick, n_ticks_max, elapsed/60, max_e1_pool, n_net2_events);
    end

    time_obj.values = time_obj.values + sim.stepSizeSec;
    stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
        stim.values, stim.setValues, time_obj.values);

    requirements = zeros([numel(mets.counts) nProcs]);
    for i = 1:nProcs
        proc_mod = processes{i};
        proc_mod.copyFromState();
        r = proc_mod.calcResourceRequirements_Current();
        gidx = proc_mod.substrateMetaboliteGlobalCompartmentIndexs;
        lidx = proc_mod.substrateMetaboliteLocalIndexs;
        if ~isempty(gidx) && ~isempty(lidx)
            requirements(gidx, i) = reshape(r(lidx, :), [], 1);
        end
    end

    requirements = max(0, requirements);
    tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
    allocations = max(0, fix(requirements .* tmp(:, ones(nProcs, 1))));
    processOrder = randperm(nProcs);

    e1_pool_this_tick = NaN;
    complex_delta_sum = 0;
    net2_delta_sum = 0;

    for i = 1:nProcs
        proc_idx = processOrder(i);
        proc_mod = processes{proc_idx};
        gidx = proc_mod.substrateMetaboliteGlobalCompartmentIndexs;
        lidx = proc_mod.substrateMetaboliteLocalIndexs;
        allocation = reshape(allocations(gidx, proc_idx), size(gidx));
        counts = mets.counts(gidx);
        proc_mod.simulationStateSideEffects = [];
        proc_mod.copyFromState();
        proc_mod.substrates(lidx, :) = allocation;

        if proc_idx == target_proc_idx
            e1_pool_this_tick = proc_mod.substrates(e1_idx);
            complexs_before = proc_mod.complexs;
        end

        proc_mod.evolveState();

        if proc_idx == target_proc_idx
            complexs_after = proc_mod.complexs;
            d = complexs_after - complexs_before;
            complex_delta_sum = sum(d(:));
            if ~isempty(net2_complex_idx)
                net2_delta_sum = sum(d(net2_complex_idx));
            end
        end

        proc_mod.copyToState();
        mets.counts(gidx) = counts + proc_mod.substrates(lidx, :) - allocation;
        if ~isempty(proc_mod.simulationStateSideEffects)
            proc_mod.simulationStateSideEffects.updateSimulationState(sim);
        end
    end

    mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
        mets.counts, mets.setCounts, time_obj.values);

    if e1_pool_this_tick > max_e1_pool
        max_e1_pool = e1_pool_this_tick;
    end
    if e1_pool_this_tick > 0 && first_e1_nonzero_tick < 0
        first_e1_nonzero_tick = tick;
    end
    if complex_delta_sum ~= 0
        n_any_complex_events = n_any_complex_events + 1;
    end
    if net2_delta_sum ~= 0
        n_net2_events = n_net2_events + 1;
        if first_net2_event_tick < 0
            first_net2_event_tick = tick;
        end
    end

    is_pinched = false;
    try
        is_pinched = geom.pinched;
    catch
    end

    if mod(tick, 25) == 0 || complex_delta_sum ~= 0 || e1_pool_this_tick > 0 || is_pinched
        fprintf(fid, '%d,%g,%g,%g,%d\n', tick, e1_pool_this_tick, complex_delta_sum, net2_delta_sum, is_pinched);
    end

    if is_pinched
        fprintf('[macromol-scan] cell pinched/divided at tick %d; stopping (natural cycle boundary)\n', tick);
        break;
    end
end

elapsed = toc;
fclose(fid);

fprintf('\n[macromol-scan] DONE: ran %d ticks in %.1f min\n', last_tick, elapsed/60);
fprintf('[macromol-scan] max E1 pool observed = %g\n', max_e1_pool);
fprintf('[macromol-scan] first tick E1 pool > 0: %d\n', first_e1_nonzero_tick);
fprintf('[macromol-scan] total any-complex-delta events: %d\n', n_any_complex_events);
fprintf('[macromol-scan] total network>=2 complex-delta events: %d (first at tick %d)\n', ...
    n_net2_events, first_net2_event_tick);

summary = struct( ...
    'process', requested_name, ...
    'seed', double(seed), ...
    'n_ticks_ran', last_tick, ...
    'e1_local_substrate_index_1based', e1_idx, ...
    'net2_complex_indices_1based', net2_complex_idx, ...
    'max_e1_pool', max_e1_pool, ...
    'first_e1_nonzero_tick', first_e1_nonzero_tick, ...
    'n_any_complex_events', n_any_complex_events, ...
    'n_net2_events', n_net2_events, ...
    'first_net2_event_tick', first_net2_event_tick, ...
    'natural_cycle_stop_tick', last_tick, ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS') ...
);
summary_path = fullfile(out_dir, sprintf('MacromolecularComplexation_e1_lifecycle_seed%03d_summary.json', seed));
fid2 = fopen(summary_path, 'w');
fprintf(fid2, '%s', jsonencode(summary));
fclose(fid2);
fprintf('[macromol-scan] summary written: %s\n', summary_path);

exit(0);
