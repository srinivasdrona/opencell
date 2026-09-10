function probe_repinit_tick13_candidate_universe()
% probe_repinit_tick13_candidate_universe  l21-repinit decisive
% candidate-universe/weight-parity check at tick 13 (0-based; MATLAB
% tick 14, 1-based). Thin, fixed-tick convenience wrapper around
% probe_repinit_candidate_universe_at_tick.m -- see that file's
% docstring for the full rationale and probe_repinit_advance_to_tick.m/
% probe_repinit_setup.m for why this whole family is a standalone,
% self-contained rewrite rather than a hook wired into
% extract_per_process_traces_v2.m.
probe_repinit_candidate_universe_at_tick(13);
fprintf('[probe_repinit_tick13_candidate_universe] done.\n');
end
