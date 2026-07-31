"""L2.event evidence foundation (Phase F).

Generic, process-adapter-based runner/framework for the ``event_class``
harness described in ``docs/phase_f/L2_EVENT_GATE_SPEC_v4.md`` (ratified
v4.1). This package intentionally contains **no** process-specific gating
wiring: it defines the versioned artifact schema, the event-adapter
interface, the stride-1 window loader, the metrics/null-bootstrap engine,
and the portable evidence-index machinery that a later per-process task will
plug concrete adapters into.

See ``docs/phase_f/l2_event/L2_EVENT_FOUNDATION_STATUS.md`` for the
ground-truth inventory this package was built against (what data actually
exists on disk vs. what the spec/catalog assume).
"""

from __future__ import annotations
