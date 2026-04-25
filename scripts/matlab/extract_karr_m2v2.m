function extract_karr_m2v2(wholecellRoot, outDir)
% EXTRACT_KARR_M2V2  Extract M2 v2 mechanism inputs:
%   - RNA polymerase counts (active / specifically bound / free / total)
%   - Transcription unit lengths (335-vec)
%   - Gene <-> TU mapping (525 x 335 incidence)
%   - Per-TU base composition (335 x 4 NTP)
%   - rnaPolymeraseStateExpectations (4-vec)
%
% Loads Simulation_fitted.mat + knowledgeBase.mat (heavy), so run once.
%
% Usage:
%   >> cd('E:\opencell\data\m1_sources\WholeCell')
%   >> extract_karr_m2v2(pwd, 'E:\opencell\data\m1_sources\karr_flat')

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
    % 1) RNA polymerase state from sim.state.RnaPolymerase
    % ----------------------------------------------------------------
    fprintf('\n--- State_RnaPolymerase ---\n');
    rp = [];
    for i = 1:numel(sim.states)
        if strcmp(sim.states{i}.wholeCellModelID,'State_RNAPolymerase')
            rp = sim.states{i}; break;
        end
    end
    if isempty(rp)
        fprintf('  not found\n');
    else
        fprintf('  class=%s\n', class(rp));
        % introspect available properties
        try, props = properties(rp); catch, props = {}; end
        out.rnap_properties = props;
        for k = 1:numel(props)
            nm = props{k};
            try
                v = rp.(nm);
                if isnumeric(v) || islogical(v)
                    out.(['rnap_' nm]) = v;
                end
            catch, end
        end
        % derived counts from .states vector (preferred)
        try
            st = rp.states;
            out.rnap_states_vec = st;
            try, out.rnap_activelyTranscribingValue   = rp.activelyTranscribingValue;   catch, end
            try, out.rnap_specificallyBoundValue      = rp.specificallyBoundValue;      catch, end
            try, out.rnap_nonSpecificallyBoundValue   = rp.nonSpecificallyBoundValue;   catch, end
            try, out.rnap_freeValue                   = rp.freeValue;                   catch, end
            try, out.rnap_notExistValue               = rp.notExistValue;               catch, end
            try, out.rnap_stateExpectations           = rp.stateExpectations;           catch, end
        catch e
            fprintf('  states extraction FAIL: %s\n', e.message);
        end
        % nActive accessor (computed property)
        try, out.rnap_nActive = rp.nActive; catch, end
        try, out.rnap_nSpecificallyBound = rp.nSpecificallyBound; catch, end
        try, out.rnap_nNonSpecificallyBound = rp.nNonSpecificallyBound; catch, end
        try, out.rnap_nFree = rp.nFree; catch, end
    end

    % ----------------------------------------------------------------
    % 2) Transcript state -> transcription unit lengths, etc.
    % ----------------------------------------------------------------
    fprintf('\n--- State_Transcript ---\n');
    tr = [];
    for i = 1:numel(sim.states)
        if strcmp(sim.states{i}.wholeCellModelID,'State_Transcript')
            tr = sim.states{i}; break;
        end
    end
    if isempty(tr)
        fprintf('  not found\n');
    else
        try, props = properties(tr); catch, props = {}; end
        out.transcript_properties = props;
        % the props we want
        wishlist = {'transcriptionUnitLengths', 'transcriptionUnitFivePrimeCoordinates', ...
                    'transcriptionUnitDirections', 'nascentRNAMatureRNAComposition', ...
                    'transcriptionUnitBaseCounts'};
        for k = 1:numel(wishlist)
            nm = wishlist{k};
            try
                v = tr.(nm);
                out.(['tr_' nm]) = v;
            catch, end
        end
    end

    % ----------------------------------------------------------------
    % 3) Process_Transcription -> nActive accessor + bound polymerase counts
    %    (sometimes these only exist on the Process not on the State)
    % ----------------------------------------------------------------
    fprintf('\n--- Process_Transcription enzymes/polymerases ---\n');
    pt = [];
    for i = 1:numel(sim.processes)
        if strcmp(sim.processes{i}.wholeCellModelID,'Process_Transcription')
            pt = sim.processes{i}; break;
        end
    end
    if ~isempty(pt)
        try, out.pt_enzymes = pt.enzymes; catch, end
        try, out.pt_boundEnzymes = pt.boundEnzymes; catch, end
        try, out.pt_enzymeWholeCellModelIDs = pt.enzymeWholeCellModelIDs; catch, end
        try, out.pt_enzymeIndexs_rnaPolymerase = pt.enzymeIndexs_rnaPolymerase; catch, end
        try, out.pt_enzymeIndexs_rnaPolymeraseHoloenzyme = pt.enzymeIndexs_rnaPolymeraseHoloenzyme; catch, end
        try
            % the rnaPolymerases handle inside the process
            rph = pt.rnaPolymerases;
            try, out.pt_rnaPolymerases_nActive = rph.nActive; catch, end
            try, out.pt_rnaPolymerases_nSpecificallyBound = rph.nSpecificallyBound; catch, end
            try, out.pt_rnaPolymerases_nNonSpecificallyBound = rph.nNonSpecificallyBound; catch, end
            try, out.pt_rnaPolymerases_nFree = rph.nFree; catch, end
            try, out.pt_rnaPolymerases_states = rph.states; catch, end
            try, out.pt_rnaPolymerases_stateExpectations = rph.stateExpectations; catch, end
            try, out.pt_rnaPolymerases_activelyTranscribingValue = rph.activelyTranscribingValue; catch, end
            try, out.pt_rnaPolymerases_specificallyBoundValue = rph.specificallyBoundValue; catch, end
            try, out.pt_rnaPolymerases_nonSpecificallyBoundValue = rph.nonSpecificallyBoundValue; catch, end
            try, out.pt_rnaPolymerases_freeValue = rph.freeValue; catch, end
        catch, end
        try
            trh = pt.transcripts;
            try, out.pt_tr_transcriptionUnitLengths = trh.transcriptionUnitLengths; catch, end
            try, out.pt_tr_transcriptionUnitBaseCounts = trh.transcriptionUnitBaseCounts; catch, end
        catch, end
        try, out.pt_rnaPolymeraseElongationRate = pt.rnaPolymeraseElongationRate; catch, end
    end

    % ----------------------------------------------------------------
    % 4) Knowledge base: gene <-> TU mapping
    % ----------------------------------------------------------------
    fprintf('\n--- KB gene<->TU mapping ---\n');
    try
        % geneTranscriptionUnitMatrix is typically 525 x 335 (genes x TUs)
        out.kb_geneTranscriptionUnitMatrix = full(kb.geneTranscriptionUnitMatrix);
        fprintf('  geneTranscriptionUnitMatrix size: %dx%d\n', size(out.kb_geneTranscriptionUnitMatrix));
    catch e
        fprintf('  geneTranscriptionUnitMatrix FAIL: %s\n', e.message);
    end
    try
        nTU = numel(kb.transcriptionUnits);
        tuWcm   = cell(nTU,1);
        tuLen   = nan(nTU,1);
        tuGenes = cell(nTU,1);  % each entry: list of gene WCM IDs
        for i = 1:nTU
            tu = kb.transcriptionUnits(i);
            try, tuWcm{i} = tu.wholeCellModelID; catch, end
            % genes: stored as cell ref array {className, idxUint32}; or array of refs
            % genes: stored as cell ref {className, idxUint32-vec} where idxUint32-vec
            % is a uint32 array of indices into kb.genes (one per gene in the TU).
            try
                g = tu.genes;
                if iscell(g) && numel(g) >= 2
                    idxs = double(g{2}(:));
                    ids = cell(numel(idxs), 1);
                    for r = 1:numel(idxs)
                        ids{r} = kb.genes(idxs(r)).wholeCellModelID;
                    end
                    tuGenes{i} = ids;
                end
            catch, end
            % length: try direct first, fall back to sequence
            try, tuLen(i) = double(tu.sequenceLength); catch
                try, tuLen(i) = numel(tu.sequence); catch, end
            end
        end
        out.kb_tu_wholeCellModelIDs = tuWcm;
        out.kb_tu_lengths = tuLen;
        out.kb_tu_geneWcmIDs = tuGenes;
        fprintf('  walked %d transcription units\n', nTU);
    catch e
        fprintf('  TU walk FAIL: %s\n', e.message);
    end

    % gene WCM order to align with the 525-vec we already have
    try
        nG = numel(kb.genes);
        gWcm = cell(nG,1);
        for i = 1:nG
            try, gWcm{i} = kb.genes(i).wholeCellModelID; catch, end
        end
        out.kb_geneWholeCellModelIDs_full = gWcm;
        fprintf('  walked %d genes\n', nG);
    catch e
        fprintf('  gene walk FAIL: %s\n', e.message);
    end

    % ----------------------------------------------------------------
    % save
    % ----------------------------------------------------------------
    outFile = fullfile(outDir, 'transcription_v2_targeted.mat');
    data = out; %#ok<NASGU>
    save(outFile, 'data', '-v7');
    fprintf('\n[OK] wrote %s\n', outFile);
end
