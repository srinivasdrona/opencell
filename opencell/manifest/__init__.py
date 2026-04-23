"""SBML → parameter-extraction-manifest emitter.

Reads a curated BioModels SBML file and emits a YAML manifest with one
entry per parameter, suitable as input to the ``param-extractor`` skill
(via the upcoming ``biology-curator`` agent).

The output is a *draft* manifest: humans curate it (prune, annotate
biological context, fix SBML-id-vs-paper-symbol mismatches) before
running the curator.

Walks:
  - global <parameter> elements
  - local <kineticLaw>/<listOfParameters>/<parameter> (per-reaction)
  - optionally <species> for initial concentrations

Resolves <unitDefinition> blocks into human-readable unit strings
(e.g. ``mole/(litre*second)``).
"""

from .sbml import (
    SbmlEntity,
    SbmlModelMetadata,
    SbmlUnit,
    SbmlUnitDefinition,
    extract_metadata,
    parse_sbml,
    resolve_unit,
    stringify_unit,
)
from .emitter import (
    ManifestEntry,
    ManifestHeader,
    build_manifest,
    write_manifest_yaml,
)

__all__ = [
    "SbmlEntity",
    "SbmlModelMetadata",
    "SbmlUnit",
    "SbmlUnitDefinition",
    "extract_metadata",
    "parse_sbml",
    "resolve_unit",
    "stringify_unit",
    "ManifestEntry",
    "ManifestHeader",
    "build_manifest",
    "write_manifest_yaml",
]
