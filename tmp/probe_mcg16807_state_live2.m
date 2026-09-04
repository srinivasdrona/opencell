% probe_mcg16807_state_live.m -- live MATLAB verification of RandStream
% ('mcg16807').State class/shape/value and rand() output sequence, to
% independently confirm the ChromCond-derived encode/decode transform
% (half-word swap + sign-based XOR) against a FRESH live probe rather than
% relying solely on the reused ChromCond derivation.
rs = RandStream('mcg16807', 'Seed', uint32(36));

fprintf('STATE_CLASS=%s\n', class(rs.State));
sz = size(rs.State);
fprintf('STATE_SIZE=%d %d\n', sz(1), sz(2));
fprintf('STATE_AFTER_SEED=%.0f\n', double(rs.State));

n = 60;
for i = 1:n
    v = rand(rs);
    fprintf('DRAW i=%d val=%.17g state_after=%.0f\n', i, v, double(rs.State));
end

rs2 = RandStream('mcg16807', 'Seed', uint32(1363919953));
fprintf('SEED2_INITIAL_STATE=%.0f\n', double(rs2.State));
v2 = rand(rs2);
fprintf('SEED2_AFTER_1_DRAW val=%.17g state=%.0f\n', v2, double(rs2.State));

disp('DONE');
