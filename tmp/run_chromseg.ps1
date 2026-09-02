$wrapper = "C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\with_matlab_slot.ps1"
$worktree = "E:\opencell-worktrees\genuine-l21-active"
& $wrapper -Worktree $worktree -Tag "l21-active-genuine-chromseg" -MatlabExpression "run('tmp/l21_active_genuine_chromosome_segregation.m');" -Slots 4
