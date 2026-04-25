function extract_karr_m1_dynamics(wholecellRoot, outDir)
% EXTRACT_KARR_M1_DYNAMICS  Extract dynamic-bound inputs for M1's
% calcFluxBounds() port plus the resulting MATLAB bounds & flux
% (rule 6 / protein bounds disabled).  Pulls a small perturbation
% panel for index-trap detection in the Python port.
%
% Outputs:
%   out.snapshot_substrates          (585, 3)   counts at fitted snapshot
%   out.snapshot_enzymes             (104,)     enzyme counts
%   out.snapshot_cell_dry_mass       scalar     sum(this.mass.cellDry)
%   out.step_size_sec                scalar     this.stepSizeSec (= 1.0)
%   out.substrate_indexs_fba              (368,)  LINEAR indices into (585,3)
%   out.substrate_indexs_external_exch    (k,)    indices into 585 only
%   out.substrate_indexs_internal_lim     (m,)    indices into 585 only
%   out.compartment_indexs_extracellular  scalar  (=2)
%   out.fba_rxn_idx_metab_conv            indices into 504 (1-based)
%   out.fba_rxn_idx_external_exch         indices into 504
%   out.fba_rxn_idx_internal_lim_exch     indices into 504
%   out.fba_rxn_idx_internal_unlim_exch   indices into 504
%   out.fba_rxn_idx_biomass_production    indices into 504
%   out.fba_rxn_idx_biomass_exchange      indices into 504
%   out.bounds_dynamic_no_protein         (504, 2)  calcFluxBounds output
%
%   out.perturb_<name>.bounds             (504, 2) bounds under perturbation
%   out.perturb_<name>.description        text
%
% Usage:
%   >> cd('E:\opencell\data\m1_sources\WholeCell')
%   >> extract_karr_m1_dynamics(pwd, 'E:\opencell\data\m1_sources\karr_flat')

    if nargin < 1, wholecellRoot = pwd; end
    if nargin < 2, outDir = fullfile(wholecellRoot,'karr_flat'); end
    if ~exist(outDir,'dir'), mkdir(outDir); end

    cd(wholecellRoot);
    warning('off','all');
    setPath();

    fprintf('=== Loading Simulation_fitted.mat ===\n');
    s = load('data/Simulation_fitted.mat');
    sim = s.simulation;

    out = struct();
    out.x_source_sim = 'data/Simulation_fitted.mat';
    out.x_matlab_release = version('-release');
    out.x_extract_timestamp_utc = datestr(now,'yyyy-mm-ddTHH:MM:SS');

    % Find Process_Metabolism
    fprintf('\n--- Process_Metabolism ---\n');
    met = [];
    for i = 1:numel(sim.processes)
        if strcmp(sim.processes{i}.wholeCellModelID, 'Process_Metabolism')
            met = sim.processes{i}; break;
        end
    end
    assert(~isempty(met), 'Process_Metabolism not found');
    fprintf('  class=%s\n', class(met));

    % ---------- snapshot tensors ----------------------------------------
    fprintf('\n--- snapshot ---\n');
    out.snapshot_substrates = met.substrates;       % (585, 3)
    out.snapshot_enzymes    = met.enzymes;          % (104,)
    out.step_size_sec       = met.stepSizeSec;
    fprintf('  substrates size = %s\n', mat2str(size(met.substrates)));
    fprintf('  enzymes size    = %s\n', mat2str(size(met.enzymes)));
    fprintf('  stepSizeSec     = %g\n', met.stepSizeSec);

    % cellDryMass via the same accessor calcFluxBounds uses
    try
        cdm = sum(met.mass.cellDry);
    catch e
        fprintf('  WARN cellDryMass via met.mass.cellDry failed: %s\n', e.message);
        cdm = NaN;
    end
    out.snapshot_cell_dry_mass = cdm;
    fprintf('  cellDryMass     = %g\n', cdm);

    % ---------- index maps ---------------------------------------------
    fprintf('\n--- index maps ---\n');
    out.substrate_indexs_fba           = met.substrateIndexs_fba;
    out.substrate_indexs_external_exch = met.substrateIndexs_externalExchangedMetabolites;
    out.substrate_indexs_internal_lim  = met.substrateIndexs_internalExchangedLimitedMetabolites;
    out.compartment_indexs_extracellular = met.compartmentIndexs_extracellular;
    out.compartment_indexs_cytosol       = met.compartmentIndexs_cytosol;
    out.compartment_indexs_membrane      = met.compartmentIndexs_membrane;

    out.fba_rxn_idx_metab_conv          = met.fbaReactionIndexs_metabolicConversion;
    out.fba_rxn_idx_external_exch       = met.fbaReactionIndexs_metaboliteExternalExchange;
    out.fba_rxn_idx_internal_exch       = met.fbaReactionIndexs_metaboliteInternalExchange;
    out.fba_rxn_idx_internal_lim_exch   = met.fbaReactionIndexs_metaboliteInternalLimitedExchange;
    out.fba_rxn_idx_internal_unlim_exch = met.fbaReactionIndexs_metaboliteInternalUnlimitedExchange;
    out.fba_rxn_idx_biomass_production  = met.fbaReactionIndexs_biomassProduction;
    out.fba_rxn_idx_biomass_exchange    = met.fbaReactionIndexs_biomassExchange;

    fprintf('  substrateIndexs_fba (linear into [585 3]) = %d entries\n', numel(met.substrateIndexs_fba));
    fprintf('  substrateIndexs_externalExch = %d entries\n', numel(met.substrateIndexs_externalExchangedMetabolites));
    fprintf('  substrateIndexs_internalLim  = %d entries\n', numel(met.substrateIndexs_internalExchangedLimitedMetabolites));
    fprintf('  fbaReactionIndexs_externalExch  = %d entries\n', numel(met.fbaReactionIndexs_metaboliteExternalExchange));
    fprintf('  fbaReactionIndexs_internalLimExch = %d entries\n', numel(met.fbaReactionIndexs_metaboliteInternalLimitedExchange));

    % ---------- main bounds: snapshot, no protein bounds ---------------
    fprintf('\n--- calcFluxBounds (no protein bounds) ---\n');
    bounds_dyn = met.calcFluxBounds( ...
        met.substrates, met.enzymes, met.fbaReactionBounds, met.fbaEnzymeBounds, ...
        true, ...   % applyEnzymeKineticBounds
        true, ...   % applyEnzymeBounds
        true, ...   % applyDirectionalityBounds
        true, ...   % applyExternalMetaboliteBounds
        true, ...   % applyInternalMetaboliteBounds
        false ...   % applyProteinBounds  (rule 6 deferred)
    );
    out.bounds_dynamic_no_protein = bounds_dyn;
    fprintf('  bounds size = %s\n', mat2str(size(bounds_dyn)));
    fprintf('  finite lower count = %d / %d\n', ...
        sum(isfinite(bounds_dyn(:,1))), size(bounds_dyn,1));
    fprintf('  finite upper count = %d / %d\n', ...
        sum(isfinite(bounds_dyn(:,2))), size(bounds_dyn,1));

    % Also pull the WITH-protein-bounds version for reference / Phase C
    try
        bounds_full = met.calcFluxBounds( ...
            met.substrates, met.enzymes, met.fbaReactionBounds, met.fbaEnzymeBounds, ...
            true, true, true, true, true, true);
        out.bounds_dynamic_with_protein = bounds_full;
        fprintf('  with-protein bounds also dumped\n');
    catch e
        fprintf('  WARN with-protein bounds failed: %s\n', e.message);
    end

    % ---------- perturbation panel -------------------------------------
    fprintf('\n--- perturbation panel ---\n');
    perturbs = {};

    % P1: zero a single enzyme (the first non-zero one)
    enz0 = met.enzymes;
    nz_enz = find(enz0 > 0, 1, 'first');
    if ~isempty(nz_enz)
        enz_p = enz0;  enz_p(nz_enz) = 0;
        bp = met.calcFluxBounds(met.substrates, enz_p, met.fbaReactionBounds, met.fbaEnzymeBounds, ...
            true, true, true, true, true, false);
        perturbs{end+1} = struct('name','zero_first_enzyme', ...
            'desc', sprintf('enzyme %d set to 0', nz_enz), ...
            'enzyme_idx', nz_enz, 'bounds', bp);
    end

    % P2: zero one extracellular substrate (first external-exchanged)
    sub_p = met.substrates;
    ext_idx = met.substrateIndexs_externalExchangedMetabolites;
    if ~isempty(ext_idx)
        idx0 = ext_idx(1);
        sub_p(idx0, met.compartmentIndexs_extracellular) = 0;
        bp = met.calcFluxBounds(sub_p, met.enzymes, met.fbaReactionBounds, met.fbaEnzymeBounds, ...
            true, true, true, true, true, false);
        perturbs{end+1} = struct('name','zero_first_external_substrate', ...
            'desc', sprintf('substrate(%d, extracellular) -> 0', idx0), ...
            'substrate_idx', idx0, 'bounds', bp);
    end

    % P3: zero one internal-limited substrate (cytosol slice)
    sub_p = met.substrates;
    int_idx = met.substrateIndexs_internalExchangedLimitedMetabolites;
    if ~isempty(int_idx)
        idx0 = int_idx(1);
        sub_p(idx0) = 0;  % MATLAB linear indexing: hits cytosol slice
        bp = met.calcFluxBounds(sub_p, met.enzymes, met.fbaReactionBounds, met.fbaEnzymeBounds, ...
            true, true, true, true, true, false);
        perturbs{end+1} = struct('name','zero_first_internal_lim_substrate', ...
            'desc', sprintf('substrate(%d, cytosol via linear idx) -> 0', idx0), ...
            'substrate_idx', idx0, 'bounds', bp);
    end

    % P4: 2x cellDryMass (rule 4 scaling)
    %    calcFluxBounds reads mass internally; we cannot pass it in,
    %    but we can monkey-set met.mass via a temporary copy if accessible.
    %    Skip for now and document the gap; Python port will validate
    %    rule 4 via P2 instead.

    out.perturbs = perturbs;
    fprintf('  panel size = %d\n', numel(perturbs));

    % ---------- save ----------------------------------------------------
    outFile = fullfile(outDir, 'metabolism_dynamics.mat');
    save(outFile, '-struct', 'out', '-v7.3');
    fprintf('\nSaved %s\n', outFile);
end
