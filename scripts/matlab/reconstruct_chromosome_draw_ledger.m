function report = reconstruct_chromosome_draw_ledger(trace_mat_path, output_json_path, max_draws_per_tick)
% reconstruct_chromosome_draw_ledger
%
% Offline, non-destructive reconstruction of the exact ordered sequence
% of raw scalar `rand()` draws Karr's SHARED `Chromosome.randStream`
% produced during one target-process tick's own `evolveState()` call,
% using ONLY the `chromosome_rand_stream_state` before/after pair already
% captured in `states_before`/`states_after` by
% `extract_per_process_traces_v2.m::merge_chromosome_rand_stream_state`.
% Process-agnostic: used by DNADamage's own L2.1 lane and by
% ReplicationInitiation's (see DEC-005/DEC-006), and handles a QUIESCENT
% tick (`state_before(t) == state_after(t)`, i.e. zero chromosome draws
% that tick -- common for processes whose own coarse candidate-set
% gating means many ticks have no chromosome-site contention at all)
% WITHOUT attempting to draw a full LCG period to "walk back" to an
% identical state by chance.
%
% Method: for each tick t, construct a SCRATCH `RandStream('mcg16807')`
% (never the live simulation's real stream -- this never touches
% anything but a throwaway clone), set its `.State` to
% `state_before(t)` (proven exact/restorable: see
% `scripts/matlab/probe_l21_chromosome_randstream_state.m`,
% `all_reconstruction_ok=true`), then repeatedly draw `rand(clone)`,
% recording each raw value, until `clone.State` exactly equals
% `state_after(t)`. This works regardless of `.State`'s own internal
% encoding (never reverse-engineered -- see that probe script's
% docstring) because every higher-level primitive Karr's Chromosome/
% RandStream wrapper classes use (`stochasticRound`, `ceil(len*rand())`
% position/strand draws, `randsample`'s `randperm`/builtin-`randi`
% rejection loop -- see `scripts/matlab/probe_l21_randsample_exact.m`)
% bottoms out in plain scalar `rand()` calls with no other
% state-advancing mechanism; a state delta between two `.State` reads is
% therefore fully and exactly characterized by the ordered list of raw
% `rand()` outputs a clone produces while walking from one to the other.
%
% Fail-closed: if a tick's walk exceeds `max_draws_per_tick` (default
% 200000 -- DNADamage's own reaction/site-sampling call volume per tick
% is small; this ceiling exists only to catch a genuinely malformed or
% mismatched state pair, e.g. from a different source-code revision,
% rather than infinite-looping) without reaching `state_after(t)`
% exactly, this function raises an error naming the tick -- it never
% silently truncates or emits a partial/guessed ledger for that tick.

if nargin < 3 || isempty(max_draws_per_tick)
    max_draws_per_tick = 200000;
end

fields_needed = {'chromosome_rand_stream_state'};
trace_data = load(trace_mat_path, 'states_before', 'states_after');
if ~isfield(trace_data.states_before, 'chromosome_rand_stream_state') || ...
        ~isfield(trace_data.states_after, 'chromosome_rand_stream_state')
    error('reconstruct_chromosome_draw_ledger:missing_field', ...
        ['trace file %s is missing states_before/after.chromosome_rand_stream_state -- ' ...
         're-extract with the ledger-capture-enabled extractor first'], trace_mat_path);
end

state_before_cell = trace_data.states_before.chromosome_rand_stream_state;
state_after_cell = trace_data.states_after.chromosome_rand_stream_state;
n_ticks = numel(state_before_cell);
if numel(state_after_cell) ~= n_ticks
    error('reconstruct_chromosome_draw_ledger:length_mismatch', ...
        'states_before/after chromosome_rand_stream_state length mismatch: %d vs %d', ...
        n_ticks, numel(state_after_cell));
end
state_before = zeros(n_ticks, 1);
state_after = zeros(n_ticks, 1);
for t = 1:n_ticks
    state_before(t) = double(state_before_cell{t});
    state_after(t) = double(state_after_cell{t});
end

n_quiescent = 0;
per_tick = struct([]);
for t = 1:n_ticks
    if isequal(state_before(t), state_after(t))
        % Quiescent tick: the target process made zero chromosome-owned
        % draws this tick (its own coarse candidate-set gating never
        % reached the shared randStream at all). Recording zero draws
        % here is the exact, literal fact of what happened -- NOT an
        % assumption or a fallback; a genuinely-nonzero-but-cyclically-
        % returning-to-the-same-state walk over an LCG with modulus
        % 2^31-1 would require ~2^31 draws, far beyond
        % max_draws_per_tick, so this is unambiguous.
        n_quiescent = n_quiescent + 1;
        per_tick(t).tick = t; %#ok<AGROW>
        per_tick(t).state_before = state_before(t); %#ok<AGROW>
        per_tick(t).state_after = state_after(t); %#ok<AGROW>
        per_tick(t).n_draws = 0; %#ok<AGROW>
        per_tick(t).draws = zeros(1, 0); %#ok<AGROW>
        continue;
    end

    clone = RandStream('mcg16807');
    clone.State = state_before(t);
    draws = zeros(1, 0);
    reached = false;
    for i = 1:max_draws_per_tick
        v = rand(clone);
        draws(end + 1) = v; %#ok<AGROW>
        if isequal(double(clone.State), state_after(t))
            reached = true;
            break;
        end
    end
    if ~reached
        error('reconstruct_chromosome_draw_ledger:tick_not_reconciled', ...
            ['tick %d: could not walk from state_before=%.17g to state_after=%.17g within ' ...
             '%d draws -- refusing to emit a partial/guessed ledger for this tick'], ...
            t, state_before(t), state_after(t), max_draws_per_tick);
    end
    per_tick(t).tick = t; %#ok<AGROW>
    per_tick(t).state_before = state_before(t); %#ok<AGROW>
    per_tick(t).state_after = state_after(t); %#ok<AGROW>
    per_tick(t).n_draws = numel(draws); %#ok<AGROW>
    per_tick(t).draws = draws; %#ok<AGROW>
end

report = struct();
report.trace_mat_path = trace_mat_path;
report.trace_sha256 = sha256_of_file(trace_mat_path);
report.dnadamage_source_sha256 = h5_read_string_attr_or_dataset(trace_mat_path, '/metadata/dnadamage_source_resolved_sha256');
report.chromosome_source_sha256 = '';
report.randstream_util_source_sha256 = '';
try
    this_file = mfilename('fullpath');
    matlab_dir = fileparts(this_file);
    scripts_dir = fileparts(matlab_dir);
    repo_root = fileparts(scripts_dir);
    worktree_wcm_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
    fallback_wcm_root = 'E:\opencell\data\m1_sources\WholeCell';
    if exist(fullfile(worktree_wcm_root, 'data', 'Simulation_fitted.mat'), 'file')
        wcm_root = worktree_wcm_root;
    else
        wcm_root = fallback_wcm_root;
    end
    chromosome_path = fullfile(wcm_root, 'src', '+edu', '+stanford', '+covert', ...
        '+cell', '+sim', '+state', 'Chromosome.m');
    randstream_util_path = fullfile(wcm_root, 'src', '+edu', '+stanford', '+covert', ...
        '+util', 'RandStream.m');
    report.chromosome_source_sha256 = sha256_of_file(chromosome_path);
    report.randstream_util_source_sha256 = sha256_of_file(randstream_util_path);
catch err
    fprintf('[reconstruct_chromosome_draw_ledger] WARNING: could not hash Chromosome.m/RandStream.m: %s\n', err.message);
end
report.matlab_release = version('-release');
report.generated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');
report.n_ticks = n_ticks;
report.n_quiescent_ticks = n_quiescent;
report.max_draws_per_tick = max_draws_per_tick;
report.per_tick = per_tick;

output_json_path = char(output_json_path);
[out_dir, ~, ~] = fileparts(output_json_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(output_json_path, 'w');
if fid == -1
    error('reconstruct_chromosome_draw_ledger:open_failed', 'Unable to open output path: %s', output_json_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(report), 'char');
fprintf('[reconstruct_chromosome_draw_ledger] wrote %s (%d ticks, %d quiescent, total draws=%d)\n', ...
    output_json_path, n_ticks, n_quiescent, sum([per_tick.n_draws]));
end

function hash_hex = sha256_of_file(path_value)
fid = fopen(path_value, 'rb');
if fid < 0
    error('reconstruct_chromosome_draw_ledger:file_unreadable', 'could not open %s', path_value);
end
raw = fread(fid, Inf, '*uint8')';
fclose(fid);
digest = java.security.MessageDigest.getInstance('SHA-256');
digest_bytes = typecast(digest.digest(raw), 'uint8');
hash_hex = lower(sprintf('%02x', digest_bytes));
end

function out = h5_read_string_attr_or_dataset(path_value, dataset_path)
try
    raw = h5read(path_value, dataset_path);
    out = char(raw(:)');
catch
    out = '';
end
end
