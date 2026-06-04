function out = seqcomplement(seq)
% seqcomplement  Minimal nucleotide complement fallback.

if isstring(seq)
    out = string(seqcomplement(char(seq)));
    return;
end

if ~ischar(seq)
    error('seqcomplement:UnsupportedType', 'Expected char or string input.');
end

out = seq;
out(seq == 'A') = 'T';
out(seq == 'T') = 'A';
out(seq == 'U') = 'A';
out(seq == 'C') = 'G';
out(seq == 'G') = 'C';
out(seq == 'a') = 't';
out(seq == 't') = 'a';
out(seq == 'u') = 'a';
out(seq == 'c') = 'g';
out(seq == 'g') = 'c';
end
