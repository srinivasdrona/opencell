function extract_metab_flux_v3(wholecellRoot, outDir, seed)
% V3: Just compute Metabolism's flux at the post-allocation tick-0 state.
% Skip evolveState calls for OTHER processes (RNADecay needs Statistics Toolbox
% which trial license lacks).

    if nargin < 1, wholecellRoot = pwd; end
    if nargin < 2, outDir = fullfile(wholecellRoot, 'metab_flux_extract'); end
    if nargin < 3, seed = uint32(0); end
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
    fprintf('Target: Metabolism (proc_idx=%d), seed=%d\n', target_idx, seed);

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

    % Mirror evolve_state_with_tap up through allocation, but don't call evolveState
    % for other processes (avoid toolbox-dependent code paths).
    time = sim.state_time;
    mets = sim.state_metabolite;
    stim = sim.state_stimulus;
    time.values = time.values + sim.stepSizeSec;
    stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
        stim.values, stim.setValues, time.values);

    processes = sim.processes;
    nProcesses = numel(processes);
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

    % Now do allocation+flux for Metabolism only
    mod = processes{target_idx};
    gidx = mod.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = mod.substrateMetaboliteLocalIndexs;
    allocation = reshape(allocations(gidx, target_idx), size(gidx));
    counts = mets.counts(gidx);

    mod.simulationStateSideEffects = [];
    mod.copyFromState();
    mod.substrates(lidx, :) = allocation;

    pre_sub = mod.substrates;
    pre_enz = mod.enzymes;
    pre_bound = mod.boundEnzymes;

    bounds_t = mod.calcFluxBounds( ...
        mod.substrates, mod.enzymes, mod.fbaReactionBounds, mod.fbaEnzymeBounds);
    [growth_t, ~, flux_t] = mod.calcGrowthRate( ...
        bounds_t, mod.fbaObjective, mod.fbaReactionStoichiometryMatrix);

    fprintf('Allocated pre-state captured.\n');
    fprintf('  pre_sub sum_abs = %.4e, nonzero = %d\n', sum(abs(pre_sub(:))), sum(pre_sub(:) ~= 0));
    fprintf('  pre_enz sum = %d (all nonzero=%d)\n', sum(pre_enz), sum(pre_enz > 0));
    fprintf('FBA results:\n');
    fprintf('  growth = %.6e\n', growth_t);
    fprintf('  flux sum_abs = %.4e\n', sum(abs(flux_t)));
    fprintf('  flux nonzero = %d / %d\n', sum(flux_t ~= 0), numel(flux_t));

    mod.evolveState();
    post_sub = mod.substrates;
    delta_post_pre = post_sub - pre_sub;
    fprintf('After evolveState:\n');
    fprintf('  post - pre sum_abs = %.4e\n', sum(abs(delta_post_pre(:))));

    out = struct();
    out.x_seed = seed;
    out.x_target_proc_idx = target_idx;
    out.x_extract_timestamp_utc = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    out.allocation = allocation;
    out.pre_sub = pre_sub;
    out.pre_enz = pre_enz;
    out.pre_bound = pre_bound;
    out.bounds = bounds_t;
    out.flux = flux_t;
    out.growth = growth_t;
    out.post_sub = post_sub;
    out.delta = delta_post_pre;

    outFile = fullfile(outDir, sprintf('metab_flux_allocated_state_s%03d_tick1.mat', seed));
    save(outFile, '-struct', 'out', '-v7.3');
    fprintf('\nSaved %s\n', outFile);
end
