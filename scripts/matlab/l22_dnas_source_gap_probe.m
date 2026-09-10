function summary = l22_dnas_source_gap_probe(varargin)
% l22_dnas_source_gap_probe
% Focused live MATLAB microscope for the DNASupercoiling seed-0 / tick-5
% topoIV stable-binding source gap.
%
% This script advances the real allocator-correct scheduler to the target
% DNASupercoiling callsite, verifies that the live pre-call state matches the
% regenerated trace surface, then runs an instrumented copy of
% ChromosomeProcessAspect.bindProteinToChromosomeStochastically() on the real
% Karr objects to capture:
%   - legal dsDNA regions
%   - accessible regions from Chromosome.getAccessibleRegions()
%   - candidate-site counts
%   - sampled sites before bind post-checks
%   - bindProteinToChromosome() acceptance/rejection result
%
% Example:
%   addpath('scripts/matlab');
%   l22_dnas_source_gap_probe( ...
%       'seed', 0, ...
%       'tick_zero_based', 5, ...
%       'out_path', fullfile(pwd, 'tmp', 'l22_dnas_source_gap_probe.json'));

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
ensure_wholecell_runtime_paths(repo_root);
provided_out_path = false;
if mod(numel(varargin), 2) == 0
    key_args = varargin(1:2:end);
    provided_out_path = any(cellfun(@(x) ischar(x) || isstring(x), key_args) & strcmpi(string(key_args), "out_path"));
end
if isempty(opts.out_path) && ~provided_out_path
    opts.out_path = fullfile(repo_root, 'tmp', 'l22_dnas_source_gap_probe.json');
end

trace_path = opts.trace_path;
if isempty(trace_path)
    trace_path = default_trace_path(repo_root, opts.seed);
end
if ~exist(trace_path, 'file')
    error('l22_dnas_source_gap_probe:missingTrace', 'Trace file not found: %s', trace_path);
end

trace_data = load(trace_path, 'states_before', 'states_after', 'metadata');
target_tick_one_based = opts.tick_zero_based + 1;

sim = karr_bootstrap();
[target_idx, canonical_name] = find_process_index(sim, 'DNASupercoiling');
if isempty(target_idx)
    error('l22_dnas_source_gap_probe:missingProcess', 'DNASupercoiling not found in simulation');
end
seed_simulation(sim, uint32(opts.seed));

summary = run_probe(sim, target_idx, canonical_name, trace_data, opts, target_tick_one_based, trace_path);

if ~isempty(opts.out_path)
    out_dir = fileparts(opts.out_path);
    if ~isempty(out_dir) && ~exist(out_dir, 'dir')
        mkdir(out_dir);
    end
    fid = fopen(opts.out_path, 'w');
    if fid < 0
        error('l22_dnas_source_gap_probe:writeFailed', 'Could not open output path: %s', opts.out_path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(summary));
    fprintf('[l22_dnas_source_gap_probe] wrote %s\n', opts.out_path);

    slim_path = fullfile(out_dir, 'l22_dnas_corrected_rng_source_probe.json');
    slim = build_corrected_rng_slim_summary(summary);
    fid_slim = fopen(slim_path, 'w');
    if fid_slim < 0
        error('l22_dnas_source_gap_probe:writeSlimFailed', 'Could not open slim output path: %s', slim_path);
    end
    cleaner_slim = onCleanup(@() fclose(fid_slim)); %#ok<NASGU>
    fprintf(fid_slim, '%s', jsonencode(slim));
    fprintf('[l22_dnas_source_gap_probe] wrote %s\n', slim_path);
end
end

function summary = run_probe(sim, target_idx, canonical_name, trace_data, opts, target_tick_one_based, trace_path)
process_name = canonical_name;
snapshot_props = {'substrates', 'enzymes', 'boundEnzymes', 'chromosome'};

time = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;
processes = sim.processes;
nProcesses = numel(processes);
rna_decay_idx = sim.processIndex('RNADecay');

summary = struct();
pre_tick_rng_ledger = struct('tick_zero_based', {}, 'state_before_evolve', {});
for abs_tick = 1:target_tick_one_based
    time.values = time.values + sim.stepSizeSec;
    stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
        stim.values, stim.setValues, time.values);

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
            mod.RNAs = max(0, mod.RNAs);
        end

        if proc_idx == target_idx
            pre_tick_rng_ledger(end + 1) = struct( ... %#ok<AGROW>
                'tick_zero_based', int32(abs_tick - 1), ...
                'state_before_evolve', serialize_randstream_state(mod.randStream));
        end

        if proc_idx == target_idx && abs_tick == target_tick_one_based
            live_before = snapshot_from_process(mod, snapshot_props);
            trace_before = trace_tick_payload(trace_data.states_before, target_tick_one_based);
            prestate_match = compare_prestate_surface(live_before, trace_before);

            summary = instrument_topoiv_call( ...
                mod, ...
                processEvalOrderIndexs, ...
                i, ...
                abs_tick, ...
                opts.tick_zero_based, ...
                trace_path, ...
                process_name, ...
                live_before, ...
                trace_before, ...
                trace_data.states_after, ...
                prestate_match);
            summary.per_tick_process_rng_states_before_evolve = pre_tick_rng_ledger;
            return;
        end

        mod.evolveState();
        mod.copyToState();
        mets.counts(gidx) = counts + mod.substrates(lidx, :) - allocation;

        if ~isempty(mod.simulationStateSideEffects)
            mod.simulationStateSideEffects.updateSimulationState(sim);
        end
    end

    mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
        mets.counts, mets.setCounts, time.values);
end

error('l22_dnas_source_gap_probe:targetNotReached', ...
    'Failed to reach DNASupercoiling tick %d', target_tick_one_based);
end

function summary = instrument_topoiv_call(mod, process_order, order_position, abs_tick, tick_zero_based, trace_path, process_name, live_before, trace_before, states_after, prestate_match)
c = mod.chromosome;
topoiv_idx = mod.enzymeIndexs_topoIV;
gyrase_idx = mod.enzymeIndexs_gyrase;
enzProps = mod.enzymeProperties;

summary = struct();
summary.process_name = process_name;
summary.trace_path = trace_path;
summary.tick_zero_based = int32(tick_zero_based);
summary.tick_one_based = int32(abs_tick);
summary.scheduler_order = int32(process_order(:)');
summary.scheduler_order_position = int32(order_position);
summary.trace_prestate_match = prestate_match;

[tmpPosStrands, lengths] = find(c.doubleStrandedRegions);
tmpIdxs = find(builtin('mod', tmpPosStrands(:, 2), 2));
dsPosStrands = tmpPosStrands(tmpIdxs, :);
lengths = lengths(tmpIdxs, 1);

[~, linkingNumbers] = find(c.linkingNumbers);
linkingNumbers = linkingNumbers(tmpIdxs, 1);
sigmas = (linkingNumbers - lengths / c.relaxedBasesPerTurn) ./ (lengths / c.relaxedBasesPerTurn);

legal = [ ...
    sigmas > mod.gyraseSigmaLimit ...
    sigmas > mod.topoIVSigmaLimit ...
    sigmas < mod.topoISigmaLimit];

summary.legal_input = struct( ...
    'dsPosStrands', int32(dsPosStrands), ...
    'lengths', int32(lengths), ...
    'linkingNumbers', double(linkingNumbers), ...
    'sigmas', double(sigmas), ...
    'legal', logical(legal));

topoiv_before = struct( ...
    'free', double(mod.enzymes(topoiv_idx, 1)), ...
    'bound', double(mod.boundEnzymes(topoiv_idx, 1)), ...
    'bound_site_count', count_bound_enzyme_sites(c, mod, topoiv_idx));

summary.pre_activity_rng_segments = struct();
summary.pre_activity_rng_segments.state_before_release = serialize_randstream_state(mod.randStream);
summary.pre_activity_rng_segments.chromosome_state_before_release = serialize_randstream_state(c.randStream);

protectedPosStrands = dsPosStrands(legal(:, topoiv_idx), :);
protectedLengths = lengths(legal(:, topoiv_idx));
released_topoiv = mod.releaseProteinFromChromosome(topoiv_idx, Inf, protectedPosStrands, protectedLengths);
summary.pre_activity_rng_segments.state_after_topoiv_release = serialize_randstream_state(mod.randStream);
summary.pre_activity_rng_segments.chromosome_state_after_topoiv_release = serialize_randstream_state(c.randStream);
released_gyrase = mod.releaseProteinFromChromosome(gyrase_idx, 1 / mod.gyraseMeanDwellTime, [], []);
summary.pre_activity_rng_segments.state_after_gyrase_release = serialize_randstream_state(mod.randStream);
summary.pre_activity_rng_segments.chromosome_state_after_gyrase_release = serialize_randstream_state(c.randStream);

topoiv_after_release = struct( ...
    'free', double(mod.enzymes(topoiv_idx, 1)), ...
    'bound', double(mod.boundEnzymes(topoiv_idx, 1)), ...
    'bound_site_count', count_bound_enzyme_sites(c, mod, topoiv_idx));

summary.precall_release = struct( ...
    'topoiv_before', topoiv_before, ...
    'released_topoiv_positions', int32(released_topoiv), ...
    'released_gyrase_positions', int32(released_gyrase), ...
    'topoiv_after_release', topoiv_after_release);

summary.pre_activity_rng_segments.state_before_post_release_random_order = serialize_randstream_state(mod.randStream);
summary.pre_activity_rng_segments.chromosome_state_before_post_release_random_order = serialize_randstream_state(c.randStream);
order = mod.randStream.randperm(length(mod.enzymes));
summary.post_release_random_order = int32(order(:)');
summary.pre_activity_rng_segments.state_after_post_release_random_order = serialize_randstream_state(mod.randStream);
summary.pre_activity_rng_segments.chromosome_state_after_post_release_random_order = serialize_randstream_state(c.randStream);

transientlyBinding = zeros(size(legal));
prior_rng_events = {};
topoiv_probe = struct('called', false);
stable_binding_segments = {};

for i = 1:length(order)
    j = order(i);
    if enzProps(j).meanDwellTime == 0
        [transientlyBinding(:, j), event_note] = compute_transient_binding_branch(mod, c, legal, dsPosStrands, lengths, j);
        if ~isempty(event_note)
            prior_rng_events{end + 1, 1} = event_note; %#ok<AGROW>
        end
    elseif any(legal(:, j))
        if j == topoiv_idx
            topoiv_probe = instrumented_bind_protein_to_chromosome_stochastically( ...
                mod, ...
                j, ...
                [], ...
                dsPosStrands(legal(:, j), :), ...
                lengths(legal(:, j)), ...
                false);
            topoiv_probe.called = true;
            topoiv_probe.order_position = int32(i);
            topoiv_probe.legal_regions = int32(dsPosStrands(legal(:, j), :));
            topoiv_probe.legal_lengths = int32(lengths(legal(:, j)));
            topoiv_probe.free_before_call = double(mod.enzymes(j, 1));
            topoiv_probe.bound_before_call = double(mod.boundEnzymes(j, 1));
            break;
        else
            bound_positions_before = bound_enzyme_positions(c, mod, j);
            segment = struct();
            segment.order_position = int32(i);
            segment.enzyme_index = int32(j);
            segment.enzyme_wid = mod.enzymeWholeCellModelIDs{j};
            segment.legal_regions = int32(dsPosStrands(legal(:, j), :));
            segment.legal_lengths = int32(lengths(legal(:, j)));
            segment.free_before_call = double(mod.enzymes(j, 1));
            segment.bound_before_call = double(mod.boundEnzymes(j, 1));
            segment.bound_positions_before = int32(bound_positions_before);
            segment.randstream_state_before = serialize_randstream_state(mod.randStream);
            mod.bindProteinToChromosomeStochastically( ...
                j, [], dsPosStrands(legal(:, j), :), lengths(legal(:, j)));
            bound_positions_after = bound_enzyme_positions(c, mod, j);
            segment.free_after_call = double(mod.enzymes(j, 1));
            segment.bound_after_call = double(mod.boundEnzymes(j, 1));
            segment.bound_positions_after = int32(bound_positions_after);
            segment.new_bound_positions = int32(setdiff(double(bound_positions_after), double(bound_positions_before), 'rows'));
            segment.randstream_state_after = serialize_randstream_state(mod.randStream);
            stable_binding_segments{end + 1, 1} = segment; %#ok<AGROW>
        end
    end
end

summary.prior_rng_events = prior_rng_events;
summary.pre_activity_rng_segments.stable_binding_segments = {stable_binding_segments};
summary.transientlyBinding = double(transientlyBinding);
summary.topoiv_call = topoiv_probe;
summary.after_topoiv_probe = struct( ...
    'free', double(mod.enzymes(topoiv_idx, 1)), ...
    'bound', double(mod.boundEnzymes(topoiv_idx, 1)), ...
    'bound_site_count', count_bound_enzyme_sites(c, mod, topoiv_idx), ...
    'complexBoundSites', compact_sparse_field(serialize_chromosome_state(c).complexBoundSites));
summary.major_region_activity = instrument_major_region_activity( ...
    mod, dsPosStrands, lengths, linkingNumbers, sigmas, legal, transientlyBinding, enzProps);

trace_after = trace_tick_payload(states_after, abs_tick);
summary.trace_after = struct( ...
    'topoiv_free', double(trace_after.enzymes(topoiv_idx, 1)), ...
    'topoiv_bound', double(trace_after.boundEnzymes(topoiv_idx, 1)), ...
    'complexBoundSites', compact_sparse_field(trace_after.chromosome.complexBoundSites), ...
    'major_region_linking_value', double(trace_linking_value_for_region( ...
        trace_after.chromosome.linkingNumbers, ...
        summary.major_region_activity.region_start, ...
        summary.major_region_activity.region_strand)));
summary.live_before = minimal_state_view(live_before, topoiv_idx);
summary.trace_before = minimal_state_view(trace_before, topoiv_idx);
end

function [values, event_note] = compute_transient_binding_branch(mod, c, legal, dsPosStrands, lengths, j)
event_note = [];
values = zeros(size(lengths));
if numel(lengths) == 1 && lengths == c.sequenceLen
    [~, mons] = find(c.monomerBoundSites);
    [~, cpxs] = find(c.complexBoundSites);
    space = lengths ...
        - sum(c.monomerDNAFootprints(mons, 1)) ...
        - sum(c.complexDNAFootprints(cpxs, 1)) ...
        - nnz(c.damagedSites);
    values(1, 1) = min(mod.enzymes(j, 1), space / mod.enzymeDNAFootprints(j, 1));
elseif numel(lengths) == 2 && all(lengths == c.sequenceLen)
    [monPosStrnds, mons] = find(c.monomerBoundSites);
    [cpxPosStrnds, cpxs] = find(c.complexBoundSites);
    space = zeros(2, 1);
    space(1) = lengths(1) ...
        - sum(c.monomerDNAFootprints(mons(monPosStrnds(:, 2) <= 2), 1)) ...
        - sum(c.complexDNAFootprints(cpxs(cpxPosStrnds(:, 2) <= 2), 1)) ...
        - nnz(c.damagedSites(:, 1:2));
    space(2) = lengths(2) ...
        - sum(c.monomerDNAFootprints(mons(monPosStrnds(:, 2) > 2), 1)) ...
        - sum(c.complexDNAFootprints(cpxs(cpxPosStrnds(:, 2) > 2), 1)) ...
        - nnz(c.damagedSites(:, 3:4));
    values = min(mod.enzymes(j, 1), sum(space) / mod.enzymeDNAFootprints(j, 1)) * ...
        space / sum(space);
    draw = mod.randStream.rand;
    if draw < 0.5
        values(1, 1) = edu.stanford.covert.util.ComputationUtil.roundHalfUp(values(1, 1));
        values(2, 1) = edu.stanford.covert.util.ComputationUtil.roundHalfDown(values(2, 1));
    else
        values(2, 1) = edu.stanford.covert.util.ComputationUtil.roundHalfUp(values(2, 1));
        values(1, 1) = edu.stanford.covert.util.ComputationUtil.roundHalfDown(values(1, 1));
    end
    event_note = struct('enzyme_index', int32(j), 'round_half_draw', double(draw));
else
    [monPosStrnds, mons] = find(c.monomerBoundSites);
    [cmpPosStrnds, cmps] = find(c.complexBoundSites);
    dmgPosStrnds = find(c.damagedSites);
    monPos = monPosStrnds(:, 1);
    cmpPos = cmpPosStrnds(:, 1);
    dmgPos = dmgPosStrnds(:, 1);
    monChrs = ceil(monPosStrnds(:, 2) / 2);
    cmpChrs = ceil(cmpPosStrnds(:, 2) / 2);
    dmgChrs = ceil(dmgPosStrnds(:, 2) / 2);

    space = zeros(size(lengths));
    for k = 1:numel(lengths)
        if ~legal(k, j)
            continue;
        end

        monTfs = monPos >= dsPosStrands(k, 1) & monPos <= dsPosStrands(k, 1) + lengths(k, 1) - 1;
        cmpTfs = cmpPos >= dsPosStrands(k, 1) & cmpPos <= dsPosStrands(k, 1) + lengths(k, 1) - 1;
        dmgTfs = dmgPos >= dsPosStrands(k, 1) & dmgPos <= dsPosStrands(k, 1) + lengths(k, 1) - 1;
        monTfs(monTfs) = monChrs(monTfs, 1) == dsPosStrands(k, 2);
        cmpTfs(cmpTfs) = cmpChrs(cmpTfs, 1) == dsPosStrands(k, 2);
        dmgTfs(dmgTfs) = dmgChrs(dmgTfs, 1) == dsPosStrands(k, 2);

        space(k, 1) = ...
            + lengths(k, 1) ...
            - sum(c.monomerDNAFootprints(mons(monTfs, 1), 1)) ...
            - sum(c.monomerDNAFootprints(cmps(cmpTfs, 1), 1)) ...
            - sum(dmgTfs);
    end

    if numel(lengths) == 1
        values(:, 1) = min(mod.enzymes(j, 1), space / mod.enzymeDNAFootprints(j, 1));
    else
        values(:, 1) = space / sum(space) * min(mod.enzymes(j, 1), sum(space) / mod.enzymeDNAFootprints(j, 1));
    end
end
end

function probe = instrumented_bind_protein_to_chromosome_stochastically(mod, enzymeIndex, nProteins, positionsStrands, lengths, checkRegionSupercoiled)
if nargin < 3 || isempty(nProteins)
    nProteins = mod.enzymes(enzymeIndex);
end
if nargin < 6
    checkRegionSupercoiled = false;
end

c = mod.chromosome;
footprint = mod.enzymeDNAFootprints(enzymeIndex);

probe = struct();
probe.enzyme_index = int32(enzymeIndex);
probe.enzyme_wid = mod.enzymeWholeCellModelIDs{enzymeIndex};
probe.nProteins_input = double(nProteins);
probe.footprint = double(footprint);
probe.positionsStrands_input = int32(positionsStrands);
probe.lengths_input = int32(lengths);

tf = ismembc(enzymeIndex, mod.enzymeMonomerLocalIndexs);
[rgnPosStrnds, rgnLens] = c.getAccessibleRegions( ...
    mod.enzymeGlobalIndexs(enzymeIndex(tf, 1), 1), ...
    mod.enzymeGlobalIndexs(enzymeIndex(~tf, 1), 1), ...
    checkRegionSupercoiled);
[rgnPosStrnds, rgnLens] = c.intersectRegions( ...
    rgnPosStrnds, rgnLens, positionsStrands, lengths);

probe.accessible_regions = int32(rgnPosStrnds);
probe.accessible_lengths = int32(rgnLens);
probe.candidate_site_count = int32(sum(max(0, rgnLens - footprint + 1)));
probe.region_weights_initial = double(max(0, rgnLens - footprint + 1));

rgnProbs = max(0, rgnLens - footprint + 1);
posStrnds = zeros(nProteins, 2);
nBound = 0;
sample_log = cell(max(1, nProteins), 1);
region_snapshots = cell(max(1, nProteins), 1);

for i = 1:nProteins
    if ~any(rgnProbs)
        break;
    end

    region_snapshots{i} = struct( ...
        'positionsStrands', int32(rgnPosStrnds), ...
        'lengths', int32(rgnLens), ...
        'weights', double(rgnProbs));
    rgnIdx = mod.randStream.randsample(numel(rgnProbs), 1, true, rgnProbs);
    randReal = mod.randStream.rand;
    offset = ceil(randReal * (rgnLens(rgnIdx) - footprint + 1)) - 1;
    posStrnds(i, :) = rgnPosStrnds(rgnIdx, :) + [offset 0];

    sample_log{i} = struct( ...
        'sample_index', int32(i), ...
        'region_index', int32(rgnIdx), ...
        'rand_real', double(randReal), ...
        'offset_zero_based', int32(offset), ...
        'sampled_position_strand', int32(posStrnds(i, :)), ...
        'region_before', int32(rgnPosStrnds(rgnIdx, :)), ...
        'region_length_before', int32(rgnLens(rgnIdx)));

    rgnPosStrnds(end + 1, :) = [ ...
        rgnPosStrnds(rgnIdx, 1) + offset + footprint, rgnPosStrnds(rgnIdx, 2)];
    rgnLens(end + 1) = rgnLens(rgnIdx) - offset - footprint;
    rgnLens(rgnIdx) = offset;
    rgnProbs([rgnIdx end + 1]) = max(0, rgnLens([rgnIdx end]) - footprint + 1);
    nBound = nBound + 1;
end

sample_log = sample_log(1:nBound);
region_snapshots = region_snapshots(1:nBound);
posStrnds = posStrnds(1:nBound, :);

probe.sampling = struct( ...
    'nBound_pre_bind', int32(nBound), ...
    'sample_log', {sample_log}, ...
    'region_snapshots', {region_snapshots}, ...
    'sampled_position_strands', int32(posStrnds));

if nBound == 0
    probe.bind_result = struct( ...
        'tfs', false(0, 1), ...
        'idxs', int32([]), ...
        'accepted_positionsStrands', int32(zeros(0, 2)), ...
        'accepted_lengths', int32([]), ...
        'maxBindings_after', int32(0), ...
        'processivityLengths', int32([]), ...
        'all_tfs', true);
    return;
end

[tfs, idxs, acceptedPosStrnds, maxBindingsAfter, processivityLengths] = mod.bindProteinToChromosome( ...
    posStrnds, enzymeIndex, nBound, [], [], false, 1, false, [], checkRegionSupercoiled);

probe.bind_result = struct( ...
    'tfs', logical(tfs), ...
    'idxs', int32(idxs), ...
    'accepted_positionsStrands', int32(acceptedPosStrnds), ...
    'accepted_lengths', int32(processivityLengths), ...
    'maxBindings_after', int32(maxBindingsAfter), ...
    'processivityLengths', int32(processivityLengths), ...
    'all_tfs', all(tfs));
end

function ledger = instrument_major_region_activity(mod, dsPosStrands, lengths, linkingNumbers, sigmas, legal, transientlyBinding, enzProps)
c = mod.chromosome;
ledger = struct();
ledger.randstream_state_before_activity_order = serialize_randstream_state(mod.randStream);
[~, majorIdx] = max(lengths);
majorIdx = majorIdx(1);
activityOrder = mod.randStream.randperm(length(enzProps));
ledger.randstream_state_after_activity_order = serialize_randstream_state(mod.randStream);
activityProps = enzProps(activityOrder);

ledger.region_index_one_based = int32(majorIdx);
ledger.region_start = int32(dsPosStrands(majorIdx, 1));
ledger.region_strand = int32(dsPosStrands(majorIdx, 2));
ledger.region_length = int32(lengths(majorIdx, 1));
ledger.sigma_before = double(sigmas(majorIdx, 1));
ledger.linking_before = double(linkingNumbers(majorIdx, 1));
ledger.activity_order = int32([activityProps.idx]);
ledger.activity_order_wids = cellfun( ...
    @(idx) mod.enzymeWholeCellModelIDs{idx}, ...
    num2cell([activityProps.idx]), ...
    'UniformOutput', false);
ledger.substrates_before = tracked_substrates_snapshot(mod);

stepLog = cell(length(activityProps), 1);
currentLinking = double(linkingNumbers(majorIdx, 1));

for j = 1:length(activityProps)
    prop = activityProps(j);
    enzymeIdx = prop.idx;
    step = struct();
    step.order_position = int32(j);
    step.enzyme_index = int32(enzymeIdx);
    step.enzyme_wid = mod.enzymeWholeCellModelIDs{enzymeIdx};
    step.legal = logical(legal(majorIdx, enzymeIdx));
    step.linking_before = double(currentLinking);
    step.substrates_before = tracked_substrates_snapshot(mod);

    if ~step.legal
        step.nBound = double(0);
        step.probOfActivity = double(0);
        step.expected_activity = double(0);
        step.stochastic_round_result = double(0);
        step.atp_event_caps = [double(0); double(0)];
        step.nStrandPassingEvents = double(0);
        step.deltaLK_per_event = double(prop.deltaLK);
        step.delta_linking_number = double(0);
        step.linking_after = double(currentLinking);
        step.substrates_after = tracked_substrates_snapshot(mod);
        stepLog{j} = step;
        continue;
    end

    if prop.meanDwellTime == 0
        nBound = transientlyBinding(majorIdx, enzymeIdx);
    else
        nBound = size(mod.findProteinInRegion( ...
            dsPosStrands(majorIdx, 1), dsPosStrands(majorIdx, 2), lengths(majorIdx, 1), enzymeIdx), 1);
    end
    probOfActivity = prop.probOfActivityFunc(sigmas(majorIdx, 1), c);
    expectedActivity = nBound * prop.activityRate * probOfActivity;
    [stochasticRoundResult, stochasticRoundDraw, stochasticRoundFrac] = ...
        stochastic_round_scalar(mod.randStream, expectedActivity);
    if prop.atpCost == 0
        atpEventCaps = [Inf; Inf];
    else
        atpEventCaps = fix(mod.substrates([mod.substrateIndexs_atp; mod.substrateIndexs_water]) / prop.atpCost);
    end
    nStrandPassingEvents = min([stochasticRoundResult; atpEventCaps]);
    deltaLinking = prop.deltaLK * nStrandPassingEvents;
    currentLinking = currentLinking + deltaLinking;

    nATP = nStrandPassingEvents * prop.atpCost;
    mod.substrates(mod.substrateIndexs_atp)       = mod.substrates(mod.substrateIndexs_atp)       - nATP;
    mod.substrates(mod.substrateIndexs_water)     = mod.substrates(mod.substrateIndexs_water)     - nATP;
    mod.substrates(mod.substrateIndexs_adp)       = mod.substrates(mod.substrateIndexs_adp)       + nATP;
    mod.substrates(mod.substrateIndexs_phosphate) = mod.substrates(mod.substrateIndexs_phosphate) + nATP;
    mod.substrates(mod.substrateIndexs_hydrogen)  = mod.substrates(mod.substrateIndexs_hydrogen)  + nATP;

    step.nBound = double(nBound);
    step.probOfActivity = double(probOfActivity);
    step.expected_activity = double(expectedActivity);
    step.stochastic_round_draw = double(stochasticRoundDraw);
    step.stochastic_round_fraction = double(stochasticRoundFrac);
    step.stochastic_round_result = double(stochasticRoundResult);
    step.atp_event_caps = double(atpEventCaps);
    step.nStrandPassingEvents = double(nStrandPassingEvents);
    step.deltaLK_per_event = double(prop.deltaLK);
    step.delta_linking_number = double(deltaLinking);
    step.linking_after = double(currentLinking);
    step.substrates_after = tracked_substrates_snapshot(mod);
    stepLog{j} = step;
end

ledger.steps = {stepLog};
ledger.final_writeback_value = double(currentLinking);
ledger.substrates_after = tracked_substrates_snapshot(mod);
end

function state = serialize_randstream_state(randStream)
state = struct();
try
    raw = randStream.state;
catch
    raw = [];
end
state.values = double(raw(:)');
state.length = int32(numel(raw));
end

function [rounded, draw, frac] = stochastic_round_scalar(randStream, value)
draw = double(rand(randStream, size(value)));
frac = double(mod(value, 1));
rounded = floor(value);
if draw < frac
    rounded = ceil(value);
end
end

function tracked = tracked_substrates_snapshot(mod)
tracked = struct( ...
    'ATP', double(mod.substrates(mod.substrateIndexs_atp, 1)), ...
    'H2O', double(mod.substrates(mod.substrateIndexs_water, 1)), ...
    'ADP', double(mod.substrates(mod.substrateIndexs_adp, 1)), ...
    'PI', double(mod.substrates(mod.substrateIndexs_phosphate, 1)), ...
    'H', double(mod.substrates(mod.substrateIndexs_hydrogen, 1)));
end

function value = trace_linking_value_for_region(field_payload, start, strand)
value = NaN;
if isempty(field_payload)
    return;
end
positions = [];
strands = [];
values = [];
if isfield(field_payload, 'positions')
    positions = double(field_payload.positions(:));
end
if isfield(field_payload, 'strands')
    strands = double(field_payload.strands(:));
end
if isfield(field_payload, 'values')
    values = double(field_payload.values(:));
end
if isempty(positions) || isempty(strands) || isempty(values)
    return;
end
idx = find(positions == double(start) & strands == double(strand), 1, 'first');
if isempty(idx)
    return;
end
value = double(values(idx, 1));
end

function count = count_bound_enzyme_sites(c, mod, enzymeIndex)
enzymeGlobalIndex = mod.enzymeGlobalIndexs(enzymeIndex);
if any(mod.enzymeMonomerLocalIndexs == enzymeIndex)
    [~, vals] = find(c.monomerBoundSites);
else
    [~, vals] = find(c.complexBoundSites);
end
count = double(sum(vals == enzymeGlobalIndex));
end

function posStrnds = bound_enzyme_positions(c, mod, enzymeIndex)
enzymeGlobalIndex = mod.enzymeGlobalIndexs(enzymeIndex);
if any(mod.enzymeMonomerLocalIndexs == enzymeIndex)
    [posStrnds, vals] = find(c.monomerBoundSites);
else
    [posStrnds, vals] = find(c.complexBoundSites);
end
if isempty(posStrnds)
    posStrnds = zeros(0, 2, 'int32');
    return;
end
tf = vals == enzymeGlobalIndex;
posStrnds = int32(posStrnds(tf, :));
end

function slim = build_corrected_rng_slim_summary(summary)
slim = struct();
slim.tick_zero_based = summary.tick_zero_based;
slim.tick_one_based = summary.tick_one_based;
slim.post_release_random_order = summary.post_release_random_order;
if isfield(summary, 'pre_activity_rng_segments') && ~isempty(summary.pre_activity_rng_segments)
    seg = summary.pre_activity_rng_segments;
    stable_segments = struct([]);
    if isfield(seg, 'stable_binding_segments') && ~isempty(seg.stable_binding_segments)
        stable_segments = [seg.stable_binding_segments{:}];
    end
    slim.pre_activity_rng_segments = struct( ...
        'state_before_release', extract_randstream_values(seg, 'state_before_release'), ...
        'chromosome_state_before_release', extract_randstream_values(seg, 'chromosome_state_before_release'), ...
        'state_after_topoiv_release', extract_randstream_values(seg, 'state_after_topoiv_release'), ...
        'chromosome_state_after_topoiv_release', extract_randstream_values(seg, 'chromosome_state_after_topoiv_release'), ...
        'state_after_gyrase_release', extract_randstream_values(seg, 'state_after_gyrase_release'), ...
        'chromosome_state_after_gyrase_release', extract_randstream_values(seg, 'chromosome_state_after_gyrase_release'), ...
        'state_before_post_release_random_order', extract_randstream_values(seg, 'state_before_post_release_random_order'), ...
        'chromosome_state_before_post_release_random_order', extract_randstream_values(seg, 'chromosome_state_before_post_release_random_order'), ...
        'state_after_post_release_random_order', extract_randstream_values(seg, 'state_after_post_release_random_order'), ...
        'chromosome_state_after_post_release_random_order', extract_randstream_values(seg, 'chromosome_state_after_post_release_random_order'), ...
        'stable_binding_segments', stable_segments);
    slim.stable_binding_segments = stable_segments;
else
    slim.pre_activity_rng_segments = struct();
    slim.stable_binding_segments = struct([]);
end
major = summary.major_region_activity;
slim.major_region_activity = struct( ...
    'state_before_activity_order', extract_randstream_values(major, 'randstream_state_before_activity_order'), ...
    'state_after_activity_order', extract_randstream_values(major, 'randstream_state_after_activity_order'), ...
    'activity_order', major.activity_order, ...
    'activity_order_wids', {major.activity_order_wids}, ...
    'gyrase_draw', extract_step_field(major.steps{1}, 1, 'stochastic_round_draw'), ...
    'topoi_draw', extract_step_field(major.steps{1}, 3, 'stochastic_round_draw'), ...
    'final_writeback_value', major.final_writeback_value);
end

function values = extract_randstream_values(container, field_name)
values = [];
if ~isfield(container, field_name)
    return;
end
field_value = container.(field_name);
if isempty(field_value)
    return;
end
if isstruct(field_value) && isfield(field_value, 'values')
    values = double(field_value.values);
end
end

function value = extract_step_field(step_cell, idx, field_name)
value = [];
if isempty(step_cell) || numel(step_cell) < idx
    return;
end
step = step_cell{idx};
if isstruct(step) && isfield(step, field_name)
    value = step.(field_name);
end
end

function payload = trace_tick_payload(state_struct, tick_one_based)
payload = struct();
payload.substrates = state_struct.substrates{tick_one_based, 1};
payload.enzymes = state_struct.enzymes{tick_one_based, 1};
payload.boundEnzymes = state_struct.boundEnzymes{tick_one_based, 1};
payload.chromosome = state_struct.chromosome{tick_one_based, 1};
end

function comparison = compare_prestate_surface(live_before, trace_before)
comparison = struct();
comparison.substrates_match = isequaln(live_before.substrates, trace_before.substrates);
comparison.enzymes_match = isequaln(live_before.enzymes, trace_before.enzymes);
comparison.boundEnzymes_match = isequaln(live_before.boundEnzymes, trace_before.boundEnzymes);

live_chrom = live_before.chromosome;
trace_chrom = trace_before.chromosome;
all_fields = unique([fieldnames(live_chrom); fieldnames(trace_chrom)]);
field_checks = cell(numel(all_fields), 1);
all_match = comparison.substrates_match && comparison.enzymes_match && comparison.boundEnzymes_match;

for i = 1:numel(all_fields)
    fn = all_fields{i};
    live_has = isfield(live_chrom, fn);
    trace_has = isfield(trace_chrom, fn);
    item = struct('field', fn, 'live_has', live_has, 'trace_has', trace_has, 'match', false);
    if live_has && trace_has
        item.match = isequaln(live_chrom.(fn), trace_chrom.(fn));
    end
    all_match = all_match && item.match;
    field_checks{i} = item;
end

comparison.chromosome_field_checks = {field_checks};
comparison.all_match = all_match;
end

function view = minimal_state_view(payload, topoiv_idx)
view = struct( ...
    'substrates_nnz', int32(nnz(payload.substrates)), ...
    'topoiv_free', double(payload.enzymes(topoiv_idx, 1)), ...
    'topoiv_bound', double(payload.boundEnzymes(topoiv_idx, 1)), ...
    'complexBoundSites', compact_sparse_field(payload.chromosome.complexBoundSites), ...
    'damagedSites', compact_sparse_field_or_empty(payload.chromosome, 'damagedSites'), ...
    'doubleStrandedRegions', compact_sparse_field_or_empty(payload.chromosome, 'doubleStrandedRegions'));
end

function out = compact_sparse_field_or_empty(chrom_payload, field_name)
if isfield(chrom_payload, field_name)
    out = compact_sparse_field(chrom_payload.(field_name));
else
    out = struct('present', false);
end
end

function out = compact_sparse_field(field_payload)
out = struct('present', true);
if isempty(field_payload)
    out.positions = int32([]);
    out.strands = int32([]);
    out.values = [];
    out.shape = int32([]);
    return;
end
if isfield(field_payload, 'positions')
    out.positions = int32(field_payload.positions(:)');
else
    out.positions = int32([]);
end
if isfield(field_payload, 'strands')
    out.strands = int32(field_payload.strands(:)');
else
    out.strands = int32([]);
end
if isfield(field_payload, 'values')
    out.values = field_payload.values(:)';
else
    out.values = [];
end
if isfield(field_payload, 'shape')
    out.shape = int32(field_payload.shape(:)');
else
    out.shape = int32([]);
end
if isfield(field_payload, 'error')
    out.error = field_payload.error;
else
    out.error = '';
end
end

function out = snapshot_from_process(proc, snapshot_props)
out = struct();
for p = 1:numel(snapshot_props)
    prop = snapshot_props{p};
    out.(prop) = sanitize_snapshot_value(proc.(prop), 0);
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
    if strcmp(cls, 'edu.stanford.covert.cell.sim.state.Chromosome')
        out = serialize_chromosome_state(v);
        return;
    end
    out = sprintf('<object:%s>', cls);
    return;
end

out = sprintf('<unsupported:%s>', class(v));
end

function opts = parse_inputs(varargin)
opts = struct( ...
    'seed', 0, ...
    'tick_zero_based', 5, ...
    'trace_path', '', ...
    'out_path', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_source_gap_probe:invalidArgs', 'Arguments must be name/value pairs');
end

for i = 1:2:numel(varargin)
    name = varargin{i};
    value = varargin{i + 1};
    switch lower(char(name))
        case 'seed'
            opts.seed = double(value);
        case 'tick_zero_based'
            opts.tick_zero_based = double(value);
        case 'trace_path'
            opts.trace_path = char(value);
        case 'out_path'
            opts.out_path = char(value);
        otherwise
            error('l22_dnas_source_gap_probe:unknownOption', 'Unknown option: %s', char(name));
    end
end
end

function repo_root = infer_repo_root()
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
end

function trace_path = default_trace_path(repo_root, seed)
if seed == 0
    subdir = 'per_process_traces_v2';
else
    subdir = sprintf('per_process_traces_v2_s%03d', seed);
end
trace_path = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', subdir, 'DNASupercoiling_100ticks.mat');
if exist(trace_path, 'file')
    return;
end
fallback_root = 'E:\opencell\data\m1_sources\karr_native';
trace_path = fullfile(fallback_root, subdir, 'DNASupercoiling_100ticks.mat');
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

function [idx, canonical_name] = find_process_index(sim, requested_name)
idx = [];
canonical_name = '';
want = normalize_name_token(requested_name);

for i = 1:numel(sim.processes)
    proc = sim.processes{i};
    short = process_short_name(proc);
    tokens = { ...
        normalize_name_token(short), ...
        normalize_name_token(proc.wholeCellModelID)};
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
    'E:\opencell\data\m1_sources\WholeCell'};

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
    if exist('setPreferences.m', 'file') == 2
        try
            setPreferences();
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
