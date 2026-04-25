"""Karr-native M2 v2: mechanism-based synthesis-rate prediction.

Reads `data/m1_sources/karr_flat/transcription_v2_targeted.mat` (gitignored,
produced by `scripts/matlab/extract_karr_m2v2.m`) plus the existing M2 v1
fixture (gene-level synthesis rates, TU binding probs, lengths) and writes
`data/karr_fixtures/karr_native_m2_v2.{json,npz}`.

Per Karr's `Transcription.m::evolveState`/`computeRNAPolymeraseTUBindingProbabilities`,
the per-second steady-state production rate of transcription unit j is

    synth_TU_j = N_active * elongation_rate * P_bind_j / sum_k(P_bind_k * length_k)

A polymerase finishes a TU completion at rate (elongation/length_j) while it is
on TU j; the fraction of active polymerases on TU j at SS equals
(P_bind_j * length_j) / sum_k(P_bind_k * length_k).  Multiplying yields the
formula above (length cancels).

For polycistronic operons each completion produces exactly one copy of each
constituent gene's mRNA, so for gene i in TU j we have
synth_gene_i = synth_TU_j summed over TUs containing i (in M.g essentially
each gene maps to exactly one TU).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parents[1]
MAT = REPO / "data" / "m1_sources" / "karr_flat" / "transcription_v2_targeted.mat"
M2_FIXTURE_JSON = REPO / "data" / "karr_fixtures" / "karr_native_m2.json"
M2_FIXTURE_NPZ = REPO / "data" / "karr_fixtures" / "karr_native_m2.npz"
OUT_JSON = REPO / "data" / "karr_fixtures" / "karr_native_m2_v2.json"
OUT_NPZ = REPO / "data" / "karr_fixtures" / "karr_native_m2_v2.npz"


def _flatten(o):
    if hasattr(o, "tolist"):
        return o.tolist()
    return o


def _to_str_list(arr):
    out = []
    for x in np.asarray(arr).ravel():
        if isinstance(x, (bytes, bytearray)):
            out.append(x.decode())
        else:
            out.append(str(x))
    return out


def main():
    if not MAT.exists():
        raise SystemExit(f"missing {MAT}; run scripts/matlab/extract_karr_m2v2.m first")

    print(f"loading {MAT.name}")
    raw = loadmat(MAT, squeeze_me=True, struct_as_record=False)
    d = raw["data"]

    # Mechanism inputs from the v2 dump
    n_active = int(d.rnap_nActive)
    n_spec = int(getattr(d, "rnap_nSpecificallyBound", 0))
    n_nonspec = int(getattr(d, "rnap_nNonSpecificallyBound", 0))
    n_free = int(getattr(d, "rnap_nFree", 0))
    n_total = n_active + n_spec + n_nonspec + n_free
    state_exp = np.asarray(d.rnap_stateExpectations, dtype=float).ravel()
    elong = float(d.pt_rnaPolymeraseElongationRate)
    tu_lengths = np.asarray(d.tr_transcriptionUnitLengths, dtype=float).ravel()  # 335
    tu_wcm_ids = _to_str_list(d.kb_tu_wholeCellModelIDs)
    tu_gene_wcm_ids = [_to_str_list(g) if not isinstance(g, str) else [g]
                       for g in d.kb_tu_geneWcmIDs]
    gene_order_525 = _to_str_list(d.kb_geneWholeCellModelIDs_full)

    n_tu = tu_lengths.size
    n_genes = len(gene_order_525)
    print(f"  N_active_RNAP={n_active} (specBound={n_spec} nonSpec={n_nonspec} free={n_free} total={n_total})")
    print(f"  state_exp={state_exp}")
    print(f"  elongation={elong} nt/s,  n_TU={n_tu},  n_genes={n_genes}")

    # Existing v1 fixture: P_bind (335) + Karr's fitted gene-level rates
    z1 = np.load(M2_FIXTURE_NPZ)
    p_bind_tu = z1["tu_binding_probabilities"].astype(float)  # (335,)
    syn_per_s_genes = z1["synthesis_rate_per_s"][:, 1]        # mean condition (525,)
    gene_lengths = z1["length_nt"].astype(float)              # (525,)
    decay_per_s = z1["decay_rate_per_s"].astype(float)        # (525,)
    expression = z1["expression"][:, 1]                       # (525,)
    if p_bind_tu.size != n_tu:
        raise RuntimeError(f"P_bind size {p_bind_tu.size} != n_TU {n_tu}")

    m2_meta = json.loads(M2_FIXTURE_JSON.read_text())
    gene_wcm_525 = list(m2_meta["ids"]["gene_wcm_525"])
    gene_types_525 = list(m2_meta["ids"]["gene_types_525"])
    if gene_wcm_525 != gene_order_525:
        # Re-permute the v2 gene order to match v1 ordering
        idx_map = {g: i for i, g in enumerate(gene_order_525)}
        # we'll keep gene_wcm_525 as the canonical order
        print("  [info] gene order differs between v1 and v2 dump; will align by WCM ID")

    # Build TU -> gene incidence (n_tu x n_genes)
    gene_idx_525 = {g: i for i, g in enumerate(gene_wcm_525)}
    tu_gene_incidence = np.zeros((n_tu, n_genes), dtype=np.int8)
    n_unmapped = 0
    n_polycistronic = 0
    for j, gids in enumerate(tu_gene_wcm_ids):
        if isinstance(gids, str):
            gids = [gids]
        if len(gids) > 1:
            n_polycistronic += 1
        for g in gids:
            i = gene_idx_525.get(g)
            if i is None:
                n_unmapped += 1
            else:
                tu_gene_incidence[j, i] = 1
    print(f"  TU-gene incidence built; {n_polycistronic}/{n_tu} polycistronic, {n_unmapped} unmapped genes")

    # Sanity: each gene should be in exactly one TU (typical for M.g)
    genes_per_count = tu_gene_incidence.sum(axis=0)
    n_in_zero = int(np.sum(genes_per_count == 0))
    n_in_one = int(np.sum(genes_per_count == 1))
    n_in_multi = int(np.sum(genes_per_count > 1))
    print(f"  genes in [0,1,>1] TUs: {n_in_zero}/{n_in_one}/{n_in_multi}")

    # === Mechanism prediction ===
    # synth_TU_j = N_active * elongation * P_bind_j / sum_k(P_bind_k * length_k)
    denom = float(np.sum(p_bind_tu * tu_lengths))
    synth_tu_per_s = n_active * elong * p_bind_tu / denom  # (335,)
    # gene-level: sum over TUs that contain the gene
    synth_gene_per_s_predicted = synth_tu_per_s @ tu_gene_incidence  # (n_genes,)

    # === Karr's fitted gene-level rates (oracle) ===
    synth_gene_per_s_karr = syn_per_s_genes  # (525,)

    # Compare on genes that are in exactly one TU (clean comparison)
    valid = (genes_per_count == 1) & np.isfinite(synth_gene_per_s_karr) \
        & (synth_gene_per_s_karr > 0) & (synth_gene_per_s_predicted > 0)
    ratio = synth_gene_per_s_predicted[valid] / synth_gene_per_s_karr[valid]
    log2r = np.log2(ratio)
    print()
    print("=== M2 v2 oracle: mechanism vs Karr fitted ===")
    print(f"  comparable genes: {int(valid.sum())} (in exactly 1 TU, both rates>0)")
    print(f"  log2 ratio:  median={np.median(log2r):+.3f}  |  mean={np.mean(log2r):+.3f}  |  std={np.std(log2r):.3f}")
    print(f"  log2 ratio:  10pct={np.percentile(log2r,10):+.3f}  90pct={np.percentile(log2r,90):+.3f}")
    print(f"  median |log2 ratio| = {np.median(np.abs(log2r)):.3f}")
    print(f"  total synth (mech)  = {np.sum(synth_gene_per_s_predicted):.4f} per s")
    print(f"  total synth (Karr)  = {np.sum(synth_gene_per_s_karr):.4f} per s")
    print(f"  total NT polym (mech) = {np.sum(synth_tu_per_s * tu_lengths):.2f} nt/s "
          f"(expected ~ N_active*elong = {n_active*elong:.0f})")

    # Save fixture
    out_meta = {
        "schema_version": 1,
        "source_mat": str(MAT.relative_to(REPO).as_posix()),
        "matrix_npz": OUT_NPZ.name,
        "scalars": {
            "n_active_rnap": n_active,
            "n_specifically_bound_rnap": n_spec,
            "n_nonspecifically_bound_rnap": n_nonspec,
            "n_free_rnap": n_free,
            "n_total_rnap": n_total,
            "rna_polymerase_elongation_rate_nt_per_s": elong,
            "denom_sum_pbind_x_length": denom,
        },
        "ids": {
            "gene_wcm_525": gene_wcm_525,
            "gene_types_525": gene_types_525,
            "tu_wcm_335": tu_wcm_ids,
        },
        "shapes": {
            "tu_lengths": [n_tu],
            "tu_binding_probabilities": [n_tu],
            "tu_gene_incidence": [n_tu, n_genes],
            "synth_tu_per_s_predicted": [n_tu],
            "synth_gene_per_s_predicted": [n_genes],
            "synth_gene_per_s_karr": [n_genes],
            "rnap_state_expectations_4": [4],
        },
        "interpretation": {
            "synth_TU_j": "N_active * elongation_rate * P_bind_j / sum_k(P_bind_k * length_k)",
            "synth_gene_i": "sum over TUs containing gene i of synth_TU_j",
            "rnap_state_expectations_index": ["activelyTranscribing", "specificallyBound", "nonSpecificallyBound", "free"],
        },
    }
    OUT_JSON.write_text(json.dumps(out_meta, indent=2))
    np.savez_compressed(
        OUT_NPZ,
        tu_lengths=tu_lengths,
        tu_binding_probabilities=p_bind_tu,
        tu_gene_incidence=tu_gene_incidence,
        synth_tu_per_s_predicted=synth_tu_per_s,
        synth_gene_per_s_predicted=synth_gene_per_s_predicted,
        synth_gene_per_s_karr=synth_gene_per_s_karr,
        gene_lengths=gene_lengths,
        decay_per_s=decay_per_s,
        expression=expression,
        rnap_state_expectations=state_exp,
    )
    print(f"\n[OK] wrote {OUT_JSON.name} + {OUT_NPZ.name}")


if __name__ == "__main__":
    main()
