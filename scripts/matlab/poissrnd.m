function r = poissrnd(lambda, varargin)
% poissrnd  Minimal Poisson RNG fallback (no Statistics Toolbox required).

if nargin < 1
    error('poissrnd:NotEnoughInputs', 'Lambda required.');
end

if isempty(varargin)
    out_size = size(lambda);
elseif numel(varargin) == 1 && isnumeric(varargin{1}) && numel(varargin{1}) > 1
    out_size = double(varargin{1});
else
    out_size = cellfun(@double, varargin);
end

if isscalar(lambda)
    lam = repmat(double(lambda), out_size);
else
    lam = double(lambda);
    if ~isequal(size(lam), out_size)
        error('poissrnd:SizeMismatch', 'Lambda size must match requested output size.');
    end
end

lam = max(lam, 0);
flat = lam(:);
out = zeros(size(flat));

for i = 1:numel(flat)
    li = flat(i);
    if li <= 0 || ~isfinite(li)
        out(i) = 0;
    elseif li < 30
        L = exp(-li);
        k = 0;
        p = 1;
        while p > L
            k = k + 1;
            p = p * rand();
        end
        out(i) = k - 1;
    else
        % Fast approximation for large lambda.
        out(i) = max(0, round(li + sqrt(li) * randn()));
    end
end

r = reshape(out, out_size);
end
