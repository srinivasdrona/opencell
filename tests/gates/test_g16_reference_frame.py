"""Gate G1.6: reference-frame consistency enforced by CI.

Every SubModel declares a reference_frame (PER_CELL, PER_VOLUME, or
PER_GRAM_DRY_WEIGHT) in its contract. Every SpeciesInfo also declares
one. The engine MUST reject any sub-model that reads or writes a species
whose reference_frame does not match the sub-model's declared frame,
unless an explicit conversion is performed via
`opencell.core.units.convert_reference_frame`.

This gate verifies:
1. The validation hook (`SubModelContract.validate_against_registry`)
   flags cross-frame reads.
2. The benchmark's existing sub-models are frame-consistent.
3. `convert_reference_frame` provides the only sanctioned escape hatch,
   and it round-trips.
"""

from __future__ import annotations

import pytest

from benchmarks.bench_coupling import (
    Consumer,
    Producer,
    build_benchmark_registry,
)
from opencell.core.ir import (
    Compartment,
    IRSpeciesRegistry,
    MoleculeType,
    ReferenceFrame,
    SpeciesInfo,
    SubModelContract,
)
from opencell.core.units import Q_, convert_reference_frame


@pytest.mark.gate
class TestGateG16ReferenceFrame:
    """G1.6: cross-frame reads must be detected; only explicit conversion allowed."""

    def test_benchmark_submodels_are_frame_consistent(self) -> None:
        """Producer + Consumer contracts must validate cleanly against the registry."""
        reg = build_benchmark_registry()
        producer = Producer()
        consumer = Consumer()
        assert producer.contract.validate_against_registry(reg) == []
        assert consumer.contract.validate_against_registry(reg) == []

    def test_frame_mismatch_is_detected(self) -> None:
        """A sub-model declaring PER_VOLUME reading a PER_CELL species
        must produce a validation error."""
        reg = build_benchmark_registry()   # A and B are PER_CELL

        bad_contract = SubModelContract(
            sub_model_id="bad_consumer",
            reads={"A"},
            writes={"B"},
            reference_frame=ReferenceFrame.PER_VOLUME,   # mismatch
        )
        errors = bad_contract.validate_against_registry(reg)
        assert errors, "Expected frame mismatch error, got none"
        assert any("PER_CELL" in e and "PER_VOLUME" in e for e in errors), (
            f"Error messages don't mention both frames: {errors}"
        )

    def test_mixed_registry_catches_per_species_mismatch(self) -> None:
        """A sub-model must match the frame of EVERY species it touches.

        Build a registry where A is PER_CELL but B is PER_VOLUME;
        a sub-model declaring either frame should fail.
        """
        reg = IRSpeciesRegistry()
        reg.register(SpeciesInfo(
            id="A", name="A", compartment=Compartment.CYTOPLASM,
            molecule_type=MoleculeType.METABOLITE,
            reference_frame=ReferenceFrame.PER_CELL,
        ))
        reg.register(SpeciesInfo(
            id="B", name="B", compartment=Compartment.CYTOPLASM,
            molecule_type=MoleculeType.METABOLITE,
            reference_frame=ReferenceFrame.PER_VOLUME,
        ))
        contract = SubModelContract(
            sub_model_id="mixed",
            reads={"A"},
            writes={"B"},
            reference_frame=ReferenceFrame.PER_CELL,
        )
        errors = contract.validate_against_registry(reg)
        assert errors, "Expected at least one frame mismatch"

    def test_convert_reference_frame_round_trip_per_volume(self) -> None:
        """PER_CELL → PER_VOLUME → PER_CELL is the identity (within fp)."""
        count = Q_(1000.0, "dimensionless")
        vol_L = 1e-15   # 1 fL
        dry_g = 1e-12
        per_vol = convert_reference_frame(count, "per_cell", "per_volume",
                                          cell_volume_L=vol_L, dry_weight_g=dry_g)
        round_trip = convert_reference_frame(per_vol, "per_volume", "per_cell",
                                              cell_volume_L=vol_L, dry_weight_g=dry_g)
        assert round_trip.magnitude == pytest.approx(count.magnitude, rel=1e-12)

    def test_convert_reference_frame_round_trip_per_gdw(self) -> None:
        """PER_CELL → PER_GRAM_DRY_WEIGHT → PER_CELL is identity."""
        count = Q_(500.0, "dimensionless")
        vol_L = 1e-15
        dry_g = 1e-12
        per_gdw = convert_reference_frame(count, "per_cell", "per_gDW",
                                           cell_volume_L=vol_L, dry_weight_g=dry_g)
        round_trip = convert_reference_frame(per_gdw, "per_gDW", "per_cell",
                                              cell_volume_L=vol_L, dry_weight_g=dry_g)
        assert round_trip.magnitude == pytest.approx(count.magnitude, rel=1e-12)

    def test_unknown_frame_raises(self) -> None:
        """An unrecognized frame label must fail loudly, not silently."""
        with pytest.raises(ValueError):
            convert_reference_frame(Q_(1.0, "dimensionless"),
                                     "per_cell", "per_phlogiston",
                                     cell_volume_L=1e-15, dry_weight_g=1e-12)
