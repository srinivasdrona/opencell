function check_minstd_reference_vector()
% Standard test vector for the Park-Miller "minimal standard" generator:
% seed=1, after 10000 iterations of x = (16807*x) mod (2^31-1), x should
% equal 1043618065. Verify MATLAB's rand(s,1,1) advances state by exactly
% this recurrence, one step per call.
s = RandStream('mcg16807', 'Seed', 1);
fprintf('state after construction (seed=1): %d\n', s.State);
for i = 1:10000
    rand(s, 1, 1);
end
fprintf('state after 10000 rand() calls: %d (expected 1043618065 if 1 step/call)\n', s.State);

% Also try setting state directly to 1 (bypass seed handling entirely)
s2 = RandStream('mcg16807', 'Seed', 1);
s2.State = 1;
fprintf('state after manually setting State=1: %d\n', s2.State);
for i = 1:10000
    rand(s2, 1, 1);
end
fprintf('state after 10000 rand() calls (manual State=1): %d\n', s2.State);
end
