# Biology Firing Canary Status

## Pytest command

`python -m pytest tests/integration/test_chassis_v6_biology_firing.py -v`

## Captured pytest output

```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0 -- /mnt/e/opencell/.venv-wsl/bin/python
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: /mnt/e/opencell-worktrees/biology-firing-test
configfile: pyproject.toml
plugins: anyio-4.13.0, hypothesis-6.152.1, jaxtyping-0.3.9, cov-7.1.0
collecting ... collected 7 items

tests/integration/test_chassis_v6_biology_firing.py::test_a1_central_dogma_transcription_generates_new_mrna FAILED [ 14%]
tests/integration/test_chassis_v6_biology_firing.py::test_a2_central_dogma_translation_increases_output_pool FAILED [ 28%]
tests/integration/test_chassis_v6_biology_firing.py::test_a3_central_dogma_dnaa_expression_occurs FAILED [ 42%]
tests/integration/test_chassis_v6_biology_firing.py::test_b1_substrate_sanity_no_negative_core_substrates FAILED [ 57%]
tests/integration/test_chassis_v6_biology_firing.py::test_b2_substrate_sanity_core_initialization_not_all_unit_values FAILED [ 71%]
tests/integration/test_chassis_v6_biology_firing.py::test_c1_metabolism_dynamic_response_atp_delta_not_constant FAILED [ 85%]
tests/integration/test_chassis_v6_biology_firing.py::test_d1_replication_gate_dnaa_binds_oric_sites_r1_to_r5 XFAIL [100%]

=================================== FAILURES ===================================
____________ test_a1_central_dogma_transcription_generates_new_mrna ____________

biology_run = BiologyRun(engine=<vivarium.core.engine.Engine object at 0x7263f33f7980>, initial_state={'karr_metabolism': (<opencell...427_DIMER_ox': 1.0, 'MG_454_DIMER': 1.0, 'MG_454_DIMER_ox': 1.0}, 'cell_dry_mass_reference_g': 3.944640855678535e-15}})

    def test_a1_central_dogma_transcription_generates_new_mrna(biology_run: BiologyRun) -> None:
        """A1: catches non-firing transcription that only decays/reshuffles pre-seeded RNA pools."""
        initial_counts = biology_run.initial_state["rna"]["counts"]
        final_counts = biology_run.final_state["rna"]["counts"]

        newly_expressed = [
            rna_id
            for rna_id, initial_value in initial_counts.items()
            if float(initial_value) <= 0.0 and float(final_counts.get(rna_id, 0.0)) > 0.0
        ]
        final_positive_total = sum(1 for value in final_counts.values() if float(value) > 0.0)

>       assert newly_expressed, (
            "A1 central dogma check failed: no previously absent mRNA species became >0 "
            f"by t={SIM_DURATION_S:.0f}s; newly_expressed={len(newly_expressed)}, "
            f"final_positive_total={final_positive_total}."
        )
E       AssertionError: A1 central dogma check failed: no previously absent mRNA species became >0 by t=5000s; newly_expressed=0, final_positive_total=129.
E       assert []

tests/integration/test_chassis_v6_biology_firing.py:128: AssertionError
---------------------------- Captured stdout setup -----------------------------

Simulation ID: 45ff9698-5723-11f1-b8b4-00155d5d4819
Created: 05/24/2026 at 09:17:23
___________ test_a2_central_dogma_translation_increases_output_pool ____________

biology_run = BiologyRun(engine=<vivarium.core.engine.Engine object at 0x7263f33f7980>, initial_state={'karr_metabolism': (<opencell...427_DIMER_ox': 1.0, 'MG_454_DIMER': 1.0, 'MG_454_DIMER_ox': 1.0}, 'cell_dry_mass_reference_g': 3.944640855678535e-15}})

    def test_a2_central_dogma_translation_increases_output_pool(biology_run: BiologyRun) -> None:
        """A2: catches non-firing translation by requiring growth in `protein.unprocessed_counts`."""
        initial_protein = biology_run.initial_state["protein"]
        final_protein = biology_run.final_state["protein"]

        output_pool_increased = [
            protein_id
            for protein_id, initial_value in initial_protein["unprocessed_counts"].items()
            if float(final_protein["unprocessed_counts"].get(protein_id, 0.0)) > float(initial_value)
        ]
        mature_pool_increased = [
            protein_id
            for protein_id, initial_value in initial_protein["counts"].items()
            if float(final_protein["counts"].get(protein_id, 0.0)) > float(initial_value)
        ]

>       assert output_pool_increased, (
            "A2 central dogma check failed: translation output pool `protein.unprocessed_counts` "
            "never increased (no direct evidence of new protein synthesis). "
            f"output_pool_increased={len(output_pool_increased)}, "
            f"mature_pool_increased={len(mature_pool_increased)}."
        )
E       AssertionError: A2 central dogma check failed: translation output pool `protein.unprocessed_counts` never increased (no direct evidence of new protein synthesis). output_pool_increased=0, mature_pool_increased=209.
E       assert []

tests/integration/test_chassis_v6_biology_firing.py:151: AssertionError
_________________ test_a3_central_dogma_dnaa_expression_occurs _________________

biology_run = BiologyRun(engine=<vivarium.core.engine.Engine object at 0x7263f33f7980>, initial_state={'karr_metabolism': (<opencell...427_DIMER_ox': 1.0, 'MG_454_DIMER': 1.0, 'MG_454_DIMER_ox': 1.0}, 'cell_dry_mass_reference_g': 3.944640855678535e-15}})

    def test_a3_central_dogma_dnaa_expression_occurs(biology_run: BiologyRun) -> None:
        """A3: catches silent replication-gate expression (`MG_469` / `MG_469_MONOMER` stays zero)."""
        series = _timeseries(biology_run.engine)
        max_dnaa_rna = float(np.max(series["dnaa_rna"]))
        max_dnaa_protein = float(np.max(series["dnaa_protein"]))

>       assert max_dnaa_rna > 0.0 or max_dnaa_protein > 0.0, (
            "A3 central dogma check failed: DnaA expression never appeared over 5,000s; "
            f"max_{DNAA_RNA_KEY}={max_dnaa_rna:.6g}, "
            f"max_{DNAA_PROTEIN_KEY}={max_dnaa_protein:.6g}."
        )
E       AssertionError: A3 central dogma check failed: DnaA expression never appeared over 5,000s; max_MG_469=0, max_MG_469_MONOMER=0.
E       assert (0.0 > 0.0 or 0.0 > 0.0)

tests/integration/test_chassis_v6_biology_firing.py:165: AssertionError
_____________ test_b1_substrate_sanity_no_negative_core_substrates _____________

biology_run = BiologyRun(engine=<vivarium.core.engine.Engine object at 0x7263f33f7980>, initial_state={'karr_metabolism': (<opencell...427_DIMER_ox': 1.0, 'MG_454_DIMER': 1.0, 'MG_454_DIMER_ox': 1.0}, 'cell_dry_mass_reference_g': 3.944640855678535e-15}})

    def test_b1_substrate_sanity_no_negative_core_substrates(biology_run: BiologyRun) -> None:
        """B1: catches accumulate+default drain bugs that drive key metabolites below zero."""
        final_substrates = biology_run.final_state["substrates"]
        core_values = {sid: float(final_substrates.get(sid, np.nan)) for sid in CORE_SUBSTRATES}
        negative = {sid: value for sid, value in core_values.items() if value < 0.0}

>       assert not negative, (
            "B1 substrate sanity check failed: core substrates dropped below zero; "
            f"values={core_values}."
        )
E       AssertionError: B1 substrate sanity check failed: core substrates dropped below zero; values={'AD': -4999999.0, 'URA': -4999999.0, 'ATP': 6987337.408536464, 'GTP': 2591275.4200909915, 'H2O': 19429944.291690964}.
E       assert not {'AD': -4999999.0, 'URA': -4999999.0}

tests/integration/test_chassis_v6_biology_firing.py:178: AssertionError
_______ test_b2_substrate_sanity_core_initialization_not_all_unit_values _______

biology_run = BiologyRun(engine=<vivarium.core.engine.Engine object at 0x7263f33f7980>, initial_state={'karr_metabolism': (<opencell...427_DIMER_ox': 1.0, 'MG_454_DIMER': 1.0, 'MG_454_DIMER_ox': 1.0}, 'cell_dry_mass_reference_g': 3.944640855678535e-15}})

    def test_b2_substrate_sanity_core_initialization_not_all_unit_values(
        biology_run: BiologyRun,
    ) -> None:
        """B2: catches `_default: 1.0` initialization of biologically central substrates."""
        initial_substrates = biology_run.initial_state["substrates"]
        core_initial = {sid: float(initial_substrates.get(sid, np.nan)) for sid in CORE_SUBSTRATES}
        max_core_initial = max(core_initial.values())

>       assert max_core_initial > 100.0, (
            "B2 substrate sanity check failed: no core substrate started above 100 at t=0; "
            f"core_initial={core_initial}."
        )
E       AssertionError: B2 substrate sanity check failed: no core substrate started above 100 at t=0; core_initial={'AD': 1.0, 'URA': 1.0, 'ATP': 1.0, 'GTP': 1.0, 'H2O': 1.0}.
E       assert 1.0 > 100.0

tests/integration/test_chassis_v6_biology_firing.py:192: AssertionError
__________ test_c1_metabolism_dynamic_response_atp_delta_not_constant __________

biology_run = BiologyRun(engine=<vivarium.core.engine.Engine object at 0x7263f33f7980>, initial_state={'karr_metabolism': (<opencell...427_DIMER_ox': 1.0, 'MG_454_DIMER': 1.0, 'MG_454_DIMER_ox': 1.0}, 'cell_dry_mass_reference_g': 3.944640855678535e-15}})

    def test_c1_metabolism_dynamic_response_atp_delta_not_constant(biology_run: BiologyRun) -> None:
        """C1: catches static-flux metabolism by requiring non-constant ATP deltas after warm-up."""
        atp = _timeseries(biology_run.engine)["atp"]
        assert atp.size > ATP_BURN_IN_TICKS + 2, (
            "C1 setup failed: ATP timeseries too short to evaluate dynamic response; "
            f"len={atp.size}."
        )

        delta = np.diff(atp[ATP_BURN_IN_TICKS:])
        delta_std = float(np.std(delta))

>       assert delta_std > ATP_DYNAMIC_STD_MIN, (
            "C1 metabolism dynamic-response check failed: ATP delta-per-tick remained effectively "
            "constant after warm-up; "
            f"std={delta_std:.12g}, burn_in_ticks={ATP_BURN_IN_TICKS}, "
            f"first_delta={float(delta[0]):.12g}, last_delta={float(delta[-1]):.12g}."
        )
E       AssertionError: C1 metabolism dynamic-response check failed: ATP delta-per-tick remained effectively constant after warm-up; std=2.17660185445e-10, burn_in_ticks=10, first_delta=1397.48428171, last_delta=1397.48428171.
E       assert 2.1766018544475552e-10 > 1e-06

tests/integration/test_chassis_v6_biology_firing.py:209: AssertionError
=========================== short test summary info ============================
FAILED tests/integration/test_chassis_v6_biology_firing.py::test_a1_central_dogma_transcription_generates_new_mrna
FAILED tests/integration/test_chassis_v6_biology_firing.py::test_a2_central_dogma_translation_increases_output_pool
FAILED tests/integration/test_chassis_v6_biology_firing.py::test_a3_central_dogma_dnaa_expression_occurs
FAILED tests/integration/test_chassis_v6_biology_firing.py::test_b1_substrate_sanity_no_negative_core_substrates
FAILED tests/integration/test_chassis_v6_biology_firing.py::test_b2_substrate_sanity_core_initialization_not_all_unit_values
FAILED tests/integration/test_chassis_v6_biology_firing.py::test_c1_metabolism_dynamic_response_atp_delta_not_constant
=================== 6 failed, 1 xfailed in 210.35s (0:03:30) ===================
Command exited with non-zero status 1
WALL=3:40.78
```

## Per-assertion result (with observed value)

- `A1` (`test_a1_central_dogma_transcription_generates_new_mrna`): **FAILED**
  - Observed: `newly_expressed=0`, `final_positive_total=129`.
- `A2` (`test_a2_central_dogma_translation_increases_output_pool`): **FAILED**
  - Observed: `output_pool_increased=0`, `mature_pool_increased=209`.
- `A3` (`test_a3_central_dogma_dnaa_expression_occurs`): **FAILED**
  - Observed: `max_MG_469=0`, `max_MG_469_MONOMER=0`.
- `B1` (`test_b1_substrate_sanity_no_negative_core_substrates`): **FAILED**
  - Observed core values: `AD=-4999999.0`, `URA=-4999999.0`, `ATP=6987337.408536464`, `GTP=2591275.4200909915`, `H2O=19429944.291690964`.
- `B2` (`test_b2_substrate_sanity_core_initialization_not_all_unit_values`): **FAILED**
  - Observed core initial: `AD=1.0`, `URA=1.0`, `ATP=1.0`, `GTP=1.0`, `H2O=1.0`.
- `C1` (`test_c1_metabolism_dynamic_response_atp_delta_not_constant`): **FAILED**
  - Observed: `std=2.17660185445e-10`, `burn_in_ticks=10`, `first_delta=1397.48428171`, `last_delta=1397.48428171`.
- `D1` (`test_d1_replication_gate_dnaa_binds_oric_sites_r1_to_r5`): **XFAIL**
  - Marked with `strict=False` and reason: `Requires DnaA expression + activation; tracked separately`.

## Runtime

- Pytest reported runtime: `210.35s (0:03:30)`
- Measured wall-clock: `3:40.78`

## Summary

Test is a valid biology canary - **6/6 assertions fail** on current chassis_v6 (plus D1 xfail).
