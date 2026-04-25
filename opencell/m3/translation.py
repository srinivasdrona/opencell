"""M3 - Karr-native translation module (v1: prescribed-rates).

Loads Karr's fitted protein-monomer state from a committed fixture
extracted by `scripts/karr_native_ingest_m3.py`.

This is **M3 v1**, mirroring the M2 pattern:  482 mature protein
monomers evolve by linear ODE

    dN_i/dt = s_i - k_i * N_i

where k_i is Karr's per-second decay rate (computed from halfLife in
seconds; 119 essential proteins have halfLife=inf -> k=0 -> linear
accumulation) and s_i = N_i^ss * k_i is Karr's prescribed steady-state
synthesis rate (by the same fitting convention as M2).  Round-trips to
counts_mature by construction; the v1 oracle is therefore numerical
correctness + extraction sanity, not independent biology.

**M3 v2** (deferred) will derive s_i from ribosome counts x mRNA_i x
elongation rate / length_i and validate against Karr's fitted s_i.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "karr_native_m3.json"
)


@dataclass
class KarrTranslationModel:
    protein_wcm_ids: list[str]
    gene_wcm_ids: list[str]
    compartment_wcm_ids: list[str]
    length_aa: np.ndarray
    half_life_s: np.ndarray
    decay_rate_per_s: np.ndarray
    molecular_weight: np.ndarray
    counts_mature: np.ndarray
    synth_rate_per_s: np.ndarray
    base_counts: np.ndarray
    elongation_rate_aa_per_s: float
    tmrna_binding_probability: float
    counts_meta: dict
    raw: dict = field(repr=False)

    @property
    def n_proteins(self) -> int:
        return len(self.protein_wcm_ids)

    @property
    def immortal_mask(self) -> np.ndarray:
        return np.isinf(self.half_life_s)

    def protein_index(self, wcm_id: str) -> int:
        return self.protein_wcm_ids.index(wcm_id)


def load_default(path: str | Path | None = None) -> KarrTranslationModel:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    meta = json.loads(p.read_text())
    z = np.load(p.parent / Path(meta["matrix_npz"]).name)
    return KarrTranslationModel(
        protein_wcm_ids=list(meta["ids"]["protein_wcm_482"]),
        gene_wcm_ids=list(meta["ids"]["gene_wcm_482"]),
        compartment_wcm_ids=list(meta["ids"]["compartment_wcm_482"]),
        length_aa=z["length_aa"],
        half_life_s=z["half_life_s"],
        decay_rate_per_s=z["decay_rate_per_s"],
        molecular_weight=z["molecular_weight"],
        counts_mature=z["counts_mature"],
        synth_rate_per_s=z["synth_rate_per_s"],
        base_counts=z["base_counts"],
        elongation_rate_aa_per_s=float(meta["scalars"][
            "ribosome_elongation_rate_aa_per_s"
        ]),
        tmrna_binding_probability=float(meta["scalars"][
            "tmrna_binding_probability"
        ]),
        counts_meta=dict(meta["counts"]),
        raw=meta,
    )


def step_analytical(
    model: KarrTranslationModel,
    protein_counts: np.ndarray,
    dt_s: float,
) -> np.ndarray:
    """Closed-form integration of dN/dt = s - k*N over dt_s seconds.

    For genes with k>0:  N(t+dt) = N_ss + (N(t)-N_ss)*exp(-k*dt) where
    N_ss = s/k.  For k=0 (immortal essentials): N(t+dt) = N(t) + s*dt.
    """
    n = np.asarray(protein_counts, dtype=float).reshape(-1).copy()
    if n.size != model.n_proteins:
        raise ValueError(
            f"protein_counts length {n.size} != n_proteins {model.n_proteins}")

    s = model.synth_rate_per_s
    k = model.decay_rate_per_s

    out = np.empty_like(n)
    no_decay = (k <= 0.0)
    if np.any(~no_decay):
        idx = ~no_decay
        ss = s[idx] / k[idx]
        out[idx] = ss + (n[idx] - ss) * np.exp(-k[idx] * dt_s)
    if np.any(no_decay):
        out[no_decay] = n[no_decay] + s[no_decay] * dt_s

    return out


def aa_consumption_per_s(model: KarrTranslationModel) -> dict[str, float]:
    """Total amino-acid consumption per second under the prescribed
    synthesis rates.  Returns a single bulk total plus a placeholder
    20-AA breakdown derived from base_counts (Karr's per-monomer AA
    composition) summed over proteins weighted by synthesis rate.
    """
    total_aa_per_s = float(np.sum(model.synth_rate_per_s * model.length_aa))
    # base_counts is (482, 722); weight rows by synth rate, sum -> (722,)
    per_metabolite = (model.synth_rate_per_s[:, None] * model.base_counts).sum(axis=0)
    return {
        "_total_aa_per_s": total_aa_per_s,
        "_per_metabolite_per_s_722": per_metabolite,
    }
