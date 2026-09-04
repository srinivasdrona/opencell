function extract_dual_division_window_seeds(seed_start, seed_end, force_seeds)
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
%
% Resumable: for each seed s in [seed_start, seed_end] NOT listed in
% force_seeds, extraction is skipped if BOTH
%   data/m1_sources/karr_native/per_process_traces_v2_event_s{s:03d}/Cytokinesis_4000ticks.mat
%   data/m1_sources/karr_native/per_process_traces_v2_event_s{s:03d}/FtsZPolymerization_200ticks.mat
% already exist (extract_dual_division_window itself already refuses to
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

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
addpath(fullfile(repo_root, 'scripts', 'matlab'));

cyt_n_ticks = 4000;
ftsz_n_ticks = 200;

fprintf('[dual-extract-seeds] seeds %d..%d, processes=Cytokinesis+FtsZPolymerization, force_seeds=[%s]\n', ...
    seed_start, seed_end, strjoin(arrayfun(@(x) sprintf('%d', x), force_seeds, 'UniformOutput', false), ', '));

failed_seeds = {};

for s = seed_start:seed_end
    out_subdir = sprintf('per_process_traces_v2_event_s%03d', s);
    out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', out_subdir);
    cyt_out_path = fullfile(out_root, sprintf('Cytokinesis_%dticks.mat', cyt_n_ticks));
    ftsz_out_path = fullfile(out_root, sprintf('FtsZPolymerization_%dticks.mat', ftsz_n_ticks));

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
        if exist(cyt_out_path, 'file') == 2 || exist(ftsz_out_path, 'file') == 2
            fprintf('[dual-extract-seeds] seed %d FAILED: force_seeds delete did not remove existing output(s)\n', s);
            failed_seeds{end + 1} = sprintf('seed %d: force_seeds delete did not remove existing output(s)', s); %#ok<AGROW>
            continue;
        end
    end

    fprintf('[dual-extract-seeds] seed %d/%d: one-pass dual-tap extraction...\n', s, seed_end);
    try
        extract_dual_division_window(uint32(s));
        fprintf('[dual-extract-seeds] seed %d DONE\n', s);
    catch ME
        fprintf('[dual-extract-seeds] seed %d FAILED: %s\n', s, ME.message);
        failed_seeds{end + 1} = sprintf('seed %d: %s', s, ME.message); %#ok<AGROW>
    end
end

fprintf('[dual-extract-seeds] all requested seeds processed (%d..%d).\n', seed_start, seed_end);

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
