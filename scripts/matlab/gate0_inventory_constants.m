function gate0_inventory_constants(outPath)
%GATE0_INVENTORY_CONSTANTS  Enumerate the source-declared constant surface.
%
% For each of the 28 fully-initialized processes in Simulation_fitted, resolve
% the process's OWN declared constant surface via the annotation getters:
%   - fixedConstantNames   (base 5 + ReactionProcess 8 + subclass-specific)
%   - fittedConstantNames  (subclass-specific)
% and record, per named property, its MATLAB class + size + element count.
%
% This is a scope-inventory pass ONLY (no values / no hashing). It answers
% "what does the source declare as a fixed/fitted constant, and of what type"
% so the value-comparison gate can be built against a verified surface rather
% than an assumption. Also flags any property that is an object handle (would
% be a state-ref mis-declared as a constant) or is absent on the instance.
%
% Usage:
%   matlab -batch "cd('E:\opencell'); addpath('E:\opencell\scripts\matlab'); ...
%       gate0_inventory_constants('data/karr_input_spec/_gate0_constant_inventory.json')"

    if nargin < 1 || isempty(outPath)
        outPath = 'data/karr_input_spec/_gate0_constant_inventory.json';
    end

    sim = karr_bootstrap();
    procs = sim.processes;
    n = numel(procs);
    fprintf('[gate0-inv] fitted simulation loaded; n_processes = %d\n', n);

    out = struct();
    out.generated_by = 'gate0_inventory_constants.m';
    out.source = 'Simulation_fitted.mat via karr_bootstrap';
    entries = {};

    for i = 1:n
        p = procs{i};
        name = p.name;
        try
            fixedNames = p.fixedConstantNames;
        catch e
            fixedNames = {};
            fprintf('[gate0-inv] %-28s fixedConstantNames getter FAILED: %s\n', name, e.message);
        end
        try
            fittedNames = p.fittedConstantNames;
        catch e
            fittedNames = {};
            fprintf('[gate0-inv] %-28s fittedConstantNames getter FAILED: %s\n', name, e.message);
        end

        e = struct();
        e.name = name;
        e.class = class(p);
        e.fixed = describe_props(p, fixedNames);
        e.fitted = describe_props(p, fittedNames);
        e.n_fixed = numel(fixedNames);
        e.n_fitted = numel(fittedNames);
        entries{end+1} = e; %#ok<AGROW>

        fprintf('[gate0-inv] %-28s fixed=%2d fitted=%2d\n', name, e.n_fixed, e.n_fitted);
    end

    out.processes = entries;

    txt = jsonencode(out, 'PrettyPrint', true);
    fid = fopen(outPath, 'w');
    fprintf(fid, '%s', txt);
    fclose(fid);
    fprintf('[gate0-inv] wrote %s\n', outPath);
end

function desc = describe_props(p, names)
    desc = {};
    for k = 1:numel(names)
        nm = names{k};
        d = struct();
        d.name = nm;
        if ~isprop(p, nm)
            d.status = 'MISSING_PROPERTY';
            d.class = '';
            d.size = [];
            d.numel = 0;
            desc{end+1} = d; %#ok<AGROW>
            continue;
        end
        v = p.(nm);
        d.class = class(v);
        d.size = size(v);
        d.numel = numel(v);
        if isobject(v) && ~isnumeric(v) && ~ischar(v) && ~islogical(v) && ~iscell(v) && ~isstruct(v)
            d.status = 'OBJECT_HANDLE';   % should not appear in a constant list
        elseif isempty(v)
            d.status = 'EMPTY';
        else
            d.status = 'OK';
        end
        desc{end+1} = d; %#ok<AGROW>
    end
end
