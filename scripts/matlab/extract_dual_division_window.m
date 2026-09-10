function extract_dual_division_window(seed, opts)
% extract_dual_division_window  One-pass dual-tap Cytokinesis +
% FtsZPolymerization division-window extractor.
%
% MOTIVATION (plan.md, 2026-09-03 operational handoff): Cytokinesis's own
% durable queue (extract_per_process_traces_v2.m, window_contract='anchor')
% runs one full ~31k-tick whole-cell trajectory per seed (~5h) to capture its
% division-anchored window (M_ticks preregistered in
% docs/phase_f/l2_event/division_window_spec.json -- 5000 as of the
% 2026-09-04 window fix, see STATUS_DUAL_CYT_WINDOW_FIX.md; was 4000).
% FtsZPolymerization's own driver
% (extract_ftsz_pre_division_window_seeds.m) is worse: because
% FtsZPolymerization does not own the pinchedDiameter/ftsZRing/chromosome
% witnesses Cytokinesis's own anchor search reads (see
% data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/
% +process/FtsZPolymerization.m -- no ftsZRing or chromosome property; only
% the base Process class's shared `geometry` handle), it discovers division
% completion by running a FIRST full free-running simulation
% (discover_division_completion_tick), then bootstraps a SECOND simulation
% and burns in tick_offset = completion - 200 ticks before capturing the
% final 200 (~6h50m total). Both drivers therefore each run their own full
% ~31k-tick trajectory for the SAME physical seed/division event -- Karr's
% Simulation.evolveState scheduler and RNG stream are deterministic given a
% seed, so seed 49 run under Cytokinesis's driver and seed 49 run under
% FtsZ's driver traverse an IDENTICAL tick-by-tick trajectory twice.
%
% This function runs that trajectory exactly ONCE: a single karr_bootstrap()
% call, a single seed_simulation() call, and a single per-tick scheduler
% loop (copyFromState -> resource request/allocation -> evolveState ->
% copyToState for all 28 processes, in Karr's own randperm-with-
% tRNAAminoacylation-before-Translation order -- see evolve_state_with_
% dual_tap below, structurally identical to extract_per_process_traces_v2.m's
% evolve_state_with_tap) that taps BOTH Cytokinesis and FtsZPolymerization
% at their own real scheduler positions on every tick, using two
% independently-sized rolling circular buffers:
%   Cytokinesis:        preregistered M_ticks (docs/phase_f/l2_event/
%                        division_window_spec.json, read via
%                        division_window_spec.m -- 5000 as of 2026-09-04,
%                        was 4000; ALSO mirrored into
%                        docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml's
%                        Cytokinesis row for human-readable catalog parity)
%   FtsZPolymerization:  preregistered M_ticks = 200 (same spec file,
%                        FtsZPolymerization entry; unchanged by this fix)
% Division completion is discovered SOLELY from Cytokinesis's own tap (the
% real CellGeometry.pinchedDiameter positive->zero transition, cross-checked
% against the four FtsZRing edge-count witnesses and chromosome.segregated
% -- see merge_event_observables below, duplicated verbatim from
% extract_per_process_traces_v2.m) -- NEVER derived from or read off of the
% FtsZPolymerization tap, which has no such witnesses of its own. Both
% windows end at that SAME absolute completion tick (the task's explicit
% "same real geometry pinchedDiameter completion tick" requirement for
% FtsZPolymerization): Cytokinesis's window is
% [completion-(cyt_n_ticks-1), completion], FtsZPolymerization's is
% [completion-(ftsz_n_ticks-1), completion] (cyt_n_ticks/ftsz_n_ticks read
% from division_window_spec.m at run time, see below).
%
% This is a NEW, STANDALONE script. It does not modify
% extract_per_process_traces_v2.m, extract_ftsz_pre_division_window_seeds.m,
% or their existing behavior in any way -- both remain valid, unmodified
% fallback single-process extraction paths (task requirement). Several
% small internal helpers below are intentionally duplicated verbatim from
% extract_per_process_traces_v2.m (with a comment at each call site) rather
% than refactoring that file to export them: MATLAB function files scope
% every helper function below the first `function` block as file-private,
% so there is no way to call them from a second file without either (a)
% editing that file to expose them, which the task's "existing single-
% process scripts remain unchanged" requirement forbids, or (b) duplicating
% the minimal needed subset here. Option (b) is smaller and strictly safer
% for this task's scope.
%
% Fail-closed atomic write: both output .mat files are written to sibling
% `.tmp-<token>` paths first and only `movefile`'d to their final,
% catalog-authoritative paths (data/m1_sources/karr_native/
% per_process_traces_v2_event_s{seed:03d}/{Process}_{n_ticks}ticks.mat --
% the SAME per-seed directory and filename convention every existing
% single-process extractor already uses, so the existing Python validators
% (scripts/l2_event/launcher.validate_existing_event_window,
% scripts/l2_event/ftsz_pre_division_evidence.validate_seed_window) find
% them at the exact paths they already look for) after BOTH windows pass an
% in-process completeness self-check. Any failure (capture error,
% incomplete window, self-check mismatch) deletes both temp paths and
% guarantees NEITHER final path is ever created or overwritten -- there is
% no code path by which only one of the two taps' output can be promoted to
% a canonical name while the other is missing/partial.
%
% Usage (from repo root):
%   matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window(49)"
%
% opts (optional, default struct()): max_search_ticks (default read from
% docs/phase_f/l2_event/division_window_spec.json's selection_contract via
% division_window_selection_contract().max_search_ticks -- 100000 as of
% the 2026-09-08 division-censor-contract preregistration; NEVER a
% hardcoded literal here, so a future contract revision changes every
% caller's default in one place) and force_reattempt (default false).

if nargin < 1 || isempty(seed)
    error('extract_dual_division_window:missing_seed', 'seed is required');
end
if nargin < 2 || isempty(opts)
    opts = struct();
end
if ~isfield(opts, 'max_search_ticks') || isempty(opts.max_search_ticks)
    opts.max_search_ticks = division_window_selection_contract().max_search_ticks;
end
if ~isfield(opts, 'force_reattempt') || isempty(opts.force_reattempt)
    opts.force_reattempt = false;
end

seed = uint32(seed);

this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);

cyt_process_name = 'Cytokinesis';
ftsz_process_name = 'FtsZPolymerization';
% Both M_ticks values are read from the single shared source of truth
% (docs/phase_f/l2_event/division_window_spec.json via division_window_spec.m)
% rather than hardcoded here -- see the 2026-09-04 Cytokinesis window
% preregistration fix (STATUS_DUAL_CYT_WINDOW_FIX.md).
cyt_n_ticks = division_window_spec('Cytokinesis');
ftsz_n_ticks = division_window_spec('FtsZPolymerization');

% Both processes' event-window traces live in the SAME per-seed directory,
% matching the existing single-process layout exactly (see
% scripts/l2_event/launcher.event_window_output_dir and
% scripts/l2_event/ftsz_pre_division_evidence.py's
% per_process_traces_v2_event_s{seed:03d} convention) -- a validator never
% needs to know this extraction was a dual-tap run to find either file.
out_subdir = sprintf('per_process_traces_v2_event_s%03d', seed);
out_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', out_subdir);

cyt_out_path = fullfile(out_root, sprintf('%s_%dticks.mat', cyt_process_name, cyt_n_ticks));
ftsz_out_path = fullfile(out_root, sprintf('%s_%dticks.mat', ftsz_process_name, ftsz_n_ticks));
% Per-seed atomic attempt record (division-censor-contract, 2026-09-08):
% docs/phase_f/l2_event/division_window_spec.json's selection_contract
% names this file 'division_window_attempt.json'; read via
% division_window_selection_contract() rather than hardcoded here.
attempt_record_name = division_window_selection_contract().attempt_record_filename;
attempt_record_path = fullfile(out_root, attempt_record_name);

cyt_exists = exist(cyt_out_path, 'file') == 2;
ftsz_exists = exist(ftsz_out_path, 'file') == 2;
if cyt_exists && ftsz_exists
    fprintf('[dual-extract] seed %d: both outputs already exist, skip:\n  %s\n  %s\n', ...
        seed, cyt_out_path, ftsz_out_path);
    return;
end
if cyt_exists || ftsz_exists
    % A lone existing file means either a prior partial/non-atomic write
    % escaped (should be structurally impossible given the atomic
    % finalize below) or one of the existing single-process scripts wrote
    % one of these exact paths independently. Either way this is refused,
    % never silently overwritten or silently "completed" -- see module
    % docstring on the atomic-write guarantee.
    error('extract_dual_division_window:partial_output_exists', ...
        ['seed %d has exactly one of the two dual-tap outputs already on disk -- refusing to run. ' ...
         'A genuine one-pass extraction always produces both together. Investigate and remove the ' ...
         'stray file by hand before retrying.\n  cytokinesis exists=%d: %s\n  ftsz exists=%d: %s'], ...
        seed, cyt_exists, cyt_out_path, ftsz_exists, ftsz_out_path);
end

% An existing RIGHT_CENSORED attempt record (no trace files, by the
% mutual-exclusivity invariant this contract enforces at write time --
% see write_division_window_attempt_record below) means this seed was
% already genuinely attempted and found non-completing at some prior
% max_search_ticks. Silently re-running would either (a) reproduce the
% same censored outcome at the same horizon, wasting a multi-hour
% trajectory, or (b) if max_search_ticks has since grown, could complete
% -- but that is exactly the "new, separate, reviewed action" this
% contract requires never happen silently. Refuse unless the caller
% explicitly opts in via opts.force_reattempt.
existing_attempt = read_division_window_attempt_record(attempt_record_path);
if ~isempty(existing_attempt)
    if ~strcmp(existing_attempt.status, 'RIGHT_CENSORED')
        error('extract_dual_division_window:attempt_record_status_conflict', ...
            ['seed %d has an existing attempt record at %s with unexpected status ''%s'' and no ' ...
             'matching trace files on disk -- investigate by hand before retrying'], ...
            seed, attempt_record_path, existing_attempt.status);
    end
    if ~opts.force_reattempt
        error('extract_dual_division_window:censored_attempt_exists', ...
            ['seed %d already has a RIGHT_CENSORED attempt record at %s (max_search_ticks=%d) -- ' ...
             'refusing to silently re-attempt. Pass opts.force_reattempt=true to explicitly retry ' ...
             '(e.g. under a larger max_search_ticks) after reviewing the existing record.'], ...
            seed, attempt_record_path, existing_attempt.max_search_ticks);
    end
    fprintf('[dual-extract] seed %d: opts.force_reattempt=true, removing existing RIGHT_CENSORED record %s\n', ...
        seed, attempt_record_path);
    delete(attempt_record_path);
end

if ~exist(out_root, 'dir')
    mkdir(out_root);
end

ensure_wholecell_runtime_paths(repo_root);

fprintf('[dual-extract] seed %d: single karr_bootstrap() call for BOTH taps...\n', seed);
[sim, mnrnd_provider, dnadamage_overlay] = karr_bootstrap();

[cyt_idx, cyt_canonical] = find_process_index(sim, cyt_process_name);
if isempty(cyt_idx)
    error('extract_dual_division_window:process_not_found', 'process not found: %s', cyt_process_name);
end
[ftsz_idx, ftsz_canonical] = find_process_index(sim, ftsz_process_name);
if isempty(ftsz_idx)
    error('extract_dual_division_window:process_not_found', 'process not found: %s', ftsz_process_name);
end
if cyt_idx == ftsz_idx
    error('extract_dual_division_window:duplicate_target_index', ...
        'Cytokinesis and FtsZPolymerization resolved to the same process index (%d) -- refusing to tap one process twice', cyt_idx);
end

cyt_proc = sim.processes{cyt_idx};
ftsz_proc = sim.processes{ftsz_idx};

% Cytokinesis: same performance/sufficiency exclusion
% extract_per_process_traces_v2.m applies for its own diameter_decrease
% anchor windows -- the full sparse 'chromosome' object is redundant once
% chromosome_segregated is flattened by merge_event_observables (see
% exclude_chromosome_object_for_diameter_anchor in that file; duplicated
% here as an inline setdiff since it is a single line, not a helper worth
% re-declaring).
cyt_snapshot_props = setdiff(pick_snapshot_properties(cyt_proc), {'chromosome'});
ftsz_snapshot_props = pick_snapshot_properties(ftsz_proc);
fprintf('[dual-extract] %s snapshot properties: %s\n', cyt_canonical, join_props(cyt_snapshot_props));
fprintf('[dual-extract] %s snapshot properties: %s\n', ftsz_canonical, join_props(ftsz_snapshot_props));

fprintf('[dual-extract] seed %d: single seed_simulation() call for BOTH taps...\n', seed);
seed_simulation(sim, seed);

anchor_opts = struct( ...
    'max_search_ticks', opts.max_search_ticks, ...
    'signal_kind', 'diameter_decrease', ...
    'signal_property', 'geometry', ...
    'signal_field', 'pinchedDiameter' ...
);

fprintf('[dual-extract] seed %d: single scheduler pass, dual tap (cyt window=%d ticks, ftsz window=%d ticks)...\n', ...
    seed, cyt_n_ticks, ftsz_n_ticks);
[cyt_before, cyt_after, cyt_tick_start, completion_tick, onset_tick, ...
 ftsz_before, ftsz_after, ftsz_tick_start, ok, error_message, censored] = ...
    capture_dual_anchor_windows(sim, cyt_idx, cyt_snapshot_props, cyt_n_ticks, ...
                                 ftsz_idx, ftsz_snapshot_props, ftsz_n_ticks, anchor_opts);

if ~ok
    if censored
        % Right-censoring (division-censor-contract, 2026-09-08): the
        % search exhausted the full max_search_ticks horizon without ever
        % observing a Cytokinesis division-completion tick. This is a
        % DISTINCT, dedicated outcome from every other capture failure --
        % no trace files are written (mutual exclusivity with the
        % COMPLETED case, enforced by write_division_window_attempt_record
        % below), and the caller (extract_dual_division_window_seeds.m)
        % must never fold this into its generic failed_seeds bucket.
        write_division_window_attempt_record(out_root, attempt_record_path, seed, 'RIGHT_CENSORED', ...
            struct('max_search_ticks', anchor_opts.max_search_ticks, ...
                   'mnrnd_provider', mnrnd_provider, ...
                   'dnadamage_overlay', dnadamage_overlay, ...
                   'onset_tick', [], 'completion_tick', [], ...
                   'cytokinesis_n_ticks', cyt_n_ticks, 'ftsz_n_ticks', ftsz_n_ticks, ...
                   'cytokinesis_sha256', '', 'ftsz_sha256', '', ...
                   'reason', error_message));
        error('extract_dual_division_window:right_censored', ...
            'seed %d: RIGHT_CENSORED (recorded at %s): %s', seed, attempt_record_path, error_message);
    end
    error('extract_dual_division_window:capture_failed', 'seed %d: %s', seed, error_message);
end

% Self-check (belt-and-braces on top of capture_dual_anchor_windows'
% internal invariants): both windows must end at the SAME absolute
% completion tick, and each window's own tick_start/window_anchor arithmetic
% must satisfy the M4 span contract this task requires.
if (completion_tick - cyt_tick_start + 1) ~= cyt_n_ticks
    error('extract_dual_division_window:cyt_span_mismatch', ...
        'Cytokinesis span mismatch: window_anchor(%d) - tick_start(%d) + 1 = %d, expected %d', ...
        completion_tick, cyt_tick_start, completion_tick - cyt_tick_start + 1, cyt_n_ticks);
end
if (completion_tick - ftsz_tick_start + 1) ~= ftsz_n_ticks
    error('extract_dual_division_window:ftsz_span_mismatch', ...
        'FtsZPolymerization span mismatch: window_anchor(%d) - tick_start(%d) + 1 = %d, expected %d', ...
        completion_tick, ftsz_tick_start, completion_tick - ftsz_tick_start + 1, ftsz_n_ticks);
end

% ---- Build both metadata structs (before any write happens) ---------------

cyt_metadata = struct( ...
    'process_name', cyt_canonical, ...
    'n_ticks', cyt_n_ticks, ...
    'rng_seed', seed, ...
    'tick_offset', 0, ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
    'snapshot_properties', {cyt_snapshot_props} ...
);
cyt_metadata = add_genuine_provider_metadata(cyt_metadata, mnrnd_provider);
cyt_metadata = add_dnadamage_source_metadata(cyt_metadata, dnadamage_overlay);
cyt_metadata.stride = int32(1);
cyt_metadata.tick_start = int32(cyt_tick_start);
cyt_metadata.window_anchor = int32(completion_tick);
cyt_metadata.signal_kind = anchor_opts.signal_kind;
cyt_metadata.signal_property = anchor_opts.signal_property;
cyt_metadata.signal_field = anchor_opts.signal_field;
cyt_metadata.max_search_ticks = int32(anchor_opts.max_search_ticks);
cyt_metadata.event_observable_projection_version = int32(2);
if ~isempty(onset_tick)
    cyt_metadata.onset_tick = int32(onset_tick);
end
% Dual-tap provenance (additive; no existing validator reads these, and no
% existing validator rejects unknown metadata keys -- see
% window_loader.load_event_window, which only checks the specific named
% keys it requires).
cyt_metadata.dual_tap_extractor = 'extract_dual_division_window';
cyt_metadata.dual_tap_partner_process = ftsz_canonical;
cyt_metadata.dual_tap_partner_n_ticks = int32(ftsz_n_ticks);
cyt_metadata.dual_tap_partner_tick_start = int32(ftsz_tick_start);

ftsz_metadata = struct( ...
    'process_name', ftsz_canonical, ...
    'n_ticks', ftsz_n_ticks, ...
    'rng_seed', seed, ...
    'tick_offset', 0, ...
    'timestamp', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
    'snapshot_properties', {ftsz_snapshot_props} ...
);
ftsz_metadata = add_genuine_provider_metadata(ftsz_metadata, mnrnd_provider);
ftsz_metadata = add_dnadamage_source_metadata(ftsz_metadata, dnadamage_overlay);
ftsz_metadata.stride = int32(1);
ftsz_metadata.tick_start = int32(ftsz_tick_start);
% Task requirement: FtsZPolymerization's window ends at the SAME real
% geometry pinchedDiameter completion tick as Cytokinesis's -- never a
% separately-discovered or fabricated value.
ftsz_metadata.window_anchor = int32(completion_tick);
% Provenance only (never validated by ftsz_pre_division_evidence.
% validate_seed_window, which does not check signal_kind/property/field):
% documents that this window's anchor was measured via Cytokinesis's own
% tap, not FtsZPolymerization's -- FtsZPolymerization has no
% pinchedDiameter/ftsZRing/chromosome properties of its own (see module
% docstring).
ftsz_metadata.signal_kind = anchor_opts.signal_kind;
ftsz_metadata.signal_property = anchor_opts.signal_property;
ftsz_metadata.signal_field = anchor_opts.signal_field;
ftsz_metadata.max_search_ticks = int32(anchor_opts.max_search_ticks);
ftsz_metadata.event_observable_projection_version = int32(2);
ftsz_metadata.signal_source_process = cyt_canonical;
ftsz_metadata.dual_tap_extractor = 'extract_dual_division_window';
ftsz_metadata.dual_tap_partner_process = cyt_canonical;
ftsz_metadata.dual_tap_partner_n_ticks = int32(cyt_n_ticks);
ftsz_metadata.dual_tap_partner_tick_start = int32(cyt_tick_start);
if ~isempty(onset_tick)
    ftsz_metadata.dual_tap_partner_onset_tick = int32(onset_tick);
end

% ---- Atomic fail-closed write: both temp files first, self-check, THEN
% both movefile calls. If either write or either self-check fails, both
% temp paths are removed and NEITHER final path is touched. -------------

token = dual_tap_temp_token();
cyt_tmp_path = fullfile(out_root, sprintf('.tmp-%s-%s_%dticks.mat', token, cyt_process_name, cyt_n_ticks));
ftsz_tmp_path = fullfile(out_root, sprintf('.tmp-%s-%s_%dticks.mat', token, ftsz_process_name, ftsz_n_ticks));

cleanup_temps = onCleanup(@() remove_if_exists({cyt_tmp_path, ftsz_tmp_path}));

states_before = cyt_before; %#ok<NASGU>
states_after = cyt_after; %#ok<NASGU>
metadata = cyt_metadata; %#ok<NASGU>
save(cyt_tmp_path, 'states_before', 'states_after', 'metadata', '-v7.3');

states_before = ftsz_before; %#ok<NASGU>
states_after = ftsz_after; %#ok<NASGU>
metadata = ftsz_metadata; %#ok<NASGU>
save(ftsz_tmp_path, 'states_before', 'states_after', 'metadata', '-v7.3');

verify_temp_output(cyt_tmp_path, cyt_process_name, cyt_n_ticks, seed);
verify_temp_output(ftsz_tmp_path, ftsz_process_name, ftsz_n_ticks, seed);

% Both temp files verified -- promote both together. movefile within the
% same volume is atomic per-file on Windows/NTFS and POSIX filesystems; the
% only remaining (unavoidable) non-atomicity is the gap BETWEEN these two
% movefile calls. If the process dies in that gap, the next run's
% cyt_exists/ftsz_exists guard above refuses to proceed (never silently
% completes with a mismatched pair) and reports exactly which of the two
% survived, so the stray file can be inspected/removed by hand rather than
% silently reused.
movefile(cyt_tmp_path, cyt_out_path);
movefile(ftsz_tmp_path, ftsz_out_path);

% Atomic per-seed COMPLETED attempt record (division-censor-contract,
% 2026-09-08), written AFTER both trace files are already safely
% promoted -- paired trace hashes are computed from the FINAL on-disk
% files, never the temp paths, so the record can never describe bytes
% that did not actually get promoted.
write_division_window_attempt_record(out_root, attempt_record_path, seed, 'COMPLETED', ...
    struct('max_search_ticks', anchor_opts.max_search_ticks, ...
           'mnrnd_provider', mnrnd_provider, ...
           'dnadamage_overlay', dnadamage_overlay, ...
           'onset_tick', onset_tick, 'completion_tick', completion_tick, ...
           'cytokinesis_n_ticks', cyt_n_ticks, 'ftsz_n_ticks', ftsz_n_ticks, ...
           'cytokinesis_sha256', sha256_of_file_dual(cyt_out_path), ...
           'ftsz_sha256', sha256_of_file_dual(ftsz_out_path), ...
           'reason', ''));

fprintf('[dual-extract] seed %d DONE:\n  %s (tick_start=%d, window_anchor=%d, onset_tick=%s)\n  %s (tick_start=%d, window_anchor=%d)\n', ...
    seed, cyt_out_path, cyt_tick_start, completion_tick, mat2str(onset_tick), ...
    ftsz_out_path, ftsz_tick_start, completion_tick);
end

% =============================================================================
% Core dual-tap scheduler loop
% =============================================================================

function [states_before_a, states_after_a, tick_start_a, completion_tick, onset_tick, ...
          states_before_b, states_after_b, tick_start_b, ok, error_message, censored] = ...
    capture_dual_anchor_windows(sim, idx_a, props_a, n_ticks_a, idx_b, props_b, n_ticks_b, anchor_opts)
% capture_dual_anchor_windows  Single free-running pass tapping TWO target
% processes (idx_a, idx_b) at their own real scheduler positions on every
% tick, maintaining two independently-sized rolling circular buffers.
%
% Division completion is detected SOLELY from process A's (Cytokinesis's)
% before/after tap -- via merge_event_observables, duplicated verbatim from
% extract_per_process_traces_v2.m -- using the exact same onset/completion
% predicates as that file's capture_anchor_window: onset is the first tick
% where before.pinchedDiameter > after.pinchedDiameter >= 0; completion is
% the first tick where before.pinchedDiameter > 0 and after.pinchedDiameter
% == 0. Process B (FtsZPolymerization) is tapped identically (same
% copyFromState -> resource request/allocation -> evolveState -> copyToState
% scheduler position) but contributes NO signal to onset/completion
% detection -- it has no pinchedDiameter/ftsZRing/chromosome properties of
% its own (see module docstring).
%
% Fails loudly (ok=false) rather than emit an incomplete window when: no
% completion is ever observed within anchor_opts.max_search_ticks;
% completion occurs before a full n_ticks_a (the larger of the two) window
% could be collected; no onset was observed; or the observed onset does not
% strictly precede tick_start_a..completion. There is no fallback that
% invents an onset or completion, matching capture_anchor_window's
% contract exactly.
%
% `censored` (new output, division-censor-contract, 2026-09-08) is true
% ONLY for the first of those failure modes (the search exhausted the
% entire max_search_ticks budget without ever observing a completion
% tick) -- the one genuine right-censoring outcome, where the seed's real
% trajectory may still complete beyond this horizon and no data quality
% problem is implicated. It is false (the default) for every other
% ok=false path, INCLUDING the mid-loop scheduler-crash path and every
% post-completion consistency failure (span-too-short, missing onset,
% onset not strictly preceding tick_start/completion) -- those seeds DID
% reach a completion tick (or crashed outright), so they are never
% right-censoring; they are genuine errors that must propagate as hard
% failures, never silently reclassified as censored.
ok = true;
error_message = '';
censored = false;
onset_tick = [];
completion_tick = [];
tick_start_a = [];
tick_start_b = [];
states_before_a = struct();
states_after_a = struct();
states_before_b = struct();
states_after_b = struct();

buffer_before_a = cell(n_ticks_a, 1);
buffer_after_a = cell(n_ticks_a, 1);
buffer_before_b = cell(n_ticks_b, 1);
buffer_after_b = cell(n_ticks_b, 1);
next_slot_a = 1;
next_slot_b = 1;

t = 0;
while t < anchor_opts.max_search_ticks
    t = t + 1;
    try
        [sim, before_a, after_a, before_b, after_b] = ...
            evolve_state_with_dual_tap(sim, idx_a, props_a, idx_b, props_b, anchor_opts);
    catch err
        ok = false;
        error_message = sprintf('dual anchor search tick %d failed:\n%s', t, getReport(err, 'extended', 'hyperlinks', 'off'));
        return;
    end

    slot_a = mod(next_slot_a - 1, n_ticks_a) + 1;
    buffer_before_a{slot_a} = before_a;
    buffer_after_a{slot_a} = after_a;
    next_slot_a = next_slot_a + 1;

    slot_b = mod(next_slot_b - 1, n_ticks_b) + 1;
    buffer_before_b{slot_b} = before_b;
    buffer_after_b{slot_b} = after_b;
    next_slot_b = next_slot_b + 1;

    % Completion/onset detection reads ONLY process A's (Cytokinesis's) tap
    % -- process B (FtsZPolymerization) never contributes to this decision
    % (see function docstring).
    before_val = before_a.pinchedDiameter;
    after_val = after_a.pinchedDiameter;
    is_onset_tick = (before_val > after_val) && (after_val >= 0);
    is_completion_tick = (before_val > 0) && (after_val == 0);

    if isempty(onset_tick) && is_onset_tick
        onset_tick = t;
    end

    if is_completion_tick
        completion_tick = t;
        break;
    end
end

if isempty(completion_tick)
    ok = false;
    censored = true;
    error_message = sprintf( ...
        ['division-completion signal did not fire within max_search_ticks=%d ticks -- refusing to ' ...
         'fabricate a window_anchor; either raise anchor_opts.max_search_ticks or this seed genuinely ' ...
         'does not complete in that many ticks'], anchor_opts.max_search_ticks);
    return;
end

if completion_tick < n_ticks_a
    ok = false;
    error_message = sprintf( ...
        ['completion observed at tick %d, before a full n_ticks_a=%d Cytokinesis window could be ' ...
         'collected -- refusing to emit a timing-incomplete file'], completion_tick, n_ticks_a);
    return;
end
% n_ticks_a > n_ticks_b is a documented invariant of the preregistered
% division_window_spec.json values (Cytokinesis M_ticks strictly exceeds
% FtsZPolymerization's) -- the Cytokinesis completeness check above
% therefore always subsumes the FtsZPolymerization one, but this is checked
% so a future catalog change that inverted the relationship could never
% silently emit an incomplete FtsZPolymerization window.
if completion_tick < n_ticks_b
    ok = false;
    error_message = sprintf( ...
        ['completion observed at tick %d, before a full n_ticks_b=%d FtsZPolymerization window could ' ...
         'be collected -- refusing to emit a timing-incomplete file'], completion_tick, n_ticks_b);
    return;
end

if isempty(onset_tick)
    ok = false;
    error_message = 'no real strict pinchedDiameter decrease (onset) was observed before completion -- refusing to fabricate onset_tick';
    return;
end
tick_start_a = completion_tick - n_ticks_a + 1;
tick_start_b = completion_tick - n_ticks_b + 1;
if onset_tick < tick_start_a
    ok = false;
    error_message = sprintf( ...
        'onset_tick=%d precedes the captured Cytokinesis window start tick_start=%d (n_ticks_a too short to contain the real onset)', ...
        onset_tick, tick_start_a);
    return;
end
if onset_tick >= completion_tick
    ok = false;
    error_message = sprintf('onset_tick=%d does not strictly precede completion=%d', onset_tick, completion_tick);
    return;
end

states_before_a = replay_circular_buffer(buffer_before_a, next_slot_a, n_ticks_a);
states_after_a = replay_circular_buffer(buffer_after_a, next_slot_a, n_ticks_a);
states_before_b = replay_circular_buffer(buffer_before_b, next_slot_b, n_ticks_b);
states_after_b = replay_circular_buffer(buffer_after_b, next_slot_b, n_ticks_b);
end

function out = replay_circular_buffer(buffer, next_slot, n_ticks)
% replay_circular_buffer  Chronological (tick_start..window_anchor order)
% flattening of a circular per-tick snapshot buffer into a states_before/
% states_after-shaped struct-of-cell-arrays. Duplicated logic from
% capture_anchor_window's own buffer replay in extract_per_process_traces_v2.m
% (that file inlines this once per call; here it is factored into a helper
% since capture_dual_anchor_windows calls it four times -- once each for
% buffer_before_a/after_a/before_b/after_b).
out = struct();
oldest_slot = mod(next_slot - 1, n_ticks) + 1;
for k = 1:n_ticks
    src_slot = mod(oldest_slot - 1 + (k - 1), n_ticks) + 1;
    src_fields = fieldnames(buffer{src_slot});
    for p = 1:numel(src_fields)
        fn = src_fields{p};
        if ~isfield(out, fn)
            out.(fn) = cell(n_ticks, 1);
        end
        out.(fn){k, 1} = buffer{src_slot}.(fn);
    end
end
end

function [sim, before_a, after_a, before_b, after_b] = ...
    evolve_state_with_dual_tap(sim, idx_a, props_a, idx_b, props_b, anchor_opts)
% evolve_state_with_dual_tap  One tick of the allocator-correct scheduler
% loop, tapping TWO target processes' properties immediately before/after
% each of their own evolveState() calls within the SAME tick.
%
% Structurally identical to extract_per_process_traces_v2.m's
% evolve_state_with_tap (duplicated verbatim below, generalized from one
% target_idx to two) -- see that function's docstring for the allocator/
% scheduler semantics this preserves exactly: copyFromState ->
% calcResourceRequirements_Current() (all processes) -> proportional
% allocation -> Karr's own randperm-with-tRNAAminoacylation-before-
% Translation evaluation order -> per-process copyFromState -> evolveState
% -> copyToState, with side effects and metabolite pool reconciliation
% applied identically. Only process A's (Cytokinesis's) tap is enriched
% via merge_event_observables (anchor_opts) -- process B
% (FtsZPolymerization) never receives the event-observable projection
% because it has no pinchedDiameter/ftsZRing/chromosome properties of its
% own (see module docstring); its tap is a plain snapshot_from_process
% call, identical to a fixed-window (non-anchor) capture in the
% single-process extractor.
before_a = empty_snapshot_struct(props_a);
after_a = empty_snapshot_struct(props_a);
before_b = empty_snapshot_struct(props_b);
after_b = empty_snapshot_struct(props_b);

time = sim.state_time;
mets = sim.state_metabolite;
stim = sim.state_stimulus;

time.values = time.values + sim.stepSizeSec;
stim.values = edu.stanford.covert.cell.sim.constant.Condition.applyConditions( ...
    stim.values, stim.setValues, time.values);

processes = sim.processes;
nProcesses = numel(processes);
rna_decay_idx = sim.processIndex('RNADecay');
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
        % Guard against negative RNA counts propagating into weighted sampling.
        mod.RNAs = max(0, mod.RNAs);
    end

    if proc_idx == idx_a
        before_a = snapshot_from_process(mod, props_a);
        before_a = merge_event_observables(before_a, mod, anchor_opts);
    elseif proc_idx == idx_b
        before_b = snapshot_from_process(mod, props_b);
    end

    mod.evolveState();

    if proc_idx == idx_a
        after_a = snapshot_from_process(mod, props_a);
        after_a = merge_event_observables(after_a, mod, anchor_opts);
    elseif proc_idx == idx_b
        after_b = snapshot_from_process(mod, props_b);
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

% =============================================================================
% Small helpers duplicated verbatim from extract_per_process_traces_v2.m
% (file-private in that file; see module docstring for why duplication,
% not refactor, is the correct choice here).
% =============================================================================

function props = pick_snapshot_properties(proc)
props = intersect(properties(proc), { ...
    'substrates', 'enzymes', 'boundEnzymes', 'chromosome', ...
    'freeRNAs', 'aminoacylatedRNAs', ...
    'mRNAs', 'freeTRNAs', 'freeTMRNA', ...
    'aminoacylatedTRNAs', 'aminoacylatedTMRNA', 'boundTMRNA', ...
    'unprocessedRNAs', 'processedRNAs', 'intergenicRNAs', ...
    'unmodifiedRNAs', 'modifiedRNAs', ...
    'unprocessedMonomers', 'processedMonomers', ...
    'signalSequenceMonomers', ...
    'unmodifiedMonomers', 'modifiedMonomers', ...
    'unfoldedMonomers', 'foldedMonomers', ...
    'unfoldedComplexs', 'foldedComplexs', ...
    'inactiveMonomers', 'matureMonomers', ...
    'inactiveComplexs', 'matureComplexs', ...
    'complexs', 'monomers', 'rnas', 'RNAs', ...
});
end

function snapshot = merge_event_observables(snapshot, mod, anchor_opts)
% merge_event_observables  Duplicated verbatim (signal_kind='diameter_decrease'
% branch only -- this extractor never uses 'boolean_transition') from
% extract_per_process_traces_v2.m. See that file for the full docstring;
% the two-step validated-temporary dereference pattern (container = mod.
% (container_name); ... container.pinchedDiameter) is preserved exactly.
container_name = anchor_opts.signal_property;
if ~isprop(mod, container_name)
    error('extract_dual_division_window:missing_signal_container', ...
        'process has no property ''%s'' (dual-tap anchor detection requires a real, readable signal container)', ...
        container_name);
end
container = mod.(container_name);  % validated temporary -- first dereference

if ~isprop(container, 'pinchedDiameter')
    error('extract_dual_division_window:missing_diameter_field', ...
        '''%s'' has no ''pinchedDiameter'' property', container_name);
end
snapshot.pinchedDiameter = double(container.pinchedDiameter);  % second dereference

if ~isprop(mod, 'ftsZRing')
    error('extract_dual_division_window:missing_ftszring', ...
        'process has no ''ftsZRing'' property required for dual-tap anchor detection witnesses');
end
ring = mod.ftsZRing;  % validated temporary
ring_fields = {'numEdgesOneStraight', 'numEdgesTwoStraight', 'numEdgesTwoBent', 'numResidualBent'};
for k = 1:numel(ring_fields)
    fn = ring_fields{k};
    if ~isprop(ring, fn)
        error('extract_dual_division_window:missing_ring_field', 'FtsZRing has no ''%s'' property', fn);
    end
    snapshot.(['ftsZRing_' fn]) = double(ring.(fn));
end

if ~isprop(mod, 'chromosome')
    error('extract_dual_division_window:missing_chromosome', ...
        'process has no ''chromosome'' property required for dual-tap anchor detection witnesses');
end
chrom = mod.chromosome;  % validated temporary
if ~isprop(chrom, 'segregated')
    error('extract_dual_division_window:missing_chromosome_field', ...
        'chromosome has no ''segregated'' property');
end
snapshot.chromosome_segregated = logical(chrom.segregated);  % second dereference
end

function out = snapshot_from_process(proc, snapshot_props)
out = struct();
for p = 1:numel(snapshot_props)
    prop = snapshot_props{p};
    out.(prop) = sanitize_snapshot_value(proc.(prop), 0);
end
end

function out = empty_snapshot_struct(snapshot_props)
out = struct();
for p = 1:numel(snapshot_props)
    out.(snapshot_props{p}) = [];
end
end

function out = sanitize_snapshot_value(v, depth)
if depth > 4
    out = '<MAX_DEPTH>';
    return;
end

if isnumeric(v) || islogical(v) || ischar(v) || isstring(v)
    out = v;
    return;
end

if iscell(v)
    out = cell(size(v));
    for i = 1:numel(v)
        out{i} = sanitize_snapshot_value(v{i}, depth + 1);
    end
    return;
end

if isstruct(v)
    out = struct();
    fns = fieldnames(v);
    for i = 1:numel(fns)
        fn = fns{i};
        try
            out.(fn) = sanitize_snapshot_value(v.(fn), depth + 1);
        catch
            out.(fn) = '<field-unreadable>';
        end
    end
    return;
end

if isobject(v)
    cls = class(v);
    if strcmp(cls, 'edu.stanford.covert.cell.sim.state.Chromosome')
        try
            out = serialize_chromosome_state(v);
            return;
        catch err
            out = struct('error', sprintf('serialize_chromosome_state failed: %s', err.message), 'class', cls);
            return;
        end
    end
    out = sprintf('<object:%s>', cls);
    return;
end

out = sprintf('<unsupported:%s>', class(v));
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

function [idx, canonical_name] = find_process_index(sim, requested_name)
idx = [];
canonical_name = '';
want = normalize_name_token(requested_name);

for i = 1:numel(sim.processes)
    proc = sim.processes{i};
    short = process_short_name(proc);
    tokens = { ...
        normalize_name_token(short), ...
        normalize_name_token(proc.wholeCellModelID) ...
    };
    if isprop(proc, 'name')
        tokens{end + 1} = normalize_name_token(proc.name); %#ok<AGROW>
    end
    if any(strcmp(tokens, want))
        idx = i;
        canonical_name = short;
        return;
    end
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

function token = normalize_name_token(s)
token = lower(regexprep(char(s), '[^a-zA-Z0-9]', ''));
end

function ensure_wholecell_runtime_paths(repo_root)
candidate_roots = { ...
    fullfile(repo_root, 'data', 'm1_sources', 'WholeCell'), ...
    'E:\opencell\data\m1_sources\WholeCell' ...
};

for i = 1:numel(candidate_roots)
    root = candidate_roots{i};
    if ~exist(root, 'dir')
        continue;
    end

    old_dir = pwd;
    cleaner = onCleanup(@() cd(old_dir)); %#ok<NASGU>
    cd(root);

    if exist('setWarnings.m', 'file') == 2
        try
            setWarnings();
        catch
        end
    end

    if exist('setPath.m', 'file') == 2
        try
            setPath();
            return;
        catch
        end
    end

    addpath(genpath(fullfile(root, 'src')));
    addpath(genpath(fullfile(root, 'lib')));
    return;
end
end

function s = join_props(props)
if isempty(props)
    s = '(none)';
    return;
end
s = props{1};
for i = 2:numel(props)
    s = [s ', ' props{i}]; %#ok<AGROW>
end
end

% =============================================================================
% Genuine-provider metadata + atomic-write helpers (new to this file)
% =============================================================================

function metadata = add_genuine_provider_metadata(metadata, mnrnd_provider)
% add_genuine_provider_metadata  Same five mnrnd_provider_* fields plus
% statistics_rng_provider_identity_json that extract_per_process_traces_v2.m
% writes for its own 'fixed'/'anchor' traces (see that file's
% "Genuine Statistics-Toolbox provider identity binding" comment) --
% required by launcher.validate_existing_event_window's genuine-provider
% identity-binding check for every event-window trace, regardless of which
% extractor produced it.
metadata.mnrnd_provider_kind = mnrnd_provider.kind;
metadata.mnrnd_provider_matlab_release = mnrnd_provider.matlab_release;
metadata.mnrnd_provider_toolbox_version = mnrnd_provider.toolbox_version;
metadata.mnrnd_provider_path_relative_to_matlabroot = mnrnd_provider.provider_path_relative_to_matlabroot;
metadata.mnrnd_provider_sha256 = mnrnd_provider.sha256_lf_normalized;
metadata.statistics_rng_provider_identity_json = mnrnd_provider.identity_json;
end

function metadata = add_dnadamage_source_metadata(metadata, dnadamage_overlay)
% add_dnadamage_source_metadata  Full-simulation source-hash binding
% (decisions/dec-005, 2026-09-04 Cytokinesis window fix): records which
% DNADamage.m source variant (original vs. signed-zero-overlay-patched)
% was actually resolved for THIS bootstrap's whole-simulation trajectory.
%
% Unlike extract_per_process_traces_v2.m's identical-looking fields (see
% that file's "if strcmp(canonical_name, 'DNADamage')" gate), this dual
% extractor writes these fields UNCONDITIONALLY for BOTH Cytokinesis and
% FtsZPolymerization output -- DNADamage participates in the shared
% 28-process scheduler every tick (calcResourceRequirements_Current /
% evolveState run for every process, not just the one being tapped), so
% its source version affects Cytokinesis's and FtsZPolymerization's real
% trajectories even though neither process's OWN source file changed. A
% 2026-09-04 Opus review found that a fresh dual-tap seed-36 re-run and an
% independently-generated conventional seed-36 trace disagreed on real
% onset/completion specifically because they had resolved DIFFERENT
% DNADamage.m sources (this worktree's overlay-aware karr_bootstrap.m vs.
% an older pre-overlay checkout) -- not run-to-run nondeterminism. Writing
% this identity into every dual-tap output lets
% scripts/l2_event/launcher.py's validate_existing_event_window and
% scripts/l2_event/validate_dual_division_canary.py's cross-check catch
% that exact confound mechanically, instead of requiring a manual review.
metadata.dnadamage_source_original_sha256 = dnadamage_overlay.source_sha256_lf_normalized;
metadata.dnadamage_source_patched_sha256 = dnadamage_overlay.patched_sha256_lf_normalized;
metadata.dnadamage_source_resolved_sha256 = dnadamage_overlay.resolved_sha256_lf_normalized;
metadata.dnadamage_source_resolved_path = dnadamage_overlay.resolved_path;
metadata.dnadamage_overlay_required = logical(dnadamage_overlay.overlay_required);
end

function token = dual_tap_temp_token()
% dual_tap_temp_token  Unique per-run temp-file token (PID + timestamp),
% mirroring scripts/l2_event/launcher.py's temp_regen_token() convention
% (used there for the identical purpose: a not-yet-validated regeneration
% output must never collide with a concurrent job's temp path).
token = sprintf('%d_%s', feature('getpid'), datestr(now, 'yyyymmddTHHMMSSFFF'));
end

function remove_if_exists(paths)
% remove_if_exists  onCleanup helper: best-effort delete of every path in
% the cell array (no error if a path was already moved/renamed away by a
% successful movefile, or never created because an earlier step failed
% first).
for i = 1:numel(paths)
    p = paths{i};
    if exist(p, 'file') == 2
        try
            delete(p);
        catch
        end
    end
end
end

function verify_temp_output(tmp_path, expected_process_name, expected_n_ticks, expected_seed)
% verify_temp_output  In-process completeness self-check on a just-written
% temp .mat file, performed BEFORE either movefile call (see the atomic
% fail-closed write section in the main function). Re-opens the file with
% `load` (not merely trusting the in-memory struct that was just saved) so
% a `save` that silently truncated or corrupted the file on disk is caught
% here rather than surfacing only when a downstream Python validator opens
% it later.
if exist(tmp_path, 'file') ~= 2
    error('extract_dual_division_window:temp_write_missing', 'expected temp output was not created: %s', tmp_path);
end
loaded = load(tmp_path, 'states_before', 'states_after', 'metadata');
if ~isfield(loaded, 'metadata') || ~isfield(loaded, 'states_before') || ~isfield(loaded, 'states_after')
    error('extract_dual_division_window:temp_write_incomplete', ...
        'temp output %s is missing states_before/states_after/metadata', tmp_path);
end
metadata = loaded.metadata;
if ~isfield(metadata, 'process_name') || ~strcmp(char(metadata.process_name), expected_process_name)
    error('extract_dual_division_window:temp_process_name_mismatch', ...
        'temp output %s has unexpected metadata.process_name (expected %s)', tmp_path, expected_process_name);
end
if ~isfield(metadata, 'n_ticks') || double(metadata.n_ticks) ~= double(expected_n_ticks)
    error('extract_dual_division_window:temp_n_ticks_mismatch', ...
        'temp output %s has unexpected metadata.n_ticks (expected %d)', tmp_path, expected_n_ticks);
end
if ~isfield(metadata, 'rng_seed') || double(metadata.rng_seed) ~= double(expected_seed)
    error('extract_dual_division_window:temp_rng_seed_mismatch', ...
        'temp output %s has unexpected metadata.rng_seed (expected %d)', tmp_path, expected_seed);
end
if ~isfield(metadata, 'window_anchor') || isfield(metadata, 'tick_end')
    error('extract_dual_division_window:temp_window_kind_mismatch', ...
        'temp output %s must carry metadata.window_anchor and must NOT carry metadata.tick_end (anchor-kind window)', tmp_path);
end
snapshot_props = metadata.snapshot_properties;
for p = 1:numel(snapshot_props)
    fn = snapshot_props{p};
    if ~isfield(loaded.states_before, fn) || numel(loaded.states_before.(fn)) ~= double(expected_n_ticks)
        error('extract_dual_division_window:temp_states_before_incomplete', ...
            'temp output %s states_before.%s does not have exactly n_ticks=%d rows', tmp_path, fn, expected_n_ticks);
    end
    if ~isfield(loaded.states_after, fn) || numel(loaded.states_after.(fn)) ~= double(expected_n_ticks)
        error('extract_dual_division_window:temp_states_after_incomplete', ...
            'temp output %s states_after.%s does not have exactly n_ticks=%d rows', tmp_path, fn, expected_n_ticks);
    end
end
end

function record = read_division_window_attempt_record(attempt_record_path)
% read_division_window_attempt_record  Return the parsed
% division_window_attempt.json struct for this seed's out_root, or []
% (empty double, MATLAB's canonical "absent" sentinel) if no such file
% exists yet. Fails loudly (error(), never a silent []) if the file
% exists but is not valid JSON or is missing the 'status' field --
% mirrors division_window_spec.m's fail-closed discipline.
if exist(attempt_record_path, 'file') ~= 2
    record = [];
    return;
end
raw = fileread(attempt_record_path);
try
    record = jsondecode(raw);
catch err
    error('extract_dual_division_window:attempt_record_invalid_json', ...
        'existing attempt record at %s is not valid JSON: %s', attempt_record_path, err.message);
end
if ~isfield(record, 'status')
    error('extract_dual_division_window:attempt_record_missing_status', ...
        'existing attempt record at %s has no ''status'' field', attempt_record_path);
end
end

function write_division_window_attempt_record(out_root, attempt_record_path, seed, status, fields)
% write_division_window_attempt_record  Atomic (temp-then-movefile) writer
% for one seed's division_window_attempt.json (division-censor-contract,
% 2026-09-08, docs/phase_f/l2_event/division_window_spec.json's
% selection_contract). `status` must be 'COMPLETED' or 'RIGHT_CENSORED'.
%
% Mutual exclusivity (enforced HERE, not merely by caller discipline):
%   COMPLETED       requires BOTH fields.cytokinesis_sha256 and
%                   fields.ftsz_sha256 to be non-empty strings (the two
%                   trace files must already have been promoted to their
%                   final paths by the caller before this function is
%                   invoked -- see the main function's call site, which
%                   only calls this AFTER both movefile calls succeed).
%   RIGHT_CENSORED  requires BOTH hashes to be empty AND requires that
%                   NEITHER of this seed's two trace file paths exists on
%                   disk at call time -- a censor record next to real
%                   trace bytes would be a direct contradiction this
%                   function refuses to persist.
% Any other combination raises rather than writing an inconsistent record.
if ~exist(out_root, 'dir')
    mkdir(out_root);
end

cyt_trace_present = ~isempty(fields.cytokinesis_sha256);
ftsz_trace_present = ~isempty(fields.ftsz_sha256);
if strcmp(status, 'COMPLETED')
    if ~cyt_trace_present || ~ftsz_trace_present
        error('extract_dual_division_window:attempt_record_completed_missing_hash', ...
            'seed %d: COMPLETED attempt record requires both cytokinesis_sha256 and ftsz_sha256 -- got cyt=%d ftsz=%d', ...
            seed, cyt_trace_present, ftsz_trace_present);
    end
elseif strcmp(status, 'RIGHT_CENSORED')
    if cyt_trace_present || ftsz_trace_present
        error('extract_dual_division_window:attempt_record_censored_has_hash', ...
            'seed %d: RIGHT_CENSORED attempt record must not carry any trace hash -- got cyt=%d ftsz=%d', ...
            seed, cyt_trace_present, ftsz_trace_present);
    end
else
    error('extract_dual_division_window:attempt_record_unknown_status', ...
        'seed %d: unknown attempt record status ''%s'' (must be COMPLETED or RIGHT_CENSORED)', seed, status);
end

record = struct( ...
    'schema_version', int32(1), ...
    'seed', int32(seed), ...
    'status', status, ...
    'max_search_ticks', int32(fields.max_search_ticks), ...
    'extractor', 'extract_dual_division_window', ...
    'recorded_at', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
    'mnrnd_provider_sha256', fields.mnrnd_provider.sha256_lf_normalized, ...
    'dnadamage_source_resolved_sha256', fields.dnadamage_overlay.resolved_sha256_lf_normalized, ...
    'cytokinesis_n_ticks', int32(fields.cytokinesis_n_ticks), ...
    'ftsz_n_ticks', int32(fields.ftsz_n_ticks), ...
    'onset_tick', ternary_empty_to_nan(fields.onset_tick), ...
    'completion_tick', ternary_empty_to_nan(fields.completion_tick), ...
    'cytokinesis_trace_sha256', fields.cytokinesis_sha256, ...
    'ftsz_trace_sha256', fields.ftsz_sha256, ...
    'reason', fields.reason ...
);

token = dual_tap_temp_token();
tmp_path = fullfile(out_root, sprintf('.tmp-%s-%s', token, 'division_window_attempt.json'));
cleanup_tmp = onCleanup(@() remove_if_exists({tmp_path})); %#ok<NASGU>
fid = fopen(tmp_path, 'w');
if fid == -1
    error('extract_dual_division_window:attempt_record_write_failed', ...
        'seed %d: unable to open temp attempt-record path %s for writing', seed, tmp_path);
end
fwrite(fid, jsonencode(record), 'char');
fclose(fid);
movefile(tmp_path, attempt_record_path);
fprintf('[dual-extract] seed %d: wrote %s attempt record to %s\n', seed, status, attempt_record_path);
end

function out = ternary_empty_to_nan(v)
% ternary_empty_to_nan  jsonencode(struct with a [] field) silently drops
% that field's key from the JSON object entirely (MATLAB's documented
% behavior), which would make onset_tick/completion_tick disappear rather
% than read as an explicit null for a RIGHT_CENSORED record. NaN
% round-trips through jsonencode/jsondecode as the JSON literal `null`,
% which is what this contract's readers (scripts/l2_event/
% division_cohort_selector.py) expect for "not applicable".
if isempty(v)
    out = NaN;
else
    out = double(v);
end
end

function hash_hex = sha256_of_file_dual(path_value)
% sha256_of_file_dual  Local sha256 helper, named distinctly (not
% sha256_of_file/sha256OfFile) to avoid any ambiguity with the
% differently-scoped same-named local functions already present in
% reconstruct_chromosome_draw_ledger.m/extract_karr_mats.m (each MATLAB
% function file scopes its own helpers privately, so no actual collision
% is possible, but a distinct name keeps grep/reading unambiguous across
% files). Identical implementation (java.security.MessageDigest) to
% those files' own helpers.
fid = fopen(path_value, 'rb');
if fid < 0
    error('extract_dual_division_window:file_unreadable', 'could not open %s', path_value);
end
raw = fread(fid, Inf, '*uint8')';
fclose(fid);
digest = java.security.MessageDigest.getInstance('SHA-256');
digest_bytes = typecast(digest.digest(raw), 'uint8');
hash_hex = lower(sprintf('%02x', digest_bytes));
end
