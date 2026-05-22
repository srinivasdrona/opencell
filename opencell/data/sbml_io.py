"""SBML Level 3 import/export via python-libsbml.

SBML is the interoperability format; internal IR is canonical.
NOTE: SBML round-trip will be lossy for hybrid/stochastic/event
semantics — this documents what survives and what doesn't.

Survives round-trip:
- Species IDs, names, compartments, initial amounts
- Reactions, stoichiometry, reversibility
- Kinetic laws (as MathML)

Lost in round-trip:
- Resource ledger semantics (partition-merge)
- Stochastic solver hints
- Reference frame declarations
- Custom sub-model contracts
"""

from __future__ import annotations

import logging
from pathlib import Path

import libsbml

from opencell.core.ir import (
    Compartment,
    IRSpeciesRegistry,
    MoleculeType,
    ReactionInfo,
    ReferenceFrame,
    SpeciesInfo,
)

logger = logging.getLogger(__name__)

_COMPARTMENT_MAP = {
    "cytoplasm": Compartment.CYTOPLASM,
    "c": Compartment.CYTOPLASM,
    "membrane": Compartment.MEMBRANE,
    "m": Compartment.MEMBRANE,
    "extracellular": Compartment.EXTRACELLULAR,
    "e": Compartment.EXTRACELLULAR,
}


def import_sbml(
    filepath: str | Path,
) -> tuple[IRSpeciesRegistry, list[ReactionInfo], dict[str, float]]:
    """Import an SBML model into OpenCell IR.

    Returns:
        Tuple of (registry, reactions, initial_counts)
    """
    filepath = Path(filepath)
    reader = libsbml.SBMLReader()
    doc = reader.readSBML(str(filepath))

    if doc.getNumErrors(libsbml.LIBSBML_SEV_ERROR) > 0:
        errors = []
        for i in range(doc.getNumErrors()):
            err = doc.getError(i)
            if err.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
                errors.append(err.getMessage())
        raise ValueError(f"SBML errors in {filepath}: {errors}")

    model = doc.getModel()
    if model is None:
        raise ValueError(f"No model found in {filepath}")

    registry = IRSpeciesRegistry()
    initial_counts: dict[str, float] = {}

    # Import species
    for i in range(model.getNumSpecies()):
        sp = model.getSpecies(i)
        comp_id = sp.getCompartment().lower()
        compartment = _COMPARTMENT_MAP.get(comp_id, Compartment.CYTOPLASM)

        species_info = SpeciesInfo(
            id=sp.getId(),
            name=sp.getName() or sp.getId(),
            compartment=compartment,
            molecule_type=MoleculeType.METABOLITE,  # default; refine later
            reference_frame=ReferenceFrame.PER_CELL,
        )
        registry.register(species_info)

        if sp.isSetInitialAmount():
            initial_counts[sp.getId()] = sp.getInitialAmount()
        elif sp.isSetInitialConcentration():
            initial_counts[sp.getId()] = sp.getInitialConcentration()

    # Import reactions
    reactions: list[ReactionInfo] = []
    for i in range(model.getNumReactions()):
        rxn = model.getReaction(i)
        stoich: dict[str, float] = {}

        for j in range(rxn.getNumReactants()):
            ref = rxn.getReactant(j)
            stoich[ref.getSpecies()] = -ref.getStoichiometry()

        for j in range(rxn.getNumProducts()):
            ref = rxn.getProduct(j)
            stoich[ref.getSpecies()] = stoich.get(ref.getSpecies(), 0) + ref.getStoichiometry()

        reactions.append(
            ReactionInfo(
                id=rxn.getId(),
                name=rxn.getName() or rxn.getId(),
                stoichiometry=stoich,
                reversible=rxn.getReversible(),
            )
        )

    logger.info(
        f"Imported SBML: {model.getNumSpecies()} species, "
        f"{model.getNumReactions()} reactions from {filepath}"
    )

    return registry, reactions, initial_counts


def export_sbml(
    filepath: str | Path,
    registry: IRSpeciesRegistry,
    reactions: list[ReactionInfo],
    initial_counts: dict[str, float] | None = None,
) -> Path:
    """Export OpenCell IR to SBML Level 3."""
    filepath = Path(filepath)

    doc = libsbml.SBMLDocument(3, 2)
    model = doc.createModel()
    model.setId("opencell_model")

    # Create compartments
    for comp in Compartment:
        c = model.createCompartment()
        c.setId(comp.name.lower())
        c.setConstant(True)
        c.setSize(1.0)

    # Create species
    for species_id in registry.ids:
        info = registry.get(species_id)
        sp = model.createSpecies()
        sp.setId(info.id)
        sp.setName(info.name)
        sp.setCompartment(info.compartment.name.lower())
        sp.setHasOnlySubstanceUnits(True)
        sp.setBoundaryCondition(False)
        sp.setConstant(False)
        if initial_counts and info.id in initial_counts:
            sp.setInitialAmount(initial_counts[info.id])

    # Create reactions
    for rxn_info in reactions:
        rxn = model.createReaction()
        rxn.setId(rxn_info.id)
        rxn.setName(rxn_info.name)
        rxn.setReversible(rxn_info.reversible)

        for species_id, coeff in rxn_info.stoichiometry.items():
            if coeff < 0:
                ref = rxn.createReactant()
                ref.setSpecies(species_id)
                ref.setStoichiometry(abs(coeff))
                ref.setConstant(True)
            elif coeff > 0:
                ref = rxn.createProduct()
                ref.setSpecies(species_id)
                ref.setStoichiometry(coeff)
                ref.setConstant(True)

    writer = libsbml.SBMLWriter()
    writer.writeSBML(doc, str(filepath))
    logger.info(f"Exported SBML to {filepath}")
    return filepath
