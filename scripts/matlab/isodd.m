function tf = isodd(x)
% isodd  Compatibility helper for WholeCell numeric strand indices.

if ~isnumeric(x)
    error('isodd:InvalidInput', 'Input must be numeric.');
end

tf = mod(x, 2) ~= 0;
end

