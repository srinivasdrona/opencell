function sim = karr_bootstrap()
% karr_bootstrap  Common Karr WCM bootstrap for all extraction scripts.
%
% Returns a fully-initialized Simulation object ready for state extraction
% or process evolution. Mirrors the pattern that worked in
% regenerate_metabolism_dynamics.m.
%
% Usage:
%   sim = karr_bootstrap();
%   met = sim.process('Metabolism');
%
% This function is invoked by each extraction script in scripts/matlab/.
% Centralizing the bootstrap means a single point of failure for license
% checks, path setup, and fixture loading.

% Find repo root (script lives in scripts/matlab/, so go up 2 levels)
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
fprintf('[karr_bootstrap] repo root: %s\n', repo_root);

% Karr WCM source tree — try current worktree first, fall back to main checkout
wcm_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
if ~exist(wcm_root, 'dir')
    fallback = 'E:\opencell\data\m1_sources\WholeCell';
    if exist(fallback, 'dir')
        fprintf('[karr_bootstrap] worktree WCM missing, using main checkout: %s\n', fallback);
        wcm_root = fallback;
    else
        error('Karr WCM source not found at: %s (and fallback %s also missing)', wcm_root, fallback);
    end
end

% Set up WCM paths
old_dir = pwd;
cleanup_obj = onCleanup(@() cd(old_dir));
cd(wcm_root);
addpath(genpath(fullfile(wcm_root, 'src')));

% Load the fitted simulation snapshot
fitted_path = fullfile(wcm_root, 'data', 'Simulation_fitted.mat');
if ~exist(fitted_path, 'file')
    error('Karr fitted simulation not found at: %s', fitted_path);
end

fprintf('[karr_bootstrap] loading fitted simulation: %s\n', fitted_path);
S = load(fitted_path);
sim = S.simulation;
fprintf('[karr_bootstrap] simulation loaded; n_processes = %d\n', numel(sim.processes));

end
