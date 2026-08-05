% run_ribosome_seeds_batch.m
% One-shot batch extractor for RibosomeAssembly event-window seeds 2-49
% (seed 0 reused from validated main-integrate provenance; seed 1 already
% extracted in this worktree). Mirrors exactly the per-seed MATLAB command
% scripts/l2_event/launcher.py's build_matlab_command would generate for
% each seed (same extract_per_process_traces_v2 call signature, same
% tick_offset=200/n_ticks=100 fixed-window contract, same diary-per-seed
% logging path), just looped in a single MATLAB session to avoid 48
% redundant cold starts. Resumable: extract_per_process_traces_v2 itself
% skips (does not overwrite) any seed whose output file already exists.
addpath('scripts/matlab');
seeds_to_run = 2:49;
for si = 1:numel(seeds_to_run)
    s = seeds_to_run(si);
    log_relpath = sprintf('artifacts/l2_event_extraction/logs/RibosomeAssembly_seed%03d.log', s);
    log_dir_ = fileparts(log_relpath);
    if ~isempty(log_dir_) && ~exist(log_dir_, 'dir')
        mkdir(log_dir_);
    end
    diary(log_relpath);
    fprintf('\n[batch] === seed %d (%d/%d) ===\n', s, si, numel(seeds_to_run));
    try
        extract_per_process_traces_v2({'RibosomeAssembly'}, sprintf('per_process_traces_v2_event_s%03d', s), 100, uint32(s), 200, 'fixed');
        fprintf('[batch] seed %d OK\n', s);
    catch err
        fprintf('[batch] seed %d FAILED: %s\n', s, getReport(err, 'extended', 'hyperlinks', 'off'));
    end
    diary off;
end
fprintf('\n[batch] ALL DONE\n');
exit(0);
