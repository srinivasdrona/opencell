"""M2 v2 - mechanism-based transcription rate prediction.

Independent oracle on M2 v1's prescribed synthesis rates.  Where v1
takes Karr's fitted ``synthesisRate`` verbatim and round-trips by
construction, v2 derives per-TU production rates from first principles
using

    synth_TU_j (per s) = N_active * elongation_rate * P_bind_j
                        / sum_k(P_bind_k * length_k)

(see ``Transcription.m::evolveState`` and
``computeRNAPolymeraseTUBindingProbabilities``).  Each TU-completion
produces one copy of every gene in the operon; per-gene rates follow
from the 525x335 TU-gene incidence.

The runtime binding probability is the fitted ``P_bind`` modulated by
two per-TU fold changes, both available in the snapshot:

    P_runtime_j = P_bind_j * tfFoldChange_j * supercoilingFoldChange_j

For M.g almost all TF fold changes are 1.0 (only the
transcription-factor-controlled operons differ), so the bare and
modulated predictions agree to within 0.1 log2 unit on the median.

Snapshot vs cell-cycle averaging
--------------------------------
Karr's fitted ``synthesisRate`` is fit to ``expression * decayRate`` at
the population/time-averaged steady state.  The simulation snapshot has
``N_active=35`` polymerases; over a cell cycle the count grows from N
to 2N, so the cell-cycle-averaged active count is roughly ``1.5 * N`` to
``2 * N``.  With the snapshot N_active, the mechanism predicts about
half of Karr's fitted rates (median log2 ratio = -0.91, |log2| = 1.49);
multiplying by 2 brings the agreement to median = +0.09, |log2| = 0.99,
in the same ballpark as M1's per-reaction oracle (0.96).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "karr_native_m2_v2.json"
)


@dataclass
class MechanismInputs:
    """Per-TU mechanism inputs from Karr's snapshot."""

    tu_wcm_ids: list[str]
    gene_wcm_ids: list[str]
    tu_lengths_nt: np.ndarray  # (n_tu,)
    p_bind_bare: np.ndarray  # (n_tu,) Karr's fittedConstants
    tu_gene_incidence: np.ndarray  # (n_tu, n_genes) int8 0/1
    elongation_rate_nt_per_s: float
    n_active_rnap: int  # snapshot
    n_total_rnap: int  # snapshot
    rnap_state_expectations: np.ndarray  # (4,) [active, specBound, nonSpec, free]
    karr_fitted_synth_per_s: np.ndarray  # (n_genes,) gene-level oracle target
    raw: dict = field(repr=False)

    @property
    def n_tu(self) -> int:
        return self.tu_lengths_nt.size

    @property
    def n_genes(self) -> int:
        return self.tu_gene_incidence.shape[1]


def load_default(path: str | Path | None = None) -> MechanismInputs:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    meta = json.loads(p.read_text())
    z = np.load(p.parent / Path(meta["matrix_npz"]).name)
    sc = meta["scalars"]
    karr = np.nan_to_num(z["synth_gene_per_s_karr"], nan=0.0)
    return MechanismInputs(
        tu_wcm_ids=list(meta["ids"]["tu_wcm_335"]),
        gene_wcm_ids=list(meta["ids"]["gene_wcm_525"]),
        tu_lengths_nt=z["tu_lengths"].astype(float),
        p_bind_bare=z["tu_binding_probabilities"].astype(float),
        tu_gene_incidence=z["tu_gene_incidence"].astype(np.int8),
        elongation_rate_nt_per_s=float(sc["rna_polymerase_elongation_rate_nt_per_s"]),
        n_active_rnap=int(sc["n_active_rnap"]),
        n_total_rnap=int(sc["n_total_rnap"]),
        rnap_state_expectations=z["rnap_state_expectations"].astype(float),
        karr_fitted_synth_per_s=karr,
        raw=meta,
    )


def predict_tu_synthesis_per_s(
    inputs: MechanismInputs,
    n_active: int | float | None = None,
    p_bind: np.ndarray | None = None,
) -> np.ndarray:
    """Return predicted per-TU synthesis rate (per second).

    ``synth_TU_j = N_active * elong * P_bind_j / sum_k(P_bind_k * length_k)``

    By default uses snapshot ``N_active`` and bare ``P_bind`` from the
    fixture; pass overrides to explore modulation (TF fold-change,
    supercoiling) or cell-cycle averaging.
    """
    n = inputs.n_active_rnap if n_active is None else float(n_active)
    pb = inputs.p_bind_bare if p_bind is None else np.asarray(p_bind, dtype=float)
    if pb.size != inputs.n_tu:
        raise ValueError(f"p_bind size {pb.size} != n_tu {inputs.n_tu}")
    denom = float(np.sum(pb * inputs.tu_lengths_nt))
    if denom <= 0.0:
        raise ValueError("denominator sum(P_bind * length) is non-positive")
    return n * inputs.elongation_rate_nt_per_s * pb / denom


def predict_gene_synthesis_per_s(
    inputs: MechanismInputs,
    n_active: int | float | None = None,
    p_bind: np.ndarray | None = None,
) -> np.ndarray:
    """Project per-TU rates onto genes via the operon incidence matrix."""
    tu_rate = predict_tu_synthesis_per_s(inputs, n_active=n_active, p_bind=p_bind)
    return tu_rate @ inputs.tu_gene_incidence  # (n_genes,)


def total_nt_polymerization_per_s(
    inputs: MechanismInputs,
    n_active: int | float | None = None,
) -> float:
    """Sanity invariant: sum_j(synth_TU_j * length_j) == N_active * elongation."""
    tu_rate = predict_tu_synthesis_per_s(inputs, n_active=n_active)
    return float(np.sum(tu_rate * inputs.tu_lengths_nt))


def compare_to_karr(
    predicted_gene_per_s: np.ndarray,
    karr_fitted_per_s: np.ndarray,
) -> dict:
    """Summarise agreement between mechanism and Karr's fitted rates.

    Compares only on genes where both are positive and finite.
    """
    pred = np.asarray(predicted_gene_per_s, dtype=float)
    karr = np.asarray(karr_fitted_per_s, dtype=float)
    valid = np.isfinite(pred) & np.isfinite(karr) & (pred > 0) & (karr > 0)
    if not np.any(valid):
        raise ValueError("no genes with both rates positive")
    log2r = np.log2(pred[valid] / karr[valid])
    return {
        "n_compared": int(valid.sum()),
        "median_log2_ratio": float(np.median(log2r)),
        "mean_log2_ratio": float(np.mean(log2r)),
        "std_log2_ratio": float(np.std(log2r)),
        "median_abs_log2_ratio": float(np.median(np.abs(log2r))),
        "p10_log2_ratio": float(np.percentile(log2r, 10)),
        "p90_log2_ratio": float(np.percentile(log2r, 90)),
        "total_predicted_per_s": float(np.sum(pred)),
        "total_karr_per_s": float(np.nansum(karr)),
    }
