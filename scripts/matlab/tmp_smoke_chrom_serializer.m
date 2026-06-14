% Smoke: extract just DNASupercoiling for seed 0 with new chromosome serializer
% to a smoke output dir, so we don't overwrite existing data until verified.
delete_if_exists = @(fp) (exist(fp,'file') && delete(fp)) + 0;
out_dir = fullfile(fileparts(fileparts(mfilename('fullpath'))), '..', 'data', 'm1_sources', 'karr_native', 'per_process_traces_chrom_smoke');
if ~exist(out_dir, 'dir'), mkdir(out_dir); end
% Force a fresh output by deleting any previous smoke file
smoke_path = fullfile(out_dir, 'DNASupercoiling_100ticks.mat');
if exist(smoke_path, 'file'), delete(smoke_path); end

fprintf('Chromosome serializer smoke: DNASupercoiling seed 0, 10 ticks\n');
extract_per_process_traces_v2({'DNASupercoiling'}, 'per_process_traces_chrom_smoke', 10, uint32(0));
fprintf('Smoke done.\n');
