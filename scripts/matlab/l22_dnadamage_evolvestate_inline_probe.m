function report = l22_dnadamage_evolvestate_inline_probe(output_json_path, process_seed, chromosome_seed, max_ticks, uvb_value)
% l22_dnadamage_evolvestate_inline_probe
% Source-faithful DNADamage evolveState probe for the L22 restart lane.
%
% This probe prepares the exact extractor scheduler target surface, then
% compares:
%   1. a manual inline copy of DNADamage.m::evolveState(), and
%   2. a direct p.evolveState() call
%
% For each tick it logs the UVB reaction subset with random order,
% maxReactions, selectionProbability, preview sample counts, actual
% positionsStrands counts, and chromosome nnz deltas. It also supports an
% optional split chromosome RNG seed so we can falsify the spec-vs-extractor
% dual-stream question without editing the extractor first.

if nargin < 1 || isempty(output_json_path)
    output_json_path = fullfile( ...
        'artifacts', ...
        'l22_dnadamage_global_override', ...
        'evolvestate_inline_probe.json');
end
if nargin < 2 || isempty(process_seed)
    process_seed = uint32(2000);
else
    process_seed = uint32(process_seed);
end
if nargin < 3 || isempty(chromosome_seed)
    chromosome_seed = process_seed;
else
    chromosome_seed = uint32(chromosome_seed);
end
if nargin < 4 || isempty(max_ticks)
    max_ticks = 100;
end
if nargin < 5 || isempty(uvb_value)
    uvb_value = 7.474096569667582;
end

report = struct();
report.process = 'DNADamage';
report.process_seed = double(process_seed);
report.chromosome_seed = double(chromosome_seed);
report.max_ticks = double(max_ticks);
report.uvb_value = double(uvb_value);
report.generated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');
report.scheduler_surface = 'target_only';
report.manual = run_mode('manual_inline', process_seed, chromosome_seed, max_ticks, uvb_value);
report.direct = run_mode('direct_evolve_state', process_seed, chromosome_seed, max_ticks, uvb_value);

output_json_path = char(output_json_path);
[out_dir, ~, ~] = fileparts(output_json_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(output_json_path, 'w');
if fid == -1
    error('l22_dnadamage_evolvestate_inline_probe:open_failed', ...
        'Unable to open output path for writing: %s', output_json_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(report), 'char');
fprintf('[l22_dnadamage_evolvestate_inline_probe] wrote %s\n', output_json_path);
end

function mode_report = run_mode(mode_name, process_seed, chromosome_seed, max_ticks, uvb_value)
sim = karr_bootstrap();
seed_simulation_l22(sim, process_seed, chromosome_seed);

tick_rows = repmat(empty_tick_row(), max_ticks, 1);
first_positive_tick = 0;
first_positive_reaction_id = '';

for tick = 1:max_ticks
    [sim, proc, tick_row, commit_state] = prepare_target_only_scheduler_surface(sim, uvb_value, tick);
    uvb_rows = manual_uvb_probe_rows(proc);
    tick_row.uvb_reactions = uvb_rows;

    if strcmp(mode_name, 'manual_inline')
        [proc, tick_row] = run_manual_inline_tick(proc, tick_row);
    else
        [proc, tick_row] = run_direct_tick(proc, tick_row);
    end

    if first_positive_tick == 0 && tick_row.intrastrand_crosslinks_delta > 0
        first_positive_tick = tick;
        first_positive_reaction_id = tick_row.first_positive_reaction_id;
    end

    tick_rows(tick, 1) = tick_row;
    sim = commit_target_only_tick(sim, proc, commit_state);
end

mode_report = struct();
mode_report.mode = mode_name;
mode_report.process_seed = double(process_seed);
mode_report.chromosome_seed = double(chromosome_seed);
mode_report.first_positive_tick = double(first_positive_tick);
mode_report.first_positive_reaction_id = first_positive_reaction_id;
mode_report.positive_tick_count = double(sum([tick_rows.intrastrand_crosslinks_delta] > 0));
mode_report.final_intrastrand_crosslinks = double(tick_rows(end).intrastrand_crosslinks_after);
mode_report.final_total_damage_nnz = double(tick_rows(end).total_damage_nnz_after);
mode_report.tick_rows = tick_rows;
end

function [proc, tick_row] = run_manual_inline_tick(proc, tick_row)
reaction_ids = matlab_cellstr_l22(proc.reactionWholeCellModelIDs);
uvb_local_idx = find_uvb_local_idx(proc);
random_order = proc.randStream.randperm(numel(proc.reactionWholeCellModelIDs));
tick_row.random_order = double(random_order(:)');

tick_row.intrastrand_crosslinks_before = double(nnz(proc.chromosome.intrastrandCrossLinks));
tick_row.total_damage_nnz_before = total_damage_nnz(proc.chromosome);

for order_pos = 1:numel(random_order)
    j = random_order(order_pos);

    [max_reactions, max_reactions_diag] = compute_max_reactions(proc, j);
    selection_probability = compute_selection_probability(proc, j);
    if max_reactions <= 0
        if proc.reactionRadiation(j) == uvb_local_idx
            row_idx = find([tick_row.uvb_reactions.reaction_index] == j, 1);
            tick_row.uvb_reactions(row_idx) = finalize_uvb_row( ...
                tick_row.uvb_reactions(row_idx), order_pos, max_reactions, selection_probability, 0, 0, proc, ...
                j, tick_row.intrastrand_crosslinks_before, tick_row.intrastrand_crosslinks_before, ...
                tick_row.total_damage_nnz_before, tick_row.total_damage_nnz_before, max_reactions_diag, true);
        end
        continue;
    end

    before_crosslinks = double(nnz(proc.chromosome.intrastrandCrossLinks));
    before_total = total_damage_nnz(proc.chromosome);
    positions = zeros(0, 2);
    side_effects = [];

    if selection_probability ~= 0
        [positions, side_effects] = proc.chromosome.setSiteDamaged( ...
            proc.reactionDamageTypes{j}, proc.reactionDNAProduct(j), selection_probability, ...
            max_reactions, proc.reactionVulnerableMotifs{j}, proc.reactionVulnerableMotifTypes{j});
    end

    if ~isempty(positions)
        proc.substrates = proc.substrates + ...
            size(positions, 1) * proc.reactionSmallMoleculeStoichiometryMatrix(:, j);
        if ~isempty(side_effects)
            proc.simulationStateSideEffects = [proc.simulationStateSideEffects; side_effects];
        end
    end

    after_crosslinks = double(nnz(proc.chromosome.intrastrandCrossLinks));
    after_total = total_damage_nnz(proc.chromosome);

    if proc.reactionRadiation(j) == uvb_local_idx
        row_idx = find([tick_row.uvb_reactions.reaction_index] == j, 1);
        tick_row.uvb_reactions(row_idx) = finalize_uvb_row( ...
            tick_row.uvb_reactions(row_idx), ...
            order_pos, ...
            max_reactions, ...
            selection_probability, ...
            0, ...
            size(positions, 1), ...
            proc, ...
            j, ...
            before_crosslinks, ...
            after_crosslinks, ...
            before_total, ...
            after_total, ...
            max_reactions_diag, ...
            false);
        if size(positions, 1) > 0 && isempty(tick_row.first_positive_reaction_id)
            tick_row.first_positive_reaction_id = reaction_ids{j};
        end
    end
end

tick_row.intrastrand_crosslinks_after = double(nnz(proc.chromosome.intrastrandCrossLinks));
tick_row.total_damage_nnz_after = total_damage_nnz(proc.chromosome);
tick_row.intrastrand_crosslinks_delta = ...
    tick_row.intrastrand_crosslinks_after - tick_row.intrastrand_crosslinks_before;
tick_row.total_damage_nnz_delta = ...
    tick_row.total_damage_nnz_after - tick_row.total_damage_nnz_before;
end

function [proc, tick_row] = run_direct_tick(proc, tick_row)
tick_row.intrastrand_crosslinks_before = double(nnz(proc.chromosome.intrastrandCrossLinks));
tick_row.total_damage_nnz_before = total_damage_nnz(proc.chromosome);
proc.evolveState();
tick_row.intrastrand_crosslinks_after = double(nnz(proc.chromosome.intrastrandCrossLinks));
tick_row.total_damage_nnz_after = total_damage_nnz(proc.chromosome);
tick_row.intrastrand_crosslinks_delta = ...
    tick_row.intrastrand_crosslinks_after - tick_row.intrastrand_crosslinks_before;
tick_row.total_damage_nnz_delta = ...
    tick_row.total_damage_nnz_after - tick_row.total_damage_nnz_before;
end

function rows = manual_uvb_probe_rows(proc)
reaction_ids = matlab_cellstr_l22(proc.reactionWholeCellModelIDs);
uvb_local_idx = find_uvb_local_idx(proc);
uvb_rxns = find(proc.reactionRadiation == uvb_local_idx);
rows = repmat(empty_uvb_row(), numel(uvb_rxns), 1);
for i = 1:numel(uvb_rxns)
    j = uvb_rxns(i);
    row = empty_uvb_row();
    row.reaction_index = double(j);
    row.reaction_id = reaction_ids{j};
    row.vulnerable_motif_type = char(proc.reactionVulnerableMotifTypes{j});
    if ischar(proc.reactionVulnerableMotifs{j})
        row.vulnerable_motif = char(proc.reactionVulnerableMotifs{j});
    else
        row.vulnerable_motif = sprintf('damage_code_%d', double(proc.reactionVulnerableMotifs{j}));
    end
    rows(i, 1) = row;
end
end

function row = finalize_uvb_row(row, order_pos, max_reactions, selection_probability, preview_positions_count, actual_positions_count, proc, reaction_idx, before_crosslinks, after_crosslinks, before_total, after_total, max_reactions_diag, guard_skipped_before_damage)
if nargin < 8
    reaction_idx = row.reaction_index;
end
if nargin < 9
    before_crosslinks = double(nnz(proc.chromosome.intrastrandCrossLinks));
end
if nargin < 10
    after_crosslinks = before_crosslinks;
end
if nargin < 11
    before_total = total_damage_nnz(proc.chromosome);
end
if nargin < 12
    after_total = before_total;
end
if nargin < 13
    max_reactions_diag = empty_max_reactions_diag();
end
if nargin < 14
    guard_skipped_before_damage = false;
end

row.order_position = double(order_pos);
if isinf(max_reactions)
    row.max_reactions_value = -1;
    row.max_reactions_is_infinite = true;
else
    row.max_reactions_value = double(max_reactions);
    row.max_reactions_is_infinite = false;
end
row.selection_probability = double(selection_probability);
row.preview_positions_count = double(preview_positions_count);
row.actual_positions_count = double(actual_positions_count);
row.max_reactions_raw_text = char(max_reactions_diag.raw_text);
row.negative_infinite_ratio_count = double(max_reactions_diag.negative_infinite_ratio_count);
row.positive_infinite_ratio_count = double(max_reactions_diag.positive_infinite_ratio_count);
row.nan_ratio_count = double(max_reactions_diag.nan_ratio_count);
row.zero_denom_positive_substrate_count = double(max_reactions_diag.zero_denom_positive_substrate_count);
row.guard_skipped_before_damage = logical(guard_skipped_before_damage);
row.intrastrand_crosslinks_before = double(before_crosslinks);
row.intrastrand_crosslinks_after = double(after_crosslinks);
row.intrastrand_crosslinks_delta = double(after_crosslinks - before_crosslinks);
row.total_damage_nnz_before = double(before_total);
row.total_damage_nnz_after = double(after_total);
row.total_damage_nnz_delta = double(after_total - before_total);
row.reaction_index = double(reaction_idx);
end

function selection_probability = compute_selection_probability(proc, reaction_idx)
radiation_lcl_idx = proc.reactionRadiation(reaction_idx);
if radiation_lcl_idx ~= 0
    selection_probability = proc.stepSizeSec * proc.reactionBounds(reaction_idx, 2) * proc.substrates(radiation_lcl_idx);
else
    selection_probability = proc.stepSizeSec * proc.reactionBounds(reaction_idx, 2);
end
end

function [max_reactions, diag] = compute_max_reactions(proc, reaction_idx)
% Normalize exact-zero stoichiometry rows so MATLAB signed zero cannot flip
% non-reactant ratios from +Inf to -Inf before the evolveState guard.
denom = abs(max(0, -proc.reactionSmallMoleculeStoichiometryMatrix(:, reaction_idx)));
ratio = proc.substrates ./ denom;
max_reactions = floor(min(ratio));
diag = empty_max_reactions_diag();
diag.raw_text = local_num_to_text(max_reactions);
diag.negative_infinite_ratio_count = sum(isinf(ratio) & ratio < 0);
diag.positive_infinite_ratio_count = sum(isinf(ratio) & ratio > 0);
diag.nan_ratio_count = sum(isnan(ratio));
diag.zero_denom_positive_substrate_count = sum(denom == 0 & proc.substrates > 0);
end

function [sim, proc, tick_row, commit_state] = prepare_target_only_scheduler_surface(sim, uvb_value, tick_index)
time = sim.state_time;
stim = sim.state_stimulus;
mets = sim.state_metabolite;
processes = sim.processes;
nProcesses = numel(processes);
target_idx = sim.processIndex('DNADamage');
rna_decay_idx = sim.processIndex('RNADecay');

proc = processes{target_idx};
uvb_local_idx = find_uvb_local_idx(proc);

time.values = time.values + sim.stepSizeSec;
stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    stim.values, stim.setValues, time.values);

requirements = zeros([numel(mets.counts) nProcesses]);
for i = 1:nProcesses
    mod = processes{i};
    mod.copyFromState();
    if i == target_idx
        mod.substrates(uvb_local_idx, :) = double(uvb_value);
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

gidx = proc.substrateMetaboliteGlobalCompartmentIndexs;
lidx = proc.substrateMetaboliteLocalIndexs;
allocation = reshape(allocations(gidx, target_idx), size(gidx));
counts = mets.counts(gidx);

proc.simulationStateSideEffects = [];
proc.copyFromState();
proc.substrates(lidx, :) = allocation;
proc.substrates(uvb_local_idx, :) = double(uvb_value);
if target_idx == rna_decay_idx && isprop(proc, 'RNAs')
    proc.RNAs = max(0, proc.RNAs);
end

tick_row = empty_tick_row();
tick_row.tick = double(tick_index);
tick_row.time_value = double(time.values);
tick_row.uvb_local_before_evolve = double(proc.substrates(uvb_local_idx, 1));
tick_row.uvb_rate_sum_pre_evolve = uvb_rate_sum(proc, uvb_local_idx);
tick_row.total_rate_sum_pre_evolve = double(sum(proc.calcExpectedReactionRates()));
tick_row.substrate_allocation_count = double(numel(allocation));
tick_row.target_metabolite_counts_snapshot = double(sum(counts));
commit_state = struct( ...
    'gidx', gidx, ...
    'lidx', lidx, ...
    'allocation', allocation, ...
    'counts', counts);
end

function sim = commit_target_only_tick(sim, proc, commit_state)
mets = sim.state_metabolite;
gidx = commit_state.gidx;
lidx = commit_state.lidx;
allocation = commit_state.allocation;
counts = commit_state.counts;

proc.copyToState();
mets.counts(gidx) = counts + proc.substrates(lidx, :) - allocation;
if ~isempty(proc.simulationStateSideEffects)
    proc.simulationStateSideEffects.updateSimulationState(sim);
end

time = sim.state_time;
mets.counts = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    mets.counts, mets.setCounts, time.values);
end

function idx = find_uvb_local_idx(proc)
substrate_wids = matlab_cellstr_l22(proc.substrateWholeCellModelIDs);
idx = find(strcmp(substrate_wids, 'UVB_radiation'), 1);
if isempty(idx)
    error('l22_dnadamage_evolvestate_inline_probe:missing_uvb_local_idx', ...
        'DNADamage substrate vector has no UVB_radiation local index');
end
end

function value = uvb_rate_sum(proc, uvb_local_idx)
rates = proc.calcExpectedReactionRates();
value = double(sum(rates(proc.reactionRadiation == uvb_local_idx)));
end

function out = empty_tick_row()
out = struct( ...
    'tick', 0, ...
    'time_value', 0, ...
    'uvb_local_before_evolve', 0, ...
    'uvb_rate_sum_pre_evolve', 0, ...
    'total_rate_sum_pre_evolve', 0, ...
    'substrate_allocation_count', 0, ...
    'target_metabolite_counts_snapshot', 0, ...
    'random_order', zeros(1, 0), ...
    'intrastrand_crosslinks_before', 0, ...
    'intrastrand_crosslinks_after', 0, ...
    'intrastrand_crosslinks_delta', 0, ...
    'total_damage_nnz_before', 0, ...
    'total_damage_nnz_after', 0, ...
    'total_damage_nnz_delta', 0, ...
    'first_positive_reaction_id', '', ...
    'uvb_reactions', struct([]));
end

function out = empty_uvb_row()
out = struct( ...
    'reaction_index', 0, ...
    'reaction_id', '', ...
    'vulnerable_motif', '', ...
    'vulnerable_motif_type', '', ...
    'order_position', 0, ...
    'max_reactions_value', 0, ...
    'max_reactions_is_infinite', false, ...
    'max_reactions_raw_text', '', ...
    'selection_probability', 0, ...
    'preview_positions_count', 0, ...
    'actual_positions_count', 0, ...
    'negative_infinite_ratio_count', 0, ...
    'positive_infinite_ratio_count', 0, ...
    'nan_ratio_count', 0, ...
    'zero_denom_positive_substrate_count', 0, ...
    'guard_skipped_before_damage', false, ...
    'intrastrand_crosslinks_before', 0, ...
    'intrastrand_crosslinks_after', 0, ...
    'intrastrand_crosslinks_delta', 0, ...
    'total_damage_nnz_before', 0, ...
    'total_damage_nnz_after', 0, ...
    'total_damage_nnz_delta', 0);
end

function out = empty_max_reactions_diag()
out = struct( ...
    'raw_text', '', ...
    'negative_infinite_ratio_count', 0, ...
    'positive_infinite_ratio_count', 0, ...
    'nan_ratio_count', 0, ...
    'zero_denom_positive_substrate_count', 0);
end

function seed_simulation_l22(sim, process_seed, chromosome_seed)
try
    if isobject(sim) && ismethod(sim, 'applyOptions') && ismethod(sim, 'seedRandStream')
        sim.applyOptions('seed', process_seed);
        sim.seedRandStream();
    elseif isprop(sim, 'randStream') && ~isempty(sim.randStream)
        sim.randStream.seed = process_seed;
    end
catch
end

if nargin < 3 || isempty(chromosome_seed)
    return;
end
if chromosome_seed == process_seed
    return;
end

try
    chromosome = sim.state('Chromosome');
    chromosome.seed = chromosome_seed;
    chromosome.seedRandStream();
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

function total = total_damage_nnz(chromosome)
fields = { ...
    'damagedBases', ...
    'abasicSites', ...
    'strandBreaks', ...
    'damagedSugarPhosphates', ...
    'intrastrandCrossLinks', ...
    'hollidayJunctions', ...
    'gapSites' ...
};
total = 0;
for i = 1:numel(fields)
    total = total + double(nnz(chromosome.(fields{i})));
end
end

function txt = local_num_to_text(value)
if isinf(value)
    if value < 0
        txt = '-Inf';
    else
        txt = 'Inf';
    end
elseif isnan(value)
    txt = 'NaN';
else
    txt = num2str(double(value), 20);
end
end
