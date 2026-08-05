% full_cycle_event_scan_macromol.m
% Lifecycle-reachability probe for MacromolecularComplexation network >= 2
% (the competitive Monte Carlo cluster gated on MG_429_MONOMER / "E1").
% Answers a narrow, falsifiable question: across a (possibly partial)
% natural Karr cell cycle (birth to division, REAL scheduler order, no
% conditioning), does E1's directly state-mirrored monomer count ever
% leave zero, and does network >= 2 (either of the two competing
% pentamers) ever actually form a complex -- reported per-complex-identity,
% not summed, so genuine 2-way competition can be distinguished from a
% degenerate single-candidate draw?
%
% MECHANISM (corrected 2026-08 post-review; see finding #2/#3 of the
% blocking Opus review): this script calls the REAL, unmodified public
% method sim.evolveState() once per tick. It does NOT reimplement any part
% of the scheduler. This is a deliberate choice, not a simplification of
% convenience: Simulation.randStream is `properties (Access = private)`,
% so it cannot be read or driven from an external script at all -- the
% only way to get byte-for-byte real scheduler semantics (real seeded
% edu.stanford.covert.util.RandStream.randperm(nProcesses) process
% ordering, PLUS the tRNAAminoacylation-before-Translation rejection loop
% in Simulation.evolveState.m:47-54, PLUS the real per-process resource
% allocation formula) is to call the real sim.evolveState() as a black
% box. An earlier version of this script reimplemented the outer loop by
% hand (global randperm(nProcs), no tRNA/Translation ordering constraint,
% and a try/catch that silently swallowed seeding failures); that was a
% synthetic approximation of the scheduler, not the real one, and has been
% removed.
%
% Reading target_proc's own substrates/complexs around a black-box
% sim.evolveState() call is still safe and precise: we call
% target_proc.copyFromState() (a pure, side-effect-free read documented
% and empirically confirmed idempotent -- see
% scripts/matlab/diag_macromol_binding_scratch.m investigation, not
% committed) both immediately before and immediately after each
% sim.evolveState() call, and diff the *shared, authoritative* state
% values it exposes. This does not depend on any assumption about
% cross-process write ordering within the tick.
%
% E1 TERMINOLOGY (finding #3): MacromolecularComplexation.
% calcResourceRequirements_Current() unconditionally returns
% zeros(size(substrates)) (verified both by static source read and by a
% live diagnostic call showing sum(r(:))==0 and r==r2 across repeated
% calls), and this process's substrateMetaboliteGlobalCompartmentIndexs /
% substrateMetaboliteLocalIndexs are BOTH empty (numel==0, confirmed
% live). That means E1 (MG_429_MONOMER) is NOT drawn through the shared,
% competitive metabolite-allocation mechanism for this process at all --
% so the reviewer's suggested rename "allocated process share" would
% overstate what this value is. It is, empirically, a direct
% copyFromState()-synced mirror of the shared monomer count (most likely
% sourced from the ProteinMonomer state per this process's own docstring:
% "Macromolecular complexes are initialized up to the amounts of RNA and
% protein subunits initialized by other processes"). It is therefore
% reported below as e1_monomer_count_direct_state_read -- an accurate,
% source-backed name that is neither the old "free cellular pool" phrasing
% (which wrongly implied a shared/contested resource) nor "allocated
% process share" (which would wrongly imply metabolite-allocation
% competition that does not apply to this substrate).
%
% Usage: matlab -batch "run('scripts/matlab/full_cycle_event_scan_macromol.m')"

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

%% Setup WholeCell paths (same fallback pattern as karr_bootstrap.m)
wc_root = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell');
if ~exist(wc_root, 'dir')
    wc_root = 'E:\opencell\data\m1_sources\WholeCell';
end
old_dir = pwd;
cd(wc_root);
if exist('setPath.m', 'file') == 2
    try; setPath(); catch; end
else
    addpath(genpath(fullfile(wc_root, 'src')));
    addpath(genpath(fullfile(wc_root, 'lib')));
end
cd(old_dir);
addpath(fullfile(repo_root, 'scripts', 'matlab'));

out_dir = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'event_scan');
if ~exist(out_dir, 'dir'); mkdir(out_dir); end

%% Bootstrap
seed = uint32(0);
n_ticks_max = 33000; % ~9.2h at dt=1s; covers Karr's published ~32400-tick cycle plus margin
requested_name = 'MacromolecularComplexation';

fprintf('\n[macromol-scan] === %s (seed=%d, up to %d ticks, natural cycle, pinch-stop) ===\n', ...
    requested_name, seed, n_ticks_max);

sim = karr_bootstrap();

%% Find process index
target_proc_idx = [];
for i = 1:numel(sim.processes)
    proc_obj = sim.processes{i};
    try
        wid = proc_obj.wholeCellModelID;
        if contains(lower(wid), lower(requested_name))
            target_proc_idx = i;
            break;
        end
    catch
    end
end
if isempty(target_proc_idx)
    error('[macromol-scan] process not found: %s', requested_name);
end
fprintf('[macromol-scan] found %s at index %d\n', requested_name, target_proc_idx);

target_proc = sim.processes{target_proc_idx};
e1_idx = find(strcmp(target_proc.substrateWholeCellModelIDs, 'MG_429_MONOMER'), 1);
if isempty(e1_idx)
    error('[macromol-scan] MG_429_MONOMER not found in substrateWholeCellModelIDs');
end
net2_complex_names = {'MG_041_062_429_PENTAMER', 'MG_041_069_429_PENTAMER'};
net2_complex_idx = [];
for c = 1:numel(net2_complex_names)
    idx = find(strcmp(target_proc.complexWholeCellModelIDs, net2_complex_names{c}), 1);
    if ~isempty(idx)
        net2_complex_idx(end+1) = idx; %#ok<AGROW>
    end
end
fprintf('[macromol-scan] E1 local substrate index = %d; network-2 complex indices = %s\n', ...
    e1_idx, mat2str(net2_complex_idx));

%% Seed -- fail closed (finding #2): no swallowing try/catch. If seeding
% is malformed, Simulation.seedRandStream() throws and this script must
% stop, not silently proceed unseeded.
sim.applyOptions('seed', double(seed));
sim.seedRandStream();

%% Scan
csv_path = fullfile(out_dir, sprintf('MacromolecularComplexation_e1_lifecycle_seed%03d.csv', seed));
fid = fopen(csv_path, 'w');
fprintf(fid, ['tick,e1_monomer_count_direct_state_read,' ...
    'complex1_delta_MG_041_062_429_PENTAMER,complex2_delta_MG_041_069_429_PENTAMER,' ...
    'any_complex_delta_total,any_complex_changed,pinched\n']);

geom = sim.state('Geometry');
n_net2_complexes = numel(net2_complex_idx);

first_e1_nonzero_tick = -1;
first_net2_event_tick_by_complex = -ones(1, max(n_net2_complexes, 1));
max_e1_value = 0;
n_any_complex_events = 0;
n_net2_events_by_complex = zeros(1, max(n_net2_complexes, 1));
max_net2_delta_by_complex = zeros(1, max(n_net2_complexes, 1));

% Prime the pre-tick snapshot from the real, current authoritative state
% (copyFromState is a pure read; see mechanism note above).
target_proc.copyFromState();
complexs_prev = target_proc.complexs;

tic;
last_tick = 0;
for tick = 1:n_ticks_max
    last_tick = tick;
    if mod(tick, 1000) == 0
        elapsed = toc;
        fprintf('[macromol-scan] tick %d/%d (%.1f min) max_e1=%g net2_events=%s\n', ...
            tick, n_ticks_max, elapsed/60, max_e1_value, mat2str(n_net2_events_by_complex));
    end

    % Real scheduler: seeded randStream.randperm(nProcesses) process order
    % with the tRNAAminoacylation-before-Translation rejection loop
    % (Simulation.evolveState.m:47-54), real resource-requirement
    % estimation and allocation, real per-process evolveState() calls,
    % real media-condition application -- all performed internally by
    % this single call. No part of the scheduler is reimplemented here.
    sim.evolveState();

    % Pure reads of the current authoritative shared state (no writes).
    target_proc.copyFromState();
    e1_value_this_tick = target_proc.substrates(e1_idx);
    complexs_now = target_proc.complexs;
    d = complexs_now - complexs_prev;
    % any_complex_delta_total is a SIGNED SUM across every complex species
    % in the shared complexs state -- informational only. It must NEVER be
    % used to gate logging or to count "did anything change": two
    % different complexes changing by +1 and -1 in the same tick (a real,
    % observed pattern -- unrelated complexes churn every tick under the
    % real scheduler) sums to exactly 0 and would silently cancel out a
    % genuine event, including a genuine net2 formation, if used as a
    % gate. any_complex_changed is the cancellation-safe boolean actually
    % used below.
    any_complex_delta_total = sum(d(:));
    any_complex_changed = any(d(:) ~= 0);
    net2_deltas = zeros(1, max(n_net2_complexes, 1));
    if n_net2_complexes > 0
        net2_deltas(1:n_net2_complexes) = d(net2_complex_idx);
    end
    complexs_prev = complexs_now;

    if e1_value_this_tick > max_e1_value
        max_e1_value = e1_value_this_tick;
    end
    if e1_value_this_tick > 0 && first_e1_nonzero_tick < 0
        first_e1_nonzero_tick = tick;
    end
    if any_complex_changed
        n_any_complex_events = n_any_complex_events + 1;
    end
    for c = 1:n_net2_complexes
        if net2_deltas(c) ~= 0
            n_net2_events_by_complex(c) = n_net2_events_by_complex(c) + 1;
            if first_net2_event_tick_by_complex(c) < 0
                first_net2_event_tick_by_complex(c) = tick;
            end
        end
        if abs(net2_deltas(c)) > max_net2_delta_by_complex(c)
            max_net2_delta_by_complex(c) = abs(net2_deltas(c));
        end
    end

    is_pinched = false;
    try
        is_pinched = geom.pinched;
    catch
    end

    if mod(tick, 25) == 0 || any_complex_changed || e1_value_this_tick > 0 || is_pinched
        fprintf(fid, '%d,%g,%g,%g,%g,%d,%d\n', tick, e1_value_this_tick, ...
            net2_deltas(1), net2_deltas(min(2, n_net2_complexes)), any_complex_delta_total, ...
            any_complex_changed, is_pinched);
    end

    if is_pinched
        fprintf('[macromol-scan] cell pinched/divided at tick %d; stopping (natural cycle boundary)\n', tick);
        break;
    end
end

elapsed = toc;
fclose(fid);

fprintf('\n[macromol-scan] DONE: ran %d ticks in %.1f min\n', last_tick, elapsed/60);
fprintf('[macromol-scan] max E1 direct-state value observed = %g\n', max_e1_value);
fprintf('[macromol-scan] first tick E1 direct-state value > 0: %d\n', first_e1_nonzero_tick);
fprintf('[macromol-scan] total any-complex-delta events (this process, all complexes): %d\n', n_any_complex_events);
fprintf('[macromol-scan] per-identity network>=2 events: %s (first ticks: %s)\n', ...
    mat2str(n_net2_events_by_complex), mat2str(first_net2_event_tick_by_complex));

was_stopped_early = (last_tick >= n_ticks_max) && ~is_pinched;

summary = struct( ...
    'process', requested_name, ...
    'seed', double(seed), ...
    'mechanism', ['real Simulation.evolveState() per tick (seeded ', ...
        'randStream.randperm process order with tRNAAminoacylation-before-', ...
        'Translation rejection loop, real resource allocation); no scheduler ', ...
        'logic reimplemented by this script'], ...
    'n_ticks_ran', last_tick, ...
    'n_ticks_max_requested', n_ticks_max, ...
    'stop_condition', struct( ...
        'pinched', is_pinched, ...
        'reached_tick_budget_without_pinch', was_stopped_early, ...
        'note', ['is_pinched=true means the run reached natural cell division ', ...
            '(Geometry.pinched) and stopped at a genuine cycle boundary; ', ...
            'reached_tick_budget_without_pinch=true means the run was stopped ', ...
            'at n_ticks_max before observing natural division, so ANY claim ', ...
            'about ticks beyond n_ticks_ran is undetermined coverage, not ', ...
            'evidence of absence'] ...
    ), ...
    'e1_field_name', 'e1_monomer_count_direct_state_read', ...
    'e1_field_semantics', ['direct copyFromState()-synced mirror of the shared ', ...
        'monomer count for MG_429_MONOMER; NOT drawn via the competitive ', ...
        'metabolite-allocation mechanism (substrateMetaboliteLocalIndexs and ', ...
        'substrateMetaboliteGlobalCompartmentIndexs are both empty for this ', ...
        'process; calcResourceRequirements_Current() unconditionally returns ', ...
        'zeros, confirmed live and idempotent across repeated calls)'], ...
    'e1_local_substrate_index_1based', e1_idx, ...
    'net2_complex_names', {net2_complex_names(1:n_net2_complexes)}, ...
    'net2_complex_indices_1based', net2_complex_idx, ...
    'max_e1_value', max_e1_value, ...
    'first_e1_nonzero_tick', first_e1_nonzero_tick, ...
    'n_any_complex_events', n_any_complex_events, ...
    'n_net2_events_by_complex', n_net2_events_by_complex, ...
    'first_net2_event_tick_by_complex', first_net2_event_tick_by_complex, ...
    'max_net2_delta_by_complex', max_net2_delta_by_complex, ...
    'natural_cycle_stop_tick', last_tick, ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS') ...
);
summary_path = fullfile(out_dir, sprintf('MacromolecularComplexation_e1_lifecycle_seed%03d_summary.json', seed));
fid2 = fopen(summary_path, 'w');
fprintf(fid2, '%s', jsonencode(summary));
fclose(fid2);
fprintf('[macromol-scan] summary written: %s\n', summary_path);

exit(0);
