function y = mnrndStub(n, p)
    % Harness scaffold (NOT vendored Karr source -- the real WholeCell
    % RandStream.mnrnd is not vendored/available in this repo). Sequential
    % multinomial sampling of n trials into numel(p) categories with
    % probabilities p. Only exercised on the OUT-OF-SCOPE scarcity-guard
    % path (see PERTURBATION_SPEC.json "explicitly_out_of_scope_for_octave_
    % execution") -- Scenario A never reaches this function because its
    % peptidase/transferase sums never exceed the water/PG160 pools. Kept
    % here only so the verbatim evolveState_ppii.m transcription has a
    % callable symbol; its behavior is not part of any exact-match claim.
    y = zeros(1, numel(p));
    remaining = n;
    pr = p;
    for k = 1:numel(p)-1
        if remaining <= 0 || sum(pr(k:end)) <= 0
            break;
        end
        y(k) = sum(rand(1, remaining) < (pr(k) / sum(pr(k:end))));
        remaining = remaining - y(k);
    end
    y(end) = remaining;
end
