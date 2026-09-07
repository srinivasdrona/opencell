function report = probe_l21_randsample_exact(output_json_path)
% probe_l21_randsample_exact
%
% Validates a from-scratch Python-portable reimplementation of MATLAB's
% real Statistics and Machine Learning Toolbox `randsample(stream, n, k,
% false)` (no weights) against the actual toolbox function, across both
% of its algorithm branches (see randsample.m, `toolbox/stats/stats/`):
%   - branch A: 4*k > n  -> rp = randperm(s,n); y = rp(1:k)
%   - branch B: 4*k <= n -> rejection-sampling loop using
%                            randi(s,n,1,k-sumx), then y = y(randperm(s,k))
%
% Also validates that MATLAB's builtin randi(s, imax, ...) for an
% mcg16807-backed stream is exactly floor(imax*rand(s))+1, one rand()
% draw per requested integer, no rejection/bias-correction (already
% spot-checked in probe_l21_chromosome_randstream_state.m; broadened
% here across more (n,k) shapes actually used by DNADamage/Chromosome).
%
% No web. This is a live-MATLAB, real-toolbox cross-check -- not a
% probe against our own prior assumptions.

if nargin < 1 || isempty(output_json_path)
    output_json_path = fullfile('artifacts', 'l21_dnadamage_chromosome_rng', 'randsample_exact_probe.json');
end

% (seed, n, k) cases spanning both branches, including a case designed to
% force at least one rejection-loop collision (k close to n/4 boundary,
% small n) and a case with k==n (fully select all).
cases = { ...
    struct('seed', 2000,  'n', 20,     'k', 3);   ...  % branch B (4*3=12<=20)
    struct('seed', 2000,  'n', 20,     'k', 6);   ...  % branch A (4*6=24>20)
    struct('seed', 2000,  'n', 10000,  'k', 5);   ...  % branch B, sparse
    struct('seed', 2000,  'n', 10000,  'k', 2600); ... % branch A boundary (4*2600=10400>10000)
    struct('seed', 12345, 'n', 500,    'k', 1);   ...  % branch B, k=1
    struct('seed', 12345, 'n', 7,      'k', 7);   ...  % k==n edge (branch A, 4*7=28>7)
    struct('seed', 42,    'n', 3,      'k', 1);   ...  % tiny n
    struct('seed', 777,   'n', 50000,  'k', 12);  ...  % branch B, realistic genome-scale n
};

rows = struct([]);
row_idx = 0;
for ci = 1:numel(cases)
    c = cases{ci};
    rs = RandStream('mcg16807');
    reset(rs, c.seed);
    state_before = double(rs.State);
    y_real = randsample(rs, c.n, c.k, false);
    state_after = double(rs.State);

    row_idx = row_idx + 1;
    rows(row_idx).seed = double(c.seed); %#ok<AGROW>
    rows(row_idx).n = double(c.n); %#ok<AGROW>
    rows(row_idx).k = double(c.k); %#ok<AGROW>
    rows(row_idx).branch = branch_label(c.n, c.k); %#ok<AGROW>
    rows(row_idx).state_before = state_before; %#ok<AGROW>
    rows(row_idx).state_after = state_after; %#ok<AGROW>
    rows(row_idx).y_real = double(sort(y_real(:)')); %#ok<AGROW>
    rows(row_idx).y_real_order = double(y_real(:)'); %#ok<AGROW>
end

report = struct();
report.matlab_release = version('-release');
report.generated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');
report.rows = rows;

output_json_path = char(output_json_path);
[out_dir, ~, ~] = fileparts(output_json_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(output_json_path, 'w');
if fid == -1
    error('probe_l21_randsample_exact:open_failed', 'Unable to open output path: %s', output_json_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(report), 'char');
fprintf('[probe_l21_randsample_exact] wrote %s (%d cases)\n', output_json_path, numel(rows));
end

function label = branch_label(n, k)
if 4 * k > n
    label = 'A_randperm_prefix';
else
    label = 'B_rejection_loop';
end
end
