function probe_txreg_footprint_constants()
% probe_txreg_footprint_constants  Live-MATLAB extraction of
% TranscriptionalRegulation's own per-TF DNA-binding footprint widths
% (enzymeDNAFootprints, indexed by LOCAL TF index 1..5) via a full
% karr_bootstrap() Simulation object. Needed to implement the missing
% isRegionUndamaged check (Chromosome.m::isRegionAccessible checks
% polymerized + proteinFree + undamaged; the Python port had only the
% first two).

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
addpath(matlab_dir);

[sim, ~, ~] = karr_bootstrap();
txreg = sim.process('TranscriptionalRegulation');

fprintf('[probe] enzymeWholeCellModelIDs: %s\n', strjoin(txreg.enzymeWholeCellModelIDs, ', '));
fprintf('[probe] enzymeDNAFootprints (local TF index order): %s\n', mat2str(txreg.enzymeDNAFootprints));
fprintf('[probe] enzymeDNAFootprints3Prime: %s\n', mat2str(txreg.enzymeDNAFootprints3Prime));
fprintf('[probe] enzymeDNAFootprints5Prime: %s\n', mat2str(txreg.enzymeDNAFootprints5Prime));

results = struct();
results.enzyme_wids = txreg.enzymeWholeCellModelIDs;
results.enzyme_dna_footprints = txreg.enzymeDNAFootprints;
results.enzyme_dna_footprints_3prime = txreg.enzymeDNAFootprints3Prime;
results.enzyme_dna_footprints_5prime = txreg.enzymeDNAFootprints5Prime;

repo_root = fileparts(fileparts(matlab_dir));
out_path = fullfile(repo_root, 'tmp', 'probe_txreg_footprint_constants_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('[probe] wrote %s\n', out_path);

end
