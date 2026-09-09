function summary = l22_dnas_full_bind_activity_probe(varargin)
% l22_dnas_full_bind_activity_probe
%
% Narrow, seed/tick-scoped diagnostic (standalone; does not modify any
% shared MATLAB source file). Built to root-cause the Opus-reviewed
% audit-boundary breach at seed=0, tick_zero_based=81 (OC process-owned
% RNG consumption = 35 draws vs the independently-recorded real MATLAB
% run's 19 draws for this tick -- STATUS_L22_DNAS_SEPT2.md /
% tmp/probe_oc_full_call_trace_seed0_tick81.json).
%
% Reuses the EXACT same real, full-process scheduler loop as
% scripts/matlab/l22_dnas_chromosome_release_rng_ledger.m and
% scripts/matlab/l22_dnas_release_call_probe.m (copyFromState,
% allocation, RNA-decay guard, real per-tick process order via
% rand_stream.randperm, evolveState, copyToState -- verbatim structure),
% but at the target process's own turn on the target tick, additionally
% captures LIVE (i.e. at the exact instant DNASupercoiling's own turn
% starts within that tick's real randomized process-evaluation order --
% NOT the tick-start states_before trace snapshot every other diagnostic
% in this wave used) the free/bound enzyme counts for gyrase, topoIV,
% and topoI, plus complexBoundSites for topoIV/gyrase before and after
% the real evolveState() call, plus the reconstructed process_draws
% sequence (same replay-forward method already relied on throughout this
% project, never a reimplemented mcg16807 formula).
%
% Example:
%   addpath('scripts/matlab');
%   l22_dnas_full_bind_activity_probe('seed', 0, 'target_tick_zero_based', 81, ...
%       'out_path', fullfile(pwd, 'tmp', 'l22_dnas_full_bind_activity_probe_s000_t081.json'));

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
ensure_wholecell_runtime_paths(repo_root);

sim = karr_bootstrap();
[target_idx, canonical_name] = find_process_index(sim, 'DNASupercoiling');
if isempty(target_idx)
    error('l22_dnas_full_bind_activity_probe:missingProcess', 'DNASupercoiling not found in simulation');
end
seed_simulation(sim, uint32(opts.seed));

summary = run_probe(sim, target_idx, canonical_name, opts);

if ~isempty(opts.out_path)
    out_dir = fileparts(opts.out_path);
    if ~isempty(out_dir) && ~exist(out_dir, 'dir')
        mkdir(out_dir);
    end
    fid = fopen(opts.out_path, 'w');
    if fid < 0
        error('l22_dnas_full_bind_activity_probe:writeFailed', 'Could not open output path: %s', opts.out_path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(summary));
    fprintf('[l22_dnas_full_bind_activity_probe] wrote %s\n', opts.out_path);
end
end

function summary = run_probe(sim, target_idx, canonical_name, opts)
time = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;
processes = sim.processes;
nProcesses = numel(processes);
rna_decay_idx = sim.processIndex('RNADecay');

target_abs_tick = opts.target_tick_zero_based + 1;
n_ticks = target_abs_tick;

summary = struct();
summary.seed = int32(opts.seed);
summary.process_name = canonical_name;
summary.target_tick_zero_based = int32(opts.target_tick_zero_based);
summary.captured = false;

for abs_tick = 1:n_ticks
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

    is_target_tick = (abs_tick == target_abs_tick);

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

        is_target = is_target_tick && (proc_idx == target_idx);
        if is_target
            summary.process_eval_order_position = int32(i);
            summary.process_eval_order = int32(processEvalOrderIndexs);

            gyrase_gidx = int64(mod.enzymeGlobalIndexs(mod.enzymeIndexs_gyrase));
            topoiv_gidx = int64(mod.enzymeGlobalIndexs(mod.enzymeIndexs_topoIV));
            topoi_gidx = int64(mod.enzymeGlobalIndexs(mod.enzymeIndexs_topoI));

            summary.live_free_bound_before = capture_free_bound_counts(mod);
            summary.live_before_bound_sites = capture_complex_bound_sites(mod.chromosome, gyrase_gidx, topoiv_gidx, topoi_gidx);
            summary.live_region_occupancy_before = capture_region_occupancy( ...
                mod.chromosome, opts.probe_region_start, opts.probe_region_len);

            % Read-only reproduction of DNASupercoiling.m's own legality +
            % accessible-region computation for topoIV, computed BEFORE
            % evolveState() runs (never mutates state; safe to call
            % immediately before the real evolveState() call that follows).
            summary.topoiv_accessible_region_probe = capture_topoiv_accessible_regions(mod, topoiv_gidx);

            chrom_state_before = serialize_randstream_state(mod.chromosome.randStream);
            proc_state_before = serialize_randstream_state(mod.randStream);
        end

        mod.evolveState();

        if is_target
            chrom_state_after = serialize_randstream_state(mod.chromosome.randStream);
            proc_state_after = serialize_randstream_state(mod.randStream);

            summary.live_free_bound_after = capture_free_bound_counts(mod);
            summary.live_after_bound_sites = capture_complex_bound_sites(mod.chromosome, gyrase_gidx, topoiv_gidx, topoi_gidx);
            summary.live_region_occupancy_after = capture_region_occupancy( ...
                mod.chromosome, opts.probe_region_start, opts.probe_region_len);

            reconstructed = reconstruct_consumed_draws( ...
                mod.chromosome.randStream, chrom_state_before, chrom_state_after);
            proc_reconstructed = reconstruct_consumed_draws( ...
                mod.randStream, proc_state_before, proc_state_after);

            summary.chromosome_state_before = chrom_state_before;
            summary.chromosome_state_after = chrom_state_after;
            summary.process_state_before = proc_state_before;
            summary.process_state_after = proc_state_after;
            summary.chromosome_release_draws = reconstructed.draws;
            summary.chromosome_release_draws_reconstructed_ok = reconstructed.ok;
            summary.process_draws = proc_reconstructed.draws;
            summary.process_draws_reconstructed_ok = proc_reconstructed.ok;
            summary.process_draws_count = int32(numel(proc_reconstructed.draws));

            summary.topoiv_newly_bound_positions_strands = set_difference_pos_strand( ...
                summary.live_after_bound_sites.topoiv.positions, summary.live_after_bound_sites.topoiv.strands, ...
                summary.live_before_bound_sites.topoiv.positions, summary.live_before_bound_sites.topoiv.strands);
            summary.gyrase_newly_bound_positions_strands = set_difference_pos_strand( ...
                summary.live_after_bound_sites.gyrase.positions, summary.live_after_bound_sites.gyrase.strands, ...
                summary.live_before_bound_sites.gyrase.positions, summary.live_before_bound_sites.gyrase.strands);

            summary.captured = true;
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
end

function out = capture_region_occupancy(chrom, region_start, region_len)
% Captures ALL monomerBoundSites/complexBoundSites/damagedSites entries
% (not filtered by any specific enzyme) within [region_start,
% region_start+region_len) on every strand -- used to directly test
% whether a region's occupancy at DNASupercoiling's REAL, live turn this
% tick (this function's caller site) differs from the tick-start
% states_before trace snapshot opencell's own diagnostics/production code
% uses as its chromosome-store input oracle.
out = struct();
out.region_start = int64(region_start);
out.region_len = int64(region_len);
region_end = region_start + region_len; % exclusive

[cpxPosStrnds, cpxs] = find(chrom.complexBoundSites);
mask = cpxPosStrnds(:, 1) >= region_start & cpxPosStrnds(:, 1) < region_end;
out.complexBoundSites = struct( ...
    'positions', int64(cpxPosStrnds(mask, 1)), ...
    'strands', int8(cpxPosStrnds(mask, 2)), ...
    'values', int64(cpxs(mask)));

[monPosStrnds, mons] = find(chrom.monomerBoundSites);
mask = monPosStrnds(:, 1) >= region_start & monPosStrnds(:, 1) < region_end;
out.monomerBoundSites = struct( ...
    'positions', int64(monPosStrnds(mask, 1)), ...
    'strands', int8(monPosStrnds(mask, 2)), ...
    'values', int64(mons(mask)));

dmgPosStrnds = find(chrom.damagedSites);
mask = dmgPosStrnds(:, 1) >= region_start & dmgPosStrnds(:, 1) < region_end;
out.damagedSites = struct( ...
    'positions', int64(dmgPosStrnds(mask, 1)), ...
    'strands', int8(dmgPosStrnds(mask, 2)));
end

function out = capture_topoiv_accessible_regions(mod, topoiv_gidx)
% Read-only reproduction of DNASupercoiling.m's legality computation
% (evolveState.m top, verbatim) plus a DIRECT, side-effect-free call to
% Chromosome.getAccessibleRegions/intersectRegions for topoIV specifically
% (mirroring bindProteinToChromosomeStochastically's own internal call,
% ChromosomeProcessAspect.m:79-84) -- to test, WITHOUT mutating any live
% state, whether the accessible-region computation genuinely yields empty
% space for topoIV's sole legal region this tick, or whether it agrees
% with opencell's own (nonzero-space) computation.
c = mod.chromosome;
out = struct();

[tmpPosStrands, lengths] = find(c.doubleStrandedRegions);
tmpIdxs = find(rem(tmpPosStrands(:, 2), 2));
dsPosStrands = tmpPosStrands(tmpIdxs, :);
lengths = lengths(tmpIdxs, 1);

[~, linkingNumbers] = find(c.linkingNumbers);
linkingNumbers = linkingNumbers(tmpIdxs, 1);
sigmas = (linkingNumbers - lengths / c.relaxedBasesPerTurn) ./ (lengths / c.relaxedBasesPerTurn);

legal_topoiv = sigmas > mod.topoIVSigmaLimit;
out.dsPosStrands_legal = int64(dsPosStrands(legal_topoiv, :));
out.lengths_legal = int64(lengths(legal_topoiv));

enzymeIndex = mod.enzymeIndexs_topoIV;
tf = ismembc(enzymeIndex, mod.enzymeMonomerLocalIndexs);
if tf
    monomerIdx = mod.enzymeGlobalIndexs(enzymeIndex);
    complexIdx = zeros(0, 1);
else
    monomerIdx = zeros(0, 1);
    complexIdx = mod.enzymeGlobalIndexs(enzymeIndex);
end

[rgnPosStrnds, rgnLens] = c.getAccessibleRegions(monomerIdx, complexIdx);
out.accessible_before_intersect_count = int32(size(rgnPosStrnds, 1));
out.accessible_before_intersect_total_len = int64(sum(rgnLens));

% Dump any accessible-region entries that overlap the target window on
% EITHER raw-strand representation (1 or 2, since getAccessibleRegions
% returns SUBSET-indexed strands for a dsDNA/dsDNA protein -- 1 for the
% first odd raw strand, 2 for the second -- not raw strand numbers 1-4).
target_start = dsPosStrands(legal_topoiv, 1);
target_len = lengths(legal_topoiv);
target_end = target_start + target_len; % exclusive, same convention as capture_region_occupancy
overlap_mask = (rgnPosStrnds(:, 1) < target_end) & (rgnPosStrnds(:, 1) + rgnLens > target_start);
out.raw_accessible_overlap_positions = int64(rgnPosStrnds(overlap_mask, 1));
out.raw_accessible_overlap_strands = int8(rgnPosStrnds(overlap_mask, 2));
out.raw_accessible_overlap_lengths = int64(rgnLens(overlap_mask));

[rgnPosStrnds2, rgnLens2] = c.intersectRegions( ...
    rgnPosStrnds, rgnLens, dsPosStrands(legal_topoiv, :), lengths(legal_topoiv));
out.accessible_after_intersect_count = int32(size(rgnPosStrnds2, 1));
out.accessible_after_intersect_positions = int64(rgnPosStrnds2(:, 1));
out.accessible_after_intersect_strands = int8(rgnPosStrnds2(:, 2));
out.accessible_after_intersect_lengths = int64(rgnLens2);
out.footprint = int64(mod.enzymeDNAFootprints(enzymeIndex));
out.nProteins_would_be = int64(mod.enzymes(enzymeIndex));

% Literal reproduction of getAccessibleRegions's internal exclusion-set
% computation (Chromosome.m:1608-1660), dumped for direct inspection
% (read-only; duplicates existing live fields, no mutation).
[releasableMonomerIndexs, releasableComplexIndexs] = c.getReleasableProteins(monomerIdx, complexIdx);
[monPosStrnds, mons] = find(c.monomerBoundSites);
[cpxPosStrnds, cpxs] = find(c.complexBoundSites);

iMonSS = find(~ismembc(mons, releasableMonomerIndexs) & c.monomerDNAFootprintBindingStrandedness(mons) == c.dnaStrandedness_ssDNA);
iMonDS = find(~ismembc(mons, releasableMonomerIndexs) & c.monomerDNAFootprintBindingStrandedness(mons) == c.dnaStrandedness_dsDNA);
iCpxSS = find(~ismembc(cpxs, releasableComplexIndexs) & c.complexDNAFootprintBindingStrandedness(cpxs) == c.dnaStrandedness_ssDNA);
iCpxDS = find(~ismembc(cpxs, releasableComplexIndexs) & c.complexDNAFootprintBindingStrandedness(cpxs) == c.dnaStrandedness_dsDNA);

excPosStrnds = [
    monPosStrnds(iMonSS, :)
    monPosStrnds(iMonDS, 1) 2*ceil(monPosStrnds(iMonDS, 2)/2)-1
    monPosStrnds(iMonDS, 1) 2*ceil(monPosStrnds(iMonDS, 2)/2)
    cpxPosStrnds(iCpxSS, :)
    cpxPosStrnds(iCpxDS, 1) 2*ceil(cpxPosStrnds(iCpxDS, 2)/2)-1
    cpxPosStrnds(iCpxDS, 1) 2*ceil(cpxPosStrnds(iCpxDS, 2)/2)
    ];
excLens = [
    c.monomerDNAFootprints(mons(iMonSS))
    c.monomerDNAFootprints(mons(iMonDS))
    c.monomerDNAFootprints(mons(iMonDS))
    c.complexDNAFootprints(cpxs(iCpxSS))
    c.complexDNAFootprints(cpxs(iCpxDS))
    c.complexDNAFootprints(cpxs(iCpxDS))
    ];

% dsDNA-binding-strandedness query (topoIV) collapses to pair-index space.
excPosStrnds(:, 2) = ceil(excPosStrnds(:, 2) / 2);

% Damage exclusion (Chromosome.m:1651-1660 -- getAccessibleRegions's own
% real damage handling, using `this.damagedSites`, the m6AD-excluded
% getter, with a fixed 1bp length per entry, always). Missing from this
% diagnostic dump's manual excPosStrnds/excLens reproduction previously
% (the AUTHORITATIVE `c.getAccessibleRegions` call above already includes
% it correctly; this only affects the DIAGNOSTIC last-entry dump below).
dmgPosStrnds = find(c.damagedSites);
if ~isempty(dmgPosStrnds)
    dmgPosStrnds(:, 2) = ceil(dmgPosStrnds(:, 2) / 2);
    excPosStrnds = [excPosStrnds; dmgPosStrnds];
    excLens = [excLens; ones(size(dmgPosStrnds, 1), 1)];
end

mask_near = (excPosStrnds(:, 1) < 3537) & (excPosStrnds(:, 1) + excLens > 3126) & (excPosStrnds(:, 2) == 1);
out.exclusions_near_region_pairIdx1 = struct( ...
    'positions', int64(excPosStrnds(mask_near, 1)), ...
    'lengths', int64(excLens(mask_near)));

% Ground truth: the FULL accessible-region fragment list (before
% intersecting with the target legal region), filtered to strand==1
% (pairIdx1, our target's pair) and positions near [2500,4000], exactly
% as returned by getAccessibleRegions -- no hand-recomputation.
mask_ground = rgnPosStrnds(:, 2) == 1 & rgnPosStrnds(:, 1) + rgnLens > 2500 & rgnPosStrnds(:, 1) < 4000;
out.ground_truth_accessible_fragments_near_pairIdx1 = struct( ...
    'positions', int64(rgnPosStrnds(mask_ground, 1)), ...
    'lengths', int64(rgnLens(mask_ground)));

% Also dump the count/total-length of ALL exclusions on pairIdx1
% anywhere on the chromosome, and the single largest one (sanity check
% for an unexpectedly-huge single entry that could span the whole region).
out.exclusions_pairIdx1_all_count = int32(sum(excPosStrnds(:, 2) == 1));
[max_exc_len, max_exc_idx] = max(excLens(excPosStrnds(:, 2) == 1));
pairIdx1_positions = excPosStrnds(excPosStrnds(:, 2) == 1, 1);
out.exclusions_pairIdx1_max_len = int64(max_exc_len);
out.exclusions_pairIdx1_max_len_position = int64(pairIdx1_positions(max_exc_idx));

% The TRUE call-global "excLens(end)" bug value: joinSplitRegions on the
% COMPLETE (all pairIdx, damage-included) exclusion set, exactly as the
% real excludeRegions call getAccessibleRegions makes would use.
[joinedAllPosStrnds, joinedAllLens] = c.joinSplitRegions(excPosStrnds, excLens);
out.joined_all_first = struct('position', int64(joinedAllPosStrnds(1, 1)), 'strand', int8(joinedAllPosStrnds(1, 2)), 'length', int64(joinedAllLens(1)));
out.joined_all_last = struct('position', int64(joinedAllPosStrnds(end, 1)), 'strand', int8(joinedAllPosStrnds(end, 2)), 'length', int64(joinedAllLens(end)));
out.joined_all_count = int32(size(joinedAllPosStrnds, 1));

% Isolated, minimal, real (not reimplemented) excludeRegions call: JUST
% our target polymerized fragment minus JUST the one exclusion that
% overlaps it, to see the true fragment-splitting behavior in isolation
% (no other confounding exclusion entries).
[isolatedPosStrnds, isolatedLens] = c.excludeRegions([3126 1], 411, [3113 1], 49);
out.isolated_exclude_test_positions = int64(isolatedPosStrnds(:, 1));
out.isolated_exclude_test_strands = int8(isolatedPosStrnds(:, 2));
out.isolated_exclude_test_lengths = int64(isolatedLens);

% Test A: single polymerized fragment, FULL real exclusion list
% (pairIdx1 subset only) -- isolates whether the anomaly comes from the
% exclusion side.
pairIdx1_mask = excPosStrnds(:, 2) == 1;
[testAPosStrnds, testALens] = c.excludeRegions( ...
    [3126 1], 411, excPosStrnds(pairIdx1_mask, :), excLens(pairIdx1_mask));
out.testA_full_exclusions_single_fragment_positions = int64(testAPosStrnds(:, 1));
out.testA_full_exclusions_single_fragment_lengths = int64(testALens);

% Dump the JOINED/merged exclusion set (post joinSplitRegions, the exact
% preprocessing excludeRegions itself performs) restricted to entries
% covering [2500,4000] on pairIdx1, to see directly what happens to the
% exclusion list around our target fragment after merging.
[joinedPosStrnds, joinedLens] = c.joinSplitRegions(excPosStrnds(pairIdx1_mask, :), excLens(pairIdx1_mask));
mask_joined_near = joinedPosStrnds(:, 1) < 4000 & joinedPosStrnds(:, 1) + joinedLens > 2500;
out.joined_exclusions_near_positions = int64(joinedPosStrnds(mask_joined_near, 1));
out.joined_exclusions_near_lengths = int64(joinedLens(mask_joined_near));
out.joined_exclusions_pairIdx1_count = int32(size(joinedPosStrnds, 1));
out.joined_exclusions_pairIdx1_first = struct('position', int64(joinedPosStrnds(1, 1)), 'length', int64(joinedLens(1)));
out.joined_exclusions_pairIdx1_last = struct('position', int64(joinedPosStrnds(end, 1)), 'length', int64(joinedLens(end)));

% Binary-search style isolation: does restricting the FULL exclusion set
% to a NEARBY window reproduce the anomaly, or does it require the FULL
% genome-wide set?
nearby_mask = pairIdx1_mask & excPosStrnds(:, 1) >= 0 & excPosStrnds(:, 1) < 10000;
[testC1PosStrnds, testC1Lens] = c.excludeRegions( ...
    [3126 1], 411, excPosStrnds(nearby_mask, :), excLens(nearby_mask));
out.testC_nearby_10000_positions = int64(testC1PosStrnds(:, 1));
out.testC_nearby_10000_lengths = int64(testC1Lens);
out.testC_nearby_10000_exc_count = int32(sum(nearby_mask));

half_mask = pairIdx1_mask & excPosStrnds(:, 1) < 290038;
[testC2PosStrnds, testC2Lens] = c.excludeRegions( ...
    [3126 1], 411, excPosStrnds(half_mask, :), excLens(half_mask));
out.testC_firsthalf_positions = int64(testC2PosStrnds(:, 1));
out.testC_firsthalf_lengths = int64(testC2Lens);
out.testC_firsthalf_exc_count = int32(sum(half_mask));

% Dump the exact 15 nearby (<10000) entries for manual inspection, and
% bisect further: does JUST the 8 entries closest to our target
% ([2000,4200)) reproduce the empty result?
out.nearby_10000_dump_positions = int64(excPosStrnds(nearby_mask, 1));
out.nearby_10000_dump_lengths = int64(excLens(nearby_mask));

closer_mask = pairIdx1_mask & excPosStrnds(:, 1) >= 2000 & excPosStrnds(:, 1) < 4200;
[testDPosStrnds, testDLens] = c.excludeRegions( ...
    [3126 1], 411, excPosStrnds(closer_mask, :), excLens(closer_mask));
out.testD_closer_2000_4200_positions = int64(testDPosStrnds(:, 1));
out.testD_closer_2000_4200_lengths = int64(testDLens);
out.testD_closer_2000_4200_exc_count = int32(sum(closer_mask));
out.testD_closer_2000_4200_dump_positions = int64(excPosStrnds(closer_mask, 1));
out.testD_closer_2000_4200_dump_lengths = int64(excLens(closer_mask));

% Instrumented, standalone COPY of excludeRegions's algorithm (verbatim
% logic, Chromosome.m:2597-2670) with fprintf tracing at every step, run
% against testC's EXACT input, to find the precise point where the
% empty-result path diverges from hand-tracing.
out.traced_testC = traced_exclude_regions(c, [3126 1], 411, excPosStrnds(nearby_mask, :), excLens(nearby_mask));

% Hardcoded, literal-value cross-check: eliminate any possibility of
% variable-aliasing/mutation between the real call and the traced copy
% by passing IDENTICAL, explicitly-typed-out literal arrays to both.
hardcoded_exc_pos = [2062;2412;2587;2762;2937;3113;3537;3712;3987;4162;4337;4687;4862;5517;5517];
hardcoded_exc_strand = ones(15, 1);
hardcoded_exc_len = [145;145;145;145;145;49;145;145;145;145;145;145;145;630;630];
[realHPosStrnds, realHLens] = c.excludeRegions([3126 1], 411, [hardcoded_exc_pos hardcoded_exc_strand], hardcoded_exc_len);
out.hardcoded_real_positions = int64(realHPosStrnds(:, 1));
out.hardcoded_real_lengths = int64(realHLens);
out.hardcoded_traced = traced_exclude_regions(c, [3126 1], 411, [hardcoded_exc_pos hardcoded_exc_strand], hardcoded_exc_len);

% Regression-test edge case: single region [0,190) on strand1, single
% exclusion [39,140) NOT touching either edge -- to resolve the exact
% real MATLAB behavior for the "matched_starts[0] > start_coor AND
% doesn't reach end" branch with only ONE matched exclusion (used by
% opencell's own _matlab_exclude_regions port and its regression test).
[edgeCasePosStrnds, edgeCaseLens] = c.excludeRegions([1 1], 190, [40 1], 140);
out.edge_case_single_exclusion_middle_positions = int64(edgeCasePosStrnds(:, 1));
out.edge_case_single_exclusion_middle_lengths = int64(edgeCaseLens);

% Test B: FULL real polymerized fragment list (pairIdx1/subsetcol1 only),
% single isolated exclusion -- isolates whether the anomaly comes from
% the polymerized-region side.
[subsetPosStrnds, subsetLens] = find(c.doubleStrandedRegions(:, 1:2:end));
subsetCol1Mask = subsetPosStrnds(:, 2) == 1;
[testBPosStrnds, testBLens] = c.excludeRegions( ...
    subsetPosStrnds(subsetCol1Mask, :), subsetLens(subsetCol1Mask), [3113 1], 49);
mask_testB_near = testBPosStrnds(:, 1) < 3700 & testBPosStrnds(:, 1) + testBLens > 2900;
out.testB_full_polymerized_single_exclusion_positions = int64(testBPosStrnds(mask_testB_near, 1));
out.testB_full_polymerized_single_exclusion_lengths = int64(testBLens(mask_testB_near));

% Raw structural diagnostic: what does doubleStrandedRegions actually
% look like (size + full find dump), and does the (:,1:2:end) subset
% getAccessibleRegions uses internally actually contain position 3126?
out.doubleStrandedRegions_size = int64(size(c.doubleStrandedRegions));
[allPosStrnds, allLens] = find(c.doubleStrandedRegions);
mask_pos = allPosStrnds(:, 1) == 3126;
out.doubleStrandedRegions_at_3126 = struct( ...
    'strands', int8(allPosStrnds(mask_pos, 2)), ...
    'lengths', int64(allLens(mask_pos)));

mask_pos2 = subsetPosStrnds(:, 1) == 3126;
out.subset_doubleStrandedRegions_at_3126 = struct( ...
    'subset_strand_col', int8(subsetPosStrnds(mask_pos2, 2)), ...
    'lengths', int64(subsetLens(mask_pos2)));
end

function out = traced_exclude_regions(c, incPosStrnds, incLens, excPosStrnds, excLens)
% Standalone, instrumented COPY (never a modification of the shared
% Chromosome.m source) of excludeRegions's verbatim algorithm, with every
% intermediate variable captured for direct diagnostic inspection. Used
% ONLY to root-cause the Opus-flagged audit-boundary breach; never used
% by production code.
L = c.sequenceLen;
out = struct();

if isscalar(excLens)
    excLens = excLens(ones(size(excPosStrnds, 1), 1), 1);
end

[incPosStrnds, incLens] = c.joinSplitOverOriCRegions(incPosStrnds, incLens);
[excPosStrnds, excLens] = c.joinSplitRegions(excPosStrnds, excLens);

out.joined_exc_positions = int64(excPosStrnds(:, 1));
out.joined_exc_lengths = int64(excLens);

excPos = [
    excPosStrnds(:, 1) - L;
    excPosStrnds(:, 1);
    excPosStrnds(:, 1) + L];
excStrnds = [excPosStrnds(:, 2); excPosStrnds(:, 2); excPosStrnds(:, 2)];
excLensTripled = [excLens; excLens; excLens];

rgnPos = zeros(0, 1);
rgnEnds = zeros(0, 1);
rgnStrnds = zeros(0, 1);
for j = 1:size(incPosStrnds, 1)
    startCoor = incPosStrnds(j, 1);
    endCoor = startCoor + incLens(j) - 1;
    strnd = incPosStrnds(j, 2);

    excIdxs = find(...
        ((excPos <= startCoor & excPos + excLensTripled-1 >= startCoor) | ...
        (excPos <= endCoor & excPos + excLensTripled-1 >= endCoor) | ...
        (excPos >= startCoor & excPos + excLensTripled-1 <= endCoor)) & ...
        excStrnds == strnd);

    out.excIdxs = int64(excIdxs);
    out.excIdxs_positions = int64(excPos(excIdxs));
    out.excIdxs_lengths = int64(excLensTripled(excIdxs));

    if isempty(excIdxs)
        addtlPos = startCoor;
        addtlEnds = endCoor;
    elseif excPos(excIdxs(1)) <= startCoor
        if excPos(excIdxs(end)) + excLensTripled(excIdxs(end)) - 1 >= endCoor
            addtlPos = excPos(excIdxs(1:end-1)) + excLensTripled(excIdxs(1:end-1));
            addtlEnds = excPos(excIdxs(2:end))-1;
        else
            addtlPos = excPos(excIdxs) + excLensTripled(excIdxs);
            addtlEnds = [excPos(excIdxs(2:end))-1; endCoor];
        end
    else
        if excPos(excIdxs(end)) + excLensTripled(excIdxs(end)) - 1 >= endCoor
            addtlPos = [startCoor; excPos(excIdxs(1:end-1)) + excLensTripled(excIdxs(1:end-1))];
            addtlEnds = excPos(excIdxs)-1;
        else
            addtlPos = [startCoor; excPos(excIdxs) + excLensTripled(excIdxs)];
            addtlEnds = [excPos(excIdxs)-1; endCoor];
        end
    end

    out.addtlPos = int64(addtlPos);
    out.addtlEnds = int64(addtlEnds);

    rgnPos = [rgnPos; addtlPos]; %#ok<AGROW>
    rgnEnds = [rgnEnds; addtlEnds]; %#ok<AGROW>
    rgnStrnds = [rgnStrnds; strnd(ones(size(addtlPos)), 1)]; %#ok<AGROW>
end

out.rgnPos_before_wrap = int64(rgnPos);
out.rgnEnds_before_wrap = int64(rgnEnds);

idx = find(rgnPos > L);
rgnPos(idx) = rgnPos(idx) - L;
rgnEnds(idx) = rgnEnds(idx) - L;

idx = find(rgnPos > rgnEnds);
out.dropped_rgnPos_gt_rgnEnds = int64(rgnPos(idx));
rgnPos(idx, :) = [];
rgnEnds(idx, :) = [];
rgnStrnds(idx, :) = [];

out.final_rgnPos = int64(rgnPos);
out.final_rgnEnds = int64(rgnEnds);
out.final_rgnStrnds = int8(rgnStrnds);
end

function out = capture_free_bound_counts(mod)
out = struct();
gyrase_idx = mod.enzymeIndexs_gyrase;
topoiv_idx = mod.enzymeIndexs_topoIV;
topoi_idx = mod.enzymeIndexs_topoI;
out.gyrase_free = double(sum(mod.enzymes(gyrase_idx, :)));
out.topoiv_free = double(sum(mod.enzymes(topoiv_idx, :)));
out.topoi_free = double(sum(mod.enzymes(topoi_idx, :)));
out.gyrase_bound = double(sum(mod.boundEnzymes(gyrase_idx, :)));
out.topoiv_bound = double(sum(mod.boundEnzymes(topoiv_idx, :)));
out.topoi_bound = double(sum(mod.boundEnzymes(topoi_idx, :)));
end

function out = capture_complex_bound_sites(chrom, gyrase_gidx, topoiv_gidx, topoi_gidx)
[subs, vals] = find(chrom.complexBoundSites);
out = struct();
out.gyrase = filter_by_value(subs, vals, gyrase_gidx);
out.topoiv = filter_by_value(subs, vals, topoiv_gidx);
out.topoi = filter_by_value(subs, vals, topoi_gidx);
end

function out = filter_by_value(subs, vals, target_val)
mask = vals == target_val;
out = struct();
out.count = int32(sum(mask));
if any(mask)
    out.positions = int64(subs(mask, 1));
    if size(subs, 2) >= 2
        out.strands = int8(subs(mask, 2));
    else
        out.strands = int8(ones(sum(mask), 1));
    end
else
    out.positions = zeros(0, 1, 'int64');
    out.strands = zeros(0, 1, 'int8');
end
end

function out = set_difference_pos_strand(pos_a, strand_a, pos_b, strand_b)
a = [double(pos_a(:)), double(strand_a(:))];
b = [double(pos_b(:)), double(strand_b(:))];
if isempty(a)
    out = struct('positions', zeros(0, 1, 'int64'), 'strands', zeros(0, 1, 'int8'));
    return;
end
if isempty(b)
    keep = true(size(a, 1), 1);
else
    keep = ~ismember(a, b, 'rows');
end
out = struct();
out.positions = int64(a(keep, 1));
out.strands = int8(a(keep, 2));
end

function reconstructed = reconstruct_consumed_draws(live_randStream, state_before, state_after)
max_iterations = 200000;
reconstructed = struct('draws', [], 'ok', false, 'iterations', 0);

if isequal(state_before.values, state_after.values)
    reconstructed.ok = true;
    return;
end

rs_type = 'mcg16807';
try
    rs_type = live_randStream.Type;
catch
end

throwaway = RandStream(rs_type, 'Seed', 1);
throwaway.State = state_before.values;

draws = zeros(0, 1);
for it = 1:max_iterations
    d = rand(throwaway, 1, 1);
    draws(end + 1, 1) = d; %#ok<AGROW>
    if isequal(throwaway.State, state_after.values)
        reconstructed.ok = true;
        reconstructed.iterations = it;
        reconstructed.draws = draws;
        return;
    end
end
reconstructed.iterations = max_iterations;
reconstructed.draws = draws;
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

function opts = parse_inputs(varargin)
opts = struct( ...
    'seed', 0, ...
    'target_tick_zero_based', 0, ...
    'probe_region_start', 0, ...
    'probe_region_len', 0, ...
    'out_path', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_full_bind_activity_probe:invalidArgs', 'Arguments must be name/value pairs');
end

for i = 1:2:numel(varargin)
    name = varargin{i};
    value = varargin{i + 1};
    switch lower(char(name))
        case 'seed'
            opts.seed = double(value);
        case 'target_tick_zero_based'
            opts.target_tick_zero_based = double(value);
        case 'probe_region_start'
            opts.probe_region_start = double(value);
        case 'probe_region_len'
            opts.probe_region_len = double(value);
        case 'out_path'
            opts.out_path = char(value);
        otherwise
            error('l22_dnas_full_bind_activity_probe:unknownOption', 'Unknown option: %s', char(name));
    end
end

if isempty(opts.out_path)
    opts.out_path = fullfile(infer_repo_root(), 'tmp', ...
        sprintf('l22_dnas_full_bind_activity_probe_s%03d_t%03d.json', opts.seed, opts.target_tick_zero_based));
end
end

function repo_root = infer_repo_root()
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
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
