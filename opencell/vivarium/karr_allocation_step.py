"""Vivarium Step implementing Karr's proportional fair-share allocation."""

from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Step

from opencell.m1 import karr_metabolism as km

# Runtime correctness guards (CovertLab pattern; see
# CovertLab/WholeCellEcoliRelease/wholecell/states/bulk_molecules.py).
# Set to False ONLY for performance benchmarking; default-on in all
# normal sim runs so allocation bugs surface at the first offending tick.
ASSERT_POSITIVE_COUNTS = True


class NegativeCountsError(RuntimeError):
    """Raised when the allocator detects a negative molecule count in
    requests, allocations, or the post-allocation unallocated pool.

    The exception message names the offending molecule index (or name,
    if available), the responsible process (if identifiable at the
    checkpoint), and which checkpoint fired (request / allocation /
    unallocated)."""


def _format_matrix_offenders(
    counts: np.ndarray,
    process_names: list[str],
    molecule_names: list[str],
) -> str:
    offender_indices = np.argwhere(counts < 0)
    offender_strings: list[str] = []
    for proc_idx, mol_idx in offender_indices[:5]:
        proc_name = process_names[int(proc_idx)]
        molecule_name = molecule_names[int(mol_idx)]
        value = float(counts[int(proc_idx), int(mol_idx)])
        offender_strings.append(f"{proc_name}/{molecule_name}={value:g}")
    if len(offender_indices) > 5:
        offender_strings.append(f"... (+{len(offender_indices) - 5} more)")
    return ", ".join(offender_strings)


def _format_unallocated_offenders(counts: np.ndarray, molecule_names: list[str]) -> str:
    offender_indices = np.where(counts < 0)[0]
    offender_strings: list[str] = []
    for mol_idx in offender_indices[:5]:
        molecule_name = molecule_names[int(mol_idx)]
        value = float(counts[int(mol_idx)])
        offender_strings.append(f"process=<aggregate>/{molecule_name}={value:g}")
    if len(offender_indices) > 5:
        offender_strings.append(f"... (+{len(offender_indices) - 5} more)")
    return ", ".join(offender_strings)


def _default_substrate_wids() -> list[str]:
    """Return Karr's full substrate WID universe (585 IDs in M1 fixtures)."""
    model = km.load_default()
    return [str(wid) for wid in model.raw["ids"]["substrate_wcm_585"]]


def _default_consumer_processes() -> list[tuple[str, list[str]]]:
    """Default consumers expected for A3.3 allocation integration."""
    return [
        ("karr_macromolecular_complexation", ["ATP", "GTP", "H2O"]),
        ("karr_protein_decay_light", ["ATP", "H2O"]),
        ("karr_rna_decay", ["H2O"]),
    ]


_L3_REQUIRED_VECTOR_MEMBERS: dict[str, tuple[str, ...]] = {
    # Track-A A4 / allocator_audit L3:
    # - DNASupercoiling must request/allocate ATP+H2O
    # - ProteinTranslocation must carry full ATP/GTP hydrolysis vector
    #   (ATP/GTP/ADP/GDP/Pi/H2O/H) in allocator request+allocation schemas.
    "karr_dna_supercoiling": ("ATP", "H2O"),
    "karr_protein_translocation": ("ATP", "GTP", "ADP", "GDP", "PI", "H2O", "H"),
}


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _normalize_consumer_process_vectors(
    consumer_processes: list[tuple[str, list[str]]],
) -> list[tuple[str, list[str]]]:
    normalized: list[tuple[str, list[str]]] = []
    for proc_name_raw, raw_wids in consumer_processes:
        proc_name = str(proc_name_raw)
        wids = _dedupe_preserve_order([str(wid) for wid in raw_wids])
        required = _L3_REQUIRED_VECTOR_MEMBERS.get(proc_name, ())
        # Vector-completeness hardening (A4): only augments consumers already
        # present in this step; no process enrollment is performed here.
        for wid in required:
            if wid not in wids:
                wids.append(wid)
        normalized.append((proc_name, wids))
    return normalized


class KarrAllocationStep(Step):
    """Allocate shared substrates by Karr's per-WID proportional fair share."""

    name = "karr_allocation_step"
    defaults: dict[str, Any] = {
        "consumer_processes": _default_consumer_processes(),
        "substrate_wids": _default_substrate_wids(),
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        configured = list(self.parameters["consumer_processes"])
        self.parameters["consumer_processes"] = _normalize_consumer_process_vectors(configured)

    def ports_schema(self) -> dict[str, Any]:
        consumers = self.parameters["consumer_processes"]
        substrate_wids = self.parameters["substrate_wids"]
        return {
            "substrates": {
                wid: {
                    "_updater": "accumulate",
                    "_default": 0.0,
                    "_emit": False,
                }
                for wid in substrate_wids
            },
            "requests": {
                proc_name: {
                    wid: {
                        "_updater": "set",
                        "_default": 0.0,
                        "_emit": False,
                    }
                    for wid in wids
                }
                for proc_name, wids in consumers
            },
            # Sole-writer exception: this step exclusively writes allocations,
            # so set-updates are safe and replace each tick's values.
            "substrates_allocated": {
                proc_name: {
                    wid: {
                        "_updater": "set",
                        "_default": 0.0,
                        "_emit": False,
                    }
                    for wid in wids
                }
                for proc_name, wids in consumers
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep

        substrates = states.get("substrates", {})
        requests = states.get("requests", {})

        process_names = list(requests.keys())
        all_requested_wids: set[str] = set()
        for reqs_by_wid in requests.values():
            all_requested_wids.update(reqs_by_wid.keys())
        molecule_names = sorted(all_requested_wids)

        if not process_names or not molecule_names:
            return {"substrates_allocated": {}}

        counts_requested = np.zeros((len(process_names), len(molecule_names)), dtype=np.float64)
        for proc_idx, proc_name in enumerate(process_names):
            reqs_by_wid = requests.get(proc_name, {})
            for mol_idx, molecule_name in enumerate(molecule_names):
                counts_requested[proc_idx, mol_idx] = float(reqs_by_wid.get(molecule_name, 0.0))

        if ASSERT_POSITIVE_COUNTS and np.any(counts_requested < 0):
            offenders = _format_matrix_offenders(
                counts_requested,
                process_names,
                molecule_names,
            )
            raise NegativeCountsError(
                f"Negative count(s) in counts_requested at checkpoint=request: {offenders}"
            )

        counts_available = np.array(
            [max(0.0, float(substrates.get(wid, 0.0))) for wid in molecule_names],
            dtype=np.float64,
        )
        counts_requested_clamped = np.maximum(counts_requested, 0.0)
        total_demand = counts_requested_clamped.sum(axis=0)
        counts_scale = np.divide(
            counts_available,
            total_demand,
            out=np.zeros_like(total_demand),
            where=total_demand > 0.0,
        )
        counts_scale = np.minimum(1.0, counts_scale)
        counts_allocated = np.floor(counts_requested_clamped * counts_scale)

        if ASSERT_POSITIVE_COUNTS and np.any(counts_allocated < 0):
            offenders = _format_matrix_offenders(
                counts_allocated,
                process_names,
                molecule_names,
            )
            raise NegativeCountsError(
                f"Negative count(s) in counts_allocated at checkpoint=allocation: {offenders}"
            )

        counts_unallocated = counts_available - counts_allocated.sum(axis=0)
        if ASSERT_POSITIVE_COUNTS and np.any(counts_unallocated < 0):
            offenders = _format_unallocated_offenders(counts_unallocated, molecule_names)
            raise NegativeCountsError(
                f"Negative count(s) in counts_unallocated at checkpoint=unallocated: {offenders}"
            )

        allocations = {
            proc_name: {
                molecule_name: float(counts_allocated[proc_idx, mol_idx])
                for mol_idx, molecule_name in enumerate(molecule_names)
            }
            for proc_idx, proc_name in enumerate(process_names)
        }
        return {"substrates_allocated": allocations}
