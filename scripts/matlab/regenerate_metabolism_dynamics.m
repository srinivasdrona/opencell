% regenerate_metabolism_dynamics.m
%
% Regenerates the MATLAB perturbation oracle at
%   data/m1_sources/karr_flat/metabolism_dynamics.mat
%
% This file is consumed by tests/m1/test_calc_flux_bounds.py to validate
% that opencell.m1.calc_flux_bounds.compute_bounds() matches Karr's MATLAB
% calcFluxBounds() under 3 specific perturbations (P1, P2, P3).
%
% Expected HDF5 paths in the output:
%   #refs#/b/bounds   shape (504, 2)  — P1: zero first non-zero enzyme
%   #refs#/c/bounds   shape (504, 2)  — P2: zero first external substrate
%   #refs#/d/bounds   shape (504, 2)  — P3: zero first internal-lim substrate
%
% Run from the OpenCell repo root:
%   matlab -batch "run('scripts/matlab/regenerate_metabolism_dynamics.m')"
%
% Author: Copilot, on behalf of sdrona — 2026-05-22

% Repo root (assumes script run from repo root or absolute path)
repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
if isempty(repo_root) || ~exist(repo_root, 'dir')
    repo_root = pwd;
end
fprintf('[regenerate_metabolism_dynamics] repo root: %s\n', repo_root);

% Karr WCM source tree
wcm_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
if ~exist(wcm_root, 'dir')
    error('Karr WCM source not found at: %s', wcm_root);
end

% Initialize WholeCell MATLAB path and load fitted simulation snapshot.
fprintf('[regenerate_metabolism_dynamics] loading Simulation_fitted.mat...\n');
orig_dir = pwd;
cd(wcm_root);
warning('off', 'all');
setPath();
s = load('data/Simulation_fitted.mat');
sim = s.simulation;
cd(orig_dir);

% Locate Process_Metabolism from the fitted simulation.
metabolism = [];
for i = 1:numel(sim.processes)
    if strcmp(sim.processes{i}.wholeCellModelID, 'Process_Metabolism')
        metabolism = sim.processes{i};
        break;
    end
end
if isempty(metabolism)
    error('Process_Metabolism not found in Simulation_fitted.mat');
end

% Capture the dynamics snapshot used by Python's load_default_dynamics().
substrates_snapshot = double(metabolism.substrates);
enzymes_snapshot    = double(metabolism.enzymes);
cell_dry_mass       = double(sum(metabolism.mass.cellDry)); %#ok<NASGU>
step_size_sec       = double(metabolism.stepSizeSec); %#ok<NASGU>

% --- Perturbation P1: zero first non-zero enzyme ---
fprintf('[regenerate_metabolism_dynamics] P1: zero first non-zero enzyme\n');
enz_p1 = enzymes_snapshot;
nz = find(enz_p1 > 0, 1, 'first');
enz_p1(nz) = 0;
metabolism.substrates = substrates_snapshot;
metabolism.enzymes    = enz_p1;
b_bounds = double(metabolism.calcFluxBounds( ...
    metabolism.substrates, metabolism.enzymes, ...
    metabolism.fbaReactionBounds, metabolism.fbaEnzymeBounds, ...
    true, true, true, true, true, false));  % rules 1-5 on, protein off

% --- Perturbation P2: zero first external substrate ---
fprintf('[regenerate_metabolism_dynamics] P2: zero first external substrate\n');
sub_p2 = substrates_snapshot;
ext_idx_0based = metabolism.substrateIndexs_externalExchangedMetabolites(1) - 1;
ext_compartment_0based = metabolism.compartmentIndexs_extracellular - 1;
sub_p2(ext_idx_0based + 1, ext_compartment_0based + 1) = 0;
metabolism.substrates = sub_p2;
metabolism.enzymes    = enzymes_snapshot;
c_bounds = double(metabolism.calcFluxBounds( ...
    metabolism.substrates, metabolism.enzymes, ...
    metabolism.fbaReactionBounds, metabolism.fbaEnzymeBounds, ...
    true, true, true, true, true, false));

% --- Perturbation P3: zero first internal-lim substrate ---
fprintf('[regenerate_metabolism_dynamics] P3: zero first internal-lim substrate\n');
sub_p3 = substrates_snapshot;
int_idx_0based = metabolism.substrateIndexs_internalExchangedLimitedMetabolites(1) - 1;
sub_p3(int_idx_0based + 1, 1) = 0;  % cytosol = compartment index 0 (cytosolIndexs - 1)
metabolism.substrates = sub_p3;
metabolism.enzymes    = enzymes_snapshot;
d_bounds = double(metabolism.calcFluxBounds( ...
    metabolism.substrates, metabolism.enzymes, ...
    metabolism.fbaReactionBounds, metabolism.fbaEnzymeBounds, ...
    true, true, true, true, true, false));

% Build a struct mimicking the HDF5 #refs# layout expected by h5py
b = struct('bounds', b_bounds);
c = struct('bounds', c_bounds);
d = struct('bounds', d_bounds);

% Save with HDF5 v7.3 format so h5py can read #refs#/b/bounds layout
output_dir  = fullfile(repo_root, 'data', 'm1_sources', 'karr_flat');
if ~exist(output_dir, 'dir')
    mkdir(output_dir);
end
output_path = fullfile(output_dir, 'metabolism_dynamics.mat');
save(output_path, 'b', 'c', 'd', '-v7.3');
fprintf('[regenerate_metabolism_dynamics] saved: %s\n', output_path);

% Quick verification that h5py-readable paths are present
fprintf('[regenerate_metabolism_dynamics] verifying HDF5 paths...\n');
info = h5info(output_path);
fprintf('  top-level groups: ');
for i = 1:numel(info.Groups)
    fprintf('%s ', info.Groups(i).Name);
end
fprintf('\n');

fprintf('[regenerate_metabolism_dynamics] DONE\n');
