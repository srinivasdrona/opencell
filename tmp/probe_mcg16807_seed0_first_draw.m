rs = RandStream('mcg16807', 'Seed', uint32(0));
fprintf('SEED0_INITIAL_STATE=%.0f\n', double(rs.State));
v = rand(rs);
fprintf('SEED0_AFTER_1_DRAW val=%.17g state=%.0f\n', v, double(rs.State));
disp('DONE');
