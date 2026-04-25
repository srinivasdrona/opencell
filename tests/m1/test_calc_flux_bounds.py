"""Validation tests for opencell.m1.calc_flux_bounds.

Primary oracle: MATLAB calcFluxBounds(applyProteinBounds=false) at the
fitted snapshot, captured in karr_native_m1_dynamics.npz.
"""
from __future__ import annotations

import numpy as np
import pytest

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb


@pytest.fixture(scope="module")
def m1():
    return km.load_default()


@pytest.fixture(scope="module")
def dyn():
    return cfb.load_default_dynamics()


def _bound_diff(a: np.ndarray, b: np.ndarray) -> dict:
    """Compare two (504, 2) bound matrices."""
    assert a.shape == b.shape == (504, 2)
    with np.errstate(invalid="ignore"):
        diff = a - b
    finite_mask = np.isfinite(a) & np.isfinite(b)
    inf_match = (np.isinf(a) & np.isinf(b) & (np.sign(a) == np.sign(b)))
    finite_max_abs = float(np.max(np.abs(diff[finite_mask]))) if finite_mask.any() else 0.0
    n_inf_mismatch = int((np.isinf(a) ^ np.isinf(b)).sum())
    n_inf_signed_mismatch = int((np.isinf(a) & np.isinf(b) &
                                 (np.sign(a) != np.sign(b))).sum())
    return {
        "finite_max_abs_diff": finite_max_abs,
        "n_inf_mismatch": n_inf_mismatch,
        "n_inf_signed_mismatch": n_inf_signed_mismatch,
        "n_total_finite": int(finite_mask.sum()),
        "n_total_inf_match": int(inf_match.sum()),
    }


def test_loader_dimensions(dyn):
    assert dyn.substrates_snapshot.shape == (585, 3)
    assert dyn.enzymes_snapshot.shape == (104,)
    assert dyn.substrate_idx_fba_sub0.shape == (368,)
    assert dyn.substrate_idx_fba_cmp0.shape == (368,)
    assert dyn.substrate_idx_external_exch_0.shape == (124,)
    assert dyn.substrate_idx_internal_lim_0.shape == (35,)
    assert dyn.bounds_dynamic_no_protein_oracle.shape == (504, 2)
    assert dyn.cell_dry_mass > 0
    assert dyn.step_size_sec == 1.0
    assert dyn.compartment_extracellular_0based in (0, 1, 2)


def test_compartment_extracellular_is_index_1(dyn):
    """Karr's MATLAB has compartmentIndexs_extracellular = 2 (1-based);
    0-based should be 1."""
    assert dyn.compartment_extracellular_0based == 1


def test_substrate_indexs_fba_unique_and_in_range(dyn):
    pairs = list(zip(dyn.substrate_idx_fba_sub0.tolist(),
                     dyn.substrate_idx_fba_cmp0.tolist()))
    assert len(set(pairs)) == 368, "FBA-substrate (sub, cmp) pairs must be unique"
    assert dyn.substrate_idx_fba_sub0.min() >= 0
    assert dyn.substrate_idx_fba_sub0.max() < 585
    assert dyn.substrate_idx_fba_cmp0.min() >= 0
    assert dyn.substrate_idx_fba_cmp0.max() < 3


def test_compute_bounds_matches_matlab_oracle_no_protein(m1, dyn):
    """The full pipeline (rules 1-5) at snapshot inputs must reproduce
    MATLAB's calcFluxBounds(applyProteinBounds=false) per element."""
    py = cfb.compute_bounds(
        substrates=dyn.substrates_snapshot,
        enzymes=dyn.enzymes_snapshot,
        cell_dry_mass=dyn.cell_dry_mass,
        step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis,
        enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn,
    )
    diff = _bound_diff(py, dyn.bounds_dynamic_no_protein_oracle)
    assert diff["n_inf_mismatch"] == 0, diff
    assert diff["n_inf_signed_mismatch"] == 0, diff
    assert diff["finite_max_abs_diff"] < 1e-9, diff


def test_rule3_off_widens_bounds(m1, dyn):
    """With directionality off many directional clamps disappear so
    bounds should be at least as wide as default."""
    full = cfb.compute_bounds(
        substrates=dyn.substrates_snapshot, enzymes=dyn.enzymes_snapshot,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis, enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn,
    )
    no_dir = cfb.compute_bounds(
        substrates=dyn.substrates_snapshot, enzymes=dyn.enzymes_snapshot,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis, enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn, apply_directionality=False,
    )
    # Disabling clamps cannot make lower higher / upper lower
    assert np.all(no_dir[:, 0] <= full[:, 0] + 1e-12)
    assert np.all(no_dir[:, 1] >= full[:, 1] - 1e-12)


def test_rule4_zero_external_substrate_zeros_uptake(m1, dyn):
    """Setting an extracellular substrate to 0 forces its external-exchange
    upper bound (uptake direction) to <= 0."""
    sub = dyn.substrates_snapshot.copy()
    ext_sub_idx = int(dyn.substrate_idx_external_exch_0[0])
    cmp_ext = dyn.compartment_extracellular_0based
    sub[ext_sub_idx, cmp_ext] = 0.0
    bounds = cfb.compute_bounds(
        substrates=sub, enzymes=dyn.enzymes_snapshot,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis, enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn,
    )
    ext_rxn_idx = int(dyn.fba_rxn_idx_external_exch[0])
    assert bounds[ext_rxn_idx, 1] <= 0.0 + 1e-12


def test_rule5_zero_internal_lim_substrate_zeros_lower(m1, dyn):
    """Setting an internal-limited substrate (cytosol slice) to 0 forces
    its internal-limited-exchange lower bound to be >= 0."""
    sub = dyn.substrates_snapshot.copy()
    int_sub_idx = int(dyn.substrate_idx_internal_lim_0[0])
    sub[int_sub_idx, 0] = 0.0  # cytosol
    bounds = cfb.compute_bounds(
        substrates=sub, enzymes=dyn.enzymes_snapshot,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis, enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn,
    )
    int_rxn_idx = int(dyn.fba_rxn_idx_internal_lim_exch[0])
    assert bounds[int_rxn_idx, 0] >= 0.0 - 1e-12


def test_rule1_zero_enzyme_zeros_catalysed_reactions(m1, dyn):
    """Setting all enzymes to 0 should zero every catalysed reaction
    (rule 2 enzyme-presence kicks in)."""
    enz = np.zeros_like(dyn.enzymes_snapshot)
    bounds = cfb.compute_bounds(
        substrates=dyn.substrates_snapshot, enzymes=enz,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis, enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn,
    )
    catalysed = np.any(m1.catalysis != 0, axis=1)
    assert np.all(bounds[catalysed, 0] == 0.0)
    assert np.all(bounds[catalysed, 1] == 0.0)


def test_rule6_protein_bounds_raises():
    """Rule 6 is intentionally not implemented in Phase A."""
    with pytest.raises(NotImplementedError):
        cfb.compute_bounds(
            substrates=np.zeros((585, 3)), enzymes=np.zeros(104),
            cell_dry_mass=1.0, step_size_sec=1.0,
            catalysis=np.zeros((504, 104)), enz_bounds=np.zeros((504, 2)),
            fba_reaction_bounds=np.zeros((504, 2)),
            dyn=cfb.load_default_dynamics(),
            apply_protein_bounds=True,
        )


def test_perturbation_panel_p1_matches_oracle(m1, dyn):
    """MATLAB perturbation P1 (zero first non-zero enzyme) bounds match
    Python re-derivation."""
    # Re-create the same perturbation: zero the first non-zero enzyme
    enz = dyn.enzymes_snapshot.copy()
    nz = int(np.where(enz > 0)[0][0])
    enz[nz] = 0.0
    py = cfb.compute_bounds(
        substrates=dyn.substrates_snapshot, enzymes=enz,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis, enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn,
    )
    # MATLAB perturbation panel oracle (#refs#/b)
    import h5py
    with h5py.File("data/m1_sources/karr_flat/metabolism_dynamics.mat", "r") as f:
        mat_b = np.array(f["#refs#/b/bounds"]).T
    diff = _bound_diff(py, mat_b)
    assert diff["n_inf_mismatch"] == 0, diff
    assert diff["finite_max_abs_diff"] < 1e-9, diff


def test_perturbation_panel_p2_matches_oracle(m1, dyn):
    """MATLAB perturbation P2 (zero first external substrate) -> Python."""
    sub = dyn.substrates_snapshot.copy()
    sub[int(dyn.substrate_idx_external_exch_0[0]),
        dyn.compartment_extracellular_0based] = 0.0
    py = cfb.compute_bounds(
        substrates=sub, enzymes=dyn.enzymes_snapshot,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis, enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn,
    )
    import h5py
    with h5py.File("data/m1_sources/karr_flat/metabolism_dynamics.mat", "r") as f:
        mat_c = np.array(f["#refs#/c/bounds"]).T
    diff = _bound_diff(py, mat_c)
    assert diff["n_inf_mismatch"] == 0, diff
    assert diff["finite_max_abs_diff"] < 1e-9, diff


def test_perturbation_panel_p3_matches_oracle(m1, dyn):
    """MATLAB perturbation P3 (zero first internal-lim substrate) -> Python."""
    sub = dyn.substrates_snapshot.copy()
    sub[int(dyn.substrate_idx_internal_lim_0[0]), 0] = 0.0  # cytosol
    py = cfb.compute_bounds(
        substrates=sub, enzymes=dyn.enzymes_snapshot,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=m1.catalysis, enz_bounds=m1.enz_bounds,
        fba_reaction_bounds=np.column_stack([m1.lb, m1.ub]),
        dyn=dyn,
    )
    import h5py
    with h5py.File("data/m1_sources/karr_flat/metabolism_dynamics.mat", "r") as f:
        mat_d = np.array(f["#refs#/d/bounds"]).T
    diff = _bound_diff(py, mat_d)
    assert diff["n_inf_mismatch"] == 0, diff
    assert diff["finite_max_abs_diff"] < 1e-9, diff


def test_audit_block_in_fixture():
    """Documented finding: ATP/CTP/GTP/UTP and 20 standard AAs are all in
    M1's FBA substrate space; AA_total is the placeholder."""
    dyn = cfb.load_default_dynamics()
    audit = {a["name"]: a for a in dyn.raw["audit"]}
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        assert audit[ntp]["in_fba_substrate_space"], ntp
    aa = ["ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
          "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER",
          "THR", "TRP", "TYR", "VAL"]
    for a in aa:
        assert audit[a]["in_fba_substrate_space"], a
    assert not audit["AA_total"]["in_585"]
