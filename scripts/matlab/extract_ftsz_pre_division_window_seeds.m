function extract_ftsz_pre_division_window_seeds(seed_start, seed_end, force_seeds)
% extract_ftsz_pre_division_window_seeds  Resumable division-anchored
% FtsZPolymerization extraction for the L2.event pre-division evidence path
% (scripts/l2_event/ftsz_pre_division_evidence.py).
%
% Mirrors the catalog-authoritative row for FtsZPolymerization in
% docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml (unedited by this script):
%   M_ticks: 200
%   N_seeds: 50
%   seed_window.tick_range_from_division: [-200, 0]
%
% Each seed is extracted with extract_per_process_traces_v2's
% window_contract='anchor' mode (default anchor_opts.signal_kind =
% 'diameter_decrease', the same real cell-division timing signal
% Cytokinesis's own anchor windows use -- FtsZ ring assembly and septum
% constriction are the same physical division event). tick_offset is 0 for
% 'anchor' mode: the window's start/end are discovered from the simulation's
% own state, never supplied as burn-in arithmetic.
%
% Usage (from repo root, any current working directory -- repo_root below
% is resolved from this file's own location, never from pwd):
%   matlab -batch "addpath(genpath('scripts/matlab')); extract_ftsz_pre_division_window_seeds(0, 49)"
%
% Resumable: for each seed s in [seed_start, seed_end] NOT listed in
% force_seeds, the output path
%   data/m1_sources/karr_native/per_process_traces_v2_event_s{s:03d}/FtsZPolymerization_200ticks.mat
% is skipped if it already exists. A partial run (killed, timed out,
% pre-empted) can be safely re-invoked with the same or a different range --
% completed seeds are never re-extracted, and a caller closing a partial
% deficit (e.g. scripts/l2_event/ftsz_pre_division_evidence.py's reported
% missing_seeds list) can pass exactly that list's [min, max] here.
%
% force_seeds (optional, default []): an explicit, opt-in list of seed
% numbers whose EXISTING output file must be deleted and re-extracted even
% though it is already present on disk. This is the only sanctioned
% overwrite path -- every seed NOT named here keeps the plain
% skip-if-exists behavior above, so a caller can never blanket-clobber a
% good ensemble by accident. It exists because a seed's output file can be
% present yet INVALID (rejected by
% scripts/l2_event/ftsz_pre_division_evidence.py's validate_seed_window, or
% flagged as a byte-identical duplicate of another seed's content) -- the
% plain skip-if-exists path alone would leave such a file on disk forever,
% since "the file exists" would keep matching true. See that module's
% resumable_extraction_command(), which emits this argument populated with
% exactly its own audit's invalid_seeds list.
%
% No MATLAB/Octave process is invoked by importing or reading this file --
% it only runs when explicitly executed via `run(...)` / `-batch`.

if nargin < 1 || isempty(seed_start)
    seed_start = 0;
end
if nargin < 2 || isempty(seed_end)
    seed_end = 49;
end
if nargin < 3 || isempty(force_seeds)
    force_seeds = [];
end

% repo_root is resolved from this file's own location (never from pwd), so
% output/report paths cannot diverge depending on the caller's current
% working directory when invoking `matlab -batch` -- identical pattern to
% extract_per_process_traces_v2.m's own repo_root resolution.
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

% No ad hoc WholeCell path setup here: extract_per_process_traces_v2 (called
% per seed below) already resolves its own repo_root the same way and calls
% ensure_wholecell_runtime_paths(repo_root) internally on every invocation --
% duplicating that setup here via cd/pwd would be redundant and was the
% source of this file's earlier cwd-dependent repo_root defect.
addpath(fullfile(repo_root, 'scripts', 'matlab'));

process_name = 'FtsZPolymerization';
n_ticks = 200;  % catalog M_ticks

fprintf('[ftsz-extract] seeds %d..%d, process=%s, n_ticks=%d, window_contract=anchor, force_seeds=[%s]\n', ...
    seed_start, seed_end, process_name, n_ticks, strjoin(arrayfun(@(x) sprintf('%d', x), force_seeds, 'UniformOutput', false), ', '));

% Per-seed failures are accumulated (not thrown immediately) so every
% requested seed still gets an attempt and a fprintf'd DONE/FAILED line, but
% ANY seed failure must make the WHOLE batch fail: see the error(...) call
% after this loop, which MATLAB's own `-batch` mode turns into a nonzero
% process exit code for an uncaught error. A caller must never see exit 0
% alongside a seed that silently failed to extract.
failed_seeds = {};

for s = seed_start:seed_end
    out_subdir = sprintf('per_process_traces_v2_event_s%03d', s);
    out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', out_subdir);
    out_path = fullfile(out_root, sprintf('%s_%dticks.mat', process_name, n_ticks));

    force_this = ismember(s, force_seeds);
    if exist(out_path, 'file')
        if ~force_this
            fprintf('[ftsz-extract] seed %d already present, skip: %s\n', s, out_path);
            continue;
        end
        fprintf('[ftsz-extract] seed %d: force_seeds requested, deleting existing output and re-extracting: %s\n', s, out_path);
        delete(out_path);
    end

    if ~exist(out_root, 'dir')
        mkdir(out_root);
    end

    fprintf('[ftsz-extract] seed %d/%d: extracting division-anchored window...\n', s, seed_end);
    try
        extract_per_process_traces_v2( ...
            {process_name}, out_subdir, n_ticks, uint32(s), 0, 'anchor', struct());
        fprintf('[ftsz-extract] seed %d DONE: %s\n', s, out_path);
    catch ME
        fprintf('[ftsz-extract] seed %d FAILED: %s\n', s, ME.message);
        failed_seeds{end + 1} = sprintf('seed %d: %s', s, ME.message); %#ok<AGROW>
    end
end

fprintf('[ftsz-extract] all requested seeds processed (%d..%d).\n', seed_start, seed_end);

if ~isempty(failed_seeds)
    % Any seed failure must fail the WHOLE batch: throw here so MATLAB's own
    % `-batch` mode exits nonzero for the uncaught error. Per-seed
    % diagnostics were already fprintf'd above; this aggregates them into
    % the thrown message so a single failed seed can never look like a
    % clean exit 0.
    error('extract_ftsz_pre_division_window_seeds:extraction_failed', ...
        'extraction failed for %d of %d requested seed(s):\n%s', ...
        numel(failed_seeds), seed_end - seed_start + 1, strjoin(failed_seeds, '\n'));
end
end
