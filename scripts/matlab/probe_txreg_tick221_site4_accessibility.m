function probe_txreg_tick221_site4_accessibility()
% Definitive live-MATLAB ground truth for TF4 (MG_428_DIMER) site4
% (position 128603 1-based) accessibility at tick 221 (0-based) of the
% genuine 4000-tick event trace, cross-checking why real Karr does NOT
% bind here (despite site4 appearing unbound+polymerized+ostensibly
% unoccluded under OC's symmetric-footprint approximation), using the
% REAL isRegionAccessible/isRegionProteinFree/getDNAFootprint methods.

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
tick0based = 221;
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

local_idx = find(strcmp(txreg.enzymeWholeCellModelIDs, 'MG_428_DIMER'));
fprintf('[probe] TF4 local idx (1-based): %d\n', local_idx);
global_complex_idx = txreg.enzymeComplexGlobalIndexs(txreg.enzymeComplexLocalIndexs == local_idx);
fprintf('[probe] TF4 global complex idx: %s\n', mat2str(global_complex_idx));

[footprint, footprint3Prime, footprint5Prime, bindingStrandedness, regionStrandedness] = ...
    chromosome.getDNAFootprint([], global_complex_idx);
fprintf('[probe] TF4 footprint=%d footprint3Prime=%d footprint5Prime=%d bindingStrandedness=%d regionStrandedness=%d\n', ...
    footprint, footprint3Prime, footprint5Prime, bindingStrandedness, regionStrandedness);

% site4 0-based position 128602 -> 1-based 128603, strand 1 (0-based strand 0)
positionsStrands = [128603, 1];
lengths = 1;

[tfs, idxs, psOut, lensOut] = chromosome.isRegionAccessible(positionsStrands, lengths, ...
    [], global_complex_idx, false, [], false, true, false);
fprintf('[probe] isRegionAccessible (isPositionsStrandFootprintCentroid=false): tfs=%d\n', tfs);

[tfs2, idxs2, psOut2, lensOut2] = chromosome.isRegionAccessible(positionsStrands, lengths, ...
    [], global_complex_idx, true, [], false, true, false);
fprintf('[probe] isRegionAccessible (isPositionsStrandFootprintCentroid=true): tfs=%d\n', tfs2);

[tfs3, idxs3, psOut3, lensOut3, monomers3, complexs3] = chromosome.isRegionProteinFree( ...
    positionsStrands, lengths, false, [], global_complex_idx, true, false);
fprintf('[probe] isRegionProteinFree (centroid=false): tfs=%d monomers=%s complexs=%s\n', tfs3, mat2str(monomers3), mat2str(complexs3));

[tfs4, idxs4, psOut4, lensOut4, monomers4, complexs4] = chromosome.isRegionProteinFree( ...
    positionsStrands, lengths, true, [], global_complex_idx, true, false);
fprintf('[probe] isRegionProteinFree (centroid=true): tfs=%d monomers=%s complexs=%s\n', tfs4, mat2str(monomers4), mat2str(complexs4));

results = struct();
results.footprint = footprint;
results.footprint3Prime = footprint3Prime;
results.footprint5Prime = footprint5Prime;
results.accessible_centroid_false = tfs;
results.accessible_centroid_true = tfs2;
results.protein_free_centroid_false = tfs3;
results.protein_free_centroid_true = tfs4;
out_path = fullfile(repo_root, 'tmp', 'probe_txreg_tick221_site4_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('[probe] wrote %s\n', out_path);

end
