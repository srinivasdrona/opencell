function r = random(dist_name, varargin)
% random  Minimal compatibility shim for Statistics Toolbox random().
% Supports distributions used by WholeCell extraction runtime:
%   'norm'/'normal'      random('norm', mu, sigma, ...)
%   'exponential'/'exp'  random('exponential', mu, ...)
%   'poiss'/'poisson'    random('poiss', lambda, ...)

if nargin < 1
    error('random:NotEnoughInputs', 'Distribution name required.');
end

dist = lower(char(dist_name));
switch dist
    case {'norm', 'normal'}
        if numel(varargin) < 2
            error('random:NotEnoughInputs', 'normal needs mu and sigma.');
        end
        mu = varargin{1};
        sigma = varargin{2};
        sz = parse_size_args(varargin(3:end), mu, sigma);
        r = mu + sigma .* randn(sz);

    case {'exponential', 'exp'}
        if isempty(varargin)
            error('random:NotEnoughInputs', 'exponential needs mean parameter.');
        end
        mu = varargin{1};
        sz = parse_size_args(varargin(2:end), mu);
        u = rand(sz);
        u(u == 0) = realmin;
        r = -mu .* log(u);

    case {'poiss', 'poisson'}
        if isempty(varargin)
            error('random:NotEnoughInputs', 'poisson needs lambda parameter.');
        end
        lambda = varargin{1};
        if isempty(varargin(2:end))
            r = poissrnd(lambda);
        else
            r = poissrnd(lambda, varargin{2:end});
        end

    otherwise
        error('random:UnsupportedDistribution', ...
            'Unsupported distribution ''%s'' in compatibility shim.', dist_name);
end
end

function sz = parse_size_args(size_args, varargin)
if isempty(size_args)
    sz = infer_broadcast_size(varargin{:});
    return;
end

if numel(size_args) == 1 && isnumeric(size_args{1}) && numel(size_args{1}) > 1
    sz = double(size_args{1});
    return;
end

sz = cellfun(@double, size_args);
end

function sz = infer_broadcast_size(varargin)
sz = [1 1];
for i = 1:numel(varargin)
    a = varargin{i};
    if ~isscalar(a)
        sz = size(a);
        return;
    end
end
end
