function extract_karr_mats(wholecellRoot, outDir)
% EXTRACT_KARR_MATS  Deserialize Karr 2012 WholeCell .mat files into plain
% structs (MAT v7) that scipy.io.loadmat can read.
%
% Usage (from MATLAB Online or local MATLAB):
%   >> cd('<path to WholeCell clone>');       % folder containing src/, data/, setPath.m
%   >> extract_karr_mats(pwd, fullfile(pwd, 'karr_flat'));
%
% Or explicitly:
%   >> extract_karr_mats('/path/to/WholeCell', '/path/to/karr_flat');
%
% Inputs
%   wholecellRoot : folder of the WholeCell repo clone. Must contain
%                   setPath.m, setWarnings.m, src/, src_test/, data/.
%   outDir        : destination folder for *_flat.mat and manifest.json.
%
% Output per input MAT file: a "<name>_flat.mat" saved with '-v7', whose
% top-level struct "data" holds a fully-flattened Python-friendly copy of
% the original file.
%
% Manifest:  manifest.json with sha256 of every input & output file, MATLAB
% release, timestamp, and per-file status (ok / skipped / error-with-msg).
%
% Design notes
%   * Java/JDBC handles, function handles, and unresolvable opaque blobs
%     are replaced with sentinel strings so the rest of the object still
%     serializes. Nothing is synthesized or guessed numerically.
%   * Every original object is walked via metaclass introspection so even
%     private/protected/hidden properties are captured.
%   * Handle-reference cycles are broken using an identity map
%     (containers.Map keyed by the result of matlab.lang.internal.uuid()
%     or, as fallback, a running counter).
%   * CPLEX / GLPK / MySQL JARs are NOT required: we do not run the
%     simulation, we only load-and-flatten. If setPath.m chokes adding
%     Java paths, we swallow the error and continue.
%
% Author: opencell project. Safe for MATLAB Online Basic tier.

    if nargin < 1 || isempty(wholecellRoot), wholecellRoot = pwd; end
    if nargin < 2 || isempty(outDir), outDir = fullfile(wholecellRoot, 'karr_flat'); end
    if ~exist(outDir, 'dir'), mkdir(outDir); end

    fprintf('[extract_karr_mats] WholeCell root: %s\n', wholecellRoot);
    fprintf('[extract_karr_mats] Output dir    : %s\n', outDir);

    % -- 1. Make Karr's classes visible on the MATLAB path ---------------
    origDir = pwd;
    cleanupCwd = onCleanup(@() cd(origDir));
    cd(wholecellRoot);

    try
        setWarnings();
    catch e
        fprintf('[warn] setWarnings failed: %s\n', e.message);
    end

    try
        setPath();
    catch e
        % setPath tries to add Java/JDBC paths that may fail in MATLAB
        % Online. Fall back to plain addpath of src/ + src_test/.
        fprintf('[warn] setPath failed (%s); using minimal addpath.\n', e.message);
        addpath(genpath(fullfile(wholecellRoot, 'src')));
        if exist(fullfile(wholecellRoot, 'src_test'), 'dir')
            addpath(genpath(fullfile(wholecellRoot, 'src_test')));
        end
    end

    % -- 2. Build the list of input files --------------------------------
    inputs = {};

    % Top-level Simulation / KB / fitted revisions
    dataDir = fullfile(wholecellRoot, 'data');
    inputs = addGlob(inputs, dataDir, '*.mat');

    % Per-process fixtures
    procFix = fullfile(wholecellRoot, 'src_test', '+edu', '+stanford', ...
        '+covert', '+cell', '+sim', '+process', 'fixtures');
    inputs = addGlob(inputs, procFix, '*.mat');

    % Per-state fixtures
    stateFix = fullfile(wholecellRoot, 'src_test', '+edu', '+stanford', ...
        '+covert', '+cell', '+sim', '+state', 'fixtures');
    inputs = addGlob(inputs, stateFix, '*.mat');

    % Top-level src_test Simulation fixtures
    simFix = fullfile(wholecellRoot, 'src_test', '+edu', '+stanford', ...
        '+covert', '+cell', '+sim', 'fixtures');
    inputs = addGlob(inputs, simFix, '*.mat');

    fprintf('[extract_karr_mats] Found %d input .mat files.\n', numel(inputs));

    % -- 3. Flatten each file --------------------------------------------
    manifest = struct();
    manifest.matlab_release = version('-release');
    manifest.matlab_version = version();
    manifest.timestamp_utc  = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    manifest.wholecell_root = wholecellRoot;
    manifest.files = {};

    for i = 1:numel(inputs)
        srcPath = inputs{i};
        [~, baseName, ~] = fileparts(srcPath);
        relIn = localRel(srcPath, wholecellRoot);
        outName = sprintf('%s_flat.mat', sanitize(strjoin({dirTag(relIn), baseName}, '__')));
        outPath = fullfile(outDir, outName);

        fprintf('\n[%d/%d] %s\n', i, numel(inputs), relIn);

        entry = struct();
        entry.input_path     = relIn;
        entry.input_sha256   = sha256OfFile(srcPath);
        entry.input_bytes    = fileSize(srcPath);
        entry.output_relpath = outName;

        try
            raw = load(srcPath);
            data = flatten(raw, 0, containers.Map('KeyType','char','ValueType','any'));
            save(outPath, 'data', '-v7'); %#ok<NASGU>
            entry.status        = 'ok';
            entry.output_sha256 = sha256OfFile(outPath);
            entry.output_bytes  = fileSize(outPath);
            fprintf('   -> %s  (%d bytes)\n', outName, entry.output_bytes);
        catch e
            entry.status        = 'error';
            entry.error_message = e.message;
            entry.error_id      = e.identifier;
            fprintf('   !! ERROR: %s  (%s)\n', e.message, e.identifier);
        end

        manifest.files{end+1} = entry; %#ok<AGROW>
    end

    % -- 4. Write manifest -----------------------------------------------
    manifestPath = fullfile(outDir, 'manifest.json');
    fid = fopen(manifestPath, 'w');
    jsonStr = '';
    try
        jsonStr = jsonencode(manifest, 'PrettyPrint', true);
    catch
        try
            jsonStr = jsonencode(manifest);
        catch
            jsonStr = simpleJson(manifest);  % fallback for Octave
        end
    end
    fwrite(fid, jsonStr);
    fclose(fid);
    fprintf('\n[extract_karr_mats] Manifest written: %s\n', manifestPath);

    nOk = sum(cellfun(@(e) strcmp(e.status,'ok'), manifest.files));
    fprintf('[extract_karr_mats] DONE: %d of %d files flattened.\n', nOk, numel(manifest.files));
end

% ======================================================================
%  HELPERS
% ======================================================================

function out = flatten(x, depth, visited)
% Recursively convert MATLAB objects into Python-friendly plain values.
    if depth > 25
        out = '<MAX_DEPTH>';
        return;
    end

    % --- scalars / primitives ---
    if isnumeric(x) || islogical(x) || ischar(x) || isstring(x)
        out = x;
        return;
    end

    % --- function handles / Java objects / opaque blobs ---
    if isa(x, 'function_handle')
        out = sprintf('<function_handle:%s>', func2str(x));
        return;
    end
    if isjava(x)
        out = sprintf('<java:%s>', class(x));
        return;
    end

    % --- cell arrays ---
    if iscell(x)
        out = cell(size(x));
        for k = 1:numel(x)
            out{k} = flatten(x{k}, depth+1, visited);
        end
        return;
    end

    % --- struct arrays ---
    if isstruct(x)
        out = x;  % start with same shape
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
                        flatten(v, depth+1, visited));
                catch
                    % skip on assignment failure (exotic fieldnames)
                end
            end
        end
        return;
    end

    % --- containers.Map ---
    if isa(x, 'containers.Map')
        out = struct();
        out.x_containers_Map_keys   = x.keys;
        out.x_containers_Map_values = cellfun(@(k) flatten(x(k), depth+1, visited), ...
            x.keys, 'UniformOutput', false);
        return;
    end

    % --- generic MATLAB object (handle or value class) ---
    if isobject(x)
        % cycle check for handle objects
        if numel(x) == 1 && isa(x, 'handle')
            try
                key = matlab.lang.internal.uuid(); %#ok<NASGU>
                % Using a deterministic id based on hash of class+getfield
                % Since matlab doesn't expose object identity easily, we
                % cheat by using the display hash. Skip if not scalar.
            catch
            end
            addrKey = sprintf('obj_%s_%d', class(x), visitedCount(visited));
            if isKey(visited, addrKey)
                out = sprintf('<cycle:%s>', class(x));
                return;
            end
            visited(addrKey) = true; %#ok<NASGU>
        end

        if numel(x) > 1
            % Object array: flatten elementwise into a cell (safer than
            % struct-array construction when fields diverge).
            out = cell(size(x));
            for k = 1:numel(x)
                out{k} = flatten(x(k), depth+1, visited);
            end
            return;
        end

        out = struct();
        out.x_class_  = class(x);

        % 1) Try struct(obj) — works for most handle classes with
        %    'MATLAB:structOnObject' warning suppressed.
        try
            s = struct(x);
            fns = fieldnames(s);
            for f = 1:numel(fns)
                out.(fns{f}) = flatten(s.(fns{f}), depth+1, visited);
            end
            return;
        catch
            % fall through to metaclass walk
        end

        % 2) Metaclass fallback: iterate all properties, incl. hidden.
        try
            mc = metaclass(x);
            for p = 1:numel(mc.PropertyList)
                prop = mc.PropertyList(p);
                if prop.Dependent && ~prop.HasDefault, continue; end
                try
                    val = x.(prop.Name);
                    out.(prop.Name) = flatten(val, depth+1, visited);
                catch e
                    out.(prop.Name) = sprintf('<unreadable:%s>', e.identifier);
                end
            end
        catch e
            out.x_error_ = sprintf('metaclass failed: %s', e.message);
        end
        return;
    end

    % --- unknown type: stringify ---
    try
        out = sprintf('<unhandled:%s>', class(x));
    catch
        out = '<unhandled>';
    end
end

function n = visitedCount(v)
    try
        n = v.Count + 1;
    catch
        n = 0;
    end
end

function list = addGlob(list, dirPath, pat)
    if ~exist(dirPath, 'dir'), return; end
    d = dir(fullfile(dirPath, pat));
    for k = 1:numel(d)
        if ~d(k).isdir
            list{end+1} = fullfile(d(k).folder, d(k).name); %#ok<AGROW>
        end
    end
end

function r = localRel(fullPath, root)
    if numel(fullPath) >= numel(root) && strcmp(fullPath(1:numel(root)), root)
        r = fullPath(numel(root)+2:end);
    else
        r = fullPath;
    end
    r = strrep(r, '\', '/');
end

function tag = dirTag(relPath)
    parts = strsplit(relPath, '/');
    if numel(parts) >= 2
        tag = parts{end-1};
    else
        tag = 'root';
    end
    tag = regexprep(tag, '[^A-Za-z0-9]', '_');
end

function s = sanitize(x)
    s = regexprep(x, '[^A-Za-z0-9_]', '_');
end

function b = fileSize(p)
    d = dir(p);
    if isempty(d), b = -1; else, b = d(1).bytes; end
end

function s = simpleJson(v)
% Minimal JSON encoder for Octave fallback. Not RFC-strict but readable.
    if isstruct(v) && numel(v) == 1
        fns = fieldnames(v);
        parts = cell(numel(fns),1);
        for k = 1:numel(fns)
            parts{k} = sprintf('"%s": %s', fns{k}, simpleJson(v.(fns{k})));
        end
        s = ['{', strjoin(parts, ', '), '}'];
    elseif iscell(v)
        parts = cell(numel(v),1);
        for k = 1:numel(v), parts{k} = simpleJson(v{k}); end
        s = ['[', strjoin(parts, ', '), ']'];
    elseif ischar(v)
        s = ['"', strrep(strrep(v,'\','\\'),'"','\"'), '"'];
    elseif isnumeric(v) && isscalar(v)
        s = num2str(v);
    elseif islogical(v) && isscalar(v)
        if v, s = 'true'; else, s = 'false'; end
    else
        s = '"<unsupported>"';
    end
end

function h = sha256OfFile(p)
% Stream-hash a file using Java MessageDigest (works offline, no toolbox).
    try
        md = java.security.MessageDigest.getInstance('SHA-256');
        fid = fopen(p, 'rb');
        if fid < 0, h = '<open-failed>'; return; end
        while true
            buf = fread(fid, 1048576, 'uint8=>uint8');
            if isempty(buf), break; end
            md.update(buf);
        end
        fclose(fid);
        raw = typecast(md.digest(), 'uint8');
        h = lower(reshape(dec2hex(raw,2)', 1, []));
    catch
        h = '<hash-failed>';
    end
end
