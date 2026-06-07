function r = binornd(n, p, varargin)
% binornd  Minimal binomial RNG fallback (no Statistics Toolbox required).

if nargin < 2
    error('binornd:NotEnoughInputs', 'n and p required.');
end

if isempty(varargin)
    out_size = broadcast_size(n, p);
elseif numel(varargin) == 1 && isnumeric(varargin{1}) && numel(varargin{1}) > 1
    out_size = double(varargin{1});
else
    out_size = cellfun(@double, varargin);
end

narr = expand_param(double(n), out_size);
parr = expand_param(double(p), out_size);
parr = min(max(parr, 0), 1);
narr = max(narr, 0);

flat_n = narr(:);
flat_p = parr(:);
out = zeros(size(flat_n));

for i = 1:numel(flat_n)
    ni = floor(flat_n(i));
    pi = flat_p(i);
    if ni <= 0 || pi <= 0
        out(i) = 0;
    elseif pi >= 1
        out(i) = ni;
    elseif ni <= 200
        out(i) = sum(rand(ni, 1) < pi);
    else
        mu = ni * pi;
        sigma = sqrt(ni * pi * (1 - pi));
        out(i) = min(ni, max(0, round(mu + sigma * randn())));
    end
end

r = reshape(out, out_size);
end

function sz = broadcast_size(a, b)
if ~isscalar(a)
    sz = size(a);
elseif ~isscalar(b)
    sz = size(b);
else
    sz = [1 1];
end
end

function arr = expand_param(x, out_size)
if isscalar(x)
    arr = repmat(x, out_size);
elseif isequal(size(x), out_size)
    arr = x;
else
    error('binornd:SizeMismatch', 'Input size must be scalar or match output size.');
end
end
