function extract_metab_flux_with_allocation(wholecellRoot, outDir, seed, nTicks)
% Extract per-tick FBA flux + growth for Metabolism at the ACTUAL allocated
% pre-state used by Karr's evolveState (post-copyFromState + post-allocation).
%
% This is the state the v2 trace's states_before captures. Comparing OC HiGHS
% vs Karr GLPK requires both running at the SAME pre-state — which is what
% this script provides.

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

    % Find target process index
    target_idx = -1;
    for i = 1:numel(sim.processes)
        if strcmp(sim.processes{i}.wholeCellModelID, 'Process_Metabolism')
            target_idx = i; break;
        end
    end
    assert(target_idx > 0, 'Process_Metabolism not found');

    fprintf('Target: Metabolism (proc_idx=%d), seed=%d, n_ticks=%d\n', target_idx, seed, nTicks);

    % Seed the simulation — mirror seed_simulation from extract_per_process_traces_v2.m
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
            run_one_tick_capture_flux(sim, target_idx);
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

function [sim, flux_t, growth_t, bounds_t, pre_sub, pre_enz, post_sub] = run_one_tick_capture_flux(sim, target_idx)
% One tick of the simulation with flux capture for the target process.
% Largely mirrors Simulation.evolveState scheduler, but for the target
% process it captures pre-state + LP flux before evolveState mutates anything.

    time = sim.state('Time');
    mets = sim.state('Metabolite');
    nProcesses = numel(sim.processes);

    time.values = time.values + sim.stepSizeSec;
    sim.calcStateSideEffects();

    % Allocation: mirror Simulation.calcResourceAllocations
    allocations = sim.allocateMetaboliteResources();

    % Compute processEvalOrderIndexs the same way Simulation does
    processEvalOrderIndexs = 1:nProcesses;
    for i = 1:5
        idx1 = -1; idx2 = -1;
        for p = 1:numel(processEvalOrderIndexs)
            if strcmp(sim.processes{processEvalOrderIndexs(p)}.wholeCellModelID, 'Process_Metabolism')
                idx1 = p;
            end
        end
        if idx1 == -1, break; end
        % Move Metabolism to its default position; same as full extraction
        break;
    end

    flux_t = []; growth_t = NaN; bounds_t = []; pre_sub = []; pre_enz = []; post_sub = [];

    for i = 1:nProcesses
        proc_idx = processEvalOrderIndexs(i);
        mod = sim.processes{proc_idx};

        gidx = mod.substrateMetaboliteGlobalCompartmentIndexs;
        lidx = mod.substrateMetaboliteLocalIndexs;
        allocation = reshape(allocations(gidx, proc_idx), size(gidx));
        counts = mets.counts(gidx);

        mod.simulationStateSideEffects = [];
        mod.copyFromState();
        mod.substrates(lidx, :) = allocation;

        if proc_idx == target_idx
            % Capture pre-state (allocated)
            pre_sub = mod.substrates;
            pre_enz = mod.enzymes;
            % Compute LP at THIS state — mirror evolveState's first line
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
