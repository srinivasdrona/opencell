"""Biology-curator: orchestrate per-paper parameter extraction campaigns.

This package consumes a manifest YAML (one entry per parameter) and runs
the deterministic param-extractor pipeline for each. Outputs:

  - <output_dir>/<model_slug>.yaml                 # DRAFT cards (RECOMMEND only)
  - <output_dir>/<model_slug>.needs_arbitration.yaml
  - <output_dir>/<model_slug>.not_found.yaml
  - <output_dir>/<model_slug>.coverage.md
  - <output_dir>/<model_slug>.curation_run.json    # provenance

Hard constraints (enforced by code, not policy):
  * never invents a value
  * never auto-promotes past DRAFT
  * never resolves AMBIGUOUS silently — always queues for human review
  * never modifies cards already at REVIEWED or APPROVED status
"""

from .manifest import (
    CurationManifest,
    ManifestParameter,
    ManifestValidationError,
    load_manifest,
)
from .runner import (
    CurationOutcome,
    CurationRun,
    run_curation,
)
from .emitter import (
    write_outputs,
)

__all__ = [
    "CurationManifest",
    "ManifestParameter",
    "ManifestValidationError",
    "load_manifest",
    "CurationOutcome",
    "CurationRun",
    "run_curation",
    "write_outputs",
]
