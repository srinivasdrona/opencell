function probe_repinit_stage_trace_ticks39_41()
% probe_repinit_stage_trace_ticks39_41  Session N+4 decisive diagnostic
% (standalone, current-main-safe rewrite -- see
% probe_repinit_advance_to_tick.m/probe_repinit_setup.m docstrings):
% dumps REAL MATLAB's own `complexBoundSites`/`enzymes[DnaA_1mer_ATP/ADP]`
% state at EVERY stage of `evolveState()` (activateFreeDnaA,
% inactivateFreeDnaAATP, bindAndPolymerizeDnaAATP, bindAndPolymerizeDnaAADP,
% releaseDnaAAxP, reactivateFreeDnaAADP), for ticks 39, 40, and 41
% (0-based; MATLAB ticks 40, 41, 42), by calling each of
% ReplicationInitiation.m's own real, public sub-methods directly on the
% live process object, in the same order evolveState() itself uses (see
% ReplicationInitiation.m:506-529) -- producing IDENTICAL final state to
% a normal `mod.evolveState()` call (same object, same methods, same
% order, same RNG stream consumption) but additionally capturing state
% after EACH stage.
%
% Unlike the earlier wired-into-the-extractor version, the per-stage
% capture below is a plain (non-nested) local helper function returning
% one stage's struct, assembled by the caller -- never a `function
% capture(idx)` nested inside another function's body sharing its parent
% workspace, which is MATLAB-illegal in a file (like
% extract_per_process_traces_v2.m) where not every local function is
% itself `end`-terminated. This standalone file has no such constraint,
% but avoids the pattern entirely anyway for portability/clarity.

[sim, target_idx] = probe_repinit_setup('ReplicationInitiation', uint32(0));

% Advance to (0-based) tick 39 == (1-based) tick 40 with the stage-trace
% hook firing on that tick; the two subsequent ticks (41, 42, 1-based)
% are each reached by a fresh single-tick advance call from the same
% live `sim`/process state the previous call left behind.
% hook_mode='replace_evolve': local_stage_trace_probe already calls
% evolveState()'s real sub-methods directly (see its own docstring), so
% it must REPLACE mod.evolveState() for this tick, not run alongside it.
[sim, ~, stages_tick40] = probe_repinit_advance_to_tick(sim, target_idx, 40, @local_stage_trace_probe, 'replace_evolve');
[sim, ~, stages_tick41] = probe_repinit_advance_to_tick(sim, target_idx, 1, @local_stage_trace_probe, 'replace_evolve');
[~, ~, stages_tick42] = probe_repinit_advance_to_tick(sim, target_idx, 1, @local_stage_trace_probe, 'replace_evolve');

fprintf('[probe_repinit_stage_trace_ticks39_41] tick 40 (1-based):\n');
disp(stages_tick40);
fprintf('[probe_repinit_stage_trace_ticks39_41] tick 41 (1-based):\n');
disp(stages_tick41);
fprintf('[probe_repinit_stage_trace_ticks39_41] tick 42 (1-based):\n');
disp(stages_tick42);
fprintf('[probe_repinit_stage_trace_ticks39_41] done.\n');
end

function stages = local_stage_trace_probe(mod)
% local_stage_trace_probe  Sibling (non-nested) local helper: replays
% ReplicationInitiation.m's own evolveState() body stage by stage,
% capturing complexBoundSites/enzymes[DnaA_1mer_ATP/ADP] after each
% stage via local_capture_stage (also a plain sibling function, never a
% nested one).
stage_names = {
    'entering'
    'after_activateFreeDnaA'
    'after_inactivateFreeDnaAATP'
    'after_bindAndPolymerizeDnaAATP'
    'after_bindAndPolymerizeDnaAADP'
    'after_releaseDnaAAxP'
    'after_reactivateFreeDnaAADP'
};
stages = struct( ...
    'stage_name', stage_names, ...
    'complexBoundSites_positions', cell(numel(stage_names), 1), ...
    'complexBoundSites_strands', cell(numel(stage_names), 1), ...
    'complexBoundSites_values', cell(numel(stage_names), 1), ...
    'enzymes_DnaA_1mer_ATP', cell(numel(stage_names), 1), ...
    'enzymes_DnaA_1mer_ADP', cell(numel(stage_names), 1) ...
);

stages(1) = local_capture_stage(mod, stages(1));

[polATPs, polADPs] = mod.calculateDnaAR1234Polymerization();

mod.activateFreeDnaA();
stages(2) = local_capture_stage(mod, stages(2));

mod.inactivateFreeDnaAATP();
stages(3) = local_capture_stage(mod, stages(3));

if collapse(mod.chromosome.supercoiled)
    [polATPs, polADPs] = mod.bindAndPolymerizeDnaAATP(polATPs, polADPs);
    stages(4) = local_capture_stage(mod, stages(4));

    [polATPs, polADPs] = mod.bindAndPolymerizeDnaAADP(polATPs, polADPs);
    stages(5) = local_capture_stage(mod, stages(5));
else
    stages(4) = stages(3);
    stages(4).stage_name = 'after_bindAndPolymerizeDnaAATP';
    stages(5) = stages(4);
    stages(5).stage_name = 'after_bindAndPolymerizeDnaAADP';
end

mod.releaseDnaAAxP(polATPs, polADPs);
stages(6) = local_capture_stage(mod, stages(6));

mod.reactivateFreeDnaAADP();
stages(7) = local_capture_stage(mod, stages(7));
end

function stage = local_capture_stage(mod, stage)
% local_capture_stage  Plain sibling local helper -- fills in one
% pre-allocated stage struct's state fields from the live process
% object. Never nested (see this file's header docstring).
[pos, val] = find(mod.chromosome.complexBoundSites);
stage.complexBoundSites_positions = double(pos(:, 1)');
stage.complexBoundSites_strands = double(pos(:, 2)');
stage.complexBoundSites_values = double(val(:)');
stage.enzymes_DnaA_1mer_ATP = double(mod.enzymes(mod.enzymeIndexs_DnaA_1mer_ATP));
stage.enzymes_DnaA_1mer_ADP = double(mod.enzymes(mod.enzymeIndexs_DnaA_1mer_ADP));
end
