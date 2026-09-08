function [sim, mod, hook_output] = probe_repinit_advance_to_tick(sim, target_idx, trigger_tick, probe_fn, hook_mode)
% probe_repinit_advance_to_tick  Standalone, allocator-correct scheduler-
% loop runner for the RepInit investigative probe scripts
% (scripts/matlab/probe_repinit_*.m).
%
% This is a DELIBERATE, STANDALONE duplicate of
% scripts/matlab/extract_per_process_traces_v2.m's own
% `evolve_state_with_tap` scheduler loop, not a call into that file --
% MATLAB local (sub)functions are only visible WITHIN the file that
% defines them, so a genuinely standalone probe script cannot call
% `evolve_state_with_tap` at all; duplicating the (unmodified, read-only)
% loop body here is what makes these probe scripts standalone in the
% first place, per the explicit requirement that
% extract_per_process_traces_v2.m's own public signatures/behavior stay
% byte-identical to main and gain NO probe-only hooks, opts, or nested
% functions. This file intentionally has NO other callers and is not
% imported by extract_per_process_traces_v2.m in either direction.
%
% Runs the SAME shared-metabolite-pool allocator/scheduler loop, tick by
% tick, from `sim`'s current state, for `trigger_tick` total ticks. For
% every tick strictly before `trigger_tick`, this is an ordinary tick:
% the target process (`target_idx`) evolves exactly as it would inside
% `extract_per_process_traces_v2.m`, and no hook fires. On tick ==
% `trigger_tick` ONLY, `probe_fn(mod)` is invoked (a function handle
% taking the live process object and returning one output, captured as
% `hook_output`); every other process's evolveState() call this tick is
% completely unaffected. `probe_fn` MUST be side-effect-free with respect
% to the live process/simulation object's own state advancement (it may
% read `mod`/`mod.chromosome`/etc., but must not itself consume RNG draws
% or mutate the object) -- calling a pure/deterministic accessor
% (isRegionAccessible, calculateDnaA*BindingRates, etc.) satisfies this;
% see each probe_repinit_*.m caller's own docstring for its specific
% probe_fn body and why it is safe.
%
% `hook_mode` (optional, default 'before_evolve'):
%   - 'before_evolve': `probe_fn(mod)` fires immediately BEFORE the
%     target process's own `mod.evolveState()` call (the same tap point
%     `merge_chromosome_rand_stream_state`/`capture_rand_stream_state`
%     use in the shared extractor); `mod.evolveState()` still runs
%     afterward exactly as normal.
%   - 'replace_evolve': `probe_fn(mod)` REPLACES the target process's
%     `mod.evolveState()` call entirely for this tick -- used ONLY by
%     probe_repinit_stage_trace_ticks39_41.m, whose own probe_fn already
%     calls evolveState()'s real sub-methods directly, in the real order,
%     to capture intermediate stage state; calling mod.evolveState() a
%     second time afterward would double-evolve the process.
%
% `mod` (second output) is the live target-process object AFTER
% `trigger_tick` ticks have fully completed (post-evolveState() or
% post-probe_fn-replacement, post-copyToState()) -- useful for a caller
% that wants to inspect post-tick state in addition to `hook_output`.
%
% No enzyme-override machinery, no fixed_tap_anchor_opts/
% merge_event_observables enrichment, and no capture_rand_stream_state
% call: this runner exists ONLY to reach a specific tick and fire one
% probe hook, not to reproduce every extraction-time metadata/override
% feature of the shared extractor.
if nargin < 5 || isempty(hook_mode)
    hook_mode = 'before_evolve';
end
if ~(strcmp(hook_mode, 'before_evolve') || strcmp(hook_mode, 'replace_evolve'))
    error('probe_repinit_advance_to_tick:invalid_hook_mode', ...
        'hook_mode must be ''before_evolve'' or ''replace_evolve'', got %s', hook_mode);
end

if trigger_tick < 1
    error('probe_repinit_advance_to_tick:invalid_trigger_tick', ...
        'trigger_tick must be >= 1, got %d', trigger_tick);
end

hook_output = [];
mod = [];
for tick = 1:trigger_tick
    is_trigger = (tick == trigger_tick);
    if is_trigger
        [sim, mod, hook_output] = local_run_one_tick(sim, target_idx, probe_fn, hook_mode);
    else
        [sim, mod, ~] = local_run_one_tick(sim, target_idx, [], 'before_evolve');
    end
end
end

function [sim, target_mod, hook_output] = local_run_one_tick(sim, target_idx, probe_fn, hook_mode)
% local_run_one_tick  One tick of the allocator-correct scheduler loop,
% verbatim (structurally) duplicated from extract_per_process_traces_v2.m's
% `evolve_state_with_tap` (main, unmodified) MINUS the anchor_opts/
% extraction_opts/enzyme-override/randStreamState/merge_* enrichment this
% probe runner never needs, PLUS a single optional `probe_fn(mod)` call
% either immediately before, or (hook_mode='replace_evolve') INSTEAD OF,
% the target process's own `mod.evolveState()`.
hook_output = [];
target_mod = [];

time = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;

time.values = time.values + sim.stepSizeSec;
stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    stim.values, stim.setValues, time.values);

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

rna_decay_idx = sim.processIndex('RNADecay');
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

    if proc_idx == target_idx && ~isempty(probe_fn) && strcmp(hook_mode, 'before_evolve')
        hook_output = probe_fn(mod);
    end

    if proc_idx == target_idx && ~isempty(probe_fn) && strcmp(hook_mode, 'replace_evolve')
        hook_output = probe_fn(mod);
    else
        mod.evolveState();
    end

    if proc_idx == target_idx
        target_mod = mod;
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
