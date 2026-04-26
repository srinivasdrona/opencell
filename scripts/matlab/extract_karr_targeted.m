function extract_karr_targeted(wholecellRoot, outDir)
% EXTRACT_KARR_TARGETED  Extract just the M1-relevant data from Karr's
% Simulation_fitted.mat + knowledgeBase.mat into Python-readable structs.
%
% Targeted (not generic) — pulls specific properties known to matter for
% M1 validation: parameters, fittedConstants, biomass composition,
% metabolism stoichiometry, growth rate. Avoids the handle-graph cycles
% that hang generic walkers.
%
% Usage:
%   >> cd('E:\opencell\data\m1_sources\WholeCell')
%   >> extract_karr_targeted(pwd, 'E:\opencell\data\m1_sources\karr_flat')

    if nargin < 1, wholecellRoot = pwd; end
    if nargin < 2, outDir = fullfile(wholecellRoot,'karr_flat'); end
    if ~exist(outDir,'dir'), mkdir(outDir); end

    cd(wholecellRoot);
    setWarnings();
    setPath();

    fprintf('=== Loading Simulation_fitted.mat ===\n');
    s = load('data/Simulation_fitted.mat');
    sim = s.simulation;
    fprintf('  simulation class: %s\n', class(sim));

    out = struct();
    out.x_source_file = 'data/Simulation_fitted.mat';
    out.x_matlab_release = version('-release');
    out.x_extract_timestamp_utc = datestr(now,'yyyy-mm-ddTHH:MM:SS');
    out.knowledgeBaseWID = s.knowledgeBaseWID;

    % --- 1. Top-level parameters via simulation.getParameters() --------
    fprintf('\n--- getParameters() ---\n');
    try
        p = sim.getParameters();
        out.parameters = safeFlatten(p, 6);
        fprintf('  ok. classes: %s\n', class(p));
    catch e
        out.parameters_err = e.message;
        fprintf('  FAIL: %s\n', e.message);
    end

    % --- 2. Fitted constants via simulation.getFittedConstants() -------
    fprintf('\n--- getFittedConstants() ---\n');
    try
        fc = sim.getFittedConstants();
        out.fittedConstants = safeFlatten(fc, 6);
        fprintf('  ok.\n');
    catch e
        out.fittedConstants_err = e.message;
        fprintf('  FAIL: %s\n', e.message);
    end

    % --- 3. Options ----------------------------------------------------
    fprintf('\n--- getOptions() ---\n');
    try
        opts = sim.getOptions();
        out.options = safeFlatten(opts, 6);
        fprintf('  ok.\n');
    catch e
        out.options_err = e.message;
        fprintf('  FAIL: %s\n', e.message);
    end

    % --- 4. Process-level extraction (just the names + parameters) -----
    fprintf('\n--- processes ---\n');
    procs_out = struct();
    try
        procs = sim.processes;
        for i = 1:numel(procs)
            p = procs{i};
            wid = p.wholeCellModelID;
            % Sanitise wid -> valid struct field
            fname = regexprep(wid, '[^A-Za-z0-9_]', '_');
            if regexp(fname,'^[0-9]'), fname = ['p_' fname]; end
            entry = struct();
            entry.x_class = class(p);
            entry.wholeCellModelID = wid;
            try, entry.name = p.name; catch, end
            try, entry.parameters = safeFlatten(p.getParameters(), 5); catch e, entry.parameters_err = e.message; end
            try, entry.fittedConstants = safeFlatten(p.getFittedConstants(), 5); catch e, entry.fittedConstants_err = e.message; end
            procs_out.(fname) = entry;
            fprintf('  %s\n', wid);
        end
    catch e
        fprintf('  enumeration FAIL: %s\n', e.message);
    end
    out.processes = procs_out;

    % --- 5. Special: full Metabolism process deep-dump -----------------
    fprintf('\n--- Metabolism (deep) ---\n');
    try
        met = [];
        for i = 1:numel(sim.processes)
            if strcmp(sim.processes{i}.wholeCellModelID, 'Process_Metabolism') ...
               || strcmp(sim.processes{i}.wholeCellModelID, 'Metabolism')
                met = sim.processes{i};
                break;
            end
        end
        if isempty(met)
            fprintf('  no Metabolism process found by id\n');
        else
            metOut = struct();
            metOut.x_class = class(met);
            % Targeted properties known to matter for FBA
            wishlist = {'reactionWholeCellModelIDs','reactionNames', ...
                'substrateWholeCellModelIDs','substrateNames', ...
                'enzymeWholeCellModelIDs','enzymeNames', ...
                'reactionStoichiometryMatrix','reactionBounds', ...
                'fbaObjective','fbaReactionBounds', ...
                'fbaReactionStoichiometryMatrix','fbaSubstrateNames', ...
                'fbaReactionNames','fbaEnzymeBounds', ...
                'reactionCatalysisMatrix','enzymeBounds', ...
                'unaccountedEnergyConsumption','growthAssociatedMaintenance', ...
                'nonGrowthAssociatedMaintenance', ...
                'macromoleculeStateInitializationGrowthFactor', ...
                'biomassComposition','byproducts','growthAssociatedMaintenanceATP', ...
                'cellCycleLength','meanInitialGrowthRate', ...
                'fbaRightHandSide','fbaReactionCatalysisMatrix', ...
                'reactionTypes','reactionCoenzymeMatrix','reactionModificationMatrix', ...
                'substrateExternalExchangeBounds','substrateExchangeBounds', ...
                'exchangeRateUpperBound_carbon','exchangeRateUpperBound_noncarbon', ...
                'substrateMolecularWeights','enzymeMolecularWeights', ...
                'fbaSubstrateIndexs_substrates', ...
                'fbaSubstrateIndexs_metaboliteInternalExchangeConstraints', ...
                'fbaSubstrateIndexs_biomass', ...
                'fbaReactionIndexs_metabolicConversion', ...
                'fbaReactionIndexs_metaboliteExternalExchange', ...
                'fbaReactionIndexs_metaboliteInternalExchange', ...
                'fbaReactionIndexs_metaboliteInternalLimitedExchange', ...
                'fbaReactionIndexs_metaboliteInternalUnlimitedExchange', ...
                'fbaReactionIndexs_biomassProduction', ...
                'fbaReactionIndexs_biomassExchange', ...
                'reactionIndexs_chemical','reactionIndexs_transport','reactionIndexs_fba', ...
                'substrateIndexs_atp','substrateIndexs_adp','substrateIndexs_amp', ...
                'substrateIndexs_phosphate','substrateIndexs_diphosphate', ...
                'substrateIndexs_water','substrateIndexs_hydrogen', ...
                'substrateIndexs_atpHydrolysis','substrateIndexs_energy', ...
                'substrateIndexs_fba', ...
                'substrateIndexs_externalExchangedMetabolites', ...
                'substrateIndexs_internalExchangedMetabolites', ...
                'substrateIndexs_internalExchangedLimitedMetabolites'};
            for w = 1:numel(wishlist)
                k = wishlist{w};
                try
                    v = met.(k);
                    metOut.(k) = safeFlatten(v, 4);
                catch
                    % property doesn't exist on this class; skip silently
                end
            end
            % Also: dump ALL property names so we can audit later
            try
                mc = metaclass(met);
                pnames = cell(numel(mc.PropertyList),1);
                for k = 1:numel(mc.PropertyList)
                    pnames{k} = mc.PropertyList(k).Name;
                end
                metOut.x_all_property_names = pnames;
            catch
            end
            out.metabolism = metOut;
            fprintf('  ok.\n');
        end
    catch e
        out.metabolism_err = e.message;
        fprintf('  FAIL: %s\n', e.message);
    end

    % --- 6. Initial state: metabolites + cell mass ---------------------
    fprintf('\n--- states ---\n');
    states_out = struct();
    try
        for i = 1:numel(sim.states)
            st = sim.states{i};
            wid = st.wholeCellModelID;
            fname = regexprep(wid,'[^A-Za-z0-9_]','_');
            if regexp(fname,'^[0-9]'), fname = ['s_' fname]; end
            entry = struct();
            entry.x_class = class(st);
            entry.wholeCellModelID = wid;
            try, entry.name = st.name; catch, end
            try, entry.stateNames = st.stateNames; catch, end
            % For Metabolite & MetabolicReaction, dump everything shallow:
            if ~isempty(strfind(class(st),'Metabolite')) ...
               || ~isempty(strfind(class(st),'MetabolicReaction')) ...
               || ~isempty(strfind(class(st),'Mass')) ...
               || ~isempty(strfind(class(st),'CellGeometry'))
                try
                    entry.dump = safeFlatten(st, 3);
                catch e
                    entry.dump_err = e.message;
                end
            end
            states_out.(fname) = entry;
            fprintf('  %s\n', wid);
        end
    catch e
        fprintf('  enumeration FAIL: %s\n', e.message);
    end
    out.states = states_out;

    % --- 7. Save flat MAT v7 -------------------------------------------
    flatMat = fullfile(outDir, 'sim_fitted_targeted.mat');
    data = out; %#ok<NASGU>
    save(flatMat, 'data', '-v7');
    fprintf('\n[OK] wrote %s\n', flatMat);

    % --- 8. Knowledge base -- separate, smaller --------------------------
    fprintf('\n=== Loading knowledgeBase.mat ===\n');
    try
        kb = load('data/knowledgeBase.mat');
        kbOut = struct();
        kbOut.x_source_file = 'data/knowledgeBase.mat';
        kbOut.x_matlab_release = version('-release');
        fns = fieldnames(kb);
        for k = 1:numel(fns)
            try
                kbOut.(fns{k}) = safeFlatten(kb.(fns{k}), 4);
                fprintf('  KB.%s ok\n', fns{k});
            catch e
                kbOut.([fns{k} '_err']) = e.message;
                fprintf('  KB.%s FAIL: %s\n', fns{k}, e.message);
            end
        end
        kbMat = fullfile(outDir,'knowledgeBase_targeted.mat');
        data = kbOut; %#ok<NASGU>
        save(kbMat,'data','-v7');
        fprintf('[OK] wrote %s\n', kbMat);
    catch e
        fprintf('KB load FAIL: %s\n', e.message);
    end

    % --- 9. M3 protein-monomer targeted dump (deep properties) ----------
    fprintf('\n=== M3 protein dump (sim.state.ProteinMonomer) ===\n');
    try
        pmstate = [];
        for i = 1:numel(sim.states)
            if strcmp(sim.states{i}.wholeCellModelID,'State_ProteinMonomer')
                pmstate = sim.states{i}; break;
            end
        end
        if isempty(pmstate)
            fprintf('  no State_ProteinMonomer found\n');
        else
            protOut = struct();
            % per-form indexs (482 each into 4820 vector)
            protOut.matureIndexs = pmstate.matureIndexs;
            protOut.nascentIndexs = pmstate.nascentIndexs;
            protOut.processedIIndexs = pmstate.processedIIndexs;
            protOut.processedIIIndexs = pmstate.processedIIIndexs;
            protOut.foldedIndexs = pmstate.foldedIndexs;
            protOut.inactivatedIndexs = pmstate.inactivatedIndexs;
            protOut.boundIndexs = pmstate.boundIndexs;
            protOut.misfoldedIndexs = pmstate.misfoldedIndexs;
            protOut.damagedIndexs = pmstate.damagedIndexs;
            protOut.signalSequenceIndexs = pmstate.signalSequenceIndexs;
            % full 4820-vec arrays (we slice to mature in Python)
            protOut.lengths = pmstate.lengths;
            protOut.halfLives = pmstate.halfLives;
            protOut.decayRates = pmstate.decayRates;
            protOut.molecularWeights = pmstate.molecularWeights;
            protOut.compartments = pmstate.compartments;
            protOut.counts = pmstate.counts;
            try, protOut.baseCounts = pmstate.baseCounts; catch, end
            try, protOut.wholeCellModelIDs = pmstate.wholeCellModelIDs; catch, end
            try, protOut.names = pmstate.names; catch, end
            % Walk the 482 KB ProteinMonomer stubs to grab wcm + gene index
            try
                skb = load('data/knowledgeBase.mat'); kbobj = skb.knowledgeBase;
                pms = kbobj.proteinMonomers; nP = numel(pms);
                wcm = cell(nP,1);
                geneWcm = cell(nP,1);
                geneIdx = nan(nP,1);
                compWcm = cell(nP,1);
                for i = 1:nP
                    p = pms(i);
                    try, wcm{i} = p.wholeCellModelID; catch, end
                    try
                        % gene cell ref: {className, idxUint32}
                        g = p.gene;
                        if iscell(g) && numel(g)>=2
                            geneIdx(i) = double(g{2});
                            geneWcm{i} = kbobj.genes(double(g{2})).wholeCellModelID;
                        end
                    catch, end
                    try
                        c = p.compartment;
                        if iscell(c) && numel(c)>=2
                            compWcm{i} = kbobj.compartments(double(c{2})).wholeCellModelID;
                        end
                    catch, end
                end
                protOut.kb_wholeCellModelIDs = wcm;
                protOut.kb_geneWholeCellModelIDs = geneWcm;
                protOut.kb_geneIndex = geneIdx;
                protOut.kb_compartmentWholeCellModelIDs = compWcm;
            catch e
                fprintf('  KB walk FAIL: %s\n', e.message);
            end
            % Process_Translation parameters (live)
            try
                for i = 1:numel(sim.processes)
                    if strcmp(sim.processes{i}.wholeCellModelID,'Process_Translation')
                        pt = sim.processes{i};
                        try, protOut.translation_ribosomeElongationRate = pt.ribosomeElongationRate; catch, end
                        try, protOut.translation_tmRNABindingProbability = pt.tmRNABindingProbability; catch, end
                        break;
                    end
                end
            catch, end
            protMat = fullfile(outDir,'proteins_targeted.mat');
            data = protOut; %#ok<NASGU>
            save(protMat,'data','-v7');
            fprintf('[OK] wrote %s (n=%d, fields: lengths/halfLives/decayRates/counts)\n', protMat, numel(protOut.matureIndexs));
        end
    catch e
        fprintf('protein dump FAIL: %s\n', e.message);
    end

    % --- 10. M2 RNA-state targeted dump (deep properties) for E.1b cell mass --
    fprintf('\n=== M2 RNA dump (sim.state.Rna) ===\n');
    try
        extract_rna_state(sim, outDir);
    catch e
        fprintf('rna dump FAIL: %s\n', e.message);
    end

    fprintf('\n=== DONE ===\n');
end


function out = extract_rna_state(sim, outDir)
% E.1b extension: dump State_Rna full molecular-weight + form indexes
% (mature index pulls 525 mature RNA species out of the 5*525 raw vector).
    out = struct();
    rnastate = [];
    for i = 1:numel(sim.states)
        if strcmp(sim.states{i}.wholeCellModelID,'State_Rna')
            rnastate = sim.states{i}; break;
        end
    end
    if isempty(rnastate)
        fprintf('  no State_Rna found\n');
        return;
    end
    rnaOut = struct();
    % Per-form indexs (each ~525 long; same convention as ProteinMonomer)
    try, rnaOut.matureIndexs = rnastate.matureIndexs; catch, end
    try, rnaOut.nascentIndexs = rnastate.nascentIndexs; catch, end
    try, rnaOut.processedIndexs = rnastate.processedIndexs; catch, end
    try, rnaOut.intergenicIndexs = rnastate.intergenicIndexs; catch, end
    try, rnaOut.boundIndexs = rnastate.boundIndexs; catch, end
    try, rnaOut.misfoldedIndexs = rnastate.misfoldedIndexs; catch, end
    try, rnaOut.damagedIndexs = rnastate.damagedIndexs; catch, end
    try, rnaOut.aminoacylatedIndexs = rnastate.aminoacylatedIndexs; catch, end
    % Per-RNA arrays (full length ~ 5*525 = 2625)
    try, rnaOut.molecularWeights = rnastate.molecularWeights; catch, end
    try, rnaOut.lengths = rnastate.lengths; catch, end
    try, rnaOut.halfLives = rnastate.halfLives; catch, end
    try, rnaOut.decayRates = rnastate.decayRates; catch, end
    try, rnaOut.compartments = rnastate.compartments; catch, end
    try, rnaOut.counts = rnastate.counts; catch, end
    try, rnaOut.expression = rnastate.expression; catch, end
    try, rnaOut.wholeCellModelIDs = rnastate.wholeCellModelIDs; catch, end
    try, rnaOut.names = rnastate.names; catch, end
    try, rnaOut.types = rnastate.types; catch, end
    try, rnaOut.baseCounts = rnastate.baseCounts; catch, end

    % Walk KB to expose gene <-> TU index mapping (safeFlatten hits MAX_DEPTH)
    try
        skb = load('data/knowledgeBase.mat'); kbobj = skb.knowledgeBase;
        nGenes = numel(kbobj.genes);
        nTus = numel(kbobj.transcriptionUnits);
        gene_wcm = cell(nGenes,1);
        tu_wcm = cell(nTus,1);
        gene_to_tu_idx = zeros(nGenes,1,'uint32');
        for i = 1:nGenes
            g = kbobj.genes(i);
            try, gene_wcm{i} = g.wholeCellModelID; catch, end
            try
                tuRef = g.transcriptionUnits;
                if iscell(tuRef) && numel(tuRef)>=2
                    gene_to_tu_idx(i) = uint32(tuRef{2}(1));  % first TU
                end
            catch
            end
        end
        % TU -> contained gene indices
        tu_to_gene_idxs = cell(nTus,1);
        for i = 1:nTus
            t = kbobj.transcriptionUnits(i);
            try, tu_wcm{i} = t.wholeCellModelID; catch, end
            try
                gRef = t.genes;
                if iscell(gRef) && numel(gRef)>=2
                    tu_to_gene_idxs{i} = uint32(gRef{2});
                end
            catch
            end
        end
        rnaOut.kb_gene_wholeCellModelIDs = gene_wcm;
        rnaOut.kb_tu_wholeCellModelIDs = tu_wcm;
        rnaOut.kb_gene_to_tu_index = gene_to_tu_idx;
        rnaOut.kb_tu_to_gene_indices = tu_to_gene_idxs;
        fprintf('  gene<->TU map ok: %d genes -> %d TUs\n', nGenes, nTus);
    catch e
        fprintf('  gene<->TU walk FAIL: %s\n', e.message);
    end

    rnaMat = fullfile(outDir,'rnas_targeted.mat');
    data = rnaOut; %#ok<NASGU>
    save(rnaMat,'data','-v7');
    n = 0; try, n = numel(rnaOut.matureIndexs); catch, end
    fprintf('[OK] wrote %s (n_mature=%d, has fields: molecularWeights/lengths/halfLives/counts + gene<->TU map)\n', rnaMat, n);
    out = rnaOut;
end


function out = safeFlatten(x, maxDepth)
% Iterative-ish flattener with strict depth cap and handle-cycle catch.
% Uses persistent visited set within a single call via nested tracker.
    visited = struct('addrs',{cell(0)}, 'count', 0);
    out = doFlatten(x, 0, maxDepth, visited);
end

function out = doFlatten(x, depth, maxDepth, visited)
    if depth >= maxDepth
        out = sprintf('<MAX_DEPTH:%s>', class(x));
        return;
    end

    if isnumeric(x) || islogical(x) || ischar(x)
        out = x; return;
    end

    if isstring(x)
        out = char(x); return;
    end

    if isa(x,'function_handle')
        out = sprintf('<fh:%s>', func2str(x)); return;
    end

    if iscell(x)
        out = cell(size(x));
        for k = 1:numel(x)
            out{k} = doFlatten(x{k}, depth+1, maxDepth, visited);
        end
        return;
    end

    if isstruct(x)
        if numel(x) > 1
            out = cell(size(x));
            for k = 1:numel(x)
                out{k} = doFlatten(x(k), depth+1, maxDepth, visited);
            end
        else
            out = struct();
            fns = fieldnames(x);
            for f = 1:numel(fns)
                try
                    out.(fns{f}) = doFlatten(x.(fns{f}), depth+1, maxDepth, visited);
                catch e
                    out.(fns{f}) = sprintf('<unreadable:%s>', e.identifier);
                end
            end
        end
        return;
    end

    if isobject(x)
        % cycle check (handle classes only; scan visited list)
        if isscalar(x) && isa(x,'handle')
            for k = 1:numel(visited.addrs)
                try
                    if visited.addrs{k} == x
                        out = sprintf('<cycle:%s>', class(x));
                        return;
                    end
                catch
                end
            end
            visited.addrs{end+1} = x; %#ok<NASGU>
        end

        if numel(x) > 1
            out = cell(size(x));
            for k = 1:numel(x)
                out{k} = doFlatten(x(k), depth+1, maxDepth, visited);
            end
            return;
        end

        out = struct();
        out.x_class_ = class(x);
        try
            s = struct(x);
            fns = fieldnames(s);
            for f = 1:numel(fns)
                try
                    out.(fns{f}) = doFlatten(s.(fns{f}), depth+1, maxDepth, visited);
                catch e
                    out.(fns{f}) = sprintf('<unreadable:%s>', e.identifier);
                end
            end
        catch e
            out.x_struct_err_ = e.message;
        end
        return;
    end

    out = sprintf('<unhandled:%s>', class(x));
end
