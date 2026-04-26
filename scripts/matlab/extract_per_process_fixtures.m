function extract_per_process_fixtures(wholecellRoot, outDir)
% EXTRACT_PER_PROCESS_FIXTURES  Deserialize the 28 per-process + 16 per-state
% MCOS-serialized fixture .mat files in Karr's WholeCell src_test/ tree into
% plain v7 .mat structs that scipy.io.loadmat can read.
%
% These fixtures live at:
%   <wholecellRoot>/src_test/+edu/+stanford/+covert/+cell/+sim/+process/fixtures/*.mat
%   <wholecellRoot>/src_test/+edu/+stanford/+covert/+cell/+sim/+state/fixtures/*.mat
%
% Each one is a saved instance of an MCOS class (e.g.
% edu.stanford.covert.cell.sim.process.Transcription). Pure-Python decoders
% (scipy, pymatreader, mat4py) cannot deserialize MCOS payloads. This script
% does the deserialization in MATLAB (which natively understands the format
% as long as the +edu class definitions are on the path) and emits a
% Python-friendly flattened struct per fixture.
%
% Usage (MATLAB Online or local Windows MATLAB):
%   >> cd('<path to opencell repo>');
%   >> extract_per_process_fixtures('data/m1_sources/WholeCell', ...
%                                   'data/karr_fixtures/per_process');
%
% Or, with defaults (run from repo root):
%   >> extract_per_process_fixtures();
%
% Inputs
%   wholecellRoot : path to the WholeCell repo clone. Must contain
%                   src/ (class defs) and src_test/ (fixture dirs).
%                   Default: 'data/m1_sources/WholeCell'
%   outDir        : destination folder. Default:
%                   'data/karr_fixtures/per_process'
%
% Outputs (per fixture)
%   <outDir>/<Name>_flat.mat   - v7 .mat with one struct 'data' holding the
%                                fully flattened object. scipy-readable.
%
% Plus:
%   <outDir>/matlab_extract_manifest.json - MATLAB release, sha256 per
%                                input/output, status per file, timestamp.
%
% After this script runs, ingest the _flat.mat files into the project's
% canonical per-process scheme by running:
%   $ python scripts/extract_per_process_fixtures.py --all --from-flat
%
% Author: opencell project. Safe for MATLAB Online Basic tier.

    if nargin < 1 || isempty(wholecellRoot)
        wholecellRoot = fullfile('data', 'm1_sources', 'WholeCell');
    end
    if nargin < 2 || isempty(outDir)
        outDir = fullfile('data', 'karr_fixtures', 'per_process');
    end

    if ~exist(wholecellRoot, 'dir')
        error('WholeCell root does not exist: %s', wholecellRoot);
    end
    if ~exist(outDir, 'dir'), mkdir(outDir); end

    fprintf('[per_process] WholeCell root: %s\n', wholecellRoot);
    fprintf('[per_process] Output dir    : %s\n', outDir);

    % --- 1. Make Karr's class definitions visible -----------------------
    addpath(genpath(fullfile(wholecellRoot, 'src')));
    addpath(genpath(fullfile(wholecellRoot, 'src_test')));
    try
        % setWarnings is optional; suppresses the structOnObject warning.
        warning('off', 'MATLAB:structOnObject');
    catch
    end

    % --- 2. Build input list -------------------------------------------
    procFix = fullfile(wholecellRoot, 'src_test', '+edu', '+stanford', ...
        '+covert', '+cell', '+sim', '+process', 'fixtures');
    stateFix = fullfile(wholecellRoot, 'src_test', '+edu', '+stanford', ...
        '+covert', '+cell', '+sim', '+state', 'fixtures');

    inputs = {};
    inputs = appendDir(inputs, procFix,  'process');
    inputs = appendDir(inputs, stateFix, 'state');

    fprintf('[per_process] Found %d fixtures (%d process + %d state).\n', ...
        numel(inputs), countKind(inputs, 'process'), countKind(inputs, 'state'));

    % --- 3. Flatten each ------------------------------------------------
    manifest = struct();
    manifest.matlab_release = version('-release');
    manifest.matlab_version = version();
    manifest.timestamp_utc  = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    manifest.wholecell_root = wholecellRoot;
    manifest.fixtures = {};

    for i = 1:numel(inputs)
        srcPath = inputs{i}.path;
        kind    = inputs{i}.kind;
        [~, baseName, ~] = fileparts(srcPath);
        outName = sprintf('%s_flat.mat', baseName);
        outPath = fullfile(outDir, outName);

        fprintf('\n[%d/%d] %s/%s\n', i, numel(inputs), kind, baseName);

        entry = struct();
        entry.input_path     = relpath(srcPath, wholecellRoot);
        entry.kind           = kind;
        entry.input_sha256   = sha256OfFile(srcPath);
        entry.output_relpath = outName;

        try
            raw = load(srcPath);
            data = flattenAny(raw, 0, containers.Map('KeyType','char','ValueType','any')); %#ok<NASGU>
            save(outPath, 'data', '-v7');
            entry.status        = 'ok';
            entry.output_sha256 = sha256OfFile(outPath);
            entry.output_bytes  = fileSize(outPath);
            fprintf('   -> %s  (%d bytes)\n', outName, entry.output_bytes);
        catch e
            entry.status        = 'error';
            entry.error_message = e.message;
            entry.error_id      = e.identifier;
            fprintf('   !! ERROR (%s): %s\n', e.identifier, e.message);
        end

        manifest.fixtures{end+1} = entry; %#ok<AGROW>
    end

    % --- 4. Write manifest ---------------------------------------------
    manifestPath = fullfile(outDir, 'matlab_extract_manifest.json');
    fid = fopen(manifestPath, 'w');
    try
        jsonStr = jsonencode(manifest, 'PrettyPrint', true);
    catch
        jsonStr = jsonencode(manifest);
    end
    fwrite(fid, jsonStr);
    fclose(fid);
    fprintf('\n[per_process] Manifest: %s\n', manifestPath);

    nOk = sum(cellfun(@(e) strcmp(e.status, 'ok'), manifest.fixtures));
    fprintf('[per_process] DONE: %d of %d flattened.\n', nOk, numel(manifest.fixtures));
    fprintf('[per_process] Next step (back in WSL/Linux):\n');
    fprintf('[per_process]   python scripts/extract_per_process_fixtures.py --all --from-flat\n');
end

% ======================================================================
%  HELPERS
% ======================================================================

function list = appendDir(list, dirPath, kindLabel)
    if ~exist(dirPath, 'dir')
        warning('[per_process] missing dir: %s', dirPath);
        return;
    end
    d = dir(fullfile(dirPath, '*.mat'));
    for k = 1:numel(d)
        if d(k).isdir, continue; end
        list{end+1} = struct('path', fullfile(d(k).folder, d(k).name), ...
                             'kind', kindLabel); %#ok<AGROW>
    end
end

function n = countKind(list, kind)
    n = 0;
    for k = 1:numel(list)
        if strcmp(list{k}.kind, kind), n = n + 1; end
    end
end

function r = relpath(fullPath, root)
    if numel(fullPath) >= numel(root) && strncmp(fullPath, root, numel(root))
        r = fullPath(numel(root)+2:end);
    else
        r = fullPath;
    end
    r = strrep(r, '\', '/');
end

function out = flattenAny(x, depth, visited)
% Flatten a MATLAB value into a plain (numeric/cell/struct) tree.
%
% Strategy (post handle-graph-cycle lessons learned):
%   * Primitives, structs, cells, containers.Map -> recurse normally.
%   * MCOS handle objects -> walk only own (declared) properties, and
%     for any property whose VALUE is itself a handle object, emit a
%     sentinel string instead of recursing. This stops the
%     cross-references between Process <-> Simulation <-> State <->
%     Reaction <-> ... that otherwise blow up combinatorially.
%   * Function handles / java / unhandled -> sentinel string.
%
% `visited` is kept as a parameter for API stability but is not used
% by the new strategy (we cut at handle boundaries instead).

    if depth > 6
        out = '<MAX_DEPTH>';
        return;
    end

    if isnumeric(x) || islogical(x) || ischar(x) || isstring(x)
        out = x;
        return;
    end

    if isa(x, 'function_handle')
        out = sprintf('<function_handle:%s>', func2str(x));
        return;
    end
    if isjava(x)
        out = sprintf('<java:%s>', class(x));
        return;
    end

    if iscell(x)
        out = cell(size(x));
        for k = 1:numel(x)
            out{k} = flattenAny(x{k}, depth+1, visited);
        end
        return;
    end

    if isstruct(x)
        out = x;
        fns = fieldnames(x);
        for k = 1:numel(x)
            for f = 1:numel(fns)
                try
                    v = subsref(x(k), substruct('.', fns{f}));
                catch
                    v = '<field-unreadable>';
                end
                try
                    out(k) = subsasgn(out(k), substruct('.', fns{f}), ...
                        flattenAny(v, depth+1, visited));
                catch
                end
            end
        end
        return;
    end

    if isa(x, 'containers.Map')
        out = struct();
        out.x_containers_Map_keys   = x.keys;
        out.x_containers_Map_values = cellfun(@(k) flattenAny(x(k), depth+1, visited), ...
            x.keys, 'UniformOutput', false);
        return;
    end

    if isobject(x)
        if numel(x) > 1
            out = cell(size(x));
            for k = 1:numel(x)
                out{k} = flattenAnyInner(x(k), depth+1);
            end
            return;
        end
        out = flattenAnyInner(x, depth);
        return;
    end

    try
        out = sprintf('<unhandled:%s>', class(x));
    catch
        out = '<unhandled>';
    end
end

function out = flattenAnyInner(x, depth)
% Walk the own (non-inherited from handle/MException etc.) properties
% of an MCOS instance. Skip properties whose VALUE is itself an MCOS
% handle object — emit a sentinel instead. This is the cycle-cut.

    out = struct();
    out.x_class_ = class(x);

    try
        mc = metaclass(x);
    catch e
        out.x_error_ = sprintf('metaclass failed: %s', e.message);
        return;
    end

    for p = 1:numel(mc.PropertyList)
        prop = mc.PropertyList(p);
        % Skip inherited handle plumbing (Listeners etc.).
        if ~strcmp(prop.DefiningClass.Name, mc.Name)
            % Allow direct ancestors in the same package tree but skip
            % everything inherited from handle/dynamicprops/MException.
            if any(strcmp(prop.DefiningClass.Name, ...
                    {'handle','dynamicprops','matlab.mixin.Copyable', ...
                     'matlab.mixin.SetGet'}))
                continue;
            end
        end
        if prop.Dependent && ~prop.HasDefault, continue; end
        if strcmp(prop.GetAccess, 'private') || strcmp(prop.GetAccess, 'protected')
            % Often these are computed on demand; skip to be safe.
            continue;
        end
        name = prop.Name;
        try
            val = x.(name);
        catch e
            out.(safeFieldName(name)) = sprintf('<unreadable:%s>', e.identifier);
            continue;
        end

        % CYCLE-CUT: any property pointing to another MCOS handle object
        % (or array thereof) gets sentinel'd, not recursed.
        if isHandleObjectLike(val)
            out.(safeFieldName(name)) = sprintf('<handle:%s:%dx%d>', ...
                class(val), size(val,1), size(val,2));
            continue;
        end

        try
            out.(safeFieldName(name)) = flattenAny(val, depth+1, []);
        catch e
            out.(safeFieldName(name)) = sprintf('<flatten-error:%s>', e.message);
        end
    end
end

function tf = isHandleObjectLike(v)
% A value we should NOT recurse into (would re-enter the MCOS web).
% containers.Map, function_handle, java are handled elsewhere; here
% we cut MCOS handle classes specifically.
    tf = false;
    if isa(v, 'function_handle'), return; end
    if isa(v, 'containers.Map'), return; end
    if ~isobject(v), return; end
    if isa(v, 'handle')
        % It's an MCOS handle: cut.
        tf = true;
    end
end

function n = safeFieldName(name)
% MATLAB struct fields cannot start with 'x_' clashing with our
% sentinels; pass-through otherwise.
    n = matlab.lang.makeValidName(name);
end

function h = sha256OfFile(p)
    md = java.security.MessageDigest.getInstance('SHA-256');
    fid = fopen(p, 'r');
    cleaner = onCleanup(@() fclose(fid));
    while true
        buf = fread(fid, 1024*1024, '*uint8');
        if isempty(buf), break; end
        md.update(buf);
    end
    bytes = typecast(md.digest(), 'uint8');
    h = lower(reshape(dec2hex(bytes, 2)', 1, []));
end

function n = fileSize(p)
    d = dir(p);
    if isempty(d), n = 0; else, n = d(1).bytes; end
end
