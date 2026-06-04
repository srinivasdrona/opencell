function y = randsample(varargin)
% randsample  Minimal fallback supporting RandStream-first signature.
%
% Supported call patterns:
%   randsample(n, k)
%   randsample(n, k, replacement)
%   randsample(n, k, replacement, w)
%   randsample(stream, n, k, replacement)
%   randsample(stream, n, k, replacement, w)

[stream, n, k, replacement, w] = parse_inputs(varargin{:});

if ~isscalar(n) || n < 0 || n ~= floor(n)
    error('randsample:InvalidPopulation', 'Population size n must be a nonnegative integer scalar.');
end
if ~isscalar(k) || k < 0 || k ~= floor(k)
    error('randsample:InvalidSampleCount', 'k must be a nonnegative integer scalar.');
end
if ~replacement && k > n
    error('randsample:SampleTooLarge', 'Cannot sample k>n without replacement.');
end
if n == 0 || k == 0
    y = zeros(0, 1);
    return;
end

if isempty(w)
    w = ones(n, 1);
else
    w = double(w(:));
    if numel(w) ~= n
        error('randsample:WeightSizeMismatch', 'Weights must have length n.');
    end
    w(~isfinite(w) | w < 0) = 0;
    if ~any(w)
        w(:) = 1;
    end
end

if replacement
    y = zeros(k, 1);
    cdf = cumsum(w) / sum(w);
    u = rand_with_stream(stream, k, 1);
    for i = 1:k
        y(i) = find(u(i) <= cdf, 1, 'first');
    end
else
    y = zeros(k, 1);
    active = true(n, 1);
    for i = 1:k
        w_i = w;
        w_i(~active) = 0;
        if ~any(w_i)
            remaining = find(active);
            pick_idx = remaining(uniform_index(stream, numel(remaining)));
        else
            cdf = cumsum(w_i) / sum(w_i);
            u = rand_with_stream(stream, 1, 1);
            pick_idx = find(u <= cdf, 1, 'first');
        end
        y(i) = pick_idx;
        active(pick_idx) = false;
    end
end
end

function [stream, n, k, replacement, w] = parse_inputs(varargin)
stream = [];
w = [];

if isempty(varargin)
    error('randsample:NotEnoughInputs', 'At least n and k are required.');
end

arg0 = varargin{1};
if isa(arg0, 'RandStream')
    if numel(varargin) < 3
        error('randsample:NotEnoughInputs', 'Expected stream, n, k.');
    end
    stream = arg0;
    n = varargin{2};
    k = varargin{3};
    if numel(varargin) >= 4
        replacement = logical(varargin{4});
    else
        replacement = false;
    end
    if numel(varargin) >= 5
        w = varargin{5};
    end
else
    n = varargin{1};
    if numel(varargin) < 2
        error('randsample:NotEnoughInputs', 'Expected n and k.');
    end
    k = varargin{2};
    if numel(varargin) >= 3
        replacement = logical(varargin{3});
    else
        replacement = false;
    end
    if numel(varargin) >= 4
        w = varargin{4};
    end
end
end

function r = rand_with_stream(stream, m, n)
if isempty(stream)
    r = rand(m, n);
else
    r = rand(stream, m, n);
end
end

function idx = uniform_index(stream, n)
u = rand_with_stream(stream, 1, 1);
idx = min(n, max(1, floor(u * n) + 1));
end
