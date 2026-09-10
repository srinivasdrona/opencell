function reextract_repinit_200ticks_with_dnadamage_binding()
% reextract_repinit_200ticks_with_dnadamage_binding
%
% Re-extracts the canonical seed=0, 200-tick ReplicationInitiation trace
% used by every RepInit L2.1/L2.2 harness, using the corrected
% extract_per_process_traces_v2.m (this integration candidate) whose
% metadata block now writes `dnadamage_source_resolved_sha256` (and its
% `dnadamage_source_original_sha256`/`dnadamage_source_patched_sha256`/
% `dnadamage_source_resolved_path` siblings) UNCONDITIONALLY for every
% trace, not just DNADamage's own 'fixed'/'anchor' event-window traces
% (see DEC-005: decisions/dec-005-full-simulation-source-hash-binding.md,
% DEC-006: decisions/dec-006-shared-chromosome-randstream-input-oracle.md
% "Related Decisions"). This is required for
% `tests/vivarium/chromosome_rand_stream_ledger.py`'s (main's, unchanged)
% stricter loader to accept a regenerated RepInit chromosome_rand_stream
% ledger sidecar -- its `dnadamage_source_sha256` cross-check hard-fails
% if the trace has no `dnadamage_source_resolved_sha256` metadata field
% at all, which was true of every PRIOR RepInit trace extraction (plain
% window_contract='', canonical_name='ReplicationInitiation', so the
% pre-existing DNADamage-only gate never fired for it).
%
% Same extraction shape as the trace this replaced (seed=0, n_ticks=200,
% tick_offset=0, window_contract='', no anchor_opts/extraction_opts/
% probe_opts overrides) -- output path, tick count, and RNG seed
% unchanged, so every existing OC-side test/harness that reads this
% trace by path continues to work identically, now with the additional
% metadata field present.

output_subdir = 'per_process_traces_v2';
n_ticks = 200;
seed = uint32(0);
tick_offset = 0;
window_contract = '';

extract_per_process_traces_v2({'ReplicationInitiation'}, output_subdir, n_ticks, seed, tick_offset, window_contract, struct(), struct());

fprintf('[reextract_repinit_200ticks_with_dnadamage_binding] done.\n');
end
