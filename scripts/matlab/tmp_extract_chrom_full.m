% FULL re-extract for all 5 chromosome-primary processes (50 seeds each)
% with the new Chromosome-state serializer.
%
% Deletes existing per-process trace files for the 5 chromosome procs first
% so extract_per_process_traces_v2 will regenerate them (otherwise its
% "already exists, skipping" guard short-circuits).
processes = {'Replication','ReplicationInitiation','DNARepair','DNASupercoiling','DNADamage'};

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
% mfilename('fullpath') = .../scripts/matlab/tmp_extract_chrom_full
% fileparts x3 strips: file -> matlab -> scripts -> repo

fprintf('Deleting existing chrom-primary trace files...\n');
deleted = 0;
for s = 0:49
    seed_dir = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', sprintf('per_process_traces_v2_s%03d', s));
    for i = 1:numel(processes)
        f = fullfile(seed_dir, sprintf('%s_100ticks.mat', processes{i}));
        if exist(f, 'file')
            delete(f);
            deleted = deleted + 1;
        end
    end
end
fprintf('Deleted %d files\n', deleted);

tstart = tic;
fprintf('\nChrom-primary re-extract: %d processes x 50 seeds with chromosome serializer\n', numel(processes));
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
