function extract_everything_v1(seedFirst, seedLast, tickFirst, tickLast, dataTypes)
% EXTRACT_EVERYTHING_V1  One-shot orchestrator for MATLAB extraction closure.
%
% Produces (idempotent, resumable chunks):
%   - data/karr_fixtures/per_process/*_flat.mat
%   - data/m1_sources/karr_native/per_process_traces_v2_sNNN/<Process>_<ticks>ticks.mat
%   - data/karr_fixtures/matlab_ground_truth/per_tick/metab_flux_per_tick_sNNN_tTTT.mat
%   - data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_sNNN_tick1.mat
%   - data/m1_sources/karr_native/ensembles/{transcription,translation}/seed_NNN/<Process>_<ticks>ticks.mat
%   - data/m1_sources/karr_native/{initial_states,fitted_constants,cell_cycle_trajectory.mat}
%   - data/m1_sources/karr_flat/{metabolism_dynamics,sim_fitted_targeted,transcription_v2_targeted, ...}
%
% Expected total runtime (fresh full run): ~12-36 hours, machine/license dependent.
% Expected total output size (fresh full run): ~4-20 GB for 100-tick scope.
%
% Args:
%   seedFirst, seedLast : inclusive seed bounds (default 0..49)
%   tickFirst, tickLast : inclusive tick bounds (default 1..100)
%   dataTypes           : cellstr selector; default = all known chunks
%                         supported values:
%                           'per_process_fixtures'
%                           'per_process_traces_v2'
%                           'metab_flux_tick1'
%                           'metab_flux_per_tick'
%                           'transcription_ensemble'
%                           'translation_ensemble'
%                           'initial_states'
%                           'fitted_constants'
%                           'karr_m1_dynamics'
%                           'karr_m1_flux_growth'
%                           'karr_targeted'
%                           'karr_m2v2'
%                           'karr_m3v2'
%                           'protein_complexes'
%                           'm3_metabolite_vocab'
%                           'cell_cycle_trajectory'
%                           'toolbox_check_only'
%
% Example:
%   extract_everything_v1(0, 49, 1, 100, ...
%       {'per_process_traces_v2','metab_flux_per_tick','metab_flux_tick1'});

    if nargin < 1 || isempty(seedFirst), seedFirst = 0; end
    if nargin < 2 || isempty(seedLast),  seedLast = 49; end
    if nargin < 3 || isempty(tickFirst), tickFirst = 1; end
    if nargin < 4 || isempty(tickLast),  tickLast = 100; end
    if nargin < 5 || isempty(dataTypes), dataTypes = defaultDataTypes(); end

    dataTypes = normalizeDataTypes(dataTypes);
    validateRanges(seedFirst, seedLast, tickFirst, tickLast);

    this_file = mfilename('fullpath');
    matlab_dir = fileparts(this_file);
    scripts_dir = fileparts(matlab_dir);
    repo_root = fileparts(scripts_dir);
    trace_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_native');
    flat_root = fullfile(repo_root, 'data', 'm1_sources', 'karr_flat');
    gt_root = fullfile(repo_root, 'data', 'karr_fixtures', 'matlab_ground_truth');
    gt_per_tick_root = fullfile(gt_root, 'per_tick');

    wholecell_root = detectWholecellRoot(repo_root);

    logf('start');
    logf('repo_root=%s', repo_root);
    logf('wholecell_root=%s', wholecell_root);
    logf('seed range=%d..%d', seedFirst, seedLast);
    logf('tick range=%d..%d', tickFirst, tickLast);
    logf('dataTypes=%s', strjoin(dataTypes, ', '));

    if any(strcmp(dataTypes, 'toolbox_check_only'))
        reportToolboxes();
        logf('toolbox_check_only requested; exiting.');
        return;
    end

    for i = 1:numel(dataTypes)
        chunk = dataTypes{i};
        switch chunk
            case 'per_process_fixtures'
                runChunk(chunk, @() run_per_process_fixtures(wholecell_root, repo_root));

            case 'per_process_traces_v2'
                runChunk(chunk, @() run_per_process_traces_v2( ...
                    seedFirst, seedLast, tickFirst, tickLast, trace_root));

            case 'metab_flux_tick1'
                runChunk(chunk, @() run_metab_flux_tick1( ...
                    wholecell_root, gt_root, seedFirst, seedLast));

            case 'metab_flux_per_tick'
                runChunk(chunk, @() run_metab_flux_per_tick( ...
                    wholecell_root, gt_per_tick_root, trace_root, ...
                    seedFirst, seedLast, tickFirst, tickLast));

            case 'transcription_ensemble'
                runChunk(chunk, @() run_transcription_ensemble( ...
                    repo_root, trace_root, seedFirst, seedLast, tickLast));

            case 'translation_ensemble'
                runChunk(chunk, @() run_translation_ensemble( ...
                    repo_root, trace_root, seedFirst, seedLast, tickLast));

            case 'initial_states'
                runChunk(chunk, @() run_script_at_repo('extract_initial_states', repo_root));

            case 'fitted_constants'
                runChunk(chunk, @() run_script_at_repo('extract_fitted_constants', repo_root));

            case 'karr_m1_dynamics'
                runChunk(chunk, @() run_karr_m1_dynamics(wholecell_root, flat_root));

            case 'karr_m1_flux_growth'
                runChunk(chunk, @() run_karr_m1_flux_growth(wholecell_root, gt_root));

            case 'karr_targeted'
                runChunk(chunk, @() run_karr_targeted(wholecell_root, flat_root));

            case 'karr_m2v2'
                runChunk(chunk, @() run_karr_m2v2(wholecell_root, flat_root));

            case 'karr_m3v2'
                runChunk(chunk, @() run_karr_m3v2(wholecell_root, flat_root));

            case 'protein_complexes'
                runChunk(chunk, @() run_protein_complexes(wholecell_root, flat_root));

            case 'm3_metabolite_vocab'
                runChunk(chunk, @() run_script_at_repo('extract_m3_metabolite_vocab', repo_root));

            case 'cell_cycle_trajectory'
                runChunk(chunk, @() run_cell_cycle_trajectory(repo_root));

            otherwise
                logf('WARN unknown dataType="%s" (skipping)', chunk);
        end
    end

    logf('done');
end

% -------------------------------------------------------------------------
% Chunk runners
% -------------------------------------------------------------------------

function run_per_process_fixtures(wholecell_root, repo_root)
    assertWholecellRoot(wholecell_root, 'per_process_fixtures');
    out_dir = fullfile(repo_root, 'data', 'karr_fixtures', 'per_process');
    extract_per_process_fixtures(wholecell_root, out_dir);
end

function run_per_process_traces_v2(seedFirst, seedLast, tickFirst, tickLast, trace_root)
    if tickFirst ~= 1
        logf('WARN per_process_traces_v2 only supports tick-first at 1; using n_ticks=tickLast=%d', tickLast);
    end
    if ~requireToolbox('Statistics and Machine Learning Toolbox', 'Statistics_Toolbox', 'per_process_traces_v2')
        return;
    end

    process_names = defaultProcessNames();
    n_ticks = tickLast;

    for seedVal = seedFirst:seedLast
        output_subdir = sprintf('per_process_traces_v2_s%03d', seedVal);
        for p = 1:numel(process_names)
            pname = process_names{p};
            out_file = fullfile(trace_root, output_subdir, sprintf('%s_%dticks.mat', pname, n_ticks));
            if exist(out_file, 'file') == 2
                logf('skip existing %s', out_file);
                continue;
            end
            logf('extract trace seed=%d process=%s ticks=%d', seedVal, pname, n_ticks);
            extract_per_process_traces_v2({pname}, output_subdir, n_ticks, uint32(seedVal));
        end
    end
end

function run_metab_flux_tick1(wholecell_root, gt_root, seedFirst, seedLast)
    assertWholecellRoot(wholecell_root, 'metab_flux_tick1');
    if ~exist(gt_root, 'dir'), mkdir(gt_root); end
    for seedVal = seedFirst:seedLast
        out_file = fullfile(gt_root, sprintf('metab_flux_allocated_state_s%03d_tick1.mat', seedVal));
        if exist(out_file, 'file') == 2
            logf('skip existing %s', out_file);
            continue;
        end
        logf('extract metab tick1 seed=%d', seedVal);
        extract_metab_flux_v3(wholecell_root, gt_root, uint32(seedVal));
    end
end

function run_metab_flux_per_tick(wholecell_root, out_root, trace_root, seedFirst, seedLast, tickFirst, tickLast)
    assertWholecellRoot(wholecell_root, 'metab_flux_per_tick');
    if ~exist(out_root, 'dir'), mkdir(out_root); end
    logf('extract metab per-tick seed=%d..%d tick=%d..%d', seedFirst, seedLast, tickFirst, tickLast);
    extract_metab_flux_per_tick(wholecell_root, out_root, trace_root, ...
        uint32(seedFirst), uint32(seedLast), tickFirst, tickLast);
end

function run_transcription_ensemble(repo_root, trace_root, seedFirst, seedLast, tickLast)
    if ~requireToolbox('Statistics and Machine Learning Toolbox', 'Statistics_Toolbox', 'transcription_ensemble')
        return;
    end
    seed_list = seedFirst:seedLast; %#ok<NASGU>
    n_ticks = tickLast; %#ok<NASGU>
    output_root = fullfile(trace_root, 'ensembles', 'transcription'); %#ok<NASGU>
    force_overwrite = false; %#ok<NASGU>
    run_script_at_repo('extract_transcription_ensemble', repo_root);
end

function run_translation_ensemble(repo_root, trace_root, seedFirst, seedLast, tickLast)
    if ~requireToolbox('Statistics and Machine Learning Toolbox', 'Statistics_Toolbox', 'translation_ensemble')
        return;
    end
    seed_list = seedFirst:seedLast; %#ok<NASGU>
    n_ticks = tickLast; %#ok<NASGU>
    output_root = fullfile(trace_root, 'ensembles', 'translation'); %#ok<NASGU>
    force_overwrite = false; %#ok<NASGU>
    run_script_at_repo('extract_translation_ensemble', repo_root);
end

function run_karr_m1_dynamics(wholecell_root, out_root)
    assertWholecellRoot(wholecell_root, 'karr_m1_dynamics');
    if ~exist(out_root, 'dir'), mkdir(out_root); end
    extract_karr_m1_dynamics(wholecell_root, out_root);
end

function run_karr_m1_flux_growth(wholecell_root, out_root)
    assertWholecellRoot(wholecell_root, 'karr_m1_flux_growth');
    if ~exist(out_root, 'dir'), mkdir(out_root); end
    extract_karr_m1_flux_growth(wholecell_root, out_root);
end

function run_karr_targeted(wholecell_root, out_root)
    assertWholecellRoot(wholecell_root, 'karr_targeted');
    if ~exist(out_root, 'dir'), mkdir(out_root); end
    extract_karr_targeted(wholecell_root, out_root);
end

function run_karr_m2v2(wholecell_root, out_root)
    assertWholecellRoot(wholecell_root, 'karr_m2v2');
    if ~exist(out_root, 'dir'), mkdir(out_root); end
    extract_karr_m2v2(wholecell_root, out_root);
end

function run_karr_m3v2(wholecell_root, out_root)
    assertWholecellRoot(wholecell_root, 'karr_m3v2');
    if ~exist(out_root, 'dir'), mkdir(out_root); end
    extract_karr_m3v2(wholecell_root, out_root);
end

function run_protein_complexes(wholecell_root, out_root)
    assertWholecellRoot(wholecell_root, 'protein_complexes');
    if ~exist(out_root, 'dir'), mkdir(out_root); end
    extract_protein_complexes(wholecell_root, out_root);
end

function run_cell_cycle_trajectory(repo_root)
    if ~requireToolbox('Statistics and Machine Learning Toolbox', 'Statistics_Toolbox', 'cell_cycle_trajectory')
        return;
    end
    run_script_at_repo('extract_cell_cycle_trajectory', repo_root);
end

% -------------------------------------------------------------------------
% General helpers
% -------------------------------------------------------------------------

function run_script_at_repo(script_name, repo_root)
    prev = pwd;
    cleaner = onCleanup(@() cd(prev)); %#ok<NASGU>
    cd(repo_root);
    logf('run script %s', script_name);
    eval(script_name);
end

function runChunk(chunk_name, fn)
    logf('BEGIN %s', chunk_name);
    t = tic;
    try
        fn();
        logf('END %s (%.1fs)', chunk_name, toc(t));
    catch err
        logf('ERROR %s: %s', chunk_name, err.message);
        logf('%s', getReport(err, 'extended', 'hyperlinks', 'off'));
    end
end

function names = defaultProcessNames()
    names = { ...
        'Metabolism', ...
        'ReplicationInitiation', ...
        'Replication', ...
        'DNADamage', ...
        'DNARepair', ...
        'DNASupercoiling', ...
        'ChromosomeCondensation', ...
        'ChromosomeSegregation', ...
        'Transcription', ...
        'TranscriptionalRegulation', ...
        'RNAProcessing', ...
        'RNAModification', ...
        'RNADecay', ...
        'tRNAAminoacylation', ...
        'Translation', ...
        'ProteinProcessingI', ...
        'ProteinProcessingII', ...
        'ProteinModification', ...
        'ProteinFolding', ...
        'ProteinActivation', ...
        'ProteinDecay', ...
        'ProteinTranslocation', ...
        'MacromolecularComplexation', ...
        'RibosomeAssembly', ...
        'FtsZPolymerization', ...
        'Cytokinesis', ...
        'HostInteraction', ...
        'TerminalOrganelleAssembly' ...
    };
end

function types = defaultDataTypes()
    types = { ...
        'per_process_fixtures', ...
        'per_process_traces_v2', ...
        'metab_flux_tick1', ...
        'metab_flux_per_tick', ...
        'transcription_ensemble', ...
        'translation_ensemble', ...
        'initial_states', ...
        'fitted_constants', ...
        'karr_m1_dynamics', ...
        'karr_m1_flux_growth', ...
        'karr_targeted', ...
        'karr_m2v2', ...
        'karr_m3v2', ...
        'protein_complexes', ...
        'm3_metabolite_vocab', ...
        'cell_cycle_trajectory' ...
    };
end

function dataTypes = normalizeDataTypes(dataTypes)
    if ischar(dataTypes)
        dataTypes = {lower(strtrim(dataTypes))};
        return;
    end
    if isstring(dataTypes)
        dataTypes = cellstr(dataTypes);
    end
    for i = 1:numel(dataTypes)
        dataTypes{i} = lower(strtrim(char(dataTypes{i})));
    end
end

function validateRanges(seedFirst, seedLast, tickFirst, tickLast)
    if seedFirst < 0 || seedLast < 0 || seedLast < seedFirst
        error('Invalid seed range: [%d, %d]', seedFirst, seedLast);
    end
    if tickFirst < 1 || tickLast < tickFirst
        error('Invalid tick range: [%d, %d]', tickFirst, tickLast);
    end
end

function root = detectWholecellRoot(repo_root)
    candidates = { ...
        fullfile(repo_root, 'data', 'm1_sources', 'WholeCell'), ...
        fullfile(repo_root, '_tmp_WholeCell'), ...
        'E:\opencell\data\m1_sources\WholeCell', ...
        'E:\opencell\_tmp_WholeCell' ...
    };
    root = '';
    for i = 1:numel(candidates)
        c = candidates{i};
        if exist(fullfile(c, 'data', 'Simulation_fitted.mat'), 'file') == 2
            root = c;
            return;
        end
    end
end

function assertWholecellRoot(root, chunkName)
    if isempty(root) || exist(fullfile(root, 'data', 'Simulation_fitted.mat'), 'file') ~= 2
        error('%s requires WholeCell root with data/Simulation_fitted.mat. Not found.', chunkName);
    end
end

function ok = requireToolbox(toolboxPrettyName, licenseFeatureName, chunkName)
    ok = false;
    has_ver = false;
    has_license = false;
    try
        v = ver();
        names = {v.Name};
        has_ver = any(strcmpi(names, toolboxPrettyName));
    catch
    end
    try
        has_license = license('test', licenseFeatureName);
    catch
    end
    ok = has_ver || has_license;
    if ~ok
        logf('WARN skipping %s: missing toolbox "%s" (license feature %s)', ...
            chunkName, toolboxPrettyName, licenseFeatureName);
    end
end

function reportToolboxes()
    logf('toolbox report start');
    reportOne('Statistics and Machine Learning Toolbox', 'Statistics_Toolbox');
    reportOne('Optimization Toolbox', 'Optimization_Toolbox');
    reportOne('Parallel Computing Toolbox', 'Distrib_Computing_Toolbox');
    logf('toolbox report end');
end

function reportOne(pretty, feature)
    has_ver = false;
    has_license = false;
    try
        v = ver();
        names = {v.Name};
        has_ver = any(strcmpi(names, pretty));
    catch
    end
    try
        has_license = license('test', feature);
    catch
    end
    logf('toolbox "%s": in_ver=%d license_test(%s)=%d', pretty, has_ver, feature, has_license);
end

function logf(varargin)
    ts = datestr(now, 'yyyy-mm-dd HH:MM:SS');
    msg = sprintf(varargin{:});
    fprintf('[extract_everything_v1][%s] %s\n', ts, msg);
end

