"""M3 v2 - mechanism-based translation rate prediction.

Mirrors `opencell.m2.transcription_v2` for the ribosome side.  Per
Karr's `Translation.m::evolveState` (line 665 ``bndProbs = this.mRNAs``)
ribosomes pick mRNAs proportional to copy count, which drops out to

    synth_protein_i = N_active_ribo * elong_aa_per_s * mRNA_i
                    / sum_k(mRNA_k * length_k)

and

    Sum_i (synth_protein_i * length_i) == N_active_ribo * elong_aa_per_s

(the conservation invariant: every active ribosome polymerizes
``elong_aa_per_s`` amino acids per second).

Discovered while building this module
-------------------------------------
The M3 v1 fixture's ``synth_rate_per_s`` (= ``counts_mature * decay``)
is **NOT a complete per-protein production rate** — it only balances
decay loss for mortal proteins.  In particular:

* 119/482 proteins are immortal (halfLife = inf), so their v1 synth = 0.
  In a growing cell these still need synth = N * growth_rate to dilute.
* Volume dilution from cell growth is ignored in the v1 framework.
* The snapshot N_active = 56 ribosomes deliver 896 aa/s (= 56 * 16),
  while v1's total fitted rate is only 38.9 aa/s = sum(synth_v1 * len)
  (a ~23x gap).  Roughly 150 aa/s is needed just to double 5M aa of
  protein content in a 9-hour cell cycle, so the v1 figure undershoots
  even the bare minimum doubling rate.

For this reason the v2 oracle here does NOT test per-protein agreement
with the v1 numbers.  Instead it tests:

* Conservation invariant (total aa polymerization = N * k).
* Linear scaling with N_active.
* Mechanism prediction sits in a physiologically sensible range
  (1.5-50x the v1 total; the v1 number is a hard lower bound but not a
  precise oracle).
* Cross-consistency: the snapshot N_active matches the snapshot count of
  ribosomes bound to mRNAs in ``State_Ribosome`` (sanity check on the
  inputs themselves).

The full closure -- mechanism rate vs *cell-cycle-averaged* per-protein
production -- requires substrate writeback + mRNA dynamics + immortal
dilution, which is the M5 / cell-cycle work, not v2.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "karr_native_m3_v2.json"
)


@dataclass
class RibosomeMechanismInputs:
    mrna_counts: np.ndarray              # (n_proteins,) snapshot mRNA copies
    length_aa: np.ndarray                # (n_proteins,) aa per protein
    n_active_ribosomes: int              # snapshot
    n_total_ribosomes: int               # snapshot (active + stalled + notExist)
    elongation_rate_aa_per_s: float
    ribosome_state_occupancies: np.ndarray  # (3,) [active, notExist, stalled]
    n_ribosomes_bound_per_mrna: np.ndarray  # (n_proteins,) snapshot
    karr_v1_synth_per_s: np.ndarray      # (n_proteins,) decay-balanced lower bound
    raw: dict = field(repr=False)

    @property
    def n_proteins(self) -> int:
        return self.length_aa.size


def load_default(path: str | Path | None = None) -> RibosomeMechanismInputs:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    meta = json.loads(p.read_text())
    z = np.load(p.parent / Path(meta["matrix_npz"]).name)
    sc = meta["scalars"]
    return RibosomeMechanismInputs(
        mrna_counts=z["mrna_counts"].astype(float),
        length_aa=z["length_aa"].astype(float),
        n_active_ribosomes=int(sc["n_active_ribosomes"]),
        n_total_ribosomes=int(sc["n_total_ribosomes"]),
        elongation_rate_aa_per_s=float(sc["ribosome_elongation_rate_aa_per_s"]),
        ribosome_state_occupancies=z["ribosome_state_occupancies"].astype(float),
        n_ribosomes_bound_per_mrna=z["n_ribosomes_bound_per_mrna"].astype(int),
        karr_v1_synth_per_s=z["synth_karr_per_s"].astype(float),
        raw=meta,
    )


def predict_synthesis_per_s(
    inputs: RibosomeMechanismInputs,
    n_active: int | float | None = None,
    mrna_counts: np.ndarray | None = None,
) -> np.ndarray:
    """Per-protein production rate in proteins/sec.

    ``synth_i = N_active * elong * mRNA_i / sum_k(mRNA_k * length_k)``
    """
    n = inputs.n_active_ribosomes if n_active is None else float(n_active)
    m = inputs.mrna_counts if mrna_counts is None else np.asarray(mrna_counts, dtype=float)
    if m.size != inputs.n_proteins:
        raise ValueError(f"mrna_counts size {m.size} != n_proteins {inputs.n_proteins}")
    denom = float(np.sum(m * inputs.length_aa))
    if denom <= 0.0:
        return np.zeros_like(inputs.length_aa)
    return n * inputs.elongation_rate_aa_per_s * m / denom


def total_aa_polymerization_per_s(
    inputs: RibosomeMechanismInputs,
    n_active: int | float | None = None,
) -> float:
    """Conservation invariant: total aa/s == N_active * elongation_rate."""
    synth = predict_synthesis_per_s(inputs, n_active=n_active)
    return float(np.sum(synth * inputs.length_aa))


def fraction_active_from_occupancies(inputs: RibosomeMechanismInputs) -> float:
    """Snapshot fraction of allocated ribosomes that are active."""
    occ = inputs.ribosome_state_occupancies
    return float(occ[0])
