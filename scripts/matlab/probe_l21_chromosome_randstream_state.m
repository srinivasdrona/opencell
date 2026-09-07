function report = probe_l21_chromosome_randstream_state(output_json_path)
% probe_l21_chromosome_randstream_state
%
% Empirically determines whether MATLAB's builtin RandStream('mcg16807')
% .State property (as delegated-through by the Karr
% edu.stanford.covert.util.RandStream wrapper's get.state/set.state, see
% +edu/+stanford/+covert/+util/RandStream.m lines 273-278) is:
%   (a) readable at any point in a draw sequence,
%   (b) exactly equal to this project's independently-derived internal LCG
%       state formula (x_n such that rand() = (16807*x_n mod (2^31-1)) / (2^31-1)),
%   (c) settable on a FRESH RandStream object such that continuing to draw
%       from the fresh object exactly reproduces the ORIGINAL stream's
%       continuation, bit-for-bit, across rand/randi/randperm.
%
% This is a pure RNG-mechanics probe -- no Simulation/Chromosome object
% required -- so it can run standalone without the full fitted-simulation
% bootstrap (faster, no license contention beyond base MATLAB).
%
% No web. No tuning to match any expected replay output: this probe
% either confirms or refutes the (a)/(b)/(c) claims against the real,
% local MATLAB installation, independent of any Python-side formula.

if nargin < 1 || isempty(output_json_path)
    output_json_path = fullfile('artifacts', 'l21_dnadamage_chromosome_rng', 'chromosome_randstream_state_probe.json');
end

seeds_to_probe = [1, 2000, 12345, 2147483646];
rows = struct([]);
row_idx = 0;

for si = 1:numel(seeds_to_probe)
    seed = seeds_to_probe(si);

    % --- Original stream: derive x0 via our formula, confirm against .State ---
    rs = RandStream('mcg16807');
    reset(rs, seed);
    state_after_reset = double(rs.State);
    expected_x0 = mod(double(seed) * 65536, 2^31 - 1);

    % Draw a mixed sequence of operations, recording .State before/after each.
    ops = {};
    op_results = {};
    op_states_before = [];
    op_states_after = [];

    % Op 1: rand()
    op_states_before(end+1) = double(rs.State); %#ok<AGROW>
    v1 = rand(rs);
    op_states_after(end+1) = double(rs.State); %#ok<AGROW>
    ops{end+1} = 'rand'; %#ok<AGROW>
    op_results{end+1} = v1; %#ok<AGROW>

    % Op 2: rand() again
    op_states_before(end+1) = double(rs.State); %#ok<AGROW>
    v2 = rand(rs);
    op_states_after(end+1) = double(rs.State); %#ok<AGROW>
    ops{end+1} = 'rand'; %#ok<AGROW>
    op_results{end+1} = v2; %#ok<AGROW>

    % Op 3: randperm(5) -- consumes exactly 5 draws per this project's formula
    op_states_before(end+1) = double(rs.State); %#ok<AGROW>
    p1 = randperm(rs, 5);
    op_states_after(end+1) = double(rs.State); %#ok<AGROW>
    ops{end+1} = 'randperm5'; %#ok<AGROW>
    op_results{end+1} = p1; %#ok<AGROW>

    % Op 4: one more rand() to have a post-randperm anchor point
    state_before_op4 = double(rs.State);
    v3 = rand(rs);
    state_after_op4 = double(rs.State);

    % --- Reconstruction test: fresh RandStream, State injected mid-sequence ---
    % Take the captured state_before_op4 (this project's analogue of a
    % "states_before[t]" ledger entry) and inject it into a BRAND NEW,
    % differently-constructed RandStream object (never reset with `seed`
    % at all -- simulating a Python-side object built fresh from nothing
    % but the captured scalar). Confirm continuing to draw reproduces v3
    % and state_after_op4 exactly.
    rs_fresh = RandStream('mcg16807');
    rs_fresh.State = state_before_op4;
    v3_reconstructed = rand(rs_fresh);
    state_after_op4_reconstructed = double(rs_fresh.State);

    reconstruction_ok = isequal(v3, v3_reconstructed) && ...
        isequal(state_after_op4, state_after_op4_reconstructed);

    % --- Cross-check against this project's independently-derived formula ---
    % Formula (see opencell/vivarium/karr_dna_damage_rng.py):
    %   state update: x_(n+1) = (16807 * x_n) mod (2^31-1)
    %   rand():       x_(n+1) / (2^31-1)   (state updates BEFORE output)
    % If .State reflects x_n *before* the pending draw (i.e. .State read
    % now equals the x_n that the NEXT rand() call will advance from and
    % divide-after-update), then:
    %   predicted_next_rand = mod(16807 * state_now, 2^31-1) / (2^31-1)
    x_before_v1 = op_states_before(1);
    predicted_v1 = mod(16807 * x_before_v1, 2^31 - 1) / (2^31 - 1);
    formula_matches_v1 = abs(predicted_v1 - v1) < 1e-12;

    x_before_v2 = op_states_before(2);
    predicted_v2 = mod(16807 * x_before_v2, 2^31 - 1) / (2^31 - 1);
    formula_matches_v2 = abs(predicted_v2 - v2) < 1e-12;

    row_idx = row_idx + 1;
    rows(row_idx).seed = double(seed); %#ok<AGROW>
    rows(row_idx).state_after_reset = state_after_reset; %#ok<AGROW>
    rows(row_idx).expected_x0_formula = expected_x0; %#ok<AGROW>
    rows(row_idx).state_after_reset_matches_formula_x0 = isequal(state_after_reset, expected_x0); %#ok<AGROW>
    rows(row_idx).op_states_before = op_states_before; %#ok<AGROW>
    rows(row_idx).op_states_after = op_states_after; %#ok<AGROW>
    rows(row_idx).v1 = v1; %#ok<AGROW>
    rows(row_idx).v2 = v2; %#ok<AGROW>
    rows(row_idx).randperm5 = double(p1); %#ok<AGROW>
    rows(row_idx).state_before_op4 = state_before_op4; %#ok<AGROW>
    rows(row_idx).v3 = v3; %#ok<AGROW>
    rows(row_idx).state_after_op4 = state_after_op4; %#ok<AGROW>
    rows(row_idx).v3_reconstructed_from_fresh_object = v3_reconstructed; %#ok<AGROW>
    rows(row_idx).state_after_op4_reconstructed = state_after_op4_reconstructed; %#ok<AGROW>
    rows(row_idx).reconstruction_ok = reconstruction_ok; %#ok<AGROW>
    rows(row_idx).formula_matches_v1 = formula_matches_v1; %#ok<AGROW>
    rows(row_idx).formula_matches_v2 = formula_matches_v2; %#ok<AGROW>
end

% --- randi(s, n, 1, m) probe: does MATLAB's builtin randi() for a
% mcg16807-backed stream advance the state one-per-rand()-equivalent, with
% output == floor(n*u)+1 (u being the raw uniform that a plain rand(s)
% call at that exact state position would also yield)? This determines
% whether randsample.m's rejection-sampling branch (4*k<=n) can be
% ledger-reconstructed by clone-stepping with plain rand() alone. ---
randi_rows = struct([]);
randi_row_idx = 0;
for si = 1:numel(seeds_to_probe)
    seed = seeds_to_probe(si);
    n_candidates = [7, 500, 100003];
    for ni = 1:numel(n_candidates)
        n_val = n_candidates(ni);
        m_draws = 6;

        rs_a = RandStream('mcg16807');
        reset(rs_a, seed);
        state_before = double(rs_a.State);
        randi_out = randi(rs_a, n_val, 1, m_draws);
        state_after = double(rs_a.State);

        % Clone from state_before, predict each randi_out(i) via
        % floor(n_val*u)+1 using consecutive plain rand() draws, and
        % check whether the resulting state trajectory (after exactly
        % m_draws plain rand() calls) matches state_after exactly.
        rs_b = RandStream('mcg16807');
        rs_b.State = state_before;
        predicted = zeros(1, m_draws);
        raw_draws = zeros(1, m_draws);
        for j = 1:m_draws
            u = rand(rs_b);
            raw_draws(j) = u;
            predicted(j) = floor(n_val * u) + 1;
        end
        state_after_b = double(rs_b.State);

        randi_row_idx = randi_row_idx + 1;
        randi_rows(randi_row_idx).seed = double(seed); %#ok<AGROW>
        randi_rows(randi_row_idx).n_val = double(n_val); %#ok<AGROW>
        randi_rows(randi_row_idx).m_draws = double(m_draws); %#ok<AGROW>
        randi_rows(randi_row_idx).randi_out = double(randi_out); %#ok<AGROW>
        randi_rows(randi_row_idx).predicted_floor_plus1 = predicted; %#ok<AGROW>
        randi_rows(randi_row_idx).values_match = isequal(double(randi_out), predicted); %#ok<AGROW>
        randi_rows(randi_row_idx).state_after_matches_m_plain_draws = isequal(state_after, state_after_b); %#ok<AGROW>
        randi_rows(randi_row_idx).state_after = state_after; %#ok<AGROW>
        randi_rows(randi_row_idx).state_after_b = state_after_b; %#ok<AGROW>
    end
end

report = struct();
report.matlab_release = version('-release');
report.generated_at = datestr(now, 'yyyy-mm-dd HH:MM:SS');
report.rows = rows;
report.randi_rows = randi_rows;
report.all_reconstruction_ok = all(arrayfun(@(r) r.reconstruction_ok, rows));
report.all_formula_matches = all(arrayfun(@(r) r.formula_matches_v1 && r.formula_matches_v2, rows));
report.all_state_after_reset_matches_formula = all(arrayfun(@(r) r.state_after_reset_matches_formula_x0, rows));
report.all_randi_values_match = all(arrayfun(@(r) r.values_match, randi_rows));
report.all_randi_state_matches = all(arrayfun(@(r) r.state_after_matches_m_plain_draws, randi_rows));

output_json_path = char(output_json_path);
[out_dir, ~, ~] = fileparts(output_json_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(output_json_path, 'w');
if fid == -1
    error('probe_l21_chromosome_randstream_state:open_failed', ...
        'Unable to open output path for writing: %s', output_json_path);
end
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(report), 'char');
fprintf('[probe_l21_chromosome_randstream_state] wrote %s\n', output_json_path);
fprintf('[probe_l21_chromosome_randstream_state] all_reconstruction_ok=%d all_formula_matches=%d all_state_after_reset_matches_formula=%d all_randi_values_match=%d all_randi_state_matches=%d\n', ...
    report.all_reconstruction_ok, report.all_formula_matches, report.all_state_after_reset_matches_formula, ...
    report.all_randi_values_match, report.all_randi_state_matches);
end
