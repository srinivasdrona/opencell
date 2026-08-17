function [sim, mnrnd_provider] = karr_bootstrap()
% karr_bootstrap  Common Karr WCM bootstrap for all extraction scripts.
%
% Returns a fully-initialized Simulation object ready for state extraction
% or process evolution, plus the genuine Statistics Toolbox mnrnd
% provider identity that was bound for this run. Mirrors the pattern that
% worked in regenerate_metabolism_dynamics.m.
%
% Usage:
%   sim = karr_bootstrap();
%   [sim, mnrnd_provider] = karr_bootstrap();
%   met = sim.process('Metabolism');
%
% This function is invoked by each extraction script in scripts/matlab/.
% Centralizing the bootstrap means a single point of failure for license
% checks, path setup, fixture loading, and genuine-mnrnd provider
% enforcement.

% Find repo root (script lives in scripts/matlab/, so go up 2 levels)
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
fprintf('[karr_bootstrap] repo root: %s\n', repo_root);

% Karr WCM source tree — try current worktree first, fall back to main checkout
worktree_wcm_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
fallback = 'E:\opencell\data\m1_sources\WholeCell';
if exist(fullfile(worktree_wcm_root, 'data', 'Simulation_fitted.mat'), 'file')
    wcm_root = worktree_wcm_root;
else
    if exist(fallback, 'dir')
        fprintf('[karr_bootstrap] worktree WCM missing, using main checkout: %s\n', fallback);
        wcm_root = fallback;
    else
        error('Karr WCM source not found at: %s (and fallback %s also missing)', worktree_wcm_root, fallback);
    end
end

% Set up WCM paths
old_dir = pwd;
cleanup_obj = onCleanup(@() cd(old_dir));
cd(wcm_root);
addpath(genpath(fullfile(wcm_root, 'src')));
addpath(fullfile(wcm_root, 'lib', 'glpkmex-2.9'));
add_worktree_source_overlays(repo_root, wcm_root, worktree_wcm_root);
mnrnd_provider = require_genuine_statistics_rng_providers(repo_root);
fprintf('[karr_bootstrap] mnrnd provider: %s (%s, toolbox %s)\n', ...
    fullfile(matlabroot, strrep(mnrnd_provider.provider_path_relative_to_matlabroot, '/', filesep)), ...
    mnrnd_provider.matlab_release, mnrnd_provider.toolbox_version);

% Load the fitted simulation snapshot
fitted_path = fullfile(wcm_root, 'data', 'Simulation_fitted.mat');
if ~exist(fitted_path, 'file')
    error('Karr fitted simulation not found at: %s', fitted_path);
end

fprintf('[karr_bootstrap] loading fitted simulation: %s\n', fitted_path);
S = load(fitted_path);
sim = S.simulation;
fprintf('[karr_bootstrap] simulation loaded; n_processes = %d\n', numel(sim.processes));

% Verify again in the caller's real working directory. MATLAB resolves the
% current folder ahead of the path, so a caller running from scripts/matlab
% could otherwise re-shadow the provider after this function's onCleanup
% restores old_dir.
cd(old_dir);
mnrnd_provider = require_genuine_statistics_rng_providers(repo_root);

end

function provider = require_genuine_statistics_rng_providers(repo_root)
% require_genuine_statistics_rng_providers  Fail closed unless every
% repo-shadowed RNG helper resolves to the real MathWorks implementation.
provider_names = {'binornd'; 'mnrnd'; 'poissrnd'; 'random'; 'randsample'};
shim_dir = fullfile(repo_root, 'scripts', 'matlab');
license_test = license('test', 'Statistics_Toolbox');
license_checkout = license('checkout', 'Statistics_Toolbox');
if license_test ~= 1 || license_checkout ~= 1
    error('karr_bootstrap:statistics_toolbox_unavailable', ...
        ['full-simulation extraction requires the genuine Statistics and Machine Learning Toolbox ' ...
         'RNG providers; license(''test'',''Statistics_Toolbox'')=%d, ' ...
         'license(''checkout'',''Statistics_Toolbox'')=%d. Repo shims under %s are prohibited as Karr evidence.'], ...
        license_test, license_checkout, shim_dir);
end

stats_info = ver('stats');
if isempty(stats_info)
    error('karr_bootstrap:statistics_toolbox_missing', ...
        ['full-simulation extraction requires ver(''stats'') to resolve the Statistics and ' ...
         'Machine Learning Toolbox; none was found. Repo shims under %s are prohibited as Karr evidence.'], ...
        shim_dir);
end
stats_info = stats_info(1);

provider_dir = fullfile(matlabroot, 'toolbox', 'stats', 'stats');
addpath(provider_dir, '-begin');
rehash;

matlab_release = version('-release');
if isempty(matlab_release) || matlab_release(1) ~= 'R'
    matlab_release = ['R' matlab_release];
end

provider_functions = repmat(struct( ...
    'name', '', ...
    'provider_path_relative_to_matlabroot', '', ...
    'sha256_lf_normalized', '' ...
), numel(provider_names), 1);
for i = 1:numel(provider_names)
    name = provider_names{i};
    expected_provider_path = fullfile(provider_dir, [name '.m']);
    if exist(expected_provider_path, 'file') ~= 2
        error('karr_bootstrap:statistics_rng_provider_missing', ...
            'required genuine MathWorks provider is missing: %s', expected_provider_path);
    end
    resolved_provider_path = which(name);
    if isempty(resolved_provider_path)
        error('karr_bootstrap:statistics_rng_provider_unresolved', ...
            'full-simulation extraction could not resolve %s after promoting %s', name, provider_dir);
    end
    if ~same_path(resolved_provider_path, expected_provider_path)
        error('karr_bootstrap:statistics_rng_provider_shadowed', ...
            ['full-simulation extraction resolved %s to %s instead of %s. ' ...
             'Current-folder and repo shims are prohibited as Karr evidence.'], ...
            name, resolved_provider_path, expected_provider_path);
    end
    provider_functions(i).name = name;
    provider_functions(i).provider_path_relative_to_matlabroot = relative_to_matlabroot(resolved_provider_path);
    provider_functions(i).sha256_lf_normalized = sha256_lf_normalized(resolved_provider_path);
end

mnrnd_idx = find(strcmp(provider_names, 'mnrnd'), 1);
provider = struct( ...
    'kind', 'statistics_toolbox', ...
    'matlab_release', matlab_release, ...
    'toolbox_version', stats_info.Version, ...
    'provider_path_relative_to_matlabroot', provider_functions(mnrnd_idx).provider_path_relative_to_matlabroot, ...
    'sha256_lf_normalized', provider_functions(mnrnd_idx).sha256_lf_normalized, ...
    'functions', provider_functions ...
);
provider.identity_json = jsonencode(struct( ...
    'kind', provider.kind, ...
    'matlab_release', provider.matlab_release, ...
    'toolbox_version', provider.toolbox_version, ...
    'functions', provider.functions ...
));
end

function add_worktree_source_overlays(repo_root, wcm_root, worktree_wcm_root)
overlay_src_root = fullfile(worktree_wcm_root, 'src');
if exist(overlay_src_root, 'dir')
    fprintf('[karr_bootstrap] using worktree source overlay: %s\n', overlay_src_root);
    addpath(genpath(overlay_src_root), '-begin');
    rehash;
    return;
end

if same_path(wcm_root, worktree_wcm_root)
    return;
end

generated_overlay_root = fullfile(repo_root, 'tmp', 'wcm_source_overlay');
generated_overlay_src = fullfile(generated_overlay_root, 'src');
generated_dnadamage_path = fullfile(generated_overlay_src, ...
    '+edu', '+stanford', '+covert', '+cell', '+sim', '+process', 'DNADamage.m');
source_dnadamage_path = fullfile(wcm_root, 'src', ...
    '+edu', '+stanford', '+covert', '+cell', '+sim', '+process', 'DNADamage.m');

ensure_dnadamage_signed_zero_overlay(source_dnadamage_path, generated_dnadamage_path);
fprintf('[karr_bootstrap] using generated DNADamage overlay: %s\n', generated_overlay_src);
addpath(genpath(generated_overlay_src), '-begin');
rehash;
end

function ensure_dnadamage_signed_zero_overlay(source_path, overlay_path)
source_text = fileread(source_path);
needle = '                maxReactions = floor(min(this.substrates ./ max(0, -this.reactionSmallMoleculeStoichiometryMatrix(:, j))));';
replacement = sprintf([ ...
    '                denom = abs(max(0, -this.reactionSmallMoleculeStoichiometryMatrix(:, j)));%% signed-zero normalization for exact-zero stoich rows\n' ...
    '                maxReactions = floor(min(this.substrates ./ denom));']);

if isempty(strfind(source_text, needle)) %#ok<STREMP>
    error('karr_bootstrap:dnadamage_overlay_source_mismatch', ...
        'Unable to find the expected DNADamage maxReactions line in %s', source_path);
end
patched_text = strrep(source_text, needle, replacement);
if strcmp(source_text, patched_text)
    error('karr_bootstrap:dnadamage_overlay_noop', ...
        'DNADamage overlay replacement did not change the source text at %s', source_path);
end

overlay_dir = fileparts(overlay_path);
if ~exist(overlay_dir, 'dir')
    mkdir(overlay_dir);
end
fid = fopen(overlay_path, 'w');
if fid < 0
    error('karr_bootstrap:dnadamage_overlay_open_failed', ...
        'Unable to open generated overlay path for writing: %s', overlay_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, patched_text, 'char');
end

function rel = relative_to_matlabroot(path_value)
prefix = [matlabroot filesep];
if ~strncmpi(path_value, prefix, numel(prefix))
    error('karr_bootstrap:mnrnd_outside_matlabroot', ...
        'resolved mnrnd path %s is not under matlabroot %s', path_value, matlabroot);
end
rel = path_value(numel(prefix) + 1:end);
rel = strrep(rel, filesep, '/');
end

function tf = same_path(path_a, path_b)
normalize = @(p) lower(strrep(char(p), '/', filesep));
tf = strcmp(normalize(path_a), normalize(path_b));
end

function hash_hex = sha256_lf_normalized(path_value)
fid = fopen(path_value, 'rb');
if fid < 0
    error('karr_bootstrap:provider_hash_unreadable', ...
        'could not open %s to compute provider identity hash', path_value);
end
raw = fread(fid, Inf, '*uint8')';
fclose(fid);
raw = raw(raw ~= uint8(13));
digest = java.security.MessageDigest.getInstance('SHA-256');
digest_bytes = typecast(digest.digest(raw), 'uint8');
hash_hex = lower(sprintf('%02x', digest_bytes));
end
