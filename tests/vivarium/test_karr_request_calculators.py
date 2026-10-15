from __future__ import annotations

import sys
from math import ceil
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

import pytest
from scipy.io import loadmat

from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess
from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.karr_request_calculators import (
    RequestCalculatorProteinPathway,
    RequestCalculatorPTransloc,
    RequestCalculatorRibAsm,
)
from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess


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
            "counts": dict.fromkeys(calc._pm_proc.monomer_enzyme_wids, 0.0),
            "unprocessed_counts": {wid: 0.0 for wid in calc._pp1_proc.unprocessed_monomer_wids},
            "processed_counts": {lipo_wid: 0.0, non_lipo_wid: 0.0},
            "unfolded_counts": {},
            "unmodified_counts": {},
            "location": {},
        },
        "complex": {"counts": dict.fromkeys(calc._pm_proc.complex_enzyme_wids, 0.0)},
    }


def test_pp2_request_uses_source_processed_i_lipoproteins() -> None:
    calc = _build_calc()
    state = _base_state(calc)
    pp2_name = calc._pp2_proc.name
    lipo_wid = calc._pp2_proc.lipoprotein_wids[0]

    state["protein"]["unprocessed_counts"][lipo_wid] = 8.0
    update_without_processed = calc.next_update(1.0, state)
    assert all(
        float(v) == 0.0 for v in update_without_processed["requests"][pp2_name].values()
    )

    fx = loadmat(
        _REPO_ROOT / "data/karr_fixtures/per_process/ProteinProcessingII_flat.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    idx = int(fx.lipoproteinMonomerIndexs[0]) - 1
    comp = ("c", "d", "e", "m", "tc", "tm")[int(fx.monomerCompartments[idx]) - 1]
    state["protein"]["compartment_counts"] = {"processed_i": {lipo_wid: {comp: 8.0}}}
    state["protein"]["enzyme_counts"] = dict(
        zip(calc._pp2_proc.enzyme_wids, fx.enzymes, strict=True)
    )
    state["protein"]["counts"].update(state["protein"]["enzyme_counts"])
    state["protein"]["compartment_counts"]["mature"] = {
        wid: {("c", "d", "e", "m", "tc", "tm")[int(c) - 1]: float(n)}
        for wid, c, n in zip(
            calc._pp2_proc.enzyme_wids, fx.enzymeMonomerCompartmentIndexs, fx.enzymes, strict=True
        )
    }
    update_with_processed = calc.next_update(1.0, state)
    expected = {wid: 0.0 for wid in calc._pp2_proc.substrate_wids}
    expected[str(fx.substrateWholeCellModelIDs[int(fx.substrateIndexs_water) - 1])] = min(
        8, ceil(float(fx.enzymes[int(fx.enzymeIndexs_signalPeptidase) - 1])
                * float(fx.lipoproteinSignalPeptidaseSpecificRate) * float(fx.stepSizeSec))
    )
    expected[str(fx.substrateWholeCellModelIDs[int(fx.substrateIndexs_PG160) - 1])] = min(
        8, ceil(float(fx.enzymes[int(fx.enzymeIndexs_diacylglycerylTransferase) - 1])
                * float(fx.lipoproteinDiacylglycerylTransferaseSpecificRate)
                * float(fx.stepSizeSec))
    )
    assert update_with_processed["requests"][pp2_name] == expected


def test_pp2_request_ignores_non_lipo_non_secreted_processed_pool() -> None:
    calc = _build_calc()
    state = _base_state(calc)
    pp2_name = calc._pp2_proc.name
    non_lipo_idx = int(calc._pp2_proc.non_lipo_non_cleaved_indices[0])
    non_lipo_wid = calc._pp2_proc.processed_monomer_wids[non_lipo_idx]

    state["protein"]["processed_counts"][non_lipo_wid] = 11.0
    update = calc.next_update(1.0, state)
    assert all(float(v) == 0.0 for v in update["requests"][pp2_name].values())


# ==============================================================================
# Finding B5: fail-closed constructor tests (reject missing or mismatched dependencies)
# ==============================================================================


def test_b5_request_calculator_ribasm_rejects_missing_dependencies() -> None:
    """B5 contract: RequestCalculatorRibAsm must raise ValueError when ribasm_proc is missing or None."""
    with pytest.raises(ValueError, match=r"(?i)ribasm"):
        RequestCalculatorRibAsm({})
    with pytest.raises(ValueError, match=r"(?i)ribasm"):
        RequestCalculatorRibAsm({"ribasm_proc": None})

    # Legitimate explicit dependency construction passes
    ribasm = KarrRibosomeAssemblyProcess({})
    calc = RequestCalculatorRibAsm({"ribasm_proc": ribasm})
    assert calc._ribasm_proc is ribasm
    assert "requests" in calc.ports_schema()


def test_b5_request_calculator_ribasm_rejects_mismatched_dependencies() -> None:
    """B5 contract: RequestCalculatorRibAsm must raise ValueError when ribasm_proc is wrong type."""
    wrong_proc = KarrProteinFoldingProcess({})
    for bad_val in (object(), wrong_proc, "invalid_ribasm_dependency"):
        with pytest.raises(ValueError, match=r"(?i)ribasm"):
            RequestCalculatorRibAsm({"ribasm_proc": bad_val})

    # Legitimate explicit dependency construction passes
    ribasm = KarrRibosomeAssemblyProcess({})
    calc = RequestCalculatorRibAsm({"ribasm_proc": ribasm})
    assert calc._ribasm_proc is ribasm
    assert "requests" in calc.ports_schema()


def test_b5_request_calculator_protein_pathway_rejects_missing_dependencies() -> None:
    """B5 contract: RequestCalculatorProteinPathway must raise ValueError when any dependency is missing or None."""
    with pytest.raises(ValueError, match=r"(?i)require|missing"):
        RequestCalculatorProteinPathway({})

    valid_deps = {
        "protein_processing_i_proc": KarrProteinProcessingIProcess({}),
        "protein_processing_ii_proc": KarrProteinProcessingIIProcess({}),
        "protein_modification_proc": KarrProteinModificationProcess({}),
        "protein_folding_proc": KarrProteinFoldingProcess({}),
        "protein_translocation_proc": KarrProteinTranslocationProcess({}),
    }

    # Partial dependencies (omitted slots) and None values must fail closed
    for slot in valid_deps:
        omitted = {k: v for k, v in valid_deps.items() if k != slot}
        with pytest.raises(ValueError, match=r"(?i)" + slot.removesuffix("_proc")):
            RequestCalculatorProteinPathway(omitted)

        none_param = dict(valid_deps)
        none_param[slot] = None
        with pytest.raises(ValueError, match=r"(?i)" + slot.removesuffix("_proc")):
            RequestCalculatorProteinPathway(none_param)

    # Legitimate explicit dependency construction passes
    calc = RequestCalculatorProteinPathway(valid_deps)
    assert calc._pp1_proc is valid_deps["protein_processing_i_proc"]
    assert calc._pp2_proc is valid_deps["protein_processing_ii_proc"]
    assert calc._pm_proc is valid_deps["protein_modification_proc"]
    assert calc._pf_proc is valid_deps["protein_folding_proc"]
    assert calc._pt_proc is valid_deps["protein_translocation_proc"]
    assert "requests" in calc.ports_schema()


def test_b5_request_calculator_protein_pathway_rejects_mismatched_dependencies() -> None:
    """B5 contract: RequestCalculatorProteinPathway must raise ValueError when any dependency has wrong type."""
    valid_deps = {
        "protein_processing_i_proc": KarrProteinProcessingIProcess({}),
        "protein_processing_ii_proc": KarrProteinProcessingIIProcess({}),
        "protein_modification_proc": KarrProteinModificationProcess({}),
        "protein_folding_proc": KarrProteinFoldingProcess({}),
        "protein_translocation_proc": KarrProteinTranslocationProcess({}),
    }
    wrong_proc = KarrRibosomeAssemblyProcess({})

    # Every named slot must reject wrong types (object(), wrong process class, string)
    for slot in valid_deps:
        for bad_val in (object(), wrong_proc, "invalid_dependency_type"):
            corrupted = dict(valid_deps)
            corrupted[slot] = bad_val
            with pytest.raises(ValueError, match=r"(?i)" + slot.removesuffix("_proc")):
                RequestCalculatorProteinPathway(corrupted)

    # Legitimate explicit dependency construction passes
    calc = RequestCalculatorProteinPathway(valid_deps)
    assert calc._pp1_proc is valid_deps["protein_processing_i_proc"]
    assert "requests" in calc.ports_schema()


def test_b5_request_calculator_ptransloc_rejects_missing_dependencies() -> None:
    """B5 contract: RequestCalculatorPTransloc must raise ValueError when protein_translocation_proc is missing or None."""
    with pytest.raises(ValueError, match=r"(?i)protein_translocation"):
        RequestCalculatorPTransloc({})
    with pytest.raises(ValueError, match=r"(?i)protein_translocation"):
        RequestCalculatorPTransloc({"protein_translocation_proc": None})

    # Legitimate explicit dependency construction passes
    pt = KarrProteinTranslocationProcess({})
    calc = RequestCalculatorPTransloc({"protein_translocation_proc": pt})
    assert calc._pt_proc is pt
    assert "requests" in calc.ports_schema()


def test_b5_request_calculator_ptransloc_rejects_mismatched_dependencies() -> None:
    """B5 contract: RequestCalculatorPTransloc must raise ValueError when protein_translocation_proc is wrong type."""
    wrong_proc = KarrRibosomeAssemblyProcess({})
    for bad_val in (object(), wrong_proc, "invalid_translocation_dependency"):
        with pytest.raises(ValueError, match=r"(?i)protein_translocation"):
            RequestCalculatorPTransloc({"protein_translocation_proc": bad_val})

    # Legitimate explicit dependency construction passes
    pt = KarrProteinTranslocationProcess({})
    calc = RequestCalculatorPTransloc({"protein_translocation_proc": pt})
    assert calc._pt_proc is pt
    assert "requests" in calc.ports_schema()
