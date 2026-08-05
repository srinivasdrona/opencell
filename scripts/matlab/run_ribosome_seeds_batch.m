% run_ribosome_seeds_batch.m
% Batch extractor for RibosomeAssembly event-window seeds 2-49 (seed 0
% reused from validated main-integrate provenance; seed 1 already
% extracted in this worktree). Mirrors exactly the per-seed MATLAB command
% scripts/l2_event/launcher.py's build_matlab_command would generate for
% each seed (same extract_per_process_traces_v2 call signature, same
% tick_offset=200/n_ticks=100 fixed-window contract, same diary-per-seed
% logging path), just looped in a single MATLAB session to avoid 48
% redundant cold starts.
%
% Resumable and non-destructive (Opus review, 2026-08-05): unlike relying
% on extract_per_process_traces_v2's own bare existence check (which would
% permanently and silently "skip" a truncated/corrupt output forever --
% e.g. from a MATLAB crash, license expiry, or Ctrl-C mid-`save`), this
% script:
%   1. validates an EXISTING final output file (structurally: required
%      .mat variables present, metadata.rng_seed matches) before deciding
%      to skip it -- an invalid existing file is treated as absent, never
%      trusted merely because it exists;
%   2. always extracts to a fresh, uniquely-named TEMP output_subdir
%      first, validates THAT freshly-written file the same way, and only
%      then atomically moves (movefile, a same-filesystem rename) it into
%      the real final path -- so the real final path is either the
%      complete prior file (untouched) or the complete new one, never a
%      truncated intermediate, and a failed/incomplete extraction can
%      never destroy previously-good evidence;
%   3. accumulates every seed's failure (extraction error OR
%      post-extraction validation failure) instead of swallowing it, and
%      exits nonzero if ANY seed failed -- a caller must never see exit 0
%      alongside an incomplete N=50 cohort.
%
% This MATLAB-native validation is deliberately NOT a substitute for the
% full Python-side contract check
% (scripts.l2_event.launcher.validate_existing_event_window, re-run over
% every seed by scripts/l2_event/ribosome_assembly_seed_audit.py after
% this batch completes) -- it exists only to catch the specific
% truncated/corrupt-file failure mode this batch script could otherwise
% itself introduce.
addpath('scripts/matlab');

process_name = 'RibosomeAssembly';
n_ticks = 100;
tick_offset = 200;
seeds_to_run = 2:49;

failed_seeds = {};

for si = 1:numel(seeds_to_run)
    s = seeds_to_run(si);
    log_relpath = sprintf('artifacts/l2_event_extraction/logs/RibosomeAssembly_seed%03d.log', s);
    log_dir_ = fileparts(log_relpath);
    if ~isempty(log_dir_) && ~exist(log_dir_, 'dir')
        mkdir(log_dir_);
    end
    diary(log_relpath);
    fprintf('\n[batch] === seed %d (%d/%d) ===\n', s, si, numel(seeds_to_run));

    final_subdir = sprintf('per_process_traces_v2_event_s%03d', s);
    final_path = fullfile('data', 'm1_sources', 'karr_native', final_subdir, ...
        sprintf('%s_%dticks.mat', process_name, n_ticks));

    if exist(final_path, 'file')
        [existing_ok, existing_reason] = ribosome_batch_validate_seed_mat(final_path, s);
        if existing_ok
            fprintf('[batch] seed %d: existing output already validated, skipping: %s\n', s, final_path);
            diary off;
            continue;
        end
        fprintf(['[batch] seed %d: existing output at %s FAILED validation (%s) -- ' ...
            're-extracting to a temp path; it will replace the existing file ONLY if ' ...
            'the new extraction independently validates.\n'], s, final_path, existing_reason);
    end

    [~, unique_token] = fileparts(tempname());
    tmp_subdir = sprintf('%s__tmp_%s', final_subdir, unique_token);
    tmp_path = fullfile('data', 'm1_sources', 'karr_native', tmp_subdir, ...
        sprintf('%s_%dticks.mat', process_name, n_ticks));

    try
        extract_per_process_traces_v2({process_name}, tmp_subdir, n_ticks, uint32(s), tick_offset, 'fixed');
        [tmp_ok, tmp_reason] = ribosome_batch_validate_seed_mat(tmp_path, s);
        if ~tmp_ok
            fprintf('[batch] seed %d FAILED: freshly-extracted output did not validate: %s\n', s, tmp_reason);
            failed_seeds{end + 1} = sprintf('seed %03d: %s', s, tmp_reason); %#ok<AGROW>
        else
            final_dir = fileparts(final_path);
            if ~exist(final_dir, 'dir')
                mkdir(final_dir);
            end
            % Atomic replace: tmp_path and final_path share the same
            % data/m1_sources/karr_native/ filesystem, so movefile is a
            % same-filesystem rename -- no reader can ever observe a
            % partially-written final_path.
            movefile(tmp_path, final_path, 'f');
            fprintf('[batch] seed %d OK: validated and moved into place: %s\n', s, final_path);
        end
    catch err
        msg = getReport(err, 'extended', 'hyperlinks', 'off');
        fprintf('[batch] seed %d FAILED: %s\n', s, msg);
        failed_seeds{end + 1} = sprintf('seed %03d: %s', s, msg); %#ok<AGROW>
    end

    tmp_root = fullfile('data', 'm1_sources', 'karr_native', tmp_subdir);
    if exist(tmp_root, 'dir')
        rmdir(tmp_root, 's');
    end

    diary off;
end

n_failed = numel(failed_seeds);
n_total = numel(seeds_to_run);
fprintf('\n[batch] ALL DONE: %d/%d seeds succeeded, %d failed.\n', n_total - n_failed, n_total, n_failed);
if n_failed > 0
    fprintf('[batch] FAILURES:\n');
    for i = 1:n_failed
        fprintf('  %s\n', failed_seeds{i});
    end
    exit(1);
end
exit(0);


function [ok, reason] = ribosome_batch_validate_seed_mat(mat_path, expected_seed)
% ribosome_batch_validate_seed_mat
% MATLAB-native structural validation: used both to decide whether an
% EXISTING output file may be safely skipped and to gate a freshly
% extracted temp file before it is atomically moved into place.
    ok = false;
    reason = '';
    if ~exist(mat_path, 'file')
        reason = 'file does not exist';
        return;
    end
    try
        info = whos('-file', mat_path);
        varnames = {info.name};
        required = {'states_before', 'states_after', 'metadata'};
        missing = setdiff(required, varnames);
        if ~isempty(missing)
            reason = sprintf('missing required variable(s): %s', strjoin(missing, ', '));
            return;
        end
        loaded = load(mat_path, 'metadata');
        if ~isfield(loaded, 'metadata') || ~isfield(loaded.metadata, 'rng_seed')
            reason = 'metadata.rng_seed field missing';
            return;
        end
        actual_seed = double(loaded.metadata.rng_seed);
        if actual_seed ~= double(expected_seed)
            reason = sprintf('metadata.rng_seed=%d does not match expected seed=%d', actual_seed, double(expected_seed));
            return;
        end
    catch err
        reason = sprintf('file failed to load (likely truncated/corrupt): %s', err.message);
        return;
    end
    ok = true;
end
