function combined = l22_dnas_chromosome_rng_probe(varargin)
% l22_dnas_chromosome_rng_probe
% Capture the live DNAS chromosome randStream state around the release seam
% on the exact per-process trace surface for the underdetermined tick-0 and
% tick-5 source gaps.

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
out_dir = fileparts(opts.out_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end

tick0_path = fullfile(out_dir, 'l22_dnas_chromosome_rng_tick0_full.json');
tick5_path = fullfile(out_dir, 'l22_dnas_chromosome_rng_tick5_full.json');

tick0 = l22_dnas_source_gap_probe( ...
    'seed', opts.seed, ...
    'tick_zero_based', 0, ...
    'trace_path', opts.trace_path, ...
    'out_path', tick0_path);
tick5 = l22_dnas_source_gap_probe( ...
    'seed', opts.seed, ...
    'tick_zero_based', 5, ...
    'trace_path', opts.trace_path, ...
    'out_path', tick5_path);

combined = struct();
combined.seed = int32(opts.seed);
combined.trace_path = tick0.trace_path;
combined.tick0 = narrow_tick_summary(tick0);
combined.tick5 = narrow_tick_summary(tick5);

fid = fopen(opts.out_path, 'w');
if fid < 0
    error('l22_dnas_chromosome_rng_probe:writeFailed', 'Could not open output path: %s', opts.out_path);
end
cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid, '%s', jsonencode(combined));
fprintf('[l22_dnas_chromosome_rng_probe] wrote %s\n', opts.out_path);
end

function summary = narrow_tick_summary(full_summary)
seg = full_summary.pre_activity_rng_segments;
summary = struct( ...
    'tick_zero_based', full_summary.tick_zero_based, ...
    'tick_one_based', full_summary.tick_one_based, ...
    'scheduler_order_position', full_summary.scheduler_order_position, ...
    'released_topoiv_positions', int32(full_summary.precall_release.released_topoiv_positions), ...
    'released_gyrase_positions', int32(full_summary.precall_release.released_gyrase_positions), ...
    'process_state_before_release', extract_randstream_values(seg, 'state_before_release'), ...
    'process_state_after_topoiv_release', extract_randstream_values(seg, 'state_after_topoiv_release'), ...
    'process_state_after_gyrase_release', extract_randstream_values(seg, 'state_after_gyrase_release'), ...
    'chromosome_state_before_release', extract_randstream_values(seg, 'chromosome_state_before_release'), ...
    'chromosome_state_after_topoiv_release', extract_randstream_values(seg, 'chromosome_state_after_topoiv_release'), ...
    'chromosome_state_after_gyrase_release', extract_randstream_values(seg, 'chromosome_state_after_gyrase_release'));
end

function values = extract_randstream_values(container, field_name)
values = [];
if ~isstruct(container) || ~isfield(container, field_name)
    return;
end
field_value = container.(field_name);
if isstruct(field_value) && isfield(field_value, 'values')
    values = double(field_value.values);
end
end

function opts = parse_inputs(varargin)
opts = struct( ...
    'seed', 0, ...
    'trace_path', '', ...
    'out_path', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_chromosome_rng_probe:invalidArgs', 'Arguments must be name/value pairs');
end

for i = 1:2:numel(varargin)
    name = varargin{i};
    value = varargin{i + 1};
    switch lower(char(name))
        case 'seed'
            opts.seed = double(value);
        case 'trace_path'
            opts.trace_path = char(value);
        case 'out_path'
            opts.out_path = char(value);
        otherwise
            error('l22_dnas_chromosome_rng_probe:unknownOption', 'Unknown option: %s', char(name));
    end
end

if isempty(opts.out_path)
    opts.out_path = fullfile(infer_repo_root(), 'tmp', 'l22_dnas_chromosome_rng_probe.json');
end
end

function repo_root = infer_repo_root()
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
end
