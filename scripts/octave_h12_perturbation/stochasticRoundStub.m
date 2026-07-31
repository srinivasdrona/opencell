function y = stochasticRoundStub(x)
    % Harness scaffold (NOT vendored Karr source -- the real WholeCell
    % RandStream.stochasticRound is not vendored/available in this repo).
    % Preserves-expectation stochastic rounding: floor(x) + Bernoulli(frac(x)).
    % For any exactly-integral x this is deterministic (frac(x)==0 =>
    % y==x with probability 1) -- the only regime the deterministic
    % ProteinProcessingII perturbation scenario (Scenario A, see
    % docs/phase_f/l2_2_design_a/h12/perturbation/PERTURBATION_SPEC.json)
    % relies on; see scripts/octave_h12_perturbation/README.md caveat.
    fl = floor(x);
    fr = x - fl;
    y = fl + (rand(size(x)) < fr);
end
