"""M2 - Karr-native transcription module.

Loads Karr's prescribed transcription rates (synthesisRate, halfLife)
plus per-TU binding probabilities and the polymerase elongation rate
from a committed fixture extracted by `scripts/karr_native_ingest_m2.py`.

This is **M2 v1**: a Karr-prescribed-rates module that tracks 525 RNA
species evolving by linear ODE

    dRNA_i/dt = s_i - k_i * RNA_i

where s_i and k_i = ln(2)/halfLife_i are taken verbatim from Karr's
WCKB.  At steady state RNA_ss = s/k = expression by construction
(Karr fits s to make this hold).  The oracle is therefore
**numerical-correctness** (round-trip + integrator), not independent
biology.

**M2 v2** (deferred) will derive s_i from first principles using
RNA polymerase counts, transcriptionUnitBindingProbabilities, and the
elongation rate, then compare against Karr's fitted s_i as an
independent oracle.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "karr_native_m2.json"
)


@dataclass
class KarrTranscriptionModel:
    gene_wcm_ids: list[str]
    gene_symbols: list[str]
    gene_types: list[str]
    half_life_min: np.ndarray
    decay_rate_per_min: np.ndarray
    decay_rate_per_s: np.ndarray
    length_nt: np.ndarray
    expression: np.ndarray
    synthesis_rate_per_min: np.ndarray
    synthesis_rate_per_s: np.ndarray
    rna_ss_predicted: np.ndarray
    tu_binding_probabilities: np.ndarray
    elongation_rate_nt_per_s: float
    counts: dict
    raw: dict = field(repr=False)

    @property
    def n_genes(self) -> int:
        return len(self.gene_wcm_ids)

    @property
    def mrna_mask(self) -> np.ndarray:
        return np.array([t == "mRNA" for t in self.gene_types], dtype=bool)

    def gene_index(self, wcm_id: str) -> int:
        return self.gene_wcm_ids.index(wcm_id)


def load_default(path: str | Path | None = None) -> KarrTranscriptionModel:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    meta = json.loads(p.read_text())
    z = np.load(p.parent / Path(meta["matrix_npz"]).name)
    # Sanitize: 3 mRNA rows (134, 323, 502) have halfLife=0 + expr=0,
    # producing 0/0 = NaN in synthesis_rate.  Treat as no-synthesis.
    syn_min = np.nan_to_num(z["synthesis_rate_per_min"], nan=0.0)
    syn_s = np.nan_to_num(z["synthesis_rate_per_s"], nan=0.0)
    return KarrTranscriptionModel(
        gene_wcm_ids=list(meta["ids"]["gene_wcm_525"]),
        gene_symbols=list(meta["ids"]["gene_symbols_525"]),
        gene_types=list(meta["ids"]["gene_types_525"]),
        half_life_min=z["half_life_min"],
        decay_rate_per_min=z["decay_rate_per_min"],
        decay_rate_per_s=z["decay_rate_per_s"],
        length_nt=z["length_nt"],
        expression=z["expression"],
        synthesis_rate_per_min=syn_min,
        synthesis_rate_per_s=syn_s,
        rna_ss_predicted=z["rna_ss_predicted"],
        tu_binding_probabilities=z["tu_binding_probabilities"],
        elongation_rate_nt_per_s=float(meta["scalars"][
            "rna_polymerase_elongation_rate_nt_per_s"
        ]),
        counts=dict(meta["counts"]),
        raw=meta,
    )


def step_analytical(
    model: KarrTranscriptionModel,
    rna_counts: np.ndarray,
    dt_s: float,
    condition: int = 1,
    synth_scale: float = 1.0,
) -> np.ndarray:
    """Closed-form integration of dRNA/dt = s - k*RNA over dt_s seconds.

    Linear first-order ODE has the analytical solution

        RNA(t+dt) = RNA_ss + (RNA(t) - RNA_ss) * exp(-k*dt)

    where RNA_ss = s/k.  Genes with k=0 (no decay) integrate as
    RNA(t+dt) = RNA(t) + s*dt.  `condition` selects which expression
    column [0=low, 1=mean, 2=high] of `synthesis_rate_per_s` to use.

    ``synth_scale`` (default 1.0) multiplies the prescribed synthesis
    rate uniformly, intended for substrate-aware throttling of the
    integrator from the Vivarium chassis.  scale==0.0 freezes synthesis.
    """
    rna = np.asarray(rna_counts, dtype=float).reshape(-1).copy()
    if rna.size != model.n_genes:
        raise ValueError(
            f"rna_counts length {rna.size} != n_genes {model.n_genes}")

    s_per_s = model.synthesis_rate_per_s[:, condition] * float(synth_scale)
    k_per_s = model.decay_rate_per_s

    out = np.empty_like(rna)
    no_decay = (k_per_s <= 0.0)
    if np.any(~no_decay):
        idx = ~no_decay
        ss = s_per_s[idx] / k_per_s[idx]
        out[idx] = ss + (rna[idx] - ss) * np.exp(-k_per_s[idx] * dt_s)
    if np.any(no_decay):
        out[no_decay] = rna[no_decay] + s_per_s[no_decay] * dt_s

    return out


def ntp_consumption_per_s(
    model: KarrTranscriptionModel,
    condition: int = 1,
    synth_scale: float = 1.0,
) -> dict[str, float]:
    """Total NTP consumption per second under the prescribed rates,
    assuming uniform 1/4 base composition (real composition is M2 v2)."""
    s_per_s = model.synthesis_rate_per_s[:, condition] * float(synth_scale)
    total_nt_per_s = float(np.sum(s_per_s * model.length_nt))
    per_ntp = total_nt_per_s / 4.0
    return {
        "ATP": per_ntp,
        "CTP": per_ntp,
        "GTP": per_ntp,
        "UTP": per_ntp,
        "_total_nt_per_s": total_nt_per_s,
    }
