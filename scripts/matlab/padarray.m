function b = padarray(a, pad_size, pad_val, direction)
% padarray  Minimal constant-value padding fallback.
% Supports direction: 'pre', 'post', 'both' (default 'both').

if nargin < 2
    error('padarray:NotEnoughInputs', 'A and PAD_SIZE are required.');
end
if nargin < 3 || isempty(pad_val)
    pad_val = 0;
end
if nargin < 4 || isempty(direction)
    direction = 'both';
end

sz = size(a);
n_dims = max(numel(sz), numel(pad_size));
sz(end + 1:n_dims) = 1;
pad_size = double(pad_size(:)');
pad_size(end + 1:n_dims) = 0;

switch lower(direction)
    case 'pre'
        pre = pad_size;
        post = zeros(1, n_dims);
    case 'post'
        pre = zeros(1, n_dims);
        post = pad_size;
    case 'both'
        pre = pad_size;
        post = pad_size;
    otherwise
        error('padarray:UnsupportedDirection', ...
            'Only ''pre'', ''post'', and ''both'' are supported.');
end

out_sz = sz + pre + post;
b = repmat(cast(pad_val, class(a)), out_sz);

subs = arrayfun(@(i) (pre(i) + 1):(pre(i) + sz(i)), 1:n_dims, 'UniformOutput', false);
b(subs{:}) = a;
end
