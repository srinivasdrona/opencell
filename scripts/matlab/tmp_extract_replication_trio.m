% Re-extract Replication/ReplicationInitiation/DNARepair with chromosome field
% (originals were extracted before commit b3df570 added chromosome to allowlist)
processes = {'Replication','ReplicationInitiation','DNARepair'};
tstart = tic;
fprintf('Replication trio re-extract: %d processes x 50 seeds\n', numel(processes));
for s = 0:49
    seed_dir = sprintf('per_process_traces_v2_s%03d', s);
    fprintf('\n=== SEED %d / 49 (elapsed %.1f min) ===\n', s, toc(tstart)/60);
    try
        extract_per_process_traces_v2(processes, seed_dir, 100, uint32(s));
    catch err
        fprintf('SEED %d FAILED: %s\n', s, err.message);
    end
end
fprintf('\n=== ALL SEEDS DONE - total %.1f min ===\n', toc(tstart)/60);
