function probe_txreg_releasable_check()
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
addpath(matlab_dir);

[sim, ~, ~] = karr_bootstrap();
txreg = sim.process('TranscriptionalRegulation');
chromosome = sim.state('Chromosome');

local_idx = find(strcmp(txreg.enzymeWholeCellModelIDs, 'MG_236_MONOMER'));
global_idx = txreg.enzymeMonomerGlobalIndexs(txreg.enzymeMonomerLocalIndexs == local_idx);
fprintf('[probe] TF3 global monomer index: %s\n', mat2str(global_idx));

[releasableMonomerIndexs, releasableComplexIndexs] = chromosome.getReleasableProteins(global_idx, []);
fprintf('[probe] releasableMonomerIndexs: %s\n', mat2str(releasableMonomerIndexs));
fprintf('[probe] releasableComplexIndexs: %s\n', mat2str(releasableComplexIndexs));
fprintf('[probe] is complex 82 releasable by TF3?: %d\n', ismember(82, releasableComplexIndexs));

if isprop(chromosome, 'complexWholeCellModelIDs') || isprop(chromosome, 'complexWholeCellModelIDs')
end
try
    names = chromosome.complexWholeCellModelIDs;
    fprintf('[probe] complex 82 WID: %s\n', names{82});
catch err
    fprintf('[probe] could not resolve complex WIDs: %s\n', err.message);
end

fprintf('[probe] reactionBoundComplex nnz: %d, size: %s\n', nnz(chromosome.reactionBoundComplex), mat2str(size(chromosome.reactionBoundComplex)));
fprintf('[probe] reactionThresholds: %s\n', mat2str(chromosome.reactionThresholds(1:min(10,numel(chromosome.reactionThresholds)))));

end
