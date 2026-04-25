function extract_karr_m3v2(wholecellRoot, outDir)
% EXTRACT_KARR_M3V2  Mechanism inputs for translation v2:
%   - Ribosome counts (active / stalled / not-existing) from State_Ribosome
%   - Mature mRNA counts at the snapshot from State_Rna
%   - Polypeptide / Polypeptide-state monomerLengths (already in M3 fixture
%     as length_aa, but re-dump for cross-check)
%
% Usage:
%   >> cd('E:\opencell\data\m1_sources\WholeCell')
%   >> extract_karr_m3v2(pwd, 'E:\opencell\data\m1_sources\karr_flat')

    if nargin < 1, wholecellRoot = pwd; end
    if nargin < 2, outDir = fullfile(wholecellRoot,'karr_flat'); end
    if ~exist(outDir,'dir'), mkdir(outDir); end
    cd(wholecellRoot);
    warning('off','all');
    setPath();

    fprintf('=== Loading Simulation_fitted.mat ===\n');
    s = load('data/Simulation_fitted.mat');
    sim = s.simulation;

    fprintf('=== Loading knowledgeBase.mat ===\n');
    kbS = load('data/knowledgeBase.mat');
    kb = kbS.knowledgeBase;

    out = struct();
    out.x_source_sim = 'data/Simulation_fitted.mat';
    out.x_source_kb  = 'data/knowledgeBase.mat';
    out.x_matlab_release = version('-release');
    out.x_extract_timestamp_utc = datestr(now,'yyyy-mm-ddTHH:MM:SS');

    % ----------------------------------------------------------------
    % 1) State_Ribosome
    % ----------------------------------------------------------------
    fprintf('\n--- State_Ribosome ---\n');
    rb = [];
    for i = 1:numel(sim.states)
        if strcmp(sim.states{i}.wholeCellModelID,'State_Ribosome')
            rb = sim.states{i}; break;
        end
    end
    if isempty(rb)
        fprintf('  not found\n');
    else
        fprintf('  class=%s\n', class(rb));
        try, props = properties(rb); catch, props = {}; end
        out.rib_properties = props;
        for k = 1:numel(props)
            nm = props{k};
            try
                v = rb.(nm);
                if isnumeric(v) || islogical(v)
                    out.(['rib_' nm]) = v;
                end
            catch, end
        end
        % computed counts
        try, out.rib_nActive = rb.nActive; catch, end
        try, out.rib_nStalled = rb.nStalled; catch, end
        try, out.rib_nNotExist = rb.nNotExist; catch, end
        try, out.rib_states_vec = rb.states; catch, end
        try, out.rib_activeValue = rb.activeValue; catch, end
        try, out.rib_stalledValue = rb.stalledValue; catch, end
        try, out.rib_notExistValue = rb.notExistValue; catch, end
    end

    % ----------------------------------------------------------------
    % 2) Process_Translation snapshot enzymes/ribosomes/mRNAs
    % ----------------------------------------------------------------
    fprintf('\n--- Process_Translation ---\n');
    pt = [];
    for i = 1:numel(sim.processes)
        if strcmp(sim.processes{i}.wholeCellModelID,'Process_Translation')
            pt = sim.processes{i}; break;
        end
    end
    if ~isempty(pt)
        try, out.pt_ribosomeElongationRate = pt.ribosomeElongationRate; catch, end
        try, out.pt_enzymeWholeCellModelIDs = pt.enzymeWholeCellModelIDs; catch, end
        try, out.pt_enzymes = pt.enzymes; catch, end
        try, out.pt_boundEnzymes = pt.boundEnzymes; catch, end
        try
            rh = pt.ribosomes;
            try, out.pt_ribosomes_nActive = rh.nActive; catch, end
            try, out.pt_ribosomes_nStalled = rh.nStalled; catch, end
            try, out.pt_ribosomes_nNotExist = rh.nNotExist; catch, end
            try, out.pt_ribosomes_states = rh.states; catch, end
        catch, end
        try, out.pt_mRNAs = pt.mRNAs; catch, end  % copy counts used as binding probs
        try, out.pt_freeTRNAs = pt.freeTRNAs; catch, end
        try, out.pt_aminoacylatedTRNAs = pt.aminoacylatedTRNAs; catch, end
        try
            pp = pt.polypeptide;
            try, out.pt_polypeptide_monomerLengths = pp.monomerLengths; catch, end
        catch, end
        try, out.pt_substrateWholeCellModelIDs = pt.substrateWholeCellModelIDs; catch, end
        try, out.pt_substrateIndexs_gtp = pt.substrateIndexs_gtp; catch, end
        try, out.pt_substrateIndexs_water = pt.substrateIndexs_water; catch, end
    end

    % ----------------------------------------------------------------
    % 3) State_Rna mature mRNA counts at the snapshot (cross-check
    %    against M2 fixture's expression vector)
    % ----------------------------------------------------------------
    fprintf('\n--- State_Rna mature snapshot counts ---\n');
    rs = [];
    for i = 1:numel(sim.states)
        if strcmp(sim.states{i}.wholeCellModelID,'State_Rna')
            rs = sim.states{i}; break;
        end
    end
    if ~isempty(rs)
        try, out.rna_matureIndexs = rs.matureIndexs; catch, end
        try, out.rna_processedIndexs = rs.processedIndexs; catch, end
        try, out.rna_nascentIndexs = rs.nascentIndexs; catch, end
        try, out.rna_counts = rs.counts; catch, end  % big matrix
        try, out.rna_lengths = rs.lengths; catch, end
        try, out.rna_types = rs.types; catch, end
        try, out.rna_geneWholeCellModelIDs = rs.geneWholeCellModelIDs; catch, end
    end

    % ----------------------------------------------------------------
    % 4) State_Polypeptide (free polypeptide chain in progress)
    % ----------------------------------------------------------------
    fprintf('\n--- State_Polypeptide ---\n');
    pp = [];
    for i = 1:numel(sim.states)
        if strcmp(sim.states{i}.wholeCellModelID,'State_Polypeptide')
            pp = sim.states{i}; break;
        end
    end
    if ~isempty(pp)
        try, out.poly_monomerLengths = pp.monomerLengths; catch, end  % per protein in aa
    end

    outFile = fullfile(outDir, 'translation_v2_targeted.mat');
    data = out; %#ok<NASGU>
    save(outFile, 'data', '-v7');
    fprintf('\n[OK] wrote %s\n', outFile);
end
