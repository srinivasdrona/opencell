from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

import numpy as np
from scipy.io import loadmat


def _parse_wid_array(value: object) -> list[str]:
    values = np.asarray(value, dtype=object).reshape(-1)
    out: list[str] = []
    for raw in values:
        item: object = raw
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return out


def load_source_derived_migrated_wids() -> frozenset[str]:
    """Source-derived migration set: TOA fixture union PT fixture translocating indices."""
    toa_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "TerminalOrganelleAssembly_flat.mat"
    pt_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinTranslocation_flat.mat"
    toa_mat = loadmat(str(toa_path), squeeze_me=True, struct_as_record=False)
    pt_mat = loadmat(str(pt_path), squeeze_me=True, struct_as_record=False)
    toa_wids = set(_parse_wid_array(toa_mat["data"].fixture.substrateWholeCellModelIDs))
    pt_fx = pt_mat["data"].fixture
    pt_wids = [str(x) for x in pt_fx.monomerWholeCellModelIDs]
    trans_indices = np.asarray(pt_fx.monomerIndexs_translocating, dtype=int) - 1
    pt_trans_wids = {pt_wids[i] for i in trans_indices}
    return frozenset(toa_wids | pt_trans_wids)


MIGRATED_WIDS = load_source_derived_migrated_wids()

LEGACY_BRANCHES = frozenset({
    "counts",
    "unprocessed_counts",
    "processed_counts",
    "unfolded_counts",
    "unmodified_counts",
    "modified_counts",
    "signal_sequence_counts",
    "location",
})

# Machine-checkable manifest of production modules with protein ports from Design 2.4
# (module_name, class_name, legacy_writable_branches, role)
PROTEIN_PROCESS_MANIFEST = (
    # Writers: legacy writable branches must not contain migrated WIDs
    ("opencell.vivarium.karr_translation_v3", "KarrTranslationV3Process", ("unprocessed_counts",), "MIGRATABLE-W"),
    ("opencell.vivarium.karr_protein_processing_i", "KarrProteinProcessingIProcess", ("unprocessed_counts", "processed_counts", "counts"), "MIGRATABLE-W/AUTH-W"),
    ("opencell.vivarium.karr_protein_processing_ii", "KarrProteinProcessingIIProcess", ("processed_counts", "unfolded_counts", "signal_sequence_counts"), "MIGRATABLE-W"),
    ("opencell.vivarium.karr_protein_folding", "KarrProteinFoldingProcess", ("unfolded_counts", "counts"), "MIGRATABLE-W/AUTH-W"),
    ("opencell.vivarium.karr_protein_modification", "KarrProteinModificationProcess", ("unmodified_counts", "modified_counts"), "MIGRATABLE-W/AUTH-W"),
    # RequestProcess inherits the real schema and evolves when request_ready is armed;
    # EvolutionStep delegates that write through the same owned RequestProcess.
    ("opencell.vivarium.karr_protein_modification", "KarrProteinModificationRequestProcess", ("unmodified_counts", "modified_counts"), "MIGRATABLE-W/AUTH-W"),
    ("opencell.vivarium.karr_protein_modification", "KarrProteinModificationEvolutionStep", ("unmodified_counts", "modified_counts"), "MIGRATABLE-W/AUTH-W"),
    ("opencell.vivarium.karr_protein_translocation", "KarrProteinTranslocationProcess", ("unprocessed_counts", "location"), "MIGRATABLE-W"),
    ("opencell.vivarium.karr_protein_decay_light", "ProteinDecayLightProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.karr_terminal_organelle_assembly", "KarrTerminalOrganelleAssemblyProcess", (), "AUTH-W"),
    ("opencell.vivarium.karr_ribosome_assembly", "KarrRibosomeAssemblyProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.karr_chromosome_segregation", "KarrChromosomeSegregationProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.karr_replication_initiation", "KarrReplicationInitiationProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.karr_dna_supercoiling", "KarrDNASupercoilingProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.protein_flat_projection_step", "ProteinFlatProjectionStep", (), "DERIVED-W/AUTH-W"),
    # Readers (DERIVED-R) / Excluded
    ("opencell.vivarium.karr_dna_repair", "KarrDNARepairProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_host_interaction", "KarrHostInteractionProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_observability_step", "KarrObservabilityStep", (), "DERIVED-R"),
    ("opencell.vivarium.karr_protein_activation", "KarrProteinActivationProcess", (), "DERIVED-R/STAGE-4"),
    ("opencell.vivarium.karr_request_calculators", "RequestCalculatorPTransloc", ("unprocessed_counts", "location"), "DERIVED-R"),
    ("opencell.vivarium.karr_request_calculators", "RequestCalculatorProteinPathway", ("unprocessed_counts", "location"), "DERIVED-R"),
    ("opencell.vivarium.karr_request_calculators", "RequestCalculatorRibAsm", (), "DERIVED-R"),
    ("opencell.vivarium.karr_rna_modification", "KarrRNAModificationProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_rna_processing", "KarrRNAProcessingProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_transcriptional_regulation", "KarrTranscriptionalRegulationProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_trna_aminoacylation", "KarrTRNAAminoacylationProcess", (), "DERIVED-R"),
    # Legacy non-runtime modules
    ("opencell.vivarium.karr_translation", "KarrTranslationProcess", (), "LEGACY"),
    ("opencell.vivarium.karr_translation_v2", "KarrTranslationV2Process", (), "LEGACY"),
)


def _instantiate_process_with_dependencies(cls: type) -> Any:
    """Instantiate Process/Step classes with explicit dependencies where required."""
    name = cls.__name__
    if name == "KarrProteinModificationEvolutionStep":
        from opencell.vivarium.karr_protein_modification import (
            KarrProteinModificationRequestProcess,
        )

        return cls({"modification_process": KarrProteinModificationRequestProcess({})})
    if name == "RequestCalculatorPTransloc":
        from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess

        return cls({"protein_translocation_proc": KarrProteinTranslocationProcess({})})
    if name == "RequestCalculatorRibAsm":
        from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess

        return cls({"ribasm_proc": KarrRibosomeAssemblyProcess({})})
    if name == "RequestCalculatorProteinPathway":
        from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
        from opencell.vivarium.karr_protein_modification import (
            KarrProteinModificationProcess,
        )
        from opencell.vivarium.karr_protein_processing_i import (
            KarrProteinProcessingIProcess,
        )
        from opencell.vivarium.karr_protein_processing_ii import (
            KarrProteinProcessingIIProcess,
        )
        from opencell.vivarium.karr_protein_translocation import (
            KarrProteinTranslocationProcess,
        )

        return cls({
            "protein_processing_i_proc": KarrProteinProcessingIProcess({}),
            "protein_processing_ii_proc": KarrProteinProcessingIIProcess({}),
            "protein_modification_proc": KarrProteinModificationProcess({}),
            "protein_folding_proc": KarrProteinFoldingProcess({}),
            "protein_translocation_proc": KarrProteinTranslocationProcess({}),
        })
    return cls({})


def _find_all_vivarium_process_classes() -> list[tuple[str, type]]:
    """Discover all Process subclasses defined in opencell/vivarium/."""
    from vivarium.core.process import Process, Step

    vivarium_dir = _REPO_ROOT / "opencell" / "vivarium"
    results = []
    for py_file in sorted(vivarium_dir.glob("*.py")):
        if py_file.name.startswith(("_", "test")):
            continue
        mod_name = f"opencell.vivarium.{py_file.stem}"
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, (Process, Step))
                and attr.__module__ == mod_name
            ):
                results.append((mod_name, attr))
    return results


def test_c2_manifest_completeness_and_classification() -> None:
    """Every Vivarium Process/Step with a protein port must be classified in manifest."""
    discovered = _find_all_vivarium_process_classes()
    manifest_classes = {cls_name for _, cls_name, _, _ in PROTEIN_PROCESS_MANIFEST}

    unclassified_with_protein = []
    for mod_name, cls in discovered:
        try:
            proc = _instantiate_process_with_dependencies(cls)
            schema = proc.ports_schema()
            if "protein" in schema and cls.__name__ not in manifest_classes:
                unclassified_with_protein.append((mod_name, cls.__name__))
        except Exception:
            # If instantiation requires non-empty parameters, inspect ports_schema source
            src = inspect.getsource(cls)
            if ('"protein"' in src or "'protein'" in src) and cls.__name__ not in manifest_classes:
                unclassified_with_protein.append((mod_name, cls.__name__))


    assert not unclassified_with_protein, (
        f"Found unclassified Process/Step classes with protein port: {unclassified_with_protein}. "
        "Every protein-port process must be classified in PROTEIN_PROCESS_MANIFEST."
    )


def test_c3_legacy_leaves_exclude_migrated_wids() -> None:
    """Claim C3: For every module in manifest, legacy writable branches must NOT contain

    any of the enrolled MIGRATED_WIDS, RequestCalculatorPTransloc branches must be nonempty,
    and protein.location must be absent from all runtime ports.
    """
    violations: list[str] = []

    # Verify RequestCalculatorPTransloc branches are nonempty in manifest
    ptrans_entry = [entry for entry in PROTEIN_PROCESS_MANIFEST if entry[1] == "RequestCalculatorPTransloc"]
    assert ptrans_entry and ptrans_entry[0][2], "RequestCalculatorPTransloc manifest branches must be nonempty"

    for mod_name, cls_name, branches, _ in PROTEIN_PROCESS_MANIFEST:
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
        try:
            proc = _instantiate_process_with_dependencies(cls)
            schema = proc.ports_schema()
        except Exception as exc:
            violations.append(f"{cls_name}: failed to instantiate ports_schema: {exc}")
            continue

        protein_schema = schema.get("protein", {})

        # protein location absent from runtime ports
        if "location" in protein_schema:
            violations.append(f"{cls_name}: declares 'location' under protein port")

        for branch in branches:
            branch_dict = protein_schema.get(branch, {})
            if isinstance(branch_dict, dict):
                declared_wids = set(branch_dict.keys())
                intersection = MIGRATED_WIDS & declared_wids
                if intersection:
                    violations.append(
                        f"{cls_name} legacy branch {branch!r} still contains migrated WIDs: {sorted(intersection)}"
                    )

    assert not violations, (
        "Claim C3 violation: migrated WIDs must be removed from all legacy writable branches "
        "and protein.location must be absent from all runtime ports:\n"
        + "\n".join(violations)
    )


# Backward-compatible alias for existing test runners
test_c2_legacy_leaves_exclude_migrated_wids = test_c3_legacy_leaves_exclude_migrated_wids


def _extract_protein_leaf_paths(d: Any, prefix: tuple[str, ...] = ("protein",)) -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = []
    if isinstance(d, dict):
        if not d:
            return []
        for k, v in d.items():
            if isinstance(v, dict) and v:
                paths.extend(_extract_protein_leaf_paths(v, prefix + (str(k),)))
            else:
                paths.append(prefix + (str(k),))
    return paths


def _is_path_declared(schema_protein: dict[str, Any], leaf_path: tuple[str, ...]) -> bool:
    curr: Any = schema_protein
    for part in leaf_path[1:]:
        if not isinstance(curr, dict) or part not in curr:
            return False
        curr = curr[part]
    return True


def _verify_emitted_protein_update(proc: Any, update: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    protein_update = update.get("protein", {})
    if not protein_update:
        return [f"{proc.name}: emitted empty protein update"]

    leaf_paths = _extract_protein_leaf_paths(protein_update)
    if not leaf_paths:
        return [f"{proc.name}: no leaf paths in protein update"]

    schema = proc.ports_schema()
    protein_schema = schema.get("protein", {})

    for path in leaf_paths:
        if not _is_path_declared(protein_schema, path):
            violations.append(
                f"{proc.name}: emitted undeclared protein leaf path: {'.'.join(path)}"
            )
        # For maturation writers, verify no migrated WID is emitted on legacy branches
        if proc.name != "protein_flat_projection" and len(path) >= 3 and path[1] in LEGACY_BRANCHES:
            wid = path[2]
            if wid in MIGRATED_WIDS:
                violations.append(
                    f"{proc.name}: migrated WID {wid!r} emitted on legacy branch {path[1]!r}: {'.'.join(path)}"
                )
    return violations


def _activate_translation_v3() -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process

    proc = KarrTranslationV3Process({})
    state = {
        "protein": {
            "counts": {
                pid: float(proc.kinetics_model.counts_mature[i])
                for i, pid in enumerate(proc.protein_ids)
            }
        },
        "complex": {"counts": {"RIBOSOME_70S": 100.0}},
        "substrates": {wid: 10000.0 for wid in proc.substrate_wids},
        "substrates_allocated": {proc.name: {wid: 10000.0 for wid in proc.substrate_wids}},
        "requests": {proc.name: {wid: 0.0 for wid in proc.substrate_wids}},
    }
    return proc, proc.next_update(1.0, state)


def _activate_protein_processing_i() -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess

    proc = KarrProteinProcessingIProcess({})
    state = {
        "substrates": {wid: 1000.0 for wid in proc.substrate_wids},
        "protein": {
            "unprocessed_counts": {
                wid: 5.0 for wid in proc.unprocessed_monomer_wids if wid not in MIGRATED_WIDS
            },
            "processed_counts": {wid: 0.0 for wid in proc.processed_monomer_wids},
            "counts": {wid: 1000.0 for wid in proc.protein_enzyme_wids},
            "enzyme_counts": {wid: 1000.0 for wid in proc.protein_enzyme_wids},
            "compartment_counts": {
                "nascent": {wid: {"c": 5.0} for wid in MIGRATED_WIDS},
                "processed_i": {wid: {"c": 0.0} for wid in MIGRATED_WIDS},
            },
        },
        "complex": {"counts": {wid: 1000.0 for wid in proc.complex_enzyme_wids}},
        "requests": {proc.name: {wid: 0.0 for wid in proc.substrate_wids}},
        "substrates_allocated": {proc.name: {wid: 1000.0 for wid in proc.substrate_wids}},
    }
    return proc, proc.next_update(1.0, state)


def _activate_protein_processing_ii(*, live_enzymes: bool = True) -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess

    proc = KarrProteinProcessingIIProcess({})
    fixture = loadmat(
        _REPO_ROOT / "data/karr_fixtures/per_process/ProteinProcessingII_flat.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    compartments = ("c", "d", "e", "m", "tc", "tm")
    enzyme_wids = _parse_wid_array(fixture.enzymeWholeCellModelIDs)
    enzyme_counts = np.asarray(fixture.enzymes, dtype=float).reshape(-1)
    enzyme_compartments = np.asarray(fixture.enzymeMonomerCompartmentIndexs, dtype=int).reshape(-1)
    count_per_wid = 2.0  # Synthetic activation, unchanged from the original guard.
    capacities = (
        enzyme_counts[int(fixture.enzymeIndexs_signalPeptidase) - 1]
        * float(fixture.lipoproteinSignalPeptidaseSpecificRate),
        enzyme_counts[int(fixture.enzymeIndexs_diacylglycerylTransferase) - 1]
        * float(fixture.lipoproteinDiacylglycerylTransferaseSpecificRate),
    )
    required_duration = max(
        count_per_wid * (
            np.atleast_1d(fixture.lipoproteinMonomerIndexs).size
            + np.atleast_1d(fixture.secretedMonomerIndexs).size
        ) / capacities[0],
        count_per_wid * np.atleast_1d(fixture.lipoproteinMonomerIndexs).size / capacities[1],
    )
    # Keep the every-WID assertions with the actual fixture enzyme vector:
    # a synthetic saturating duration, not inflated biology or default-chassis evidence.
    fixture_step = float(fixture.stepSizeSec)
    proc.parameters["time_step"] = float(np.ceil(required_duration / fixture_step)) * fixture_step
    state = {
        "protein": {
            "counts": {},
            "processed_counts": {
                wid: 0.0 for wid in proc.processed_monomer_wids if wid not in MIGRATED_WIDS
            },
            "unfolded_counts": {
                wid: 0.0 for wid in proc.processed_monomer_wids if wid not in MIGRATED_WIDS
            },
            "signal_sequence_counts": {
                wid: 0.0 for wid in proc.signal_sequence_monomer_wids if wid not in MIGRATED_WIDS
            },
            "enzyme_counts": {wid: 100000.0 for wid in proc.enzyme_wids},
            "compartment_counts": {
                "processed_i": {
                    wid: {c: 0.0 for c in ("c", "d", "e", "m", "tc", "tm")}
                    for wid in MIGRATED_WIDS
                },
                "processed_ii": {
                    wid: {c: 0.0 for c in ("c", "d", "e", "m", "tc", "tm")}
                    for wid in MIGRATED_WIDS
                },
                "mature": {
                    wid: {
                        c: float(count) if live_enzymes and c == compartments[int(comp) - 1] else 0.0
                        for c in compartments
                    }
                    for wid, comp, count in zip(
                        enzyme_wids, enzyme_compartments, enzyme_counts, strict=True
                    )
                },
            },
        },
        "processedMonomers": {wid: 0.0 for wid in proc.processed_monomer_wids},
        "unprocessedMonomers": {wid: 0.0 for wid in proc.unprocessed_monomer_wids},
        "requests": {proc.name: {wid: 0.0 for wid in proc.substrate_wids}},
        "substrates_allocated": {proc.name: {wid: 100000.0 for wid in proc.substrate_wids}},
    }
    for wid in MIGRATED_WIDS:
        home = proc.migrated_compartment_by_wid[wid]
        state["protein"]["compartment_counts"]["processed_i"][wid][home] = count_per_wid
    return proc, proc.next_update(1.0, state)


def _activate_protein_folding() -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess

    proc = KarrProteinFoldingProcess({})
    state = {
        "substrates": {wid: 1000.0 for wid in proc.substrate_wids},
        "substrates_allocated": {proc.name: {wid: 1000.0 for wid in proc.substrate_wids}},
        "requests": {proc.name: {wid: 0.0 for wid in proc.substrate_wids}},
        "complex": {"counts": {wid: 1000.0 for wid in proc.complex_enzyme_wids}},
        "protein": {
            "counts": {wid: 1000.0 for wid in proc.protein_enzyme_wids},
            "enzyme_counts": {wid: 1000.0 for wid in proc.protein_enzyme_wids},
            "unfolded_counts": {
                wid: 5.0 for wid in proc.unfolded_monomer_wids if wid not in MIGRATED_WIDS
            },
            "compartment_counts": {
                "processed_ii": {
                    wid: {
                        c: (5.0 if c == proc.migrated_compartment_by_wid[wid] else 0.0)
                        for c in ("c", "d", "e", "m", "tc", "tm")
                    }
                    for wid in MIGRATED_WIDS
                },
                "folded": {
                    wid: {c: 0.0 for c in ("c", "d", "e", "m", "tc", "tm")}
                    for wid in MIGRATED_WIDS
                },
            },
        },
    }
    return proc, proc.next_update(1.0, state)


def _activate_protein_modification(wrapper: str | None = None) -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.karr_protein_modification import (
        KarrProteinModificationEvolutionStep,
        KarrProteinModificationProcess,
        KarrProteinModificationRequestProcess,
    )

    owner = (
        KarrProteinModificationRequestProcess({})
        if wrapper
        else KarrProteinModificationProcess({})
    )
    proc = owner
    state = {
        "substrates": {wid: 10000.0 for wid in proc.substrate_wids},
        "substrates_allocated": {proc.name: {wid: 10000.0 for wid in proc.substrate_wids}},
        "requests": {proc.name: {wid: 0.0 for wid in proc.substrate_wids}},
        "complex": {"counts": {wid: 1000.0 for wid in proc.complex_enzyme_wids}},
        "protein": {
            "counts": {wid: 1000.0 for wid in proc.monomer_enzyme_wids},
            "enzyme_counts": {wid: 1000.0 for wid in proc.monomer_enzyme_wids},
            "unmodified_counts": {
                wid: 5.0 for wid in proc.unmodified_monomer_wids if wid not in MIGRATED_WIDS
            },
            "modified_counts": {
                wid: 0.0 for wid in proc.modified_monomer_wids if wid not in MIGRATED_WIDS
            },
            "compartment_counts": {
                "folded": {
                    wid: {
                        c: (5.0 if c == proc.migrated_compartment_by_wid[wid] else 0.0)
                        for c in ("c", "d", "e", "m", "tc", "tm")
                    }
                    for wid in MIGRATED_WIDS
                },
                "mature": {
                    wid: {c: 0.0 for c in ("c", "d", "e", "m", "tc", "tm")}
                    for wid in MIGRATED_WIDS
                },
            },
        },
    }
    if wrapper:
        state["phase"] = {"request_ready": True}
    if wrapper == "evolution":
        proc = KarrProteinModificationEvolutionStep({"modification_process": owner})
        assert proc._modification_process is owner
        assert proc.ports_schema()["protein"] == owner.ports_schema()["protein"]
    return proc, proc.next_update(1.0, state)


def _activate_protein_modification_request() -> tuple[Any, dict[str, Any]]:
    return _activate_protein_modification("request")


def _activate_protein_modification_evolution() -> tuple[Any, dict[str, Any]]:
    return _activate_protein_modification("evolution")


def _activate_protein_translocation() -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.karr_protein_translocation import (
        KarrProteinTranslocationProcess,
    )

    proc = KarrProteinTranslocationProcess({})
    test_wids = ["MG_014_MONOMER", "MG_191_MONOMER", "MG_032_MONOMER"]
    state = {
        "substrates": {wid: 10000.0 for wid in proc.substrate_wids},
        "complex": {"counts": {wid: 1000.0 for wid in proc.complex_count_wids}},
        "protein": {
            "counts": {"MG_297_MONOMER": 1000.0},
            "compartment_counts": {
                "processed_i": {
                    wid: {
                        c: (2.0 if c == "c" and wid in test_wids else 0.0)
                        for c in ("c", "d", "e", "m", "tc", "tm")
                    }
                    for wid in proc.translocatable_wids
                }
            },
        },
        "requests": {proc.name: {wid: 0.0 for wid in proc.request_wids}},
        "substrates_allocated": {proc.name: {wid: 10000.0 for wid in proc.vector_wids}},
    }
    return proc, proc.next_update(1.0, state)


def _activate_protein_decay_light() -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess

    proc = ProteinDecayLightProcess({})
    state = {
        "complex": {"counts": {wid: 1000000.0 for wid in proc.complex_wids}},
        "protein": {
            "counts": {wid: 1000000.0 for wid in proc.protein_wids if wid not in MIGRATED_WIDS},
        },
        "substrates": {wid: 1e9 for wid in proc.substrate_wids},
    }
    return proc, proc.next_update(1000.0, state)


def _activate_terminal_organelle_assembly() -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.karr_terminal_organelle_assembly import (
        KarrTerminalOrganelleAssemblyProcess,
    )

    proc = KarrTerminalOrganelleAssemblyProcess({})
    state = {
        "protein": {
            "compartment_counts": {
                "mature": {
                    wid: {
                        proc.unincorporated_compartment_by_wid[wid]: 10.0,
                        proc.incorporated_compartment_by_wid[wid]: 0.0,
                    }
                    for wid in proc.component_wids
                }
            }
        }
    }
    return proc, proc.next_update(1.0, state)


def _activate_protein_flat_projection() -> tuple[Any, dict[str, Any]]:
    from opencell.vivarium.protein_flat_projection_step import ProteinFlatProjectionStep

    step = ProteinFlatProjectionStep({})
    state = {
        "protein": {
            "compartment_counts": {
                "mature": {
                    wid: {"c": 5.0, "d": 0.0, "e": 0.0, "m": 0.0, "tc": 0.0, "tm": 0.0}
                    for wid in MIGRATED_WIDS
                }
            }
        }
    }
    return step, step.next_update(1.0, state)


def test_c5_declared_writes_only() -> None:
    """Claim C5: Activate every scoped protein writer named by the Stage 2 design,

    call real next_update, flatten actual emitted protein leaf paths, and prove every
    emitted path is declared and no migrated WID is emitted on legacy branches.
    Also proves no empty-schema trick (empty dict in ports_schema to bypass checks).
    """
    activators = (
        _activate_translation_v3,
        _activate_protein_processing_i,
        _activate_protein_processing_ii,
        _activate_protein_folding,
        _activate_protein_modification,
        _activate_protein_modification_request,
        _activate_protein_modification_evolution,
        _activate_protein_translocation,
        _activate_protein_decay_light,
        _activate_terminal_organelle_assembly,
        _activate_protein_flat_projection,
    )

    all_violations: list[str] = []
    for activate_fn in activators:
        proc, update = activate_fn()
        violations = _verify_emitted_protein_update(proc, update)
        all_violations.extend(violations)

        # Also check for empty-schema trick in ports_schema
        schema = proc.ports_schema()
        protein_schema = schema.get("protein", {})
        for branch, decl in protein_schema.items():
            if isinstance(decl, dict) and len(decl) == 0:
                all_violations.append(
                    f"{proc.name}: declares empty dict for branch protein.{branch!r} (empty-schema trick)"
                )

    assert not all_violations, (
        "Claim C5 violation: emitted undeclared writes, emitted migrated WIDs on legacy branches, "
        "or detected empty-schema trick:\n"
        + "\n".join(all_violations)
    )


def test_canary_c5_rejects_undeclared_migrated_wid_write() -> None:
    """Canary B1: Reject broken process that emits an undeclared migrated-WID write

    on a legacy branch (reviewer planted {"protein": {"counts": {migrated_wid: 1.0}}} in PPII).
    Must fail based on actual emitted update paths, not class/source inspection.
    """
    from opencell.vivarium.karr_protein_processing_ii import (
        KarrProteinProcessingIIProcess,
    )

    proc = KarrProteinProcessingIIProcess({})
    migrated_wid = next(iter(sorted(MIGRATED_WIDS)))

    # Plant undeclared write on legacy counts branch
    broken_update = {
        "protein": {
            "counts": {migrated_wid: 1.0},
        }
    }
    violations = _verify_emitted_protein_update(proc, broken_update)
    assert violations, "Canary failed: audit must reject undeclared migrated WID write on legacy branch"
    assert any("counts" in v and migrated_wid in v for v in violations), (
        f"Expected violation naming 'counts' and {migrated_wid}, got {violations}"
    )


def test_c2b_no_fake_empty_counts_declaration_in_pp2() -> None:
    """Guard against hollow-green test gaming: KarrProteinProcessingIIProcess must NOT

    declare a fake empty 'counts': {} in ports_schema solely to pass AST checks while
    leaving dynamic writes active.
    Stage 1 authorization covers only the 8 migrated WIDs; non-migrated dynamic writes
    remain out of scope/PPII blocker and must not be masked by a fake empty declaration.
    """
    from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess

    proc = KarrProteinProcessingIIProcess({})
    schema = proc.ports_schema()
    protein_schema = schema.get("protein", {})
    if "counts" in protein_schema:
        counts_decl = protein_schema["counts"]
        assert counts_decl != {}, (
            "KarrProteinProcessingIIProcess declares a fake empty 'counts': {} in ports_schema. "
            "An empty counts dict is test gaming to satisfy branch-level AST checks while leaving "
            "undeclared dynamic writes active. Stage 1 requires no fake empty counts declaration."
        )


def test_c2b_migrated_wids_never_emitted_to_legacy_branches() -> None:
    """Claim C2b: Proves actual Stage-1 property via dynamic execution: no migrated WID can be

    emitted through any legacy flat/queue branch, especially PP2's dynamic protein.counts;
    migrated PP2 deltas route strictly through compartment_counts.processed_i and processed_ii
    at biological compartments.
    """
    proc, update = _activate_protein_processing_ii()
    prot_update = update.get("protein", {})

    # 1. No migrated WID may appear in any legacy flat/queue branch
    for branch_name in ("counts", "processed_counts", "unfolded_counts", "signal_sequence_counts"):
        if branch_name in prot_update:
            branch_dict = prot_update[branch_name]
            intersection = set(branch_dict.keys()) & MIGRATED_WIDS
            assert not intersection, (
                f"Migrated WIDs {sorted(intersection)} emitted into legacy branch {branch_name!r}"
            )

    # 2. Migrated deltas must appear in compartment_counts processed_i and processed_ii
    assert "compartment_counts" in prot_update, "compartment_counts missing from PP2 update for migrated WIDs"
    comp_update = prot_update["compartment_counts"]
    assert "processed_i" in comp_update and "processed_ii" in comp_update, (
        "PP2 must emit both processed_i and processed_ii under compartment_counts for migrated WIDs"
    )
    for wid in MIGRATED_WIDS:
        has_pi = wid in comp_update["processed_i"]
        has_pii = wid in comp_update["processed_ii"]
        assert has_pi and has_pii, f"Expected compartment_counts delta for {wid} in PP2"


def test_pp2_shadow_enzymes_do_not_activate_migrated_peptides() -> None:
    """A large compatibility shadow must not replace absent live mature enzymes."""
    proc, update = _activate_protein_processing_ii(live_enzymes=False)
    protein = update.get("protein", {})
    assert update.get("substrates", {}) == {}
    for index in proc.peptidase_indices:
        wid = proc.unprocessed_monomer_wids[int(index)]
        for form in ("processed_i", "processed_ii", "signal_sequence"):
            assert wid not in protein.get("compartment_counts", {}).get(form, {})
    for branch in ("counts", "processed_counts", "unfolded_counts", "signal_sequence_counts"):
        assert not set(protein.get(branch, {})) & MIGRATED_WIDS


def test_qo2_dna_supercoiling_does_not_intersect_migrated_wids() -> None:
    """Probe B (QO2): KarrDNASupercoilingProcess protein.counts WID set must NOT

    intersect the 8 TOA MIGRATED_WIDS.
    """
    from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess

    proc = KarrDNASupercoilingProcess({})
    schema = proc.ports_schema()
    counts_wids = set(schema.get("protein", {}).get("counts", {}).keys())
    enzyme_wids = set(proc.protein_enzyme_wids)
    all_dnas_protein_wids = counts_wids | enzyme_wids

    intersection = all_dnas_protein_wids & MIGRATED_WIDS
    assert not intersection, (
        f"KarrDNASupercoilingProcess protein WIDs unexpectedly intersect MIGRATED_WIDS: {sorted(intersection)}"
    )
