"""Gate G1.8: thermodynamic feasibility check (stub for Phase 1).

The micro-model (constitutive gene expression) has no flux-carrying
reactions with meaningful ΔG — transcription and translation are
polymerization events modeled as first-order kinetics in abstract
molecule counts. Thermodynamic feasibility only becomes testable when
we reach the Chassagnole 2002 central-carbon metabolism in Phase 2.

For Phase 1 we install the **infrastructure** — a
`ThermoFeasibilityReport` data structure and a `check_directionality`
function — so the Phase 2 metabolic module can plug in directly.

A single "real" test is included: reactions tagged IRREVERSIBLE must
not reverse direction in a provided flux vector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

import pytest


class ReactionDirection(Enum):
    IRREVERSIBLE_FORWARD = auto()
    IRREVERSIBLE_REVERSE = auto()
    REVERSIBLE = auto()


@dataclass
class ThermoFeasibilityReport:
    """Audit report produced by `check_directionality`."""

    violations: list[str] = field(default_factory=list)
    n_reactions: int = 0
    n_irreversible: int = 0

    @property
    def feasible(self) -> bool:
        return not self.violations


def check_directionality(
    fluxes: dict[str, float],
    directions: dict[str, ReactionDirection],
    zero_tol: float = 1e-9,
) -> ThermoFeasibilityReport:
    """Verify that each flux respects its declared direction.

    Parameters
    ----------
    fluxes : dict of reaction_id → signed flux (forward positive)
    directions : dict of reaction_id → ReactionDirection
    zero_tol : absolute flux threshold below which "no flux" is assumed

    Returns
    -------
    ThermoFeasibilityReport : list of violations and summary statistics
    """
    report = ThermoFeasibilityReport(n_reactions=len(fluxes))
    for rxn, flux in fluxes.items():
        direction = directions.get(rxn, ReactionDirection.REVERSIBLE)
        if direction is ReactionDirection.REVERSIBLE:
            continue
        report.n_irreversible += 1
        if direction is ReactionDirection.IRREVERSIBLE_FORWARD and flux < -zero_tol:
            report.violations.append(f"{rxn}: forward-only but flux = {flux:.3g} < 0")
        elif direction is ReactionDirection.IRREVERSIBLE_REVERSE and flux > zero_tol:
            report.violations.append(f"{rxn}: reverse-only but flux = {flux:.3g} > 0")
    return report


@pytest.mark.gate
class TestGateG18ThermoFeasibility:
    """G1.8: thermodynamic feasibility infrastructure + stub test."""

    def test_empty_system_is_trivially_feasible(self) -> None:
        """No reactions → no violations, report.feasible is True."""
        report = check_directionality({}, {})
        assert report.feasible
        assert report.n_reactions == 0

    def test_all_reversible_cannot_violate(self) -> None:
        fluxes = {"r1": +1.0, "r2": -2.5, "r3": 0.0}
        directions = {k: ReactionDirection.REVERSIBLE for k in fluxes}
        report = check_directionality(fluxes, directions)
        assert report.feasible
        assert report.n_irreversible == 0

    def test_forward_only_with_negative_flux_flagged(self) -> None:
        fluxes = {"pyk": -0.5}  # pyruvate kinase reversing — not allowed
        directions = {"pyk": ReactionDirection.IRREVERSIBLE_FORWARD}
        report = check_directionality(fluxes, directions)
        assert not report.feasible
        assert any("pyk" in v and "< 0" in v for v in report.violations)

    def test_reverse_only_with_positive_flux_flagged(self) -> None:
        fluxes = {"ppck": +1.2}
        directions = {"ppck": ReactionDirection.IRREVERSIBLE_REVERSE}
        report = check_directionality(fluxes, directions)
        assert not report.feasible
        assert any("ppck" in v and "> 0" in v for v in report.violations)

    def test_near_zero_flux_within_tolerance_ok(self) -> None:
        fluxes = {"r": -1e-12}
        directions = {"r": ReactionDirection.IRREVERSIBLE_FORWARD}
        report = check_directionality(fluxes, directions, zero_tol=1e-9)
        assert report.feasible

    def test_micro_model_has_no_thermo_constraints(self) -> None:
        """Micro-model rationale: transcription/translation are abstract
        first-order kinetics, not mass-balanced reactions with ΔG.
        Running the check with no directionality constraints is expected
        to be trivially feasible."""
        micro_fluxes = {
            "transcription": 0.60,  # mRNA synth
            "mrna_decay": 0.60,  # at SS matches synth
            "translation": 4.16,  # SS: k_P * m_ss
            "protein_decay": 4.16,
        }
        report = check_directionality(micro_fluxes, directions={})
        assert report.feasible, "Micro-model is thermo-agnostic in Phase 1"
