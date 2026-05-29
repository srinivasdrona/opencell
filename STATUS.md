1) Task: Fix RNAProcessing L2.1 fingerprint at tick=4 processedRNAs[140].
2) Baseline Failure: tick=4, observable=processedRNAs, index=140, oc_val=1.0, karr_val=0.0, diff=1.0.
3) WID Mapping: processedRNAs[140] = MG487; driver reaction at tick 4 was TU_138 (ridx=137).
4) Root Cause Hypothesis: zero-H2O ticks still allowed RNaseIII+RNaseP zero-stoich tRNA-cleavage reactions in OC (deterministic + stochastic residual paths).
5) Patch (17 lines): added a precomputed RNaseIII+RNaseP zero-stoich mask and gated those reactions when H2O pool is zero in both deterministic and residual-selection phases.
6) Mandatory Verify Command: cd /mnt/e/opencell-worktrees/fix-rna-processing && source /mnt/e/opencell/.venv-wsl/bin/activate && python -m pytest tests/vivarium/test_karr_rna_processing_l2_replay.py --tb=line -rs -q 2>&1 | tail -10
7) Verify Result: [wip] shifted failure to tick=9, observable=unprocessedRNAs, index=73, oc_val=1.0, karr_val=0.0, diff=1.0; tick-4 processedRNAs[140] mismatch is no longer first-failing.
8) Next Step: reconcile mRNA/tmRNA unprocessed consumption on zero-substrate ticks (class-level gating/selection parity with MATLAB evolveState_Helper).
