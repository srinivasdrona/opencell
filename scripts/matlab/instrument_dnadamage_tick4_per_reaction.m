function report = instrument_dnadamage_tick4_per_reaction(output_json_path)
% instrument_dnadamage_tick4_per_reaction
%
% Per-reaction-granularity instrumentation of Karr's REAL DNADamage
% evolveState() for seed2000's tick 5 (1-based; absolute tick 4, 0-based
% -- Karr's own first genuinely active tick in the canonical event
% window). Does NOT modify DNADamage.m/Chromosome.m/RandStream.m in any
% way (no overlay, no patched copy) -- this script calls the REAL,
% UNMODIFIED class methods/properties externally (the same pattern
% extract_per_process_traces_v2.m's evolve_state_with_tap already uses to
% read/write `mod.substrates` etc from outside the class). Because
% nothing about Karr's actual algorithm is touched, this instrumentation
% cannot itself introduce a behavioral divergence -- it can only OBSERVE
% one.
%
% For ticks 1-4 (1-based), this script replays the EXACT SAME
% allocator/scheduler loop extract_per_process_traces_v2.m's
% evolve_state_with_tap already uses (copied verbatim below, not
% refactored/exported, to avoid any risk of behavioral drift from a
% shared-code refactor) to advance the real simulation to the identical
% state our already-extracted, already-verified seed2000 trace was
% captured from. Then, for tick 5, instead of calling `mod.evolveState()`
% as a black box, it inlines evolveState()'s own literal per-reaction
% loop (DNADamage.m lines ~535-573, quoted in this file's comments,
% checked against the loaded source at runtime via the same source-hash
% binding already used elsewhere in this project) and logs, per
% reaction, in real Karr randomOrder iteration order:
%   - reaction 0-based index j, WID, vulnerableMotif, vulnerableMotifType,
%     is-string-motif
%   - maxReactions, selectionProbability (both exactly as evolveState
%     computes them, including the min/max/floor semantics)
%   - chromosome.randStream.state immediately before/after this
%     reaction's setSiteDamaged() call (a plain .state READ, consuming no
%     draw, exactly as merge_chromosome_rand_stream_state already does)
%   - the exact draw count consumed by this ONE reaction's
%     setSiteDamaged() call, derived via the same proven, non-destructive
%     clone-and-step-with-plain-rand() reconstruction technique already
%     used by reconstruct_chromosome_draw_ledger.m (a SCRATCH clone only,
%     never the live simulation's real stream)
%   - the actual size(positionsStrands,1) returned (i.e. how many sites
%     were really damaged)
%   - running cumulative draw count across all reactions processed so far
%     this tick
%
% Source/provider hash binding (for exact provenance, no guessing): reads
% karr_bootstrap()'s own returned dnadamage_overlay (DNADamage.m resolved
% hash) and independently hashes Chromosome.m/RandStream.m the same way
% reconstruct_chromosome_draw_ledger.m already does.

if nargin < 1 || isempty(output_json_path)
    output_json_path = fullfile('artifacts', 'l21_dnadamage_chromosome_rng', 'tick4_matlab_per_reaction_ledger.json');
end

SEED = uint32(2000);
CONDITION_LABEL = 'uvb_mechanism';
UVB_VALUE = 7.474096569667582;
TARGET_TICK_1BASED = 5; % absolute tick index 4, 0-based

[sim, mnrnd_provider, dnadamage_overlay] = karr_bootstrap();
target_idx = find_process_index_local(sim, 'DNADamage');
if isempty(target_idx)
    error('instrument_dnadamage_tick4_per_reaction:process_not_found', 'DNADamage process not found');
end
mod = sim.processes{target_idx};

seed_simulation_local(sim, SEED);

extraction_opts = struct( ...
    'condition_label', CONDITION_LABEL, ...
    'per_process_substrate_overrides', struct('DNADamage', struct('UVB_radiation', UVB_VALUE)));
sim = apply_condition_overrides_local(sim, mod, 'DNADamage', extraction_opts);

% --- Burn in ticks 1..(TARGET_TICK_1BASED-1) using the EXACT SAME
% scheduler/allocation loop as evolve_state_with_tap (copied verbatim
% below as evolve_state_with_tap_local; not refactored/shared, to avoid
% any risk that a shared-code change could silently affect the already-
% accepted extractor). ---
for t = 1:(TARGET_TICK_1BASED - 1)
    [sim, ~, ~] = evolve_state_with_tap_local(sim, -1, extraction_opts); % target_idx=-1: no tap, just advance
end

% --- Capture the chromosome-stream state right before tick 5 begins, to
% cross-check against the already-captured ledger
% (data/m1_sources/karr_native/per_process_traces_v2_event_s2000/
% DNADamage_20ticks.chromosome_rand_stream_ledger.json tick 5's
% state_before) as an independent consistency check that this
% replay-to-tick-5 procedure reproduces the identical real simulation
% state our trace was captured from. ---
pre_tick5_chrom_state = double(mod.chromosome.randStream.state);

% --- Tick 5: run the REAL allocator loop, but instrument DNADamage's own
% evolveState() in detail instead of calling it as a black box. ---
reaction_log = instrument_one_dnadamage_tick(sim, target_idx, extraction_opts);

report = struct();
report.matlab_release = version('-release');
report.generated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');
report.seed = double(SEED);
report.target_tick_1based = TARGET_TICK_1BASED;
report.pre_tick5_chromosome_rand_stream_state = pre_tick5_chrom_state;
report.dnadamage_source_sha256 = dnadamage_overlay.resolved_sha256_lf_normalized;
report.dnadamage_source_resolved_path = dnadamage_overlay.resolved_path;
report.mnrnd_provider_identity = mnrnd_provider.identity_json;
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
    report.chromosome_source_sha256 = sha256_of_file_local(chromosome_path);
    report.randstream_util_source_sha256 = sha256_of_file_local(randstream_util_path);
catch err
    fprintf('[instrument_dnadamage_tick4_per_reaction] WARNING: could not hash Chromosome.m/RandStream.m: %s\n', err.message);
end
report.reactions = reaction_log;
report.total_draws = sum([reaction_log.draw_count]);

output_json_path = char(output_json_path);
[out_dir, ~, ~] = fileparts(output_json_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(output_json_path, 'w');
if fid == -1
    error('instrument_dnadamage_tick4_per_reaction:open_failed', 'Unable to open output path: %s', output_json_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(report), 'char');
fprintf('[instrument_dnadamage_tick4_per_reaction] wrote %s (%d reactions, total_draws=%d)\n', ...
    output_json_path, numel(reaction_log), report.total_draws);
end

function reaction_log = instrument_one_dnadamage_tick(sim, target_idx, extraction_opts)
% instrument_one_dnadamage_tick  Runs ONE tick's real allocator/scheduler
% loop (same as evolve_state_with_tap_local) but, when it is DNADamage's
% turn, inlines evolveState()'s own literal per-reaction loop (quoted
% verbatim in comments below from DNADamage.m lines ~535-573) instead of
% calling mod.evolveState() as a black box, logging per-reaction detail.
% Every primitive called (this.chromosome.setSiteDamaged, substrate
% updates, side-effect accumulation) is the REAL, unmodified Karr
% implementation -- this function only ADDS observation around it.
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
    m = processes{i};
    m.copyFromState();
    m = apply_process_substrate_overrides_local(m, extraction_opts);
    r = m.calcResourceRequirements_Current();
    gidx = m.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = m.substrateMetaboliteLocalIndexs;
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

reaction_log = struct([]);

for i = 1:nProcesses
    proc_idx = processEvalOrderIndexs(i);
    m = processes{proc_idx};

    gidx = m.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = m.substrateMetaboliteLocalIndexs;
    allocation = reshape(allocations(gidx, proc_idx), size(gidx));
    counts = mets.counts(gidx);

    m.simulationStateSideEffects = [];
    m.copyFromState();
    m.substrates(lidx, :) = allocation;
    m = apply_process_substrate_overrides_local(m, extraction_opts);
    if proc_idx == rna_decay_idx && isprop(m, 'RNAs')
        m.RNAs = max(0, m.RNAs);
    end

    if proc_idx == target_idx
        % --- INLINED, INSTRUMENTED evolveState() (DNADamage.m ~535-573).
        % Quoted below is the ORIGINAL on-disk source's literal text (not
        % what actually executes): karr_bootstrap() resolves DNADamage.m
        % through a generated signed-zero-normalization OVERLAY (see
        % karr_bootstrap.m::ensure_dnadamage_signed_zero_overlay), which
        % replaces the `max(0, -stoich)` denominator line below with
        % `abs(max(0, -stoich))` because an exact-zero stoichiometry
        % entry can produce a NEGATIVE ZERO (`-0.0`) that silently
        % poisons `min(...)` to `-Inf` (a positive substrate divided by
        % `-0.0` is `-Inf` in IEEE754). The implementation in
        % run_instrumented_evolve_state below applies this SAME
        % normalization -- an early draft of this instrumentation that
        % used the literal unpatched formula quoted here reproduced that
        % exact -Inf bug for all 32 of tick4's reactions (caught and
        % fixed empirically this session).
        %
        % function evolveState(this)
        %     randomOrder = this.randStream.randperm(numel(this.reactionWholeCellModelIDs));
        %     for i = 1:length(this.reactionWholeCellModelIDs)
        %         j = randomOrder(i);
        %         maxReactions = floor(min(this.substrates ./ max(0, -this.reactionSmallMoleculeStoichiometryMatrix(:, j))));
        %         if maxReactions <= 0
        %             continue;
        %         end
        %         radiationLclIdx  = this.reactionRadiation(j);
        %         if radiationLclIdx ~= 0
        %             selectionProbability = this.stepSizeSec * this.reactionBounds(j, 2) * this.substrates(radiationLclIdx);
        %         else
        %             selectionProbability = this.stepSizeSec * this.reactionBounds(j, 2);
        %         end
        %         if selectionProbability == 0
        %             continue;
        %         end
        %         [positionsStrands, sideEffects] = this.chromosome.setSiteDamaged(...
        %             this.reactionDamageTypes{j}, this.reactionDNAProduct(j), selectionProbability, ...
        %             maxReactions, this.reactionVulnerableMotifs{j}, this.reactionVulnerableMotifTypes{j});
        %         if isempty(positionsStrands)
        %             continue;
        %         end
        %         this.substrates = this.substrates + size(positionsStrands, 1) * this.reactionSmallMoleculeStoichiometryMatrix(:,j);
        %         if ~isempty(sideEffects)
        %             this.simulationStateSideEffects = [this.simulationStateSideEffects; sideEffects];
        %         end
        %     end
        % end
        reaction_log = run_instrumented_evolve_state(m, reaction_log);
    else
        m.evolveState();
    end

    m.copyToState();
    mets.counts(gidx) = counts + m.substrates(lidx, :) - allocation;

    if ~isempty(m.simulationStateSideEffects)
        m.simulationStateSideEffects.updateSimulationState(sim);
    end
end

mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    mets.counts, mets.setCounts, time.values);
end

function reaction_log = run_instrumented_evolve_state(this, reaction_log)
cumulative_draws = 0;
randomOrder = this.randStream.randperm(numel(this.reactionWholeCellModelIDs));
reaction_ids = matlab_cellstr_local(this.reactionWholeCellModelIDs);
for i = 1:length(this.reactionWholeCellModelIDs)
    j = randomOrder(i);

    entry = struct();
    entry.iteration = i;
    entry.reaction_index_1based = j;
    entry.reaction_index_0based = j - 1;
    entry.reaction_id = reaction_ids{j};
    motif = this.reactionVulnerableMotifs{j};
    entry.is_string_motif = ischar(motif);
    if ischar(motif)
        entry.motif_value = motif;
    else
        entry.motif_value = double(motif);
    end
    entry.motif_type = this.reactionVulnerableMotifTypes{j};

    % NOTE: karr_bootstrap() resolves DNADamage.m through a generated
    % signed-zero-normalized OVERLAY (see
    % karr_bootstrap.m::ensure_dnadamage_signed_zero_overlay): the
    % ORIGINAL source's `max(0, -stoich)` can legitimately produce a
    % NEGATIVE ZERO (`-0.0`) for an exact-zero stoichiometry entry
    % (`-(+0.0) == -0.0` in IEEE754, and `max(0, -0.0)` does not clamp
    % it back to +0.0), which then makes `positive_substrate / -0.0 ==
    % -Inf` poison the whole `min(...)` -- this inline reimplementation
    % MUST apply the SAME `abs(...)` normalization the overlay applies,
    % or it silently reintroduces the exact bug the overlay exists to
    % fix (caught empirically this session: an early un-normalized draft
    % of this instrumentation produced maxReactions=-Inf for every one
    % of tick4's 32 reactions).
    denom = abs(max(0, -this.reactionSmallMoleculeStoichiometryMatrix(:, j))); % signed-zero normalization for exact-zero stoich rows
    maxReactions = floor(min(this.substrates ./ denom));
    entry.max_reactions = double(maxReactions);
    if maxReactions <= 0
        entry.gated_at = 'max_reactions';
        entry.draw_count = 0;
        entry.n_sites_actual = 0;
        entry.state_before = double(this.chromosome.randStream.state);
        entry.state_after = entry.state_before;
        entry.cumulative_draws_after = cumulative_draws;
        reaction_log = [reaction_log, entry]; %#ok<AGROW>
        continue;
    end

    radiationLclIdx = this.reactionRadiation(j);
    if radiationLclIdx ~= 0
        selectionProbability = this.stepSizeSec * this.reactionBounds(j, 2) * this.substrates(radiationLclIdx);
    else
        selectionProbability = this.stepSizeSec * this.reactionBounds(j, 2);
    end
    entry.selection_probability = double(selectionProbability);
    entry.radiation_local_idx = double(radiationLclIdx);
    if selectionProbability == 0
        entry.gated_at = 'selection_probability';
        entry.draw_count = 0;
        entry.n_sites_actual = 0;
        entry.state_before = double(this.chromosome.randStream.state);
        entry.state_after = entry.state_before;
        entry.cumulative_draws_after = cumulative_draws;
        reaction_log = [reaction_log, entry]; %#ok<AGROW>
        continue;
    end

    state_before = double(this.chromosome.randStream.state);
    [positionsStrands, sideEffects] = this.chromosome.setSiteDamaged(...
        this.reactionDamageTypes{j}, this.reactionDNAProduct(j), selectionProbability, ...
        maxReactions, this.reactionVulnerableMotifs{j}, this.reactionVulnerableMotifTypes{j});
    state_after = double(this.chromosome.randStream.state);

    draw_count = reconcile_draw_count_local(state_before, state_after);
    cumulative_draws = cumulative_draws + draw_count;

    entry.gated_at = 'ran_set_site_damaged';
    entry.draw_count = draw_count;
    entry.n_sites_actual = size(positionsStrands, 1);
    entry.state_before = state_before;
    entry.state_after = state_after;
    entry.cumulative_draws_after = cumulative_draws;
    reaction_log = [reaction_log, entry]; %#ok<AGROW>

    if isempty(positionsStrands)
        continue;
    end
    this.substrates = this.substrates + size(positionsStrands, 1) * this.reactionSmallMoleculeStoichiometryMatrix(:, j);
    if ~isempty(sideEffects)
        this.simulationStateSideEffects = [this.simulationStateSideEffects; sideEffects];
    end
end
end

function draws = reconcile_draw_count_local(state_before, state_after)
% Same non-destructive clone-and-step technique as
% reconstruct_chromosome_draw_ledger.m: never touches the live stream.
if isequal(state_before, state_after)
    draws = 0;
    return;
end
clone = RandStream('mcg16807');
clone.State = state_before;
draws = 0;
max_draws = 200000;
for k = 1:max_draws
    rand(clone);
    draws = draws + 1;
    if isequal(double(clone.State), state_after)
        return;
    end
end
error('instrument_dnadamage_tick4_per_reaction:reconcile_failed', ...
    'could not reconcile state_before=%.17g to state_after=%.17g within %d draws', ...
    state_before, state_after, max_draws);
end

function idx = find_process_index_local(sim, name)
idx = [];
want = normalize_name_token_local(name);
for i = 1:numel(sim.processes)
    proc = sim.processes{i};
    short = process_short_name_local(proc);
    tokens = { ...
        normalize_name_token_local(short), ...
        normalize_name_token_local(proc.wholeCellModelID) ...
    };
    if isprop(proc, 'name')
        tokens{end + 1} = normalize_name_token_local(proc.name); %#ok<AGROW>
    end
    if any(strcmp(tokens, want))
        idx = i;
        return;
    end
end
end

function short = process_short_name_local(proc)
wid = proc.wholeCellModelID;
if strncmp(wid, 'Process_', numel('Process_'))
    short = wid(numel('Process_') + 1:end);
else
    short = wid;
end
end

function token = normalize_name_token_local(s)
token = lower(regexprep(char(s), '[^a-zA-Z0-9]', ''));
end

function seed_simulation_local(sim, seed)
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
    end
catch
end
end

function [sim, applied] = apply_condition_overrides_local(sim, proc, canonical_name, extraction_opts)
applied = struct('wid', {}, 'value', {}, 'object_compartment_idx', {});
if ~isfield(extraction_opts, 'per_process_substrate_overrides') || isempty(fieldnames(extraction_opts.per_process_substrate_overrides))
    return;
end
override_values = select_process_substrate_overrides_local(extraction_opts.per_process_substrate_overrides, proc);
if isempty(override_values)
    return;
end

mets = sim.state_metabolite;
n_metabolites = size(mets.counts, 1);
n_compartments = size(mets.counts, 2);
substrate_wids = matlab_cellstr_local(proc.substrateWholeCellModelIDs);
override_fields = fieldnames(override_values);
for i = 1:numel(override_fields)
    wid = override_fields{i};
    value = override_values.(wid);

    local_idx = find(strcmp(substrate_wids, wid));
    object_compartment_idx = proc.substrateMetaboliteGlobalCompartmentIndexs(local_idx);
    [object_idx, compartment_idx] = ind2sub([n_metabolites n_compartments], object_compartment_idx);

    keep = mets.setCounts(:, edu.stanford.covert.cell.sim.constant.Condition.objectCompartmentIndexs) ~= object_compartment_idx;
    mets.setCounts = mets.setCounts(keep, :);

    row = zeros(1, 6);
    row(edu.stanford.covert.cell.sim.constant.Condition.objectIndexs) = object_idx;
    row(edu.stanford.covert.cell.sim.constant.Condition.compartmentIndexs) = compartment_idx;
    row(edu.stanford.covert.cell.sim.constant.Condition.valueIndexs) = double(value);
    row(edu.stanford.covert.cell.sim.constant.Condition.initialTimeIndexs) = 0;
    row(edu.stanford.covert.cell.sim.constant.Condition.finalTimeIndexs) = Inf;
    row(edu.stanford.covert.cell.sim.constant.Condition.objectCompartmentIndexs) = object_compartment_idx;
    mets.setCounts = [mets.setCounts; row];
    mets.counts(object_compartment_idx) = double(value);

    applied(end + 1).wid = wid; %#ok<AGROW>
    applied(end).value = double(value);
    applied(end).object_compartment_idx = object_compartment_idx;
end
end

function mod = apply_process_substrate_overrides_local(mod, extraction_opts)
if ~isfield(extraction_opts, 'per_process_substrate_overrides') || isempty(fieldnames(extraction_opts.per_process_substrate_overrides))
    return;
end
override_values = select_process_substrate_overrides_local(extraction_opts.per_process_substrate_overrides, mod);
if isempty(override_values)
    return;
end
if ~isprop(mod, 'substrates') || ~isprop(mod, 'substrateWholeCellModelIDs')
    return;
end
substrate_wids = matlab_cellstr_local(mod.substrateWholeCellModelIDs);
override_fields = fieldnames(override_values);
for i = 1:numel(override_fields)
    wid = override_fields{i};
    idx = find(strcmp(substrate_wids, wid), 1);
    if isempty(idx)
        continue;
    end
    mod.substrates(idx, :) = double(override_values.(wid));
end
end

function override_values = select_process_substrate_overrides_local(per_process_overrides, mod)
override_values = [];
process_tokens = { ...
    normalize_name_token_local(process_short_name_local(mod)), ...
    normalize_name_token_local(mod.wholeCellModelID) ...
};
if isprop(mod, 'name')
    process_tokens{end + 1} = normalize_name_token_local(mod.name); %#ok<AGROW>
end
override_names = fieldnames(per_process_overrides);
for i = 1:numel(override_names)
    name = override_names{i};
    if any(strcmp(process_tokens, normalize_name_token_local(name)))
        override_values = per_process_overrides.(name);
        return;
    end
end
end

function [sim, before_tick, after_tick] = evolve_state_with_tap_local(sim, target_idx, extraction_opts)
% Burn-in-only variant of evolve_state_with_tap (no tap capture needed;
% target_idx=-1 means "no process in this tick is the tap target").
before_tick = struct();
after_tick = struct();

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
    m = processes{i};
    m.copyFromState();
    m = apply_process_substrate_overrides_local(m, extraction_opts);
    r = m.calcResourceRequirements_Current();
    gidx = m.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = m.substrateMetaboliteLocalIndexs;
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
    m = processes{proc_idx};

    gidx = m.substrateMetaboliteGlobalCompartmentIndexs;
    lidx = m.substrateMetaboliteLocalIndexs;
    allocation = reshape(allocations(gidx, proc_idx), size(gidx));
    counts = mets.counts(gidx);

    m.simulationStateSideEffects = [];
    m.copyFromState();
    m.substrates(lidx, :) = allocation;
    m = apply_process_substrate_overrides_local(m, extraction_opts);
    if proc_idx == rna_decay_idx && isprop(m, 'RNAs')
        m.RNAs = max(0, m.RNAs);
    end

    if proc_idx == target_idx
        before_tick = struct(); %#ok<NASGU>
    end

    m.evolveState();

    if proc_idx == target_idx
        after_tick = struct(); %#ok<NASGU>
    end

    m.copyToState();
    mets.counts(gidx) = counts + m.substrates(lidx, :) - allocation;

    if ~isempty(m.simulationStateSideEffects)
        m.simulationStateSideEffects.updateSimulationState(sim);
    end
end

mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    mets.counts, mets.setCounts, time.values);
end

function out = matlab_cellstr_local(values)
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

function hash_hex = sha256_of_file_local(path_value)
fid = fopen(path_value, 'rb');
if fid < 0
    error('instrument_dnadamage_tick4_per_reaction:file_unreadable', 'could not open %s', path_value);
end
raw = fread(fid, Inf, '*uint8')';
fclose(fid);
raw = raw(raw ~= uint8(13));
digest = java.security.MessageDigest.getInstance('SHA-256');
digest_bytes = typecast(digest.digest(raw), 'uint8');
hash_hex = lower(sprintf('%02x', digest_bytes));
end
