function counts = mnrnd(n, p, varargin)
% mnrnd  Minimal multinomial RNG fallback (scalar n, vector p; no
% Statistics Toolbox required).
%
% scripts/l2_event/launcher.py's build_matlab_command unconditionally
% prepends addpath('scripts/matlab') for EVERY event-window extraction job
% (fixed or anchor, any process, since the scheduler runs every process's
% evolveState() every tick) -- so this file shadows the real
% Statistics-Toolbox mnrnd for every simulated tick, not just
% Cytokinesis/ProteinProcessingII. See docs/phase_f/l2_event/
% EVENT_WINDOW_EXTRACTOR_CONTRACT.md ("Legacy mnrnd compatibility") for
% the identity-binding metadata (mnrnd_shim_version/mnrnd_shim_sha256)
% that lets a trace produced under a stale/pre-fix revision of this file
% be told apart from one produced under the current revision.
%
% Canary D root cause (fixed here): the previous revision built
% edges = [0 cumsum(p)] directly from the FULL sparse probability vector,
% then forced edges(end)=1. A trailing run of zero-probability categories
% can leave the penultimate cumulative edge slightly above 1 through
% floating-point summation; forcing the final edge to exactly 1 then makes
% the pair genuinely decreasing and triggers
% MATLAB:histcounts:DecreasingBinEdges. This is not a row/column issue;
% p(:)' below already normalizes orientation.
%
% Fix: bin edges are built ONLY from the strictly-positive categories (so
% every edge step is > 0, hence strictly increasing by construction), and
% counts are mapped back to their ORIGINAL positions (including the
% zero-probability ones, which always get count 0) afterward.
%
% Deliberately does NOT call histcounts/histc: histcounts does not exist
% in Octave (verified: not part of Octave core or the Octave-Forge
% statistics package) and depending on a toolbox-adjacent binning
% function is exactly the class of problem this fallback exists to avoid.
% The bin-counting loop below uses only rand/cumsum/sum/comparison --
% pure language core, identical in MATLAB and Octave -- so it is directly
% exercised by the Octave-based functional regression test
% (tests/scripts/test_mnrnd_shim.py), not just parsed.
%
% Supported input shapes: a scalar, finite, nonnegative-integer-valued n;
% p any non-empty numeric ROW or COLUMN vector (never a matrix) of
% finite, nonnegative values, with sum(p) > 0 whenever n > 0. Every other
% shape/value FAILS CLOSED (errors) -- never silently clamped, coerced, or
% reinterpreted. n == 0 always returns correctly-shaped all-zero counts
% without drawing, even if sum(p) == 0 (a degenerate-but-harmless "zero
% draws requested" case). Output is always a 1-by-numel(p) ROW of counts;
% Karr's own call sites apply their own trailing transpose (e.g.
% ProteinProcessingII.m:394's `...)'`) so that convention is preserved
% here, not decided by this file.

if nargin < 2
    error('mnrnd:NotEnoughInputs', 'n and p are required.');
end

if ~isscalar(n)
    error('mnrnd:UnsupportedN', 'Fallback mnrnd supports scalar n only.');
end
n = double(n);
if ~isfinite(n) || n < 0 || n ~= floor(n)
    error('mnrnd:InvalidN', 'n must be a finite nonnegative integer scalar.');
end

if ~isnumeric(p) || ~isvector(p) || isempty(p)
    error('mnrnd:InvalidP', 'p must be a non-empty numeric vector (row or column), never a matrix.');
end
p_row = double(p(:)');
if any(~isfinite(p_row))
    error('mnrnd:NonFiniteP', 'p must contain only finite values (no NaN/Inf).');
end
if any(p_row < 0)
    error('mnrnd:NegativeP', 'p must be nonnegative.');
end

if ~isempty(varargin)
    if numel(varargin) ~= 1 || varargin{1} ~= 1
        error('mnrnd:UnsupportedShape', 'Fallback mnrnd only supports one sample draw (m == 1).');
    end
end

counts = zeros(1, numel(p_row));

if n == 0
    return;
end

tp = sum(p_row);
if tp <= 0
    error('mnrnd:ZeroProbabilityMass', 'sum(p) must be > 0 when n > 0.');
end
p_row = p_row / tp;

positive_idx = find(p_row > 0);
p_pos = p_row(positive_idx);

% Every step added to cumsum here is strictly > 0 (positive_idx only
% keeps strictly-positive categories), and there is no trailing zero run
% whose final clamp can create a decreasing edge pair.
edges = [0, cumsum(p_pos)];
edges(end) = 1;

u = rand(n, 1);
n_pos = numel(p_pos);
counts_pos = zeros(1, n_pos);
for k = 1:n_pos
    if k == 1
        % First bin is closed on both ends ([0, edges(2)]) so u == 0 is
        % counted; every other bin is left-open/right-closed
        % ((edges(k), edges(k+1)]) so bins never overlap or leave a gap.
        counts_pos(k) = sum(u >= edges(k) & u <= edges(k + 1));
    else
        counts_pos(k) = sum(u > edges(k) & u <= edges(k + 1));
    end
end

counts(positive_idx) = counts_pos;
end
