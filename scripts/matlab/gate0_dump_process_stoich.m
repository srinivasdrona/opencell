function gate0_dump_process_stoich(outPath)
% GATE0_DUMP_PROCESS_STOICH  Authoritative source-of-truth dump of per-process
% reaction STOICHIOMETRY matrices, resolved live from the fitted Karr simulation.
%
% Companion to gate0_dump_process_inputs.m. The frozen input spec froze each
% process's stoichiometry (shape + sha256 + per-reaction breakdown) derived from
% the extracted fixture. This dumps the LIVE matrices from Simulation_fitted so a
% Python comparator can confirm the fixture's stoichiometry is faithful to source
% (not an extraction artifact).
%
% For each process that defines them, dumps (as sparse nonzero triples, exact):
%   reactionStoichiometryMatrix, reactionSmallMoleculeStoichiometryMatrix,
%   reactionDNAStoichiometryMatrix
% Each as: { size:[...], nz_idx:[1-based column-major linear indices], nz_val:[...] }
%
% Usage:
%   >> cd('E:\opencell'); addpath('E:\opencell\scripts\matlab');
%   >> gate0_dump_process_stoich('data/karr_input_spec/_gate0_source_stoich.json');

    if nargin < 1 || isempty(outPath)
        outPath = fullfile('data', 'karr_input_spec', '_gate0_source_stoich.json');
    end

    matrixNames = { ...
        'reactionStoichiometryMatrix', ...
        'reactionSmallMoleculeStoichiometryMatrix', ...
        'reactionDNAStoichiometryMatrix'};

    sim = karr_bootstrap();
    procs = sim.processes;
    n = numel(procs);
    fprintf('[gate0-stoich] fitted simulation loaded; n_processes = %d\n', n);

    out = struct();
    out.source = 'karr_bootstrap -> Simulation_fitted.mat (live process stoichiometry)';
    entries = struct('name', {}, 'matrices', {});

    for i = 1:n
        p = procs{i};
        nm = local_leaf_name(class(p));
        mats = struct();
        present = {};
        for j = 1:numel(matrixNames)
            mname = matrixNames{j};
            M = [];
            try
                M = p.(mname);
            catch
                continue; % property not defined for this process
            end
            if isempty(M)
                continue;
            end
            M = full(M);
            idx = find(M);                 % 1-based column-major linear indices
            vals = M(idx);
            entry = struct();
            entry.size = int64(size(M));
            entry.nz_idx = int64(idx(:)');
            entry.nz_val = double(vals(:)');
            mats.(mname) = entry;
            present{end+1} = sprintf('%s(%dnz)', mname, numel(idx)); %#ok<AGROW>
        end
        entries(end+1) = struct('name', nm, 'matrices', mats); %#ok<AGROW>
        if isempty(present)
            fprintf('[gate0-stoich] %-30s (no stoichiometry matrices)\n', nm);
        else
            fprintf('[gate0-stoich] %-30s %s\n', nm, strjoin(present, ' '));
        end
    end

    out.processes = entries;

    outDir = fileparts(outPath);
    if ~isempty(outDir) && ~exist(outDir, 'dir'), mkdir(outDir); end
    txt = jsonencode(out);
    fid = fopen(outPath, 'w');
    if fid < 0, error('cannot open %s', outPath); end
    fwrite(fid, txt, 'char');
    fclose(fid);
    fprintf('[gate0-stoich] wrote %s (%d processes)\n', outPath, numel(entries));
end

function nm = local_leaf_name(cls)
    parts = strsplit(cls, '.');
    nm = parts{end};
end
