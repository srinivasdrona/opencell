function verify_extended_draws_match_prefix()
% Sanity check before committing to the "generously-sized batch generated
% directly from process_state_before" design: for a known-good tick
% (seed 0, tick 0, already validated exact via the black-box
% replay-forward reconstruction in the committed ledger), verify that
% simply seeding a throwaway RandStream to `process_state_before` and
% drawing N=500 values directly gives a sequence whose first L values
% EXACTLY match the already-recorded `process_draws` (L = length of that
% array), and that after consuming exactly L draws the throwaway's state
% matches the recorded `process_state_after`. This validates that a
% direct large draw-from-state batch is equivalent (for the audited
% prefix) to the incremental replay-forward search already used and
% trusted -- no reliance on knowing MATLAB's internal recurrence formula,
% since MATLAB itself generates the draws either way.
addpath('scripts/matlab');
ledger_path = fullfile(pwd, 'data', 'l22_dnas_rare_event', 'chromosome_release_rng_ledger', 'seed_000.json');
raw = jsondecode(fileread(ledger_path));

results = struct('tick', {}, 'prefix_match', {}, 'state_after_match', {}, 'recorded_len', {});
for t = 1:min(10, numel(raw.ticks))
    tick = raw.ticks(t);
    state_before = double(tick.process_state_before.values);
    state_after = double(tick.process_state_after.values);
    recorded_draws = double(tick.process_draws(:)');
    L = numel(recorded_draws);

    s = RandStream('mcg16807', 'Seed', 1);
    s.State = state_before;
    big_draws = rand(s, 1, 500);
    state_after_big = double(s.State);

    if L > 0
        prefix_match = isequal(big_draws(1:L), recorded_draws);
    else
        prefix_match = true;
    end

    % Also verify state after consuming exactly L draws from the fresh
    % throwaway matches the recorded after-state (re-seed and redo L only).
    s2 = RandStream('mcg16807', 'Seed', 1);
    s2.State = state_before;
    if L > 0
        rand(s2, 1, L);
    end
    state_after_L = double(s2.State);
    state_after_match = isequal(state_after_L, state_after);

    results(end + 1) = struct( ... %#ok<AGROW>
        'tick', int32(tick.tick_zero_based), ...
        'prefix_match', prefix_match, ...
        'state_after_match', state_after_match, ...
        'recorded_len', int32(L));
end

for i = 1:numel(results)
    r = results(i);
    fprintf('tick=%d recorded_len=%d prefix_match=%d state_after_match=%d\n', ...
        r.tick, r.recorded_len, r.prefix_match, r.state_after_match);
end

out_path = fullfile(pwd, 'tmp', 'verify_extended_draws_match_prefix_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('wrote %s\n', out_path);
end
