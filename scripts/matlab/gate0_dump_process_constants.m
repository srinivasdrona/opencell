function gate0_dump_process_constants(outPath)
% GATE0_DUMP_PROCESS_CONSTANTS  Dump live source-declared process constants.
%
% For each fully initialized process in Simulation_fitted, resolve the declared
% constant surface from the live getters:
%   - fixedConstantNames
%   - fittedConstantNames
% and dump each named constant with a strict type-tagged encoding suitable for
% exact comparison against the extracted per-process flat fixtures.
%
% Numeric values are emitted as sparse nonzero triples using MATLAB's native
% column-major linear indexing (`find(M)` / `M(find(M))`), matching the Python
% comparator's canonicalization.
%
% Usage:
%   >> cd('E:\opencell'); addpath('E:\opencell\scripts\matlab');
%   >> gate0_dump_process_constants('data/karr_input_spec/_gate0_source_constants.json');

    if nargin < 1 || isempty(outPath)
        outPath = fullfile('data', 'karr_input_spec', '_gate0_source_constants.json');
    end

    sim = karr_bootstrap();
    procs = sim.processes;
    n = numel(procs);
    fprintf('[gate0-const] fitted simulation loaded; n_processes = %d\n', n);

    out = struct();
    out.generated_by = 'gate0_dump_process_constants.m';
    out.source = 'karr_bootstrap -> Simulation_fitted.mat (live process constants)';
    entries = struct('name', {}, 'class', {}, 'fixed_names', {}, 'fitted_names', {}, 'constants', {});

    totalFixed = 0;
    totalFitted = 0;
    totalConstants = 0;

    for i = 1:n
        p = procs{i};
        cls = class(p);
        procName = local_leaf_name(cls);

        fixedNames = local_name_list(p.fixedConstantNames);
        fittedNames = local_name_list(p.fittedConstantNames);
        allNames = local_union_names(fixedNames, fittedNames);

        constants = struct();
        for j = 1:numel(allNames)
            nm = allNames{j};
            constants.(nm) = local_encode_constant(p.(nm));
        end

        entries(end+1) = struct( ... %#ok<AGROW>
            'name', procName, ...
            'class', cls, ...
            'fixed_names', {fixedNames}, ...
            'fitted_names', {fittedNames}, ...
            'constants', constants);

        totalFixed = totalFixed + numel(fixedNames);
        totalFitted = totalFitted + numel(fittedNames);
        totalConstants = totalConstants + numel(allNames);

        fprintf('[gate0-const] %-30s count=%3d fixed=%3d fitted=%2d\n', ...
            procName, numel(allNames), numel(fixedNames), numel(fittedNames));
    end

    out.n_processes = n;
    out.n_fixed = totalFixed;
    out.n_fitted = totalFitted;
    out.n_constants = totalConstants;
    out.processes = entries;

    outDir = fileparts(outPath);
    if ~isempty(outDir) && ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    txt = jsonencode(out);
    fid = fopen(outPath, 'w');
    if fid < 0
        error('cannot open %s', outPath);
    end
    fwrite(fid, txt, 'char');
    fclose(fid);
    fprintf('[gate0-const] wrote %s (%d processes, %d constants)\n', ...
        outPath, n, totalConstants);
end

function nm = local_leaf_name(cls)
    parts = strsplit(cls, '.');
    nm = parts{end};
end

function names = local_name_list(raw)
    if isempty(raw)
        names = {};
        return;
    end
    if ischar(raw)
        names = {raw};
        return;
    end
    if isstring(raw)
        names = cell(1, numel(raw));
        for k = 1:numel(raw)
            names{k} = char(raw(k));
        end
        return;
    end
    if iscell(raw)
        names = cell(1, numel(raw));
        for k = 1:numel(raw)
            names{k} = local_string_scalar(raw{k});
        end
        return;
    end
    error('Unsupported constant-name container class: %s', class(raw));
end

function names = local_union_names(fixedNames, fittedNames)
    allNames = [fixedNames(:); fittedNames(:)];
    if isempty(allNames)
        names = {};
        return;
    end
    names = reshape(unique(allNames, 'stable'), 1, []);
end

function entry = local_encode_constant(v)
    entry = struct();

    if isempty(v)
        entry.kind = 'empty';
        entry.class = class(v);
        entry.size = int64(size(v));
        return;
    end

    if isnumeric(v) || islogical(v)
        M = full(v);
        idx = find(M); % 1-based column-major linear indices, including N-D
        vals = M(idx);
        entry.kind = 'numeric';
        entry.class = class(v);
        entry.size = int64(size(M));
        entry.nz_idx = int64(idx(:)');
        entry.nz_val = local_encode_numeric_json_values(vals(:)');
        return;
    end

    if ischar(v) || isstring(v)
        entry.kind = 'char';
        entry.size = int64(size(v));
        if isstring(v)
            if isscalar(v)
                entry.value = char(v);
            else
                entry.value = reshape(cellstr(v(:)), 1, []);
            end
            return;
        end
        if size(v, 1) <= 1
            entry.value = v;
        else
            entry.value = reshape(cellstr(v), 1, []);
        end
        return;
    end

    if iscell(v)
        entry.size = int64(size(v));
        if local_is_cellstr(v)
            entry.kind = 'cellstr';
            entry.value = local_flat_cellstr(v);
        else
            entry.kind = 'cell';
            entry.items = local_flat_cell_items(v);
        end
        return;
    end

    error('Unsupported constant class: %s', class(v));
end

function values = local_flat_cellstr(v)
    values = cell(1, numel(v));
    for k = 1:numel(v)
        values{k} = local_string_scalar(v{k});
    end
end

function items = local_flat_cell_items(v)
    items = cell(1, numel(v));
    for k = 1:numel(v)
        items{k} = local_encode_constant(v{k});
    end
end

function tf = local_is_cellstr(v)
    tf = true;
    for k = 1:numel(v)
        if ~local_is_string_scalar(v{k})
            tf = false;
            return;
        end
    end
end

function txt = local_string_scalar(v)
    if ischar(v)
        txt = v;
        return;
    end
    if isstring(v) && isscalar(v)
        txt = char(v);
        return;
    end
    error('Expected string scalar cell content, got %s', class(v));
end

function tf = local_is_string_scalar(v)
    tf = ischar(v) || (isstring(v) && isscalar(v));
end

function out = local_encode_numeric_json_values(vals)
    out = cell(size(vals));
    for k = 1:numel(vals)
        x = vals(k);
        if isfinite(x)
            out{k} = double(x);
        elseif isnan(x)
            out{k} = 'NaN';
        elseif x > 0
            out{k} = 'Inf';
        else
            out{k} = '-Inf';
        end
    end
end
