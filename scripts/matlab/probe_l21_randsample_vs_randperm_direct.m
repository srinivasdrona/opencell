function report = probe_l21_randsample_vs_randperm_direct(output_json_path)
if nargin < 1 || isempty(output_json_path)
    output_json_path = fullfile('artifacts', 'l21_dnadamage_chromosome_rng', 'randsample_vs_randperm_direct.json');
end

rs1 = RandStream('mcg16807');
reset(rs1, 12345);
rp7 = randperm(rs1, 7);

rs2 = RandStream('mcg16807');
reset(rs2, 12345);
rs7 = randsample(rs2, 7, 7, false);

report = struct();
report.randperm7 = double(rp7);
report.randsample7of7 = double(rs7(:)');
report.equal = isequal(double(rp7), double(rs7(:)'));

output_json_path = char(output_json_path);
[out_dir, ~, ~] = fileparts(output_json_path);
if ~isempty(out_dir) && ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(output_json_path, 'w');
cleanup_fid = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(report), 'char');
fprintf('[probe] randperm7=%s randsample7of7=%s equal=%d\n', mat2str(rp7), mat2str(rs7(:)'), report.equal);
end
