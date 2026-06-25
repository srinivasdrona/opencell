function extract_karr_m1_flux_growth(wholecellRoot, outDir)
% EXTRACT_KARR_M1_FLUX_GROWTH  Extract Karr's MATLAB FBA flux vector and
% growth rate at the fitted snapshot. This is the ground truth OC's HiGHS
% solver needs to match (or get within calibrated tolerance of).
%
% Outputs:
%   out.snapshot_substrates    (585, 3)
%   out.snapshot_enzymes       (104,)
%   out.snapshot_cell_dry_mass scalar
%   out.bounds_dynamic         (504, 2)
%   out.fba_flux               (504,)  — the LP solution
%   out.growth_per_s           scalar  — biomass flux / s
%   out.fba_objective          (504,)  — objective vector used
%
% Usage:
%   >> cd('E:\opencell\data\m1_sources\WholeCell')
%   >> extract_karr_m1_flux_growth(pwd, 'E:\opencell\data\karr_fixtures\matlab_ground_truth')

    if nargin < 1, wholecellRoot = pwd; end
    if nargin < 2, outDir = fullfile(wholecellRoot, 'karr_flux_extract'); end
    if ~exist(outDir, 'dir'), mkdir(outDir); end

    cd(wholecellRoot);
    warning('off', 'all');
    setPath();

    fprintf('=== Loading Simulation_fitted.mat ===\n');
    s = load('data/Simulation_fitted.mat');
    sim = s.simulation;

    out = struct();
    out.x_source_sim = 'data/Simulation_fitted.mat';
    out.x_matlab_release = version('-release');
    out.x_extract_timestamp_utc = datestr(now, 'yyyy-mm-ddTHH:MM:SS');

    fprintf('\n--- Locating Process_Metabolism ---\n');
    met = [];
    for i = 1:numel(sim.processes)
        if strcmp(sim.processes{i}.wholeCellModelID, 'Process_Metabolism')
            met = sim.processes{i}; break;
        end
    end
    assert(~isempty(met), 'Process_Metabolism not found');
    fprintf('  class=%s\n', class(met));

    % Snapshot
    out.snapshot_substrates = met.substrates;
    out.snapshot_enzymes = met.enzymes;
    try
        out.snapshot_cell_dry_mass = sum(met.mass.cellDry);
    catch
        out.snapshot_cell_dry_mass = NaN;
    end
    out.step_size_sec = met.stepSizeSec;
    fprintf('  cellDryMass = %g\n', out.snapshot_cell_dry_mass);

    % Compute dynamic bounds (rules 1-5, no protein)
    fprintf('\n--- Computing dynamic bounds (no protein) ---\n');
    bounds_dyn = met.calcFluxBounds( ...
        met.substrates, met.enzymes, met.fbaReactionBounds, met.fbaEnzymeBounds, ...
        true, true, true, true, true, false);
    out.bounds_dynamic = bounds_dyn;
    fprintf('  bounds size = %s\n', mat2str(size(bounds_dyn)));

    % Get FBA objective
    out.fba_objective = met.fbaObjective;
    fprintf('  fbaObjective nonzero = %d\n', sum(out.fba_objective ~= 0));

    % NOW the critical step: run the LP using Karr's calcGrowthRate
    fprintf('\n--- Solving LP via calcGrowthRate ---\n');
    [growth, ~, fbaReactionFluxs] = met.calcGrowthRate( ...
        bounds_dyn, met.fbaObjective, met.fbaReactionStoichiometryMatrix);
    out.growth_per_s = growth;
    out.fba_flux = fbaReactionFluxs;
    fprintf('  growth_per_s = %.6e\n', growth);
    fprintf('  fba_flux size = %s\n', mat2str(size(fbaReactionFluxs)));
    fprintf('  fba_flux nonzero = %d / %d\n', ...
        sum(fbaReactionFluxs ~= 0), numel(fbaReactionFluxs));
    fprintf('  fba_flux sum_abs = %.4e\n', sum(abs(fbaReactionFluxs)));
    fprintf('  fba_flux min = %.4e, max = %.4e\n', ...
        min(fbaReactionFluxs), max(fbaReactionFluxs));

    % Also dump linear programming options for reproducibility
    out.linearProgrammingOptions = met.linearProgrammingOptions;
    out.realmax = met.realmax;
    fprintf('  realmax = %.0e\n', out.realmax);
    fprintf('  default solver = %s\n', out.linearProgrammingOptions.solver);

    % Save
    outFile = fullfile(outDir, 'metabolism_matlab_flux_growth.mat');
    save(outFile, '-struct', 'out', '-v7.3');
    fprintf('\nSaved %s\n', outFile);
end
