from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet

_SHAPE = (1000, 4)
_GYRASE_GLOBAL_IDX = 1
_TOPOIV_GLOBAL_IDX = 78
_DNAA_ADP_GLOBAL_IDX = 180
_DNAA_ATP_GLOBAL_IDX = 181


def _binding_tables() -> dict[str, np.ndarray]:
    monomer_footprints = np.zeros(482, dtype=np.int64)
    monomer_binding = np.full(482, 2, dtype=np.int64)
    complex_footprints = np.zeros(201, dtype=np.int64)
    complex_footprints[_GYRASE_GLOBAL_IDX - 1] = 100
    complex_footprints[_TOPOIV_GLOBAL_IDX - 1] = 100
    complex_footprints[_DNAA_ADP_GLOBAL_IDX - 1] = 60
    complex_footprints[_DNAA_ATP_GLOBAL_IDX - 1] = 60
    complex_binding = np.full(201, 2, dtype=np.int64)
    return {
        "monomer_footprints": monomer_footprints,
        "complex_footprints": complex_footprints,
        "monomer_binding_strandedness": monomer_binding,
        "complex_binding_strandedness": complex_binding,
    }


def _store_with_complex_sites(
    entries: list[tuple[int, int, int]],
) -> ChromosomeStore:
    store = ChromosomeStore(shape=_SHAPE)
    store.set_field(
        "complexBoundSites",
        SparseTriplet(
            positions=np.asarray([entry[0] for entry in entries], dtype=np.int64),
            strands=np.asarray([entry[1] for entry in entries], dtype=np.int64),
            values=np.asarray([entry[2] for entry in entries], dtype=np.int64),
            shape=_SHAPE,
        ),
    )
    return store


def test_set_site_protein_bound_releases_overlapping_external_complex() -> None:
    store = _store_with_complex_sites(
        [
            (100, 0, _DNAA_ADP_GLOBAL_IDX),
            (260, 0, _DNAA_ADP_GLOBAL_IDX),
            (400, 2, _DNAA_ADP_GLOBAL_IDX),
        ]
    )
    result = store.set_site_protein_bound(
        positions=[150],
        strands=[0],
        field_name="complexBoundSites",
        binding_global_index=_TOPOIV_GLOBAL_IDX,
        binding_footprint=100,
        binding_both_strands=True,
        region_both_strands=True,
        main_effect_complex_indices=[_GYRASE_GLOBAL_IDX, _TOPOIV_GLOBAL_IDX],
        **_binding_tables(),
    )

    bound_sites = store.get_field("complexBoundSites")
    assert result.n_bound == 1
    assert result.released_monomers.tolist() == []
    assert result.released_complexes.tolist() == [0, -1]
    assert [
        (effect.molecule_kind, effect.global_index, effect.mature_delta, effect.bound_delta)
        for effect in result.side_effects
    ] == [("complex", _DNAA_ADP_GLOBAL_IDX, 1, -1)]
    assert bound_sites.to_regions() == [
        (150, 0, _TOPOIV_GLOBAL_IDX),
        (260, 0, _DNAA_ADP_GLOBAL_IDX),
        (400, 2, _DNAA_ADP_GLOBAL_IDX),
    ]


def test_set_site_protein_bound_releases_same_anchor_opposite_strand_for_dsdna_binding() -> None:
    store = _store_with_complex_sites([(25, 1, _DNAA_ADP_GLOBAL_IDX)])
    result = store.set_site_protein_bound(
        positions=[25],
        strands=[0],
        field_name="complexBoundSites",
        binding_global_index=_TOPOIV_GLOBAL_IDX,
        binding_footprint=100,
        binding_both_strands=True,
        region_both_strands=True,
        main_effect_complex_indices=[_TOPOIV_GLOBAL_IDX],
        **_binding_tables(),
    )

    bound_sites = store.get_field("complexBoundSites")
    assert result.released_complexes.tolist() == [-1]
    assert [
        (effect.molecule_kind, effect.global_index, effect.mature_delta, effect.bound_delta)
        for effect in result.side_effects
    ] == [("complex", _DNAA_ADP_GLOBAL_IDX, 1, -1)]
    assert bound_sites.to_regions() == [(25, 0, _TOPOIV_GLOBAL_IDX)]


def test_set_site_protein_bound_uses_full_release_footprint_inclusive_end() -> None:
    store = _store_with_complex_sites(
        [
            (149, 0, _DNAA_ADP_GLOBAL_IDX),
            (150, 0, _DNAA_ATP_GLOBAL_IDX),
        ]
    )
    result = store.set_site_protein_bound(
        positions=[100],
        strands=[0],
        field_name="complexBoundSites",
        binding_global_index=_TOPOIV_GLOBAL_IDX,
        binding_footprint=50,
        binding_both_strands=True,
        region_both_strands=True,
        main_effect_complex_indices=[_TOPOIV_GLOBAL_IDX],
        **_binding_tables(),
    )

    bound_sites = store.get_field("complexBoundSites")
    assert result.released_complexes.tolist() == [-1]
    assert [
        (effect.global_index, effect.mature_delta)
        for effect in result.side_effects
    ] == [(_DNAA_ADP_GLOBAL_IDX, 1)]
    assert bound_sites.to_regions() == [
        (100, 0, _TOPOIV_GLOBAL_IDX),
        (150, 0, _DNAA_ATP_GLOBAL_IDX),
    ]


def test_set_site_protein_bound_conserves_owned_binding_counts_when_rebinding_same_species() -> None:
    store = _store_with_complex_sites([(25, 0, _TOPOIV_GLOBAL_IDX)])
    result = store.set_site_protein_bound(
        positions=[30],
        strands=[0],
        field_name="complexBoundSites",
        binding_global_index=_TOPOIV_GLOBAL_IDX,
        binding_footprint=20,
        binding_both_strands=True,
        region_both_strands=True,
        main_effect_complex_indices=[_GYRASE_GLOBAL_IDX, _TOPOIV_GLOBAL_IDX],
        **_binding_tables(),
    )

    bound_sites = store.get_field("complexBoundSites")
    assert result.released_complexes.tolist() == [0, 0]
    assert result.side_effects == ()
    assert bound_sites.to_regions() == [(30, 0, _TOPOIV_GLOBAL_IDX)]
