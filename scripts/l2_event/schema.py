"""Versioned artifact schema for the L2.event evidence foundation.

This mirrors the artifact set required by ``L2_EVENT_GATE_SPEC_v4.md`` §9
(surface S8): ``result.json``, ``SUMMARY.json``, ``input_manifest.json``,
``null_calibration.json``, and ``provenance.json``. It is a **separate**
schema from ``scripts/l22_evidence/schema.py`` (Design-A's per-tick gate) --
event-class processes must never be silently folded into the per-tick
scoreboard (surface S9).

Nothing in this module talks to ``PROCESS_CATALOG.yaml`` directly; that
cross-check lives in :mod:`scripts.l2_event.registry`, so a schema change
here can never accidentally stale or promote the Design-A catalog hash.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

#: Bumped whenever any field in the dataclasses below changes shape.
SCHEMA_VERSION = 1

#: Registry file schema version (docs/phase_f/l2_event/event_registry.yaml).
REGISTRY_SCHEMA_VERSION = 1

#: Evidence-index schema version (docs/phase_f/l2_event/evidence_index.json).
EVIDENCE_INDEX_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Vocabulary (kept as plain string literals, not an Enum, so JSON round-trips
# without a custom encoder -- matches scripts/l22_evidence/schema.py style).
# ---------------------------------------------------------------------------

#: Per-gate channel verdicts. ``NOT_GATEABLE_REDUNDANT`` is D6's escape hatch
#: for Cytokinesis magnitude; it must never silently count as PASS.
#:
#: Opus5 review (M1 + one-sided-empty metric correction) added four verdicts
#: that must never be treated as PASS/SEED_NOISE by any aggregation logic:
#:
#: * ``INSUFFICIENT_KARR_SUPPORT`` -- Karr fired, but below the
#:   registry-configured support floor (e.g. RA repeated_firing requires
#:   >=50 pooled fire ticks; Cytokinesis single_firing requires >=45/50
#:   seeds fired per spec C2). Distinct from ``NO_KARR_SUPPORT`` (zero
#:   support): this is *some* support, just not enough to trust a
#:   calibrated bootstrap.
#: * ``DEGENERATE_NULL`` -- the Karr-only clustered null bootstrap collapsed
#:   to ``q95_null == 0`` (zero-width null). A ``SEED_NOISE`` verdict can
#:   never be derived from a degenerate null: ``w1 <= 0`` would trivially
#:   "pass" on a coincidence, not a calibrated noise floor.
#: * ``NO_OC_SUPPORT`` -- Karr fired but OC produced zero events/payload
#:   across the whole cohort: the mirror image of the existing hard-FAIL
#:   "Karr silent, OC fires" case (no capped-silence green either way).
#:
#: Opus5 review round 3 (payload-gate per-component correctness) added two
#: more verdicts, used only by :func:`scripts.l2_event.metrics.payload_gate`
#: (both per-component and as the aggregated channel verdict when they are
#: the worst thing observed across components) -- both are FAIL-class, never
#: PASS/SEED_NOISE:
#:
#: * ``NO_OC_COMPONENT`` -- a payload component Karr reports is completely
#:   absent from every OC payload in the cohort (not merely zero-valued --
#:   the key itself never appears). Silently treating this as "OC reported
#:   0.0" would zero-fill a missing mapping into a numeric divergence
#:   instead of flagging the real bug (an adapter payload-key mapping gap).
#: * ``SPURIOUS_OC_COMPONENT`` -- the mirror image: OC reports a payload
#:   component that never appears anywhere on the Karr side. This can only
#:   be an adapter/OC-port bug (OC is inventing a component Karr's own
#:   normalization never produced) and must FAIL, never be silently
#:   dropped from the comparison.
ChannelVerdict = Literal[
    "PASS",
    "FAIL",
    "SEED_NOISE",
    "NO_KARR_SUPPORT",
    "NO_OC_SUPPORT",
    "INSUFFICIENT_KARR_SUPPORT",
    "DEGENERATE_NULL",
    "NOT_GATEABLE_REDUNDANT",
    "NOT_COMPUTED",
    "NO_OC_COMPONENT",
    "SPURIOUS_OC_COMPONENT",
]

#: Process-level aggregate verdict. ``NOT_APPLICABLE`` marks a structural
#: smoke run (e.g. RibosomeAssembly seed0) that intentionally never produces
#: a gate PASS/FAIL -- it must never be mistaken for a gating verdict.
ProcessVerdict = Literal["PASS", "FAIL", "REFUSED", "BLOCKED", "NOT_APPLICABLE"]

#: Reasons the runner refuses to compute a verdict at all (requirement 4).
#: These are input/precondition failures, distinct from a computed FAIL.
RefusalReason = Literal[
    "MISSING_WINDOW",
    "INCOMPLETE_WINDOW",
    "NOT_EVENT_WINDOW_TRACE",
    "SINGLE_SEED_ENSEMBLE_REQUIRED",
    "EMPTY_EVENT_SUPPORT",
    "ADAPTER_PROCESS_MISMATCH",
    "ADAPTER_NOT_REGISTERED",
    "ADAPTER_NOT_GATING_READY",
    "REGISTRY_PROCESS_UNKNOWN",
    "REGISTRY_OUT_OF_V4_SCOPE",
]

EVENT_TIMING_MODELS = ("single_firing", "repeated_firing")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return obj.as_posix()
    raise TypeError(f"Object of type {type(obj)!r} is not JSON serializable")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` atomically (tmp file + os.replace).

    Mirrors the atomic-write discipline used by ``scripts/l22_evidence``
    (avoid partially-written artifacts if a run is interrupted).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Normalized event record (D7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventObservation:
    """One tick's normalized event record, per D7's shared cross-language
    contract: ``{fire_count, fired, timing_tick, payload}``.

    Both the (future) MATLAB extractor and the Python adapter side must
    produce this exact shape from their respective native inputs.
    """

    tick: int
    fired: bool
    fire_count: int
    timing_tick: int | None
    payload: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.fire_count < 0:
            raise ValueError(f"fire_count must be >= 0, got {self.fire_count}")
        if self.fired and self.fire_count == 0:
            raise ValueError("fired=True requires fire_count >= 1")
        if not self.fired and self.fire_count != 0:
            raise ValueError("fired=False requires fire_count == 0")
        if self.fired and self.timing_tick is None:
            raise ValueError("fired=True requires a timing_tick")
        if not self.fired and self.timing_tick is not None:
            raise ValueError("fired=False requires timing_tick is None")

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventTimeline:
    """The full per-tick sequence of :class:`EventObservation` for one
    (process, seed) pair over the fully enumerated stride-1 window."""

    process: str
    seed: int
    observations: tuple[EventObservation, ...]

    @property
    def n_ticks(self) -> int:
        return len(self.observations)

    @property
    def total_fire_count(self) -> int:
        return sum(o.fire_count for o in self.observations)

    @property
    def fire_ticks(self) -> tuple[int, ...]:
        """Bag of tick indices where an event fired (one entry per fire,
        not deduplicated -- matches D2 addendum's "bag" semantics)."""
        ticks: list[int] = []
        for obs in self.observations:
            if obs.fired:
                ticks.extend([obs.tick] * obs.fire_count)
        return tuple(ticks)


# ---------------------------------------------------------------------------
# Gate channel result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PayloadComponentResult:
    """One payload component's OWN computed result (Opus5 review round 3,
    payload-gate item #1): its own W1 statistic, its own seed-cluster
    bootstrapped null, its own threshold/verdict, and a standardized
    ratio (``statistic_value / q95_null``) that lets components with very
    different absolute scales be compared on equal footing. The channel's
    aggregated verdict is the WORST verdict across all
    :class:`PayloadComponentResult` entries -- never derived from picking
    whichever component happens to have the largest raw W1 (that silently
    let a component with a large-but-proportionally-noisy W1 mask a
    small-but-60x-its-own-null divergence in a different component).
    """

    component: str
    verdict: ChannelVerdict
    statistic_value: float | None
    q95_null: float | None
    threshold: float | None
    standardized_ratio: float | None
    reasons: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateChannelResult:
    """One gate channel's (count | timing | payload) computed result."""

    channel: str
    verdict: ChannelVerdict
    statistic_name: str
    statistic_value: float | None
    q95_null: float | None
    k_eng: float | None
    threshold: float | None
    n_nonzero_oc: int
    n_nonzero_karr: int
    reasons: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    #: Opus5 review round 3 (item #6): `k_eng_provenance` is now a real,
    #: typed schema field (not just a loosely-keyed entry inside `extra`)
    #: so it cannot be silently omitted by a future caller and is bound
    #: into `result.json`'s own tracked sha256 like every other field here.
    k_eng_provenance: str | None = None
    #: Non-empty only for the payload channel (Opus5 review round 3, item
    #: #1): the full per-component breakdown backing the aggregated
    #: `verdict` above.
    per_component: list["PayloadComponentResult"] = field(default_factory=list)
    #: The representative standardized ratio (`statistic_value / q95_null`)
    #: for whichever component determined the aggregated `verdict` -- a
    #: quick top-level summary; `per_component` carries every component's
    #: own ratio.
    standardized_ratio: float | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Top-level artifacts (S8)
# ---------------------------------------------------------------------------


@dataclass
class ResultDoc:
    schema_version: int
    process: str
    adapter_id: str
    event_timing_model: str
    mode: Literal["gate", "structural_smoke"]
    verdict: ProcessVerdict
    channels: list[GateChannelResult]
    oc_only_fire_ticks: dict[str, list[int]]
    n_seeds_karr: int
    n_seeds_oc: int
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["channels"] = [c.to_json() if isinstance(c, GateChannelResult) else c for c in self.channels]
        return payload


@dataclass
class InputManifestEntry:
    path: str
    sha256: str
    seed: int
    n_ticks: int
    tick_offset: float | None
    trace_kind: str


@dataclass
class InputManifest:
    schema_version: int
    process: str
    inputs: list[InputManifestEntry]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "process": self.process,
            "inputs": [asdict(i) for i in self.inputs],
        }


@dataclass
class NullCalibrationDoc:
    schema_version: int
    process: str
    channel: str
    statistic_name: str
    b_resamples: int
    q95_null: float
    cluster_unit: Literal["seed"] = "seed"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProvenanceDoc:
    schema_version: int
    process: str
    adapter_id: str
    adapter_module: str
    karr_source: str
    git_sha: str | None
    registry_sha256: str
    generated_at: str
    #: Opus5 review round 3 (item #6): this is now a REAL schema field
    #: (previously only claimed to exist in STATUS.md prose while actually
    #: living solely inside `GateChannelResult.extra`'s loosely-typed dict).
    #: Always the current value of `scripts.l2_event.metrics.K_ENG_PROVENANCE`
    #: at generation time -- explicitly provisional/non-ratifying, never a
    #: ratified statistical threshold. Bound into `provenance.json`'s own
    #: tracked sha256 like every other field here.
    k_eng_provenance: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
