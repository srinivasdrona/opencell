function extract_metab_flux_per_tick(wholecellRoot, outDir, traceRoot, seedFirst, seedLast, tickFirst, tickLast)
% Extract Karr's Metabolism flux at every tick of a recorded per-tick trace,
% by injecting Karr's recorded pre_sub, pre_enz, pre_bound at each tick
% and running calcFluxBounds + calcGrowthRate. Saves one .mat per (seed, tick)
% with the same schema as extract_metab_flux_v3 output.
%
% Usage:
%   extract_metab_flux_per_tick('E:/opencell/data/m1_sources/WholeCell', ...
%                               'E:/opencell/data/karr_fixtures/matlab_ground_truth/per_tick', ...
%                               'E:/opencell/data/m1_sources/karr_native', ...
%                               uint32(0), uint32(0), 1, 100)
%
% Arguments
%   wholecellRoot : path to CovertLab WholeCell repo root (has setPath.m, data/Simulation_fitted.mat)
%   outDir        : output directory for per-tick .mat files
%   traceRoot     : path to per_process_traces_v2_s{NNN}/ tree
%   seedFirst     : first seed to extract (uint32)
%   seedLast      : last seed to extract (uint32, inclusive)
%   tickFirst     : first tick index (1-based, matching Karr trace indexing)
%   tickLast      : last tick index (inclusive)
%
% Output: outDir/metab_flux_per_tick_s{NNN}_t{TT}.mat for each (seed, tick)
%
% Companion to extract_metab_flux_v3.m (single-tick extractor). This version
% iterates many ticks at fixed pre-states from Karr's recorded trace, without
% running evolveState (so no Statistics Toolbox dependency for other processes).

    if nargin < 6, tickFirst = 1; end
    if nargin < 7, tickLast = 100; end
    if ~exist(outDir, 'dir'), mkdir(outDir); end

    origDir = pwd;
    cleanup = onCleanup(@() cd(origDir));
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
    fprintf('Target: Metabolism (proc_idx=%d)\n', target_idx);

    mod = sim.processes{target_idx};

    for seedVal = uint32(seedFirst:seedLast)
        traceFile = fullfile(traceRoot, sprintf('per_process_traces_v2_s%03d', seedVal), ...
                             'Metabolism_100ticks.mat');
        if ~exist(traceFile, 'file')
            fprintf('SKIP seed=%d: trace file not found: %s\n', seedVal, traceFile);
            continue;
        end
        fprintf('\n=== seed=%d: loading trace %s ===\n', seedVal, traceFile);
        % v7.3 .mat needs matfile() for object refs
        mf = matfile(traceFile);
        stbf = mf.states_before;
        % stbf.substrates is a 1x100 cell of (3 x 585) arrays
        sub_cells = stbf.substrates;
        enz_cells = stbf.enzymes;
        if isfield(stbf, 'boundEnzymes')
            bound_cells = stbf.boundEnzymes;
        else
            bound_cells = [];
        end

        n_ticks_in_trace = numel(sub_cells);
        fprintf('  trace has %d ticks; extracting ticks %d..%d\n', ...
                n_ticks_in_trace, tickFirst, min(tickLast, n_ticks_in_trace));

        for t = tickFirst:min(tickLast, n_ticks_in_trace)
            outFile = fullfile(outDir, sprintf('metab_flux_per_tick_s%03d_t%03d.mat', seedVal, t));
            if exist(outFile, 'file')
                continue;  % idempotent
            end

            pre_sub = sub_cells{t};   % (3 x 585) — TRANSPOSED from python's (585, 3)
            pre_enz = enz_cells{t};   % (1 x 104)
            if iscell(bound_cells) && ~isempty(bound_cells)
                pre_bound = bound_cells{t};
            else
                pre_bound = [];
            end

            % MATLAB Metabolism stores substrates as (585 x 3) per its accessor
            % conventions; double-check by reshape if needed.
            if size(pre_sub, 1) == 3 && size(pre_sub, 2) == 585
                pre_sub_matlab = pre_sub';   % -> (585, 3)
            elseif size(pre_sub, 1) == 585 && size(pre_sub, 2) == 3
                pre_sub_matlab = pre_sub;
            else
                error('Unexpected pre_sub shape at seed=%d t=%d: [%d %d]', ...
                      seedVal, t, size(pre_sub, 1), size(pre_sub, 2));
            end

            mod.simulationStateSideEffects = [];
            mod.substrates = pre_sub_matlab;
            mod.enzymes = pre_enz(:);  % (104, 1) column
            if ~isempty(pre_bound)
                if size(pre_bound, 1) == 1
                    mod.boundEnzymes = pre_bound(:);
                else
                    mod.boundEnzymes = pre_bound;
                end
            end

            bounds_t = mod.calcFluxBounds( ...
                mod.substrates, mod.enzymes, mod.fbaReactionBounds, mod.fbaEnzymeBounds);
            [growth_t, ~, flux_t] = mod.calcGrowthRate( ...
                bounds_t, mod.fbaObjective, mod.fbaReactionStoichiometryMatrix);

            out = struct();
            out.x_seed = seedVal;
            out.x_tick = uint32(t);
            out.x_target_proc_idx = target_idx;
            out.x_extract_timestamp_utc = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
            out.pre_sub = mod.substrates;
            out.pre_enz = mod.enzymes;
            if ~isempty(pre_bound), out.pre_bound = mod.boundEnzymes; end
            out.bounds = bounds_t;
            out.flux = flux_t;
            out.growth = growth_t;

            save(outFile, '-struct', 'out', '-v7.3');
            if mod(t, 10) == 0 || t == tickFirst
                fprintf('  seed=%d t=%03d: growth=%.3e flux_L1=%.3e\n', ...
                        seedVal, t, growth_t, sum(abs(flux_t)));
            end
        end
        fprintf('  seed=%d: done.\n', seedVal);
    end
    fprintf('\nALL DONE.\n');
end
