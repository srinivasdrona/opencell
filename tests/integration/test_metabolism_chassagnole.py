"""Oracle test: OpenCell's SBML translator vs libroadrunner on Chassagnole 2002.

libroadrunner is the de facto standard SBML simulator (Tellurium ships it,
COPASI-comparable correctness, ~15 years of community use).  We validate
:class:`opencell.models.metabolism.MetabolismModel` by:

1. Loading BIOMD0000000051 with our libsbml+sympy compiler
2. Loading the same SBML bytes with libroadrunner
3. Integrating both for 60 simulated seconds (LSODA on our side, CVODE on RR)
4. Asserting agreement to ``rtol=1e-3`` on every dynamic species at 7 sample times

If this passes, the MathML→Python translation is provably correct on a model
with: 18 species, 48 reactions, 7 assignment rules, time-driven cofactors,
multiple compartments, polymorphic kinetics (MM, Hill, ordered Bi-Bi, etc.).

The test is skipped when libroadrunner is not installed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

roadrunner = pytest.importorskip("roadrunner")
libsbml = pytest.importorskip("libsbml")

from opencell.models.metabolism import MetabolismModel, DEFAULT_SBML_PATH  # noqa: E402
from opencell.solvers.ode_scipy import solve_ode_scipy, ScipySolverConfig  # noqa: E402


pytestmark = pytest.mark.skipif(
    not DEFAULT_SBML_PATH.exists(),
    reason="Chassagnole reference SBML not present",
)


T_END = 60.0
T_EVAL = np.array([1.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0])
RTOL_AGREEMENT = 1e-3
ATOL_AGREEMENT = 1e-6  # for species near zero


@pytest.fixture(scope="module")
def model() -> MetabolismModel:
    return MetabolismModel.load()


@pytest.fixture(scope="module")
def opencell_trajectory(model: MetabolismModel) -> dict[str, np.ndarray]:
    res = solve_ode_scipy(
        model.rhs,
        model.initial_y,
        (0.0, T_END),
        config=ScipySolverConfig(method="LSODA", rtol=1e-9, atol=1e-12),
        t_eval=T_EVAL,
    )
    assert res.success, f"OpenCell integration failed: {res.message}"
    return {sid: res.ys[i] for i, sid in enumerate(model.species_ids)}


@pytest.fixture(scope="module")
def roadrunner_trajectory(model: MetabolismModel) -> dict[str, np.ndarray]:
    rr = roadrunner.RoadRunner(str(model.sbml.sbml_path))
    rr.integrator.relative_tolerance = 1e-10
    rr.integrator.absolute_tolerance = 1e-12
    # Dense simulation, then index at our T_EVAL points to avoid roadrunner's
    # mutually-exclusive `times` vs `start/end/points` API.
    n_dense = 6001
    result = rr.simulate(0.0, T_END, n_dense)
    dense_t = np.asarray(result[:, 0])
    cols = result.colnames
    out: dict[str, np.ndarray] = {}
    sample_idx = np.searchsorted(dense_t, T_EVAL)
    for sid in model.species_ids:
        col = f"[{sid}]"
        if col not in cols:
            raise AssertionError(f"Species {sid!r} missing from roadrunner output")
        j = cols.index(col)
        out[sid] = np.asarray(result[sample_idx, j])
    return out


class TestChassagnoleAgreement:
    def test_all_species_agree_with_roadrunner(
        self,
        model: MetabolismModel,
        opencell_trajectory: dict[str, np.ndarray],
        roadrunner_trajectory: dict[str, np.ndarray],
    ):
        failures: list[str] = []
        for sid in model.species_ids:
            ours = opencell_trajectory[sid]
            theirs = roadrunner_trajectory[sid]
            if not np.allclose(ours, theirs, rtol=RTOL_AGREEMENT, atol=ATOL_AGREEMENT):
                rel_err = np.abs(ours - theirs) / (np.abs(theirs) + ATOL_AGREEMENT)
                failures.append(
                    f"  {sid}: max_rel_err={rel_err.max():.3e} "
                    f"(ours={ours.tolist()}, rr={theirs.tolist()})"
                )
        assert not failures, "Disagreements with libroadrunner:\n" + "\n".join(failures)

    def test_no_negative_concentrations(
        self,
        model: MetabolismModel,
        opencell_trajectory: dict[str, np.ndarray],
    ):
        for sid in model.species_ids:
            assert np.all(opencell_trajectory[sid] >= -ATOL_AGREEMENT), (
                f"Negative concentration in {sid}: {opencell_trajectory[sid]}"
            )

    def test_initial_conditions_match(
        self,
        model: MetabolismModel,
    ):
        rr = roadrunner.RoadRunner(str(model.sbml.sbml_path))
        for i, sid in enumerate(model.species_ids):
            rr_init = rr[f"init([{sid}])"]
            assert model.initial_y[i] == pytest.approx(rr_init, rel=1e-9), (
                f"Initial value mismatch for {sid}: "
                f"ours={model.initial_y[i]}, rr={rr_init}"
            )


class TestMetabolismProvenance:
    def test_provenance_contains_paper_pairing(self, model: MetabolismModel):
        prov = model.provenance()
        assert prov["biomodels_id"] == "BIOMD0000000051"
        assert prov["paper_doi"] == "10.1002/bit.10288"
        assert prov["paper_pubmed_id"] == "17590932"
        assert len(prov["sbml_sha256"]) == 64
        assert prov["n_dynamic_species"] == 18
        assert prov["n_reactions"] == 48
