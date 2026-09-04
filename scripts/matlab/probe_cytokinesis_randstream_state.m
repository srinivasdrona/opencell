function probe_cytokinesis_randstream_state(seed, tick_start, local_from, local_to, out_path)
% probe_cytokinesis_randstream_state  Stage-1 randStream state probe for
% the L2.1 Cytokinesis active-window tick-228 residual divergence (see
% STATUS_L21_CYTOKINESIS_ACTIVE_FIX.md).
%
% Records the REAL Cytokinesis process's this.randStream.state entering
% and exiting each of its own evolveState() calls, for a bounded window of
% the ACTUAL full Simulation trajectory (never an isolated per-process
% replay, never inferred from OC's own aggregate output) -- reruns the
% identical seed=0 setup that produced the accepted genuine event trace
% data/m1_sources/karr_native/per_process_traces_v2_event_s000/
% Cytokinesis_4000ticks.mat (tick_start=27047), from t=1 up to a fixed,
% caller-supplied absolute tick limit. Does NOT re-discover tick_start via
% anchor search -- that value is already known/verified from the accepted
% trace's own metadata, and is passed in explicitly so this probe can
% never silently target the wrong absolute tick range.
%
% Reuses the shared karr_bootstrap() entry point (fitted Simulation
% snapshot + genuine mnrnd provider enforcement) unchanged. Duplicates
% (does not import -- MATLAB script-local functions are not externally
% callable across files) the per-tick scheduler/allocation loop
% (evolve_state_with_tap) and small supporting helpers from
% extract_per_process_traces_v2.m, functionally verbatim except for two
% added this.randStream.state captures immediately before/after the
% target process's own evolveState() call, plus a chromosome.segregated
% read at the same two points. The duplicated block's provenance (SHA256
% of scripts/matlab/extract_per_process_traces_v2.m at duplication time:
% ea6675d76f012e89c3599a01e9deb1ef32c7aea69fc97d637b1e1224c794eb25 --
% re-synced 2026-09-04 when the authoritative extractor gained its OWN
% generic capture_rand_stream_state()/before_tick.randStreamState /
% after_tick.randStreamState instrumentation plus unconditional dec-005
% DNADamage source-hash-binding metadata; the shared scheduler/allocation
% loop and process tap points this probe duplicates were manually
% re-diffed against the new file and found unchanged) is recorded in the
% output JSON's metadata so future drift between the two copies is
% mechanically detectable (re-hash and compare).
%
% No source file is modified and no path overlay is used in this stage --
% RandStream.state is a public-getter dependent property
% (edu.stanford.covert.util.RandStream.m: `function value = get.state
% (this); value = this.randStream.State; end`), readable externally
% without any instrumentation of Cytokinesis.m itself. If this stage's
% state deltas do not localize the tick-228 divergence to a single tick,
% Stage 2 (a hash-bound Cytokinesis.m source overlay under
% tmp/wcm_source_overlay/, mirroring karr_bootstrap.m's existing DNADamage
% signed-zero overlay pattern -- never modifying the canonical file in
% place) adds per-phase state checkpoints inside evolveState for the
% implicated tick only.
%
% Inputs:
%   seed        : uint32 simulation seed (0 for the accepted genuine trace)
%   tick_start  : absolute 1-based tick where the accepted trace's
%                 trace-local tick 0 begins (27047 for seed 0; read from
%                 Cytokinesis_4000ticks.mat metadata/tick_start, never
%                 re-derived here)
%   local_from  : first trace-local tick (0-based, matching the Python
%                 harness's tick numbering) to bracket with state capture
%   local_to    : last trace-local tick (0-based) to bracket with capture
%   out_path    : output JSON path
%
% Usage (seed 0, accepted trace's tick_start=27047, local ticks 224-230):
%   probe_cytokinesis_randstream_state(uint32(0), 27047, 224, 230, ...
%       'tmp/cytokinesis_randstream_probe_s000.json');

if nargin < 1 || isempty(seed)
    seed = uint32(0);
end
if nargin < 2 || isempty(tick_start)
    error('probe_cytokinesis_randstream_state:missing_tick_start', ...
        'tick_start is required -- read it from the accepted trace''s metadata, never guess it here');
end
if nargin < 3 || isempty(local_from)
    local_from = 224;
end
if nargin < 4 || isempty(local_to)
    local_to = 230;
end
if nargin < 5 || isempty(out_path)
    out_path = 'tmp/cytokinesis_randstream_probe.json';
end

seed = uint32(seed);
tick_start = double(tick_start);
local_from = double(local_from);
local_to = double(local_to);

if local_to < local_from
    error('probe_cytokinesis_randstream_state:bad_range', 'local_to must be >= local_from');
end

capture_from_abs = tick_start + local_from;
capture_to_abs = tick_start + local_to;
run_to_abs = capture_to_abs + 1; % one extra tick of margin beyond the requested window

this_file_hash_note = 'ea6675d76f012e89c3599a01e9deb1ef32c7aea69fc97d637b1e1224c794eb25';

fprintf('[probe] bootstrapping Karr simulation (seed=%d)\n', seed);
[sim, mnrnd_provider, ~] = karr_bootstrap();

[target_idx, canonical_name] = find_process_index_probe(sim, 'Cytokinesis');
if isempty(target_idx) || ~strcmp(canonical_name, 'Cytokinesis')
    error('probe_cytokinesis_randstream_state:process_not_found', ...
        'Cytokinesis process not found in bootstrapped simulation');
end

seed_simulation_probe(sim, seed);

extraction_opts = struct('per_process_substrate_overrides', struct());

captures = struct( ...
    'absolute_tick', {}, 'local_tick', {}, ...
    'entry_state', {}, 'exit_state', {}, ...
    'chromosome_segregated_before', {}, 'chromosome_segregated_after', {} ...
);

fprintf('[probe] free-running to absolute tick %d (capturing local ticks %d..%d, absolute %d..%d)\n', ...
    run_to_abs, local_from, local_to, capture_from_abs, capture_to_abs);

for t = 1:run_to_abs
    [sim, entry_state, exit_state, seg_before, seg_after] = ...
        evolve_state_with_tap_probe(sim, target_idx, extraction_opts);

    if t >= capture_from_abs && t <= capture_to_abs
        idx = numel(captures) + 1;
        captures(idx).absolute_tick = t;
        captures(idx).local_tick = t - tick_start;
        captures(idx).entry_state = double(entry_state);
        captures(idx).exit_state = double(exit_state);
        captures(idx).chromosome_segregated_before = logical(seg_before);
        captures(idx).chromosome_segregated_after = logical(seg_after);
        fprintf('[probe] local_tick=%d absolute_tick=%d entry_state=%s exit_state=%s seg_before=%d seg_after=%d\n', ...
            t - tick_start, t, mat2str(double(entry_state)), mat2str(double(exit_state)), ...
            logical(seg_before), logical(seg_after));
    end

    if mod(t, 2000) == 0
        fprintf('[probe] ... absolute tick %d / %d\n', t, run_to_abs);
    end
end

result = struct( ...
    'seed', double(seed), ...
    'tick_start', tick_start, ...
    'local_from', local_from, ...
    'local_to', local_to, ...
    'run_to_absolute_tick', run_to_abs, ...
    'duplicated_from_file', 'scripts/matlab/extract_per_process_traces_v2.m', ...
    'duplicated_from_sha256', this_file_hash_note, ...
    'mnrnd_provider_kind', mnrnd_provider.kind, ...
    'mnrnd_provider_sha256', mnrnd_provider.sha256_lf_normalized, ...
    'captures', captures ...
);

out_dir = fileparts(out_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(out_path, 'w');
if fid < 0
    error('probe_cytokinesis_randstream_state:write_failed', 'unable to open %s for writing', out_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(result), 'char');

fprintf('[probe] wrote %s\n', out_path);
end

% -----------------------------------------------------------------------
% Duplicated (not imported -- MATLAB script-local functions defined after
% the first function in a .m file are not callable from another file) from
% scripts/matlab/extract_per_process_traces_v2.m's evolve_state_with_tap
% and its direct callees, functionally verbatim except for the two
% randStream.state + chromosome.segregated captures marked below. Any
% future change to the canonical evolve_state_with_tap's scheduler/
% allocation semantics must be manually re-applied here; re-hash
% extract_per_process_traces_v2.m and compare against
% duplicated_from_sha256 above to detect drift.
% -----------------------------------------------------------------------
function [sim, entry_state, exit_state, seg_before, seg_after] = ...
    evolve_state_with_tap_probe(sim, target_idx, extraction_opts)
entry_state = [];
exit_state = [];
seg_before = false;
seg_after = false;

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
    apply_process_substrate_overrides_probe(mod, extraction_opts);
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
    apply_process_substrate_overrides_probe(mod, extraction_opts);
    if proc_idx == rna_decay_idx && isprop(mod, 'RNAs')
        % Guard against negative RNA counts propagating into weighted sampling.
        mod.RNAs = max(0, mod.RNAs);
    end

    if proc_idx == target_idx
        entry_state = mod.randStream.state;          % <-- Stage-1 instrumentation
        seg_before = logical(mod.chromosome.segregated); % <-- Stage-1 instrumentation
    end

    mod.evolveState();

    if proc_idx == target_idx
        exit_state = mod.randStream.state;            % <-- Stage-1 instrumentation
        seg_after = logical(mod.chromosome.segregated);  % <-- Stage-1 instrumentation
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

function apply_process_substrate_overrides_probe(mod, extraction_opts) %#ok<INUSD>
% Deliberately narrower than the canonical apply_process_substrate_overrides:
% this probe only ever runs Cytokinesis (no per-process substrate override
% support needed), so it fails loudly rather than silently no-op/duplicate
% the DNADamage-specific override logic it will never exercise.
if ~isfield(extraction_opts, 'per_process_substrate_overrides') || isempty(fieldnames(extraction_opts.per_process_substrate_overrides))
    return;
end
error('probe_cytokinesis_randstream_state:overrides_not_supported', ...
    'This probe does not support per_process_substrate_overrides');
end

function [idx, canonical_name] = find_process_index_probe(sim, requested_name)
% Duplicated from extract_per_process_traces_v2.m's find_process_index.
idx = [];
canonical_name = '';
want = normalize_name_token_probe(requested_name);

for i = 1:numel(sim.processes)
    proc = sim.processes{i};
    short = process_short_name_probe(proc);
    tokens = { ...
        normalize_name_token_probe(short), ...
        normalize_name_token_probe(proc.wholeCellModelID) ...
    };
    if isprop(proc, 'name')
        tokens{end + 1} = normalize_name_token_probe(proc.name); %#ok<AGROW>
    end
    if any(strcmp(tokens, want))
        idx = i;
        canonical_name = short;
        return;
    end
end
end

function short = process_short_name_probe(proc)
wid = proc.wholeCellModelID;
if strncmp(wid, 'Process_', numel('Process_'))
    short = wid(numel('Process_') + 1:end);
else
    short = wid;
end
end

function token = normalize_name_token_probe(s)
token = lower(regexprep(char(s), '[^a-zA-Z0-9]', ''));
end

function seed_simulation_probe(sim, seed)
% Duplicated from extract_per_process_traces_v2.m's seed_simulation.
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
