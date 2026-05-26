"""A4 L3 request/allocation vector coverage for supercoiling + translocation."""

from __future__ import annotations

import sys
from pathlib import Path

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

from opencell.vivarium.karr_allocation_step import KarrAllocationStep


def _make_step(consumer_processes: list[tuple[str, list[str]]]) -> KarrAllocationStep:
    substrate_wids = sorted(
        {
            wid
            for _, wids in consumer_processes
            for wid in wids
        }
        | {"ATP", "GTP", "ADP", "GDP", "PI", "H2O", "H"}
    )
    return KarrAllocationStep(
        {
            "consumer_processes": consumer_processes,
            "substrate_wids": substrate_wids,
        }
    )


def test_a4_dna_supercoiling_vector_hardening_adds_h2o_member() -> None:
    step = _make_step([("karr_dna_supercoiling", ["ATP"])])

    consumers = dict(step.parameters["consumer_processes"])
    assert consumers["karr_dna_supercoiling"] == ["ATP", "H2O"]

    req_schema = step.ports_schema()["requests"]["karr_dna_supercoiling"]
    alloc_schema = step.ports_schema()["substrates_allocated"]["karr_dna_supercoiling"]
    assert set(req_schema) == {"ATP", "H2O"}
    assert set(alloc_schema) == {"ATP", "H2O"}


def test_a4_protein_translocation_vector_hardening_expands_to_full_vector() -> None:
    step = _make_step([("karr_protein_translocation", ["ATP"])])

    consumers = dict(step.parameters["consumer_processes"])
    assert set(consumers["karr_protein_translocation"]) == {
        "ATP",
        "GTP",
        "ADP",
        "GDP",
        "PI",
        "H2O",
        "H",
    }

    req_schema = step.ports_schema()["requests"]["karr_protein_translocation"]
    alloc_schema = step.ports_schema()["substrates_allocated"]["karr_protein_translocation"]
    assert set(req_schema) == set(consumers["karr_protein_translocation"])
    assert set(alloc_schema) == set(consumers["karr_protein_translocation"])


def test_a4_vector_hardening_preserves_existing_members_and_order() -> None:
    step = _make_step(
        [
            ("karr_protein_translocation", ["ATP", "ATP", "CUSTOM_MARKER"]),
            ("unrelated_process", ["ATP"]),
        ]
    )

    consumers = dict(step.parameters["consumer_processes"])
    assert consumers["karr_protein_translocation"][0:2] == ["ATP", "CUSTOM_MARKER"]
    assert set(consumers["karr_protein_translocation"]) == {
        "ATP",
        "CUSTOM_MARKER",
        "GTP",
        "ADP",
        "GDP",
        "PI",
        "H2O",
        "H",
    }
    assert consumers["unrelated_process"] == ["ATP"]


def test_a4_vector_hardening_does_not_enroll_absent_consumers() -> None:
    step = _make_step([("unrelated_process", ["ATP"])])
    consumers = dict(step.parameters["consumer_processes"])

    assert "karr_dna_supercoiling" not in consumers
    assert "karr_protein_translocation" not in consumers
