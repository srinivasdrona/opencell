function out = buildProteinComplexs_bounds(totalProteinMonomers, proteinComplexMatrix)
    % Verbatim transcription of MacromolecularComplexation.m line 390-392.
    ub = floor(min(totalProteinMonomers(:, ones(1, size(proteinComplexMatrix, 2))) ./ proteinComplexMatrix, [], 1))';
    out = ub;
end
