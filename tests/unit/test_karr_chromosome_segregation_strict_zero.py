from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from opencell.vivarium.karr_chromosome_segregation import KarrChromosomeSegregationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: Iterable[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def _assert_zero_or_absent_substrate_delta(update: dict[str, Any], wids: Iterable[str]) -> None:
    substrate_delta = update.get("substrates", {})
    for wid in wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12


def test_karr_chromosome_segregation_strict_zero_no_global_fallback() -> None:
    """The process must gate GTP/H2O availability purely from
    `substrates_allocated`, never falling back to a global `state["substrates"]`
    read (Karr's per-process `this.substrates` is already the allocated
    partition; there is no global-pool read in ChromosomeSegregation.m).

    Uses a guarded global `substrates` mapping that raises if GTP or H2O is
    read. This proves the process gates availability from
    `substrates_allocated`, while retaining the full state shape expected by
    the chassis.
    """
    process = KarrChromosomeSegregationProcess({})
    blocked_wids = [process.gtp_wid, process.h2o_wid]

    substrate_values = {wid: 0.0 for wid in process.substrate_wids}
    substrate_values[process.gtp_wid] = 10_000.0
    substrate_values[process.h2o_wid] = 10_000.0
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    protein_counts = {wid: 10.0 for wid in process.monomer_enzyme_wids}
    complex_counts = {wid: 10.0 for wid in process.complex_enzyme_wids}

    length = process.sequence_len
    polymerized = {
        "positions": [0, 0, 0, 0],
        "strands": [0, 1, 2, 3],
        "values": [length, length, length, length],
        "shape": process.chromosome_shape,
    }
    linking = {
        "positions": [0, 0, 0, 0],
        "strands": [0, 1, 2, 3],
        "values": [52013, 52013, 52026, 52026],
        "shape": process.chromosome_shape,
    }

    state = {
        "chromosome": {
            "segregated": False,
            "polymerizedRegions": polymerized,
            "linkingNumbers": linking,
        },
        "protein": {"counts": protein_counts},
        "complex": {"counts": complex_counts},
        # Guarded global pool: reading GTP/H2O here fails the test.
        "substrates": guarded_substrates,
        # Allocated amount below gtpCost: the process must gate on THIS, not
        # on the (much larger) guarded global pool above.
        "substrates_allocated": {process.name: {process.gtp_wid: 0.0, process.h2o_wid: 0.0}},
    }

    update = process.next_update(1.0, state)

    assert "segregated" not in update.get("chromosome", {})
    _assert_zero_or_absent_substrate_delta(update, blocked_wids)
