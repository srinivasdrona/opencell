function extract_l2_0a_allocator_oracle(n_ticks, seed)
% extract_l2_0a_allocator_oracle
% L2.0a oracle: capture Karr's per-tick allocator arithmetic (the authoritative
% oracle for the allocation-boundary gate). For each of the first n_ticks ticks,
% BEFORE evolveState, capture:
%   pool_before  : global metabolite pool  = mets.counts(:)          [nMC x 1]
%   requirements : per-process requirements (evolveState.m:31-35)     [nMC x nProc]
%   allocations  : per-process allocation  (evolveState.m:36-37)      [nMC x nProc]
% then advance the whole simulation one tick and repeat.
%
% This is Karr's REAL allocation output (uncapped fair-share `fix(...)`), NOT a
% Python recomputation -- so the gate (D5) compares OC's KarrAllocationStep to a
% genuine oracle, not to numbers OC could re-derive itself.
%
% Output: data/m1_sources/karr_native/l2_0a_allocator_oracle_s%03d.mat (-v7.3):
%   pool_before{t}, requirements{t}, allocations{t}, metabolite_wids,
%   compartment_wids, counts_shape, process_names, metadata.

if nargin < 1 || isempty(n_ticks); n_ticks = 5; end
if nargin < 2 || isempty(seed); seed = uint32(0); else; seed = uint32(seed); end

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native');
if ~exist(out_root, 'dir'); mkdir(out_root); end

sim = karr_bootstrap();
seed_simulation(sim, seed);

process_names = collect_process_ids(sim);
mets = sim.state_metabolite;
counts_shape = size(mets.counts);
metabolite_wids = cellstr(mets.wholeCellModelIDs);
try
    compartment_wids = cellstr(sim.compartment.wholeCellModelIDs);
catch
    compartment_wids = arrayfun(@(k) sprintf('compartment_%d', k), (1:counts_shape(2))', 'UniformOutput', false);
end

% L2.0a design position: 1 tick x 28 processes at the allocation boundary.
% Capture the allocator oracle at t=0 READ-ONLY (no sim advance) -- this also
% sidesteps the Transcription/releaseProteinFromSites bug that a full standalone
% evolveState advance hits. The oracle at a single tick is 28 processes x all
% metabolite-compartment WIDs, which is the design's intended surface.
n_ticks = 1;
pool_before   = cell(n_ticks, 1);
requirements  = cell(n_ticks, 1);
allocations   = cell(n_ticks, 1);

nProcesses = numel(sim.processes);
[pool_before{1}, requirements{1}, allocations{1}] = capture_allocator_oracle(sim);
fprintf('[l2_0a] tick 1: pool_nnz=%d req_nnz=%d alloc_nnz=%d (nProc=%d, nMC=%d)\n', ...
    nnz(pool_before{1}), nnz(requirements{1}), nnz(allocations{1}), nProcesses, numel(pool_before{1}));

metadata = struct( ...
    'n_ticks', n_ticks, ...
    'rng_seed', seed, ...
    'nProcesses', nProcesses, ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
    'source', '@Simulation/evolveState.m:24-37');

out_path = fullfile(out_root, sprintf('l2_0a_allocator_oracle_s%03d.mat', seed));
save(out_path, 'pool_before', 'requirements', 'allocations', ...
    'metabolite_wids', 'compartment_wids', 'counts_shape', 'process_names', ...
    'metadata', '-v7.3');
fprintf('[l2_0a] saved: %s\n', out_path);

end


function [pool_before, requirements, allocations] = capture_allocator_oracle(sim)
% Read-only capture of Karr's allocation-boundary oracle at the current tick
% (@Simulation/evolveState.m:24-37 arithmetic, verbatim). Does NOT advance the
% simulation or mutate shared state beyond the copyFromState the requirements
% estimate already performs.
mets = sim.state_metabolite;
processes = sim.processes;
nProcesses = numel(processes);
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
pool_before = mets.counts(:);
tmp = mets.counts(:) ./ max(1, sum(requirements, 2));
allocations = max(0, fix(requirements .* tmp(:, ones(nProcesses, 1))));
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


function short = process_short_name(proc)
wid = proc.wholeCellModelID;
if strncmp(wid, 'Process_', numel('Process_'))
    short = wid(numel('Process_') + 1:end);
else
    short = wid;
end
end
