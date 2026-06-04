function counts = mnrnd(n, p, varargin)
% mnrnd  Minimal multinomial RNG fallback (scalar n, vector p).

if nargin < 2
    error('mnrnd:NotEnoughInputs', 'n and p are required.');
end
if ~isscalar(n)
    error('mnrnd:UnsupportedN', 'Fallback mnrnd supports scalar n only.');
end
n = double(n);
if n < 0 || n ~= floor(n)
    error('mnrnd:InvalidN', 'n must be a nonnegative integer scalar.');
end

p = double(p(:)');
p(p < 0) = 0;
tp = sum(p);
if tp <= 0
    counts = zeros(size(p));
    return;
end
p = p / tp;

if n == 0
    counts = zeros(size(p));
    return;
end

if ~isempty(varargin)
    if numel(varargin) ~= 1 || varargin{1} ~= 1
        error('mnrnd:UnsupportedShape', 'Fallback mnrnd only supports one sample draw.');
    end
end

edges = [0 cumsum(p)];
edges(end) = 1;
u = rand(n, 1);
counts = histcounts(u, edges);
end
