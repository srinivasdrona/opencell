function extract_dual_division_window_seeds(seed_start, seed_end, force_seeds, opts)
% extract_dual_division_window_seeds  Resumable one-pass dual-tap
% Cytokinesis + FtsZPolymerization division-window extraction across a
% seed range.
%
% Thin resumable/atomic driver around extract_dual_division_window.m,
% mirroring extract_ftsz_pre_division_window_seeds.m's exact resumability
% contract (skip-if-both-exist, explicit opt-in force_seeds re-extraction,
% aggregate-then-throw failure reporting) so this driver can eventually
% stand in for BOTH extract_per_process_traces_v2.m's Cytokinesis queue and
% extract_ftsz_pre_division_window_seeds.m's FtsZ queue for the remaining
% N=50 sweep -- see plan.md's 2026-09-03 operational handoff ("Build a
% one-pass dual-tap Cytokinesis+FtsZ extractor canary for seed 49 ... Do not
% reduce N=50 or disturb the live queues until both existing fail-closed
% validators accept the canary"). This driver is NOT wired into either live
% queue by this change; it exists so a single seed (or a future authorized
% batch) can be run without disturbing the two live single-process queues.
%
% Usage (from repo root):
%   matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window_seeds(49, 49)"
%   matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window_seeds(6, 6, [], struct('max_search_ticks', 100000))"
%
% Resumable: for each seed s in [seed_start, seed_end] NOT listed in
% force_seeds, extraction is skipped if BOTH
%   data/m1_sources/karr_native/per_process_traces_v2_event_s{s:03d}/Cytokinesis_{cyt_n_ticks}ticks.mat
%   data/m1_sources/karr_native/per_process_traces_v2_event_s{s:03d}/FtsZPolymerization_{ftsz_n_ticks}ticks.mat
% already exist, where cyt_n_ticks/ftsz_n_ticks are read from the shared
% docs/phase_f/l2_event/division_window_spec.json (5000/200 as of the
% 2026-09-04 window fix; was 4000/200) (extract_dual_division_window itself already refuses to
% proceed if exactly one of the two exists -- see that file's
% partial-output guard -- so this driver's own skip check is a fast-path,
% not the sole safety net).
%
% force_seeds (optional, default []): opt-in list of seeds whose existing
% output pair must be deleted and re-extracted even though present. Mirrors
% extract_ftsz_pre_division_window_seeds.m's force_seeds contract exactly,
% including the post-delete existence recheck (delete() can silently fail
% to remove a file without raising) -- a seed whose stale files survive a
% requested delete is recorded as failed, never as a silent DONE.
%
% Division-censor-contract (2026-09-08, fixed 2026-09-09 per Opus
% re-review): a forced re-extraction must ALSO delete that seed's
% division_window_attempt.json sidecar (if present) alongside both .mat
% files, and the post-delete recheck must confirm ALL THREE paths are
% gone -- a stale RIGHT_CENSORED attempt record surviving a force_seeds
% request would otherwise make extract_dual_division_window.m's own
% censored_attempt_exists guard refuse the very re-extraction this driver
% was asked to perform, permanently blocking a sanctioned re-attempt.
%
% opts (optional, default struct(), passed through unmodified to every
% extract_dual_division_window call this driver makes): lets a sanctioned
% batch run at an explicit horizon (e.g. struct('max_search_ticks', 100000)
% for the division-censor-contract's required censoring horizon) or with
% force_reattempt=true (to retry a seed whose PRIOR attempt already
% produced a RIGHT_CENSORED record -- see extract_dual_division_window.m's
% own opts.force_reattempt guard). When omitted, each call falls back to
% extract_dual_division_window's own default (division_window_selection_
% contract().max_search_ticks).
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
if nargin < 4 || isempty(opts)
    opts = struct();
end

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
addpath(fullfile(repo_root, 'scripts', 'matlab'));

cyt_n_ticks = division_window_spec('Cytokinesis');
ftsz_n_ticks = division_window_spec('FtsZPolymerization');
attempt_record_name = division_window_selection_contract().attempt_record_filename;

fprintf('[dual-extract-seeds] seeds %d..%d, processes=Cytokinesis+FtsZPolymerization, force_seeds=[%s]\n', ...
    seed_start, seed_end, strjoin(arrayfun(@(x) sprintf('%d', x), force_seeds, 'UniformOutput', false), ', '));

failed_seeds = {};
censored_seeds = {};

for s = seed_start:seed_end
    out_subdir = sprintf('per_process_traces_v2_event_s%03d', s);
    out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', out_subdir);
    cyt_out_path = fullfile(out_root, sprintf('Cytokinesis_%dticks.mat', cyt_n_ticks));
    ftsz_out_path = fullfile(out_root, sprintf('FtsZPolymerization_%dticks.mat', ftsz_n_ticks));
    attempt_record_path = fullfile(out_root, attempt_record_name);

    force_this = ismember(s, force_seeds);
    both_exist = exist(cyt_out_path, 'file') == 2 && exist(ftsz_out_path, 'file') == 2;
    if both_exist && ~force_this
        fprintf('[dual-extract-seeds] seed %d already present, skip:\n  %s\n  %s\n', s, cyt_out_path, ftsz_out_path);
        continue;
    end
    if force_this
        fprintf('[dual-extract-seeds] seed %d: force_seeds requested, deleting any existing outputs and re-extracting\n', s);
        delete_if_exists(cyt_out_path);
        delete_if_exists(ftsz_out_path);
        delete_if_exists(attempt_record_path);
        if exist(cyt_out_path, 'file') == 2 || exist(ftsz_out_path, 'file') == 2 || exist(attempt_record_path, 'file') == 2
            fprintf('[dual-extract-seeds] seed %d FAILED: force_seeds delete did not remove existing output(s)\n', s);
            failed_seeds{end + 1} = sprintf('seed %d: force_seeds delete did not remove existing output(s)', s); %#ok<AGROW>
            continue;
        end
    end

    fprintf('[dual-extract-seeds] seed %d/%d: one-pass dual-tap extraction...\n', s, seed_end);
    try
        extract_dual_division_window(uint32(s), opts);
        fprintf('[dual-extract-seeds] seed %d DONE\n', s);
    catch ME
        if strcmp(ME.identifier, 'extract_dual_division_window:right_censored')
            % Right-censoring (division-censor-contract, 2026-09-08) is a
            % genuine, expected, per-seed outcome under this contract --
            % NEVER folded into failed_seeds (which would make the
            % driver's aggregate-then-throw at the end incorrectly treat
            % an honest censor as an extraction defect requiring
            % investigation). extract_dual_division_window itself already
            % wrote this seed's division_window_attempt.json before
            % raising; this driver only needs to keep the ascending scan
            % moving to the next seed.
            fprintf('[dual-extract-seeds] seed %d RIGHT_CENSORED: %s\n', s, ME.message);
            censored_seeds{end + 1} = sprintf('seed %d: %s', s, ME.message); %#ok<AGROW>
        else
            fprintf('[dual-extract-seeds] seed %d FAILED: %s\n', s, ME.message);
            failed_seeds{end + 1} = sprintf('seed %d: %s', s, ME.message); %#ok<AGROW>
        end
    end
end

fprintf('[dual-extract-seeds] all requested seeds processed (%d..%d); %d censored.\n', ...
    seed_start, seed_end, numel(censored_seeds));

if ~isempty(failed_seeds)
    error('extract_dual_division_window_seeds:extraction_failed', ...
        'extraction failed for %d of %d requested seed(s):\n%s', ...
        numel(failed_seeds), seed_end - seed_start + 1, strjoin(failed_seeds, '\n'));
end
end

function delete_if_exists(path_value)
if exist(path_value, 'file') == 2
    delete(path_value);
end
end
