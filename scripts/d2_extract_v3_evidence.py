"""Extract source-truth evidence for D.2 design v3 from *_flat.mat fixtures."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[1]
PER_PROCESS = ROOT / "data" / "karr_fixtures" / "per_process"
OUT_JSON = ROOT / "artifacts" / "d2_v3_evidence.json"
OUT_MD = ROOT / "artifacts" / "d2_v3_evidence.md"


def _arr(v: Any) -> np.ndarray:
    return np.array(v).ravel()


def _to_str_list(v: Any) -> list[str]:
    return [str(x) for x in _arr(v).tolist()]


def _to_int_list(v: Any) -> list[int]:
    return [int(x) for x in _arr(v).tolist()]


def _load_fixture(path: Path):
    return loadmat(path, squeeze_me=True, struct_as_record=False)["data"].fixture


def _summarize_unknown(msg: str) -> dict[str, Any]:
    return {"status": "unknown", "reason": msg}


def main() -> int:
    ribo_path = PER_PROCESS / "RibosomeAssembly_flat.mat"
    mc_path = PER_PROCESS / "MacromolecularComplexation_flat.mat"
    pc_path = PER_PROCESS / "ProteinComplex_flat.mat"
    met_path = PER_PROCESS / "Metabolite_flat.mat"

    required = [ribo_path, mc_path, pc_path, met_path]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        payload = {"status": "failed", "missing_inputs": missing}
        OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        OUT_MD.write_text(
            "# D.2 v3 Evidence Extraction\n\n- status: failed\n- reason: missing inputs\n",
            encoding="utf-8",
        )
        return 1

    ribo = _load_fixture(ribo_path)
    _mc = _load_fixture(mc_path)
    pc = _load_fixture(pc_path)
    met = _load_fixture(met_path)

    process_names = _to_str_list(met.processWholeCellModelIDs)  # 1-based index in MATLAB
    formation_ids = _to_int_list(pc.formationProcesses)
    complex_wids = _to_str_list(pc.wholeCellModelIDs)
    counts = np.array(pc.counts)
    molecular_weights = np.array(pc.molecularWeights).reshape(-1)
    mature_idx = np.array(pc.matureIndexs).reshape(-1).astype(int) - 1
    bound_idx = np.array(pc.boundIndexs).reshape(-1).astype(int) - 1
    counts_sum = counts.sum(axis=1)
    n_avogadro = 6.02214076e23
    mature_mass_g = float((counts_sum[mature_idx] * molecular_weights[mature_idx]).sum() / n_avogadro)
    bound_mass_g = float((counts_sum[bound_idx] * molecular_weights[bound_idx]).sum() / n_avogadro)
    total_mass_g = float((counts_sum * molecular_weights).sum() / n_avogadro)

    hist: Counter[int] = Counter(formation_ids)
    hist_named = {
        process_names[k - 1] if 1 <= k <= len(process_names) else f"UNKNOWN_{k}": v
        for k, v in sorted(hist.items(), key=lambda kv: (-kv[1], kv[0]))
    }

    by_process: dict[str, list[str]] = {}
    for pid in sorted(set(formation_ids)):
        pname = process_names[pid - 1] if 1 <= pid <= len(process_names) else f"UNKNOWN_{pid}"
        ids = sorted({wid for wid, fp in zip(complex_wids, formation_ids) if fp == pid})
        by_process[pname] = ids

    ribo_substrate_ids = _to_str_list(ribo.substrateWholeCellModelIDs)
    ribo_enzyme_ids = _to_str_list(ribo.enzymeWholeCellModelIDs)
    idx_30s = _to_int_list(ribo.enzymeIndexs_30S_assembly_gtpase)
    idx_50s = _to_int_list(ribo.enzymeIndexs_50S_assembly_gtpase)
    gtpases_30s = [ribo_enzyme_ids[i - 1] for i in idx_30s]
    gtpases_50s = [ribo_enzyme_ids[i - 1] for i in idx_50s]

    ribosome_owned_wids = {
        pname: ids
        for pname, ids in by_process.items()
        if pname in {"Process_RibosomeAssembly", "Process_Translation"}
    }

    result: dict[str, Any] = {
        "inputs": {
            "ribosome_flat_mat": str(ribo_path.relative_to(ROOT)),
            "macromolecular_complexation_flat_mat": str(mc_path.relative_to(ROOT)),
            "protein_complex_flat_mat": str(pc_path.relative_to(ROOT)),
            "metabolite_flat_mat": str(met_path.relative_to(ROOT)),
        },
        "blocker_1_ribosome_costs": {
            "status": "extracted",
            "source_fields": {
                "substrateWholeCellModelIDs": ribo_substrate_ids,
                "substrateIndexs": {
                    "gtp": int(ribo.substrateIndexs_gtp),
                    "gdp": int(ribo.substrateIndexs_gdp),
                    "phosphate": int(ribo.substrateIndexs_phosphate),
                    "water": int(ribo.substrateIndexs_water),
                    "hydrogen": int(ribo.substrateIndexs_hydrogen),
                },
                "enzymeWholeCellModelIDs": ribo_enzyme_ids,
                "enzymeIndexs_30S_assembly_gtpase": idx_30s,
                "enzymeIndexs_50S_assembly_gtpase": idx_50s,
                "gtpases_30S_named": gtpases_30s,
                "gtpases_50S_named": gtpases_50s,
                "complexWholeCellModelIDs": _to_str_list(ribo.complexWholeCellModelIDs),
                "complexIndexs": {
                    "30S": int(ribo.complexIndexs_30S_ribosome),
                    "50S": int(ribo.complexIndexs_50S_ribosome),
                },
            },
            "interpretation": {
                "thirty_vs_fifty_split": "30S uses 2 assembly GTPases, 50S uses 4 assembly GTPases.",
                "must_not_use_blanket_6x": True,
                "note": (
                    "RibosomeAssembly fixture explicitly carries 30S/50S split signals. "
                    "Apply per-step costs, do not collapse into a blanket 6x claim."
                ),
            },
        },
        "blocker_2_scope_ownership": {
            "status": "extracted",
            "formation_process_histogram_named": hist_named,
            "formation_process_whitelist_for_D2": [
                "Process_MacromolecularComplexation",
                "Process_RibosomeAssembly",
            ],
            "formation_process_explicit_exclusions": [
                "Process_FtsZPolymerization",
                "Process_DnaApolymerization (represented via Process_ReplicationInitiation in this fixture set)",
                "Process_TranscriptionalRegulation/Transcription",
                "Process_ChromosomeCondensation",
            ],
            "ribosome_related_process_ownership": ribosome_owned_wids,
            "note": (
                "Build scope from snapshot ownership fields. Do not absorb non-whitelisted processes into D.2."
            ),
        },
        "blocker_3_emit_conservation": _summarize_unknown(
            "Design-level check; emit schema must include +product and -consumed-subcomplex deltas."
        ),
        "blocker_4_oracle_target": {
            "status": "extracted",
            "source_fields": {
                "counts": "ProteinComplex_flat.fixture.counts",
                "molecularWeights": "ProteinComplex_flat.fixture.molecularWeights",
                "matureIndexs": "ProteinComplex_flat.fixture.matureIndexs",
                "boundIndexs": "ProteinComplex_flat.fixture.boundIndexs",
            },
            "mass_targets_g": {
                "mature_only": mature_mass_g,
                "bound_only": bound_mass_g,
                "all_forms_total": total_mass_g,
            },
            "interpretation": {
                "oracle_rule": "Compare D.2 mature output to mature-only target; all-forms total is integration-stage target.",
                "must_not_compare_mature_to_all_forms": True,
            },
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")

    md_lines = [
        "# D.2 v3 Evidence Extraction",
        "",
        "## Inputs",
        f"- `{result['inputs']['ribosome_flat_mat']}`",
        f"- `{result['inputs']['macromolecular_complexation_flat_mat']}`",
        f"- `{result['inputs']['protein_complex_flat_mat']}`",
        f"- `{result['inputs']['metabolite_flat_mat']}`",
        "",
        "## BLOCKER #1 (Ribosome costs)",
        "- status: `extracted`",
        f"- substrates: `{', '.join(ribo_substrate_ids)}`",
        f"- 30S assembly GTPases: `{', '.join(gtpases_30s)}`",
        f"- 50S assembly GTPases: `{', '.join(gtpases_50s)}`",
        "- rule: use per-step split (2 vs 4), not blanket 6x shortcut.",
        "",
        "## BLOCKER #2 (Scope ownership)",
        "- status: `extracted`",
        "- formation process histogram (named):",
    ]
    for k, v in hist_named.items():
        md_lines.append(f"  - `{k}`: {v}")
    md_lines.extend(
        [
            "- D.2 whitelist: `Process_MacromolecularComplexation`, `Process_RibosomeAssembly`",
            "",
            "## BLOCKER #3 (Emit conservation)",
            f"- status: `{result['blocker_3_emit_conservation']['status']}`",
            f"- reason: {result['blocker_3_emit_conservation']['reason']}",
            "",
            "## BLOCKER #4 (Oracle target)",
            "- status: `extracted`",
            f"- mature-only mass target (g): `{mature_mass_g:.16e}`",
            f"- all-forms total mass (g): `{total_mass_g:.16e}`",
            "- rule: mature-to-mature for D.2; mature+bound for integration-stage checks.",
            "",
            "## Output JSON",
            f"- `{OUT_JSON.relative_to(ROOT)}`",
        ]
    )
    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
