function out = serialize_chromosome_state(chrom)
% serialize_chromosome_state
% Convert the Chromosome state object's primary writable properties to a
% MATLAB struct of sparse triples that h5py can load as numeric data.
%
% Each property is stored as a struct with fields:
%   positions : Nx1 int64 (1-based position on genome)
%   strands   : Nx1 int8  (1..4 strand index)
%   values    : Nx1 int32 (the nonzero value at that position/strand)
%   shape     : 1x2 int64 [sequenceLen, nStrands]
%
% This avoids materializing the full (~580k x 4) dense matrices while
% preserving the exact state needed for chromosome-primary L2.2 distances
% (Replication, ReplicationInitiation, DNARepair, DNASupercoiling, DNADamage).

if ~isobject(chrom)
    out = struct('error', sprintf('not a Chromosome object: %s', class(chrom)));
    return;
end

% Properties we care about for chromosome-primary L2.2 gates.
% These are all CircularSparseMat of size [sequenceLen x nStrands].
props = { ...
    'polymerizedRegions', ...  % Replication, ReplicationInitiation
    'linkingNumbers', ...      % DNASupercoiling (primary signal)
    'monomerBoundSites', ...   % All (protein-DNA interactions)
    'complexBoundSites', ...   % All
    'gapSites', ...            % DNARepair, DNADamage
    'abasicSites', ...         % DNARepair, DNADamage
    'damagedSugarPhosphates', ... % DNADamage
    'damagedBases', ...        % DNADamage, DNARepair
    'intrastrandCrossLinks', ... % DNADamage, DNARepair
    'strandBreaks', ...        % DNARepair (primary repair signal)
    'hollidayJunctions' ...    % DNARepair
};
hidden_sparse_props = { ...
    'damagedSites', ...
    'singleStrandedRegions', ...
    'doubleStrandedRegions', ...
    'supercoils', ...
    'superhelicalDensity', ...
    'supercoiled' ...
};
hidden_scalar_props = { ...
    'validated', ...
    'validated_damaged', ...
    'validated_polymerizedRegions', ...
    'validated_linkingNumbers', ...
    'validated_singleStrandedRegions', ...
    'validated_doubleStrandedRegions', ...
    'validated_supercoils', ...
    'validated_superhelicalDensity', ...
    'validated_supercoiled', ...
    'validated_damagedSites', ...
    'validated_damagedSites_shifted_incm6AD', ...
    'validated_damagedSites_nonRedundant', ...
    'validated_damagedSites_excm6AD' ...
};

out = struct();
% Capture genome dimensions once (used as shape metadata).
try
    out.sequenceLen = int64(chrom.sequenceLen);
catch
    out.sequenceLen = int64(-1);
end
try
    out.nCompartments = int8(chrom.nCompartments);
catch
    out.nCompartments = int8(-1);
end

for i = 1:numel(props)
    p = props{i};
    out.(p) = sparse_triple_safe(chrom, p);
end

for i = 1:numel(hidden_sparse_props)
    p = hidden_sparse_props{i};
    out.(p) = sparse_triple_generic_safe(chrom, p);
end

for i = 1:numel(hidden_scalar_props)
    p = hidden_scalar_props{i};
    out.(p) = scalar_safe(chrom, p);
end
end

function tri = sparse_triple_safe(chrom, prop_name)
% Extract sparse triple from a Chromosome property (CircularSparseMat).
% SparseMat.find returns [subs, vals] where subs is Nx2 (position, strand).
tri = struct( ...
    'positions', zeros(0, 1, 'int64'), ...
    'strands',   zeros(0, 1, 'int8'), ...
    'values',    zeros(0, 1, 'int32'), ...
    'shape',     int64([0 0]), ...
    'error',     '' ...
);
try
    v = chrom.(prop_name);
    sz = size(v);
    tri.shape = int64(sz(1:min(2, numel(sz))));
    if isempty(sz) || prod(sz) == 0
        return;
    end
    [subs, vals] = find(v);
    if isempty(subs)
        return;
    end
    % subs is Nx2 : column 1 = position, column 2 = strand
    tri.positions = int64(subs(:, 1));
    if size(subs, 2) >= 2
        tri.strands = int8(subs(:, 2));
    else
        tri.strands = int8(ones(size(subs, 1), 1));
    end
    tri.values = int32(vals(:));
catch err
    tri.error = err.message;
end
end

function tri = sparse_triple_generic_safe(chrom, prop_name)
% Extract sparse triple while preserving the source value dtype.
tri = struct( ...
    'positions', zeros(0, 1, 'int64'), ...
    'strands',   zeros(0, 1, 'int8'), ...
    'values',    zeros(0, 1), ...
    'shape',     int64([0 0]), ...
    'error',     '' ...
);
try
    v = chrom.(prop_name);
    sz = size(v);
    tri.shape = int64(sz(1:min(2, numel(sz))));
    if isempty(sz) || prod(sz) == 0
        return;
    end
    [subs, vals] = find(v);
    if isempty(subs)
        return;
    end
    tri.positions = int64(subs(:, 1));
    if size(subs, 2) >= 2
        tri.strands = int8(subs(:, 2));
    else
        tri.strands = int8(ones(size(subs, 1), 1));
    end
    tri.values = vals(:);
catch err
    tri.error = err.message;
end
end

function value = scalar_safe(chrom, prop_name)
% Read a scalar validation/cache field without throwing away the extraction.
try
    value = chrom.(prop_name);
catch err
    value = struct('error', err.message);
end
end
