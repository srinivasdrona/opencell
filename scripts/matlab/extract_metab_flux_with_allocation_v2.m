function extract_metab_flux_with_allocation_v2(wholecellRoot, outDir, seed, nTicks)
% V2: Mirror extract_per_process_traces_v2.m's evolve_state_with_tap exactly,
% with added FBA flux capture for Metabolism at the allocated pre-state.

    if nargin < 1, wholecellRoot = pwd; end
    if nargin < 2, outDir = fullfile(wholecellRoot, 'metab_flux_extract'); end
    if nargin < 3, seed = uint32(0); end
    if nargin < 4, nTicks = uint32(10); end
    if ~exist(outDir, 'dir'), mkdir(outDir); end

    cd(wholecellRoot);
    warning('off', 'all');
    setPath();

    fprintf('=== Loading Simulation_fitted.mat ===\n');
    s = load('data/Simulation_fitted.mat');
    sim = s.simulation;

    target_idx = -1;
    for i = 1:numel(sim.processes)
        if strcmp(sim.processes{i}.wholeCellModelID, 'Process_Metabolism')
            target_idx = i; break;
        end
    end
    assert(target_idx > 0, 'Process_Metabolism not found');
    fprintf('Target: Metabolism (proc_idx=%d), seed=%d, n_ticks=%d\n', target_idx, seed, nTicks);

    % Seed simulation (mirror seed_simulation in v2 script)
    sim.applyOptions('seed', seed);
    sim.seedRandStream();
    for i = 1:numel(sim.processes)
        if isprop(sim.processes{i}, 'seed')
            sim.processes{i}.seed = seed;
            if ismethod(sim.processes{i}, 'seedRandStream')
                sim.processes{i}.seedRandStream();
            end
        end
    end

    flux_records = cell(nTicks, 1);
    growth_records = zeros(nTicks, 1);
    bounds_records = cell(nTicks, 1);
    pre_substrates = cell(nTicks, 1);
    pre_enzymes = cell(nTicks, 1);
    post_substrates = cell(nTicks, 1);

    for t = 1:nTicks
        fprintf('--- tick %d ---\n', t);
        [sim, flux_t, growth_t, bounds_t, pre_sub, pre_enz, post_sub] = ...
            evolve_state_with_flux_capture(sim, target_idx);
        flux_records{t, 1} = flux_t;
        growth_records(t) = growth_t;
        bounds_records{t, 1} = bounds_t;
        pre_substrates{t, 1} = pre_sub;
        pre_enzymes{t, 1} = pre_enz;
        post_substrates{t, 1} = post_sub;
        fprintf('  growth=%.4e, flux_sum_abs=%.4e\n', growth_t, sum(abs(flux_t)));
    end

    out = struct();
    out.x_seed = seed;
    out.x_n_ticks = nTicks;
    out.x_target_proc_idx = target_idx;
    out.x_extract_timestamp_utc = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    out.flux = flux_records;
    out.growth = growth_records;
    out.bounds = bounds_records;
    out.pre_substrates = pre_substrates;
    out.pre_enzymes = pre_enzymes;
    out.post_substrates = post_substrates;

    outFile = fullfile(outDir, sprintf('metab_flux_per_tick_s%03d_%dticks.mat', seed, nTicks));
    save(outFile, '-struct', 'out', '-v7.3');
    fprintf('\nSaved %s\n', outFile);
end

function [sim, flux_t, growth_t, bounds_t, pre_sub, pre_enz, post_sub] = evolve_state_with_flux_capture(sim, target_idx)
% Mirror evolve_state_with_tap from extract_per_process_traces_v2.m,
% but capture FBA flux + growth at the target process's allocated pre-state.

    time = sim.state_time;
    mets = sim.state_metabolite;
    stim = sim.state_stimulus;

    time.values = time.values + sim.stepSizeSec;
    stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
        stim.values, stim.setValues, time.values);

    processes = sim.processes;
    nProcesses = numel(processes);
    rna_decay_idx = sim.processIndex('RNADecay');

    % Compute resource requirements
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

    flux_t = []; growth_t = NaN; bounds_t = []; pre_sub = []; pre_enz = []; post_sub = [];

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
            % Capture pre-state (post-allocation, pre-evolveState)
            pre_sub = mod.substrates;
            pre_enz = mod.enzymes;
            % Run calcFluxBounds + calcGrowthRate to capture flux at this state
            bounds_t = mod.calcFluxBounds( ...
                mod.substrates, mod.enzymes, mod.fbaReactionBounds, mod.fbaEnzymeBounds);
            [growth_t, ~, flux_t] = mod.calcGrowthRate( ...
                bounds_t, mod.fbaObjective, mod.fbaReactionStoichiometryMatrix);
        end

        mod.evolveState();

        if proc_idx == target_idx
            post_sub = mod.substrates;
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
