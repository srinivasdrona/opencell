function extract_txreg_releasable_proteins()
% extract_txreg_releasable_proteins  One-time extraction of Karr's
% Chromosome.m::getReleasableProteins(bindingMonomers, bindingComplexs)
% result for each of TranscriptionalRegulation's 5 transcription factors.
%
% Source: edu.stanford.covert.cell.sim.state.Chromosome.m:1575
% getReleasableProteins(this, bindingMonomers, bindingComplexs) -- a
% STATIC (chromosome-state-independent) per-protein-identity property: the
% set of complex/monomer global indices that a given query protein is
% allowed to displace/release when binding a site, based on
% reaction-catalysis relationships (reactionMonomerCatalysisMatrix,
% reactionComplexCatalysisMatrix, reactionBoundMonomer/Complex,
% reactionThresholds) -- NOT on the current chromosome occupancy. This is
% the missing exemption `_third_party_site_occluded` (in
% opencell/vivarium/karr_transcriptional_regulation.py) never modeled: a
% third-party complex/monomer bound near a candidate TF site should NOT
% count as an occluding blocker if it is on the TF's own releasable list
% (empirically confirmed live: TF3/MG_236_MONOMER's site2 candidate at
% tick 11 of the genuine 4000-tick trace is occluded-by-proximity by a
% 630nt-footprint complex (global index 82), but real MATLAB
% isRegionAccessible reports it ACCESSIBLE because complex 82 is on TF3's
% releasableComplexIndexs list).
%
% Since bindProteinToChromosome is always called with EXACTLY 1 protein
% species (isBindingStable enforces "Can only bind 1 protein at a time"),
% this is queried once per TF (never a multi-protein union), matching the
% real per-tick call shape exactly.

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
addpath(matlab_dir);

[sim, ~, ~] = karr_bootstrap();
txreg = sim.process('TranscriptionalRegulation');
chromosome = sim.state('Chromosome');

tf_wids = txreg.enzymeWholeCellModelIDs;
n_tf = numel(tf_wids);
fprintf('[extract] %d TFs: %s\n', n_tf, strjoin(tf_wids, ', '));

results = struct();
results.tf_wids = {tf_wids};
per_tf = cell(n_tf, 1);

for i = 1:n_tf
    local_idx = i;
    global_monomer_idx = txreg.enzymeMonomerGlobalIndexs(txreg.enzymeMonomerLocalIndexs == local_idx);
    global_complex_idx = txreg.enzymeComplexGlobalIndexs(txreg.enzymeComplexLocalIndexs == local_idx);

    [releasableMonomerIndexs, releasableComplexIndexs] = ...
        chromosome.getReleasableProteins(global_monomer_idx, global_complex_idx);

    % 0 is the sentinel "no releasable proteins" value getReleasableProteins
    % returns per its own source (see the `else releasableXIndexs = 0;`
    % branches) -- strip it so the fixture's set is a clean, possibly-empty
    % index list.
    releasableMonomerIndexs = releasableMonomerIndexs(releasableMonomerIndexs ~= 0);
    releasableComplexIndexs = releasableComplexIndexs(releasableComplexIndexs ~= 0);

    % Own DNA footprint of the TF ITSELF (the QUERY protein in
    % isRegionAccessible/isRegionProteinFree's overlap test -- NOT the
    % footprint of whatever occupant might already be bound nearby). Real
    % MATLAB: `footprint = max([1; monomerDNAFootprints(monomers);
    % complexDNAFootprints(complexs)])` (Chromosome.m::getDNAFootprint),
    % then `[footprint3Prime, footprint5Prime] =
    % calculateFootprintOverhangs(footprint)` (symmetric-ish split of
    % footprint-1). Previously `_third_party_site_occluded` incorrectly
    % used the OCCUPANT's own footprint centered on the OCCUPANT's
    % position for this test -- empirically found wrong live (tick 221 of
    % the genuine 4000-tick trace: TF4/MG_428_DIMER's real occlusion by a
    % 75nt-footprint complex 70nt away only reproduces using TF4's OWN
    % 28nt footprint in a proper interval-overlap test against the
    % occupant's own start-anchored span, not a symmetric window centered
    % on the occupant).
    [own_footprint, own_footprint_3prime, own_footprint_5prime] = ...
        chromosome.getDNAFootprint(global_monomer_idx, global_complex_idx);

    fprintf('[extract] TF %d (%s): global_monomer_idx=%s global_complex_idx=%s releasable_monomers=%s releasable_complexes=%s own_footprint=%d (3prime=%d 5prime=%d)\n', ...
        i, tf_wids{i}, mat2str(global_monomer_idx), mat2str(global_complex_idx), ...
        mat2str(releasableMonomerIndexs'), mat2str(releasableComplexIndexs'), ...
        own_footprint, own_footprint_3prime, own_footprint_5prime);

    entry = struct();
    entry.tf_wid = tf_wids{i};
    entry.local_idx = i;
    entry.global_monomer_idx = double(global_monomer_idx);
    entry.global_complex_idx = double(global_complex_idx);
    entry.releasable_monomer_global_idxs = double(releasableMonomerIndexs(:)');
    entry.releasable_complex_global_idxs = double(releasableComplexIndexs(:)');
    entry.own_footprint = double(own_footprint);
    entry.own_footprint_3prime = double(own_footprint_3prime);
    entry.own_footprint_5prime = double(own_footprint_5prime);
    per_tf{i} = entry;
end

results.per_tf = per_tf;

repo_root = fileparts(fileparts(matlab_dir));
out_path = fullfile(repo_root, 'data', 'karr_fixtures', 'per_process', 'TranscriptionalRegulation_releasable_proteins.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results, 'PrettyPrint', true));
fclose(fid);
fprintf('[extract] wrote %s\n', out_path);

end
