function extract_protein_complexes(wholecellRoot, outDir)
% EXTRACT_PROTEIN_COMPLEXES  Pull complete protein-complex composition
% from Karr's knowledgeBase.mat into a flat JSON-friendly MAT.
%
% Walks kb.proteinComplexs (201 entries) and for each captures:
%   - wholeCellModelID, name, formation compartment WCM ID
%   - numSubunits, numDistinctSubunits, dnaFootprint
%   - composition: monomers, sub-complexes, metabolites, RNAs, prosthetic
%     groups, chaperone substrates -- each with WCM ID, coefficient, and
%     compartment WCM ID
%
% Sign convention from KB: each complex appears in its own biosynthesis
% with coefficient +1 (the product); reactant participants carry
% negative coefficients.
%
% Usage (from MATLAB R2026a):
%   >> cd('E:\opencell\data\m1_sources\WholeCell')
%   >> extract_protein_complexes(pwd, 'E:\opencell\data\m1_sources\karr_flat')

    if nargin < 1, wholecellRoot = pwd; end
    if nargin < 2, outDir = fullfile(wholecellRoot, 'karr_flat'); end
    if ~exist(outDir, 'dir'), mkdir(outDir); end

    cd(wholecellRoot);
    warning('off','all');
    addpath(genpath(fullfile(wholecellRoot,'lib')));
    addpath(genpath(fullfile(wholecellRoot,'src')));

    fprintf('=== Loading knowledgeBase.mat ===\n');
    s = load('data/knowledgeBase.mat');
    kb = s.knowledgeBase;
    fprintf('  kb class: %s\n', class(kb));

    nC = numel(kb.proteinComplexs);
    nM = numel(kb.proteinMonomers);
    nMet = numel(kb.metabolites);
    nRna = numel(kb.genes);  % gene-level RNA WIDs are on rna of monomer; complex.rnas refs RNAs
    nComp = numel(kb.compartments);
    fprintf('  complexes=%d, monomers=%d, metabolites=%d, compartments=%d\n', ...
        nC, nM, nMet, nComp);

    % Build lookup tables: WCM IDs by index for each KB class type.
    monomer_wid = cell(nM,1);
    for i = 1:nM
        try, monomer_wid{i} = kb.proteinMonomers(i).wholeCellModelID; catch, end
    end
    complex_wid = cell(nC,1);
    for i = 1:nC
        try, complex_wid{i} = kb.proteinComplexs(i).wholeCellModelID; catch, end
    end
    metabolite_wid = cell(nMet,1);
    for i = 1:nMet
        try, metabolite_wid{i} = kb.metabolites(i).wholeCellModelID; catch, end
    end
    compartment_wid = cell(nComp,1);
    for i = 1:nComp
        try, compartment_wid{i} = kb.compartments(i).wholeCellModelID; catch, end
    end
    % RNA refs in complex.rnas are TranscriptionUnit-level, but Karr
    % uses Gene-level RNA WCM IDs; pull both for safety.
    nTU = 0;
    try, nTU = numel(kb.transcriptionUnits); catch, end
    tu_wid = cell(nTU,1);
    for i = 1:nTU
        try, tu_wid{i} = kb.transcriptionUnits(i).wholeCellModelID; catch, end
    end
    gene_wid = cell(numel(kb.genes),1);
    for i = 1:numel(kb.genes)
        try, gene_wid{i} = kb.genes(i).wholeCellModelID; catch, end
    end

    fprintf('  monomer wid sample: %s, %s, %s\n', monomer_wid{1}, monomer_wid{2}, monomer_wid{3});
    fprintf('  complex wid sample: %s, %s, %s\n', complex_wid{1}, complex_wid{2}, complex_wid{3});
    fprintf('  metabolite wid sample: %s, %s, %s\n', metabolite_wid{1}, metabolite_wid{2}, metabolite_wid{3});
    fprintf('  compartments: ');
    for ci = 1:numel(compartment_wid)
        if ~isempty(compartment_wid{ci}) && ischar(compartment_wid{ci})
            fprintf('%s ', compartment_wid{ci});
        else
            fprintf('<empty> ');
        end
    end
    fprintf('\n');

    % Walk complexes.
    fprintf('\n=== Walking %d complexes ===\n', nC);
    out = struct();
    out.x_source_file = 'data/knowledgeBase.mat';
    out.x_matlab_release = version('-release');
    out.x_extract_timestamp_utc = datestr(now,'yyyy-mm-ddTHH:MM:SS');
    out.complex_wids_201 = complex_wid;
    out.monomer_wids_482 = monomer_wid;
    out.metabolite_wids_722 = metabolite_wid;
    out.compartment_wids_6 = compartment_wid;

    complexes = cell(nC, 1);
    for i = 1:nC
        c = kb.proteinComplexs(i);
        entry = struct();
        try, entry.wholeCellModelID = c.wholeCellModelID; catch, entry.wholeCellModelID = ''; end
        try, entry.name = c.name; catch, entry.name = ''; end
        try, entry.idx = i; catch, end
        try, entry.numSubunits = c.numSubunits; catch, end
        try, entry.numDistinctSubunits = c.numDistinctSubunits; catch, end
        try, entry.dnaFootprint = c.dnaFootprint; catch, end
        try, entry.density = c.density; catch, end
        try, entry.activationRule = c.activationRule; catch, end
        try
            cmpRef = c.compartment;
            if iscell(cmpRef) && numel(cmpRef) >= 2
                ci = double(cmpRef{2});
                if ci > 0 && ci <= nComp
                    entry.formation_compartment_wid = compartment_wid{ci};
                else
                    entry.formation_compartment_wid = '';
                end
            else
                entry.formation_compartment_wid = '';
            end
        catch e
            entry.formation_compartment_wid = '';
            entry.compartment_err = e.message;
        end

        % Resolve participants: monomer / complex / metabolite / prosthetic / RNA.
        entry.monomers      = resolveParticipants(c, 'proteinMonomers',   'proteinMonomerCoefficients',   'proteinMonomerCompartments',   monomer_wid,    compartment_wid);
        entry.subcomplexes  = resolveParticipants(c, 'proteinComplexs',   'proteinComplexCoefficients',   'proteinComplexCompartments',   complex_wid,    compartment_wid);
        entry.metabolites   = resolveParticipants(c, 'metabolites',       'metaboliteCoefficients',       'metaboliteCompartments',       metabolite_wid, compartment_wid);
        entry.prosthetic    = resolveParticipants(c, 'prostheticGroups',  'prostheticGroupCoefficients',  'prostheticGroupCompartments',  metabolite_wid, compartment_wid);
        entry.chaperones    = resolveParticipants(c, 'chaperoneSubstrates','chaperoneCoefficients',       'chaperoneCompartments',        metabolite_wid, compartment_wid);
        entry.rnas          = resolveParticipants(c, 'rnas',              'rnaCoefficients',              'rnaCompartments',              gene_wid,       compartment_wid);

        complexes{i} = entry;
        if mod(i, 25) == 0
            fprintf('  ... %d/%d (%s)\n', i, nC, entry.wholeCellModelID);
        end
    end
    out.complexes = complexes;

    outFile = fullfile(outDir, 'protein_complexes.mat');
    data = out; %#ok<NASGU>
    save(outFile, 'data', '-v7');
    fprintf('\n[OK] wrote %s\n', outFile);

    % Spot-check a few well-known complexes.
    fprintf('\n=== Spot checks ===\n');
    spot = {'DNA_GYRASE', 'RNA_POLYMERASE', 'RIBOSOME_30S', 'RIBOSOME_50S', 'RIBOSOME_70S', 'MG_213_214_298_6MER_ADP'};
    for s_i = 1:numel(spot)
        target = spot{s_i};
        for i = 1:nC
            if strcmp(complex_wid{i}, target)
                e = complexes{i};
                fprintf('--- %s (%s) ---\n', target, e.name);
                fprintf('  monomers (%d):\n', numel(e.monomers));
                for k = 1:min(numel(e.monomers), 5)
                    p = e.monomers{k};
                    fprintf('    %+d * %s @ %s\n', p.coefficient, p.molecule_wid, p.compartment_wid);
                end
                fprintf('  subcomplexes (%d):\n', numel(e.subcomplexes));
                for k = 1:min(numel(e.subcomplexes), 5)
                    p = e.subcomplexes{k};
                    fprintf('    %+d * %s @ %s\n', p.coefficient, p.molecule_wid, p.compartment_wid);
                end
                fprintf('  metabolites (%d), prosthetic (%d), chaperones (%d), rnas (%d)\n', ...
                    numel(e.metabolites), numel(e.prosthetic), numel(e.chaperones), numel(e.rnas));
                break;
            end
        end
    end
    fprintf('\n=== DONE ===\n');
end


function out = resolveParticipants(c, refField, coefField, cmpField, wid_table, comp_table)
% Resolve a cell-ref participant set into [{molecule_wid, coefficient,
% compartment_wid}, ...] using the supplied lookup tables.
    out = {};
    try
        ref = c.(refField);
        coefs = c.(coefField);
        cmpRef = c.(cmpField);
    catch
        return;
    end
    if isempty(coefs) || ~iscell(ref) || numel(ref) < 2
        return;
    end
    idxs = double(ref{2});
    if isempty(idxs), return; end
    n = numel(idxs);
    if numel(coefs) ~= n
        % Coefficients length mismatch: best-effort, take min.
        n = min(n, numel(coefs));
    end
    cmpIdxs = [];
    if iscell(cmpRef) && numel(cmpRef) >= 2
        cmpIdxs = double(cmpRef{2});
    end
    out = cell(n, 1);
    for k = 1:n
        idx = idxs(k);
        wid = '';
        if idx > 0 && idx <= numel(wid_table)
            wid = wid_table{idx};
        end
        cmpW = '';
        if k <= numel(cmpIdxs) && cmpIdxs(k) > 0 && cmpIdxs(k) <= numel(comp_table)
            cmpW = comp_table{cmpIdxs(k)};
        end
        out{k} = struct( ...
            'molecule_wid', wid, ...
            'coefficient', double(coefs(k)), ...
            'compartment_wid', cmpW, ...
            'molecule_idx_1based', idx);
    end
end
