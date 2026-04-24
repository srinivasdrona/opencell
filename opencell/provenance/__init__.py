"""Append-only parameter provenance store (Phase 4 / A3 v0.1).

See ``opencell/provenance/store.py`` and the design rules in plan.md
(non-negotiable principles, sec. "Append-only provenance").
"""

from opencell.provenance.store import (
    ProvenanceEvent,
    ProvenanceStore,
)

__all__ = ["ProvenanceEvent", "ProvenanceStore"]
