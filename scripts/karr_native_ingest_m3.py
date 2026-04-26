"""Extract Karr's translation/protein data into a committed fixture.

Reads `data/m1_sources/karr_flat/proteins_targeted.mat` (gitignored)
and writes:
  - data/karr_fixtures/karr_native_m3.json  (metadata + ID strings)
  - data/karr_fixtures/karr_native_m3.npz   (numeric arrays)

Sole runtime dependency of `opencell.m3.translation`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from opencell._karr_archive import load_karr_archive  # noqa: E402

OUT_DIR = REPO / "data" / "karr_fixtures"
JSON_OUT = OUT_DIR / "karr_native_m3.json"
NPZ_OUT = OUT_DIR / "karr_native_m3.npz"

SCHEMA_VERSION = "karr_native_m3__v1"


def _scalar(x) -> float:
    return float(np.asarray(x).item())


def main() -> None:
    arc = load_karr_archive()
    d = arc["proteins_targeted"]

    # 482 mature-indexs into the 4820-vec (state forms x species).
    mature_idx_1 = np.asarray(d.matureIndexs, dtype=int).reshape(-1)
    n_proteins = mature_idx_1.size
    assert n_proteins == 482, n_proteins
    midx = mature_idx_1 - 1  # MATLAB->Python

    lengths_4820 = np.asarray(d.lengths, dtype=float).reshape(-1)
    half_lives_4820 = np.asarray(d.halfLives, dtype=float).reshape(-1)
    decay_rates_4820 = np.asarray(d.decayRates, dtype=float).reshape(-1)
    mol_w_4820 = np.asarray(d.molecularWeights, dtype=float).reshape(-1)
    compartments_4820 = np.asarray(d.compartments, dtype=int).reshape(-1)
    counts_4820 = np.asarray(d.counts, dtype=float)
    base_counts_4820 = np.asarray(d.baseCounts, dtype=float)

    # Slice to mature
    length_aa = lengths_4820[midx].astype(np.int32)
    half_life_s = half_lives_4820[midx]      # seconds; inf for non-decayed
    decay_rate_per_s = decay_rates_4820[midx]
    molecular_weight = mol_w_4820[midx]
    compartment = compartments_4820[midx]
    counts_mature = counts_4820[midx, 0]      # column 0 = mature initial counts
    base_counts = base_counts_4820[midx, :]   # (482, 722) - per-monomer base composition

    # Synthesis rate at steady state: dN/dt = s - k*N = 0  =>  s = k*N
    synth_rate_per_s = counts_mature * decay_rate_per_s

    wcm_ids = [str(x) for x in d.kb_wholeCellModelIDs]
    gene_wcm_ids = [str(x) for x in d.kb_geneWholeCellModelIDs]
    comp_wcm_ids = [str(x) for x in d.kb_compartmentWholeCellModelIDs]

    elongation_rate_aa_per_s = _scalar(d.translation_ribosomeElongationRate)
    tmrna_binding = _scalar(d.translation_tmRNABindingProbability)

    # Compartment WCM-ID histogram (sanity)
    comp_hist: dict[str, int] = {}
    for c in comp_wcm_ids:
        comp_hist[c] = comp_hist.get(c, 0) + 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        NPZ_OUT,
        mature_index_4820=mature_idx_1,
        length_aa=length_aa,
        half_life_s=half_life_s,
        decay_rate_per_s=decay_rate_per_s,
        molecular_weight=molecular_weight,
        compartment_index=compartment,
        counts_mature=counts_mature,
        synth_rate_per_s=synth_rate_per_s,
        base_counts=base_counts,
    )

    JSON_OUT.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "source_archive": "data/karr_archive/",
        "source_archive_files": ["proteins_targeted"],
        "matrix_npz": str(NPZ_OUT.relative_to(REPO)),
        "counts": {
            "n_proteins": n_proteins,
            "n_immortal_halflife_inf": int(np.isinf(half_life_s).sum()),
            "n_zero_initial_count": int((counts_mature == 0).sum()),
            "compartment_histogram": comp_hist,
        },
        "scalars": {
            "ribosome_elongation_rate_aa_per_s": elongation_rate_aa_per_s,
            "tmrna_binding_probability": tmrna_binding,
            "total_mature_counts": float(counts_mature.sum()),
            "total_synth_rate_per_s_at_ss": float(synth_rate_per_s.sum()),
            "total_aa_polymerization_per_s_at_ss": float(
                np.sum(synth_rate_per_s * length_aa)),
        },
        "ids": {
            "protein_wcm_482": wcm_ids,
            "gene_wcm_482": gene_wcm_ids,
            "compartment_wcm_482": comp_wcm_ids,
        },
        "shapes": {
            "length_aa": list(length_aa.shape),
            "half_life_s": list(half_life_s.shape),
            "counts_mature": list(counts_mature.shape),
            "base_counts": list(base_counts.shape),
        },
        "interpretation": (
            "Karr-native M3 translation fixture. 482 protein monomers "
            "extracted from sim.state.ProteinMonomer with the matureIndexs "
            "slice (each species has 10 maturation forms; only mature is "
            "tracked here). halfLife is in SECONDS (inf for non-decayed "
            "essential proteins, mapped to decay_rate=0). counts_mature is "
            "Karr's fitted initial count for the mature form. "
            "synth_rate_per_s = counts_mature * decay_rate_per_s by Karr's "
            "fitting convention (dN/dt = s - k*N = 0 at steady state). "
            "Ribosome elongation rate = 16 aa/s. base_counts is per-monomer "
            "composition over Karr's 722 metabolite vocabulary (rows=mature "
            "monomers, cols=metabolites; non-zero where AA is consumed in "
            "polymerization)."
        ),
    }, indent=2))

    print(f"wrote {JSON_OUT.relative_to(REPO)} ({JSON_OUT.stat().st_size:,} B)")
    print(f"wrote {NPZ_OUT.relative_to(REPO)} ({NPZ_OUT.stat().st_size:,} B)")
    print(f"proteins: {n_proteins}; total mature counts: {counts_mature.sum():.0f}; "
          f"elong: {elongation_rate_aa_per_s} aa/s")
    print(f"sample (prot 0 = {wcm_ids[0]} from gene {gene_wcm_ids[0]}):")
    print(f"  len={length_aa[0]} aa, halfLife={half_life_s[0]:.4g} s, "
          f"decay={decay_rate_per_s[0]:.4g} /s, count_mature={counts_mature[0]:.0f}, "
          f"synth_at_ss={synth_rate_per_s[0]:.4g} /s")


if __name__ == "__main__":
    main()
