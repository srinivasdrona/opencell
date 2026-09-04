% probe_mcg16807_seed_edge_cases.m -- live MATLAB check of RandStream
% ('mcg16807') behavior for seed<=0, to validate the ChromCond-derived
% _initialize_mcg edge-case handling (_MCG_DEFAULT_STATE=931316785 for
% seed<=0) against a fresh live probe before reusing it for Cytokinesis.
seeds = [0, int64(-5), 1, uint32(2147483647), uint32(2147483646)];
for i = 1:numel(seeds)
    s = seeds(i);
    try
        rs = RandStream('mcg16807', 'Seed', s);
        fprintf('seed=%s -> state=%.0f\n', num2str(s), double(rs.State));
    catch err
        fprintf('seed=%s -> ERROR: %s\n', num2str(s), err.message);
    end
end
disp('DONE');
