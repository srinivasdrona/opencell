# Chassis v6 — Full 28-Process Composite Implementation

You are a Codex session. Read `SESSION_CONTEXT.md` first (8 hard rules).

## Token budget
**~180k**. This is the largest turn of Phase D. It's allowed because it bundles three pieces of work that share context (composite wiring + CPK-002 + CPK-003 fixes). Commit at every checkpoint (~7 expected). If you approach 140k without hitting checkpoint 6, commit current WIP and STOP with `status: PARTIAL` — Azure throttles at ~200k.

## Mission

Land `build_karr_chassis_v6` — the full 28-process composite — in `opencell/vivarium/karr_composite.py`. This unblocks E.1 (real trajectory match) and Phase E generally.

## Three bundled work items

1. **Composite wiring** (main): wire all 28 processes into one VivariumComposite per `docs/design/pd_final_chassis_v6.md`. Inherit chassis_v5 wiring + add HostInteraction + the previously-missing processes now on main.

2. **CPK-002 fix** (chromosome.damage_sites split): per `docs/design/cpk_dispositions_2026-05-23.md` §CPK-002. Split into `damage_events_cumulative` + `repair_events_cumulative`. Add `chromosome_views.current_damage_sites()` helper.

3. **CPK-003 fix** (fork position path alignment): per `docs/design/cpk_dispositions_2026-05-23.md` §CPK-003. Change `karr_dna_damage.py` to read `chromosome.fork_position_bp.left/right` instead of `chromosome.fork_positions`.

Bundling these into one turn is intentional — v6 wiring touches the chromosome.* topology anyway, and pre-existing CPK schema conflicts will break v6 invariants if we wire-first-fix-later.

## Prerequisites
Verify before starting:
- `naming-drift-rename` merged: `karr_m1.py` should NOT exist; `karr_metabolism.py` SHOULD exist
- `karr_d2_real.py` should NOT exist; `karr_macromolecular_complexation.py` SHOULD exist (class: `MacromolecularComplexationProcess`)
- `karr_rna_decay.py` present (RNADecay #13)
- `karr_host_interaction.py` present (the re-merged HostInteraction)
- Full suite green on main: ≥883 pass (or higher if naming-drift added)

If any prerequisite missing, STOP and write to STATUS.md.

## Design sources (READ FIRST, IN ORDER)

1. `docs/design/pd_final_chassis_v6.md` — canonical v6 spec; 28-process scorecard skeleton; topology hints
2. `docs/design/cpk_dispositions_2026-05-23.md` — CPK-002 and CPK-003 fix specs
3. `docs/design/pc_final_chassis_v5.md` — chassis_v5 wiring (your starting point)
4. `opencell/vivarium/karr_composite.py` — existing `build_karr_chassis_v5()` (extend, don't rewrite)

## Process inventory (all 28 must be wired)

After naming-drift, canonical module → class mapping:

| # | Module | Class |
|---|---|---|
| 1 | karr_replication | Replication |
| 2 | karr_replication_initiation | ReplicationInitiation |
| 3 | karr_dna_supercoiling | DnaSupercoiling |
| 4 | karr_chromosome_condensation | ChromosomeCondensation |
| 5 | karr_chromosome_segregation | ChromosomeSegregation |
| 6 | karr_dna_damage | DnaDamage |
| 7 | karr_dna_repair | DnaRepair |
| 8 | karr_ftsz_polymerization | FtsZPolymerization |
| 9 | karr_cytokinesis | Cytokinesis |
| 10 | karr_terminal_organelle_assembly | TerminalOrganelleAssembly |
| 11 | karr_cell_cycle_coordinator | CellCycleCoordinator |
| 12 | karr_host_interaction | HostInteraction |
| 13 | karr_rna_decay | RnaDecay |
| 14 | karr_rna_processing | RnaProcessing |
| 15 | karr_rna_modification | RnaModification |
| 16 | karr_trna_aminoacylation | TrnaAminoacylation |
| 17 | karr_ribosome_assembly | RibosomeAssembly |
| 18 | karr_protein_processing_i | ProteinProcessingI |
| 19 | karr_protein_processing_ii | ProteinProcessingII |
| 20 | karr_protein_folding | ProteinFolding |
| 21 | karr_protein_modification | ProteinModification |
| 22 | karr_protein_translocation | ProteinTranslocation |
| 23 | karr_protein_activation | ProteinActivation |
| 24 | karr_protein_decay_light | ProteinDecayLight |
| 25 | karr_macromolecular_complexation | MacromolecularComplexationProcess |
| 26 | karr_metabolism | KarrMetabolismProcess |
| 27 | karr_transcription | KarrTranscriptionProcess (use the v3 variant per central-dogma chassis) |
| 28 | karr_translation | KarrTranslationProcess (use the v3 variant) |
| (+) | karr_transcriptional_regulation | TranscriptionalRegulation |
| (+) | karr_allocation_step | KarrAllocationStep |

That's 28 biology processes + the allocation/coordinator infrastructure. Use the v3 transcription/translation variants where central-dogma chassis depends on them (cross-check pc_final_chassis_v5 wiring).

Verify your inventory by reading first ~10 lines of each `opencell/vivarium/karr_*.py` and confirming class names.

## CHASSIS_V6_EXPECTED_PROCESS_KEYS

Export this module-level constant from `karr_composite.py`:
```python
CHASSIS_V6_EXPECTED_PROCESS_KEYS = (
    "karr_replication",
    "karr_replication_initiation",
    # ... all 28 process keys (canonical names from above table)
    "karr_cell_cycle_coordinator",
    "karr_host_interaction",
)
```

E.1 test and E-final G1 gate both assert `len(CHASSIS_V6_EXPECTED_PROCESS_KEYS) == 28`.

## Test plan

Create `tests/integration/test_karr_chassis_v6.py`:

```python
def test_v6_builds():
    composite = build_karr_chassis_v6()
    proc_keys = composite["processes"].keys()
    assert set(proc_keys) >= set(CHASSIS_V6_EXPECTED_PROCESS_KEYS)

def test_v6_one_tick():
    """One tick completes without schema warnings."""
    composite = build_karr_chassis_v6()
    engine = Engine(composite=composite, ...)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        engine.update(1.0)
    # state still valid
    state = engine.state.get_value()
    assert "chromosome" in state
    assert "rna" in state
    assert "protein" in state

def test_v6_short_run_100s():
    """100 ticks complete; mass-balance reasonable."""
    composite = build_karr_chassis_v6()
    engine = Engine(composite=composite, ...)
    engine.update(100.0)
    ts = engine.emitter.get_timeseries()
    # dry mass should grow monotonically (or near-monotonically)
    masses = ts["cell_geometry"]["dry_mass_g"]
    assert masses[-1] > masses[0] * 0.99  # allow small numerical jitter

def test_v6_cpk_002_resolved():
    """CPK-002: chromosome.damage_sites split into damage_events / repair_events."""
    composite = build_karr_chassis_v6()
    # schema check via topology
    schema = composite.get_schema()
    assert "damage_events_cumulative" in schema["chromosome"]
    assert "repair_events_cumulative" in schema["chromosome"]

def test_v6_cpk_003_resolved():
    """CPK-003: karr_dna_damage reads fork_position_bp.left/right, not fork_positions."""
    # inspect dna_damage process schema
    from opencell.vivarium.karr_dna_damage import DnaDamage
    proc = DnaDamage({})
    ports = proc.ports_schema()
    chrom = ports.get("chromosome", {})
    assert "fork_position_bp" in chrom
    assert "fork_positions" not in chrom  # legacy path removed
```

Use `@pytest.mark.slow` on `test_v6_short_run_100s` (longest at ~30-60s).

## Commit checkpoints (target 7 commits)

1. Imports + inventory verification + `CHASSIS_V6_EXPECTED_PROCESS_KEYS` constant → commit "v6: inventory constants"
2. CPK-002 schema split (damage_events / repair_events + helper) → commit "v6/cpk-002: damage_sites split"
3. CPK-003 fork-position alignment → commit "v6/cpk-003: dna_damage reads fork_position_bp"
4. `build_karr_chassis_v6()` function — wiring core 25 processes (replication/DNA/cytokinesis + RNA + protein + cell-cycle + allocation) → commit "v6: core composite wiring"
5. Add HostInteraction + TerminalOrganelle wiring + topology hookups → commit "v6: host + terminal organelle wiring"
6. Tests `test_karr_chassis_v6.py` — first 3 tests passing → commit "v6: smoke tests pass"
7. CPK regression tests + final assertions → commit "v6: cpk regression tests"

If you hit token pressure between checkpoints 4-7, the priority is to LAND checkpoint 4 (core wiring) — that's what unblocks E.1.

## Hard rules
- Narrow pytest in the inner loop: `pytest -x tests/integration/test_karr_chassis_v6.py` per checkpoint
- DO NOT run full suite until after checkpoint 7
- DO NOT add new processes — all 28 already exist on main
- DO NOT modify existing process modules EXCEPT for CPK-002 (karr_dna_damage, karr_dna_repair) and CPK-003 (karr_dna_damage). All other modules: import only.
- DO NOT change v3/v4/v5 chassis builders — extend, don't replace
- Update `opencell/vivarium/__init__.py` to re-export new symbols

## Acceptance
- `build_karr_chassis_v6()` returns a valid composite with 28 process keys
- All 5 chassis_v6 tests pass
- Full suite ≥883 pass (current baseline) after merge
- CPK-002 + CPK-003 marked RESOLVED in `docs/design/cross_process_key_issues.md` (append status update)
- Zero new UserWarnings (no schema collisions)

## STATUS.md
Per-checkpoint milestones, current commit count, current token usage, any deviation from spec.

Begin by reading the 4 design sources, then verifying prerequisites.
