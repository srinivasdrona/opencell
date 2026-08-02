function this = evolveState_ppii_matlab(this)
    % TRUE VERBATIM transcription of ProteinProcessingII.m evolveState
    % (data/karr_vendored_source/ProteinProcessingII.m lines 349-445).
    % ZERO substitutions -- unlike scripts/octave_h12_perturbation/
    % evolveState_ppii.m (which replaces this.randStream.stochasticRound/
    % .mnrnd with free-function Octave scaffold stubs), this file keeps
    % `this.randStream.stochasticRound(...)`/`this.randStream.mnrnd(...)`
    % as literal method calls on a real `this.randStream` object. `this.*`
    % property access is struct-field access here (identical syntax to the
    % real classdef property access Karr's code uses); `this.randStream`
    % MUST be populated by the caller with a real
    % edu.stanford.covert.util.RandStream instance (see
    % run_ppii_scenario_b_matlab.m) -- there is no stub fallback in this
    % file, and none is permitted: if `this.randStream` is missing/wrong
    % type, or the Statistics Toolbox is not licensed, MATLAB itself
    % raises an error when `stochasticRound`/`mnrnd` is called, which is
    % the intended abort behavior, not a bug to work around.
    %
    % This file is checked byte-for-byte (modulo comment/whitespace
    % normalization only -- NO allowed substitutions) against
    % ProteinProcessingII.m lines 349-445 by
    % tests/scripts/test_h12_perturbation_source_binding.py.
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
        transformations = this.randStream.stochasticRound(transformations);
        if sum(transformations(peptidaseIndexs)) > this.substrates(this.substrateIndexs_water)
            transformations(peptidaseIndexs) = min(transformations(peptidaseIndexs), ...
                this.randStream.mnrnd(this.substrates(this.substrateIndexs_water), ...
                transformations(peptidaseIndexs) / sum(transformations(peptidaseIndexs)))');
        end
        if sum(transformations(transferaseIndexs)) > this.substrates(this.substrateIndexs_PG160)
            transformations(transferaseIndexs) = min(transformations(transferaseIndexs), ...
                this.randStream.mnrnd(this.substrates(this.substrateIndexs_PG160), ...
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
        transformations = this.randStream.stochasticRound(transformations);
        if sum(transformations(peptidaseIndexs)) > this.substrates(this.substrateIndexs_water)
            transformations(peptidaseIndexs) = min(transformations(peptidaseIndexs), ...
                this.randStream.mnrnd(this.substrates(this.substrateIndexs_water), ...
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
