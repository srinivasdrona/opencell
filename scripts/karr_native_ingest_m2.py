"""Extract Karr's transcription data into a committed fixture.

Reads `data/m1_sources/karr_flat/{sim_fitted,knowledgeBase}_targeted.mat`
(both gitignored) and writes:
  - data/karr_fixtures/karr_native_m2.json (metadata + ID strings)
  - data/karr_fixtures/karr_native_m2.npz  (numeric arrays)

Sole runtime dependency of `opencell.m2.transcription`.

Run via .venv-wsl:
  wsl bash -lc 'source /mnt/e/opencell/.venv-wsl/bin/activate && \
                python /mnt/e/opencell/scripts/karr_native_ingest_m2.py'
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parents[1]
SIM_MAT = REPO / "data" / "m1_sources" / "karr_flat" / "sim_fitted_targeted.mat"
KB_MAT = REPO / "data" / "m1_sources" / "karr_flat" / "knowledgeBase_targeted.mat"
RNA_MAT = REPO / "data" / "m1_sources" / "karr_flat" / "rnas_targeted.mat"
OUT_DIR = REPO / "data" / "karr_fixtures"
JSON_OUT = OUT_DIR / "karr_native_m2.json"
NPZ_OUT = OUT_DIR / "karr_native_m2.npz"

SCHEMA_VERSION = "karr_native_m2__v2"


def _scalar(x) -> float:
    return float(np.asarray(x).item())


def main() -> None:
    sim = loadmat(str(SIM_MAT), struct_as_record=False, squeeze_me=True)
    kb = loadmat(str(KB_MAT), struct_as_record=False, squeeze_me=True)

    pt = sim["data"].processes.Process_Transcription
    elongation_rate_nt_per_s = _scalar(pt.parameters.rnaPolymeraseElongationRate)
    tu_binding = np.asarray(
        pt.fittedConstants.transcriptionUnitBindingProbabilities, dtype=float
    ).reshape(-1)
    assert tu_binding.size == 335, tu_binding.size

    genes = kb["data"].knowledgeBase.genes
    n_genes = len(genes)
    assert n_genes == 525, n_genes

    # 525 entries
    wcm_ids: list[str] = []
    symbols: list[str] = []
    gene_types: list[str] = []
    half_life: np.ndarray = np.zeros(n_genes, dtype=float)
    length_nt: np.ndarray = np.zeros(n_genes, dtype=np.int32)
    direction: np.ndarray = np.zeros(n_genes, dtype=np.int8)
    start_coord: np.ndarray = np.zeros(n_genes, dtype=np.int32)
    end_coord: np.ndarray = np.zeros(n_genes, dtype=np.int32)
    expression: np.ndarray = np.zeros((n_genes, 3), dtype=float)   # 3-col: low / mean / high
    synthesis_rate: np.ndarray = np.zeros((n_genes, 3), dtype=float)
    essential: list[str] = []

    for i, g in enumerate(genes):
        wcm_ids.append(str(getattr(g, "wholeCellModelID")))
        symbols.append(str(getattr(g, "symbol")))
        gene_types.append(str(getattr(g, "type")))
        half_life[i] = _scalar(getattr(g, "halfLife"))
        s = int(_scalar(getattr(g, "startCoordinate")))
        e = int(_scalar(getattr(g, "endCoordinate")))
        start_coord[i] = s
        end_coord[i] = e
        length_nt[i] = abs(e - s) + 1
        direction[i] = int(_scalar(getattr(g, "direction")))
        expression[i, :] = np.asarray(getattr(g, "expression"), dtype=float).reshape(-1)[:3]
        synthesis_rate[i, :] = np.asarray(
            getattr(g, "synthesisRate"), dtype=float
        ).reshape(-1)[:3]
        essential.append(str(getattr(g, "essential")))

    # Karr WCKB convention: halfLife is in MINUTES, synthesisRate is in
    # transcripts per MINUTE.  At steady state: RNA = synthesisRate / decay
    # where decay = ln(2) / halfLife (also per minute).  We carry a
    # per-second variant for the 1-s tick chassis.
    with np.errstate(divide="ignore", invalid="ignore"):
        decay_rate_per_min = np.where(half_life > 0, np.log(2.0) / half_life, 0.0)
    decay_rate_per_s = decay_rate_per_min / 60.0
    synthesis_rate_per_s = synthesis_rate / 60.0

    # Steady-state derived from Karr's own fitted synthesisRate + halfLife:
    #   dRNA/dt = s - k*RNA = 0  =>  RNA_ss = s / k
    # Use column 1 of synthesisRate / expression as the canonical mean.
    syn_mean_per_min = synthesis_rate[:, 1].copy()
    rna_ss_predicted = np.where(
        decay_rate_per_min > 0,
        syn_mean_per_min / decay_rate_per_min,
        0.0,
    )

    # Type counts (sanity)
    type_counts: dict[str, int] = {}
    for t in gene_types:
        type_counts[t] = type_counts.get(t, 0) + 1

    # ---- E.1b: per-gene RNA molecular weight (Da/mol) ------------------
    # State_Rna stores 7 forms x 347 mature TUs of MW; KB has the
    # gene -> TU index map.  For each of our 525 genes we look up its
    # primary TU, then find that TU's MW in the State_Rna mature slice.
    # Polycistronic TUs are split equally across their member genes so
    # that summing per-gene counts * per_gene_mw at SS reconstructs the
    # TU-level mass correctly when all member-gene counts are equal.
    rna_mat = loadmat(str(RNA_MAT), struct_as_record=False, squeeze_me=True)["data"]
    mature_idx_full = np.asarray(rna_mat.matureIndexs, dtype=int).reshape(-1) - 1
    mw_full = np.asarray(rna_mat.molecularWeights, dtype=float).reshape(-1)
    mature_mw = mw_full[mature_idx_full]
    state_tu_wcm = [str(x) for x in
                    np.asarray(rna_mat.wholeCellModelIDs, dtype=object).reshape(-1)]
    mature_tu_wcm = [state_tu_wcm[i] for i in mature_idx_full]
    state_tu_wcm_to_mw = dict(zip(mature_tu_wcm, mature_mw.tolist()))

    kb_tu_wcm = [str(x) for x in
                 np.asarray(rna_mat.kb_tu_wholeCellModelIDs, dtype=object).reshape(-1)]
    kb_gene_wcm = [str(x) for x in
                   np.asarray(rna_mat.kb_gene_wholeCellModelIDs, dtype=object).reshape(-1)]
    gene_to_tu_1based = np.asarray(rna_mat.kb_gene_to_tu_index, dtype=int).reshape(-1)

    # Validate that the M2 gene order matches the KB gene order.
    assert kb_gene_wcm == wcm_ids, (
        "kb gene wcm order != KB.genes order (M2 fixture). "
        f"first mismatch idx={[i for i,(a,b) in enumerate(zip(kb_gene_wcm, wcm_ids)) if a!=b][:3]}"
    )

    # Count member genes per TU (1-based indexing).
    n_tus = len(kb_tu_wcm)
    members_per_tu = np.zeros(n_tus + 1, dtype=int)
    for tu1 in gene_to_tu_1based:
        if tu1 > 0:
            members_per_tu[tu1] += 1

    rna_molecular_weight = np.zeros(n_genes, dtype=float)
    rna_mw_provenance: list[str] = []
    for i, (gene, tu1) in enumerate(zip(wcm_ids, gene_to_tu_1based)):
        if tu1 <= 0 or tu1 > n_tus:
            rna_mw_provenance.append("orphan")
            continue
        tu_wcm = kb_tu_wcm[tu1 - 1]
        tu_mw = state_tu_wcm_to_mw.get(tu_wcm, 0.0)
        n_members = max(1, int(members_per_tu[tu1]))
        rna_molecular_weight[i] = tu_mw / n_members
        rna_mw_provenance.append(
            f"TU={tu_wcm} mw={tu_mw:.0f} /{n_members}members"
            if tu_mw > 0 else f"TU={tu_wcm} (not in mature set)"
        )

    n_genes_with_mw = int((rna_molecular_weight > 0).sum())

    # For non-mRNA genes (tRNA/rRNA/sRNA) where the State_Rna mature
    # set doesn't expose a direct TU MW, fall back to a sequence-derived
    # estimate: length_nt * avg_NMP_MW where avg_NMP_MW = 339.5 Da/NT
    # (mean of A/C/G/U monophosphate residues in RNA).  rRNA dominates
    # cell RNA mass so we cannot just zero-out the missing entries.
    AVG_NMP_MW = 339.5
    n_fallback = 0
    for i in range(n_genes):
        if rna_molecular_weight[i] == 0.0 and length_nt[i] > 0:
            rna_molecular_weight[i] = float(length_nt[i]) * AVG_NMP_MW
            n_fallback += 1
    n_genes_with_mw_after_fallback = int((rna_molecular_weight > 0).sum())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        NPZ_OUT,
        half_life_min=half_life,
        decay_rate_per_min=decay_rate_per_min,
        decay_rate_per_s=decay_rate_per_s,
        length_nt=length_nt,
        direction=direction,
        start_coord=start_coord,
        end_coord=end_coord,
        expression=expression,
        synthesis_rate_per_min=synthesis_rate,
        synthesis_rate_per_s=synthesis_rate_per_s,
        rna_ss_predicted=rna_ss_predicted,
        tu_binding_probabilities=tu_binding,
        rna_molecular_weight=rna_molecular_weight,
    )

    JSON_OUT.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "source_sim_mat": str(SIM_MAT.relative_to(REPO)),
        "source_kb_mat": str(KB_MAT.relative_to(REPO)),
        "matrix_npz": str(NPZ_OUT.relative_to(REPO)),
        "counts": {
            "n_genes": n_genes,
            "n_transcription_units": int(tu_binding.size),
            "type_counts": type_counts,
        },
        "scalars": {
            "rna_polymerase_elongation_rate_nt_per_s": elongation_rate_nt_per_s,
        },
        "ids": {
            "gene_wcm_525": wcm_ids,
            "gene_symbols_525": symbols,
            "gene_types_525": gene_types,
            "gene_essential_525": essential,
        },
        "shapes": {
            "expression": list(expression.shape),
            "synthesis_rate": list(synthesis_rate.shape),
            "rna_ss_predicted": list(rna_ss_predicted.shape),
            "tu_binding_probabilities": list(tu_binding.shape),
            "rna_molecular_weight": list(rna_molecular_weight.shape),
        },
        "rna_mw_coverage": {
            "n_genes_with_tu_mw": n_genes_with_mw,
            "n_genes_with_seqlen_fallback": n_fallback,
            "n_genes_with_mw_total": n_genes_with_mw_after_fallback,
            "n_genes_total": n_genes,
            "fraction_total": n_genes_with_mw_after_fallback / n_genes,
            "policy": "TU MW split equally across member genes; non-mRNA fall back to length_nt * 339.5 Da",
        },
        "interpretation": (
            "Karr-native M2 transcription fixture. 525 genes (482 mRNA + "
            "3 rRNA + 4 sRNA + 36 tRNA per Karr WCKB) with halfLife (min), "
            "length_nt, expression(3) and synthesisRate(3) [low / mean / "
            "high]. 335 transcriptionUnits with Karr's fitted "
            "binding probabilities (the gold-standard fit; Karr fits these "
            "to make simulated steady-state expression match observed "
            "microarray data). Steady-state RNA count derived as "
            "synthesisRate / decay where decay = ln(2)/halfLife. "
            "rna_ss_predicted is the column 1 (mean) prediction; the "
            "M2 oracle compares this against KB.expression[:, 1]."
        ),
    }, indent=2))

    print(f"wrote {JSON_OUT.relative_to(REPO)} ({JSON_OUT.stat().st_size:,} B)")
    print(f"wrote {NPZ_OUT.relative_to(REPO)} ({NPZ_OUT.stat().st_size:,} B)")
    print(f"genes: {n_genes} ({type_counts}); TUs: {tu_binding.size}; "
          f"elongation rate: {elongation_rate_nt_per_s} nt/s")
    # Spot-check
    print(f"sample (gene 0 = {wcm_ids[0]}, {symbols[0]}, {gene_types[0]}):")
    print(f"  halfLife={half_life[0]:.3f} min, decay={decay_rate_per_min[0]:.4g} /min,"
          f" length={length_nt[0]} nt")
    print(f"  expression=({expression[0,0]:.3g}, {expression[0,1]:.3g}, "
          f"{expression[0,2]:.3g})")
    print(f"  synthesisRate=({synthesis_rate[0,0]:.3g}, "
          f"{synthesis_rate[0,1]:.3g}, {synthesis_rate[0,2]:.3g}) /min")
    print(f"  rna_ss_predicted={rna_ss_predicted[0]:.3g}")


if __name__ == "__main__":
    main()
