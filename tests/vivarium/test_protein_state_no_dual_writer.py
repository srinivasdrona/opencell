from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
import sys

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

MIGRATED_WIDS = frozenset({
    "MG_191_MONOMER",
    "MG_192_MONOMER",
    "MG_217_MONOMER",
    "MG_218_MONOMER",
    "MG_312_MONOMER",
    "MG_317_MONOMER",
    "MG_318_MONOMER",
    "MG_386_MONOMER",
})

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
    ("opencell.vivarium.karr_protein_modification", "KarrProteinModificationProcess", ("unmodified_counts", "modified_counts"), "MIGRATABLE-W"),
    ("opencell.vivarium.karr_protein_translocation", "KarrProteinTranslocationProcess", ("unprocessed_counts", "location"), "MIGRATABLE-W"),
    ("opencell.vivarium.karr_protein_decay_light", "ProteinDecayLightProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.karr_terminal_organelle_assembly", "KarrTerminalOrganelleAssemblyProcess", (), "AUTH-W"),
    ("opencell.vivarium.karr_ribosome_assembly", "KarrRibosomeAssemblyProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.karr_chromosome_segregation", "KarrChromosomeSegregationProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.karr_replication_initiation", "KarrReplicationInitiationProcess", ("counts",), "AUTH-W"),
    ("opencell.vivarium.karr_dna_supercoiling", "KarrDNASupercoilingProcess", ("counts",), "AUTH-W"),
    # Readers (DERIVED-R) / Excluded
    ("opencell.vivarium.karr_dna_repair", "KarrDNARepairProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_host_interaction", "KarrHostInteractionProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_observability_step", "KarrObservabilityStep", (), "DERIVED-R"),
    ("opencell.vivarium.karr_protein_activation", "KarrProteinActivationProcess", (), "DERIVED-R/STAGE-4"),
    ("opencell.vivarium.karr_request_calculators", "RequestCalculatorPTransloc", (), "DERIVED-R"),
    ("opencell.vivarium.karr_request_calculators", "RequestCalculatorProteinPathway", (), "DERIVED-R"),
    ("opencell.vivarium.karr_request_calculators", "RequestCalculatorRibAsm", (), "DERIVED-R"),
    ("opencell.vivarium.karr_rna_modification", "KarrRNAModificationProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_rna_processing", "KarrRNAProcessingProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_transcriptional_regulation", "KarrTranscriptionalRegulationProcess", (), "DERIVED-R"),
    ("opencell.vivarium.karr_trna_aminoacylation", "KarrTRNAAminoacylationProcess", (), "DERIVED-R"),
    # Legacy non-runtime modules
    ("opencell.vivarium.karr_translation", "KarrTranslationProcess", (), "LEGACY"),
    ("opencell.vivarium.karr_translation_v2", "KarrTranslationV2Process", (), "LEGACY"),
)


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
            # instantiate with default/empty params
            proc = cls({})
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


def test_c2_legacy_leaves_exclude_migrated_wids() -> None:
    """Claim C2: For every module in manifest, legacy writable branches must NOT contain

    any of the 8 MIGRATED_WIDS.
    """
    violations: list[str] = []

    for mod_name, cls_name, branches, _ in PROTEIN_PROCESS_MANIFEST:
        if not branches:
            continue
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
        try:
            proc = cls({})
            schema = proc.ports_schema()
        except Exception as exc:
            violations.append(f"{cls_name}: failed to instantiate ports_schema: {exc}")
            continue

        protein_schema = schema.get("protein", {})
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
        "Claim C2 violation: migrated WIDs must be removed from all legacy writable branches:\n"
        + "\n".join(violations)
    )


def test_c2b_declared_writes_only_ast_scan() -> None:
    """Claim C2b: AST scan over opencell/vivarium/*.py: for each Process,

    all protein leaf branches written in next_update / _build_update must be
    declared in ports_schema().
    Kills undeclared writes (such as karr_protein_processing_ii M08 writing undeclared 'counts').
    """
    vivarium_dir = _REPO_ROOT / "opencell" / "vivarium"
    violations: list[str] = []

    for py_file in sorted(vivarium_dir.glob("*.py")):
        if py_file.name.startswith(("_", "test")):
            continue
        source_text = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Search for methods that build updates
                update_methods = [
                    m for m in node.body
                    if isinstance(m, ast.FunctionDef) and m.name in ("next_update", "_build_update")
                ]
                if not update_methods:
                    continue

                written_protein_branches: set[str] = set()
                # Track variables assigned to update["protein"]
                protein_dict_vars: set[str] = set()

                for method in update_methods:
                    for sub in ast.walk(method):
                        # Detect update["protein"] = <var>
                        if isinstance(sub, ast.Assign):
                            for target in sub.targets:
                                if (
                                    isinstance(target, ast.Subscript)
                                    and isinstance(target.slice, ast.Constant)
                                    and target.slice.value == "protein"
                                    and isinstance(sub.value, ast.Name)
                                ):
                                    protein_dict_vars.add(sub.value.id)

                        # Direct dict literal: update["protein"] = { "branch": ... }
                        if isinstance(sub, ast.Dict):
                            for key, val in zip(sub.keys, sub.values, strict=False):
                                if isinstance(key, ast.Constant) and key.value == "protein" and isinstance(val, ast.Dict):
                                    for subkey in val.keys:
                                        if isinstance(subkey, ast.Constant) and isinstance(subkey.value, str):
                                            written_protein_branches.add(subkey.value)
                        # Direct subscript: update["protein"]["branch"] = ...
                        elif (
                            isinstance(sub, ast.Subscript)
                            and isinstance(sub.value, ast.Subscript)
                            and isinstance(sub.value.slice, ast.Constant)
                            and sub.value.slice.value == "protein"
                            and isinstance(sub.slice, ast.Constant)
                            and isinstance(sub.slice.value, str)
                        ):
                            written_protein_branches.add(sub.slice.value)

                # Second pass: detect <protein_dict_var>["branch"] = ...
                for method in update_methods:
                    for sub in ast.walk(method):
                        if isinstance(sub, ast.Assign):
                            for target in sub.targets:
                                if (
                                    isinstance(target, ast.Subscript)
                                    and isinstance(target.value, ast.Name)
                                    and target.value.id in protein_dict_vars
                                    and isinstance(target.slice, ast.Constant)
                                    and isinstance(target.slice.value, str)
                                ):
                                    written_protein_branches.add(target.slice.value)

                if not written_protein_branches:
                    continue

                # Now check ports_schema
                mod_name = f"opencell.vivarium.{py_file.stem}"
                try:
                    mod = importlib.import_module(mod_name)
                    cls = getattr(mod, node.name)
                    proc = cls({})
                    schema = proc.ports_schema()
                    declared_branches = set(schema.get("protein", {}).keys())
                except Exception:
                    # If cannot instantiate directly, do AST check on ports_schema
                    declared_branches = set()
                    for m in node.body:
                        if isinstance(m, ast.FunctionDef) and m.name == "ports_schema":
                            for sub in ast.walk(m):
                                if isinstance(sub, ast.Dict):
                                    for key, val in zip(sub.keys, sub.values, strict=False):
                                        if isinstance(key, ast.Constant) and key.value == "protein" and isinstance(val, ast.Dict):
                                            for subkey in val.keys:
                                                if isinstance(subkey, ast.Constant) and isinstance(subkey.value, str):
                                                    declared_branches.add(subkey.value)


                undeclared = written_protein_branches - declared_branches
                if undeclared:
                    violations.append(
                        f"{py_file.name}::{node.name} writes undeclared protein branch(es) {sorted(undeclared)} "
                        f"(declared: {sorted(declared_branches)})"
                    )

    assert not violations, (
        "Claim C2b violation: processes write protein leaves not declared in ports_schema:\n"
        + "\n".join(violations)
    )



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
