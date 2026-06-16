% full_cycle_event_scan.m
% Scan a full Karr cell cycle and log which ticks Cytokinesis and
% RibosomeAssembly produce non-zero deltas.
%
% Usage: matlab -batch "run('scripts/matlab/full_cycle_event_scan.m')"

repo_root = pwd;

%% Setup WholeCell paths (inlined from extract_per_process_traces_v2)
wc_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
if ~exist(wc_root, 'dir')
    wc_root = 'E:\opencell\data\m1_sources\WholeCell';
end
old_dir = pwd;
cd(wc_root);
if exist('setWarnings.m', 'file') == 2
    try; setWarnings(); catch; end
end
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

n_ticks = 32400;
seed = uint32(0);
target_names = {'Cytokinesis', 'RibosomeAssembly'};

for t_idx = 1:numel(target_names)
    requested_name = target_names{t_idx};
    fprintf('\n[scan] === %s (seed=%d, %d ticks) ===\n', requested_name, seed, n_ticks);

    %% Boot sim (must cd to WholeCell root for CachedSimulationObjectUtil)
    old_wd = pwd;
    cd(wc_root);
    sim = edu.stanford.covert.cell.sim.util.CachedSimulationObjectUtil.load();
    cd(old_wd);

    %% Find process index
    target_proc_idx = [];
    canonical_name = requested_name;
    req_lower = lower(requested_name);
    for i = 1:numel(sim.processes)
        proc_obj = sim.processes{i};
        % Try wholeCellModelID first (e.g. 'Process_Cytokinesis')
        try
            wid = proc_obj.wholeCellModelID;
            if contains(lower(wid), req_lower)
                target_proc_idx = i;
                % Extract short name from WID: 'Process_Cytokinesis' -> 'Cytokinesis'
                parts = strsplit(wid, '_');
                if numel(parts) >= 2
                    canonical_name = strjoin(parts(2:end), '_');
                else
                    canonical_name = wid;
                end
                break;
            end
        catch
        end
        % Fallback: class name
        cn = class(proc_obj);
        if contains(lower(cn), req_lower)
            target_proc_idx = i;
            parts = strsplit(cn, '.');
            canonical_name = parts{end};
            break;
        end
    end
    if isempty(target_proc_idx)
        fprintf('[scan] process not found: %s\n', requested_name);
        continue;
    end
    fprintf('[scan] found %s at index %d\n', canonical_name, target_proc_idx);

    %% Identify snapshot properties (broader list matching v2 extractor)
    all_props = properties(sim.processes{target_proc_idx});
    candidate_props = { ...
        'substrates', 'enzymes', 'boundEnzymes', 'complexs', 'monomers', ...
        'RNAs', 'rnas', 'freeRNAs', 'chromosome', ...
        'unprocessedRNAs', 'processedRNAs', 'intergenicRNAs', ...
        'unmodifiedRNAs', 'modifiedRNAs', ...
        'unprocessedMonomers', 'processedMonomers', ...
        'signalSequenceMonomers', ...
        'unfoldedMonomers', 'foldedMonomers', ...
        'unfoldedComplexs', 'foldedComplexs', ...
        'inactiveMonomers', 'matureMonomers', ...
        'inactiveComplexs', 'matureComplexs', ...
        'aminoacylatedRNAs', 'freeTRNAs', ...
    };
    track_props = intersect(all_props, candidate_props);
    if isempty(track_props)
        % Fallback: track ALL non-dependent properties
        track_props = all_props;
        fprintf('[scan] WARNING: no standard props found, tracking all %d properties\n', numel(track_props));
    end
    fprintf('[scan] tracking: %s\n', strjoin(track_props, ', '));

    %% Seed (use sim's own method, not per-process assignment)
    try
        sim.applyOptions('seed', double(seed));
        sim.seedRandStream();
    catch
        try
            if isprop(sim, 'randStream') && ~isempty(sim.randStream)
                sim.randStream.seed = double(seed);
            end
        catch
        end
    end

    %% Open CSV
    csv_path = fullfile(out_dir, sprintf('%s_event_ticks_seed%03d.csv', canonical_name, seed));
    fid = fopen(csv_path, 'w');
    fprintf(fid, 'tick,has_event,delta_summary\n');

    n_events = 0;
    tic;

    %% Cache simulation objects
    time_obj = sim.state_time;
    mets = sim.state_metabolite;
    stim = sim.state_stimulus;
    processes = sim.processes;
    nProcs = numel(processes);

    for tick = 1:n_ticks
        if mod(tick, 500) == 0
            elapsed = toc;
            fprintf('[scan] %s tick %d/%d (%.1f min, %d events)\n', ...
                canonical_name, tick, n_ticks, elapsed/60, n_events);
        end

        try
            %% Advance time
            time_obj.values = time_obj.values + sim.stepSizeSec;
            stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
                stim.values, stim.setValues, time_obj.values);

            %% Collect resource requirements
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

            %% Allocate
            requirements = max(0, requirements);
            tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
            allocations = max(0, fix(requirements .* tmp(:, ones(nProcs, 1))));

            %% Random process order (simplified — no tRNA/translation constraint)
            processOrder = randperm(nProcs);

            %% Evolve each process
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

                %% Capture before for target
                if proc_idx == target_proc_idx
                    before = struct();
                    for p = 1:numel(track_props)
                        before.(track_props{p}) = proc_mod.(track_props{p});
                    end
                end

                proc_mod.evolveState();

                %% Capture after and check delta for target
                if proc_idx == target_proc_idx
                    has_event = false;
                    delta_parts = {};
                    for p = 1:numel(track_props)
                        av = proc_mod.(track_props{p});
                        d = av - before.(track_props{p});
                        if any(d(:) ~= 0)
                            has_event = true;
                            delta_parts{end+1} = sprintf('%s:sum=%.0f', track_props{p}, sum(d(:)));
                        end
                    end
                    if has_event
                        n_events = n_events + 1;
                        fprintf(fid, '%d,1,"%s"\n', tick, strjoin(delta_parts, ';'));
                    end
                end

                proc_mod.copyToState();
                mets.counts(gidx) = counts + proc_mod.substrates(lidx, :) - allocation;

                if ~isempty(proc_mod.simulationStateSideEffects)
                    proc_mod.simulationStateSideEffects.updateSimulationState(sim);
                end
            end

            %% Apply metabolite conditions
            mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
                mets.counts, mets.setCounts, time_obj.values);

        catch ME
            fprintf('[scan] ERROR tick %d: %s\n', tick, ME.message);
        end
    end

    elapsed = toc;
    fclose(fid);
    fprintf('[scan] %s DONE: %d events in %d ticks (%.1f min)\n', ...
        canonical_name, n_events, n_ticks, elapsed/60);
    clear sim;
end

%% Summary
summary_path = fullfile(out_dir, sprintf('scan_summary_seed%03d.txt', seed));
fid = fopen(summary_path, 'w');
fprintf(fid, 'Full cycle event scan\nseed: %d\nn_ticks: %d\ntimestamp: %s\n', ...
    seed, n_ticks, datestr(now, 'yyyy-mm-dd HH:MM:SS'));
fclose(fid);
fprintf('[scan] Summary: %s\n', summary_path);
exit(0);
