function extract_per_process_traces_v2(process_names, output_subdir, n_ticks, seed, tick_offset, window_contract, anchor_opts)
% extract_per_process_traces_v2
% Allocator-correct per-process trace extraction with per-tick tap points.
%
% For each named process, this function inlines the Simulation.evolveState
% scheduler/allocation loop each tick and captures:
%   states_before: target process properties after copyFromState + allocation
%   states_after:  target process properties after evolveState (before copyToState)
%
% tick_offset (optional, default 0): number of full-simulation burn-in ticks to
%   advance BEFORE snapshotting begins. Use this to capture an "event window" for
%   processes that are quiescent at cell birth (t=0) but active later -- e.g.
%   RibosomeAssembly's first assembly event is ~tick 238, so tick_offset=200 with
%   n_ticks=100 snapshots ticks 200..299 and captures the firing window. With the
%   default tick_offset=0 the behaviour is identical to the original extractor.
%
% window_contract (optional, default '' -- fully backward compatible, no new
%   metadata written): '' | 'fixed' | 'anchor'. Selects which of the two
%   docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md (M4) window
%   kinds this extraction produces, and causes metadata/stride,
%   metadata/tick_start, and metadata/tick_end (fixed) or
%   metadata/window_anchor (anchor) to be written alongside the existing
%   metadata/n_ticks, process_name, rng_seed, tick_offset keys:
%     'fixed'  -- the window is the caller-supplied tick_offset burn-in
%                 (unchanged capture loop below); tick_start == tick_offset,
%                 tick_end == tick_offset + n_ticks - 1, stride == 1.
%     'anchor' -- the window ends at a REAL, observed division-complete
%                 state (see capture_anchor_window/default_anchor_opts
%                 below), never a caller-supplied or fabricated tick. Do
%                 not pass tick_offset with 'anchor' (must be empty/0); the
%                 window start is discovered, not requested.
%
% anchor_opts (optional, only used when window_contract == 'anchor'): struct
%   with fields max_search_ticks (default 50000), signal_property (default
%   'geometry'), signal_field (default 'pinched'). The default targets
%   Cytokinesis's own real completion signal -- CellGeometry.pinched, which
%   Cytokinesis.evolveState() itself defines as pinchedDiameter == 0 (see
%   data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/
%   CellGeometry.m and .../+process/Cytokinesis.m) -- so the discovered
%   anchor tick is the simulation's own division-complete tick, not an
%   externally supplied or hardcoded value.
%
% Output file:
%   data/m1_sources/karr_native/<output_subdir>/<Process>_<n_ticks>ticks.mat
% containing states_before, states_after, metadata (-v7.3).

if nargin < 4 || isempty(seed)
    seed = uint32(0);
else
    seed = uint32(seed);
end
if nargin < 5 || isempty(tick_offset)
    tick_offset = 0;
else
    tick_offset = double(tick_offset);
end
if nargin < 2 || isempty(output_subdir)
    if seed == 0
        output_subdir = 'per_process_traces_v2';
    else
        output_subdir = sprintf('per_process_traces_v2_s%03d', seed);
    end
end
if nargin < 3 || isempty(n_ticks)
    n_ticks = 100;
end
if nargin < 6 || isempty(window_contract)
    window_contract = '';
end
if ~any(strcmp(window_contract, {'', 'fixed', 'anchor'}))
    error('extract_per_process_traces_v2:invalid_window_contract', ...
        'window_contract must be '''', ''fixed'', or ''anchor'' (got ''%s'')', window_contract);
end
if strcmp(window_contract, 'anchor') && tick_offset ~= 0
    error('extract_per_process_traces_v2:anchor_tick_offset_conflict', ...
        ['tick_offset must not be supplied with window_contract=''anchor'' -- the window ' ...
         'start is discovered from the real division signal, not a caller-supplied burn-in.']);
end
if nargin < 7 || isempty(anchor_opts)
    anchor_opts = struct();
end
anchor_opts = default_anchor_opts(anchor_opts);

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', output_subdir);
if ~exist(out_root, 'dir')
    mkdir(out_root);
end

ensure_wholecell_runtime_paths(repo_root);

if nargin < 1 || isempty(process_names)
    sim_probe = karr_bootstrap();
    process_names = collect_process_ids(sim_probe);
    clear sim_probe;
end

for i = 1:numel(process_names)
    requested_name = process_names{i};
    fprintf('\n[trace_v2] === %s ===\n', requested_name);

    sim = karr_bootstrap();
    [target_idx, canonical_name] = find_process_index(sim, requested_name);
    if isempty(target_idx)
        fprintf('[trace_v2] WARN process not found: %s\n', requested_name);
        continue;
    end

    out_path = fullfile(out_root, sprintf('%s_%dticks.mat', canonical_name, n_ticks));
    if exist(out_path, 'file')
        fprintf('[trace_v2] already exists, skipping: %s\n', out_path);
        continue;
    end

    proc = sim.processes{target_idx};
    snapshot_props = pick_snapshot_properties(proc);
    fprintf('[trace_v2] %s snapshot properties: %s\n', canonical_name, join_props(snapshot_props));

    seed_simulation(sim, seed);

    ok = true;
    error_message = '';
    effective_tick_start = tick_offset;
    window_anchor_tick = [];

    if strcmp(window_contract, 'anchor')
        % Division-anchored window: no caller burn-in -- the window start is
        % discovered from the real Cytokinesis/CellGeometry completion
        % signal (see capture_anchor_window), never fabricated or supplied.
        [states_before, states_after, effective_tick_start, window_anchor_tick, ok, error_message] = ...
            capture_anchor_window(sim, target_idx, snapshot_props, n_ticks, anchor_opts);
    else
        states_before = struct();
        states_after = struct();
        for p = 1:numel(snapshot_props)
            states_before.(snapshot_props{p}) = cell(n_ticks, 1);
            states_after.(snapshot_props{p}) = cell(n_ticks, 1);
        end

        % Optional event-window burn-in: advance the whole simulation tick_offset
        % ticks without snapshotting, so the subsequent n_ticks capture a window
        % where an otherwise-quiescent-at-birth process is active.
        for bt = 1:tick_offset
            [sim, ~, ~] = evolve_state_with_tap(sim, target_idx, snapshot_props);
        end

        for t = 1:n_ticks
            try
                [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props);
                for p = 1:numel(snapshot_props)
                    prop = snapshot_props{p};
                    states_before.(prop){t, 1} = before_tick.(prop);
                    states_after.(prop){t, 1} = after_tick.(prop);
                end
            catch err
                ok = false;
                error_message = sprintf('tick %d failed:\n%s', t, getReport(err, 'extended', 'hyperlinks', 'off'));
                break;
            end
        end
    end

    if ~ok
        fprintf('[trace_v2] ERROR %s\n', error_message);
        fprintf('[trace_v2] skipped write: %s\n', out_path);
        continue;
    end

    metadata = struct( ...
        'process_name', canonical_name, ...
        'n_ticks', n_ticks, ...
        'rng_seed', seed, ...
        'tick_offset', effective_tick_start, ...
        'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
        'snapshot_properties', {snapshot_props} ...
    );

    % M4 stride/window-boundary metadata contract (docs/phase_f/l2_event/
    % EVENT_WINDOW_EXTRACTOR_CONTRACT.md) -- only written when the caller
    % opted into a window_contract; '' (default) preserves the exact
    % pre-M4 metadata shape for every existing non-event-window caller.
    if strcmp(window_contract, 'fixed')
        metadata.stride = int32(1);
        metadata.tick_start = int32(effective_tick_start);
        metadata.tick_end = int32(effective_tick_start + n_ticks - 1);
    elseif strcmp(window_contract, 'anchor')
        metadata.stride = int32(1);
        metadata.tick_start = int32(effective_tick_start);
        metadata.window_anchor = int32(window_anchor_tick);
    end

    save(out_path, 'states_before', 'states_after', 'metadata', '-v7.3');
    fprintf('[trace_v2] saved: %s\n', out_path);
end

end

function props = pick_snapshot_properties(proc)
props = intersect(properties(proc), { ...
    'substrates', 'enzymes', 'boundEnzymes', 'chromosome', ...
    'freeRNAs', 'aminoacylatedRNAs', ...
    'mRNAs', 'freeTRNAs', 'freeTMRNA', ...
    'aminoacylatedTRNAs', 'aminoacylatedTMRNA', 'boundTMRNA', ...
    'unprocessedRNAs', 'processedRNAs', 'intergenicRNAs', ...
    'unmodifiedRNAs', 'modifiedRNAs', ...
    'unprocessedMonomers', 'processedMonomers', ...
    'signalSequenceMonomers', ...
    'unmodifiedMonomers', 'modifiedMonomers', ...
    'unfoldedMonomers', 'foldedMonomers', ...
    'unfoldedComplexs', 'foldedComplexs', ...
    'inactiveMonomers', 'matureMonomers', ...
    'inactiveComplexs', 'matureComplexs', ...
    'complexs', 'monomers', 'rnas', 'RNAs', ...
});
end

function [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props)
before_tick = empty_snapshot_struct(snapshot_props);
after_tick = empty_snapshot_struct(snapshot_props);

time = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;

time.values = time.values + sim.stepSizeSec;
stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    stim.values, stim.setValues, time.values);

processes = sim.processes;
nProcesses = numel(processes);
rna_decay_idx = sim.processIndex('RNADecay');
requirements = zeros([numel(mets.counts) nProcesses]);
for i = 1:nProcesses
    mod = processes{i};
    mod.copyFromState();
    r = mod.calcResourceRequirements_Current();
    gidx = mod.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = mod.substrateMetaboliteLocalIndexs;
    if ~isempty(gidx) && ~isempty(lidx)
        requirements(gidx, i) = reshape(r(lidx, :), [], 1);
    end
end

requirements = max(0, requirements);
tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));

rand_stream = [];
if isobject(sim) && ismethod(sim, 'getForTest')
    try
        rand_stream = sim.getForTest('randStream');
    catch
    end
end

while true
    if isempty(rand_stream)
        processEvalOrderIndexs = randperm(nProcesses);
    else
        processEvalOrderIndexs = rand_stream.randperm(nProcesses);
    end
    idx1 = find(processEvalOrderIndexs == sim.processIndex_tRNAAminoacylation, 1);
    idx2 = find(processEvalOrderIndexs == sim.processIndex_translation, 1);
    if isempty(idx1) || isempty(idx2) || idx1 < idx2
        break;
    end
end

for i = 1:nProcesses
    proc_idx = processEvalOrderIndexs(i);
    mod = processes{proc_idx};

    gidx = mod.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = mod.substrateMetaboliteLocalIndexs;
    allocation = reshape(allocations(gidx, proc_idx), size(gidx));
    counts = mets.counts(gidx);

    mod.simulationStateSideEffects = [];
    mod.copyFromState();
    mod.substrates(lidx, :) = allocation;
    if proc_idx == rna_decay_idx && isprop(mod, 'RNAs')
        % Guard against negative RNA counts propagating into weighted sampling.
        mod.RNAs = max(0, mod.RNAs);
    end

    if proc_idx == target_idx
        before_tick = snapshot_from_process(mod, snapshot_props);
    end

    mod.evolveState();

    if proc_idx == target_idx
        after_tick = snapshot_from_process(mod, snapshot_props);
    end

    mod.copyToState();
    mets.counts(gidx) = counts + mod.substrates(lidx, :) - allocation;

    if ~isempty(mod.simulationStateSideEffects)
        mod.simulationStateSideEffects.updateSimulationState(sim);
    end
end

mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    mets.counts, mets.setCounts, time.values);
end

function opts = default_anchor_opts(opts)
% default_anchor_opts  Fill in defaults for window_contract='anchor'.
%
% signal_property/signal_field default to Cytokinesis's own real division
% completion signal: CellGeometry.pinched, which Cytokinesis.evolveState()
% defines as pinchedDiameter == 0 (see CellGeometry.m get.pinched and
% Cytokinesis.m's ring-bending/dissociation logic). Callers extracting a
% different EVENT_CLASS process's division-anchored window may override
% signal_property/signal_field to that process's own equivalent real
% completion signal -- never to a value derived from the expected/desired
% outcome.
if ~isfield(opts, 'max_search_ticks') || isempty(opts.max_search_ticks)
    opts.max_search_ticks = 50000;
end
if ~isfield(opts, 'signal_property') || isempty(opts.signal_property)
    opts.signal_property = 'geometry';
end
if ~isfield(opts, 'signal_field') || isempty(opts.signal_field)
    opts.signal_field = 'pinched';
end
end

function [states_before, states_after, tick_start, anchor_tick, ok, error_message] = ...
    capture_anchor_window(sim, target_idx, snapshot_props, n_ticks, anchor_opts)
% capture_anchor_window  Division-anchored event-window capture.
%
% Free-runs the simulation tick-by-tick from t=1 (identical per-tick
% scheduler/allocation/tap semantics as the fixed-window path, via
% evolve_state_with_tap), maintaining a size-n_ticks circular buffer of the
% most recent (before, after) snapshots. After each tick it reads the
% REAL simulation state at
% sim.processes{target_idx}.(anchor_opts.signal_property).(anchor_opts.signal_field)
% -- never a precomputed/expected tick -- and stops the first time that
% signal is true AND a full n_ticks buffer has been collected. The anchor
% tick and the n_ticks window ending at it are both derived from that one
% real observation; there is no fallback that invents an anchor when the
% signal never fires (see the max_search_ticks exhaustion branch below,
% which fails loudly instead).
ok = true;
error_message = '';
anchor_tick = [];
tick_start = [];
states_before = struct();
states_after = struct();

target_proc = sim.processes{target_idx};
if ~isprop(target_proc, anchor_opts.signal_property)
    ok = false;
    error_message = sprintf( ...
        'anchor signal property ''%s'' not found on process (window_contract=''anchor'' requires a real, ' ...
        'readable completion signal on the target process)', anchor_opts.signal_property);
    return;
end

buffer_before = cell(n_ticks, 1);
buffer_after = cell(n_ticks, 1);
buffer_len = 0;
next_slot = 1;

t = 0;
found = false;
while t < anchor_opts.max_search_ticks
    t = t + 1;
    try
        [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props);
    catch err
        ok = false;
        error_message = sprintf('anchor search tick %d failed:\n%s', t, getReport(err, 'extended', 'hyperlinks', 'off'));
        return;
    end

    slot = mod(next_slot - 1, n_ticks) + 1;
    buffer_before{slot} = before_tick;
    buffer_after{slot} = after_tick;
    next_slot = next_slot + 1;
    buffer_len = min(buffer_len + 1, n_ticks);

    is_fired = false;
    try
        is_fired = logical(target_proc.(anchor_opts.signal_property).(anchor_opts.signal_field));
    catch
        is_fired = false;
    end

    if is_fired && buffer_len == n_ticks
        found = true;
        anchor_tick = t;
        tick_start = t - n_ticks + 1;
        break;
    end
end

if ~found
    ok = false;
    error_message = sprintf( ...
        ['division-anchor signal ''%s.%s'' did not fire within max_search_ticks=%d ticks -- refusing to ' ...
         'fabricate a window_anchor; either raise anchor_opts.max_search_ticks or this seed genuinely does ' ...
         'not divide in that many ticks'], anchor_opts.signal_property, anchor_opts.signal_field, ...
        anchor_opts.max_search_ticks);
    return;
end

for p = 1:numel(snapshot_props)
    states_before.(snapshot_props{p}) = cell(n_ticks, 1);
    states_after.(snapshot_props{p}) = cell(n_ticks, 1);
end

% The buffer is circular; `next_slot`'s current position is the slot that
% will be overwritten NEXT, i.e. the oldest entry still held. Replay the
% buffer starting there so states_before/after end up in chronological
% order (row 1 == tick_start .. row n_ticks == anchor_tick).
oldest_slot = mod(next_slot - 1, n_ticks) + 1;
for k = 1:n_ticks
    src_slot = mod(oldest_slot - 1 + (k - 1), n_ticks) + 1;
    for p = 1:numel(snapshot_props)
        prop = snapshot_props{p};
        states_before.(prop){k, 1} = buffer_before{src_slot}.(prop);
        states_after.(prop){k, 1} = buffer_after{src_slot}.(prop);
    end
end
end

function out = snapshot_from_process(proc, snapshot_props)
out = struct();
for p = 1:numel(snapshot_props)
    prop = snapshot_props{p};
    out.(prop) = sanitize_snapshot_value(proc.(prop), 0);
end
end

function out = empty_snapshot_struct(snapshot_props)
out = struct();
for p = 1:numel(snapshot_props)
    out.(snapshot_props{p}) = [];
end
end

function out = sanitize_snapshot_value(v, depth)
if depth > 4
    out = '<MAX_DEPTH>';
    return;
end

if isnumeric(v) || islogical(v) || ischar(v) || isstring(v)
    out = v;
    return;
end

if iscell(v)
    out = cell(size(v));
    for i = 1:numel(v)
        out{i} = sanitize_snapshot_value(v{i}, depth + 1);
    end
    return;
end

if isstruct(v)
    out = struct();
    fns = fieldnames(v);
    for i = 1:numel(fns)
        fn = fns{i};
        try
            out.(fn) = sanitize_snapshot_value(v.(fn), depth + 1);
        catch
            out.(fn) = '<field-unreadable>';
        end
    end
    return;
end

if isobject(v)
    cls = class(v);
    % Special-case the Chromosome state object: write a sparse-triple
    % struct of its primary writable properties so chromosome-primary
    % L2.2 distances (Replication / DNARepair / DNASupercoiling /
    % DNADamage / ReplicationInitiation) have real signal instead of
    % the previous '<object:...>' placeholder string.
    if strcmp(cls, 'edu.stanford.covert.cell.sim.state.Chromosome')
        try
            out = serialize_chromosome_state(v);
            return;
        catch err
            out = struct('error', sprintf('serialize_chromosome_state failed: %s', err.message), 'class', cls);
            return;
        end
    end
    out = sprintf('<object:%s>', cls);
    return;
end

out = sprintf('<unsupported:%s>', class(v));
end

function seed_simulation(sim, seed)
try
    if isobject(sim) && ismethod(sim, 'applyOptions') && ismethod(sim, 'seedRandStream')
        sim.applyOptions('seed', seed);
        sim.seedRandStream();
        return;
    end
catch
end

try
    if isprop(sim, 'randStream') && ~isempty(sim.randStream)
        sim.randStream.seed = seed;
        return;
    end
catch
end
end

function names = collect_process_ids(sim)
names = cell(numel(sim.processes), 1);
for i = 1:numel(sim.processes)
    names{i} = process_short_name(sim.processes{i});
end
end

function [idx, canonical_name] = find_process_index(sim, requested_name)
idx = [];
canonical_name = '';
want = normalize_name_token(requested_name);

for i = 1:numel(sim.processes)
    proc = sim.processes{i};
    short = process_short_name(proc);
    tokens = { ...
        normalize_name_token(short), ...
        normalize_name_token(proc.wholeCellModelID) ...
    };
    if isprop(proc, 'name')
        tokens{end + 1} = normalize_name_token(proc.name); %#ok<AGROW>
    end
    if any(strcmp(tokens, want))
        idx = i;
        canonical_name = short;
        return;
    end
end
end

function short = process_short_name(proc)
wid = proc.wholeCellModelID;
if strncmp(wid, 'Process_', numel('Process_'))
    short = wid(numel('Process_') + 1:end);
else
    short = wid;
end
end

function token = normalize_name_token(s)
token = lower(regexprep(char(s), '[^a-zA-Z0-9]', ''));
end

function ensure_wholecell_runtime_paths(repo_root)
candidate_roots = { ...
    fullfile(repo_root, 'data', 'm1_sources', 'WholeCell'), ...
    'E:\opencell\data\m1_sources\WholeCell' ...
};

for i = 1:numel(candidate_roots)
    root = candidate_roots{i};
    if ~exist(root, 'dir')
        continue;
    end

    old_dir = pwd;
    cleaner = onCleanup(@() cd(old_dir)); %#ok<NASGU>
    cd(root);

    if exist('setWarnings.m', 'file') == 2
        try
            setWarnings();
        catch
        end
    end

    if exist('setPath.m', 'file') == 2
        try
            setPath();
            return;
        catch
        end
    end

    addpath(genpath(fullfile(root, 'src')));
    addpath(genpath(fullfile(root, 'lib')));
    return;
end
end

function s = join_props(props)
if isempty(props)
    s = '(none)';
    return;
end
s = props{1};
for i = 2:numel(props)
    s = [s ', ' props{i}]; %#ok<AGROW>
end
end
