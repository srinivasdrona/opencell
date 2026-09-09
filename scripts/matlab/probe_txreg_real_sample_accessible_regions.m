function probe_txreg_real_sample_accessible_regions()
% Final decisive check: call the REAL live
% Chromosome.m::sampleAccessibleRegions directly with the exact tick-11
% candidate set (positions/strands/weights), a REAL RandStream reset to
% seed 0, and the tick-11 ground-truth chromosome occupancy overlay, to
% see EXACTLY which site index it returns -- settling whether OC's port of
% this exact algorithm has a remaining bug, independent of any candidate/
% weight/accessibility-data question (already independently verified).

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
tick0based = 11;
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

local_idx = find(strcmp(txreg.enzymeWholeCellModelIDs, 'MG_236_MONOMER'));
global_monomer_idx = txreg.enzymeMonomerGlobalIndexs(txreg.enzymeMonomerLocalIndexs == local_idx);

accessible = ~txreg.tfBoundPromoters & reshape(chromosome.isRegionPolymerized(txreg.tfPositionStrands, 1, false), [], 2);
sites = find((txreg.tfIndexs == local_idx) & accessible);
positionsStrands = txreg.tfPositionStrands(sites, :);
weights = txreg.tfAffinities(sites);
site_names = {'site0','site2','site5','site6','site9','site10','site12','site13'};

fprintf('[probe] sites=%s\n', mat2str(sites'));
fprintf('[probe] weights=%s\n', mat2str(weights'));

% Overwrite chromosome's own randStream reference with a FRESH seed-0
% stream (the process's own randStream is what bindTranscriptionFactors
% actually uses -- chromosome.randStream is a shared reference to it via
% storeObjectReferences-style wiring in the real class; here we directly
% control it for a clean, reproducible test).
txreg.randStream.reset(0);
chromosome.randStream.reset(0);
% Chromosome delegates its OWN randStream property to whichever object
% called setSiteProteinBound -- but sampleAccessibleRegions uses
% `this.randStream` where `this` is the CHROMOSOME object itself. Confirm
% which stream it actually uses:
fprintf('[probe] chromosome.randStream is same handle as txreg.randStream: %d\n', ...
    isequal(chromosome.randStream, txreg.randStream));

lengths = ones(numel(sites), 1);
[tfs, idxs, psOut, lensOut] = chromosome.sampleAccessibleRegions(1, weights, positionsStrands, lengths, ...
    global_monomer_idx, [], false, [], true, true, false);

fprintf('[probe] sampleAccessibleRegions returned idxs (into candidate list): %s\n', mat2str(idxs'));
if ~isempty(idxs)
    fprintf('[probe] winning site: %s (candidate idx %d)\n', site_names{idxs(1)}, idxs(1));
end

results = struct();
results.sites = sites;
results.weights = weights;
results.winning_idxs = idxs;
out_path = fullfile(repo_root, 'tmp', 'probe_txreg_real_sample_accessible_regions_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('[probe] wrote %s\n', out_path);

end
