"""M. genitalium organism-specific biological constants.

These constants are biology-specific to M. genitalium (Karr 2012 model)
and MUST NOT leak into generic infrastructure. Generic primitives should
accept these as configuration, not import them.

When porting to another organism (JCVI-syn3A, E. coli, etc.), create a
sibling module (e.g., `e_coli_constants.py`) and pass the appropriate
constants via configuration. Do NOT duplicate or override these values
in the new module.

Naming discipline (Day 32, 2026-06-18):
- Generic primitives: descriptive of mechanism (e.g., SparseTripletStore)
- Biology-specific: prefix with organism (e.g., MGenChromosome)
- The rename test: if you added a second organism tomorrow, would this
  class/constant need a rename? If yes, prefix with organism. If no,
  keep generic.

See docs/phase_f/POST_L5_REFACTOR_PLAN.md for the planned reorganization
that will move these into a proper `models/m_genitalium/` namespace.
"""

from __future__ import annotations

# Genome length in base pairs. Karr 2012 M. genitalium G37 genome.
# Used by: ChromosomeStore default shape, DNADamage position sampling,
# DNASupercoiling chromosome length, ReplicationInitiation chromosome length.
GENOME_LENGTH_BP: int = 580_076

# Number of chromosome compartments. Karr models 4 (two parent strands +
# two daughter strands during/after replication).
N_CHROMOSOME_COMPARTMENTS: int = 4

# Number of protein-coding + RNA genes tracked in the M. genitalium model.
# Source: Karr 2012 Knowledge Base (524 genes + 1 placeholder = 525).
N_GENES: int = 525

# Number of protein monomer species in Karr 2012 M. genitalium model.
# Source: Karr 2012 ProteinMonomer fixture (~482 mature monomers).
N_MONOMERS: int = 482

# Number of transcription units (operons + monogenic units).
# Source: Karr 2012 TranscriptionUnit fixture.
N_TRANSCRIPTION_UNITS: int = 335

# Number of RNA species after processing (mature RNAs).
N_PROCESSED_RNAS: int = 347

# Time step in seconds. Karr 2012 uses uniform 1-second discrete ticks.
# Multi-timescale (per-process timesteps) is deferred to Post-L5
# performance optimization phase (see plan.md Post-L5 section).
DEFAULT_TIME_STEP_S: float = 1.0

# Cell cycle target duration in seconds. Karr 2012 M. genitalium
# divides in approximately 9 hours under optimal conditions.
TARGET_CELL_CYCLE_S: float = 9 * 3600.0  # 32400 s


__all__ = [
    "GENOME_LENGTH_BP",
    "N_CHROMOSOME_COMPARTMENTS",
    "N_GENES",
    "N_MONOMERS",
    "N_TRANSCRIPTION_UNITS",
    "N_PROCESSED_RNAS",
    "DEFAULT_TIME_STEP_S",
    "TARGET_CELL_CYCLE_S",
]
