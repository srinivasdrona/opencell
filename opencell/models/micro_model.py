"""Micro-model: constitutive gene expression (Alon 2006 / Thattai 2001).

The simplest publishable benchmark for our simulation engine.
Uses published E. coli parameters and a textbook analytical solution.

References:
  Alon (2006) Chapter 1, Box 1.1. DOI: 10.1201/9781420011432
  Thattai & van Oudenaarden (2001) PNAS 98(15). DOI: 10.1073/pnas.151588598
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from opencell.data.micro_model_parameters import MICRO_MODEL_PARAMETER_VALUES


@dataclass(frozen=True)
class MicroModelParams:
    """Parameters for constitutive gene expression in E. coli.

    Source: Thattai & van Oudenaarden (2001), Figure 1 caption "base case".
    DOI: 10.1073/pnas.151588598

    Verbatim from Fig. 1 caption (verified against PDF, 2026-04-23):
      "The mRNA half-life is fixed at 2 min. The base case corresponds to
       a burst size b = 20, a transcript initiation rate k_R = 0.01 s^-1
       and a protein half-life ln(2)/g_P = 1 h."

    Conversions to min^-1 (units used internally):
      k_R   = 0.01 s^-1 × 60                  = 0.60 mRNA/min
      gamma_R = ln(2) / 2 min                 = 0.34657 /min
      k_P   = b × gamma_R = 20 × 0.34657      = 6.9315 protein/mRNA/min
      gamma_P = ln(2) / 60 min                = 0.011552 /min
    """

    alpha_m: float = MICRO_MODEL_PARAMETER_VALUES[
        "thattai-2001-transcription-initiation-per-minute"
    ]
    beta_m: float = math.log(2) / MICRO_MODEL_PARAMETER_VALUES[
        "thattai-2001-mrna-half-life-minutes"
    ]
    alpha_p: float = (
        MICRO_MODEL_PARAMETER_VALUES["thattai-2001-protein-burst-size"] * beta_m
    )
    beta_p: float = math.log(2) / MICRO_MODEL_PARAMETER_VALUES[
        "thattai-2001-protein-half-life-minutes"
    ]

    @property
    def m_ss(self) -> float:
        """Analytical steady-state mRNA count."""
        return self.alpha_m / self.beta_m

    @property
    def p_ss(self) -> float:
        """Analytical steady-state protein count."""
        return (self.alpha_m * self.alpha_p) / (self.beta_m * self.beta_p)

    @property
    def burst_size(self) -> float:
        """Average proteins per mRNA lifetime (b = α_p / β_m)."""
        return self.alpha_p / self.beta_m

    @property
    def protein_variance_ss(self) -> float:
        """Analytical steady-state protein variance (Thattai 2001 Eq. 5)."""
        b = self.burst_size
        return self.p_ss * (1 + b / (1 + self.beta_p / self.beta_m))

    @property
    def protein_fano_factor(self) -> float:
        """Fano factor = Var/Mean at steady state."""
        return self.protein_variance_ss / self.p_ss

    def m_exact(self, t: float | np.ndarray, m0: float = 0.0) -> float | np.ndarray:
        """Exact analytical mRNA time course.

        m(t) = m_ss * (1 - e^(-β_m t)) + m0 * e^(-β_m t)
        """
        exp_m = np.exp(-self.beta_m * t)
        return self.m_ss * (1 - exp_m) + m0 * exp_m

    def p_exact(
        self, t: float | np.ndarray, m0: float = 0.0, p0: float = 0.0
    ) -> float | np.ndarray:
        """Exact analytical protein time course (Alon Box 1.1).

        For m0=0, p0=0, β_m ≠ β_p:
        p(t) = (α_m·α_p)/(β_m·β_p) · [1 + (β_p·e^(-β_m·t) - β_m·e^(-β_p·t))/(β_m - β_p)]
        """
        exp_m = np.exp(-self.beta_m * t)
        exp_p = np.exp(-self.beta_p * t)
        p_ss = self.p_ss
        delta_beta = self.beta_m - self.beta_p

        # Alon (2006) Box 1.1 exact solution
        p_particular = p_ss * (1 + (self.beta_p * exp_m - self.beta_m * exp_p) / delta_beta)

        # Add homogeneous solution for nonzero initial conditions
        if m0 != 0.0 or p0 != 0.0:
            # Contribution from m0 ≠ 0
            (m0 - self.m_ss) * exp_m
            p_from_m0 = self.alpha_p * (m0 - self.m_ss) / delta_beta * (exp_p - exp_m)
            p_particular = p_particular + p_from_m0 + p0 * exp_p
            # Remove the p0=0 assumption baked into p_particular
            # (p_particular already assumes p0=0, so just add p0*exp_p)

        return p_particular
