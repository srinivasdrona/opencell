function summary = pick_snapshot_properties_smoke_test(varargin)
% Smoke-test the checked-in pick_snapshot_properties allowlist across
% the 22 in-scope processes. Because the helper is a local function inside
% extract_per_process_traces_v2.m, this test materializes an equivalent
% top-level function from the on-disk source text and calls it directly.

opts = parse_inputs(varargin{:});
repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));

full_allowlist = { ...
    'substrates', 'enzymes', 'boundEnzymes', ...
    'freeRNAs', 'aminoacylatedRNAs', ...
    'mRNAs', 'freeTRNAs', 'freeTMRNA', ...
    'aminoacylatedTRNAs', 'aminoacylatedTMRNA', 'boundTMRNA', ...
    'unprocessedRNAs', 'processedRNAs', 'intergenicRNAs', ...
    'unmodifiedRNAs', 'modifiedRNAs', ...
    'unprocessedMonomers', 'processedMonomers', ...
    'signalSequenceMonomers', ...
    'unmodifiedMonomers', 'modifiedMonomers', ...
    'unfoldedMonomers', 'foldedMonomers', ...
    'unfoldedComplexs', 'foldedComplexs', ...
    'inactiveMonomers', 'matureMonomers', ...
    'inactiveComplexs', 'matureComplexs', ...
    'complexs', 'monomers', 'rnas', 'RNAs', ...
};

audit_sensitive_props = { ...
    'mRNAs', 'freeTRNAs', 'freeTMRNA', ...
    'aminoacylatedTRNAs', 'aminoacylatedTMRNA', 'boundTMRNA', ...
    'intergenicRNAs', 'signalSequenceMonomers', ...
    'unfoldedComplexs', 'foldedComplexs', 'RNAs', ...
};

affected_processes = { ...
    'Translation', 'Transcription', 'RNAProcessing', 'RNADecay', ...
    'ProteinFolding', 'ProteinDecay', 'RibosomeAssembly', 'ProteinProcessingII', ...
};

source_allowlist = parse_allowlist_from_source(repo_root);
if ~isequal(source_allowlist, full_allowlist)
    error('pick_snapshot_properties_smoke_test:AllowlistMismatch', ...
        'Checked-in allowlist does not match the SB-2a fix block.');
end

helper_allowlist = source_allowlist(~ismember(source_allowlist, opts.RemoveAllowlistProps));
[helper_dir, helper_cleanup] = materialize_pick_snapshot_properties(helper_allowlist);
cleanup_helper = onCleanup(@() helper_cleanup()); %#ok<NASGU>
addpath(helper_dir);

sim = [];
bootstrap_error = '';
try
    sim = karr_bootstrap();
catch err
    bootstrap_error = getReport(err, 'extended', 'hyperlinks', 'off');
end

pass_count = 0;
fail_count = 0;
skipped_count = 0;
failures = {};
skips = {};

for i = 1:numel(opts.Processes)
    process_name = opts.Processes{i};
    if ~isempty(bootstrap_error)
        skipped_count = skipped_count + 1;
        msg = sprintf('SKIPPED %s: bootstrap failed: %s', process_name, first_line(bootstrap_error));
        skips{end + 1} = msg; %#ok<AGROW>
        fprintf('%s\n', msg);
        continue;
    end

    try
        proc = resolve_process(sim, process_name);
        class_file = which(class(proc));
        if isempty(class_file)
            throw_skip('class file not found on MATLAB path');
        end

        props = pick_snapshot_properties(proc);
        class_props = properties(proc);
        expected = intersect(class_props, full_allowlist);
        if isempty(expected)
            error('pick_snapshot_properties_smoke_test:EmptyExpected', ...
                'No allowlisted properties found on instantiated process.');
        end
        if ~isequal(props, expected)
            error('pick_snapshot_properties_smoke_test:Mismatch', ...
                'Expected {%s} but got {%s}.', strjoin(expected, ', '), strjoin(props, ', '));
        end

        audit_expected = intersect(class_props, audit_sensitive_props);
        if ismember(process_name, affected_processes)
            if isempty(audit_expected)
                error('pick_snapshot_properties_smoke_test:MissingAuditProps', ...
                    'Affected process exposed none of the audit-sensitive properties.');
            end
            missing_audit = setdiff(audit_expected, props);
            if ~isempty(missing_audit)
                error('pick_snapshot_properties_smoke_test:MissingAuditProps', ...
                    'Missing audit-sensitive properties: %s', strjoin(missing_audit, ', '));
            end
        end

        extra_expected = lookup_expected_props(opts.InjectedExpectedProps, process_name);
        if ~isempty(extra_expected)
            missing_extra = setdiff(extra_expected, props);
            if ~isempty(missing_extra)
                error('pick_snapshot_properties_smoke_test:InjectedExpectationFailed', ...
                    'Missing injected expected properties: %s', strjoin(missing_extra, ', '));
            end
        end

        pass_count = pass_count + 1;
        fprintf('PASS %s: %s | class=%s\n', process_name, strjoin(props, ', '), class_file);
    catch err
        if strcmp(err.identifier, 'pick_snapshot_properties_smoke_test:Skip')
            skipped_count = skipped_count + 1;
            msg = sprintf('SKIPPED %s: %s', process_name, err.message);
            skips{end + 1} = msg; %#ok<AGROW>
            fprintf('%s\n', msg);
        else
            fail_count = fail_count + 1;
            msg = sprintf('FAIL %s: %s', process_name, err.message);
            failures{end + 1} = msg; %#ok<AGROW>
            fprintf('%s\n', msg);
        end
    end
end

fprintf('PASS=%d FAIL=%d SKIPPED=%d\n', pass_count, fail_count, skipped_count);

summary = struct();
summary.pass = pass_count;
summary.fail = fail_count;
summary.skipped = skipped_count;
summary.failures = {failures};
summary.skips = {skips};

if fail_count > 0 || pass_count == 0
    error('pick_snapshot_properties_smoke_test:Failures', ...
        'Smoke test failed (PASS=%d FAIL=%d SKIPPED=%d).', ...
        pass_count, fail_count, skipped_count);
end
end

function opts = parse_inputs(varargin)
default_processes = { ...
    'Translation', 'Transcription', 'ReplicationInitiation', 'DNARepair', ...
    'Replication', 'DNASupercoiling', 'RNAProcessing', 'RNAModification', ...
    'RNADecay', 'tRNAAminoacylation', 'ProteinModification', 'ProteinFolding', ...
    'ProteinDecay', 'ProteinTranslocation', 'MacromolecularComplexation', ...
    'RibosomeAssembly', 'FtsZPolymerization', 'Cytokinesis', 'Metabolism', ...
    'DNADamage', 'ProteinProcessingI', 'ProteinProcessingII', ...
};

parser = inputParser();
parser.FunctionName = mfilename;
addParameter(parser, 'Processes', default_processes);
addParameter(parser, 'RemoveAllowlistProps', {});
addParameter(parser, 'InjectedExpectedProps', struct());
parse(parser, varargin{:});

opts = parser.Results;
opts.Processes = normalize_cellstr(opts.Processes);
opts.RemoveAllowlistProps = normalize_cellstr(opts.RemoveAllowlistProps);
end

function values = normalize_cellstr(values)
if isempty(values)
    values = {};
elseif isstring(values)
    values = cellstr(values);
elseif ischar(values)
    values = {values};
else
    values = cellfun(@char, values, 'UniformOutput', false);
end
end

function allowlist = parse_allowlist_from_source(repo_root)
target_file = fullfile(repo_root, 'scripts', 'matlab', 'extract_per_process_traces_v2.m');
source_text = fileread(target_file);
tokens = regexp(source_text, ...
    'function props = pick_snapshot_properties\(proc\)([\s\S]*?)\nend', ...
    'tokens', 'once');
if isempty(tokens)
    error('pick_snapshot_properties_smoke_test:ParseError', ...
        'Could not locate pick_snapshot_properties in %s.', target_file);
end
quoted = regexp(tokens{1}, '''([^'']+)''', 'tokens');
allowlist = cellfun(@(item) item{1}, quoted, 'UniformOutput', false);
end

function [helper_dir, cleanup_fn] = materialize_pick_snapshot_properties(allowlist)
helper_dir = tempname();
mkdir(helper_dir);
helper_file = fullfile(helper_dir, 'pick_snapshot_properties.m');

fid = fopen(helper_file, 'w');
if fid == -1
    error('pick_snapshot_properties_smoke_test:WriteError', ...
        'Unable to create helper file: %s', helper_file);
end

fprintf(fid, 'function props = pick_snapshot_properties(proc)\n');
fprintf(fid, 'props = intersect(properties(proc), { ...\n');
for i = 1:numel(allowlist)
    suffix = '';
    if i < numel(allowlist)
        suffix = ', ...';
    end
    fprintf(fid, '    ''%s''%s\n', allowlist{i}, suffix);
end
fprintf(fid, '});\n');
fprintf(fid, 'end\n');
fclose(fid);

cleanup_fn = @() cleanup_helper_dir(helper_dir);
end

function cleanup_helper_dir(helper_dir)
if contains(path, helper_dir)
    rmpath(helper_dir);
end
if exist(helper_dir, 'dir')
    rmdir(helper_dir, 's');
end
end

function proc = resolve_process(sim, process_name)
try
    proc = sim.process(process_name);
    return;
catch
end

target_id = ['Process_' process_name];
for i = 1:numel(sim.processes)
    candidate = sim.processes{i};
    if strcmp(candidate.wholeCellModelID, target_id)
        proc = candidate;
        return;
    end
end

throw_skip(sprintf('process could not be resolved: %s', process_name));
end

function values = lookup_expected_props(injected_expected, process_name)
values = {};
if ~isstruct(injected_expected) || isempty(fieldnames(injected_expected))
    return;
end
if isfield(injected_expected, process_name)
    values = normalize_cellstr(injected_expected.(process_name));
end
end

function throw_skip(message)
err = MException('pick_snapshot_properties_smoke_test:Skip', message);
throw(err);
end

function line = first_line(text)
parts = regexp(text, '\r?\n', 'split');
line = strtrim(parts{1});
end
