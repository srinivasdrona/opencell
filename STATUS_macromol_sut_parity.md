# STATUS_macromol_sut_parity

## Beat 1 - source read complete

1. Read the mandated prompt files plus the fixed OC/Python source and chromosome serializer.
2. The prompt-specified Karr MATLAB path `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/MacromolecularComplexation.m` is not present in this worktree, so the audit uses the verbatim Karr `evolveState` and helper excerpts preserved in `docs/design/a3_step3_joint_design_v1.md` as the closest available source anchor.
3. Karr's algorithm is two-regime: cluster 1 uses deterministic stoichiometric upper bounds; clusters 2..N use a Monte Carlo loop that recomputes rates, draws one complex, forms one copy, subtracts subunits, and repeats until no complex can form.
4. OC matches the cluster decomposition and the closed-form bounds branch, but its `_per_cluster_mc` helper samples a complex and then samples a Poisson count, allowing multiple copies to form in one iteration.
5. The main parity risk is therefore the substrate-limited competition loop, not the outer per-cluster wiring.

## Beat 2 - audit authored

1. Wrote `docs/phase_f/sut_audits/macromol_oc_vs_karr.md` with inventory, baseline facts, algorithm summaries, a step-by-step mapping table, an RNG inventory, and a substrate-availability branch trace.
2. The audit verdict is `DIVERGENT_BUG`, not `FAITHFUL`.
3. The decisive mismatch is the OC competitive kernel: Karr forms exactly one complex per MC iteration, while OC draws a Poisson multiplicity and may form several before recomputing rates.
4. That extra Poisson draw changes substrate exhaustion behavior precisely in the low-substrate regime this audit was asked to evaluate.

## Beat 3 - self-check pass

1. Re-grepped the preserved Karr excerpt for RNG calls and confirmed the only Karr draw in the audited algorithm is `randStream.rand()`.
2. Confirmed §3 lists both OC stochastic operations: the categorical complex-selection draw and the extra Poisson multiplicity draw.
3. Re-checked substrate handling and added the explicit "no complexes formed anywhere" early-return path for both Karr and OC into §4.
4. Final audit position remains unchanged: the competitive-loop kernel is algorithmically divergent, so the process should stay labeled `regime_bounded`.
