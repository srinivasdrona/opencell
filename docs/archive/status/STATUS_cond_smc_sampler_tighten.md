# STATUS — cond_smc_sampler_tighten

Date: 2026-06-22
Branch: current
Task: Tighten ChromosomeCondensation SMC sampler — port `bindProteinToChromosomeStochastically` faithfully

## Beat 1
Replace OC's synthetic SMC-position-picking logic in `karr_chromosome_condensation.py` with a Karr-faithful port of `bindProteinToChromosomeStochastically` (region weighting + region selection via weighted sample + position-within-region picking), using `self._rng` for ALL draws in the exact MATLAB order (weighted region pick first, then uniform position pick), so the per-binding-event RNG sequence aligns with Karr's MATLAB `randStream`.

## Beat 2
### (a) Day-35 tick-9 failure record (verbatim)
```text
cause_code: CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE
compare_mode: absolute
process: ChromosomeCondensation
observable: substrates, wid: ATP
oracle_type: bit_identity
tick: 9

karr_after:   [44, 2, 2, 416290, 2]   # ATP, ADP, PI, H2O, H
karr_compare: [44, 2, 2, 416290, 2]
oc_after:     [42, 2, 4, 416288, 4]
oc_compare:   [42, 2, 4, 416288, 4]
oc_counterfactual:         [41, 2, 5, 416287, 5]
oc_counterfactual_compare: [41, 2, 5, 416287, 5]
```

### (b) MATLAB authoritative algorithm (verbatim)
```matlab
function [nBound, posStrnds] = bindProteinToChromosomeStochastically(this,...
        enzymeIndex, nProteins, positionsStrands, lengths,...
        calcRegionWeightsFun, calcBindingPositionFun, calcNewRegionsFun, ...
        checkRegionSupercoiled)
    nBound = 0;
    if nProteins == 0
        posStrnds = zeros(0,2);
        return;
    end
    
    c = this.chromosome;
    footprint = this.enzymeDNAFootprints(enzymeIndex);
    if nargin < 4 || isscalar(positionsStrands) && isnan(positionsStrands)
        [positionsStrands, lengths] = find(c.polymerizedRegions);
    end
    if nargin < 6 || isempty(calcRegionWeightsFun)
        calcRegionWeightsFun = @calcRegionWeights;
    end
    if nargin < 7 || isempty(calcBindingPositionFun)
        calcBindingPositionFun = @calcBindingPosition;
    end
    if nargin < 8 || isempty(calcNewRegionsFun)
        calcNewRegionsFun = @calcNewRegions;
    end
    
    %% find accessible regions
    tf = ismembc(enzymeIndex, this.enzymeMonomerLocalIndexs);
    [rgnPosStrnds, rgnLens] = c.getAccessibleRegions(...
        this.enzymeGlobalIndexs(enzymeIndex( tf, 1), 1), ...
        this.enzymeGlobalIndexs(enzymeIndex(~tf, 1), 1));
    [rgnPosStrnds, rgnLens] = c.intersectRegions(...
        rgnPosStrnds, rgnLens, positionsStrands, lengths);
    
    %% compute probability of binding each region
    rgnProbs = calcRegionWeightsFun(rgnLens);
    
    %% randomly select regions to bind
    posStrnds = zeros(nProteins, 2);
    nBound = 0;
    for i = 1:nProteins
        if ~any(rgnProbs); break; end
        
        %pick a region to bind
        rgnIdx = this.randStream.randsample(numel(rgnProbs), 1, true, rgnProbs);
        
        %pick a position within region to bind
        offset = calcBindingPositionFun(this.randStream.rand, rgnLens(rgnIdx)) - 1;
        
        %store selected position and strand
        posStrnds(i, :) = rgnPosStrnds(rgnIdx,:) + [offset 0];
        
        %split region about new protein position
        [rgnPosStrnds, rgnLens, rgnProbs] = calcNewRegionsFun(rgnPosStrnds, rgnLens, rgnProbs, rgnIdx, offset);
        
        nBound = nBound + 1;
    end
    
    posStrnds = posStrnds(1:nBound, :);
end
```

```matlab
function weights = calcRegionWeights(lens)
    weights = max(0, lens - footprint + 1);
end

function position = calcBindingPosition(randReal, len)
    position = ceil(randReal * (len - footprint + 1));
end

function [rgnPosStrnds, rgnLens, rgnProbs] = calcNewRegions(rgnPosStrnds, rgnLens, rgnProbs, rgnIdx, offset)
    rgnPosStrnds(end + 1, :) = [
        rgnPosStrnds(rgnIdx, 1) + offset + footprint, rgnPosStrnds(rgnIdx, 2)];
    rgnLens(end + 1) = rgnLens(rgnIdx) - offset - footprint;
    rgnLens(rgnIdx) = offset;
    rgnProbs([rgnIdx end+1]) = calcRegionWeightsFun(rgnLens([rgnIdx end]));
end
```

```matlab
function [rgnPosStrnds, rgnLens, rgnProbs] = calcNewRegions(this, rgnPosStrnds, rgnLens, ~, rgnIdx, offset)
    c = this.chromosome;
    [rgnPosStrnds, rgnLens] = c.excludeRegions(rgnPosStrnds, rgnLens, ...
        [mod(rgnPosStrnds(rgnIdx,1)+offset -this.smcSepNt/2-this.smcSepProbCenter/2+this.enzymeDNAFootprints(this.enzymeIndexs_SMC_ADP)/2 -1, c.sequenceLen)+1 ...
        rgnPosStrnds(rgnIdx,2)], this.smcSepNt + this.smcSepProbCenter);
    rgnProbs = max(0, rgnLens - this.enzymeDNAFootprints(this.enzymeIndexs_SMC_ADP) + 1);
end
```

## Beat 3 — Plan
- Keep the edit surgical in `opencell/vivarium/karr_chromosome_condensation.py`, focused on the no-hints SMC position picker.
- Preserve chemistry and hint-path behavior so `test_karr_chromosome_condensation_l2_replay.py` remains green.
- Enforce two explicit RNG draws per bind event in order: weighted region pick first, then position pick.
- Preserve existing region construction/exclusion interfaces to avoid broader behavior churn.
- Do not touch any other process files, harness code, or pair-test logic.

## Beat 4 — Pre-mortem (Inversion)
- Way 1: L2.1 replay regression.
  Signal: `tests/vivarium/test_karr_chromosome_condensation_l2_replay.py` fails after sampler edit.
- Way 2: RNG draw count mismatch per bind.
  Signal: first divergence shifts earlier with larger ATP mismatch (e.g., tick 0-8 or |diff| > 2), indicating draw-sequence drift.
- Way 3: `Generator.choice(p=...)` transformation mismatch vs MATLAB `randsample`.
  Signal: chemistry direction remains right but DD drift persists at similar magnitude/ticks (distributional mismatch, no convergence gain).

## Beat 5 — Verification protocol (executed in order)
1. `bin\oc-pytest tests/vivarium/test_karr_chromosome_condensation_l2_replay.py -v`
2. `bin\oc-pytest tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py -v --tb=short`
3. `bin\oc-pytest tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k "ChromosomeCondensation" --tb=no -q`
4. Compared first divergence/diff against baseline (tick 9, ATP off-by-2).

## Code change summary
File changed:
- `opencell/vivarium/karr_chromosome_condensation.py`

Actual patch retained:
- In `_sample_binding_positions`:
  - region pick now uses one explicit uniform draw against cumulative weights (instead of `Generator.choice`), to mirror one MATLAB `randsample`-style draw.
  - position pick now uses one explicit uniform draw with MATLAB-style mapping `ceil(rand * n_bind_positions) - 1` (replacing `integers(...)`).

No other process file changed.

## Verification outcomes
- L2.1 replay: PASS.
- Cond+Seg DD: FAIL at tick 9, ATP diff -2 (same as baseline Day-35 record).
- Cond DS sweep (`-k "ChromosomeCondensation"`): 17 failed, 4 skipped, 0 passed (no observed pass-count gain).

## Drift comparison vs baseline
- Baseline: first divergence tick 9, ATP off-by-2.
- Current patch: first divergence tick 9, ATP off-by-2.
- Net: stable but no convergence improvement.

## Exit decision
- Threshold not met (`tick 50+` and `|diff| <= 1` not achieved).
- Kept only the minimal RNG-discipline patch that preserves current behavior and L2.1.
- Residual: sampler still intrinsically over-binds in no-hints honest-mode replay by tick 9.
