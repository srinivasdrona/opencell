"""Oracle test: OpenCell's SBML translator vs libroadrunner on Vilar 2002.

This is the second sub-model validation against libroadrunner (after
metabolism / Chassagnole 2002). Vilar 2002 (BIOMD0000000035) is a
genetic-oscillator model where every dynamic species is declared with
``hasOnlySubstanceUnits=true`` — molecule counts, not concentrations.

We integrate both engines for 200 simulated time-units (long enough to
cover ~3 oscillation periods of the activator-repressor limit cycle) and
require agreement to ``rtol=1e-3`` on every species at multiple sample
times.

Mass-action models with no assignment rules typically agree more tightly
than that, but oscillator dynamics integrated over many periods accumulate
phase drift; the tolerance accommodates that without masking real bugs.

The test is skipped when libroadrunner is not installed.
"""

from __future__ import annotations

import numpy as np
import pytest

roadrunner = pytest.importorskip("roadrunner")
libsbml = pytest.importorskip("libsbml")

from opencell.models.transcription import (  # noqa: E402
    DEFAULT_SBML_PATH,
    TranscriptionModel,
)
from opencell.solvers.ode_scipy import (  # noqa: E402
    ScipySolverConfig,
    solve_ode_scipy,
)

pytestmark = pytest.mark.skipif(
    not DEFAULT_SBML_PATH.exists(),
    reason="Vilar reference SBML not present",
)


T_END = 200.0
# Sample times spanning early transient and ~3 oscillation periods
T_EVAL = np.array([1.0, 5.0, 25.0, 50.0, 100.0, 150.0, 200.0])
RTOL_AGREEMENT = 1e-3
ATOL_AGREEMENT = 1e-3  # absolute floor: small molecule counts (e.g. DA, DR ~1)


@pytest.fixture(scope="module")
def model() -> TranscriptionModel:
    return TranscriptionModel.load()


@pytest.fixture(scope="module")
def opencell_trajectory(model: TranscriptionModel) -> dict[str, np.ndarray]:
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
def roadrunner_trajectory(model: TranscriptionModel) -> dict[str, np.ndarray]:
    rr = roadrunner.RoadRunner(str(model.sbml.sbml_path))
    rr.integrator.relative_tolerance = 1e-10
    rr.integrator.absolute_tolerance = 1e-12
    # Request amounts explicitly: Vilar's species are hasOnlySubstanceUnits=true,
    # and OpenCell stores amount-mode species as amounts. Match that.
    rr.selections = ["time"] + model.species_ids
    n_dense = 8001
    result = rr.simulate(0.0, T_END, n_dense)
    dense_t = np.asarray(result[:, 0])
    cols = result.colnames
    out: dict[str, np.ndarray] = {}
    sample_idx = np.searchsorted(dense_t, T_EVAL)
    for sid in model.species_ids:
        if sid not in cols:
            raise AssertionError(f"Species {sid!r} missing from roadrunner output (cols={cols})")
        j = cols.index(sid)
        out[sid] = np.asarray(result[sample_idx, j])
    return out


class TestVilarAgreement:
    def test_all_species_agree_with_roadrunner(
        self,
        model: TranscriptionModel,
        opencell_trajectory: dict[str, np.ndarray],
        roadrunner_trajectory: dict[str, np.ndarray],
    ) -> None:
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

    def test_no_negative_counts(
        self,
        model: TranscriptionModel,
        opencell_trajectory: dict[str, np.ndarray],
    ) -> None:
        for sid in model.species_ids:
            assert np.all(opencell_trajectory[sid] >= -ATOL_AGREEMENT), (
                f"Negative count in {sid}: {opencell_trajectory[sid]}"
            )

    def test_gene_copy_conservation(
        self,
        model: TranscriptionModel,
        opencell_trajectory: dict[str, np.ndarray],
    ) -> None:
        # Single-copy genes: DA + DAp = 1 and DR + DRp = 1 at every sample
        da = opencell_trajectory["DA"] + opencell_trajectory["DAp"]
        dr = opencell_trajectory["DR"] + opencell_trajectory["DRp"]
        np.testing.assert_allclose(da, 1.0, rtol=1e-6, atol=1e-9)
        np.testing.assert_allclose(dr, 1.0, rtol=1e-6, atol=1e-9)

    def test_initial_conditions_match(self, model: TranscriptionModel) -> None:
        rr = roadrunner.RoadRunner(str(model.sbml.sbml_path))
        for i, sid in enumerate(model.species_ids):
            # Amount-mode: OpenCell stores amount; ask roadrunner for init amount.
            rr_init = rr[f"init({sid})"]
            assert model.initial_y[i] == pytest.approx(rr_init, rel=1e-9, abs=1e-12), (
                f"Initial value mismatch for {sid}: ours={model.initial_y[i]}, rr={rr_init}"
            )


class TestTranscriptionProvenance:
    def test_provenance_contains_paper_pairing(self, model: TranscriptionModel) -> None:
        prov = model.provenance()
        assert prov["biomodels_id"] == "BIOMD0000000035"
        assert prov["paper_doi"] == "10.1073/pnas.092133899"
        assert prov["paper_pubmed_id"] == "11972055"
        assert len(prov["sbml_sha256"]) == 64
        assert prov["n_dynamic_species"] == 9
        assert prov["n_reactions"] == 16
