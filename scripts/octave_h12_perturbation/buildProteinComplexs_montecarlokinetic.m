function proteinComplexs = buildProteinComplexs_montecarlokinetic(totalProteinMonomers, proteinComplexMatrix, randStream)
    % Verbatim transcription of MacromolecularComplexation.m lines 334-358.
    % `randStream` here is a plain struct with a `.rand()` function-handle
    % field (see run_macromol_network2.m) standing in for the real
    % WholeCell RandStream object -- see the RNG-fidelity caveat in
    % scripts/octave_h12_perturbation/README.md.
    nComplexs = size(proteinComplexMatrix, 2);
    proteinComplexs = zeros(nComplexs, 1);
    while true
        cumprob = buildProteinComplexs_rates_collisionTheory(...
            totalProteinMonomers, proteinComplexMatrix, 'cumulative probability');
        if isnan(cumprob(1)); break; end;
        selectedComplex = find(randStream.rand() < cumprob, 1, 'first');
        if isempty(selectedComplex)
            selectedComplex = find(cumprob == 1, 1, 'first');
        end
        proteinComplexs(selectedComplex) = proteinComplexs(selectedComplex) + 1;
        totalProteinMonomers = totalProteinMonomers - proteinComplexMatrix(:, selectedComplex);
    end
end
