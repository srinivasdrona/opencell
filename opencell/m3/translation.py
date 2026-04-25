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
DEFAULT_VOCAB_JSON = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "karr_native_m3_vocab.json"
)

# 20 standard amino acids in canonical order (Karr's aminoAcidIndexs[:20]).
# This is the order returned by `aa_consumption_per_s` and mirrored in the
# M3 Vivarium wrapper schema.  FMET is excluded; M1's substrate vocabulary
# does carry FMET separately but central-dogma chassis treats FMET demand
# as MET (initiator-methionine consumption is one-per-protein-per-synth).
AA_WCM_IDS: tuple[str, ...] = (
    "ALA", "ARG", "ASN", "ASP", "CYS",
    "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO",
    "SER", "THR", "TRP", "TYR", "VAL",
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
    aa_wcm_ids: tuple[str, ...]
    aa_col_indices: np.ndarray
    raw: dict = field(repr=False)

    @property
    def n_proteins(self) -> int:
        return len(self.protein_wcm_ids)

    @property
    def immortal_mask(self) -> np.ndarray:
        return np.isinf(self.half_life_s)

    def protein_index(self, wcm_id: str) -> int:
        return self.protein_wcm_ids.index(wcm_id)


def _load_aa_vocab(vocab_path: Path) -> tuple[tuple[str, ...], np.ndarray]:
    """Resolve the 20 standard-AA column indices into base_counts (482, 722).

    Returns (aa_wcm_ids, col_indices) ordered as :data:`AA_WCM_IDS`.  When
    the side-car vocab JSON is missing we fall back to ``AA_WCM_IDS`` with
    placeholder col indices = -1, so callers must guard.  Phase C requires
    the vocab JSON; we raise rather than silently degrade.
    """
    if not vocab_path.exists():
        raise FileNotFoundError(
            f"M3 amino-acid vocab JSON missing: {vocab_path}.  Run "
            "`scripts/extract_m3_metabolite_vocab.py` (or rerun the MATLAB "
            "extractor) to regenerate."
        )
    vocab = json.loads(vocab_path.read_text())
    full_aa_ids = list(vocab["aa_wcm_ids"])
    full_aa_idx = list(vocab["aminoAcidIndexs_0based"])
    name_to_col = dict(zip(full_aa_ids, full_aa_idx))
    cols = np.array([name_to_col[aa] for aa in AA_WCM_IDS], dtype=int)
    return AA_WCM_IDS, cols


def load_default(
    path: str | Path | None = None,
    vocab_path: str | Path | None = None,
) -> KarrTranslationModel:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    vp = Path(vocab_path) if vocab_path is not None else DEFAULT_VOCAB_JSON
    meta = json.loads(p.read_text())
    z = np.load(p.parent / Path(meta["matrix_npz"]).name)
    aa_ids, aa_cols = _load_aa_vocab(vp)
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
        aa_wcm_ids=aa_ids,
        aa_col_indices=aa_cols,
        raw=meta,
    )


def step_analytical(
    model: KarrTranslationModel,
    protein_counts: np.ndarray,
    dt_s: float,
    synth_scale: float = 1.0,
) -> np.ndarray:
    """Closed-form integration of dN/dt = s - k*N over dt_s seconds.

    For genes with k>0:  N(t+dt) = N_ss + (N(t)-N_ss)*exp(-k*dt) where
    N_ss = s/k.  For k=0 (immortal essentials): N(t+dt) = N(t) + s*dt.

    ``synth_scale`` (default 1.0) multiplies the prescribed synthesis
    rate ``s`` uniformly, intended for substrate-aware throttling of
    the integrator from the Vivarium chassis.  Throttling is OFF when
    scale==1.0; scale==0.0 freezes synthesis.
    """
    n = np.asarray(protein_counts, dtype=float).reshape(-1).copy()
    if n.size != model.n_proteins:
        raise ValueError(
            f"protein_counts length {n.size} != n_proteins {model.n_proteins}")

    s = model.synth_rate_per_s * float(synth_scale)
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


def aa_consumption_per_s(
    model: KarrTranslationModel,
    synth_scale: float = 1.0,
) -> dict:
    """Amino-acid consumption per second under the prescribed synthesis rates.

    Returns a dict containing:
      * one entry per WCM ID in :data:`AA_WCM_IDS` (20 floats), the
        per-AA consumption rate in molecules/s computed from
        ``base_counts[:, aa_col]`` weighted by ``synth_rate_per_s``;
      * ``_total_aa_per_s`` -- bulk total residues/s (= ``Sum_i s_i * length_i``);
      * ``_per_metabolite_per_s_722`` -- the full 722-vector for callers
        that need to wire in non-AA metabolite demand later.

    ``synth_scale`` (default 1.0) scales every entry uniformly.
    """
    s = model.synth_rate_per_s * float(synth_scale)
    total_aa_per_s = float(np.sum(s * model.length_aa))
    per_metabolite = (s[:, None] * model.base_counts).sum(axis=0)

    out: dict = {
        aa: float(per_metabolite[col])
        for aa, col in zip(model.aa_wcm_ids, model.aa_col_indices)
    }
    out["_total_aa_per_s"] = total_aa_per_s
    out["_per_metabolite_per_s_722"] = per_metabolite
    return out

