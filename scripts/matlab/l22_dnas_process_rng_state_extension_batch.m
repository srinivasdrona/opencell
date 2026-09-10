function summary = l22_dnas_process_rng_state_extension_batch(varargin)
% l22_dnas_process_rng_state_extension_batch
%
% Regenerates a GENEROUSLY-SIZED, per-tick, per-seed process-owned
% (this.randStream) draw buffer directly from the exact captured
% ``process_state_before`` value already present in the committed
% chromosome-release-RNG ledger corpus
% (data/l22_dnas_rare_event/chromosome_release_rng_ledger/seed_{NNN}.json)
% -- NOT by re-running the real multi-process scheduler again (no
% karr_bootstrap() needed at all), and NOT by reverse-engineering
% mcg16807's internal state-advance formula (empirically falsified this
% session: MATLAB's real behavior does not match the standard Park-Miller
% recurrence Xn+1=(16807*Xn) mod (2^31-1) at any fixed step count, up to
% and including the well-known MINSTD reference vector test -- see
% scripts/matlab/verify_mcg16807_stepwise.m, scripts/matlab/check_minstd_reference_vector.m).
%
% Design rationale (replaces the exhausting finite process_draws list):
% a throwaway MATLAB RandStream, seeded directly to a captured
% process_state_before value, reliably and deterministically reproduces
% MATLAB's REAL subsequent draws -- this is exactly the same trust
% assumption the existing "replay-forward" reconstruction already relies
% on (it is HOW that reconstruction proves it reached the recorded
% after-state at all). This script verified that assumption explicitly
% (scripts/matlab/verify_extended_draws_match_prefix.m): drawing 500 values fresh
% from process_state_before gives a sequence whose leading
% `process_draws`-length prefix is BYTE-IDENTICAL to the already-audited
% replay-forward reconstruction, for every tick checked (10/10, seed 0).
%
% Rather than a "just enough" list sized to what one specific real MATLAB
% run happened to consume that tick (the design that exhausted whenever
% OC's own computation legitimately needed slightly more), this generates
% a FIXED, GENEROUS batch (default 1000 draws/tick -- roughly 25x the
% largest per-tick consumption observed anywhere in this investigation,
% ~40) directly from the real captured entering state. OC's own
% consumption is NOT capped at "what MATLAB happened to use that tick";
% the buffer is sized for headroom, not for exact replay of a specific
% historical run. The recorded MATLAB `process_state_after` and original
% `process_draws` length remain in the output as an AUDIT reference (not
% a hard requirement) so the previously-established exactness proof is
% never lost, just no longer treated as a ceiling.
%
% Fails loudly (does not write output, non-zero exit implied by MATLAB
% error) if any tick's audit check does not reproduce the original
% replay-forward reconstruction's prefix/after-state exactly -- this would
% indicate a genuine RandStream non-determinism or a state-capture defect,
% not a condition to paper over.
%
% Usage:
%   addpath('scripts/matlab');
%   l22_dnas_process_rng_state_extension_batch('seeds', [0 1 2], ...
%       'batch_size', 1000, ...
%       'input_ledger_dir', fullfile(pwd, 'data', 'l22_dnas_rare_event', 'chromosome_release_rng_ledger'), ...
%       'out_dir', fullfile(pwd, 'data', 'l22_dnas_rare_event', 'process_rng_state_ledger'));

opts = parse_inputs(varargin{:});

if ~exist(opts.out_dir, 'dir')
    mkdir(opts.out_dir);
end

summary = struct('seed', {}, 'n_ticks', {}, 'all_audits_ok', {});
for si = 1:numel(opts.seeds)
    seed = opts.seeds(si);
    in_path = fullfile(opts.input_ledger_dir, sprintf('seed_%03d.json', seed));
    if ~exist(in_path, 'file')
        error('l22_dnas_process_rng_state_extension_batch:missingInput', ...
            'Input ledger not found: %s', in_path);
    end
    raw = jsondecode(fileread(in_path));

    out_ticks = struct('tick_zero_based', {}, 'process_state_before', {}, ...
        'process_state_after_recorded', {}, 'recorded_draws_len', {}, ...
        'audit_prefix_match', {}, 'audit_state_after_match', {}, ...
        'batch_size', {}, 'extended_draws', {}, 'provenance_hash', {});

    all_ok = true;
    for t = 1:numel(raw.ticks)
        tick = raw.ticks(t);
        state_before = double(tick.process_state_before.values);
        state_after_recorded = double(tick.process_state_after.values);
        if isfield(tick, 'process_draws') && ~isempty(tick.process_draws)
            recorded_draws = double(tick.process_draws(:)');
        else
            recorded_draws = zeros(1, 0);
        end
        L = numel(recorded_draws);

        s = RandStream('mcg16807', 'Seed', 1);
        s.State = state_before;
        big_draws = rand(s, 1, opts.batch_size);

        if L > 0
            prefix_match = isequal(big_draws(1:L), recorded_draws);
        else
            prefix_match = true;
        end

        s2 = RandStream('mcg16807', 'Seed', 1);
        s2.State = state_before;
        if L > 0
            rand(s2, 1, L);
        end
        state_after_L = double(s2.State);
        state_after_match = isequal(state_after_L, state_after_recorded);

        if ~prefix_match || ~state_after_match
            all_ok = false;
            error('l22_dnas_process_rng_state_extension_batch:auditFailed', ...
                'seed=%d tick=%d: audit failed (prefix_match=%d, state_after_match=%d). Refusing to write an unverified extended-draws artifact.', ...
                seed, int32(tick.tick_zero_based), prefix_match, state_after_match);
        end

        provenance_payload = sprintf('%d|%d|%.17g|%.17g|%d', ...
            seed, tick.tick_zero_based, state_before, state_after_recorded, opts.batch_size);
        provenance_hash = compute_sha256(provenance_payload);

        out_ticks(end + 1) = struct( ... %#ok<AGROW>
            'tick_zero_based', int32(tick.tick_zero_based), ...
            'process_state_before', state_before, ...
            'process_state_after_recorded', state_after_recorded, ...
            'recorded_draws_len', int32(L), ...
            'audit_prefix_match', prefix_match, ...
            'audit_state_after_match', state_after_match, ...
            'batch_size', int32(opts.batch_size), ...
            'extended_draws', big_draws, ...
            'provenance_hash', provenance_hash);
    end

    seed_summary = struct();
    seed_summary.seed = int32(seed);
    seed_summary.process_name = 'DNASupercoiling';
    seed_summary.rng_type = 'mcg16807';
    seed_summary.n_ticks = int32(numel(raw.ticks));
    seed_summary.batch_size = int32(opts.batch_size);
    seed_summary.source_ledger = in_path;
    seed_summary.ticks = out_ticks;

    out_path = fullfile(opts.out_dir, sprintf('seed_%03d.json', seed));
    fid = fopen(out_path, 'w');
    if fid < 0
        error('l22_dnas_process_rng_state_extension_batch:writeFailed', 'Could not open output path: %s', out_path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(seed_summary));
    clear cleaner;
    fprintf('[l22_dnas_process_rng_state_extension_batch] seed=%d ticks=%d all_audits_ok=%d wrote %s\n', ...
        seed, numel(raw.ticks), all_ok, out_path);

    summary(end + 1) = struct('seed', int32(seed), 'n_ticks', int32(numel(raw.ticks)), 'all_audits_ok', all_ok); %#ok<AGROW>
end
end

function hash = compute_sha256(text)
md = java.security.MessageDigest.getInstance('SHA-256');
raw_bytes = typecast(md.digest(uint8(text)), 'uint8');
hash = lower(reshape(dec2hex(raw_bytes, 2)', 1, []));
end

function opts = parse_inputs(varargin)
opts = struct( ...
    'seeds', 0, ...
    'batch_size', 1000, ...
    'input_ledger_dir', '', ...
    'out_dir', '');

if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_process_rng_state_extension_batch:invalidArgs', 'Arguments must be name/value pairs');
end

for i = 1:2:numel(varargin)
    name = varargin{i};
    value = varargin{i + 1};
    switch lower(char(name))
        case 'seeds'
            opts.seeds = double(value);
        case 'batch_size'
            opts.batch_size = double(value);
        case 'input_ledger_dir'
            opts.input_ledger_dir = char(value);
        case 'out_dir'
            opts.out_dir = char(value);
        otherwise
            error('l22_dnas_process_rng_state_extension_batch:unknownOption', 'Unknown option: %s', char(name));
    end
end

repo_root = infer_repo_root();
if isempty(opts.input_ledger_dir)
    opts.input_ledger_dir = fullfile(repo_root, 'data', 'l22_dnas_rare_event', 'chromosome_release_rng_ledger');
end
if isempty(opts.out_dir)
    opts.out_dir = fullfile(repo_root, 'data', 'l22_dnas_rare_event', 'process_rng_state_ledger');
end
end

function repo_root = infer_repo_root()
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
end
