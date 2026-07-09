"""Tests for core/ir.py — Internal Runtime Representation."""

import pytest

from opencell.core.ir import (
    Compartment,
    IRSpeciesRegistry,
    MoleculeType,
    ReactionInfo,
    ReferenceFrame,
    SpeciesInfo,
    StoichiometryMatrix,
    SubModelContract,
    validate_contracts,
)


def make_atp() -> SpeciesInfo:
    return SpeciesInfo(
        id="atp_c",
        name="ATP",
        compartment=Compartment.CYTOPLASM,
        molecule_type=MoleculeType.METABOLITE,
        reference_frame=ReferenceFrame.PER_CELL,
        molar_mass_da=507.18,
        atom_counts={"C": 10, "H": 16, "N": 5, "O": 13, "P": 3},
        is_shared=True,
    )


def make_adp() -> SpeciesInfo:
    return SpeciesInfo(
        id="adp_c",
        name="ADP",
        compartment=Compartment.CYTOPLASM,
        molecule_type=MoleculeType.METABOLITE,
        reference_frame=ReferenceFrame.PER_CELL,
        molar_mass_da=427.20,
        atom_counts={"C": 10, "H": 15, "N": 5, "O": 10, "P": 2},
    )


class TestIRSpeciesRegistry:
    def test_register_and_lookup(self) -> None:
        reg = IRSpeciesRegistry()
        atp = make_atp()
        idx = reg.register(atp)
        assert idx == 0
        assert reg.get("atp_c") is atp
        assert reg.index("atp_c") == 0
        assert reg.id_at(0) == "atp_c"
        assert reg.size == 1

    def test_duplicate_registration_raises(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(make_atp())

    def test_freeze_prevents_registration(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        reg.freeze()
        with pytest.raises(RuntimeError, match="frozen"):
            reg.register(make_adp())

    def test_ids_in_order(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        reg.register(make_adp())
        assert reg.ids == ["atp_c", "adp_c"]

    def test_shared_species(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())  # is_shared=True
        reg.register(make_adp())  # is_shared=False
        assert reg.shared_species() == ["atp_c"]

    def test_species_by_compartment(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        reg.register(
            SpeciesInfo(
                id="glc_e",
                name="Glucose (ext)",
                compartment=Compartment.EXTRACELLULAR,
                molecule_type=MoleculeType.METABOLITE,
                reference_frame=ReferenceFrame.PER_VOLUME,
            )
        )
        assert reg.species_by_compartment(Compartment.CYTOPLASM) == ["atp_c"]
        assert reg.species_by_compartment(Compartment.EXTRACELLULAR) == ["glc_e"]

    def test_species_by_type(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        reg.register(
            SpeciesInfo(
                id="gene1_mrna",
                name="Gene 1 mRNA",
                compartment=Compartment.CYTOPLASM,
                molecule_type=MoleculeType.MRNA,
                reference_frame=ReferenceFrame.PER_CELL,
            )
        )
        assert reg.species_by_type(MoleculeType.METABOLITE) == ["atp_c"]
        assert reg.species_by_type(MoleculeType.MRNA) == ["gene1_mrna"]


class TestStoichiometryMatrix:
    def test_from_reactions(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        reg.register(make_adp())

        rxn = ReactionInfo(
            id="atp_hydrolysis",
            name="ATP hydrolysis",
            stoichiometry={"atp_c": -1, "adp_c": 1},
        )
        S = StoichiometryMatrix.from_reactions([rxn], reg)
        assert S.n_species == 2
        assert S.n_reactions == 1
        assert S.matrix[0, 0] == -1  # ATP consumed
        assert S.matrix[1, 0] == 1  # ADP produced

    def test_mass_balance_check(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        reg.register(make_adp())

        rxn = ReactionInfo(
            id="atp_hydrolysis",
            name="ATP hydrolysis",
            stoichiometry={"atp_c": -1, "adp_c": 1},
        )
        S = StoichiometryMatrix.from_reactions([rxn], reg)
        residuals = S.mass_balance_check(reg)
        # ATP→ADP: mass difference = 427.20 - 507.18 = -79.98 (Pi + H2O missing)
        assert residuals["atp_hydrolysis"] != 0  # unbalanced without Pi + H2O

    def test_dense_array(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        rxn = ReactionInfo(id="r1", name="r1", stoichiometry={"atp_c": -1})
        S = StoichiometryMatrix.from_reactions([rxn], reg)
        arr = S.as_dense_array
        assert arr.shape == (1, 1)


class TestSubModelContract:
    def test_validate_missing_species(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())
        contract = SubModelContract(
            sub_model_id="metabolism",
            reads={"atp_c", "nonexistent"},
            writes={"atp_c"},
        )
        errors = contract.validate_against_registry(reg)
        assert any("nonexistent" in e for e in errors)

    def test_validate_frame_mismatch(self) -> None:
        reg = IRSpeciesRegistry()
        reg.register(make_atp())  # PER_CELL
        contract = SubModelContract(
            sub_model_id="metabolism",
            reads={"atp_c"},
            reference_frame=ReferenceFrame.PER_GRAM_DRY_WEIGHT,
        )
        errors = contract.validate_against_registry(reg)
        assert any("conversion required" in e.lower() for e in errors)

    def test_validate_contracts_multiple_writers(self) -> None:
        c1 = SubModelContract(sub_model_id="metabolism", writes={"atp_c"})
        c2 = SubModelContract(sub_model_id="translation", writes={"atp_c"})
        errors = validate_contracts([c1, c2])
        assert any("atp_c" in e for e in errors)
