"""Tests for `opencell.m1.protein_complexes` (Phase D.0).

Spot-checks on well-known M. genitalium complexes against Karr's KB:
* DNA gyrase: A2B2 tetramer (MG_003 + MG_004)
* RNA polymerase: 5-subunit core (alpha2, beta, beta', omega -> MG_022,
  MG_177x2, MG_340, MG_341)
* Ribosome: 30S = 20 proteins + 1 rRNA, 50S = 32 proteins + 2 rRNAs,
  70S = 30S + 50S sub-complex
"""

from __future__ import annotations

import pytest

from opencell.m1.protein_complexes import (
    ComplexCompositionModel,
    load_default,
)


@pytest.fixture(scope="module")
def model() -> ComplexCompositionModel:
    return load_default()


# -------- shape / coverage --------


def test_loads_201_complexes(model) -> None:
    assert len(model.all_wids()) == 201
    assert model.counts["n_complexes"] == 201


def test_compartment_vocab_has_six_wids(model) -> None:
    assert set(model.compartment_wids) == {"c", "d", "e", "m", "tc", "tm"}


def test_every_complex_has_at_least_one_participant(model) -> None:
    """A protein complex must assemble from something."""
    bare = []
    for wid, c in model.complexes.items():
        n_parts = (
            len(c.monomers)
            + len(c.subcomplexes)
            + len(c.metabolites)
            + len(c.prosthetic)
            + len(c.chaperones)
            + len(c.rnas)
        )
        if n_parts == 0:
            bare.append(wid)
    assert not bare, f"complexes with no participants: {bare}"


# -------- DNA gyrase --------


def test_dna_gyrase_a2b2(model) -> None:
    c = model["DNA_GYRASE"]
    mons = {p.molecule_wid: p.coefficient for p in c.monomers}
    assert mons == {"MG_003_MONOMER": 2.0, "MG_004_MONOMER": 2.0}
    assert c.subcomplexes == []
    for p in c.monomers:
        assert p.compartment_wid == "c"


def test_dna_gyrase_flatten_to_monomers(model) -> None:
    out = model.flatten_to_monomers("DNA_GYRASE", copies=3)
    assert out == {"MG_003_MONOMER": 6.0, "MG_004_MONOMER": 6.0}


# -------- RNA polymerase --------


def test_rna_polymerase_4_distinct_subunits(model) -> None:
    c = model["RNA_POLYMERASE"]
    mons = {p.molecule_wid: p.coefficient for p in c.monomers}
    # alpha2 -> MG_177 x 2; beta -> MG_340; beta' -> MG_341; omega -> MG_022
    assert mons == {
        "MG_022_MONOMER": 1.0,
        "MG_177_MONOMER": 2.0,
        "MG_340_MONOMER": 1.0,
        "MG_341_MONOMER": 1.0,
    }
    assert c.num_distinct_subunits >= 4
    assert sum(p.coefficient for p in c.monomers) == 5  # 5-subunit core


# -------- Ribosomes (sub-complex hierarchy) --------


def test_ribosome_30s_has_20_proteins_and_1_rrna(model) -> None:
    c = model["RIBOSOME_30S"]
    assert len(c.monomers) == 20
    assert sum(p.coefficient for p in c.monomers) == 20  # one copy each
    assert len(c.rnas) == 1
    assert c.rnas[0].coefficient == 1


def test_ribosome_50s_has_32_proteins_and_2_rrnas(model) -> None:
    c = model["RIBOSOME_50S"]
    assert len(c.monomers) == 32
    assert len(c.rnas) == 2


def test_ribosome_70s_is_30s_plus_50s(model) -> None:
    c = model["RIBOSOME_70S"]
    subs = {p.molecule_wid: p.coefficient for p in c.subcomplexes}
    assert subs == {"RIBOSOME_30S": 1.0, "RIBOSOME_50S": 1.0}
    assert c.monomers == []


def test_ribosome_70s_flatten_to_monomers_aggregates(model) -> None:
    out = model.flatten_to_monomers("RIBOSOME_70S")
    # 30S contributes 20 distinct monomers, 50S contributes 32; some
    # may overlap, but total should be 52 monomer-copies.
    assert sum(out.values()) == 52
    # Spot-check a 30S protein and a 50S protein are present.
    assert "MG_070_MONOMER" in out  # 30S
    assert "MG_473_MONOMER" in out  # 50S


def test_ribosome_70s_flatten_full_includes_rrnas(model) -> None:
    full = model.flatten_full("RIBOSOME_70S")
    assert sum(full["monomers"].values()) == 52
    # 30S has 1 rRNA, 50S has 2 -> total 3 rRNA copies in the 70S.
    assert sum(full["rnas"].values()) == 3


# -------- multi-copy demand aggregation --------


def test_monomers_required_multiplies_demand(model) -> None:
    demand = {"DNA_GYRASE": 2.0, "RNA_POLYMERASE": 3.0}
    out = model.monomers_required(demand)
    assert out["MG_003_MONOMER"] == 4.0  # 2 * 2
    assert out["MG_004_MONOMER"] == 4.0
    assert out["MG_177_MONOMER"] == 6.0  # 3 * 2
    assert out["MG_022_MONOMER"] == 3.0


# -------- API / safety --------


def test_unknown_complex_raises_keyerror(model) -> None:
    with pytest.raises(KeyError):
        model.flatten_to_monomers("NOT_A_REAL_COMPLEX")


def test_get_returns_none_for_unknown(model) -> None:
    assert model.get("NOT_A_REAL_COMPLEX") is None


def test_contains_works(model) -> None:
    assert "DNA_GYRASE" in model
    assert "NOPE" not in model


def test_formation_compartment_for_known_complexes(model) -> None:
    assert model.formation_compartment("DNA_GYRASE") == "c"
    assert model.formation_compartment("RNA_POLYMERASE") == "c"


def test_participant_is_immutable(model) -> None:
    p = model["DNA_GYRASE"].monomers[0]
    with pytest.raises(Exception):
        p.coefficient = 999  # frozen dataclass


# -------- coverage spot-checks --------


def test_some_complexes_have_metabolites(model) -> None:
    """E.g., enzyme-cofactor complexes carry an ADP/ATP/Mg metabolite."""
    n_with_mets = sum(1 for c in model.complexes.values() if c.metabolites)
    assert n_with_mets > 5, f"only {n_with_mets} complexes carry metabolites"


def test_some_complexes_have_subcomplexes(model) -> None:
    n_with_subs = sum(1 for c in model.complexes.values() if c.subcomplexes)
    assert n_with_subs > 5, f"only {n_with_subs} complexes nest subcomplexes"


def test_complex_unique_wids(model) -> None:
    wids = model.all_wids()
    assert len(wids) == len(set(wids))
