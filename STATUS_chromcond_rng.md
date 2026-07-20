# ChromosomeCondensation RNG alignment diagnosis

## Scope

Diagnosis only. I did not modify `opencell/` code.

## Answer

No. OC does not consume the same RNG stream as Karr for stochastic SMC binding.
The first divergence is before any position is chosen:

1. OC is not using Karr's MCG16807 / `MatlabRandStream` here at all. It seeds a
   NumPy generator instead:

```python
165:    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
166:        super().__init__(parameters)
167:        self._load_fixture(self.parameters["fixture_path"])
168:        self._load_trace_anchor(self.parameters["trace_path"])
169:        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
```

2. Karr's first stochastic step inside the binder is a weighted
   `this.randStream.randsample(...)` over `rgnProbs`, while OC's first
   stochastic step is a raw `self._rng.random()` followed by a manual cumulative
   search over Python-computed weights. Even if both happened to use one uniform
   draw internally, they are not consuming the same generator or the same API.

3. The region list being sampled is not guaranteed to match before the first
   draw. Karr samples from chromosome accessibility intersected with the
   `posStrnds` / `lens` provided by `ChromosomeCondensation.evolveState`; OC
   samples from `_build_available_intervals(...)`, which reconstructs intervals
   from `polymerizedRegions` plus `complex_bound` reconciliation.

Because of (1) and (3), RNG alignment is coupled to the geometry/input fix: you
cannot make the binding stream align unless OC first feeds the sampler the same
regions and then uses the same RNG primitive sequence as Karr.

## Karr call path

`ChromosomeCondensation.evolveState` computes the candidate regions, excludes
existing SMCs, then calls the generic chromosome-process binder:

```matlab
255:            c = this.chromosome;
256:            [posStrnds, lens] = find(c.polymerizedRegions);
257:            smcPosStrands = find(c.complexBoundSites == this.enzymeGlobalIndexs(this.enzymeIndexs_SMC_ADP));
258:            smcPosStrands = [
259:                mod(smcPosStrands(:,1)-this.smcSepNt/2-this.smcSepProbCenter/2+this.enzymeDNAFootprints(this.enzymeIndexs_SMC_ADP)/2 -1, c.sequenceLen)+1  2*ceil(smcPosStrands(:,2)/2)-1;
260:                mod(smcPosStrands(:,1)-this.smcSepNt/2-this.smcSepProbCenter/2+this.enzymeDNAFootprints(this.enzymeIndexs_SMC_ADP)/2 -1, c.sequenceLen)+1  2*ceil(smcPosStrands(:,2)/2)];
261:            [posStrnds, lens] = c.excludeRegions(posStrnds, lens, smcPosStrands, this.smcSepNt(ones(size(smcPosStrands, 1), 1), 1) + this.smcSepProbCenter);
266:            nBound = this.bindProteinToChromosomeStochastically(...
267:                this.enzymeIndexs_SMC_ADP,...
268:                nBindingMax, posStrnds, lens, [], [], @this.calcNewRegions);
```

Inside `ChromosomeProcessAspect.bindProteinToChromosomeStochastically`, the
explicit RNG-touching calls are, in order, once per attempted binding:

```matlab
80:            [rgnPosStrnds, rgnLens] = c.getAccessibleRegions(...
83:            [rgnPosStrnds, rgnLens] = c.intersectRegions(...
87:            rgnProbs = calcRegionWeightsFun(rgnLens);
92:            for i = 1:nProteins
93:                if ~any(rgnProbs); break; end
96:                rgnIdx = this.randStream.randsample(numel(rgnProbs), 1, true, rgnProbs);
99:                offset = calcBindingPositionFun(this.randStream.rand, rgnLens(rgnIdx)) - 1;
102:                posStrnds(i, :) = rgnPosStrnds(rgnIdx,:) + [offset 0];
105:                [rgnPosStrnds, rgnLens, rgnProbs] = calcNewRegionsFun(rgnPosStrnds, rgnLens, rgnProbs, rgnIdx, offset);
```

The default binding-position helper is:

```matlab
273:            function position = calcBindingPosition(randReal, len)
274:                position = ceil(randReal * (len - footprint + 1));
```

For condensation specifically, the region-update helper is:

```matlab
286:        function [rgnPosStrnds, rgnLens, rgnProbs] = calcNewRegions(this, rgnPosStrnds, rgnLens, ~, rgnIdx, offset)
287:            c = this.chromosome;
288:            [rgnPosStrnds, rgnLens] = c.excludeRegions(rgnPosStrnds, rgnLens, ...
289:                [mod(rgnPosStrnds(rgnIdx,1)+offset -this.smcSepNt/2-this.smcSepProbCenter/2+this.enzymeDNAFootprints(this.enzymeIndexs_SMC_ADP)/2 -1, c.sequenceLen)+1 ...
290:                rgnPosStrnds(rgnIdx,2)], this.smcSepNt + this.smcSepProbCenter);
291:            rgnProbs = max(0, rgnLens - this.enzymeDNAFootprints(this.enzymeIndexs_SMC_ADP) + 1);
```

So the Karr binder's ordered stochastic interface is:

1. `randStream.randsample(numel(rgnProbs), 1, true, rgnProbs)` to choose a
   region index.
2. `randStream.rand` to choose an offset inside that region.
3. Repeat after `calcNewRegions` mutates `rgnPosStrnds` / `rgnLens`.

## OC call path

OC's no-hints path builds its own interval set, then samples from that set with
`self._rng`:

```python
501:        intervals_by_strand = self._build_available_intervals(
502:            polymerized=polymerized,
503:            complex_bound=complex_bound,
504:        )
517:        bound_positions, bound_strands = self._sample_binding_positions(
518:            intervals_by_strand=intervals_by_strand,
519:            n_to_bind=bind_cap,
520:            sequence_len=polymerized.shape[0],
521:        )
```

The interval construction is not the same as Karr's `getAccessibleRegions` plus
`intersectRegions`; it starts directly from `polymerized.to_regions()` and the
possibly reconciled `complex_bound` sparse map:

```python
652:    def _build_available_intervals(
653:        self,
654:        *,
655:        polymerized: SparseTriplet,
656:        complex_bound: SparseTriplet,
657:    ) -> dict[int, list[tuple[int, int]]]:
662:        for start, strand, length in polymerized.to_regions():
674:        for pos, strand, enzyme_idx in complex_bound.to_regions():
675:            if int(enzyme_idx) != self.smc_adp_global_index:
676:                continue
682:                exclude_start = (int(pos) + self._smc_exclusion_offset) % sequence_len
684:                for lo, hi in _split_circular_region(
685:                    exclude_start,
686:                    self._smc_exclusion_len,
687:                    sequence_len,
688:                ):
```

Inside `_sample_binding_positions`, the explicit RNG calls are, in order, once
per successful sample:

```python
706:        for _ in range(int(n_to_bind)):
707:            regions: list[tuple[int, int, int]] = []
714:            weights = np.asarray(
715:                [max(0, int(length) - self._smc_bindable_span + 1) for _, _, length in regions],
716:                dtype=np.float64,
717:            )
722:            region_pick_u = float(self._rng.random())
723:            cumulative = np.cumsum(weights, dtype=np.float64)
724:            threshold = region_pick_u * total_weight
725:            region_idx = int(np.searchsorted(cumulative, threshold, side="right"))
728:            region_start, region_strand, region_len = regions[region_idx]
733:            rand_real = float(self._rng.random())
742:                offset = max(0, int(math.ceil(u * n_bind_positions)) - 1)
743:            bind_pos = int((region_start + offset) % sequence_len)
747:            exclude_start = int((bind_pos + self._smc_exclusion_offset) % sequence_len)
749:            for lo, hi in _split_circular_region(
750:                exclude_start,
751:                self._smc_exclusion_len,
752:                sequence_len,
753:            ):
```

The executed probe in `tmp/probe_chromcond_rng.py` confirmed the OC sampler is
exactly two `random()` calls per successful bind in this path:

```json
{
  "rng_calls": [
    {"method": "random", "value": 0.2},
    {"method": "random", "value": 0.6},
    {"method": "random", "value": 0.8},
    {"method": "random", "value": 0.1}
  ],
  "positions": [4, 20],
  "strands": [0, 1]
}
```

## First divergence

The first concrete divergence is the very first region-selection step:

- Karr: `this.randStream.randsample(numel(rgnProbs), 1, true, rgnProbs)` on an
  MCG16807-backed `randStream`, after `getAccessibleRegions` and
  `intersectRegions`.
- OC: `self._rng.random()` from `np.random.default_rng(...)`, followed by manual
  cumulative-weight selection over `_build_available_intervals(...)`.

That means the mismatch is not just "same draws, different results." It is a
different RNG engine, a different stochastic API for region selection, and
potentially different region/length inputs before the first draw.

After that, the offset draw is structurally similar:

- Karr: `ceil(randReal * (len - footprint + 1)) - 1`
- OC: `ceil(u * (region_len - _smc_bindable_span + 1)) - 1`

So if the same region lengths were presented and the same uniform draw were
consumed from the same engine, the offset formula could align. The blocker is
that the preceding region-selection call and candidate-region construction do
not align today.

## Coupled finding

Yes: geometry/input alignment and RNG alignment are coupled here.

Even if OC swapped in the MCG16807 adapter, it would still diverge if
`_build_available_intervals(...)` does not reproduce Karr's
`getAccessibleRegions -> intersectRegions -> excludeRegions` region list from
the real chromosome geometry. Conversely, even perfect geometry would still not
bit-align while OC keeps using `np.random.default_rng(...)` plus manual weighted
selection instead of Karr's `randStream.randsample(...)` then `randStream.rand`.

## Recommended fix direction (not implemented)

Port the binding path at the binder level, not just the final position formula:
have the no-hints condensation path construct the same `rgnPosStrnds` /
`rgnLens` Karr samples from, then consume an MCG16807-backed stream with the
same call order as Karr's binder: weighted region pick first, offset pick
second, then region update via the condensation-specific `calcNewRegions`
exclude logic. Any OC-only reconciliation and post-sampling bonus appends in the
no-hints path should be removed or isolated, because they change the sampled
region set and final bound positions independently of RNG alignment.
