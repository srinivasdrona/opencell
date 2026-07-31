function rates = buildProteinComplexs_rates_collisionTheory(totalProteinMonomers, proteinComplexMatrix, normalization)
    % Verbatim transcription of MacromolecularComplexation.m lines 360-388.
    rates = prod((totalProteinMonomers(:, ones(size(proteinComplexMatrix,2), 1)) / mean(totalProteinMonomers)) .^ proteinComplexMatrix, 1)';
    ub = buildProteinComplexs_bounds(totalProteinMonomers, proteinComplexMatrix);
    rates(ub == 0) = 0;
    if nargin >= 3
        switch normalization(1)
            case 'c'
                rates = cumsum(rates);
                rates = rates / rates(end);
            case 'p'
                rates = rates / sum(rates);
            otherwise
                error('MacromolecularComplexation:error', 'Invalid normalization');
        end
    end
end
