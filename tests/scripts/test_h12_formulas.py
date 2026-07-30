"""Formula unit tests for `scripts/l22_evidence/h12.py`'s `predict_*`
functions, using small hand-constructed `before`/`fixture` inputs with
hand-computed expected outputs (independent of any real oracle/fixture
data) -- distinct from the full-scale run against real Karr oracle traces
(`docs/phase_f/l2_2_design_a/h12/*.json`, produced by `run_h12`).

Each test derives its expected numbers directly from the SAME formula
documented (with MATLAB source-line citations) in each predictor's
docstring, worked out by hand in the test's own comment block, so a
regression in the arithmetic itself (not just a full-scale oracle
mismatch) is caught immediately and cheaply (no oracle/fixture I/O).

Also covers the guard/regime-validity boundary for each predictor (a
"regime invalid" case alongside the "regime valid, full match" case), and
the MacromolecularComplexation network>=2 "genuine Monte Carlo, excluded"
vs "all-bounds-zero, guaranteed-deterministic" split.

Run via `bin\\oc-pytest tests/scripts/test_h12_formulas.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import h12  # noqa: E402


def _arr(*values) -> np.ndarray:
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = tuple(values[0])
    return np.array(values, dtype=np.float64)


# ---------------------------------------------------------------------------
# tRNAAminoacylation
# ---------------------------------------------------------------------------


def _trna_fixture() -> dict:
    return {
        "substrateIndexs_water_0b": 0,
        "substrateIndexs_hydrogen_0b": 1,
        "speciesIndexs_enzymes_0b": np.array([0]),
        # rows = RNAs (2), cols = [sub0, sub1(water col dummy... see below), sub2, enz0, rna0, rna1]
        # NOTE: cols 0/1 are the water/hydrogen substrate columns (exempted
        # from the guard); col 2 is the one real, checked substrate; col 3
        # is the (also checked) enzyme "budget" column; cols 4/5 are the
        # freeRNA self-columns (never in `guard_cols`, never in `demand`).
        "speciesReactantByproductMatrix": np.array(
            [
                [0.0, 0.0, 1.0, 2.0, 9.0, 0.0],
                [0.0, 0.0, 2.0, 1.0, 0.0, 9.0],
            ]
        ),
        "reactionStoichiometryMatrix": np.array(
            [
                [-1.0, 0.0],
                [0.0, -1.0],
                [1.0, 1.0],
            ]
        ),
        "reactionModificationMatrix": np.array(
            [
                [1.0, 0.0],
                [0.0, 1.0],
            ]
        ),
    }


def test_trna_aminoacylation_full_saturation_matches_hand_computed_deltas():
    fixture = _trna_fixture()
    before = {
        "freeRNAs": _arr([5.0, 7.0])[None, :],
        "aminoacylatedRNAs": _arr([0.0, 0.0])[None, :],
        "substrates": _arr([100.0, 100.0, 100.0])[None, :],
        "enzymes": _arr([100.0])[None, :],
    }
    preds = h12.predict_trna_aminoacylation(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    assert p.regime_valid is True
    assert p.nontrivial is True
    # demand[2] = 1*5 + 2*7 = 19 <= supply[2]=100; demand[3] = 2*5 + 1*7 = 17 <= supply[3]=100
    np.testing.assert_array_equal(p.predicted_delta["freeRNAs"], _arr(-5.0, -7.0))
    np.testing.assert_array_equal(p.predicted_delta["aminoacylatedRNAs"], _arr(5.0, 7.0))
    # reaction_fluxes = [5,7]; reaction_mod @ fluxes = [5,7];
    # reaction_stoich @ [5,7] = [-5, -7, 5+7=12]
    np.testing.assert_array_equal(p.predicted_delta["substrates"], _arr(-5.0, -7.0, 12.0))
    np.testing.assert_array_equal(p.predicted_delta["enzymes"], _arr(0.0))


def test_trna_aminoacylation_guard_fails_when_enzyme_supply_insufficient():
    fixture = _trna_fixture()
    before = {
        "freeRNAs": _arr([5.0, 7.0])[None, :],
        "aminoacylatedRNAs": _arr([0.0, 0.0])[None, :],
        "substrates": _arr([100.0, 100.0, 100.0])[None, :],
        # demand[3] (enzyme col) = 2*5+1*7 = 17 > supply[3]=10 -> guard fails
        "enzymes": _arr([10.0])[None, :],
    }
    preds = h12.predict_trna_aminoacylation(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    assert p.regime_valid is False
    assert p.regime_reason == "resource_guard_failed"
    assert p.predicted_delta == {}


# ---------------------------------------------------------------------------
# ProteinProcessingI
# ---------------------------------------------------------------------------


def _ppi_fixture() -> dict:
    return {
        "substrateIndexs_water_0b": 0,
        "substrateIndexs_hydrogen_0b": 1,
        "substrateIndexs_methionine_0b": 2,
        "substrateIndexs_formate_0b": 3,
        "enzymeIndexs_deformylase_0b": 0,
        "enzymeIndexs_methionineAminoPeptidase_0b": 1,
        "deformylaseSpecificRate": 2.0,
        "methionineAminoPeptidaseSpecificRate": 3.0,
        "stepSizeSec": 1.0,
        "cleavage_mask": np.array([True, False]),
    }


def test_protein_processing_i_full_saturation_matches_hand_computed_deltas():
    fixture = _ppi_fixture()
    before = {
        "unprocessedMonomers": _arr([3.0, 2.0])[None, :],
        "enzymes": _arr([10.0, 10.0])[None, :],
        "substrates": _arr([100.0, 0.0, 0.0, 0.0])[None, :],
    }
    preds = h12.predict_protein_processing_i(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    # total=5, cleave_sum=3 (species0 only); deform_limit=10*2*1=20>=5;
    # cleave_limit=10*3*1=30>=3; water=100>=5+3=8 -> regime valid
    assert p.regime_valid is True
    assert p.nontrivial is True
    np.testing.assert_array_equal(p.predicted_delta["unprocessedMonomers"], _arr(-3.0, -2.0))
    np.testing.assert_array_equal(p.predicted_delta["processedMonomers"], _arr(3.0, 2.0))
    # water -= total+cleave_sum(8); formate += total(5); hydrogen += total(5); methionine += cleave_sum(3)
    np.testing.assert_array_equal(p.predicted_delta["substrates"], _arr(-8.0, 5.0, 3.0, 5.0))
    np.testing.assert_array_equal(p.predicted_delta["enzymes"], _arr(0.0, 0.0))


def test_protein_processing_i_guard_fails_when_water_insufficient():
    fixture = _ppi_fixture()
    before = {
        "unprocessedMonomers": _arr([3.0, 2.0])[None, :],
        "enzymes": _arr([10.0, 10.0])[None, :],
        # water=7 < total(5)+cleave_sum(3)=8 -> guard fails
        "substrates": _arr([7.0, 0.0, 0.0, 0.0])[None, :],
    }
    preds = h12.predict_protein_processing_i(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    assert p.regime_valid is False
    assert p.regime_reason == "capacity_or_water_guard_failed"
    assert p.predicted_delta == {}


# ---------------------------------------------------------------------------
# ProteinProcessingII
# ---------------------------------------------------------------------------


def _ppii_fixture() -> dict:
    return {
        "substrateIndexs_water_0b": 0,
        "substrateIndexs_PG160_0b": 1,
        "substrateIndexs_SNGLYP_0b": 2,
        "substrateIndexs_hydrogen_0b": 3,
        "enzymeIndexs_signalPeptidase_0b": 0,
        "enzymeIndexs_diacylglycerylTransferase_0b": 1,
        "lipoproteinSignalPeptidaseSpecificRate": 2.0,
        "lipoproteinDiacylglycerylTransferaseSpecificRate": 1.0,
        "stepSizeSec": 1.0,
        "unprocessedMonomerIndexs_0b": np.array([0]),
        "lipoproteinMonomerIndexs_0b": np.array([1]),
        "secretedMonomerIndexs_0b": np.array([2]),
    }


def test_protein_processing_ii_full_saturation_matches_hand_computed_deltas():
    fixture = _ppii_fixture()
    before = {
        "unprocessedMonomers": _arr([2.0, 3.0, 4.0, 0.0])[None, :],
        "enzymes": _arr([10.0, 10.0])[None, :],
        "substrates": _arr([100.0, 100.0, 100.0, 100.0])[None, :],
    }
    preds = h12.predict_protein_processing_ii(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    # peptidase_demand = unproc[1]+unproc[2] = 7; transferase_demand = unproc[1] = 3
    # peptidase_limit = 10*2*1=20>=7; transferase_limit=10*1*1=10>=3
    # water=100>=7; pg160=100>=3 -> regime valid
    assert p.regime_valid is True
    assert p.nontrivial is True
    np.testing.assert_array_equal(p.predicted_delta["unprocessedMonomers"], _arr(-2.0, -3.0, -4.0, 0.0))
    np.testing.assert_array_equal(p.predicted_delta["processedMonomers"], _arr(2.0, 3.0, 4.0, 0.0))
    # signal_delta[peptidase_idx=1,2] = unproc[1,2] = 3,4; passthrough idx0 forced 0
    np.testing.assert_array_equal(p.predicted_delta["signalSequenceMonomers"], _arr(0.0, 3.0, 4.0, 0.0))
    # water -= peptidase_demand(7); pg160 -= transferase_demand(3);
    # snglyp += transferase_demand(3); hydrogen += transferase_demand(3)
    np.testing.assert_array_equal(p.predicted_delta["substrates"], _arr(-7.0, -3.0, 3.0, 3.0))
    np.testing.assert_array_equal(p.predicted_delta["enzymes"], _arr(0.0, 0.0))


def test_protein_processing_ii_guard_fails_when_pg160_insufficient():
    fixture = _ppii_fixture()
    before = {
        "unprocessedMonomers": _arr([2.0, 3.0, 4.0, 0.0])[None, :],
        "enzymes": _arr([10.0, 10.0])[None, :],
        # pg160(col1)=2 < transferase_demand(3) -> guard fails
        "substrates": _arr([100.0, 2.0, 100.0, 100.0])[None, :],
    }
    preds = h12.predict_protein_processing_ii(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    assert p.regime_valid is False
    assert p.regime_reason == "capacity_or_metabolite_guard_failed"
    assert p.predicted_delta == {}


# ---------------------------------------------------------------------------
# ProteinFolding
# ---------------------------------------------------------------------------


def _folding_fixture() -> dict:
    return {
        "substrateIndexs_water_0b": 0,
        "substrateIndexs_hydrogen_0b": 1,
        # 4 total species rows; folded_rows selects rows [0,1,2] (monomerA,
        # monomerB, complexC) as folding-eligible; row3 is unrelated/unused.
        "proteinProstheticGroupMatrix": np.array(
            [
                [0.0, 0.0, 2.0],
                [0.0, 0.0, 3.0],
                [0.0, 0.0, 1.0],
                [0.0, 0.0, 999.0],
            ]
        ),
        # single chaperone column, required by all 3 folding-eligible rows
        # (mirrors real trigger-factor semantics: every monomer requires it).
        "proteinChaperoneMatrix": np.array(
            [
                [1.0],
                [1.0],
                [1.0],
                [0.0],
            ]
        ),
        "monomerComplexIndexs_folded_0b": np.array([0, 1, 2]),
        "complexIndexs_folding_0b": np.array([0]),
        "complexIndexs_notFolding_0b": np.array([1]),
        "speciesIndexs_monomers_0b": np.array([0, 1]),
        "speciesIndexs_complexs_0b": np.array([2]),
    }


def _folding_fixture_two_chaperones() -> dict:
    """Variant with 2 chaperone columns: chaperone0 required by ALL 3
    folding-eligible species (trigger-factor-like); chaperone1 required
    ONLY by monomerB (row 1) -- lets a single zero-count chaperone block
    exactly one species while the others remain eligible."""
    fixture = _folding_fixture()
    fixture["proteinChaperoneMatrix"] = np.array(
        [
            [1.0, 0.0],  # monomerA: needs chaperone0 only
            [1.0, 1.0],  # monomerB: needs chaperone0 AND chaperone1
            [1.0, 0.0],  # complexC: needs chaperone0 only
            [0.0, 0.0],  # unused row
        ]
    )
    return fixture


def test_protein_folding_full_saturation_matches_hand_computed_deltas():
    fixture = _folding_fixture()
    before = {
        "unfoldedMonomers": _arr([5.0, 7.0])[None, :],
        "unfoldedComplexs": _arr([4.0, 9.0])[None, :],
        "substrates": _arr([100.0, 100.0, 100.0])[None, :],
        "enzymes": _arr([50.0])[None, :],
    }
    preds = h12.predict_protein_folding(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    # flux=[5,7,4]; demand[2]=2*5+3*7+1*4=35 <= substrates[2]=100 -> valid
    assert p.regime_valid is True
    assert p.nontrivial is True
    np.testing.assert_array_equal(p.predicted_delta["unfoldedMonomers"], _arr(-5.0, -7.0))
    np.testing.assert_array_equal(p.predicted_delta["foldedMonomers"], _arr(5.0, 7.0))
    # unfolded_complexs_delta[folding=0] = -flux[complexs_idx]=-4; [notfolding=1] = -unfolded_complexs[1]=-9
    np.testing.assert_array_equal(p.predicted_delta["unfoldedComplexs"], _arr(-4.0, -9.0))
    np.testing.assert_array_equal(p.predicted_delta["foldedComplexs"], _arr(4.0, 9.0))
    np.testing.assert_array_equal(p.predicted_delta["substrates"], _arr(0.0, 0.0, -35.0))
    np.testing.assert_array_equal(p.predicted_delta["enzymes"], _arr(0.0))


def test_protein_folding_guard_fails_when_prosthetic_group_substrate_insufficient():
    fixture = _folding_fixture()
    before = {
        "unfoldedMonomers": _arr([5.0, 7.0])[None, :],
        "unfoldedComplexs": _arr([4.0, 9.0])[None, :],
        # col2 (real substrate) = 10 < demand(35) -> guard fails
        "substrates": _arr([100.0, 100.0, 10.0])[None, :],
        "enzymes": _arr([50.0])[None, :],
    }
    preds = h12.predict_protein_folding(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    assert p.regime_valid is False
    assert p.regime_reason == "prosthetic_group_guard_failed"
    # only the unconditional not-folding passthrough is asserted in the fail branch
    np.testing.assert_array_equal(p.predicted_delta["unfoldedComplexs_notfolding_only"], fixture["complexIndexs_notFolding_0b"])


def test_protein_folding_zero_count_chaperone_blocks_only_the_dependent_species():
    """Source-faithful MATLAB semantics (ProteinFolding.m ~line 535):
    `species = max(0, [substrates; enzymes*Inf; ...]')`. A present
    chaperone (count>0) gives `count*Inf == Inf` (non-limiting); an
    ABSENT chaperone (count==0) gives `0*Inf == NaN`, and
    `max(0, NaN) == 0` in MATLAB -- forcing that species' flux to zero
    WITHOUT failing the whole tick. This is a PER-SPECIES guard: only
    monomerB (the sole species requiring the scarce chaperone1) is
    excluded; monomerA and complexC -- which don't need chaperone1 --
    still fold at full flux.

    Hand-computed with `_folding_fixture_two_chaperones()`
    (chaperone0 present=50, chaperone1 absent=0):
      eligible_flux = [5 (monomerA, chap0 only), 0 (monomerB, needs
      chap1 too -> blocked), 4 (complexC, chap0 only)]
      demand (col2 of proteinProstheticGroupMatrix) = 2*5 + 3*0 + 1*4 = 14
      <= substrates[2]=100 -> regime_valid=True (guard satisfied, not failed)
      nontrivial=True (5 and 4 still nonzero)
    """
    fixture = _folding_fixture_two_chaperones()
    before = {
        "unfoldedMonomers": _arr([5.0, 7.0])[None, :],
        "unfoldedComplexs": _arr([4.0, 9.0])[None, :],
        "substrates": _arr([100.0, 100.0, 100.0])[None, :],
        "enzymes": _arr([50.0, 0.0])[None, :],  # chaperone0 present, chaperone1 absent
    }
    preds = h12.predict_protein_folding(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    assert p.regime_valid is True
    assert p.regime_reason != "prosthetic_group_guard_failed"
    assert p.nontrivial is True
    # monomerA (idx0) unaffected; monomerB (idx1) zeroed by the absent chaperone1
    np.testing.assert_array_equal(p.predicted_delta["unfoldedMonomers"], _arr(-5.0, 0.0))
    np.testing.assert_array_equal(p.predicted_delta["foldedMonomers"], _arr(5.0, 0.0))
    # complexC (folding-network idx0) unaffected by chaperone1 (only needs chaperone0)
    np.testing.assert_array_equal(p.predicted_delta["unfoldedComplexs"], _arr(-4.0, -9.0))
    np.testing.assert_array_equal(p.predicted_delta["foldedComplexs"], _arr(4.0, 9.0))
    # demand = 2*5 + 3*0 + 1*4 = 14 (monomerB's contribution excluded)
    np.testing.assert_array_equal(p.predicted_delta["substrates"], _arr(0.0, 0.0, -14.0))
    assert "monomer_folding_fires" in p.branch_tags
    assert "complex_folding_fires" in p.branch_tags


def test_protein_folding_all_chaperones_zero_yields_trivial_no_op_not_a_guard_failure():
    """When EVERY chaperone a species depends on is present at count zero,
    `eligible_flux` collapses to all zeros for every folding-eligible
    species. Per MATLAB's `max(0, 0*Inf) == 0` semantics this is a
    trivial (nothing folds) tick, NOT a failed/invalid regime -- the
    demand computed over an empty eligible set is trivially `0 <=
    substrates`, so the guard is satisfied, just satisfied vacuously."""
    fixture = _folding_fixture_two_chaperones()
    before = {
        "unfoldedMonomers": _arr([5.0, 7.0])[None, :],
        "unfoldedComplexs": _arr([4.0, 9.0])[None, :],
        "substrates": _arr([100.0, 100.0, 100.0])[None, :],
        "enzymes": _arr([0.0, 0.0])[None, :],  # both chaperones absent
    }
    preds = h12.predict_protein_folding(seed=0, before=before, fixture=fixture)
    assert len(preds) == 1
    p = preds[0]
    assert p.regime_valid is True
    assert p.nontrivial is False
    np.testing.assert_array_equal(p.predicted_delta["unfoldedMonomers"], _arr(0.0, 0.0))
    np.testing.assert_array_equal(p.predicted_delta["foldedMonomers"], _arr(0.0, 0.0))
    # folding-network complex (idx0) blocked too (needs chaperone0); not-folding (idx1) is unconditional
    np.testing.assert_array_equal(p.predicted_delta["unfoldedComplexs"], _arr(0.0, -9.0))
    np.testing.assert_array_equal(p.predicted_delta["foldedComplexs"], _arr(0.0, 9.0))
    np.testing.assert_array_equal(p.predicted_delta["substrates"], _arr(0.0, 0.0, 0.0))
    assert p.branch_tags == frozenset()


# ---------------------------------------------------------------------------
# MacromolecularComplexation
# ---------------------------------------------------------------------------


def _complexation_fixture() -> dict:
    return {
        "complexComposition": np.array(
            [
                [2.0, 0.0],
                [1.0, 0.0],
                [0.0, 3.0],
                [0.0, 1.0],
            ]
        ),
        "substrates2complexNetworks": np.array([1, 1, 2, 2]),
        "complexs2complexNetworks": np.array([1, 2]),
    }


def test_macromolecular_complexation_network1_matches_hand_computed_ground_truth():
    fixture = _complexation_fixture()
    before = {"substrates": _arr([10.0, 100.0, 1.0, 1.0])[None, :]}
    preds = h12.predict_macromolecular_complexation(seed=0, before=before, fixture=fixture)
    net1 = [p for p in preds if p.unit == "network_1"][0]
    # network1: sub_idx=[0,1], cx_idx=[0]; block=[[2],[1]]; pool=[10,100];
    # ratio=[10/2=5, 100/1=100]; ub=floor(min(5,100))=5
    assert net1.regime_valid is True
    assert net1.regime_reason == "network_1_karr_ground_truth_no_competition"
    assert net1.nontrivial is True
    np.testing.assert_array_equal(net1.predicted_delta["complexs"], _arr(5.0, 0.0))
    # substrates_delta[sub_idx] = -(block @ ub) = -([[2],[1]] @ [5]) = [-10,-5]
    np.testing.assert_array_equal(net1.predicted_delta["substrates"], _arr(-10.0, -5.0, 0.0, 0.0))


def test_macromolecular_complexation_network_ge2_nonzero_bound_is_excluded_as_genuine_monte_carlo():
    fixture = _complexation_fixture()
    # network2: sub_idx=[2,3], cx_idx=[1]; block=[[3],[1]]; pool=[100,2];
    # ratio=[100/3=33.3, 2/1=2]; ub=floor(min(33.3,2))=2 (nonzero!)
    before = {"substrates": _arr([10.0, 100.0, 100.0, 2.0])[None, :]}
    preds = h12.predict_macromolecular_complexation(seed=0, before=before, fixture=fixture)
    net2 = [p for p in preds if p.unit == "network_2"][0]
    assert net2.regime_valid is False
    assert net2.regime_reason == "network_ge2_nonzero_bound_genuine_monte_carlo_competition"
    assert net2.predicted_delta == {}


def test_macromolecular_complexation_network_ge2_all_bounds_zero_is_guaranteed_deterministic():
    fixture = _complexation_fixture()
    # network2: sub_idx=[2,3], cx_idx=[1]; block=[[3],[1]]; pool=[0.5,0.5];
    # ratio=[0.5/3=0.16, 0.5/1=0.5]; ub=floor(min(0.16,0.5))=floor(0.16)=0
    before = {"substrates": _arr([10.0, 100.0, 0.5, 0.5])[None, :]}
    preds = h12.predict_macromolecular_complexation(seed=0, before=before, fixture=fixture)
    net2 = [p for p in preds if p.unit == "network_2"][0]
    assert net2.regime_valid is True
    assert net2.regime_reason == "network_ge2_all_bounds_zero_monotonic_guarantee"
    assert net2.nontrivial is False
    np.testing.assert_array_equal(net2.predicted_delta["complexs"], _arr(0.0, 0.0))
    np.testing.assert_array_equal(net2.predicted_delta["substrates"], _arr(0.0, 0.0, 0.0, 0.0))
