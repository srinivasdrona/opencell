"""Tests for engine, guards, sentinels, crash bundle, checkpoint."""

import json
import tempfile
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
import pytest

jax.config.update("jax_enable_x64", True)

from opencell.core.compartments import CellGeometry
from opencell.core.crash_bundle import CrashBundle, capture_crash_bundle
from opencell.core.checkpoint import save_checkpoint, load_checkpoint
from opencell.core.engine import Engine, EngineConfig
from opencell.core.guards import Guards
from opencell.core.ir import (
    Compartment,
    IRSpeciesRegistry,
    MoleculeType,
    ReferenceFrame,
    SpeciesInfo,
)
from opencell.core.manifest import RunManifest
from opencell.core.sentinels import BACTERIAL_SENTINELS, check_sentinel, check_all_sentinels
from opencell.core.state import CellState
from opencell.models.base import DummyConsumer, DummyProducer


def make_simple_registry() -> IRSpeciesRegistry:
    reg = IRSpeciesRegistry()
    reg.register(SpeciesInfo(
        id="A", name="Species A", compartment=Compartment.CYTOPLASM,
        molecule_type=MoleculeType.METABOLITE,
        reference_frame=ReferenceFrame.PER_CELL,
        molar_mass_da=100.0, atom_counts={"C": 5, "H": 10},
    ))
    reg.register(SpeciesInfo(
        id="B", name="Species B", compartment=Compartment.CYTOPLASM,
        molecule_type=MoleculeType.METABOLITE,
        reference_frame=ReferenceFrame.PER_CELL,
        molar_mass_da=100.0, atom_counts={"C": 5, "H": 10},
    ))
    return reg


class TestEngine:
    def test_producer_consumer_steady_state(self) -> None:
        """Producer + Consumer should reach approximate steady state."""
        reg = make_simple_registry()
        producer = DummyProducer("A", rate=10.0)  # produce 10/s
        consumer = DummyConsumer("A", rate_constant=0.1)  # consume 0.1*A/s

        state = CellState.initialize(reg, {"A": 0.0, "B": 0.0})
        config = EngineConfig(dt=0.1, t_end=200.0, log_interval=1000)
        engine = Engine([producer, consumer], reg, config)
        result = engine.run(state)

        assert result.success
        # Steady state: production = consumption → 10 = 0.1*A → A = 100
        final_A = result.states[-1].get_count("A")
        assert abs(final_A - 100.0) < 5.0, f"Expected ~100, got {final_A}"

    def test_conservation_with_conversion(self) -> None:
        """A→B conversion should conserve total counts."""
        reg = make_simple_registry()

        class Converter(DummyProducer):
            @property
            def id(self) -> str:
                return "converter"

            @property
            def contract(self):
                from opencell.core.ir import SubModelContract
                return SubModelContract(
                    sub_model_id=self.id,
                    reads={"A"}, writes={"A", "B"},
                    reference_frame=ReferenceFrame.PER_CELL,
                )

            def compute_derivatives(self, t, state):
                a = state.get_count("A")
                rate = 0.05 * a
                return {"A": -rate, "B": rate}

        state = CellState.initialize(reg, {"A": 100.0, "B": 0.0})
        config = EngineConfig(dt=0.1, t_end=50.0, log_interval=1000)
        engine = Engine([Converter("A", 0)], reg, config)
        result = engine.run(state)

        assert result.success
        final = result.states[-1]
        total = final.get_count("A") + final.get_count("B")
        assert abs(total - 100.0) < 0.1, f"Conservation violated: total={total}"


class TestGuards:
    def test_positivity_pass(self) -> None:
        g = Guards()
        violations = g.check_positivity({"atp": 100.0, "adp": 50.0}, step=0, time_s=0.0)
        assert len(violations) == 0

    def test_positivity_fail(self) -> None:
        g = Guards()
        violations = g.check_positivity({"atp": -5.0, "adp": 50.0}, step=1, time_s=0.1)
        assert len(violations) == 1
        assert violations[0].species_id == "atp"

    def test_fraction_bounds_pass(self) -> None:
        g = Guards()
        violations = g.check_fraction_bounds({"occupancy": 0.5}, step=0, time_s=0.0)
        assert len(violations) == 0

    def test_fraction_bounds_fail(self) -> None:
        g = Guards()
        violations = g.check_fraction_bounds({"occupancy": 1.5}, step=0, time_s=0.0)
        assert len(violations) == 1

    def test_conservation_pass(self) -> None:
        g = Guards()
        violations = g.check_conservation(100.0, 100.0, "total_mass", step=0, time_s=0.0)
        assert len(violations) == 0

    def test_conservation_fail(self) -> None:
        g = Guards()
        violations = g.check_conservation(100.0, 110.0, "total_mass", step=0, time_s=0.0)
        assert len(violations) == 1

    def test_summary(self) -> None:
        g = Guards()
        g.check_positivity({"atp": -1.0}, step=0, time_s=0.0)
        summary = g.summary()
        assert "1" in summary
        assert "atp" in summary


class TestSentinels:
    def test_in_range(self) -> None:
        assert check_sentinel("cell_volume_fL", 0.07) is None

    def test_out_of_range(self) -> None:
        warning = check_sentinel("cell_volume_fL", 1000.0)
        assert warning is not None
        assert "SENTINEL WARNING" in warning

    def test_unknown_sentinel(self) -> None:
        assert check_sentinel("unknown_variable", 42.0) is None

    def test_check_all(self) -> None:
        warnings = check_all_sentinels({
            "cell_volume_fL": 0.07,
            "atp_concentration_mM": 999.0,  # too high
        })
        assert len(warnings) == 1
        assert "ATP" in warnings[0]


class TestCrashBundle:
    def test_classify_numerical(self) -> None:
        b = CrashBundle(state_norm=float("nan"))
        assert b.classify_bug() == "numerical"

    def test_classify_biology(self) -> None:
        b = CrashBundle(
            state_norm=100.0, derivative_norm=10.0,
            violated_invariant="positivity",
            solver_stats={"rejected_steps": 0},
        )
        assert b.classify_bug() == "biology"

    def test_save_and_load(self) -> None:
        b = CrashBundle(step=42, time_s=1.5, error_message="test crash")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = b.save(tmpdir)
            assert path.exists()
            with open(path) as f:
                data = json.load(f)
            assert data["step"] == 42

    def test_capture_function(self) -> None:
        bundle = capture_crash_bundle(
            step=10, time_s=0.5, dt=0.01,
            state_array=np.array([100.0, 50.0, -1.0]),
            derivative_array=np.array([0.0, 1.0, -100.0]),
            species_ids=["A", "B", "C"],
            error_message="negative count",
            last_module="metabolism",
        )
        assert bundle.step == 10
        assert len(bundle.top_changed) > 0


class TestCheckpoint:
    def test_save_and_load_roundtrip(self) -> None:
        counts = np.array([100.0, 50.0, 25.0])
        species_ids = ["atp", "adp", "amp"]
        rng_key = np.array(jax.random.PRNGKey(42))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_checkpoint(
                Path(tmpdir) / "test.h5",
                time_s=10.5,
                counts=counts,
                species_ids=species_ids,
                rng_key_data=rng_key,
                metadata={"solver": "tsit5"},
            )
            assert path.exists()

            loaded = load_checkpoint(path)
            assert loaded["time_s"] == 10.5
            np.testing.assert_array_almost_equal(loaded["counts"], counts)
            assert loaded["species_ids"] == species_ids
            assert loaded["metadata"]["solver"] == "tsit5"


class TestManifest:
    def test_capture(self) -> None:
        m = RunManifest.capture(rng_seed=42)
        assert m.python_version != ""
        assert m.jax_version != ""
        assert m.rng_seed == 42

    def test_save(self) -> None:
        m = RunManifest.capture()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = m.save(tmpdir)
            assert path.exists()
            with open(path) as f:
                data = json.load(f)
            assert "jax_version" in data
