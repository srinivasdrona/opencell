"""Allocator default-key consistency checks for enrolled consumers."""

from __future__ import annotations

from opencell.vivarium.karr_allocation_step import KarrAllocationStep
from opencell.vivarium.karr_macromolecular_complexation import MacromolecularComplexationProcess
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess
from opencell.vivarium.karr_rna_decay import RnaDecayLightProcess


def test_allocator_default_keys_match_consumer_process_names() -> None:
    step = KarrAllocationStep({})
    configured = {str(proc_name) for proc_name, _ in step.parameters["consumer_processes"]}
    expected = {
        MacromolecularComplexationProcess.name,
        ProteinDecayLightProcess.name,
        RnaDecayLightProcess.name,
    }
    assert configured == expected
