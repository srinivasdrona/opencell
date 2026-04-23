"""Gate G1.4: Atom balance across module boundaries.

Runs the producer+consumer coupling benchmark and verifies that total atom
counts (C, H, O) are conserved within numerical tolerance across the entire
simulation. This is the infrastructure test for mass-balance auditing that
will matter once we have real biochemistry (Chassagnole 2002 onward).

In the current benchmark, A and B share the same atomic composition
(C5H10O2), so the total atom count should be conserved to machine precision
because each A consumed produces exactly one B.
"""

from __future__ import annotations

import pytest

from benchmarks.bench_coupling import (
    Consumer,
    Producer,
    build_benchmark_registry,
)
from opencell.core.engine import Engine, EngineConfig
from opencell.core.state import CellState


@pytest.mark.gate
class TestGateG14AtomBalance:
    """G1.4: Atom counts must balance across the producer→consumer pipeline."""

    def test_total_atoms_tracked_per_species(self) -> None:
        """The registry+state machinery can enumerate per-element atom totals."""
        reg = build_benchmark_registry()
        state = CellState.initialize(reg, {"A": 10.0, "B": 5.0})

        atoms = state.total_atoms()
        # 10 A (5C,10H,2O) + 5 B (5C,10H,2O) = 15×(5C,10H,2O)
        assert atoms["C"] == pytest.approx(15 * 5)
        assert atoms["H"] == pytest.approx(15 * 10)
        assert atoms["O"] == pytest.approx(15 * 2)

    def test_atom_conservation_in_closed_reaction(self) -> None:
        """When A → B with matched stoichiometry, atoms are conserved.

        Disables the producer (rate=0) so the system is closed and atom
        totals cannot change.
        """
        reg = build_benchmark_registry()
        producer = Producer(rate=0.0)       # closed system
        consumer = Consumer(rate_constant=0.1)

        state = CellState.initialize(reg, {"A": 100.0, "B": 0.0})
        initial_atoms = dict(state.total_atoms())

        config = EngineConfig(dt=0.1, t_end=50.0, log_interval=10000)
        engine = Engine([producer, consumer], reg, config)
        result = engine.run(state)

        final = result.states[-1]
        final_atoms = final.total_atoms()

        for element in ("C", "H", "O"):
            assert final_atoms[element] == pytest.approx(
                initial_atoms[element], rel=1e-6
            ), (
                f"Atom {element} not conserved: "
                f"initial={initial_atoms[element]}, final={final_atoms[element]}"
            )

    def test_open_system_atom_balance_matches_influx(self) -> None:
        """In an open system, d(total_atoms)/dt = atom-influx from producer.

        Producer adds A at rate R → atom influx = R × atom_count(A).
        After t_end, total_atoms should equal
        initial + R · t_end · atom_count(A) within integration error.
        """
        reg = build_benchmark_registry()
        prod_rate = 10.0
        t_end = 50.0
        producer = Producer(rate=prod_rate)
        consumer = Consumer(rate_constant=0.1)

        state = CellState.initialize(reg, {"A": 0.0, "B": 0.0})
        initial_atoms = dict(state.total_atoms())

        config = EngineConfig(dt=0.1, t_end=t_end, log_interval=10000)
        engine = Engine([producer, consumer], reg, config)
        result = engine.run(state)
        final_atoms = result.states[-1].total_atoms()

        a_info = reg.get("A")
        for element, n_per_A in a_info.atom_counts.items():
            expected_delta = prod_rate * t_end * n_per_A
            observed_delta = final_atoms[element] - initial_atoms[element]
            assert observed_delta == pytest.approx(expected_delta, rel=1e-3), (
                f"Atom {element}: expected influx {expected_delta}, "
                f"got delta {observed_delta}"
            )
