function this = evolveState_ppii(this)
    % Verbatim transcription of ProteinProcessingII.m evolveState
    % (data/karr_vendored_source/ProteinProcessingII.m lines 348-446).
    % `this.*` property access is replaced by struct field access
    % (identical syntax in Octave for structs); `this.randStream.
    % stochasticRound`/`.mnrnd` are replaced by local scaffold stubs
    % (stochasticRoundStub.m/mnrndStub.m) -- both are no-ops on the
    % exact-integral inputs Scenario A is constructed to produce, so this
    % substitution provably does not affect Scenario A's outcome (see
    % scripts/octave_h12_perturbation/README.md). No other line of logic
    % below differs from the vendored source.
    this.processedMonomers(this.unprocessedMonomerIndexs) = ...
        this.processedMonomers(this.unprocessedMonomerIndexs) + ...
        this.unprocessedMonomers(this.unprocessedMonomerIndexs);
    this.unprocessedMonomers(this.unprocessedMonomerIndexs) = 0;

    if ~any(this.unprocessedMonomers([this.lipoproteinMonomerIndexs; this.secretedMonomerIndexs]))
        return;
    end

    peptidaseIndexs = [this.lipoproteinMonomerIndexs; this.secretedMonomerIndexs];
    transferaseIndexs = this.lipoproteinMonomerIndexs;

    peptidaseLimit = this.enzymes(this.enzymeIndexs_signalPeptidase) * ...
        this.lipoproteinSignalPeptidaseSpecificRate * this.stepSizeSec;

    if any(this.unprocessedMonomers(transferaseIndexs))
        transferaseLimit = this.enzymes(this.enzymeIndexs_diacylglycerylTransferase) * ...
            this.lipoproteinDiacylglycerylTransferaseSpecificRate * this.stepSizeSec;

        transformations = this.unprocessedMonomers;
        transformations(peptidaseIndexs) = transformations(peptidaseIndexs) * ...
            min([1, peptidaseLimit / sum(transformations(peptidaseIndexs))]);
        transformations(transferaseIndexs) = transformations(transferaseIndexs) * ...
            min([1, transferaseLimit / sum(transformations(transferaseIndexs))]);
        transformations = stochasticRoundStub(transformations);
        if sum(transformations(peptidaseIndexs)) > this.substrates(this.substrateIndexs_water)
            transformations(peptidaseIndexs) = min(transformations(peptidaseIndexs), ...
                mnrndStub(this.substrates(this.substrateIndexs_water), ...
                transformations(peptidaseIndexs) / sum(transformations(peptidaseIndexs)))');
        end
        if sum(transformations(transferaseIndexs)) > this.substrates(this.substrateIndexs_PG160)
            transformations(transferaseIndexs) = min(transformations(transferaseIndexs), ...
                mnrndStub(this.substrates(this.substrateIndexs_PG160), ...
                transformations(transferaseIndexs) / sum(transformations(transferaseIndexs)))');
        end

        this.signalSequenceMonomers(peptidaseIndexs) = ...
            this.signalSequenceMonomers(peptidaseIndexs) + transformations(peptidaseIndexs);
        this.processedMonomers = this.processedMonomers + transformations;
        this.unprocessedMonomers = this.unprocessedMonomers - transformations;

        peptidaseLimit = peptidaseLimit - sum(transformations(peptidaseIndexs));

        this.substrates(this.substrateIndexs_water) = this.substrates(this.substrateIndexs_water) - ...
            sum(transformations(peptidaseIndexs));
        this.substrates([this.substrateIndexs_PG160; this.substrateIndexs_SNGLYP; this.substrateIndexs_hydrogen]) = ...
            this.substrates([this.substrateIndexs_PG160; this.substrateIndexs_SNGLYP; this.substrateIndexs_hydrogen]) + ...
            [-1;1;1] * sum(transformations(transferaseIndexs));
    end

    transformations = this.unprocessedMonomers;
    transformations(peptidaseIndexs) = transformations(peptidaseIndexs) * ...
        min([1, peptidaseLimit / sum(transformations(peptidaseIndexs))]);
    transformations(transferaseIndexs) = 0;
    if any(transformations)
        transformations = stochasticRoundStub(transformations);
        if sum(transformations(peptidaseIndexs)) > this.substrates(this.substrateIndexs_water)
            transformations(peptidaseIndexs) = min(transformations(peptidaseIndexs), ...
                mnrndStub(this.substrates(this.substrateIndexs_water), ...
                transformations(peptidaseIndexs) / sum(transformations(peptidaseIndexs)))');
        end

        this.signalSequenceMonomers(peptidaseIndexs) = ...
            this.signalSequenceMonomers(peptidaseIndexs) + transformations(peptidaseIndexs);
        this.processedMonomers = this.processedMonomers + transformations;
        this.unprocessedMonomers = this.unprocessedMonomers - transformations;

        this.substrates(this.substrateIndexs_water) = this.substrates(this.substrateIndexs_water) - ...
            sum(transformations(peptidaseIndexs));
    end
end
