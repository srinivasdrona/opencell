% Probe: does RandStream-based weighted randsample(n,1,true,w) consume
% exactly 1 raw draw, and does it correspond to a cumulative-weight
% inverse-CDF lookup against that single draw (first index where
% cumsum(w)/sum(w) >= draw)? This determines how the DNASupercoiling
% process-RNG replay ledger's raw draws must be consumed to reproduce
% ChromosomeProcessAspect.bindProteinToChromosomeStochastically's region
% choice exactly. No reimplementation of mcg16807 -- only observing the
% documented relationship between randsample's raw-draw consumption and
% its output, exactly as was already done for randperm.
function probe_randsample_algorithm()
results = struct('n', {}, 'weights', {}, 'idx', {}, 'raw_draw', {}, ...
    'state_after_randsample', {}, 'state_after_rawdraw', {}, 'states_match', {}, ...
    'cdf_lookup_idx', {}, 'idx_equals_cdf_lookup', {});

weight_sets = { ...
    [1 1 1], ...
    [5 2 1 1 1], ...
    [10 1 1 1 1 1 1 1 1 1], ...
    [3 7], ...
    [1 1 1 1 1 1 1 1 1 1 1 1] ...
};

for i = 1:numel(weight_sets)
    w = weight_sets{i};
    n = numel(w);

    sA = RandStream('mcg16807', 'Seed', 777);
    startState = sA.State;

    idx = randsample(sA, n, 1, true, w);
    stateAfterSample = sA.State;

    sB = RandStream('mcg16807', 'Seed', 777);
    sB.State = startState;
    rawDraw = rand(sB, 1, 1);
    stateAfterRaw = sB.State;

    cdf = cumsum(w) / sum(w);
    cdfIdx = find(rawDraw <= cdf, 1, 'first');

    r = struct();
    r.n = n;
    r.weights = w;
    r.idx = idx;
    r.raw_draw = rawDraw;
    r.state_after_randsample = double(stateAfterSample);
    r.state_after_rawdraw = double(stateAfterRaw);
    r.states_match = isequal(stateAfterSample, stateAfterRaw);
    r.cdf_lookup_idx = cdfIdx;
    r.idx_equals_cdf_lookup = isequal(idx, cdfIdx);
    results(end + 1) = r; %#ok<AGROW>
end

out_path = fullfile(pwd, 'tmp', 'probe_randsample_algorithm_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('wrote %s\n', out_path);
for i = 1:numel(results)
    r = results(i);
    fprintf('n=%d states_match=%d idx=%d cdf_idx=%d idx_eq_cdf=%d\n', ...
        r.n, r.states_match, r.idx, r.cdf_lookup_idx, r.idx_equals_cdf_lookup);
end
end
