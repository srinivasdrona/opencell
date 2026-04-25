% Extract the 722-element metabolite vocabulary that ProteinMonomer.baseCounts uses.
% Output: data/m1_sources/karr_flat/m3_metabolite_vocab.mat with field
%   metabolite_722_ids (cellstr, 722x1) -- WCM IDs in column order of
%   ProteinMonomer.baseCounts.
%
% Usage: matlab -batch "addpath('scripts/matlab'); extract_m3_metabolite_vocab"
function extract_m3_metabolite_vocab()
    mat_path = 'data/m1_sources/karr_flat/sim_fitted_targeted.mat';
    if exist(mat_path, 'file') ~= 2
        error('%s not found; run from repo root', mat_path);
    end
    s = load(mat_path);
    fprintf('Top-level fields: %s\n', strjoin(fieldnames(s), ', '));
    data = s.data;
    fprintf('data fields: %s\n', strjoin(fieldnames(data), ', '));
    if isfield(data, 'metabolism')
        meta = data.metabolism;
        fprintf('metabolism fields: %s\n', strjoin(fieldnames(meta), ', '));
        if isfield(meta, 'substrateWholeCellModelIDs')
            fprintf('Met process substrateWholeCellModelIDs: %d\n', ...
                numel(meta.substrateWholeCellModelIDs));
        end
    end
    procs = data.processes;
    fprintf('processes fields (first 5): %s\n', ...
        strjoin(fieldnames(procs), ', '));
    if isfield(procs, 'Process_ProteinMonomer') || ...
       isfield(procs, 'Process_Translation')
        if isfield(procs, 'Process_Translation')
            tl = procs.Process_Translation;
            fprintf('Process_Translation fields: %s\n', ...
                strjoin(fieldnames(tl), ', '));
        end
    end
    states = data.states;
    pmstate = states.State_ProteinMonomer;
    fprintf('pmstate fields: %s\n', strjoin(fieldnames(pmstate), ', '));
    if isfield(states, 'State_Metabolite')
        metstate = states.State_Metabolite;
        fprintf('metstate fields: %s\n', strjoin(fieldnames(metstate), ', '));
    end
    if ~isprop(metstate, 'wholeCellModelIDs')
        error('Metabolite state has no wholeCellModelIDs property');
    end
    metIDs = metstate.wholeCellModelIDs;
    fprintf('Metabolite WCM IDs: %d\n', numel(metIDs));
    fprintf('baseCounts columns:  %d\n', size(pmstate.baseCounts, 2));
    if numel(metIDs) ~= size(pmstate.baseCounts, 2)
        % Possibly compartment-expanded; check substrateIndexs.
        if isprop(pmstate, 'substrateWholeCellModelIDs')
            metIDs = pmstate.substrateWholeCellModelIDs;
            fprintf('Falling back to ProteinMonomer.substrateWholeCellModelIDs: %d\n', numel(metIDs));
        end
    end
    if numel(metIDs) ~= size(pmstate.baseCounts, 2)
        warning('Vocab length %d != baseCounts cols %d -- saving anyway.', ...
            numel(metIDs), size(pmstate.baseCounts, 2));
    end
    metabolite_722_ids = metIDs;
    out_path = 'data/m1_sources/karr_flat/m3_metabolite_vocab.mat';
    save(out_path, 'metabolite_722_ids', '-v7.3');
    fprintf('Wrote %s\n', out_path);
end
