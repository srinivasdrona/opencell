function extract_ftsz_pre_division_window_seeds(seed_start, seed_end)
% extract_ftsz_pre_division_window_seeds  Resumable division-anchored
% FtsZPolymerization extraction for the L2.event pre-division evidence path
% (scripts/l2_event/ftsz_pre_division_evidence.py).
%
% Mirrors the catalog-authoritative row for FtsZPolymerization in
% docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml (unedited by this script):
%   M_ticks: 200
%   N_seeds: 50
%   seed_window.tick_range_from_division: [-200, 0]
%
% Each seed is extracted with extract_per_process_traces_v2's
% window_contract='anchor' mode (default anchor_opts.signal_kind =
% 'diameter_decrease', the same real cell-division timing signal
% Cytokinesis's own anchor windows use -- FtsZ ring assembly and septum
% constriction are the same physical division event). tick_offset is 0 for
% 'anchor' mode: the window's start/end are discovered from the simulation's
% own state, never supplied as burn-in arithmetic.
%
% Usage (from repo root):
%   matlab -batch "addpath(genpath('scripts/matlab')); extract_ftsz_pre_division_window_seeds(0, 49)"
%
% Resumable: for each seed s in [seed_start, seed_end], the output path
%   data/m1_sources/karr_native/per_process_traces_v2_event_s{s:03d}/FtsZPolymerization_200ticks.mat
% is skipped if it already exists. A partial run (killed, timed out,
% pre-empted) can be safely re-invoked with the same or a different range --
% completed seeds are never re-extracted, and a caller closing a partial
% deficit (e.g. scripts/l2_event/ftsz_pre_division_evidence.py's reported
% missing_seeds list) can pass exactly that list's [min, max] here.
%
% No MATLAB/Octave process is invoked by importing or reading this file --
% it only runs when explicitly executed via `run(...)` / `-batch`.

if nargin < 1 || isempty(seed_start); seed_start = 0; end
if nargin < 2 || isempty(seed_end); seed_end = 49; end

repo_root = pwd;

%% Setup WholeCell paths (mirrors scripts/matlab/full_cycle_event_scan_v2.m)
wc_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
if ~exist(wc_root, 'dir')
    wc_root = 'E:\opencell\data\m1_sources\WholeCell';
end
old_dir = pwd;
cd(wc_root);
if exist('setPath.m', 'file') == 2
    try; setPath(); catch; end
else
    addpath(genpath(fullfile(wc_root, 'src')));
    addpath(genpath(fullfile(wc_root, 'lib')));
end
cd(old_dir);
addpath(fullfile(repo_root, 'scripts', 'matlab'));

process_name = 'FtsZPolymerization';
n_ticks = 200;  % catalog M_ticks

fprintf('[ftsz-extract] seeds %d..%d, process=%s, n_ticks=%d, window_contract=anchor\n', ...
    seed_start, seed_end, process_name, n_ticks);

for s = seed_start:seed_end
    out_subdir = sprintf('per_process_traces_v2_event_s%03d', s);
    out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', out_subdir);
    out_path = fullfile(out_root, sprintf('%s_%dticks.mat', process_name, n_ticks));

    if exist(out_path, 'file')
        fprintf('[ftsz-extract] seed %d already present, skip: %s\n', s, out_path);
        continue;
    end

    if ~exist(out_root, 'dir'); mkdir(out_root); end

    fprintf('[ftsz-extract] seed %d/%d: extracting division-anchored window...\n', s, seed_end);
    try
        extract_per_process_traces_v2( ...
            {process_name}, out_subdir, n_ticks, uint32(s), 0, 'anchor', struct());
        fprintf('[ftsz-extract] seed %d DONE: %s\n', s, out_path);
    catch ME
        fprintf('[ftsz-extract] seed %d FAILED: %s\n', s, ME.message);
    end
end

fprintf('[ftsz-extract] all requested seeds processed (%d..%d).\n', seed_start, seed_end);
end
