function report = l22_dnadamage_global_override_probe(output_json_path, seed, max_ticks, uvb_value)
% l22_dnadamage_global_override_probe
% Compare DNADamage UVB delivery on both:
%   1. the raw process-local surface, and
%   2. the exact extractor scheduler/allocation surface.
%
% This is a diagnosis tool for the L22 restart/global-override lane. It
% writes a tick ledger with:
%   - authoritative global stimulus value / scheduled setValue
%   - process-local UVB value after copyFromState / override stages
%   - UVB-only and total expected-rate sums
%   - post-evolve chromosome deltas
%   - tick-1 per-UVB-reaction gating diagnostics

if nargin < 1 || isempty(output_json_path)
    output_json_path = fullfile('artifacts', 'l22_dnadamage_global_override', 'probe_ledger_scheduler_v2.json');
end
if nargin < 2 || isempty(seed)
    seed = uint32(2000);
else
    seed = uint32(seed);
end
if nargin < 3 || isempty(max_ticks)
    max_ticks = 20;
end
if nargin < 4 || isempty(uvb_value)
    uvb_value = 7.474096569667582;
end

report = struct();
report.process = 'DNADamage';
report.seed = double(seed);
report.max_ticks = double(max_ticks);
report.uvb_value = double(uvb_value);
report.generated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');
report.modes = struct();

mode_names = { ...
    'extractor_local_only_raw', ...
    'global_stimulus_raw', ...
    'extractor_local_only_scheduler', ...
    'global_stimulus_scheduler' ...
};
for i = 1:numel(mode_names)
    mode_name = mode_names{i};
    report.modes.(mode_name) = run_mode(mode_name, seed, max_ticks, uvb_value);
end

output_json_path = char(output_json_path);
[out_dir, ~, ~] = fileparts(output_json_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(output_json_path, 'w');
if fid == -1
    error('l22_dnadamage_global_override_probe:open_failed', ...
        'Unable to open output path for writing: %s', output_json_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(report), 'char');
fprintf('[l22_dnadamage_global_override_probe] wrote %s\n', output_json_path);
end

function mode_report = run_mode(mode_name, seed, max_ticks, uvb_value)
cond = condition_indexs();
sim = karr_bootstrap();
seed_simulation_l22(sim, seed);

target_idx = sim.processIndex('DNADamage');
if isempty(target_idx) || target_idx == 0
    error('l22_dnadamage_global_override_probe:missing_process', 'DNADamage process not found');
end
proc = sim.processes{target_idx};
stim = sim.state_stimulus;

substrate_wids = matlab_cellstr_l22(proc.substrateWholeCellModelIDs);
uvb_local_idx = find(strcmp(substrate_wids, 'UVB_radiation'), 1);
if isempty(uvb_local_idx)
    error('l22_dnadamage_global_override_probe:missing_uvb_local_idx', ...
        'DNADamage substrate vector has no UVB_radiation local index');
end
stimulus_map_idx = find(proc.substrateStimulusLocalIndexs == uvb_local_idx, 1);
if isempty(stimulus_map_idx)
    error('l22_dnadamage_global_override_probe:missing_uvb_stimulus_mapping', ...
        'UVB_radiation local index %d is absent from substrateStimulusLocalIndexs', uvb_local_idx);
end
uvb_object_compartment_idx = proc.substrateStimulusGlobalCompartmentIndexs(stimulus_map_idx);
if uvb_object_compartment_idx <= 0
    error('l22_dnadamage_global_override_probe:invalid_uvb_stimulus_mapping', ...
        'UVB_radiation local index %d has invalid stimulus object-compartment index %d', ...
        uvb_local_idx, uvb_object_compartment_idx);
end

[stimulus_object_idx, stimulus_compartment_idx] = ind2sub( ...
    [numel(stim.wholeCellModelIDs) sim.compartment.count], uvb_object_compartment_idx);

use_global_stimulus = ~isempty(strfind(mode_name, 'global_stimulus')); %#ok<STREMP>
use_scheduler = ~isempty(strfind(mode_name, 'scheduler')); %#ok<STREMP>

if use_global_stimulus
    stim.setValues = replace_condition_value( ...
        stim.setValues, ...
        stimulus_object_idx, ...
        stimulus_compartment_idx, ...
        uvb_object_compartment_idx, ...
        uvb_value, ...
        cond);
    stim.values(uvb_object_compartment_idx) = double(uvb_value);
end

rows = repmat(empty_row(), max_ticks, 1);
first_positive_tick = 0;
first_positive_field = '';
uvb_reaction_diagnostics_tick1 = struct([]);

for tick = 1:max_ticks
    if use_scheduler
        [sim, row, proc] = run_scheduler_target_only_tick( ...
            sim, target_idx, tick, uvb_local_idx, uvb_object_compartment_idx, uvb_value, use_global_stimulus, cond);
    else
        [sim, row, proc] = run_raw_tick( ...
            sim, target_idx, tick, uvb_local_idx, uvb_object_compartment_idx, uvb_value, use_global_stimulus, cond);
    end
    rows(tick, 1) = row;

    if tick == 1
        run_exact_counts = use_scheduler && strcmp(mode_name, 'extractor_local_only_scheduler');
        uvb_reaction_diagnostics_tick1 = diagnose_uvb_reactions(proc, uvb_local_idx, run_exact_counts);
    end

    if first_positive_tick == 0
        if row.intrastrand_crosslinks_delta > 0
            first_positive_tick = tick;
            first_positive_field = 'intrastrandCrossLinks';
        elseif row.total_damage_nnz_delta > 0
            first_positive_tick = tick;
            first_positive_field = 'other_damage_field';
        end
    end
end

mode_report = struct();
mode_report.mode = mode_name;
if use_scheduler
    mode_report.execution_style = 'extractor_scheduler_through_target_turn';
else
    mode_report.execution_style = 'raw_process_only';
end
mode_report.seed = double(seed);
mode_report.uvb_local_idx = double(uvb_local_idx);
mode_report.uvb_object_compartment_idx = double(uvb_object_compartment_idx);
mode_report.stimulus_object_idx = double(stimulus_object_idx);
mode_report.stimulus_compartment_idx = double(stimulus_compartment_idx);
mode_report.first_positive_tick = double(first_positive_tick);
mode_report.first_positive_field = first_positive_field;
mode_report.positive_tick_count = double(sum([rows.total_damage_nnz_delta] > 0));
mode_report.uvb_reaction_diagnostics_tick1 = uvb_reaction_diagnostics_tick1;
mode_report.rows = rows;
end

function [sim, row, proc] = run_raw_tick(sim, target_idx, tick_index, uvb_local_idx, uvb_object_compartment_idx, uvb_value, use_global_stimulus, cond)
time = sim.state_time;
stim = sim.state_stimulus;
mets = sim.state_metabolite;
proc = sim.processes{target_idx};
uvb_reaction_mask = proc.reactionRadiation == uvb_local_idx;

time.values = time.values + sim.stepSizeSec;
stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    stim.values, stim.setValues, time.values);

row = empty_row();
row.tick = double(tick_index);
row.time_value = double(time.values);
row.global_stimulus_value_at_tick_start = double(stim.values(uvb_object_compartment_idx));
row.global_stimulus_scheduled_value = lookup_active_condition_value( ...
    stim.setValues, uvb_object_compartment_idx, time.values, cond);

proc.copyFromState();
row.local_after_requirements_copy = scalar_from_local_idx(proc.substrates, uvb_local_idx);
if ~use_global_stimulus
    proc.substrates(uvb_local_idx, :) = double(uvb_value);
end
row.local_after_requirements_override = scalar_from_local_idx(proc.substrates, uvb_local_idx);
rates_req = proc.calcExpectedReactionRates();
row.uvb_rate_sum_requirements = double(sum(rates_req(uvb_reaction_mask)));
row.total_rate_sum_requirements = double(sum(rates_req));

proc.copyFromState();
row.local_after_execution_copy = scalar_from_local_idx(proc.substrates, uvb_local_idx);
if ~use_global_stimulus
    proc.substrates(uvb_local_idx, :) = double(uvb_value);
end
row.local_before_evolve = scalar_from_local_idx(proc.substrates, uvb_local_idx);
rates_exec = proc.calcExpectedReactionRates();
row.uvb_rate_sum_pre_evolve = double(sum(rates_exec(uvb_reaction_mask)));
row.total_rate_sum_pre_evolve = double(sum(rates_exec));

row.intrastrand_crosslinks_before = double(nnz(proc.chromosome.intrastrandCrossLinks));
row.total_damage_nnz_before = total_damage_nnz(proc.chromosome);
proc.evolveState();
row.intrastrand_crosslinks_after = double(nnz(proc.chromosome.intrastrandCrossLinks));
row.total_damage_nnz_after = total_damage_nnz(proc.chromosome);
row.intrastrand_crosslinks_delta = ...
    row.intrastrand_crosslinks_after - row.intrastrand_crosslinks_before;
row.total_damage_nnz_delta = row.total_damage_nnz_after - row.total_damage_nnz_before;

proc.copyToState();
row.global_stimulus_value_after_copy_to_state = double(stim.values(uvb_object_compartment_idx));
mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    mets.counts, mets.setCounts, time.values);
end

function [sim, row, target_proc] = run_scheduler_target_only_tick(sim, target_idx, tick_index, uvb_local_idx, uvb_object_compartment_idx, uvb_value, use_global_stimulus, cond)
time = sim.state_time;
stim = sim.state_stimulus;
mets = sim.state_metabolite;
processes = sim.processes;
nProcesses = numel(processes);
rna_decay_idx = sim.processIndex('RNADecay');
target_proc = sim.processes{target_idx};

time.values = time.values + sim.stepSizeSec;
stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    stim.values, stim.setValues, time.values);

row = empty_row();
row.tick = double(tick_index);
row.time_value = double(time.values);
row.global_stimulus_value_at_tick_start = double(stim.values(uvb_object_compartment_idx));
row.global_stimulus_scheduled_value = lookup_active_condition_value( ...
    stim.setValues, uvb_object_compartment_idx, time.values, cond);

requirements = zeros([numel(mets.counts) nProcesses]);
for i = 1:nProcesses
    mod = processes{i};
    mod.copyFromState();
    if i == target_idx
        row_local_after_copy = scalar_after_optional_uvb_override(mod, true, use_global_stimulus, uvb_local_idx, uvb_value);
        row.local_after_requirements_copy = scalar_from_local_idx(mod.substrates, uvb_local_idx);
        row.local_after_requirements_override = row_local_after_copy;
        rates_req = mod.calcExpectedReactionRates();
        uvb_reaction_mask = mod.reactionRadiation == uvb_local_idx;
        row.uvb_rate_sum_requirements = double(sum(rates_req(uvb_reaction_mask)));
        row.total_rate_sum_requirements = double(sum(rates_req));
    end
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

mod = processes{target_idx};
gidx = mod.substrateMetaboliteGlobalCompartmentIndexs;
lidx = mod.substrateMetaboliteLocalIndexs;
allocation = reshape(allocations(gidx, target_idx), size(gidx));
counts = mets.counts(gidx);

mod.simulationStateSideEffects = [];
mod.copyFromState();
mod.substrates(lidx, :) = allocation;
local_after_exec = scalar_after_optional_uvb_override(mod, true, use_global_stimulus, uvb_local_idx, uvb_value);
if target_idx == rna_decay_idx && isprop(mod, 'RNAs')
    mod.RNAs = max(0, mod.RNAs);
end

row.local_after_execution_copy = scalar_from_local_idx(mod.substrates, uvb_local_idx);
row.local_before_evolve = local_after_exec;
rates_exec = mod.calcExpectedReactionRates();
uvb_reaction_mask = mod.reactionRadiation == uvb_local_idx;
row.uvb_rate_sum_pre_evolve = double(sum(rates_exec(uvb_reaction_mask)));
row.total_rate_sum_pre_evolve = double(sum(rates_exec));
row.intrastrand_crosslinks_before = double(nnz(mod.chromosome.intrastrandCrossLinks));
row.total_damage_nnz_before = total_damage_nnz(mod.chromosome);
target_proc = mod;

mod.evolveState();

row.intrastrand_crosslinks_after = double(nnz(mod.chromosome.intrastrandCrossLinks));
row.total_damage_nnz_after = total_damage_nnz(mod.chromosome);
row.intrastrand_crosslinks_delta = ...
    row.intrastrand_crosslinks_after - row.intrastrand_crosslinks_before;
row.total_damage_nnz_delta = row.total_damage_nnz_after - row.total_damage_nnz_before;
target_proc = mod;

mod.copyToState();
mets.counts(gidx) = counts + mod.substrates(lidx, :) - allocation;
if ~isempty(mod.simulationStateSideEffects)
    mod.simulationStateSideEffects.updateSimulationState(sim);
end

row.global_stimulus_value_after_copy_to_state = double(stim.values(uvb_object_compartment_idx));
mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    mets.counts, mets.setCounts, time.values);
end

function value = scalar_after_optional_uvb_override(mod, is_target, use_global_stimulus, uvb_local_idx, uvb_value)
if is_target && ~use_global_stimulus
    mod.substrates(uvb_local_idx, :) = double(uvb_value);
end
value = scalar_from_local_idx(mod.substrates, uvb_local_idx);
end

function out = empty_row()
out = struct( ...
    'tick', 0, ...
    'time_value', 0, ...
    'global_stimulus_value_at_tick_start', 0, ...
    'global_stimulus_scheduled_value', 0, ...
    'local_after_requirements_copy', 0, ...
    'local_after_requirements_override', 0, ...
    'uvb_rate_sum_requirements', 0, ...
    'total_rate_sum_requirements', 0, ...
    'local_after_execution_copy', 0, ...
    'local_before_evolve', 0, ...
    'uvb_rate_sum_pre_evolve', 0, ...
    'total_rate_sum_pre_evolve', 0, ...
    'intrastrand_crosslinks_before', 0, ...
    'intrastrand_crosslinks_after', 0, ...
    'intrastrand_crosslinks_delta', 0, ...
    'total_damage_nnz_before', 0, ...
    'total_damage_nnz_after', 0, ...
    'total_damage_nnz_delta', 0, ...
    'global_stimulus_value_after_copy_to_state', 0);
end

function seed_simulation_l22(sim, seed)
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

function out = matlab_cellstr_l22(values)
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

function value = scalar_from_local_idx(values, idx)
value = double(values(idx, 1));
end

function total = total_damage_nnz(chromosome)
fields = { ...
    'damagedBases', ...
    'abasicSites', ...
    'strandBreaks', ...
    'damagedSugarPhosphates', ...
    'intrastrandCrossLinks', ...
    'hollidayJunctions', ...
    'gapSites'};
total = 0;
for i = 1:numel(fields)
    total = total + double(nnz(chromosome.(fields{i})));
end
end

function rows = diagnose_uvb_reactions(proc, uvb_local_idx, exact_counts)
uvb_rxn_idxs = find(proc.reactionRadiation == uvb_local_idx);
reaction_ids = matlab_cellstr_l22(proc.reactionWholeCellModelIDs);
motif_cache = struct();
rows = repmat(struct( ...
    'reaction_index', 0, ...
    'reaction_id', '', ...
    'selection_probability', 0, ...
    'max_reactions_value', 0, ...
    'max_reactions_is_infinite', false, ...
    'vulnerable_motif', '', ...
    'vulnerable_motif_type', '', ...
    'estimated_accessible_sites', 0, ...
    'exact_accessible_sites', 0), numel(uvb_rxn_idxs), 1);
for i = 1:numel(uvb_rxn_idxs)
    j = uvb_rxn_idxs(i);
    denom = abs(max(0, -proc.reactionSmallMoleculeStoichiometryMatrix(:, j)));
    max_reactions_raw = floor(min(proc.substrates ./ denom));
    rows(i).reaction_index = double(j);
    rows(i).reaction_id = reaction_ids{j};
    rows(i).selection_probability = double(proc.stepSizeSec * proc.reactionBounds(j, 2) * proc.substrates(uvb_local_idx));
    rows(i).max_reactions_is_infinite = isinf(max_reactions_raw);
    if isinf(max_reactions_raw)
        rows(i).max_reactions_value = -1;
    else
        rows(i).max_reactions_value = double(max_reactions_raw);
    end
    rows(i).vulnerable_motif_type = char(proc.reactionVulnerableMotifTypes{j});
    motif = proc.reactionVulnerableMotifs{j};
    if ischar(motif)
        rows(i).vulnerable_motif = motif;
        rows(i).estimated_accessible_sites = double(estimated_accessible_sites(proc.chromosome, motif));
        if exact_counts
            cache_key = matlab.lang.makeValidName(['motif_' motif]);
            if ~isfield(motif_cache, cache_key)
                motif_cache.(cache_key) = double(exact_accessible_site_count(proc.chromosome, motif));
            end
            rows(i).exact_accessible_sites = motif_cache.(cache_key);
        end
    else
        rows(i).vulnerable_motif = sprintf('damage_code_%d', double(motif));
    end
end
end

function nSites = estimated_accessible_sites(chromosome, seq)
[~, boundMonomers] = find(chromosome.monomerBoundSites);
[~, boundComplexs] = find(chromosome.complexBoundSites);
nAccessibleSites = ...
    collapse(chromosome.polymerizedRegions) ...
    - sum(chromosome.monomerDNAFootprints(boundMonomers, 1)) ...
    - sum(chromosome.complexDNAFootprints(boundComplexs, 1)) ...
    - nnz(chromosome.damagedSites);
nGC = sum(seq == 'G' | seq == 'C');
seqLen = numel(seq);
nSites = nAccessibleSites * ...
    (chromosome.sequenceGCContent / 2)^nGC * ...
    ((1 - chromosome.sequenceGCContent) / 2)^(seqLen - nGC);
end

function count = exact_accessible_site_count(chromosome, seq)
dnaLength = chromosome.sequenceLen;
posStrnds = find(chromosome.polymerizedRegions);
nStrands = max(posStrnds(:, 2));
seqLen = numel(seq);
count = 0;
for strand = 1:nStrands
    positions = (1:dnaLength)';
    strands = strand * ones(dnaLength, 1);
    dir = 2 * (mod(strands, 2) == 1) - 1;
    pos = 0:seqLen - 1;
    subsequences = chromosome.sequence.subsequence( ...
        positions(:, ones(1, seqLen)) + ...
        dir(:, ones(1, seqLen)) .* pos(ones(dnaLength, 1), :), ...
        strands);
    if isscalar(seq)
        idx = find(subsequences == seq);
    elseif size(seq, 2) == 2
        idx = find(subsequences(:, 1) == seq(1) & subsequences(:, 2) == seq(2));
    else
        idx = find(all(subsequences == seq(ones(size(subsequences, 1), 1), :), 2));
    end
    if isempty(idx)
        continue;
    end
    positions = positions(idx, :);
    strands = strands(idx, :);
    [~, idxs] = chromosome.isRegionAccessible([positions strands], seqLen, [], [], true, [], false, false);
    count = count + numel(idxs);
end
end

function set_values = replace_condition_value(set_values, object_idx, compartment_idx, object_compartment_idx, value, cond)
keep = set_values(:, cond.objectCompartmentIndexs) ~= object_compartment_idx;
set_values = set_values(keep, :);
row = zeros(1, 6);
row(cond.objectIndexs) = object_idx;
row(cond.compartmentIndexs) = compartment_idx;
row(cond.valueIndexs) = double(value);
row(cond.initialTimeIndexs) = 0;
row(cond.finalTimeIndexs) = Inf;
row(cond.objectCompartmentIndexs) = object_compartment_idx;
set_values = [set_values; row];
end

function value = lookup_active_condition_value(set_values, object_compartment_idx, time_value, cond)
active = set_values( ...
    set_values(:, cond.objectCompartmentIndexs) == object_compartment_idx & ...
    time_value >= set_values(:, cond.initialTimeIndexs) & ...
    time_value <= set_values(:, cond.finalTimeIndexs), ...
    cond.valueIndexs);
if isempty(active)
    value = 0;
    return;
end
value = double(active(end));
end

function cond = condition_indexs()
cond = struct( ...
    'objectIndexs', 1, ...
    'compartmentIndexs', 2, ...
    'valueIndexs', 3, ...
    'initialTimeIndexs', 4, ...
    'finalTimeIndexs', 5, ...
    'objectCompartmentIndexs', 6);
end
