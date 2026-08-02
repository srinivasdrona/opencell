% Driver: runs evolveState_ppii_matlab (true-verbatim, real-RandStream
% transcription of ProteinProcessingII.m evolveState) for the Scenario B
% scarcity-matrix states, using a REAL edu.stanford.covert.util.RandStream
% instance for every draw -- never a stub, never MATLAB/Octave's ambient
% global rand stream.
%
% Per Opus5's Turn 3 rejection of the Octave-stub-based Scenario B design:
% this driver requires genuine MATLAB (not Octave) plus the Statistics
% Toolbox, and ABORTS with no fallback if either is unavailable, or if
% edu.stanford.covert.util.RandStream cannot be constructed. There is no
% code path in this file that silently substitutes a stub/scaffold RNG.
%
% The WholeCell src root (containing +edu/+stanford/+covert/+util/
% RandStream.m) is read ONLY from the PPII_WHOLECELL_SRC_ROOT environment
% variable -- there is NO ambient/hardcoded fallback path (Opus5 turn-4
% correction 2). The resolved RandStream runtime path and an LF-normalized
% SHA-256 hash of that file are recorded in every state's run-manifest so
% Python can independently cross-check them against the vendored copy at
% data/karr_vendored_source/RandStream.m.
%
% Mode is selected via the PPII_SCENARIO_B_MODE environment variable:
%   'canary' -> transferase_capacity_scarce state only, its pre-registered
%               canary seed prefix (20 seeds -- widened per Opus5 turn-4
%               correction 5; still an explicit prefix/subset of that
%               state's own 50-seed full block, never a separate range)
%   'full'   -> all 5 states, each state's full pre-registered seed block
%               (50 seeds each)
%   (unset)  -> ERROR (mode must always be explicit; there is no silent
%               default, to avoid ever accidentally running the wrong
%               cardinality of evidence)
%
% Actual per-state seed lists are NOT hardcoded here -- they are read from
% each state's frozen ppii_scenario_b_<name>_prediction.json (written by
% scripts/l22_evidence/h12_perturbation.py generate-inputs-scenario-b
% BEFORE this driver ever runs, per the frozen-prediction/hash-bind
% requirement). This guarantees a single source of truth for the
% pre-registered seed schedule instead of duplicating seed-range literals
% in both Python and MATLAB source (which could silently drift out of
% sync). This driver reads the frozen seed list, but never recomputes or
% overrides it.
%
% Output CSVs use dlmwrite(...,'precision','%.17g') (Opus5 turn-4
% correction 4), NOT csvwrite, so every double (including large exact
% values like the 141888 substrates_water constant) round-trips losslessly.
%
% NOT INVOKED by anything in this commit. Execution requires explicit
% follow-up authorization: first probe_matlab_environment.m (parse/
% license/toolbox/RandStream/mnrnd-shape preflight, authorized separately),
% then this driver in 'canary' mode (Opus5 review of this code/spec
% commit), then 'full' mode (GPT-5.6 Sol authorization after canary
% review). See PERTURBATION_SPEC.json scenario_b_execution_status.
function run_ppii_scenario_b_matlab()

this_dir = fileparts(mfilename('fullpath'));
repo_root = fullfile(this_dir, '..', '..');
state_dir = fullfile(repo_root, 'data', 'm1_sources', 'karr_native', 'h12_perturbation_traces');
wholecell_src = getenv('PPII_WHOLECELL_SRC_ROOT');

% ---- Abort criteria: no stub fallback for any of these ----
if exist('OCTAVE_VERSION', 'builtin') ~= 0
    error('run_ppii_scenario_b_matlab:notMatlab', ...
        'This driver requires genuine MATLAB (Octave detected). Aborting: no stub fallback is permitted.');
end
if isempty(wholecell_src)
    error('run_ppii_scenario_b_matlab:noWholeCellSrcRoot', ...
        ['PPII_WHOLECELL_SRC_ROOT environment variable is not set. Aborting: no ambient/default ', ...
         'WholeCell src root is assumed (Opus5 turn-4 correction 2).']);
end
if license('test', 'Statistics_Toolbox') ~= 1
    error('run_ppii_scenario_b_matlab:noStatisticsToolbox', ...
        'Statistics Toolbox license unavailable. Aborting: no stub fallback is permitted.');
end
if ~isempty(ver('stats')) == false
    error('run_ppii_scenario_b_matlab:noStatisticsToolboxInstalled', ...
        'Statistics Toolbox not installed (ver(''stats'') empty). Aborting: no stub fallback is permitted.');
end
addpath(wholecell_src);
if exist('edu.stanford.covert.util.RandStream', 'class') ~= 8
    error('run_ppii_scenario_b_matlab:noKarrRandStream', ...
        'edu.stanford.covert.util.RandStream class not found on path %s. Aborting: no stub fallback is permitted.', ...
        wholecell_src);
end
import edu.stanford.covert.util.RandStream;
% Constructor smoke-test: fail fast (before any state is touched) if the
% class exists but cannot actually be constructed (e.g. wrong Statistics
% Toolbox version for the underlying builtin RandStream generator type).
try
    probeStream = RandStream('mcg16807', 'Seed', 0); %#ok<NASGU>
catch probeErr
    error('run_ppii_scenario_b_matlab:randStreamConstructionFailed', ...
        'edu.stanford.covert.util.RandStream(''mcg16807'', ''Seed'', 0) failed to construct: %s. Aborting.', ...
        probeErr.message);
end
randstream_class_confirmed = true;
% Recorded once (same for the whole driver run) so Python can
% independently cross-check the runtime RandStream against the vendored
% copy at data/karr_vendored_source/RandStream.m -- never trusting
% randstream_class_confirmed's boolean self-report alone (Opus5 turn-4
% correction 2).
randstream_runtime_path = which('edu.stanford.covert.util.RandStream');
randstream_runtime_sha256_lf_normalized = sha256_file_lf_normalized(randstream_runtime_path);

mode = getenv('PPII_SCENARIO_B_MODE');
if isempty(mode) || ~(strcmp(mode, 'canary') || strcmp(mode, 'full'))
    error('run_ppii_scenario_b_matlab:badMode', ...
        'PPII_SCENARIO_B_MODE must be set to ''canary'' or ''full'' (got ''%s'').', mode);
end

all_state_names = {'transferase_capacity_scarce', 'pg160_scarce', 'peptidase_capacity_scarce', ...
    'water_scarce', 'simultaneous_peptidase_capacity_and_water_scarce'};
if strcmp(mode, 'canary')
    state_names = {'transferase_capacity_scarce'};
else
    state_names = all_state_names;
end

harness_file = fullfile(this_dir, 'evolveState_ppii_matlab.m');
harness_sha256 = sha256_file_lf_normalized(harness_file);

for i = 1:numel(state_names)
    name = state_names{i};

    prediction_path = fullfile(state_dir, ['ppii_scenario_b_', name, '_prediction.json']);
    if exist(prediction_path, 'file') ~= 2
        error('run_ppii_scenario_b_matlab:missingFrozenPrediction', ...
            'Frozen prediction file not found: %s. Run generate-inputs-scenario-b first.', prediction_path);
    end
    prediction = jsondecode(fileread(prediction_path));
    seeds = prediction.mode_seeds.(mode);
    seeds = seeds(:)';

    state_file = fullfile(state_dir, ['ppii_scenario_b_', name, '_state.m']);
    actual_state_hash = sha256_file_lf_normalized(state_file);
    if ~strcmp(actual_state_hash, prediction.state_file_sha256)
        error('run_ppii_scenario_b_matlab:staleFrozenPrediction', ...
            ['State file %s has changed since its prediction was frozen ', ...
             '(expected sha256 %s, got %s). Re-run generate-inputs-scenario-b.'], ...
            state_file, prediction.state_file_sha256, actual_state_hash);
    end

    run(state_file);
    n_mono = numel(this0.unprocessedMonomers);
    n_sub = numel(this0.substrates);
    n_seeds = numel(seeds);
    % Leading column is the ACTUAL seed id (not a 0-based row index) so
    % ingest can cross-check the exact recorded seed set against the
    % frozen pre-registered seed schedule.
    out = zeros(n_seeds, 1 + 3 * n_mono + n_sub);

    for k = 1:n_seeds
        seed = seeds(k);
        % Independent, real Karr RandStream per (state, seed) -- never
        % the ambient global stream, never reused across states or
        % between canary/full for the same seed id.
        this = this0;
        this.randStream = RandStream('mcg16807', 'Seed', seed);
        this = evolveState_ppii_matlab(this);
        row = [this.unprocessedMonomers', this.processedMonomers', this.signalSequenceMonomers', this.substrates'];
        out(k, :) = [seed, row];
    end

    out_csv = fullfile(state_dir, ['ppii_scenario_b_', name, '_after.csv']);
    % Lossless integer/float output (Opus5 turn-4 correction 4): csvwrite
    % uses a lossy default format (e.g. would round a value like 141888
    % through %10.5g and fail to round-trip exactly); dlmwrite with
    % 'precision','%.17g' round-trips every double exactly.
    dlmwrite(out_csv, out, 'precision', '%.17g');

    manifest = struct();
    manifest.state_name = name;
    manifest.mode = mode;
    manifest.seeds = seeds;
    manifest.n_seeds = n_seeds;
    manifest.matlab_version = version();
    manifest.statistics_toolbox_licensed = true;
    manifest.randstream_class_confirmed = randstream_class_confirmed;
    manifest.wholecell_src_root_used = wholecell_src;
    manifest.randstream_runtime_path = randstream_runtime_path;
    manifest.randstream_runtime_sha256_lf_normalized = randstream_runtime_sha256_lf_normalized;
    manifest.harness_file = 'evolveState_ppii_matlab.m';
    manifest.harness_sha256_lf_normalized = harness_sha256;
    manifest.state_file_sha256_lf_normalized = actual_state_hash;
    manifest.generated_at_utc = datestr(datetime('now', 'TimeZone', 'UTC'), 'yyyy-mm-ddTHH:MM:SSZ');

    manifest_path = fullfile(state_dir, ['ppii_scenario_b_', name, '_run_manifest.json']);
    fid = fopen(manifest_path, 'w');
    fprintf(fid, '%s', jsonencode(manifest));
    fclose(fid);

    fprintf('wrote %d seeds x %d columns to ppii_scenario_b_%s_after.csv (mode=%s)\n', ...
        n_seeds, size(out, 2), name, mode);
end

end

function value = sha256_file_lf_normalized(path)
% LF-normalized SHA-256 of a text file, matching the convention used by
% scripts/l22_evidence/h12_perturbation.py's _sha256_lf_normalized (CRLF
% and lone CR both collapsed to LF before hashing) so hashes computed in
% MATLAB and Python for the same tracked/generated text file agree.
raw = fileread(path);
raw = strrep(raw, char([13 10]), char(10));
raw = strrep(raw, char(13), char(10));
bytes = uint8(raw);
md = java.security.MessageDigest.getInstance('SHA-256');
digestBytes = typecast(md.digest(bytes), 'uint8');
value = sprintf('%02x', digestBytes);
end
