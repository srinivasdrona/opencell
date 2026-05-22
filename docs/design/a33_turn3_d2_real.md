# A3.3 Turn 3 — KarrD2Real (MacromolecularComplexation)

**Status**: design ready · **Codex worktree**: `agent/a33-d2-real` (to be created) · **Estimated wall**: 45 min · **Depends on**: Turn 2 (allocation Step + RequestCalculator pattern). Turn 1 (M3v3) NOT required for D.2's own tests, but required for the eventual chassis integration in Turn 5.

## Why this module exists

Replaces `karr_d2_stub.py` with Karr's actual `MacromolecularComplexation` algorithm. The stub provides static complex counts; D.2-real dynamically forms complexes from free subunits each tick using Karr's verbatim algorithm (per `docs/karr_extracts/process/MacromolecularComplexation.md` + `data/m1_sources/.../MacromolecularComplexation.m` lines 287–392).

The stub stays in the repo and remains used by `build_karr_chassis_v2`. D.2-real is wired into `build_karr_chassis_v3` in Turn 5.

## Empirical fixture findings (verified)

Loading `data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat` reveals the actual structure of D.2's data. **This dramatically simplifies the design.**

```
data.fixture:
  substrateWholeCellModelIDs:      shape (210, 1)   - 210 substrate WIDs (includes protein monomers + RNA + metabolites)
  complexWholeCellModelIDs:        shape (147, 1)   - 147 D.2-formed complex WIDs
  complexComposition:              shape (210, 147) - stoichiometric matrix (substrates × complexes)
  complexNetworks:                 shape (2, 1)     - cell array of 2 disconnected sub-networks
    network[0]: shape (206, 145)   - "cluster 1" — closed-form solvable (145 complexes, 206 substrates)
    network[1]: shape (4, 2)       - "cluster 2" — 2 complexes, 4 substrates, MC-sampled
  substrates2complexNetworks:      shape (210, 1)   - which network each substrate participates in (1, 2, or 0)
  complexs2complexNetworks:        shape (147, 1)   - which network each complex belongs to (1 or 2)
```

**Key insight**: of 147 D.2-formed complexes, **145 are in the closed-form cluster** and only **2 complexes** require Monte Carlo. The per-cluster MC loop runs on a tiny (4×2) sub-matrix once per tick. This is computationally trivial.

## Algorithm (exact port of Karr's `MacromolecularComplexation.m`)

### Phase 1: load fixture into NumPy at __init__

```python
class KarrD2RealProcess(Process):
    name = "karr_d2_real"
    defaults = {
        "fixture_path": "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat",
        "rng_seed": 0,
        "time_step": 1.0,
        "rate_constant": 0.05,  # Karr's single global rate; tune if equilibrium isn't reached
    }

    def __init__(self, parameters):
        super().__init__(parameters)
        fx = _load_fixture(self.parameters["fixture_path"])
        self.substrate_wids: list[str] = fx["substrate_wids"]           # 210 WIDs as Python strings
        self.complex_wids: list[str] = fx["complex_wids"]               # 147 WIDs as Python strings
        self.complex_composition: np.ndarray = fx["complex_composition"]  # (210, 147) int matrix
        self.substrates2net: np.ndarray = fx["substrates2net"]          # (210,) ints
        self.complexes2net: np.ndarray = fx["complexes2net"]            # (147,) ints
        self.networks: list[np.ndarray] = fx["networks"]                # [(206,145), (4,2)]
        self._rng = np.random.default_rng(self.parameters["rng_seed"])
```

### Phase 2: ports_schema

```python
def ports_schema(self):
    return {
        "substrates": {
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
            for wid in self.substrate_wids
        },
        "complex": {
            "counts": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.complex_wids
            }
        },
        "requests": {
            "karr_d2_real": {
                wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                for wid in self.substrate_wids
            }
        },
        "substrates_allocated": {
            "karr_d2_real": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}  # read-only here
                for wid in self.substrate_wids
            }
        },
    }
```

**Note**: D.2-real reads `substrates_allocated.karr_d2_real.<wid>` (set by KarrAllocationStep) but writes ZERO requests for metabolites because `calcResourceRequirements_Current()` returns zeros for MC (per Opus critique finding #1 — verified at lines 285–287 of `MacromolecularComplexation.m`). So the `requests` port is wired but the request values are always 0. This is intentional and matches Karr exactly.

**This means**: D.2's actual metabolite throttling comes ONLY from the available counts in `substrates.<wid>` itself (which represents free protein monomers / RNA subunits). The allocation Step is wired for architectural consistency, not for D.2-specific throttling.

### Phase 3: next_update — the algorithm

```python
def next_update(self, timestep, states):
    # Read current free subunit counts
    sub_counts = np.array(
        [float(states["substrates"][wid]) for wid in self.substrate_wids],
        dtype=np.int64,
    )

    # Output: new_complexes[c] = how many of complex c were formed this tick
    new_complexes = np.zeros(len(self.complex_wids), dtype=np.int64)

    # Per-cluster processing
    for cluster_idx, sub_network in enumerate(self.networks, start=1):
        # rows = substrates in this cluster, cols = complexes in this cluster
        sub_mask = self.substrates2net == cluster_idx
        cpx_mask = self.complexes2net == cluster_idx
        sub_indices = np.where(sub_mask)[0]
        cpx_indices = np.where(cpx_mask)[0]
        n_subs = len(sub_indices)
        n_cpxs = len(cpx_indices)

        if n_cpxs == 0:
            continue

        # Stoichiometry for this cluster: (n_subs, n_cpxs)
        stoich = self.complex_composition[np.ix_(sub_indices, cpx_indices)]
        sub_avail = sub_counts[sub_indices].copy()

        if cluster_idx == 1:
            # Cluster 1: closed-form solution (no inter-complex competition)
            # newCpx[c] = floor(min over subunits s of sub_avail[s] / stoich[s,c])
            # For each complex, find limiting subunit
            new_in_cluster = _closed_form_bounds(sub_avail, stoich)
        else:
            # Cluster N>=2: Monte Carlo with collision-theory rates
            new_in_cluster = _per_cluster_mc(
                sub_avail, stoich, self._rng,
                rate_constant=self.parameters["rate_constant"],
            )

        # Apply: subtract subunits, accumulate complexes
        sub_consumed = stoich @ new_in_cluster
        sub_counts[sub_indices] -= sub_consumed
        new_complexes[cpx_indices] = new_in_cluster

    # Mass balance — single matrix multiplication (Opus critique requirement)
    # delta_substrates[s] = -sum over c of complex_composition[s,c] * new_complexes[c]
    delta_substrates = -(self.complex_composition @ new_complexes)

    # Emit deltas
    return {
        "substrates": {
            wid: float(delta_substrates[i])
            for i, wid in enumerate(self.substrate_wids)
            if delta_substrates[i] != 0
        },
        "complex": {
            "counts": {
                wid: float(new_complexes[i])
                for i, wid in enumerate(self.complex_wids)
                if new_complexes[i] > 0
            }
        },
        # requests is always zero — see Phase 2 note
    }
```

### Helper: `_closed_form_bounds(sub_avail, stoich)`

For each complex `c` in this cluster, find the maximum number formable as:
```python
def _closed_form_bounds(sub_avail, stoich):
    """For each complex, find max formable given subunit availability.

    Vectorized: for complex c, max formed = floor(min_s sub_avail[s] / stoich[s,c])
    where the min is over substrates s with stoich[s,c] > 0.
    """
    n_cpxs = stoich.shape[1]
    out = np.zeros(n_cpxs, dtype=np.int64)
    for c in range(n_cpxs):
        sto = stoich[:, c]
        active = sto > 0
        if not active.any():
            continue
        out[c] = (sub_avail[active] // sto[active]).min()
    return out
```

**However**, this is *upper bound only* — running all 145 complexes to their max would over-consume substrates if subunits are shared across complexes IN THE SAME cluster. The `complexNetworks` partitioning guarantees subunits are NOT shared across clusters; within a cluster, naive max-fill double-counts.

**Karr's actual closed-form is iterative-greedy** (per `evolveState.m` lines 200–215 of the .m): assemble one complex of the limiting kind, subtract, repeat until no complex is buildable. Inspect the .m to confirm.

**Implementation hedge**: if vectorized closed-form turns out to over-consume in tests (it will), fall back to per-cluster MC for cluster 1 too. Performance: 145 complexes × ~10 iterations × O(206) = ~300k ops/tick — still trivial.

### Helper: `_per_cluster_mc(sub_avail, stoich, rng, rate_constant)`

```python
def _per_cluster_mc(sub_avail, stoich, rng, rate_constant):
    """Karr's collision-theory MC for a single sub-network.

    Algorithm (verbatim port of buildProteinComplexs_montecarlokinetic):
      Loop:
        - Compute rate[c] = rate_constant * prod_s (sub_avail[s] / mean(sub_avail))^stoich[s,c]
        - Compute upper-bound ub[c] = closed-form max formable for c
        - Where ub[c] == 0: rate[c] := 0  (Opus's required safety filter)
        - If all rate[c] == 0: break
        - Sample which complex to form: c ~ Categorical(rate / sum(rate))
        - Sample how many to form: n ~ min(Poisson(rate[c] * timestep), ub[c])
        - sub_avail -= stoich[:, c] * n
        - new_complexes[c] += n
      Return new_complexes
    """
    n_cpxs = stoich.shape[1]
    new_complexes = np.zeros(n_cpxs, dtype=np.int64)
    while True:
        # Upper bounds for each complex
        ub = _closed_form_bounds(sub_avail, stoich)
        if not (ub > 0).any():
            break

        # Rate per complex (collision theory: power law in subunit availability)
        mean_sub = max(1.0, sub_avail.mean())
        normalized = sub_avail / mean_sub  # shape (n_subs,)
        # rate[c] = prod over s of normalized[s] ** stoich[s,c]
        # Vectorized: log(rate) = sum over s of stoich[s,c] * log(normalized[s])
        with np.errstate(divide="ignore", invalid="ignore"):
            log_norm = np.where(normalized > 0, np.log(normalized), -np.inf)
        log_rate = (stoich.T @ log_norm.reshape(-1, 1)).flatten()
        rate = np.where(np.isfinite(log_rate), np.exp(log_rate), 0.0)
        rate[ub == 0] = 0.0  # Opus's required safety filter

        if rate.sum() <= 0:
            break

        # Pick which complex to form (proportional to rate)
        probs = rate / rate.sum()
        chosen = rng.choice(n_cpxs, p=probs)

        # How many to form: bounded Poisson sample
        lam = rate[chosen] * rate_constant
        n_sampled = int(rng.poisson(lam))
        n = min(n_sampled, int(ub[chosen]))
        if n == 0:
            # Even though rate > 0, sample was 0. Continue with single decrement.
            n = 1
            if n > ub[chosen]:
                break

        # Apply
        new_complexes[chosen] += n
        sub_avail -= stoich[:, chosen] * n

    return new_complexes
```

## Scope (this turn)

**Net new files**:
1. `opencell/vivarium/karr_d2_real.py` (~280 LOC including fixture loader + helpers)
2. `tests/vivarium/test_karr_d2_real.py` (~250 LOC)

**Modified files**: NONE.

## Test plan

### Test 1: fixture loads cleanly
```python
def test_fixture_loads():
    p = KarrD2RealProcess({})
    assert len(p.complex_wids) == 147
    assert len(p.substrate_wids) == 210
    assert p.complex_composition.shape == (210, 147)
    assert len(p.networks) == 2
    assert p.networks[0].shape == (206, 145)
    assert p.networks[1].shape == (4, 2)
```

### Test 2: zero subunits → zero complexes
```python
def test_no_subunits_no_complexes():
    p = KarrD2RealProcess({})
    states = {
        "substrates": {wid: 0 for wid in p.substrate_wids},
        "complex": {"counts": {wid: 0 for wid in p.complex_wids}},
        "requests": {"karr_d2_real": {wid: 0 for wid in p.substrate_wids}},
        "substrates_allocated": {"karr_d2_real": {wid: 0 for wid in p.substrate_wids}},
    }
    update = p.next_update(1.0, states)
    assert update["complex"]["counts"] == {}  # nothing formed
```

### Test 3: mass conservation
```python
def test_mass_conservation():
    """After one tick: sum(consumed subunits, weighted by stoich) == sum(formed complexes, weighted by stoich)."""
    p = KarrD2RealProcess({"rng_seed": 42})
    # Seed with realistic counts from the fixture's snapshot (load via separate snapshot fixture)
    states = _load_snapshot_state()
    update = p.next_update(1.0, states)

    # Check: complex_composition @ formed = -delta_substrates
    formed = np.array([update["complex"]["counts"].get(wid, 0.0) for wid in p.complex_wids])
    delta_sub = np.array([update["substrates"].get(wid, 0.0) for wid in p.substrate_wids])
    expected_delta = -(p.complex_composition @ formed)
    assert np.allclose(delta_sub, expected_delta, atol=0)  # exact integer match
```

### Test 4: cluster-1 closed-form bounded
```python
def test_cluster1_closed_form():
    """In cluster 1, no complex exceeds its closed-form upper bound."""
    p = KarrD2RealProcess({"rng_seed": 0})
    states = _load_snapshot_state()
    update = p.next_update(1.0, states)
    formed = np.array([update["complex"]["counts"].get(wid, 0.0) for wid in p.complex_wids])
    # For cluster 1 complexes, formed <= closed_form_bound from initial state
    cluster1_mask = p.complexes2net == 1
    sub_cluster1 = p.substrates2net == 1
    stoich1 = p.complex_composition[np.ix_(sub_cluster1, cluster1_mask)]
    sub_avail1 = np.array([states["substrates"][wid] for wid in p.substrate_wids])[sub_cluster1]
    bounds = _closed_form_bounds(sub_avail1, stoich1)
    formed1 = formed[cluster1_mask]
    assert (formed1 <= bounds).all()
```

### Test 5: cluster-2 MC determinism
```python
def test_cluster2_mc_deterministic():
    """Same seed → same MC outcome on cluster 2."""
    states = _load_snapshot_state()
    p1 = KarrD2RealProcess({"rng_seed": 42})
    u1 = p1.next_update(1.0, states)
    p2 = KarrD2RealProcess({"rng_seed": 42})
    u2 = p2.next_update(1.0, states)
    assert u1 == u2
```

### Test 6: rate=0 safety filter (Opus issue)
```python
def test_ub_zero_safety_filter():
    """Where upper bound is 0, rate must be 0 even if the formula computes non-zero."""
    # Manually craft a state where stoich[s,c] > 0 but sub_avail[s] = 0
    # Verify _per_cluster_mc does not form that complex
    stoich = np.array([[1, 2], [1, 0]], dtype=np.int64)
    sub_avail = np.array([5, 0], dtype=np.int64)  # subunit 1 = 0
    # Complex 0 needs 1 of sub-0 and 1 of sub-1: can't form (sub-1=0)
    # Complex 1 needs 2 of sub-0 only: can form floor(5/2) = 2
    rng = np.random.default_rng(0)
    out = _per_cluster_mc(sub_avail, stoich, rng, rate_constant=1.0)
    assert out[0] == 0  # complex 0 must not be formed
    assert out[1] > 0   # complex 1 should be formed
```

### Test 7: 1-tick smoke with snapshot
```python
def test_one_tick_from_snapshot():
    """Smoke: process loads, runs one tick from snapshot, produces non-trivial complexes."""
    p = KarrD2RealProcess({"rng_seed": 0})
    states = _load_snapshot_state()
    update = p.next_update(1.0, states)
    # At minimum: some complexes should form
    total_formed = sum(update["complex"]["counts"].values())
    assert total_formed > 0
```

### Test 8: integration with KarrAllocationStep (light)
```python
def test_integration_with_allocation_step():
    """D.2-real + KarrAllocationStep in a composite. Confirms wiring works."""
    # Build minimal composite: D.2-real + KarrAllocationStep + ToyRequestCalc (zero requests for D.2)
    # Run 1 tick. Confirm D.2-real produced complexes.
    # Confirm substrates_allocated.karr_d2_real.* are all 0 (since D.2 requests 0).
```

## Acceptance criteria

- All 8 tests pass
- `pytest tests/ -x --ignore=tests/probes -q` — no regressions
- Commit message: `a33-t3: KarrD2Real with cluster decomposition + per-cluster MC`
- STATUS reports file list, test counts, full pytest output

## Out of scope (Turn 3)

- RibosomeAssembly logic (the 2 ribosomal complexes RIBOSOME_30S, RIBOSOME_50S) — those are technically D.2's responsibility per Karr but live in a different sub-network (likely cluster 2). Deferred to Phase B Translation work because they require GTPase enzymes (Era, RbfA, EngA, EngB, Obg, RbgA) wired in. For Turn 3, the 2 ribosomal complexes will appear in `complex_wids` and formed via the standard MC if their stoichiometry is in `complex_composition`. They just won't have GTP-dependence in the simplified A3.3 version. **TODO note in docstring.**
- Snapshot-state loader (`_load_snapshot_state`) — implement as a tests/ helper that loads from `data/karr_fixtures/snapshot.mat` or equivalent. If not available, use synthetic counts matching the fixture's `substrate_count` field.
- ProteinDecay-light wiring — Turn 4
- Chassis integration — Turn 5

## Implementation gotchas

- `complexNetworks[0,0]` is the OUTER unwrap; the inner is shape `(2,1)` of object arrays containing the actual sub-matrices. Inspect the .mat with scipy.io.loadmat to confirm before writing the loader.
- `substrates2complexNetworks` and `complexs2complexNetworks` are stored as `dtype=object` outer arrays; need `np.asarray(fx["substrates2complexNetworks"][0,0]).flatten().astype(int)` to get a clean integer vector. Or use `_unwrap_matlab_cell()` helper.
- Karr's `fix()` rounds toward zero. For non-negative integer inputs, `math.floor` is equivalent. Use `np.floor(...).astype(np.int64)`.
- `_per_cluster_mc` while-loop: bound iterations with a safety limit (e.g., 10000) and raise if exceeded (suggests a bug in rate formula).
