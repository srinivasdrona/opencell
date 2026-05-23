from __future__ import annotations

import importlib
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from vivarium.core.process import Process

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

_MODULE_SPECS = (
    ("pc-t1-ref", "opencell.vivarium.karr_replication_initiation", "opencell/vivarium/karr_replication_initiation.py"),
    ("pc-t2", "opencell.vivarium.karr_replication", "opencell/vivarium/karr_replication.py"),
    ("pc-t3", "opencell.vivarium.karr_dna_supercoiling", "opencell/vivarium/karr_dna_supercoiling.py"),
    ("pc-t4", "opencell.vivarium.karr_chromosome_condensation", "opencell/vivarium/karr_chromosome_condensation.py"),
    ("pc-t5", "opencell.vivarium.karr_chromosome_segregation", "opencell/vivarium/karr_chromosome_segregation.py"),
    ("pc-t6", "opencell.vivarium.karr_dna_damage", "opencell/vivarium/karr_dna_damage.py"),
    ("pc-t7", "opencell.vivarium.karr_dna_repair", "opencell/vivarium/karr_dna_repair.py"),
    ("pc-t8", "opencell.vivarium.karr_ftsz_polymerization", "opencell/vivarium/karr_ftsz_polymerization.py"),
    ("pc-t9", "opencell.vivarium.karr_cytokinesis", "opencell/vivarium/karr_cytokinesis.py"),
    ("pc-t10", "opencell.vivarium.karr_terminal_organelle_assembly", "opencell/vivarium/karr_terminal_organelle_assembly.py"),
    ("pd-t1", "opencell.vivarium.karr_host_interaction", "opencell/vivarium/karr_host_interaction.py"),
)

_TARGET_PORTS = {"chromosome", "cell", "substrates", "requests", "substrates_allocated"}

# Keep empty by default; cross-process key conflicts should be fixed, not allowlisted.
_KNOWN_UPDATER_CONFLICT_ALLOWLIST: set[str] = set()


def _flatten_schema(node: Any, prefix: list[str]) -> list[tuple[list[str], Any, Any]]:
    rows: list[tuple[list[str], Any, Any]] = []
    if isinstance(node, dict):
        if "_default" in node or "_updater" in node:
            rows.append((prefix, node.get("_default", None), node.get("_updater", None)))
        else:
            for key, value in node.items():
                rows.extend(_flatten_schema(value, [*prefix, str(key)]))
    return rows


@lru_cache(maxsize=1)
def _scan_matrix() -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    missing_modules: list[str] = []
    module_source: dict[str, str] = {}

    for process_id, module_name, rel_path in _MODULE_SPECS:
        if not (_REPO_ROOT / rel_path).exists():
            missing_modules.append(process_id)
            continue

        module = importlib.import_module(module_name)
        process_classes = [
            obj
            for obj in vars(module).values()
            if isinstance(obj, type) and issubclass(obj, Process) and obj is not Process
        ]
        assert process_classes, f"No Process subclass found in {module_name}"
        process_cls = process_classes[0]
        process = process_cls()
        schema = process.ports_schema()

        module_source[process_id] = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")

        for port_name, port_node in schema.items():
            if port_name not in _TARGET_PORTS:
                continue
            for path_parts, default, updater in _flatten_schema(port_node, [port_name]):
                rows.append(
                    {
                        "process": process_id,
                        "module": module_name,
                        "leaf_path": ".".join(path_parts),
                        "default": default,
                        "updater": updater,
                    }
                )

    return rows, missing_modules, module_source


def test_all_state_leaves_have_single_declaration_or_consistent_updaters() -> None:
    rows, _, _ = _scan_matrix()

    by_leaf: dict[str, set[str]] = {}
    for row in rows:
        leaf = row["leaf_path"]
        if not (leaf.startswith("chromosome.") or leaf.startswith("cell.")):
            continue
        by_leaf.setdefault(leaf, set()).add(str(row["updater"]))

    conflicts = {
        leaf: sorted(updaters)
        for leaf, updaters in by_leaf.items()
        if len(updaters) > 1
    }
    unexpected_conflicts = {
        leaf: updaters
        for leaf, updaters in conflicts.items()
        if leaf not in _KNOWN_UPDATER_CONFLICT_ALLOWLIST
    }
    assert not unexpected_conflicts, f"Unexpected updater conflicts: {unexpected_conflicts}"


def test_chromosome_replication_state_value_domain() -> None:
    rows, _, module_source = _scan_matrix()

    expected_domain = {"idle", "initiating", "elongating", "complete"}
    processes_declaring_replication_state = {
        row["process"]
        for row in rows
        if row["leaf_path"] == "chromosome.replication_state"
    }

    domain_by_process: dict[str, set[str]] = {}
    for process_id in processes_declaring_replication_state:
        source = module_source.get(process_id, "")
        values = set(
            re.findall(r"""["']replication_state["']\s*:\s*["']([^"']+)["']""", source)
        )
        values.update(
            re.findall(r"""replication_state\s*[!=]=\s*["']([^"']+)["']""", source)
        )
        for body in re.findall(r"""replication_state\s+in\s+\{([^}]*)\}""", source):
            values.update(re.findall(r"""["']([^"']+)["']""", body))
        if values:
            domain_by_process[process_id] = values

    assert domain_by_process, "No replication_state value-domain usage found"
    for process_id, values in domain_by_process.items():
        assert values.issubset(expected_domain), (
            f"{process_id} uses out-of-domain replication_state values: {sorted(values)}"
        )

    observed_union = set().union(*domain_by_process.values())
    assert observed_union == expected_domain, (
        f"Observed replication_state domain {sorted(observed_union)} != expected {sorted(expected_domain)}"
    )


def test_substrate_keys_are_consistent_case() -> None:
    rows, _, _ = _scan_matrix()

    tokens: list[str] = []
    for row in rows:
        leaf = row["leaf_path"]
        if leaf.startswith("substrates.") or leaf.startswith("requests.") or leaf.startswith("substrates_allocated."):
            tokens.append(leaf.split(".")[-1])

    case_map: dict[str, set[str]] = {}
    for token in tokens:
        case_map.setdefault(token.lower(), set()).add(token)

    mixed = {k: sorted(v) for k, v in case_map.items() if len(v) > 1}
    assert not mixed, f"Mixed-case substrate/request tokens detected: {mixed}"
