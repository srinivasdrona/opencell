function report = l22_dnadamage_uvb_sampling_probe(output_json_path, seed, uvb_value, n_reps)
% l22_dnadamage_uvb_sampling_probe
% Build the DNADamage target-only extractor pre-evolve surface for tick 1,
% then call Chromosome.sampleAccessibleSites() directly for each UVB
% sequence-motif reaction repeatedly. This isolates whether the Karr
% sampling path itself is capable of producing candidate lesion sites.

if nargin < 1 || isempty(output_json_path)
    output_json_path = fullfile('artifacts', 'l22_dnadamage_global_override', 'uvb_sampling_probe.json');
end
if nargin < 2 || isempty(seed)
    seed = uint32(2000);
else
    seed = uint32(seed);
end
if nargin < 3 || isempty(uvb_value)
    uvb_value = 7.474096569667582;
end
if nargin < 4 || isempty(n_reps)
    n_reps = 200;
end

sim = karr_bootstrap();
seed_simulation_l22(sim, seed);
proc = prepare_target_only_scheduler_surface(sim, uvb_value);

substrate_wids = matlab_cellstr_l22(proc.substrateWholeCellModelIDs);
uvb_local_idx = find(strcmp(substrate_wids, 'UVB_radiation'), 1);
uvb_rxn_idxs = find(proc.reactionRadiation == uvb_local_idx);
reaction_ids = matlab_cellstr_l22(proc.reactionWholeCellModelIDs);

rows = struct([]);
row_idx = 0;
for i = 1:numel(uvb_rxn_idxs)
    j = uvb_rxn_idxs(i);
    motif = proc.reactionVulnerableMotifs{j};
    if ~ischar(motif)
        continue;
    end
    row_idx = row_idx + 1;
    denom = abs(max(0, -proc.reactionSmallMoleculeStoichiometryMatrix(:, j)));
    max_reactions_raw = floor(min(proc.substrates ./ denom));
    if isinf(max_reactions_raw)
        max_reactions_value = -1;
        max_reactions_for_sampling = intmax('int32');
    else
        max_reactions_value = double(max_reactions_raw);
        max_reactions_for_sampling = max_reactions_raw;
    end
    prob = double(proc.stepSizeSec * proc.reactionBounds(j, 2) * proc.substrates(uvb_local_idx));
    expected_accessible = estimated_accessible_sites(proc.chromosome, motif);
    exact_accessible = exact_accessible_site_count(proc.chromosome, motif);

    nonempty_count = 0;
    total_selected_sites = 0;
    max_selected_sites = 0;
    for rep = 1:n_reps
        positions = proc.chromosome.sampleAccessibleSites(prob, max_reactions_for_sampling, motif);
        n_selected = size(positions, 1);
        if n_selected > 0
            nonempty_count = nonempty_count + 1;
            total_selected_sites = total_selected_sites + n_selected;
            max_selected_sites = max(max_selected_sites, n_selected);
        end
    end

    rows(row_idx).reaction_index = double(j); %#ok<AGROW>
    rows(row_idx).reaction_id = reaction_ids{j}; %#ok<AGROW>
    rows(row_idx).motif = motif; %#ok<AGROW>
    rows(row_idx).selection_probability = prob; %#ok<AGROW>
    rows(row_idx).estimated_accessible_sites = double(expected_accessible); %#ok<AGROW>
    rows(row_idx).exact_accessible_sites = double(exact_accessible); %#ok<AGROW>
    rows(row_idx).max_reactions_value = double(max_reactions_value); %#ok<AGROW>
    rows(row_idx).nonempty_count = double(nonempty_count); %#ok<AGROW>
    rows(row_idx).nonempty_fraction = double(nonempty_count / n_reps); %#ok<AGROW>
    rows(row_idx).total_selected_sites = double(total_selected_sites); %#ok<AGROW>
    rows(row_idx).max_selected_sites = double(max_selected_sites); %#ok<AGROW>
end

report = struct();
report.process = 'DNADamage';
report.seed = double(seed);
report.uvb_value = double(uvb_value);
report.n_reps = double(n_reps);
report.generated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');
report.rows = rows;

output_json_path = char(output_json_path);
[out_dir, ~, ~] = fileparts(output_json_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(output_json_path, 'w');
if fid == -1
    error('l22_dnadamage_uvb_sampling_probe:open_failed', ...
        'Unable to open output path for writing: %s', output_json_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(report), 'char');
fprintf('[l22_dnadamage_uvb_sampling_probe] wrote %s\n', output_json_path);
end

function proc = prepare_target_only_scheduler_surface(sim, uvb_value)
time = sim.state_time;
stim = sim.state_stimulus;
mets = sim.state_metabolite;
processes = sim.processes;
nProcesses = numel(processes);
target_idx = sim.processIndex('DNADamage');
proc = processes{target_idx};

substrate_wids = matlab_cellstr_l22(proc.substrateWholeCellModelIDs);
uvb_local_idx = find(strcmp(substrate_wids, 'UVB_radiation'), 1);

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
proc.copyFromState();
proc.substrates(lidx, :) = allocation;
proc.substrates(uvb_local_idx, :) = double(uvb_value);
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
