function probe_txreg_full_init_sequence()
% probe_txreg_full_init_sequence  Live-MATLAB verification of whether the
% ACTUAL genuine-trace extraction recipe (karr_bootstrap() + seed_simulation(),
% as literally used by scripts/matlab/extract_per_process_traces_v2.m to
% produce data/m1_sources/karr_native/per_process_traces_v2_event_s000/
% TranscriptionalRegulation_4000ticks.mat) leaves TranscriptionalRegulation's
% private RandStream at a genuinely fresh seed(0) state before tick 1, or
% whether some hidden pre-tick-1 draw sequence (e.g. from a real
% Simulation.initializeState() call) desyncs it.
%
% Source citations:
%   - edu.stanford.covert.cell.sim.Process.m:283-290
%       constructRandStream() / seedRandStream() -- each process's private
%       RandStream is `RandStream('mcg16807')`, reset via
%       `this.randStream.reset(this.seed)`.
%   - edu.stanford.covert.cell.sim.@Simulation/Simulation.m:430-460
%       Simulation.seedRandStream() -- resets the simulation's own stream,
%       every state's stream, and every PROCESS's private stream, all to
%       the SAME scalar `this.seed` (propagated via `o.seed = this.seed`
%       before `o.seedRandStream()`).
%   - edu.stanford.covert.cell.sim.@Simulation/initializeState.m
%       Full Simulation.initializeState() calls `this.seedRandStream()`
%       FIRST, then does bulk metabolite/RNA/protein initialization using
%       `this.randStream` (the SIMULATION's own stream, never a process's),
%       and only THEN (in the "%% initialize processes" loop) calls each
%       process's own initializeState() in `processesInInitOrder` --
%       TranscriptionalRegulation.initializeState() is a direct alias for
%       evolveState() (TranscriptionalRegulation.m:329-331), so a REAL,
%       full Simulation.initializeState() call WOULD consume TF-binding
%       draws on TranscriptionalRegulation's own stream before any tick.
%   - scripts/matlab/extract_per_process_traces_v2.m:176-180,1047-1053
%       The ACTUAL extraction recipe used for the genuine trace does NOT
%       call `sim.initializeState()` at all. It loads a pre-fitted,
%       already-initialized snapshot via karr_bootstrap()
%       (Simulation_fitted.mat -- itself the product of some EARLIER,
%       untracked initializeState() run, saved once to disk), then only
%       calls `seed_simulation(sim, seed)` (== `sim.applyOptions('seed',
%       seed); sim.seedRandStream();`) before entering the raw
%       evolve_state_with_tap() per-tick loop. This REPLACES whatever
%       RandStream state existed on the loaded process object with a fresh
%       `reset(seed)`, and never invokes any process's initializeState()
%       again.
%
% This probe empirically settles which of the two pictures is correct for
% THIS specific genuine trace (rather than assuming either), by capturing
% the real edu.stanford.covert.util.RandStream `.state` at each of three
% points and comparing them directly:
%   (1) immediately after karr_bootstrap() (the loaded, pre-seed state --
%       expected to be some leftover non-fresh state from whatever
%       initializeState() run produced Simulation_fitted.mat);
%   (2) immediately after the real seed_simulation-equivalent call
%       (`sim.applyOptions('seed',0); sim.seedRandStream();`) -- this is
%       the process RandStream state the genuine extraction actually
%       begins tick 1 from;
%   (3) a brand-new, independently-constructed
%       `edu.stanford.covert.util.RandStream('mcg16807'); rs.reset(0)` --
%       i.e. exactly what OC's `TxRegMcgRandStream(0)` reproduces.
% If (2) == (3) bit-for-bit, the genuine extraction's tick-1 RNG state is
% provably a fresh seed(0) reset with NO hidden pre-tick-1 draw
% consumption, and OC's existing fresh-seed replay design is already
% source-faithful (the tick-536 divergence must have a different root
% cause). If (2) != (3), the delta between them is the genuine missing
% warmup that OC must reproduce -- and this probe additionally reports the
% state (2) both raw and via a same-tick real `proc.evolveState()` call so
% the exact consumed draw count/values can be reconstructed if needed.

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
addpath(matlab_dir);

[sim, mnrnd_provider] = karr_bootstrap(); %#ok<ASGLU>

target_idx = [];
for i = 1:numel(sim.processes)
    if strcmp(sim.processes{i}.wholeCellModelID, 'Process_TranscriptionalRegulation')
        target_idx = i;
        break;
    end
end
if isempty(target_idx)
    error('probe_txreg_full_init_sequence:process_not_found', ...
        'Process_TranscriptionalRegulation not found in sim.processes');
end
proc = sim.processes{target_idx};

% --- (1) state immediately after karr_bootstrap(), before any reseed ------
state_post_bootstrap = proc.randStream.state;
fprintf('[probe] (1) post-bootstrap randStream.state: %s\n', mat2str(state_post_bootstrap));

% --- (2) state after the REAL genuine-trace-extraction seeding recipe ----
% Literal equivalent of extract_per_process_traces_v2.m's seed_simulation()
% first branch (sim.applyOptions/sim.seedRandStream both resolve on this
% object -- verified below by asserting the methods exist).
if ~(isobject(sim) && ismethod(sim, 'applyOptions') && ismethod(sim, 'seedRandStream'))
    error('probe_txreg_full_init_sequence:seed_api_missing', ...
        'sim is missing applyOptions/seedRandStream -- extraction recipe assumption invalid');
end
sim.applyOptions('seed', uint32(0));
sim.seedRandStream();
state_post_seed_simulation = proc.randStream.state;
fprintf('[probe] (2) post-seed_simulation(seed=0) randStream.state: %s\n', mat2str(state_post_seed_simulation));

% --- (3) brand-new independent RandStream('mcg16807'), reset(0) ----------
rs_fresh = edu.stanford.covert.util.RandStream('mcg16807');
rs_fresh.reset(0);
state_fresh_reset0 = rs_fresh.state;
fprintf('[probe] (3) fresh RandStream(''mcg16807'').reset(0) State: %s\n', mat2str(state_fresh_reset0));

matches_fresh = isequal(state_post_seed_simulation, state_fresh_reset0);
fprintf('[probe] (2) == (3) (no hidden pre-tick-1 warmup): %d\n', matches_fresh);

% --- Diagnostic only (not used for the verdict above): also run a REAL,
% full Simulation.initializeState() on a SEPARATE, freshly-bootstrapped sim
% to directly observe whether TranscriptionalRegulation.initializeState()
% actually fires and by how much it would move the process stream, for
% comparison/documentation purposes (this is NOT the genuine extraction's
% own recipe, since extract_per_process_traces_v2.m never calls this).
init_probe_ok = true;
init_probe_message = '';
state_post_full_init = [];
tfBoundPromoters_post_full_init = [];
enzymes_post_full_init = [];
try
    sim2 = karr_bootstrap();
    sim2.applyOptions('seed', uint32(0));
    target_idx2 = [];
    for i = 1:numel(sim2.processes)
        if strcmp(sim2.processes{i}.wholeCellModelID, 'Process_TranscriptionalRegulation')
            target_idx2 = i;
            break;
        end
    end
    proc2 = sim2.processes{target_idx2};
    sim2.initializeState();
    state_post_full_init = proc2.randStream.state;
    tfBoundPromoters_post_full_init = proc2.tfBoundPromoters;
    enzymes_post_full_init = proc2.enzymes;
    fprintf('[probe] (diagnostic) post-full-sim.initializeState() randStream.state: %s\n', mat2str(state_post_full_init));
    fprintf('[probe] (diagnostic) post-full-sim.initializeState() nnz(tfBoundPromoters): %d\n', nnz(tfBoundPromoters_post_full_init));
catch err
    init_probe_ok = false;
    init_probe_message = getReport(err, 'extended', 'hyperlinks', 'off');
    fprintf('[probe] (diagnostic) full sim.initializeState() probe FAILED: %s\n', init_probe_message);
end

scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
results = struct();
results.state_post_bootstrap = state_post_bootstrap;
results.state_post_seed_simulation = state_post_seed_simulation;
results.state_fresh_reset0 = state_fresh_reset0;
results.matches_fresh = logical(matches_fresh);
results.init_probe_ok = logical(init_probe_ok);
results.init_probe_message = init_probe_message;
results.state_post_full_init = state_post_full_init;
results.tfBoundPromoters_post_full_init_nnz = nnz(tfBoundPromoters_post_full_init);
results.enzymes_post_full_init = enzymes_post_full_init;

out_path = fullfile(repo_root, 'tmp', 'probe_txreg_full_init_sequence_result.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(results));
fclose(fid);
fprintf('[probe] wrote %s\n', out_path);

end
