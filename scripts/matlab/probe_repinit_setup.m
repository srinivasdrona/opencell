function [sim, target_idx] = probe_repinit_setup(process_name, seed)
% probe_repinit_setup  Standalone bootstrap + process lookup + seed for
% the RepInit investigative probe scripts (scripts/matlab/probe_repinit_*.m).
%
% Structurally duplicates (unmodified) extract_per_process_traces_v2.m's
% own `karr_bootstrap()` call plus its local `find_process_index`/
% `seed_simulation` helpers -- MATLAB local (sub)functions are only
% visible within the file that defines them, so a standalone probe
% script cannot call those directly; this is what makes these probe
% scripts standalone in the first place (see
% probe_repinit_advance_to_tick.m's docstring for the same rationale).
% This file has no other callers and is never imported by
% extract_per_process_traces_v2.m.
if nargin < 2 || isempty(seed)
    seed = uint32(0);
end

[sim, ~, ~] = karr_bootstrap();

target_idx = [];
want = local_normalize_name_token(process_name);
for i = 1:numel(sim.processes)
    proc = sim.processes{i};
    short = local_process_short_name(proc);
    tokens = { ...
        local_normalize_name_token(short), ...
        local_normalize_name_token(proc.wholeCellModelID) ...
    };
    if isprop(proc, 'name')
        tokens{end + 1} = local_normalize_name_token(proc.name); %#ok<AGROW>
    end
    if any(strcmp(tokens, want))
        target_idx = i;
        break;
    end
end
if isempty(target_idx)
    error('probe_repinit_setup:process_not_found', 'process not found: %s', process_name);
end

try
    if isobject(sim) && ismethod(sim, 'applyOptions') && ismethod(sim, 'seedRandStream')
        sim.applyOptions('seed', seed);
        sim.seedRandStream();
    elseif isprop(sim, 'randStream') && ~isempty(sim.randStream)
        sim.randStream.seed = seed;
    end
catch
end
end

function short = local_process_short_name(proc)
wid = proc.wholeCellModelID;
if strncmp(wid, 'Process_', numel('Process_'))
    short = wid(numel('Process_') + 1:end);
else
    short = wid;
end
end

function token = local_normalize_name_token(s)
token = lower(regexprep(char(s), '[^a-zA-Z0-9]', ''));
end
