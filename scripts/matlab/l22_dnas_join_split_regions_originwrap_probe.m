function summary = l22_dnas_join_split_regions_originwrap_probe(varargin)
% l22_dnas_join_split_regions_originwrap_probe
%
% Standalone, isolated (no full-scheduler replay needed -- just a
% Chromosome state object for `sequenceLen`/`nCompartments` and the real,
% unmodified `joinSplitRegions`/`excludeRegions` methods), hardcoded-input
% cross-check against live MATLAB for the origin-wrap normalization step
% inside `Chromosome.joinSplitRegions` (`Chromosome.m:2811-2817`) -- the
% central fidelity blocker Opus's review of the first audit-boundary-
% closure attempt identified: `_matlab_exclude_regions`'s Python port
% previously used a plain adjacent/overlapping-same-strand merge
% (`_merge_linear_regions`) for its `joinSplitRegions`-equivalent
% preprocessing step, omitting the real function's origin-wrap
% rewrite -- which directly changes the `excLens(end)` value the
% excludeRegions indexing bug (root cause A) reads, whenever a
% boundary-crossing exclusion (root cause C: unsplit footprints that
% extend past `chromosome_length`) coexists on the same pair-strand with
% an exclusion near the chromosome origin.
%
% Runs Opus's exact hand example (0-based positions
% [(500,0,10),(580051,0,630)] on a 580076bp chromosome) PLUS two
% additional cases: no near-origin exclusion (no wrap should fire) and a
% near-origin exclusion placed right at the review's suggested boundary
% (0-based position 605, i.e. exactly at the edge of where the wrap
% condition flips), through the REAL `c.joinSplitRegions` AND the REAL
% `c.excludeRegions` (called on a representative included fragment), for
% direct, mechanical comparison against opencell's Python port
% (`_matlab_join_split_regions`/`_matlab_exclude_regions`,
% `opencell/vivarium/karr_dna_supercoiling.py`) -- no inference, no
% reliance on the pooled projection tensor.
%
% All positions in this probe's OWN input/output are documented as
% either 0-based (matching opencell's convention, suffixed `_0based`) or
% 1-based (real MATLAB's native convention, suffixed `_1based`) to avoid
% any silent off-by-one translation error.
%
% Example:
%   addpath('scripts/matlab');
%   l22_dnas_join_split_regions_originwrap_probe('out_path', ...
%       fullfile(pwd, 'tmp', 'l22_dnas_join_split_regions_originwrap_probe.json'));

opts = parse_inputs(varargin{:});
repo_root = infer_repo_root();
ensure_wholecell_runtime_paths(repo_root);

sim = karr_bootstrap();
c = sim.state('Chromosome');
L = c.sequenceLen;

summary = struct();
summary.sequence_len = int64(L);
summary.cases = {};

% Case 1: Opus's exact hand example. 0-based [(500,0,10),(580051,0,630)]
% -> 1-based [(501,1,10),(580052,1,630)] (MATLAB pair-strand 1 == OC
% pair-strand 0, both representing pairIdx1's first duplex copy).
summary.cases{end + 1} = run_case(c, L, 'opus_hand_example', ...
    [501 1; 580052 1], [10; 630], [1 1], 10);

% Case 2: same far-boundary exclusion alone, no near-origin exclusion --
% the wrap condition needs >=2 entries on the same strand, so this
% should NOT trigger the wrap (regression guard: the wrap only fires
% when genuinely reachable).
summary.cases{end + 1} = run_case(c, L, 'far_exclusion_alone_no_wrap', ...
    [580052 1], [630], [1 1], 1);

% Case 3: near-origin exclusion placed exactly at the review's suggested
% boundary (0-based 605 -> 1-based 606), to mechanically locate the
% wrap-condition's edge: ends(last)+1 >= starts(idx)+L
% => 580052+630-1+1 >= starts(idx)+580076 => 580682 >= starts(idx)+580076
% => starts(idx) <= 606 (1-based). At exactly 606 the condition is
% satisfied (equality); one past it (607) should NOT trigger.
summary.cases{end + 1} = run_case(c, L, 'boundary_edge_wrap_triggers', ...
    [606 1; 580052 1], [10; 630], [1 1], 10);
summary.cases{end + 1} = run_case(c, L, 'boundary_edge_plus_one_no_wrap', ...
    [607 1; 580052 1], [10; 630], [1 1], 10);

% Case 5: THE decisive fragment-accessibility divergence Opus's review
% surfaced -- for exclusions (0-based) [(500,0,10),(580051,0,630)], the
% CORRECT (full joinSplitRegions-with-origin-wrap) merged shape is
% [(0,510),(580051,25)] (0-based), but a pre-split
% (`_split_circular_region`-based) + naive-adjacent-merge-only
% implementation would instead compute [(0,605),(580051,25)] (the
% wrapped remainder of the boundary-crossing exclusion, 605bp, merged
% with the near-origin exclusion via plain overlap/adjacency, WITHOUT
% the real origin-wrap's length-shrinking rewrite). These two merged
% shapes DISAGREE on whether 0-based positions [510,604] (95bp) are
% excluded: the correct answer says NO (fully accessible); the
% pre-split-and-naive-merge answer would incorrectly say YES (blocked).
% Included fragment here: 0-based [510,604] -> 1-based [511,605], length 95.
summary.cases{end + 1} = run_case(c, L, 'decisive_fragment_510_604_accessibility', ...
    [501 1; 580052 1], [10; 630], [511 1], 95);

% Case 6: Opus's second-review mandatory cross-check -- a FULL-CHROMOSOME
% included fragment ([1 1], length=sequenceLen) with two exclusions
% (100bp-anchored, 50bp footprint each) positioned so the resulting
% accessible-region output straddles BOTH ends of the linear
% representation simultaneously: one accessible fragment runs from just
% after the first exclusion to just before the second (the "normal"
% middle chunk), and the OTHER represents the wrapped remainder that,
% without `joinSplitOverOriCRegions`'s second call-site application (on
% the raw OUTPUT fragment list, Chromosome.m near 2674-2677), would
% incorrectly appear as TWO separate fragments (one ending near
% sequenceLen, one starting at position 1) instead of ONE joined
% wrapped fragment.
summary.cases{end + 1} = run_case(c, L, 'opus_review2_full_chromosome_included', ...
    [100 1; 580000 1], [50; 50], [1 1], L);

% Case 7: real-enzyme-footprint variant of case 6 (topoIV footprint=34 at
% position 100, gyrase footprint=140 positioned 150bp before the
% chromosome end, so neither individually overshoots the boundary --
% isolating this case to ONLY exercise `joinSplitOverOriCRegions`, not
% `joinSplitRegions`'s separate origin-wrap normalization) -- used as the
% ground truth for
% `test_accessible_binding_regions_join_split_over_oric_wrapped_fragment`'s
% end-to-end `_accessible_binding_regions` inversion.
summary.cases{end + 1} = run_case(c, L, 'oric_join_real_footprints', ...
    [101 1; 579927 1], [34; 140], [1 1], L);

if ~isempty(opts.out_path)
    out_dir = fileparts(opts.out_path);
    if ~isempty(out_dir) && ~exist(out_dir, 'dir')
        mkdir(out_dir);
    end
    fid = fopen(opts.out_path, 'w');
    if fid < 0
        error('l22_dnas_join_split_regions_originwrap_probe:writeFailed', 'Could not open output path: %s', opts.out_path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', jsonencode(summary));
    fprintf('[l22_dnas_join_split_regions_originwrap_probe] wrote %s\n', opts.out_path);
end
end

function out = run_case(c, L, case_name, posStrnds_1based, lens, incPosStrnd_1based, incLen)
out = struct();
out.case_name = case_name;
out.input_positions_1based = int64(posStrnds_1based(:, 1));
out.input_strands_1based = int8(posStrnds_1based(:, 2));
out.input_lengths = int64(lens);

% Real, unmodified c.joinSplitRegions -- direct call, no reimplementation.
[joinedPosStrnds, joinedLens] = c.joinSplitRegions(posStrnds_1based, lens);
out.joined_positions_1based = int64(joinedPosStrnds(:, 1));
out.joined_strands_1based = int8(joinedPosStrnds(:, 2));
out.joined_lengths = int64(joinedLens);
% 0-based equivalents, for direct diffing against the Python port's
% output (which operates in 0-based coordinates throughout).
out.joined_positions_0based = int64(joinedPosStrnds(:, 1) - 1);

% Real, unmodified c.excludeRegions on a representative included
% fragment, to also mechanically compare the FINAL accessible-region
% output (not just the joinSplitRegions intermediate), exactly as
% `_matlab_exclude_regions` is exercised in production.
[accPosStrnds, accLens] = c.excludeRegions(incPosStrnd_1based, incLen, posStrnds_1based, lens);
out.included_position_1based = int64(incPosStrnd_1based(1));
out.included_strand_1based = int8(incPosStrnd_1based(2));
out.included_length = int64(incLen);
out.accessible_positions_1based = int64(accPosStrnds(:, 1));
out.accessible_strands_1based = int8(accPosStrnds(:, 2));
out.accessible_lengths = int64(accLens);
out.accessible_positions_0based = int64(accPosStrnds(:, 1) - 1);
end

function opts = parse_inputs(varargin)
opts = struct('out_path', '');
if mod(numel(varargin), 2) ~= 0
    error('l22_dnas_join_split_regions_originwrap_probe:invalidArgs', 'Arguments must be name/value pairs');
end
for i = 1:2:numel(varargin)
    name = varargin{i};
    value = varargin{i + 1};
    switch lower(char(name))
        case 'out_path'
            opts.out_path = char(value);
        otherwise
            error('l22_dnas_join_split_regions_originwrap_probe:unknownOption', 'Unknown option: %s', char(name));
    end
end
if isempty(opts.out_path)
    opts.out_path = fullfile(infer_repo_root(), 'tmp', 'l22_dnas_join_split_regions_originwrap_probe.json');
end
end

function repo_root = infer_repo_root()
this_file = mfilename('fullpath');
matlab_dir = fileparts(this_file);
scripts_dir = fileparts(matlab_dir);
repo_root = fileparts(scripts_dir);
end

function ensure_wholecell_runtime_paths(repo_root)
candidate_roots = { ...
    fullfile(repo_root, 'data', 'm1_sources', 'WholeCell'), ...
    'E:\opencell\data\m1_sources\WholeCell'};

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
