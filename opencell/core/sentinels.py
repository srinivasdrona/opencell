"""Order-of-magnitude sentinels for OpenCell.

Defines broad expected ranges for key biological variables.
Catches 10x/1000x mistakes from unit errors, exponent slips,
or hallucinated parameters. Ranges are intentionally loose —
catch nonsense, not constrain science.

Sources: General microbiology textbooks + Karr 2012.
Ranges are APPROXIMATE — refine as we learn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SentinelRange:
    """Expected order-of-magnitude range for a variable.

    Attributes:
        name: Variable name
        min_val: Lower bound (inclusive)
        max_val: Upper bound (inclusive)
        unit: Unit string (for display)
        source: Where this range comes from
    """

    name: str
    min_val: float
    max_val: float
    unit: str
    source: str = "general microbiology"


# Default sentinel ranges for bacterial cell simulation
BACTERIAL_SENTINELS: dict[str, SentinelRange] = {
    "cell_volume_fL": SentinelRange(
        "cell_volume",
        0.01,
        10.0,
        "fL",
        "M. genitalium ~0.07 fL, E. coli ~1 fL",
    ),
    "atp_concentration_mM": SentinelRange(
        "ATP concentration",
        0.1,
        20.0,
        "mM",
        "typical bacterial: 1-10 mM",
    ),
    "ribosome_count": SentinelRange(
        "ribosomes per cell",
        100,
        100_000,
        "copies",
        "M. genitalium ~500, E. coli ~20,000-70,000",
    ),
    "mrna_per_gene": SentinelRange(
        "mRNA copies per gene",
        0.01,
        100,
        "copies",
        "most genes: 0.1-10 copies; highly expressed: up to ~50",
    ),
    "protein_per_gene": SentinelRange(
        "protein copies per gene",
        1,
        1_000_000,
        "copies",
        "range: ~10 to ~100,000 typical",
    ),
    "doubling_time_min": SentinelRange(
        "doubling time",
        20,
        2000,
        "minutes",
        "E. coli ~20 min, M. genitalium ~720 min (12 hr)",
    ),
    "transcription_rate_nt_per_s": SentinelRange(
        "transcription elongation rate",
        10,
        100,
        "nt/s",
        "bacterial RNAP: ~30-80 nt/s",
    ),
    "translation_rate_aa_per_s": SentinelRange(
        "translation elongation rate",
        5,
        25,
        "aa/s",
        "bacterial ribosome: ~10-20 aa/s",
    ),
    "growth_rate_per_hr": SentinelRange(
        "growth rate",
        0.01,
        3.0,
        "1/hr",
        "M. genitalium ~0.08, E. coli ~2.0",
    ),
    "metabolic_flux_mmol_gDW_hr": SentinelRange(
        "metabolic flux",
        0.001,
        100,
        "mmol/gDW/hr",
        "glucose uptake E. coli ~10, most fluxes 0.01-50",
    ),
}


def check_sentinel(
    name: str,
    value: float,
    sentinels: dict[str, SentinelRange] | None = None,
) -> str | None:
    """Check a value against its sentinel range.

    Returns None if OK, or a warning string if out of range.
    """
    if sentinels is None:
        sentinels = BACTERIAL_SENTINELS

    if name not in sentinels:
        return None

    s = sentinels[name]
    if value < s.min_val or value > s.max_val:
        msg = (
            f"SENTINEL WARNING: {s.name} = {value:.4g} {s.unit} "
            f"is outside expected range [{s.min_val}, {s.max_val}]. "
            f"Source: {s.source}"
        )
        logger.warning(msg)
        return msg
    return None


def check_all_sentinels(
    values: dict[str, float],
    sentinels: dict[str, SentinelRange] | None = None,
) -> list[str]:
    """Check multiple values against sentinel ranges.

    Returns list of warning messages (empty if all OK).
    """
    warnings = []
    for name, value in values.items():
        msg = check_sentinel(name, value, sentinels)
        if msg is not None:
            warnings.append(msg)
    return warnings
