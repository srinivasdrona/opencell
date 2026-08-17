function tf = iseven(x)
% iseven  Compatibility helper for WholeCell numeric strand indices.

if ~isnumeric(x)
    error('iseven:InvalidInput', 'Input must be numeric.');
end

tf = mod(x, 2) == 0;
end

