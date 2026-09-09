% Probe: does RandStream.randperm(n) consume exactly n raw draws, and does
% argsort(rand(1,n)) from the same starting state reproduce randperm's
% output? Answers whether MATLAB's randperm can be replayed as "draw n
% raw uniforms, argsort" using only raw draws already captured by the
% existing black-box replay-forward ledger (no reimplementation of
% mcg16807 needed either way).
function probe_randperm_algorithm()
addpath('scripts/matlab');
results = struct('n', {}, 'perm', {}, 'raw_draws', {}, 'argsort_of_raw', {}, ...
    'state_after_randperm', {}, 'state_after_rawdraws', {}, 'states_match', {}, ...
    'perm_equals_argsort', {}, 'perm_equals_argsort_desc', {});

ns = [3, 5, 9, 12, 20];
for i = 1:numel(ns)
    n = ns(i);

    sA = RandStream('mcg16807', 'Seed', 12345);
    sA.State = sA.State; % no-op, just to fix a known starting state
    startState = sA.State;

    permOut = randperm(sA, n);
    stateAfterPerm = sA.State;

    sB = RandStream('mcg16807', 'Seed', 12345);
    sB.State = startState;
    rawDraws = rand(sB, 1, n);
    stateAfterRaw = sB.State;

    [~, ascIdx] = sort(rawDraws, 'ascend');
    [~, descIdx] = sort(rawDraws, 'descend');

    r = struct();
    r.n = n;
    r.perm = permOut;
    r.raw_draws = rawDraws;
    r.argsort_of_raw = ascIdx;
    r.state_after_randperm = double(stateAfterPerm);
    r.state_after_rawdraws = double(stateAfterRaw);
    r.states_match = isequal(stateAfterPerm, stateAfterRaw);
    r.perm_equals_argsort = isequal(permOut, ascIdx);
    r.perm_equals_argsort_desc = isequal(permOut, descIdx);
    results(end + 1) = r; %#ok<AGROW>
end

out_path = fullfile(pwd, 'tmp', 'probe_randperm_algorithm_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('wrote %s\n', out_path);
for i = 1:numel(results)
    r = results(i);
    fprintf('n=%d states_match=%d perm_eq_argsort_asc=%d perm_eq_argsort_desc=%d\n', ...
        r.n, r.states_match, r.perm_equals_argsort, r.perm_equals_argsort_desc);
end
end
