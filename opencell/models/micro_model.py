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


@dataclass(frozen=True)
class MicroModelParams:
    """Parameters for constitutive gene expression in E. coli.

    Source: Thattai & van Oudenaarden (2001), Table 1 / Figure 2 legend.
    DOI: 10.1073/pnas.151588598
    All rates in min⁻¹ as stated in paper: "All rates in units of min⁻¹".

    Verification status: UNVERIFIED_WEB — values obtained via web search
    of paper content, not human-verified against PDF. See
    docs/biology/micro_model_derivation.md for full provenance.

    k₁ has three values in the paper (0.15, 0.30, 0.60); we use 0.30
    (the middle value) as default.
    """

    alpha_m: float = 0.30   # k₁: Transcription rate (mRNA/min) [Table 1: 0.15/0.30/0.60]
    beta_m: float = 0.023   # γ₁: mRNA degradation rate (1/min) [Table 1 / Fig 2 legend]
    alpha_p: float = 5.0    # k₂: Translation rate per transcript (protein/mRNA/min) [Table 1]
    beta_p: float = 0.10    # γ₂: Protein degradation+dilution rate (1/min) [Table 1]

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

    def p_exact(self, t: float | np.ndarray, m0: float = 0.0, p0: float = 0.0) -> float | np.ndarray:
        """Exact analytical protein time course (Alon Box 1.1).

        For m0=0, p0=0, β_m ≠ β_p:
        p(t) = (α_m·α_p)/(β_m·β_p) · [1 + (β_p·e^(-β_m·t) - β_m·e^(-β_p·t))/(β_m - β_p)]
        """
        exp_m = np.exp(-self.beta_m * t)
        exp_p = np.exp(-self.beta_p * t)
        p_ss = self.p_ss
        delta_beta = self.beta_m - self.beta_p

        # Alon (2006) Box 1.1 exact solution
        p_particular = p_ss * (
            1 + (self.beta_p * exp_m - self.beta_m * exp_p) / delta_beta
        )

        # Add homogeneous solution for nonzero initial conditions
        if m0 != 0.0 or p0 != 0.0:
            # Contribution from m0 ≠ 0
            m_homo = (m0 - self.m_ss) * exp_m
            p_from_m0 = self.alpha_p * (m0 - self.m_ss) / delta_beta * (exp_p - exp_m)
            p_particular = p_particular + p_from_m0 + p0 * exp_p
            # Remove the p0=0 assumption baked into p_particular
            # (p_particular already assumes p0=0, so just add p0*exp_p)

        return p_particular
