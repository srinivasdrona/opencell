function extract_per_process_traces_v2(process_names, output_subdir, n_ticks, seed, tick_offset, window_contract, anchor_opts, extraction_opts)
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
%                 (unchanged capture loop below); ticks 1..tick_offset are
%                 consumed as burn-in BEFORE capture begins, so the first
%                 captured (absolute, 1-based) tick is tick_offset + 1:
%                 tick_start == tick_offset + 1, tick_end == tick_offset +
%                 n_ticks, stride == 1. metadata.tick_offset always records
%                 the burn-in tick COUNT (never a discovered/derived tick),
%                 and is never timing arithmetic on its own.
%     'anchor' -- the window ends at a REAL, observed division-complete
%                 state (see capture_anchor_window/default_anchor_opts
%                 below), never a caller-supplied or fabricated tick. Do
%                 not pass tick_offset with 'anchor' (must be empty/0); the
%                 window start is discovered, not requested.
%
% anchor_opts (optional, only used when window_contract == 'anchor'): struct
%   with fields max_search_ticks (default 50000), signal_kind (default
%   'diameter_decrease'), signal_property (default 'geometry'), signal_field
%   (used only for signal_kind='boolean_transition', default 'pinched').
%   Two signal_kind detectors, both evaluated from the SAME per-tick
%   before/after tap values evolve_state_with_tap already captures (never a
%   post-hoc re-read of a mutable handle object after the tick has passed):
%     'diameter_decrease' (default; Cytokinesis) -- onset is the first tick
%       where before.pinchedDiameter > after.pinchedDiameter >= 0 (a real
%       strict contraction observed during that tick's own evolveState
%       call); completion is the first tick where before.pinchedDiameter > 0
%       and after.pinchedDiameter == 0. Both read CellGeometry.pinchedDiameter
%       (see data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/
%       +sim/+state/CellGeometry.m and .../+process/Cytokinesis.m), never the
%       vestigial boolean `pinched`/`ftsz_ring_complete` flags.
%     'boolean_transition' (generic EVENT_CLASS processes) -- completion is
%       the first tick where before.(signal_field) is false and
%       after.(signal_field) is true: a genuine false->true transition with
%       a captured prior value, never assumed true at tick 1. No onset_tick
%       is produced for this kind (single-event anchors have no interval).
%   The discovered anchor tick(s) are always the simulation's own observed
%   values, never externally supplied or fabricated.
%
% extraction_opts (optional, default struct()): fixed-window or anchor-window
%   extraction identity/override surface. Supported fields:
%     condition_label                -- char/string label persisted into
%                                       metadata.condition_label (human-
%                                       readable identity only).
%     metadata_identity_json         -- char/string exact identity payload
%                                       persisted into
%                                       metadata.extraction_identity_json so
%                                       validation can refuse a wrong-
%                                       condition trace by metadata mismatch
%                                       instead of by path/name heuristics.
%     per_process_substrate_overrides -- struct keyed by process name, then
%                                       substrate WID, each leaf a numeric
%                                       scalar override applied on the REAL
%                                       process-local substrate vector before
%                                       calcResourceRequirements_Current() and
%                                       again after allocation injection but
%                                       before evolveState().
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
if nargin < 8 || isempty(extraction_opts)
    extraction_opts = struct();
end
anchor_opts = default_anchor_opts(anchor_opts);
extraction_opts = default_extraction_opts(extraction_opts);

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

% Per-process failures are accumulated (not thrown immediately) so multi-
% process diagnostics are preserved (every requested process still gets a
% fprintf'd WARN/ERROR line), but ANY requested-process failure must make
% the WHOLE batch fail: see the error(...) call after this loop below,
% which build_matlab_command's outer try/catch turns into a nonzero exit.
% A caller must never see exit 0 alongside a skipped/failed process.
failed_processes = {};

for i = 1:numel(process_names)
    requested_name = process_names{i};
    fprintf('\n[trace_v2] === %s ===\n', requested_name);

    sim = karr_bootstrap();
    [target_idx, canonical_name] = find_process_index(sim, requested_name);
    if isempty(target_idx)
        fprintf('[trace_v2] WARN process not found: %s\n', requested_name);
        failed_processes{end + 1} = sprintf('%s: process not found', requested_name); %#ok<AGROW>
        continue;
    end

    out_path = fullfile(out_root, sprintf('%s_%dticks.mat', canonical_name, n_ticks));
    if exist(out_path, 'file')
        fprintf('[trace_v2] already exists, skipping: %s\n', out_path);
        continue;
    end

    proc = sim.processes{target_idx};
    snapshot_props = pick_snapshot_properties(proc);
    snapshot_props = exclude_chromosome_object_for_diameter_anchor(snapshot_props, window_contract, anchor_opts);
    fprintf('[trace_v2] %s snapshot properties: %s\n', canonical_name, join_props(snapshot_props));

    seed_simulation(sim, seed);

    ok = true;
    error_message = '';
    % burn_in_tick_offset is the caller-supplied burn-in tick COUNT (0 for
    % window_contract='anchor', enforced above) and is what metadata.tick_offset
    % must always record -- never the discovered/derived window start.
    % effective_tick_start starts equal to it for 'fixed'/'' (no burn-in
    % discovery happens there) and is overwritten below, for 'anchor' only,
    % with the observed absolute tick_start capture_anchor_window returns.
    burn_in_tick_offset = tick_offset;
    effective_tick_start = tick_offset;
    window_anchor_tick = [];
    onset_tick = [];

    if strcmp(window_contract, 'anchor')
        % Division-anchored window: no caller burn-in -- the window start is
        % discovered from the real Cytokinesis/CellGeometry completion
        % signal (see capture_anchor_window), never fabricated or supplied.
        [states_before, states_after, effective_tick_start, window_anchor_tick, onset_tick, ok, error_message] = ...
            capture_anchor_window(sim, target_idx, snapshot_props, n_ticks, anchor_opts, extraction_opts);
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
            [sim, ~, ~] = evolve_state_with_tap(sim, target_idx, snapshot_props, [], extraction_opts);
        end

        for t = 1:n_ticks
            try
                [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, [], extraction_opts);
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
        failed_processes{end + 1} = sprintf('%s: %s', canonical_name, error_message); %#ok<AGROW>
        continue;
    end

    metadata = struct( ...
        'process_name', canonical_name, ...
        'n_ticks', n_ticks, ...
        'rng_seed', seed, ...
        'tick_offset', burn_in_tick_offset, ...
        'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
        'snapshot_properties', {snapshot_props} ...
    );

    if strcmp(window_contract, 'fixed') || strcmp(window_contract, 'anchor')
        % mnrnd shim identity-binding metadata (legacy-mnrnd defect fix,
        % post-Turn-3): scripts/l2_event/launcher.py's build_matlab_command
        % always prepends addpath('scripts/matlab') for EVERY event-window
        % extraction job (fixed or anchor, any process -- the scheduler
        % runs every process's evolveState() every tick), so
        % scripts/matlab/mnrnd.m unconditionally shadows the real
        % Statistics-Toolbox mnrnd for the whole run, not just for
        % Cytokinesis/ProteinProcessingII. A trace produced under a
        % stale/pre-fix (duplicate-edge-unsafe) revision of that file must
        % never silently skip_valid against today's fixed shim:
        % mnrnd_shim_version is a coarse, human-bumped gate;
        % mnrnd_shim_sha256 is the strong content binding that also catches
        % an edit nobody remembered to version-bump. See
        % validate_existing_event_window (scripts/l2_event/launcher.py) and
        % docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md ("Legacy
        % mnrnd compatibility"). Written for 'fixed' and 'anchor' only --
        % the '' (no window_contract) legacy path below is intentionally
        % left untouched to preserve its exact pre-M4 metadata shape.
        metadata.mnrnd_shim_version = int32(1);
        metadata.mnrnd_shim_sha256 = mnrnd_shim_sha256_hex(matlab_dir);
    end

    if ~isempty(extraction_opts.condition_label)
        metadata.condition_label = extraction_opts.condition_label;
    end
    if ~isempty(extraction_opts.metadata_identity_json)
        metadata.extraction_identity_json = extraction_opts.metadata_identity_json;
    end

    % M4 stride/window-boundary metadata contract (docs/phase_f/l2_event/
    % EVENT_WINDOW_EXTRACTOR_CONTRACT.md) -- only written when the caller
    % opted into a window_contract; '' (default) preserves the exact
    % pre-M4 metadata shape for every existing non-event-window caller.
    if strcmp(window_contract, 'fixed')
        % Burn-in consumes absolute ticks 1..tick_offset BEFORE capture
        % begins, so the first captured tick is tick_offset + 1, not
        % tick_offset (single absolute 1-based coordinate system shared
        % with 'anchor' below and with window_loader.WindowGrid.absolute_tick).
        metadata.stride = int32(1);
        metadata.tick_start = int32(effective_tick_start + 1);
        metadata.tick_end = int32(effective_tick_start + n_ticks);
    elseif strcmp(window_contract, 'anchor')
        % capture_anchor_window's own tick numbering already starts at
        % absolute tick 1 (no burn-in exists for 'anchor'; enforced above),
        % so tick_start/window_anchor need no further +1 adjustment here.
        metadata.stride = int32(1);
        metadata.tick_start = int32(effective_tick_start);
        metadata.window_anchor = int32(window_anchor_tick);
        % Anchor-config identity-binding metadata (M4 correction): persisted
        % so a trace produced for a DIFFERENT signal_kind/signal_property/
        % signal_field/max_search_ticks request can never validate/skip-valid
        % against a spec it wasn't actually generated for (see
        % launcher.validate_existing_event_window's anchor cross-check).
        metadata.signal_kind = anchor_opts.signal_kind;
        metadata.signal_property = anchor_opts.signal_property;
        metadata.signal_field = anchor_opts.signal_field;
        metadata.max_search_ticks = int32(anchor_opts.max_search_ticks);
        % Schema/version tag for merge_event_observables()'s flattened
        % numeric event-observable projection (performance/sufficiency
        % patch, post-Turn-3): bumped 1 -> 2 because signal_kind=
        % 'diameter_decrease' traces now additionally carry
        % 'chromosome_segregated' and no longer carry the full
        % 'chromosome' object (see exclude_chromosome_object_for_diameter_
        % anchor/merge_event_observables above). Must always match the
        % Python-side scripts.l2_event.launcher.EVENT_OBSERVABLE_
        % PROJECTION_VERSION literal exactly -- validate_existing_event_
        % window cross-checks it so a stale v1 on-disk anchor trace
        % (either signal_kind) can never silently skip-valid against a v2
        % spec.
        metadata.event_observable_projection_version = int32(2);
        % onset_tick (M4/ratified-decision addition): the real, observed
        % first strict pinchedDiameter decrease -- the process-local
        % contraction-onset-to-completion TIMING anchor. Only produced for
        % signal_kind='diameter_decrease' (Cytokinesis); a
        % 'boolean_transition' single-event anchor has no distinct onset,
        % so onset_tick is intentionally omitted (never fabricated) for
        % that kind. window_anchor remains the CAPTURE-boundary
        % (completion) tick; onset_tick is never a substitute for it and
        % tick_offset (== burn_in_tick_offset, always 0 for 'anchor' mode)
        % is never read as a timing anchor by any downstream adapter.
        if ~isempty(onset_tick)
            metadata.onset_tick = int32(onset_tick);
        end
    end

    save(out_path, 'states_before', 'states_after', 'metadata', '-v7.3');
    fprintf('[trace_v2] saved: %s\n', out_path);
end

if ~isempty(failed_processes)
    % Any requested-process failure must fail the WHOLE batch: throw here so
    % build_matlab_command's outer try/catch (see build_matlab_command below)
    % converts this into a nonzero MATLAB exit code. Per-process diagnostics
    % were already fprintf'd above; this aggregates them into the thrown
    % message so a single failed process can never look like a clean exit 0.
    error('extract_per_process_traces_v2:extraction_failed', ...
        'extraction failed for %d of %d requested process(es):\n%s', ...
        numel(failed_processes), numel(process_names), strjoin(failed_processes, '\n'));
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

function props = exclude_chromosome_object_for_diameter_anchor(props, window_contract, anchor_opts)
% exclude_chromosome_object_for_diameter_anchor  Performance/sufficiency
% patch (post-Turn-3): for window_contract='anchor' with
% signal_kind='diameter_decrease' (Cytokinesis) ONLY, drop the full
% 'chromosome' property from the per-tick snapshot set. The anchor search
% loop runs before/after tap points for up to anchor_opts.max_search_ticks
% ticks (default 50000); sanitize_snapshot_value/serialize_chromosome_state
% serializes the ENTIRE sparse Chromosome state object (positions x
% strands matrices) twice per searched tick for a process that, per its
% own evolveState() (see Cytokinesis.m: `if ~this.chromosome.segregated;
% return; end`), only ever reads a single scalar boolean off of it. That
% scalar is captured separately and flattened by merge_event_observables
% (see 'chromosome_segregated' below) -- the full object is therefore
% redundant, unbounded-cost snapshot weight, not lost signal.
%
% Fixed windows and generic 'boolean_transition' anchors are NEVER
% affected: 'chromosome' snapshots for every other process/profile are
% preserved exactly as before (requirement: "do not remove chromosome
% snapshots for other processes/profiles").
if strcmp(window_contract, 'anchor') && strcmp(anchor_opts.signal_kind, 'diameter_decrease')
    props = setdiff(props, {'chromosome'});
end
end

function [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, anchor_opts, extraction_opts)
% evolve_state_with_tap  One tick of the allocator-correct scheduler loop,
% tapping the target process's properties immediately before/after its own
% evolveState() call.
%
% anchor_opts (optional, default [] -- no change to fixed-window/backward-
% compatible behaviour): when non-empty, merge_event_observables() is
% called at BOTH tap points (never post-hoc, after the tick has already
% passed) so before_tick/after_tick carry the real per-tick numeric event-
% observable projection (see merge_event_observables) that
% capture_anchor_window uses to detect onset/completion.
%
% extraction_opts (optional, default struct()): when per-process substrate
% overrides are present, apply them on the REAL process-local substrate
% vector before calcResourceRequirements_Current() and again after
% allocator injection but before evolveState() so fixed-window stimulus
% cohorts exercise the same scheduler/allocation path as an ordinary run.
if nargin < 4
    anchor_opts = [];
end
if nargin < 5
    extraction_opts = struct();
end
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
    mod = apply_process_substrate_overrides(mod, extraction_opts);
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
    mod = apply_process_substrate_overrides(mod, extraction_opts);
    if proc_idx == rna_decay_idx && isprop(mod, 'RNAs')
        % Guard against negative RNA counts propagating into weighted sampling.
        mod.RNAs = max(0, mod.RNAs);
    end

    if proc_idx == target_idx
        before_tick = snapshot_from_process(mod, snapshot_props);
        if ~isempty(anchor_opts)
            before_tick = merge_event_observables(before_tick, mod, anchor_opts);
        end
    end

    mod.evolveState();

    if proc_idx == target_idx
        after_tick = snapshot_from_process(mod, snapshot_props);
        if ~isempty(anchor_opts)
            after_tick = merge_event_observables(after_tick, mod, anchor_opts);
        end
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
% signal_kind defaults to 'diameter_decrease' (Cytokinesis's own real
% CellGeometry.pinchedDiameter contraction/completion signal -- see
% CellGeometry.m/Cytokinesis.m). signal_property is the process property
% that holds the signal's container ('geometry' for Cytokinesis).
% signal_field is used only for signal_kind='boolean_transition' (generic
% EVENT_CLASS processes) -- ignored for 'diameter_decrease', which always
% reads pinchedDiameter plus the FtsZRing ring-state witnesses plus the
% chromosome_segregated scalar (see merge_event_observables); the full
% sparse 'chromosome' object is excluded from the snapshot for this
% signal_kind (see exclude_chromosome_object_for_diameter_anchor).
% Callers extracting a different process's
% division/event-anchored window may override signal_kind/signal_property/
% signal_field to that process's own equivalent real signal -- never to a
% value derived from the expected/desired outcome.
if ~isfield(opts, 'max_search_ticks') || isempty(opts.max_search_ticks)
    opts.max_search_ticks = 50000;
end
if ~isfield(opts, 'signal_kind') || isempty(opts.signal_kind)
    opts.signal_kind = 'diameter_decrease';
end
if ~any(strcmp(opts.signal_kind, {'diameter_decrease', 'boolean_transition'}))
    error('extract_per_process_traces_v2:invalid_signal_kind', ...
        'anchor_opts.signal_kind must be ''diameter_decrease'' or ''boolean_transition'' (got ''%s'')', opts.signal_kind);
end
if ~isfield(opts, 'signal_property') || isempty(opts.signal_property)
    opts.signal_property = 'geometry';
end
if ~isfield(opts, 'signal_field') || isempty(opts.signal_field)
    if strcmp(opts.signal_kind, 'diameter_decrease')
        opts.signal_field = 'pinchedDiameter';
    else
        opts.signal_field = 'pinched';
    end
end
end

function opts = default_extraction_opts(opts)
% default_extraction_opts  Fill in defaults for optional extraction identity
% / override payloads. All fields are optional and backward-compatible:
% empty values mean "no extra metadata, no overrides".
if ~isfield(opts, 'condition_label') || isempty(opts.condition_label)
    opts.condition_label = '';
end
if ~isfield(opts, 'metadata_identity_json') || isempty(opts.metadata_identity_json)
    opts.metadata_identity_json = '';
end
if ~isfield(opts, 'per_process_substrate_overrides') || isempty(opts.per_process_substrate_overrides)
    opts.per_process_substrate_overrides = struct();
end
end

function mod = apply_process_substrate_overrides(mod, extraction_opts)
% apply_process_substrate_overrides  Apply any requested per-process
% substrate overrides to the REAL process-local substrate vector.
%
% The override map is keyed by process name, then by substrate WID. Matching
% is name-normalized (same helper as find_process_index) so the caller may
% use "DNADamage", "Process_DNADamage", or a punctuation variant without
% changing semantics.
if ~isfield(extraction_opts, 'per_process_substrate_overrides') || isempty(fieldnames(extraction_opts.per_process_substrate_overrides))
    return;
end
override_values = select_process_substrate_overrides(extraction_opts.per_process_substrate_overrides, mod);
if isempty(override_values)
    return;
end
if ~isprop(mod, 'substrates') || ~isprop(mod, 'substrateWholeCellModelIDs')
    error('extract_per_process_traces_v2:missing_substrate_override_surface', ...
        'process %s has no substrates/substrateWholeCellModelIDs surface required for per-process substrate overrides', ...
        process_short_name(mod));
end

substrate_wids = matlab_cellstr(mod.substrateWholeCellModelIDs);
override_fields = fieldnames(override_values);
for i = 1:numel(override_fields)
    wid = override_fields{i};
    idx = find(strcmp(substrate_wids, wid), 1);
    if isempty(idx)
        error('extract_per_process_traces_v2:unknown_override_substrate', ...
            'process %s does not expose override substrate WID ''%s'' on its local substrate vector', ...
            process_short_name(mod), wid);
    end
    mod.substrates(idx, :) = double(override_values.(wid));
end
end

function override_values = select_process_substrate_overrides(per_process_overrides, mod)
override_values = [];
process_tokens = { ...
    normalize_name_token(process_short_name(mod)), ...
    normalize_name_token(mod.wholeCellModelID) ...
};
if isprop(mod, 'name')
    process_tokens{end + 1} = normalize_name_token(mod.name); %#ok<AGROW>
end
override_names = fieldnames(per_process_overrides);
for i = 1:numel(override_names)
    name = override_names{i};
    if any(strcmp(process_tokens, normalize_name_token(name)))
        override_values = per_process_overrides.(name);
        return;
    end
end
end

function out = matlab_cellstr(values)
if ischar(values)
    out = cellstr(values);
    return;
end
if isstring(values)
    out = cellstr(values);
    return;
end

raw = values(:);
out = cell(numel(raw), 1);
for i = 1:numel(raw)
    item = raw{i};
    if isstring(item)
        item = char(item);
    end
    out{i} = char(item);
end
end

function snapshot = merge_event_observables(snapshot, mod, anchor_opts)
% merge_event_observables  Add the smallest source-faithful FLATTENED
% NUMERIC event-observable projection to an existing tap-point snapshot
% struct. Never exposes a raw state/handle object to the caller --
% window_loader._cell_series() (Python) can only materialize numeric or
% logical per-tick scalars, never MATLAB objects/structs -- so every value
% merged in here is a `double`/`logical` scalar, read via a validated
% temporary variable (`container = mod.(container_name);`) and then a
% second, separate dereference off of that temporary. This two-step form
% is a readability/validation choice (each dereference gets its own
% isprop/isfield check before use), not a workaround for a MATLAB parse
% restriction -- chained dynamic-field access (`a.(b).(c)`) is itself
% valid MATLAB/Octave syntax.
container_name = anchor_opts.signal_property;
if ~isprop(mod, container_name)
    error('extract_per_process_traces_v2:missing_signal_container', ...
        'process has no property ''%s'' (window_contract=''anchor'' requires a real, readable signal container)', ...
        container_name);
end
container = mod.(container_name);  % validated temporary -- first dereference

switch anchor_opts.signal_kind
    case 'diameter_decrease'
        % Cytokinesis's own real completion signal: CellGeometry.pinchedDiameter
        % (see CellGeometry.m) plus the four FtsZRing ring-state witnesses
        % Cytokinesis.evolveState() itself gates the diameter update on (see
        % Cytokinesis.m) -- included so onset/completion can be cross-checked
        % against the real ring state that produced them, never trusting the
        % scalar diameter alone.
        if ~isprop(container, 'pinchedDiameter')
            error('extract_per_process_traces_v2:missing_diameter_field', ...
                '''%s'' has no ''pinchedDiameter'' property', container_name);
        end
        snapshot.pinchedDiameter = double(container.pinchedDiameter);  % second dereference

        if ~isprop(mod, 'ftsZRing')
            error('extract_per_process_traces_v2:missing_ftszring', ...
                'process has no ''ftsZRing'' property required for signal_kind=''diameter_decrease'' witnesses');
        end
        ring = mod.ftsZRing;  % validated temporary
        ring_fields = {'numEdgesOneStraight', 'numEdgesTwoStraight', 'numEdgesTwoBent', 'numResidualBent'};
        for k = 1:numel(ring_fields)
            fn = ring_fields{k};
            if ~isprop(ring, fn)
                error('extract_per_process_traces_v2:missing_ring_field', 'FtsZRing has no ''%s'' property', fn);
            end
            snapshot.(['ftsZRing_' fn]) = double(ring.(fn));
        end

        % chromosome_segregated (performance/sufficiency patch): the exact
        % scalar boolean Cytokinesis.evolveState() itself reads to gate
        % contraction (Cytokinesis.m: `if ~this.chromosome.segregated;
        % return; end`) -- the ONLY chromosome-state field this process
        % ever reads. Flattened here (validated temporary + second
        % dereference, same two-step form as pinchedDiameter/FtsZRing
        % above) so a real, sufficient conditioning signal is available to
        % window_loader without ever snapshotting the full sparse
        % Chromosome object (see
        % exclude_chromosome_object_for_diameter_anchor/
        % pick_snapshot_properties above).
        if ~isprop(mod, 'chromosome')
            error('extract_per_process_traces_v2:missing_chromosome', ...
                'process has no ''chromosome'' property required for signal_kind=''diameter_decrease'' witnesses');
        end
        chrom = mod.chromosome;  % validated temporary
        if ~isprop(chrom, 'segregated')
            error('extract_per_process_traces_v2:missing_chromosome_field', ...
                'chromosome has no ''segregated'' property');
        end
        snapshot.chromosome_segregated = logical(chrom.segregated);  % second dereference

    case 'boolean_transition'
        field_name = anchor_opts.signal_field;
        has_field = (isobject(container) && isprop(container, field_name)) || ...
                    (isstruct(container) && isfield(container, field_name));
        if ~has_field
            error('extract_per_process_traces_v2:missing_signal_field', ...
                '''%s'' has no field/property ''%s''', container_name, field_name);
        end
        value = container.(field_name);  % second dereference, on a validated temporary
        snapshot.(field_name) = logical(value);

    otherwise
        error('extract_per_process_traces_v2:invalid_signal_kind', ...
            'anchor_opts.signal_kind must be ''diameter_decrease'' or ''boolean_transition'' (got ''%s'')', ...
            anchor_opts.signal_kind);
end
end

function [states_before, states_after, tick_start, window_anchor_tick, onset_tick, ok, error_message] = ...
    capture_anchor_window(sim, target_idx, snapshot_props, n_ticks, anchor_opts, extraction_opts)
% capture_anchor_window  Division/event-anchored window capture (M4,
% ratified Cytokinesis timing decision 2026-08-02).
%
% Free-runs the simulation tick-by-tick from t=1 using the SAME per-tick
% scheduler/allocation/tap semantics as the fixed-window path
% (evolve_state_with_tap), maintaining a size-n_ticks circular buffer of
% (before, after) snapshots. Each snapshot carries the real, per-tick
% event-observable projection merged in by merge_event_observables --
% never a post-hoc re-read of a mutable handle object after the tick has
% already passed.
%
% Two REAL, per-tick observed transitions are detected directly from each
% tick's own before/after values (never a persistent end-of-tick flag,
% never assumed true at tick 1 without a genuine prior sample):
%   onset (signal_kind='diameter_decrease' only) -- the FIRST tick where
%     before.pinchedDiameter > after.pinchedDiameter >= 0: a real strict
%     contraction observed during that tick's own evolveState call.
%   completion -- 'diameter_decrease': the first tick where
%     before.pinchedDiameter > 0 && after.pinchedDiameter == 0.
%     'boolean_transition': the first tick where before.(signal_field) is
%     false and after.(signal_field) is true (a genuine false->true
%     transition with a captured prior value).
%
% The search stops at the FIRST completion tick found -- it never scans
% past it, so a completion can never be silently duplicated by continuing
% to search for a second one. The n_ticks window is the fixed-length span
% ending exactly at that completion tick (cohort lengths stay equal). This
% function fails loudly (ok=false) rather than emit a timing-incomplete
% file when: no completion is ever observed; completion occurs before a
% full n_ticks window could be collected; no onset was observed (diameter_
% decrease only); or the observed onset does not strictly precede
% tick_start..completion. There is no fallback that invents an onset or
% completion.
ok = true;
error_message = '';
onset_tick = [];
completion_tick = [];
tick_start = [];
window_anchor_tick = [];
states_before = struct();
states_after = struct();

buffer_before = cell(n_ticks, 1);
buffer_after = cell(n_ticks, 1);
next_slot = 1;

t = 0;
while t < anchor_opts.max_search_ticks
    t = t + 1;
    try
        [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, anchor_opts, extraction_opts);
    catch err
        ok = false;
        error_message = sprintf('anchor search tick %d failed:\n%s', t, getReport(err, 'extended', 'hyperlinks', 'off'));
        return;
    end

    slot = mod(next_slot - 1, n_ticks) + 1;
    buffer_before{slot} = before_tick;
    buffer_after{slot} = after_tick;
    next_slot = next_slot + 1;

    is_onset_tick = false;
    switch anchor_opts.signal_kind
        case 'diameter_decrease'
            before_val = before_tick.pinchedDiameter;
            after_val = after_tick.pinchedDiameter;
            is_onset_tick = (before_val > after_val) && (after_val >= 0);
            is_completion_tick = (before_val > 0) && (after_val == 0);
        case 'boolean_transition'
            before_val = logical(before_tick.(anchor_opts.signal_field));
            after_val = logical(after_tick.(anchor_opts.signal_field));
            is_completion_tick = (~before_val) && after_val;
        otherwise
            ok = false;
            error_message = sprintf('anchor_opts.signal_kind must be ''diameter_decrease'' or ''boolean_transition'' (got ''%s'')', anchor_opts.signal_kind);
            return;
    end

    if isempty(onset_tick) && is_onset_tick
        onset_tick = t;
    end

    if is_completion_tick
        completion_tick = t;
        break;
    end
end

if isempty(completion_tick)
    ok = false;
    error_message = sprintf( ...
        ['division/event-completion signal did not fire within max_search_ticks=%d ticks -- refusing to ' ...
         'fabricate a window_anchor; either raise anchor_opts.max_search_ticks or this seed genuinely does ' ...
         'not complete in that many ticks'], anchor_opts.max_search_ticks);
    return;
end

if completion_tick < n_ticks
    ok = false;
    error_message = sprintf( ...
        ['completion observed at tick %d, before a full n_ticks=%d window could be collected -- refusing to ' ...
         'emit a timing-incomplete file'], completion_tick, n_ticks);
    return;
end

tick_start = completion_tick - n_ticks + 1;
window_anchor_tick = completion_tick;

if strcmp(anchor_opts.signal_kind, 'diameter_decrease')
    if isempty(onset_tick)
        ok = false;
        error_message = 'no real strict pinchedDiameter decrease (onset) was observed before completion -- refusing to fabricate onset_tick';
        return;
    end
    if onset_tick < tick_start
        ok = false;
        error_message = sprintf( ...
            'onset_tick=%d precedes the captured window start tick_start=%d (n_ticks window too short to contain the real onset)', ...
            onset_tick, tick_start);
        return;
    end
    if onset_tick >= window_anchor_tick
        ok = false;
        error_message = sprintf('onset_tick=%d does not strictly precede completion/window_anchor=%d', onset_tick, window_anchor_tick);
        return;
    end
end

% The buffer is circular; `next_slot`'s current position is the slot that
% will be overwritten NEXT, i.e. the oldest entry still held. Replay the
% buffer starting there so states_before/after end up in chronological
% order (row 1 == tick_start .. row n_ticks == window_anchor_tick).
% Fields are discovered per-tick (not hardcoded) so both the standard
% snapshot_props and whatever merge_event_observables added are captured.
oldest_slot = mod(next_slot - 1, n_ticks) + 1;
for k = 1:n_ticks
    src_slot = mod(oldest_slot - 1 + (k - 1), n_ticks) + 1;
    src_fields = fieldnames(buffer_before{src_slot});
    for p = 1:numel(src_fields)
        fn = src_fields{p};
        if ~isfield(states_before, fn)
            states_before.(fn) = cell(n_ticks, 1);
            states_after.(fn) = cell(n_ticks, 1);
        end
        states_before.(fn){k, 1} = buffer_before{src_slot}.(fn);
        states_after.(fn){k, 1} = buffer_after{src_slot}.(fn);
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

function hash_hex = mnrnd_shim_sha256_hex(matlab_dir)
% mnrnd_shim_sha256_hex  SHA-256 (lowercase hex) of scripts/matlab/mnrnd.m,
% with CR (0x0D) bytes stripped first so a CRLF-checked-out file hashes
% identically to an LF one. scripts/l2_event/launcher.py's
% mnrnd_shim_sha256_hex Python helper normalizes the same way when
% computing the EXPECTED hash at validate_existing_event_window time, so
% the two independently-computed hashes agree byte-for-byte regardless of
% checkout line-ending settings.
%
% No Statistics/other toolbox required: java.security.MessageDigest is
% part of the JVM every desktop MATLAB release embeds. This function is
% only ever called from the real (never-run-in-CI) extraction path, never
% from the Octave-based pure-function regression test for mnrnd.m itself.
mnrnd_path = fullfile(matlab_dir, 'mnrnd.m');
fid = fopen(mnrnd_path, 'rb');
if fid < 0
    error('extract_per_process_traces_v2:mnrnd_shim_unreadable', ...
        'could not open %s to compute its identity-binding hash', mnrnd_path);
end
raw = fread(fid, Inf, '*uint8')';
fclose(fid);
raw = raw(raw ~= uint8(13));
digest = java.security.MessageDigest.getInstance('SHA-256');
digest_bytes = typecast(digest.digest(raw), 'uint8');
hash_hex = lower(sprintf('%02x', digest_bytes));
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
