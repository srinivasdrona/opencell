% Standalone preflight probe for the genuine-MATLAB Scenario B execution
% environment. Performs ONLY read-only checks (MATLAB vs Octave, license,
% toolbox installation, RandStream class construction) and prints a
% human-readable PASS/FAIL report -- it makes no state changes, writes no
% output files, and runs no ProteinProcessingII evolveState code.
%
% This is the "parse/license/toolbox probe" step GPT-5.6 Sol authorizes
% separately from (and strictly before) the 1x5 canary run. It exists so
% that environment-availability failures are diagnosed in isolation from
% the canary's actual evidentiary run, per the abort-with-no-fallback
% requirement (Opus5 Turn 3 correction 1): if MATLAB, the Statistics
% Toolbox, or edu.stanford.covert.util.RandStream construction fails here,
% run_ppii_scenario_b_matlab.m would abort at the same checks anyway --
% this script just lets that be diagnosed up front, cheaply, without
% touching any generated evidence files.
%
% NOT INVOKED by anything in this commit or by run_ppii_scenario_b_matlab.m
% itself -- it is a separate, manually-run diagnostic tool.
function probe_matlab_environment()

this_dir = fileparts(mfilename('fullpath'));
repo_root = fullfile(this_dir, '..', '..');
wholecell_src = fullfile(repo_root, 'data', 'm1_sources', 'WholeCell', 'src');

report = struct();
report.is_octave = exist('OCTAVE_VERSION', 'builtin') ~= 0;
report.matlab_version = version();

if report.is_octave
    fprintf('[FAIL] Running under Octave, not MATLAB. OCTAVE_VERSION=%s\n', getenv('OCTAVE_VERSION'));
    fprintf('       Genuine-MATLAB Scenario B evidence cannot be generated under Octave.\n');
    report.overall_pass = false;
    print_report(report);
    return;
end
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

addpath(wholecell_src);
report.wholecell_src_path = wholecell_src;
report.randstream_class_found = exist('edu.stanford.covert.util.RandStream', 'class') == 8;
if report.randstream_class_found
    fprintf('[ OK ] edu.stanford.covert.util.RandStream class found on path %s\n', wholecell_src);
else
    fprintf('[FAIL] edu.stanford.covert.util.RandStream class NOT found on path %s\n', wholecell_src);
end

report.randstream_constructs = false;
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

report.overall_pass = ~report.is_octave && report.statistics_toolbox_licensed && ...
    report.statistics_toolbox_installed && report.randstream_class_found && report.randstream_constructs;

print_report(report);

end

function print_report(report)
fprintf('\n=== probe_matlab_environment summary ===\n');
if report.overall_pass
    fprintf('OVERALL: PASS -- environment is ready for run_ppii_scenario_b_matlab.m\n');
else
    fprintf('OVERALL: FAIL -- run_ppii_scenario_b_matlab.m would abort in this environment (no stub fallback exists)\n');
end
end
