function m_ticks = division_window_spec(process_name)
% division_window_spec  Single source of truth loader (MATLAB side) for
% division-window (event-anchor) capture sizes, mirroring
% scripts/l2_event/division_window_spec.py exactly against the SAME
% canonical file: docs/phase_f/l2_event/division_window_spec.json.
%
% Do NOT hardcode Cytokinesis/FtsZPolymerization M_ticks anywhere else in
% MATLAB code -- extract_dual_division_window.m and
% extract_dual_division_window_seeds.m both call this function instead of
% a local `cyt_n_ticks = 4000` literal.
%
% Usage:
%   cyt_n_ticks = division_window_spec('Cytokinesis');
%   ftsz_n_ticks = division_window_spec('FtsZPolymerization');
%
% Fails loudly (error(), never a silent default) if the spec file is
% missing, is not valid JSON, or has no entry (or no `m_ticks` field) for
% the requested process -- matching the Python loader's "no fallback
% default, no silent tuning path" discipline exactly.

if nargin < 1 || isempty(process_name)
    error('division_window_spec:missing_process', 'process_name is required');
end

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
spec_path = fullfile(repo_root, 'docs', 'phase_f', 'l2_event', 'division_window_spec.json');

if exist(spec_path, 'file') ~= 2
    error('division_window_spec:missing_file', 'division-window spec not found at %s', spec_path);
end

raw = fileread(spec_path);
try
    doc = jsondecode(raw);
catch err
    error('division_window_spec:invalid_json', 'division-window spec at %s is not valid JSON: %s', ...
        spec_path, err.message);
end

if ~isfield(doc, 'processes') || ~isfield(doc.processes, process_name)
    error('division_window_spec:unknown_process', ...
        'division-window spec at %s has no entry for process ''%s''', spec_path, process_name);
end

entry = doc.processes.(process_name);
if ~isfield(entry, 'm_ticks')
    error('division_window_spec:missing_m_ticks', ...
        'division-window spec entry for ''%s'' at %s has no m_ticks field', process_name, spec_path);
end

m_ticks = double(entry.m_ticks);
end
