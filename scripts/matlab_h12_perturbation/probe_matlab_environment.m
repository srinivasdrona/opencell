% Standalone preflight probe for the genuine-MATLAB Scenario B execution
% environment. Performs ONLY read-only checks (MATLAB vs Octave, license,
% toolbox installation, RandStream class resolution/hash/construction,
% and a genuine-MATLAB mnrnd column-vector shape probe) and persists a
% structured JSON result -- it makes no other state changes and runs no
% ProteinProcessingII evolveState code.
%
% This is the "parse/license/toolbox/RandStream/mnrnd-shape probe" step
% GPT-5.6 Sol authorizes separately from (and strictly before) the 1x5
% canary run. Per Opus5 turn-4 corrections 1-3:
%   - the WholeCell src root is read ONLY from the PPII_WHOLECELL_SRC_ROOT
%     environment variable -- there is NO ambient/hardcoded fallback path;
%   - `which('edu.stanford.covert.util.RandStream')` and an LF-normalized
%     SHA-256 hash of that resolved file are recorded so the Python side
%     can independently cross-check them against the vendored copy at
%     data/karr_vendored_source/RandStream.m (this script does NOT do
%     that comparison itself -- it only records the runtime facts);
%   - ALL report fields are collected unconditionally (no early return),
%     the structured JSON result is ALWAYS written (even on failure),
%     and only THEN does this script call error(...) if overall_pass is
%     false, so both MATLAB's own exit code AND the JSON file agree, and
%     the JSON file is always available for Python to independently
%     re-validate (it never trusts the exit code alone either).
%
% The mnrnd(3, [0.5;0.5]) column-vector shape probe (Opus5 turn-4
% correction 1) exists because evolveState_ppii_matlab.m calls
% this.randStream.mnrnd(n, columnVector)' VERBATIM -- i.e. it passes a
% COLUMN vector `p` straight through to RandStream.mnrnd, which is itself
% a thin passthrough to the builtin mnrnd with no shape correction (see
% data/karr_vendored_source/RandStream.m:127-137). If genuine MATLAB's
% Statistics Toolbox mnrnd rejects/mishandles a column-vector p, the
% verbatim transcription would itself error at runtime. This is
% intentionally NOT fixed post hoc in evolveState_ppii_matlab.m; an
% 'error' result here is recorded as a Karr dormant-source defect that
% hard-blocks FULL-mode execution only (canary-mode plumbing runs remain
% permitted -- see h12_perturbation.py's _validate_matlab_probe_result).
%
% NOT INVOKED by anything in this commit or by run_ppii_scenario_b_matlab.m
% itself -- it is a separate, manually-run diagnostic tool.
function probe_matlab_environment()

report = struct();
report.is_octave = exist('OCTAVE_VERSION', 'builtin') ~= 0;
if report.is_octave
    report.matlab_version = getenv('OCTAVE_VERSION');
else
    report.matlab_version = version();
end

wholecell_src = getenv('PPII_WHOLECELL_SRC_ROOT');
report.wholecell_src_root_used = wholecell_src;

report.statistics_toolbox_licensed = false;
report.statistics_toolbox_installed = false;
report.randstream_class_found = false;
report.randstream_constructs = false;
report.randstream_runtime_path = '';
report.randstream_runtime_sha256_lf_normalized = '';
report.mnrnd_shape_test_status = 'not_run';
report.mnrnd_shape_test_error_message = '';
report.mnrnd_shape_test_result = [];

if report.is_octave
    fprintf('[FAIL] Running under Octave, not MATLAB. OCTAVE_VERSION=%s\n', report.matlab_version);
    fprintf('       Genuine-MATLAB Scenario B evidence cannot be generated under Octave.\n');
else
    fprintf('[ OK ] Running under genuine MATLAB, version %s\n', report.matlab_version);

    report.statistics_toolbox_licensed = license('test', 'Statistics_Toolbox') == 1;
    if report.statistics_toolbox_licensed
        fprintf('[ OK ] Statistics Toolbox license available\n');
    else
        fprintf('[FAIL] Statistics Toolbox license NOT available (license(''test'', ''Statistics_Toolbox'') == 0)\n');
    end

    statsVer = ver('stats');
    report.statistics_toolbox_installed = ~isempty(statsVer);
    if report.statistics_toolbox_installed
        fprintf('[ OK ] Statistics Toolbox installed, version %s\n', statsVer(1).Version);
    else
        fprintf('[FAIL] Statistics Toolbox NOT installed (ver(''stats'') empty)\n');
    end

    if isempty(wholecell_src)
        fprintf(['[FAIL] PPII_WHOLECELL_SRC_ROOT environment variable is not set -- no ambient/default ' ...
            'WholeCell src root is assumed (Opus5 turn-4 correction 2).\n']);
    else
        addpath(wholecell_src);
        report.randstream_class_found = exist('edu.stanford.covert.util.RandStream', 'class') == 8;
        if report.randstream_class_found
            fprintf('[ OK ] edu.stanford.covert.util.RandStream class found under root %s\n', wholecell_src);
            report.randstream_runtime_path = which('edu.stanford.covert.util.RandStream');
            report.randstream_runtime_sha256_lf_normalized = sha256_lf_normalized_file(report.randstream_runtime_path);
            fprintf('[INFO] randstream_runtime_path = %s\n', report.randstream_runtime_path);
            fprintf('[INFO] randstream_runtime_sha256_lf_normalized = %s\n', report.randstream_runtime_sha256_lf_normalized);
        else
            fprintf('[FAIL] edu.stanford.covert.util.RandStream class NOT found under root %s\n', wholecell_src);
        end

        if report.randstream_class_found
            try
                import edu.stanford.covert.util.RandStream;
                probeStream = RandStream('mcg16807', 'Seed', 0); %#ok<NASGU>
                report.randstream_constructs = true;
                fprintf('[ OK ] edu.stanford.covert.util.RandStream(''mcg16807'', ''Seed'', 0) constructed successfully\n');
            catch probeErr
                fprintf('[FAIL] edu.stanford.covert.util.RandStream construction failed: %s\n', probeErr.message);
            end
        end
    end

    % Genuine-MATLAB mnrnd column-vector shape probe -- independent of
    % WholeCell/RandStream resolution above; runs whenever we are on
    % genuine MATLAB. See the file-level comment for why this exact shape
    % (n=3, column-vector p=[0.5;0.5]) is probed and why a failure here is
    % NOT fixed post hoc in evolveState_ppii_matlab.m.
    try
        mnrnd_probe_result = mnrnd(3, [0.5; 0.5]);
        report.mnrnd_shape_test_status = 'pass';
        report.mnrnd_shape_test_result = mnrnd_probe_result;
        fprintf('[ OK ] mnrnd(3, [0.5;0.5]) succeeded: [%s]\n', num2str(mnrnd_probe_result));
    catch mnrndErr
        report.mnrnd_shape_test_status = 'error';
        report.mnrnd_shape_test_error_message = mnrndErr.message;
        fprintf('[FAIL] mnrnd(3, [0.5;0.5]) raised an error: %s\n', mnrndErr.message);
        fprintf('       Recorded as a Karr dormant-source defect -- NOT fixed post hoc (Opus5 turn-4 correction 1).\n');
    end
end

% overall_pass reflects BASIC ENVIRONMENT READINESS ONLY (genuine MATLAB,
% WholeCell root resolved, Statistics Toolbox licensed+installed,
% RandStream class found and constructible). It deliberately does NOT
% factor in mnrnd_shape_test_status: canary-mode plumbing runs must remain
% possible even if the mnrnd column-vector shape probe errors (Opus5
% turn-4 correction 1) -- only FULL mode is additionally hard-blocked by
% an mnrnd 'error' result, via h12_perturbation.py's
% _validate_matlab_probe_result computing a separate `full_mode_permitted`
% flag (= overall_pass AND mnrnd_shape_test_status == 'pass'). If
% overall_pass itself required mnrnd to pass, a real mnrnd failure would
% make even canary mode impossible to run, defeating that separation.
report.overall_pass = ~report.is_octave && ~isempty(wholecell_src) && report.statistics_toolbox_licensed && ...
    report.statistics_toolbox_installed && report.randstream_class_found && report.randstream_constructs;

print_report(report);
write_probe_result_json(report);

if ~report.overall_pass
    error('probe_matlab_environment:overallFail', 'probe_matlab_environment overall_pass=false -- see printed report above and the persisted result JSON.');
end

end

function h = sha256_lf_normalized_file(path)
% Byte-level CRLF/CR -> LF normalization followed by SHA-256, matching
% run_ppii_scenario_b_matlab.m's sha256_file_lf_normalized convention
% exactly (both sides must agree bit-for-bit with
% scripts/l22_evidence/h12_perturbation.py::_sha256_lf_normalized).
raw = fileread(path);
raw = strrep(raw, char([13 10]), char(10));
raw = strrep(raw, char(13), char(10));
bytes = uint8(raw);
md = java.security.MessageDigest.getInstance('SHA-256');
digestBytes = typecast(md.digest(bytes), 'uint8');
h = sprintf('%02x', digestBytes);
end

function write_probe_result_json(report)
out_path = getenv('PPII_PROBE_RESULT_JSON');
if isempty(out_path)
    error('probe_matlab_environment:noResultPath', ...
        'PPII_PROBE_RESULT_JSON environment variable not set -- cannot persist structured probe result.');
end
report.generated_at_utc = datestr(datetime('now', 'TimeZone', 'UTC'), 'yyyy-mm-ddTHH:MM:SSZ');
json_text = jsonencode(report);
out_dir = fileparts(out_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(out_path, 'w');
if fid == -1
    error('probe_matlab_environment:cannotWrite', 'Could not open %s for writing.', out_path);
end
fwrite(fid, json_text, 'char');
fclose(fid);
fprintf('[INFO] probe result JSON written to %s\n', out_path);
end

function print_report(report)
fprintf('\n=== probe_matlab_environment summary ===\n');
if report.overall_pass
    if strcmp(report.mnrnd_shape_test_status, 'pass')
        fprintf('OVERALL: PASS -- environment is ready for run_ppii_scenario_b_matlab.m canary AND full mode\n');
    else
        fprintf(['OVERALL: PASS (canary-mode plumbing only) -- basic environment readiness confirmed, but ' ...
            'mnrnd_shape_test_status=%s hard-blocks FULL mode until independently resolved ' ...
            '(Opus5 turn-4 correction 1)\n'], report.mnrnd_shape_test_status);
    end
else
    fprintf(['OVERALL: FAIL -- run_ppii_scenario_b_matlab.m would abort in this environment ' ...
        '(no stub fallback exists)\n']);
end
end
