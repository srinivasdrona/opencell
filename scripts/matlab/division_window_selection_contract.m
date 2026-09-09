function contract = division_window_selection_contract()
% division_window_selection_contract  Single source of truth loader
% (MATLAB side) for the Cytokinesis+FtsZPolymerization dual-tap cohort's
% seed-selection/censoring-horizon contract, mirroring
% scripts/l2_event/division_window_spec.selection_contract() exactly
% against the SAME canonical file:
% docs/phase_f/l2_event/division_window_spec.json's top-level
% 'selection_contract' block (schema_version 3, preregistered 2026-09-08).
%
% This is a SELECTION contract (which seeds count toward the cohort, and
% in what order/at what common censoring horizon) layered on top of, never
% a replacement for, division_window_spec.m's own per-process m_ticks
% accessor.
%
% Usage:
%   contract = division_window_selection_contract();
%   contract.candidate_seed_start        % 0
%   contract.required_completed_windows  % 50
%   contract.max_search_ticks            % 100000 (the common censoring horizon)
%   contract.selection_order             % 'ascending_seed'
%   contract.attempt_record_filename     % 'division_window_attempt.json'
%
% Fails loudly (error(), never a silent default) if the spec file is
% missing, is not valid JSON, has no 'selection_contract' block, or that
% block is missing any of the keys this function returns -- matching
% division_window_spec.m's "no fallback default, no silent tuning path"
% discipline exactly.

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
spec_path = fullfile(repo_root, 'docs', 'phase_f', 'l2_event', 'division_window_spec.json');

if exist(spec_path, 'file') ~= 2
    error('division_window_selection_contract:missing_file', ...
        'division-window spec not found at %s', spec_path);
end

raw = fileread(spec_path);
try
    doc = jsondecode(raw);
catch err
    error('division_window_selection_contract:invalid_json', ...
        'division-window spec at %s is not valid JSON: %s', spec_path, err.message);
end

if ~isfield(doc, 'selection_contract')
    error('division_window_selection_contract:missing_block', ...
        'division-window spec at %s has no top-level ''selection_contract'' key', spec_path);
end

contract = doc.selection_contract;
required_fields = {'applies_to', 'candidate_seed_start', 'required_completed_windows', ...
    'max_search_ticks', 'selection_order', 'attempt_record_filename', 'attempt_status_values', ...
    'formal_estimand', 'stopping_rule', 'censor_record_required_identity_fields', ...
    'authoritative_operational_root'};
for i = 1:numel(required_fields)
    field_name = required_fields{i};
    if ~isfield(contract, field_name)
        error('division_window_selection_contract:missing_field', ...
            'division-window spec at %s''s selection_contract is missing required field ''%s''', ...
            spec_path, field_name);
    end
end

contract.candidate_seed_start = double(contract.candidate_seed_start);
contract.required_completed_windows = double(contract.required_completed_windows);
contract.max_search_ticks = double(contract.max_search_ticks);
end
