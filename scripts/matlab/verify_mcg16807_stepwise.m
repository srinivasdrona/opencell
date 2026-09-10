% Robust, step-by-step verification of MATLAB's mcg16807 state/output
% transition formula. Seeds a throwaway RandStream to a KNOWN state,
% records (state_before, draw, state_after) for EVERY individual draw
% across many steps, so a candidate Python recurrence can be checked
% against EVERY single-step transition (not just a batch endpoint),
% removing any ambiguity about "how many steps until it matches".
function verify_mcg16807_stepwise()
s = RandStream('mcg16807', 'Seed', 12345);
startState = double(s.State);

n = 30;
records = struct('step', {}, 'state_before', {}, 'draw', {}, 'state_after', {});
for i = 1:n
    stateBefore = double(s.State);
    d = rand(s, 1, 1);
    stateAfter = double(s.State);
    records(end + 1) = struct( ...
        'step', int32(i), ...
        'state_before', stateBefore, ...
        'draw', double(d), ...
        'state_after', stateAfter); %#ok<AGROW>
end

out = struct();
out.seed = int32(12345);
out.start_state = startState;
out.records = records;

out_path = fullfile(pwd, 'tmp', 'verify_mcg16807_stepwise_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(out));
fclose(fid);
fprintf('wrote %s\n', out_path);
for i = 1:n
    r = records(i);
    fprintf('step=%d before=%d draw=%.17g after=%d\n', r.step, r.state_before, r.draw, r.state_after);
end
end
