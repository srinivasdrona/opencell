function probe_txreg_real_tick_candidates(tick0based)
% probe_txreg_real_tick_candidates  Directly compute the REAL
% `bindTranscriptionFactors` coarse candidate set AND the richer
% isRegionAccessible-filtered set for TF3 (0-based; MG_236_MONOMER is
% actually TF4 -- this generalizes probe_txreg_real_tick11_candidates.m
% to target TF-species-agnostic and any tick) at the given tick of the
% genuine 4000-tick event trace, using the ACTUAL process's own
% `tfPositionStrands`/`tfIndexs` constants (not a Python re-derivation),
% overlaid onto the real reconstructed chromosome state for that tick.

if nargin < 1 || isempty(tick0based)
    tick0based = 684;
end

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
if size(chrom_cell, 1) == 1
    chrom_tick = chrom_cell{1, tick0based + 1};
else
    chrom_tick = chrom_cell{tick0based + 1, 1};
end

siz = [double(chrom_tick.sequenceLen), double(chrom_tick.nCompartments)];
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

% Real coarse `accessible` mask exactly as bindTranscriptionFactors computes it.
accessible = ~txreg.tfBoundPromoters & reshape(chromosome.isRegionPolymerized(txreg.tfPositionStrands, 1, false), [], 2);
fprintf('[probe] tick=%d tfBoundPromoters nnz: %d\n', tick0based, nnz(txreg.tfBoundPromoters));

local_idx = find(strcmp(txreg.enzymeWholeCellModelIDs, 'MG_236_MONOMER'));
fprintf('[probe] TF3 local idx (1-based): %d\n', local_idx);
sites = find((txreg.tfIndexs == local_idx) & accessible);
fprintf('[probe] REAL coarse candidate sites (linear indices into [17,2]): %s\n', mat2str(sites'));
fprintf('[probe] numel(coarse sites) = %d\n', numel(sites));
positionsStrands = txreg.tfPositionStrands(sites, :);
weights = txreg.tfAffinities(sites);
fprintf('[probe] positions: %s\n', mat2str(positionsStrands(:,1)'));
fprintf('[probe] strands: %s\n', mat2str(positionsStrands(:,2)'));
fprintf('[probe] weights: %s\n', mat2str(weights'));
fprintf('[probe] enzymes(TF3): %g\n', txreg.enzymes(local_idx));

global_monomer_idx = txreg.enzymeMonomerGlobalIndexs(txreg.enzymeMonomerLocalIndexs == local_idx);
[tfs_rich, ~, ~, ~] = chromosome.isRegionAccessible(positionsStrands, ones(numel(sites),1), ...
    global_monomer_idx, [], false, [], false, true, false);
fprintf('[probe] rich isRegionAccessible mask (same order as coarse sites): %s\n', mat2str(tfs_rich'));
fprintf('[probe] numel(rich accessible) = %d\n', nnz(tfs_rich));

results = struct();
results.tick = tick0based;
results.sites = sites;
results.positions = positionsStrands(:,1);
results.strands = positionsStrands(:,2);
results.weights = weights;
results.rich_accessible = tfs_rich;
results.enzymes_tf3 = txreg.enzymes(local_idx);
out_path = fullfile(repo_root, 'tmp', sprintf('probe_txreg_real_tick%d_candidates_result.json', tick0based));
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('[probe] wrote %s\n', out_path);

end
