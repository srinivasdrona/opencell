% FULL re-extract for all 5 chromosome-primary processes (50 seeds each)
% with the new Chromosome-state serializer.
%
% NOTE (2026-06-14): previously this script deleted all existing chrom-primary
% trace files at the start so extract_per_process_traces_v2 would regenerate
% them. That was needed for the *first* run (to overwrite placeholder data
% from the broken serializer) but is DESTRUCTIVE on restart - it throws away
% completed work. Now the destructive delete is removed; restart-friendly.
% If you need to force regeneration, delete files manually before launching.
processes = {'Replication','ReplicationInitiation','DNARepair','DNASupercoiling','DNADamage'};

tstart = tic;
fprintf('\nChrom-primary re-extract: %d processes x 50 seeds with chromosome serializer\n', numel(processes));
fprintf('(extract_per_process_traces_v2 has its own already-exists skip guard)\n');
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
