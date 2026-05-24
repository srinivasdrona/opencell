from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess
from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.karr_request_calculators import RequestCalculatorProteinPathway


def _build_calc() -> RequestCalculatorProteinPathway:
    pp1 = KarrProteinProcessingIProcess({})
    pp2 = KarrProteinProcessingIIProcess({})
    pm = KarrProteinModificationProcess({})
    pf = KarrProteinFoldingProcess({})
    pt = KarrProteinTranslocationProcess({})
    return RequestCalculatorProteinPathway(
        {
            "protein_processing_i_proc": pp1,
            "protein_processing_ii_proc": pp2,
            "protein_modification_proc": pm,
            "protein_folding_proc": pf,
            "protein_translocation_proc": pt,
        }
    )


def _base_state(calc: RequestCalculatorProteinPathway) -> dict[str, Any]:
    pp2 = calc._pp2_proc
    non_lipo_idx = int(pp2.non_lipo_non_cleaved_indices[0])
    non_lipo_wid = pp2.processed_monomer_wids[non_lipo_idx]
    lipo_wid = pp2.lipoprotein_wids[0]
    return {
        "substrates": {wid: 13.0 for wid in calc.ports_schema()["substrates"]},
        "protein": {
            "counts": {},
            "unprocessed_counts": {wid: 0.0 for wid in calc._pp1_proc.unprocessed_monomer_wids},
            "processed_counts": {lipo_wid: 0.0, non_lipo_wid: 0.0},
            "unfolded_counts": {},
            "unmodified_counts": {},
            "location": {},
        },
    }


def test_pp2_request_uses_processed_lipoproteins() -> None:
    calc = _build_calc()
    state = _base_state(calc)
    pp2_name = calc._pp2_proc.name
    lipo_wid = calc._pp2_proc.lipoprotein_wids[0]

    state["protein"]["unprocessed_counts"][lipo_wid] = 8.0
    update_without_processed = calc.next_update(1.0, state)
    assert all(
        float(v) == 0.0 for v in update_without_processed["requests"][pp2_name].values()
    )

    state["protein"]["processed_counts"][lipo_wid] = 8.0
    update_with_processed = calc.next_update(1.0, state)
    for wid in calc._pp2_proc.substrate_wids:
        if wid in calc._pp2_consumed:
            assert float(update_with_processed["requests"][pp2_name][wid]) == 13.0
        else:
            assert float(update_with_processed["requests"][pp2_name][wid]) == 0.0


def test_pp2_request_ignores_non_lipo_processed_pool() -> None:
    calc = _build_calc()
    state = _base_state(calc)
    pp2_name = calc._pp2_proc.name
    non_lipo_idx = int(calc._pp2_proc.non_lipo_non_cleaved_indices[0])
    non_lipo_wid = calc._pp2_proc.processed_monomer_wids[non_lipo_idx]

    state["protein"]["processed_counts"][non_lipo_wid] = 11.0
    update = calc.next_update(1.0, state)
    assert all(float(v) == 0.0 for v in update["requests"][pp2_name].values())
