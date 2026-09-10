function probe_repinit_tick13_isregionaccessible()
% probe_repinit_tick13_isregionaccessible  l21-repinit decisive
% cross-check (standalone, current-main-safe rewrite -- see
% probe_repinit_advance_to_tick.m/probe_repinit_setup.m docstrings for
% why this is a self-contained duplicate rather than a hook wired into
% the shared extractor): calls the REAL MATLAB `Chromosome.
% isRegionAccessible` for the EXACT 28 (position, strand) candidates
% OC's own chromosome-RNG-ledger-driven replay drew from the real ledger
% at tick 13 (0-based; MATLAB tick 14, 1-based), to settle whether real
% Karr's own `isRegionAccessible` accepts the same 26/28 (matching OC) or
% fewer.
%
% Candidates and expected OC decisions are reproduced verbatim from
% `scripts/tmp_repinit_tick13_double_strand_probe.py`'s own run against
% the real ledger + real ground-truth `polymerizedRegions`/
% `linkingNumbers` at this tick (see STATUS_L21_REPINIT_SEPT2.md, Session
% N+1). Positions below are 0-based (OC/Python convention); +1 for
% MATLAB's 1-based `positionsStrands`. Strand 0 (OC) -> strand 1 (MATLAB,
% 1-based dnaABoxStartPositions/complexBoundSites strand column).
%
% Output: prints the real MATLAB tfs/extents/releasable-index/
% catalysis-matrix result for these 28 candidates to stdout and returns
% (no .mat write -- this standalone rewrite is read-only/diagnostic,
% unlike the earlier wired-into-the-extractor version whose output path
% was data/m1_sources/karr_native/tick13_accessibility_probe_adp_v4/).

positions_0based = [
    385299; 548516; 509128; 387596; 118885; 96575; 6725; 92437; 61332; ...
    205752; 327378; 559610; 137468; 13895; 19336; 510969; 511209; 526744; ...
    320252; 97482; 288855; 471316; 545925; 340103; 321265; 278303; 440049; ...
    187213];

if numel(positions_0based) ~= 28
    error('probe_repinit_tick13_isregionaccessible:bad_candidate_count', ...
        'Expected exactly 28 candidates, got %d', numel(positions_0based));
end

positions_strands = [positions_0based + 1, ones(numel(positions_0based), 1)];

[sim, target_idx] = probe_repinit_setup('ReplicationInitiation', uint32(0));
probe_fn = @(mod) local_isregionaccessible_probe(mod, positions_strands);
[~, ~, result] = probe_repinit_advance_to_tick(sim, target_idx, 14, probe_fn);

disp(result);
fprintf('[probe_repinit_tick13_isregionaccessible] done.\n');
end

function result = local_isregionaccessible_probe(mod, positions_strands)
% local_isregionaccessible_probe  Sibling (non-nested) local helper --
% called via an anonymous-function handle from the main function above,
% never a nested function sharing the caller's workspace, so this file
% needs no `end`-termination consistency across every local function
% (the exact MATLAB-legality concern the earlier wired-into-the-extractor
% version's `function capture(idx)` raised).
protein_local_index = mod.enzymeIndexs_DnaA_1mer_ADP;
monomer_gbl_indexs = mod.enzymeMonomerGlobalIndexs(mod.enzymeMonomerLocalIndexs == protein_local_index);
complex_gbl_indexs = mod.enzymeComplexGlobalIndexs(mod.enzymeComplexLocalIndexs == protein_local_index);
lengths = ones(size(positions_strands, 1), 1);
[tfs, ~, ~, extents] = mod.chromosome.isRegionAccessible(...
    positions_strands, lengths, monomer_gbl_indexs, complex_gbl_indexs, ...
    false, [], false, true, true);
[releasableMonomerIndexs, releasableComplexIndexs] = mod.chromosome.getReleasableProteins(monomer_gbl_indexs, complex_gbl_indexs);
full_matrix = full(mod.chromosome.reactionComplexCatalysisMatrix);
result = struct( ...
    'positions_strands', double(positions_strands), ...
    'tfs', double(tfs(:)'), ...
    'extents', double(extents(:)'), ...
    'monomer_gbl_indexs', double(monomer_gbl_indexs(:)'), ...
    'complex_gbl_indexs', double(complex_gbl_indexs(:)'), ...
    'releasableMonomerIndexs', double(releasableMonomerIndexs(:)'), ...
    'releasableComplexIndexs', double(releasableComplexIndexs(:)'), ...
    'catalysisMatrix_shape', double(size(full_matrix)), ...
    'catalysisMatrix_nnz_total', double(nnz(full_matrix)) ...
);
end
