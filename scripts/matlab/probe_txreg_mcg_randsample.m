function probe_txreg_mcg_randsample()
% probe_txreg_mcg_randsample  Live-MATLAB verification of
% edu.stanford.covert.util.RandStream.randsample(this, n, k, false, w)
% (the weighted-without-replacement rejection-sampling branch) against a
% Python port, for the exact TranscriptionalRegulation tick-11 scenario:
% seed 0, n=8 candidates, k=8 (batched draw truncated to 1 needed by the
% caller), weights = tfAffinities for [site0, site2, site5, site6, site9,
% site10, site12, site13].
%
% Minimal, fast probe: does NOT construct a full Simulation() (expensive,
% requires fitted KB data); only needs the WholeCell class path so
% edu.stanford.covert.util.RandStream resolves.

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

worktree_wcm_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
fallback = 'E:\opencell\data\m1_sources\WholeCell';
if exist(fullfile(worktree_wcm_root, 'src'), 'dir')
    wcm_root = worktree_wcm_root;
elseif exist(fallback, 'dir')
    wcm_root = fallback;
else
    error('Karr WCM source not found at: %s (and fallback %s also missing)', worktree_wcm_root, fallback);
end

addpath(genpath(fullfile(wcm_root, 'src')));

results = struct();

% --- Case A: seed 0, exact tick-11 candidate weights, n=k=8 -----------------
rs = edu.stanford.covert.util.RandStream('mcg16807');
rs.reset(0);
weights_a = [0.20000000298023224, 0.7801949977874756, 0.5365309715270996, ...
    0.7532579898834229, 0.5, 0.8835390210151672, 1.1398500204086304, 1.247849941253662];
out_a = rs.randsample(8, 8, false, weights_a);
results.case_a_seed0_n8_k8 = out_a;
fprintf('[probe] case A (seed=0, n=8, k=8): %s\n', mat2str(out_a));

% --- Case B: same weights, k=1 (what a naive direct-k=1 caller would see) ---
rs2 = edu.stanford.covert.util.RandStream('mcg16807');
rs2.reset(0);
out_b = rs2.randsample(8, 1, false, weights_a);
results.case_b_seed0_n8_k1 = out_b;
fprintf('[probe] case B (seed=0, n=8, k=1): %s\n', mat2str(out_b));

% --- Case C: base rand(8) at seed 0, for cross-check against the Python shim's raw scalar stream ---
rs3 = edu.stanford.covert.util.RandStream('mcg16807');
rs3.reset(0);
out_c = rs3.rand(8, 1);
results.case_c_seed0_rand8 = out_c;
fprintf('[probe] case C (seed=0, raw rand(8,1)): %s\n', mat2str(out_c));

out_path = fullfile(repo_root, 'tmp', 'probe_txreg_mcg_randsample_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('[probe] wrote %s\n', out_path);

end
