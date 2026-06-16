# Cytokinesis OC vs Karr Static SUT Parity Audit

## Overall Verdict

**DIVERGENT_DOCUMENTED** — OC is an intentional "Karr-light v1" simplification, explicitly documented in the OC file's own docstring (lines 1-12).

## Algorithm Summary

**Karr** (`Cytokinesis.m:173-259`): Four stochastic phases operating on an edge-wise FtsZ polygon ring model. Each phase iterates over individual ring edges with per-element `randStream.rand()` draws against rate thresholds. Tracks polymer state transitions (GTP→GDP), enzyme binding/unbinding, substrate hydrolysis (H2O→Pi+H), and explicit pinched-diameter geometry evolution. Multiple RNG draws per tick.

**OC** (`karr_cytokinesis.py:199-251`): Bulk progress ratchet. `division_progress` increments by `active_division_rate_per_s * dt`, capped by allocated GTP × `progress_per_gtp`. Division completes when progress reaches 1.0. Zero RNG draws. No edge-wise mechanics, no polymer state transitions, no geometry.

## Step-by-Step Mapping

| Step | Karr `evolveState` | OC `next_update` | Verdict |
|---|---|---|---|
| 1. Activation gate | `chromosome.segregated` must be true (`Cytokinesis.m:174-176`) | `ftsz_ring_complete` AND `segregation_progress >= 1.0` (`karr_cytokinesis.py:253-257`) | OC_SIMPLIFIED — OC adds an extra `ftsz_ring_complete` gate not in Karr's evolveState (though Karr checks ring state implicitly via phase conditions) |
| 2. Bind first straight filaments | Per-edge loop with `randStream.rand() <= rateFilamentBindingMembrane` and enzyme check (`Cytokinesis.m:181-192`) | Not implemented | DIVERGENT |
| 3. Bind second straight filaments | Per-edge loop with same stochastic check (`Cytokinesis.m:193-201`) | Not implemented | DIVERGENT |
| 4. Unbind residual bent filaments | Per-element `randStream.rand() <= rateFilamentDissociation` (`Cytokinesis.m:204-214`) | Not implemented | DIVERGENT |
| 5. GTP hydrolysis to bend filaments | Per-edge `randStream.rand() <= rateFtsZGtpHydrolysis` + H2O substrate check (`Cytokinesis.m:217-233`) | Bulk: GTP consumed proportional to progress delta (`karr_cytokinesis.py:223-226`) | DIVERGENT |
| 6. Geometry update | `calcNextPinchedDiameter` when all edges bent (`Cytokinesis.m:234-236`) | `division_progress` linear ratchet (`karr_cytokinesis.py:220-224`) | DIVERGENT |
| 7. First bent ring dissociation | Per-edge `randStream.rand() <= rateFilamentDissociation` (`Cytokinesis.m:239-250`) | Not implemented | DIVERGENT |
| 8. Division completion | Implicit via geometry reaching zero diameter across multiple cycles | `division_progress >= 1.0` triggers `division_complete = True` (`karr_cytokinesis.py:247-249`) | DIVERGENT |

## RNG Draw Inventory

| Karr draw | OC draw | Match |
|---|---|---|
| `randStream.rand()` per edge in Phase 1 (bind first straight, `Cytokinesis.m:184`) | None | NO |
| `randStream.rand()` per edge in Phase 2 (bind second straight, `Cytokinesis.m:194`) | None | NO |
| `randStream.rand()` per element in Phase 3 (dissociate residual, `Cytokinesis.m:206`) | None | NO |
| `randStream.rand()` per edge in Phase 4 (GTP hydrolysis, `Cytokinesis.m:220`) | None | NO |
| `randStream.rand()` per edge in Phase 5 (dissociate first bent, `Cytokinesis.m:241`) | None | NO |

OC has **zero** RNG draws. Karr has **5 classes** of per-element stochastic draws. The processes are fundamentally different in their stochastic structure.

## Substrate-Availability Handling

**Karr**: H2O is checked per-edge during GTP hydrolysis phase only (`Cytokinesis.m:220`). H2O, Pi, and H are updated stoichiometrically after each successful hydrolysis event. Enzyme (FtsZ polymer) availability is checked per-edge.

**OC**: GTP (not H2O) is the substrate constraint. Available GTP caps the progress delta. No per-edge enzyme checks. Substrate stoichiometry is reduced to a single `progress_per_gtp` coupling constant.

## Documented Divergences

The OC file's docstring (`karr_cytokinesis.py:1-12`) explicitly states:

> Karr-light v1 scope:
> - Bulk cytokinesis progress ratchet
> - Dual-gate activation
> - Allocation-bounded GTP consumption
>
> Deferred to v2:
> - Edge-wise FtsZ polygon mechanics
> - Per-monomer FtsZ GTP/GDP polymer state transitions
> - Explicit pinched-diameter geometry evolution

This is a **deliberate architectural simplification**, not an accidental bug. The OC port replaces Karr's multi-phase stochastic edge-wise ring mechanics with a single deterministic progress ratchet that produces the same qualitative outcome (division eventually completes) without modeling the intermediate FtsZ polymer dynamics.

## Implications

- The DIVERGENT_DOCUMENTED label is correct — no algorithm fix is possible without implementing the full FtsZ ring mechanics (v2 scope).
- For L2.event purposes, this process can be validated on **division timing** (when does division_complete become true?) but not on **mechanism fidelity** (the intermediate bind/bend/dissociate dynamics are absent).
- The absence of RNG draws means OC's cytokinesis is fully deterministic given its inputs, while Karr's is stochastic.
