function probe_txreg_real_accessibility()
% probe_txreg_real_accessibility  Definitive live-MATLAB ground truth for
% Chromosome.m::isRegionAccessible on the exact tick-11 chromosome state
% from the genuine TranscriptionalRegulation_4000ticks.mat event trace,
% for TF3 (MG_236_MONOMER)'s 8 coarse candidate sites (site0, site2, site5,
% site6, site9, site10, site12, site13; column 0 / strand 1 each).
%
% Reconstructs the real Chromosome state object's sparse properties
% directly from the trace's exported sparse-triple data (already 1-based
% MATLAB-native from the extractor), then calls the actual
% isRegionAccessible method -- no Python re-implementation, no
% approximation.

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
addpath(matlab_dir);

[sim, ~, ~] = karr_bootstrap();
txreg = sim.process('TranscriptionalRegulation');
chromosome = sim.state('Chromosome');

repo_root = fileparts(fileparts(matlab_dir));
trace_path = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', ...
    'per_process_traces_v2_event_s000', 'TranscriptionalRegulation_4000ticks.mat');
raw = load(trace_path, 'states_before');
chrom_cell = raw.states_before.chromosome;
fprintf('[probe] class(chrom_cell)=%s size=%s\n', class(chrom_cell), mat2str(size(chrom_cell)));
% tick index 11 (0-based Python) == 12th MATLAB cell (1-based)
tick0based = 11;
if size(chrom_cell, 1) == 1
    chrom_tick = chrom_cell{1, tick0based + 1};
else
    chrom_tick = chrom_cell{tick0based + 1, 1};
end
fprintf('[probe] chromosome tick struct fields: %s\n', strjoin(fieldnames(chrom_tick), ', '));

siz = [double(chrom_tick.sequenceLen), double(chrom_tick.nCompartments)];
fprintf('[probe] siz = %s\n', mat2str(siz));

sparse_field_names = {'polymerizedRegions', 'monomerBoundSites', 'complexBoundSites', ...
    'damagedBases', 'gapSites', 'abasicSites', 'damagedSugarPhosphates', ...
    'intrastrandCrossLinks', 'strandBreaks', 'hollidayJunctions'};

for i = 1:numel(sparse_field_names)
    fname = sparse_field_names{i};
    if ~isfield(chrom_tick, fname)
        continue;
    end
    entry = chrom_tick.(fname);
    if isfield(entry, 'positions') && ~isempty(entry.positions)
        subs = [double(entry.positions(:)), double(entry.strands(:))];
        vals = double(entry.values(:));
    else
        subs = zeros(0, 2);
        vals = zeros(0, 1);
    end
    mat = edu.stanford.covert.util.CircularSparseMat(subs, vals, siz, 1);
    chromosome.(fname) = mat;
end

fprintf('[probe] chromosome sparse properties overlaid from tick %d\n', tick0based);

% TF3 (MG_236_MONOMER) is local index 4 (1-based) per enzymeWholeCellModelIDs order.
local_idx = find(strcmp(txreg.enzymeWholeCellModelIDs, 'MG_236_MONOMER'));
fprintf('[probe] TF3 local index (1-based): %d\n', local_idx);
global_idx = txreg.enzymeMonomerGlobalIndexs(txreg.enzymeMonomerLocalIndexs == local_idx);
fprintf('[probe] TF3 global monomer index (1-based): %s\n', mat2str(global_idx));
fprintf('[probe] TF3 footprint via global index lookup: %d\n', chromosome.monomerDNAFootprints(global_idx));

% Candidate (position, strand) pairs -- 1-based positions/strands matching
% the trace's own convention (strand 1 = 0-based strand 0).
site_names = {'site0','site2','site5','site6','site9','site10','site12','site13'};
site_positions_0based = [15529, 39057, 160980, 188553, 353972, 374853, 402937, 446196];
positionsStrands = [double(site_positions_0based(:)) + 1, ones(numel(site_positions_0based), 1)];
lengths = ones(size(positionsStrands, 1), 1);

[tfs, idxs, psOut, lensOut] = chromosome.isRegionAccessible(positionsStrands, lengths, ...
    global_idx, [], false, [], false, true, false);

fprintf('[probe] isRegionAccessible tfs (accessible mask, in candidate order): %s\n', mat2str(tfs));
for i = 1:numel(site_names)
    fprintf('  %s -> accessible=%d\n', site_names{i}, tfs(i));
end

results = struct();
results.site_names = {site_names};
results.accessible = tfs;
out_path = fullfile(repo_root, 'tmp', 'probe_txreg_real_accessibility_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('[probe] wrote %s\n', out_path);

end
