function gate0_dump_process_inputs(outPath)
% GATE0_DUMP_PROCESS_INPUTS  Authoritative source-of-truth dump of per-process
% INPUT vocabularies, resolved live from the fitted Karr simulation.
%
% This is the "Gate 0" reference: it constructs the 28 processes fresh from the
% real WholeCell source + Knowledge Base (via karr_bootstrap -> Simulation_fitted),
% runs their real initializeConstants, and dumps the RESOLVED input vocabularies.
% A later Python step compares this against our extracted fixtures and the derived
% frozen input spec (data/karr_input_spec/), so we never freeze an
% extraction-level omission into the "source of truth".
%
% For each process it dumps:
%   substrateWholeCellModelIDs, enzymeWholeCellModelIDs, stimuliWholeCellModelIDs
%   (the resolved input species vocabularies), and state_refs (the shared state
%   objects the process references, from this.states class names).
%
% Usage:
%   >> cd('E:\opencell'); addpath('E:\opencell\scripts\matlab');
%   >> gate0_dump_process_inputs('data/karr_input_spec/_gate0_source_truth.json');

    if nargin < 1 || isempty(outPath)
        outPath = fullfile('data', 'karr_input_spec', '_gate0_source_truth.json');
    end

    sim = karr_bootstrap();
    procs = sim.processes;
    n = numel(procs);
    fprintf('[gate0] fitted simulation loaded; n_processes = %d\n', n);

    out = struct();
    out.source = 'karr_bootstrap -> Simulation_fitted.mat (live initializeConstants)';
    entries = struct('name', {}, 'class', {}, ...
                     'substrateWholeCellModelIDs', {}, ...
                     'enzymeWholeCellModelIDs', {}, ...
                     'stimuliWholeCellModelIDs', {}, ...
                     'state_refs', {});

    for i = 1:n
        p = procs{i};
        cls = class(p);
        nm = local_leaf_name(cls);

        sub = local_cellstr(p.substrateWholeCellModelIDs);
        enz = local_cellstr(p.enzymeWholeCellModelIDs);
        stim = local_cellstr(p.stimuliWholeCellModelIDs);
        refs = local_state_refs(p);

        entries(end+1) = struct( ...
            'name', nm, 'class', cls, ...
            'substrateWholeCellModelIDs', {sub}, ...
            'enzymeWholeCellModelIDs', {enz}, ...
            'stimuliWholeCellModelIDs', {stim}, ...
            'state_refs', {refs}); %#ok<AGROW>

        fprintf('[gate0] %-30s sub=%3d enz=%3d stim=%2d refs=%d\n', ...
            nm, numel(sub), numel(enz), numel(stim), numel(refs));
    end

    out.processes = entries;

    outDir = fileparts(outPath);
    if ~isempty(outDir) && ~exist(outDir, 'dir'), mkdir(outDir); end
    txt = jsonencode(out);
    fid = fopen(outPath, 'w');
    if fid < 0, error('cannot open %s', outPath); end
    fwrite(fid, txt, 'char');
    fclose(fid);
    fprintf('[gate0] wrote %s (%d processes)\n', outPath, numel(entries));
end

function nm = local_leaf_name(cls)
    parts = strsplit(cls, '.');
    nm = parts{end};
end

function c = local_cellstr(v)
    % Normalize a MATLAB cell array of char / string to a row cell of char.
    if isempty(v)
        c = {};
        return;
    end
    if ischar(v)
        c = {v};
        return;
    end
    c = cell(1, numel(v));
    for k = 1:numel(v)
        x = v{k};
        if ischar(x)
            c{k} = x;
        else
            c{k} = char(x);
        end
    end
end

function refs = local_state_refs(p)
    % The shared state objects this process references (this.states),
    % reported by their state-class leaf name (e.g. Chromosome, Rna, Metabolite).
    refs = {};
    try
        st = p.states;
    catch
        return;
    end
    if isempty(st), return; end
    refs = cell(1, numel(st));
    for k = 1:numel(st)
        refs{k} = local_leaf_name(class(st{k}));
    end
    refs = unique(refs, 'stable');
end
