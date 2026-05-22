"""Provenance store v0.1 — append-only event log for parameter origins.

Phase 4 / A3 design rules (from plan.md non-negotiable principles):

* **Append-only.** No update, no delete. Corrections are *new events*
  with a `supersedes` reference to the prior event id.
* **Minimum normalization on insert.** Every event has at least:
  ``param_name``, ``value``, ``unit`` (canonical), ``source_kind``,
  ``source_ref`` (DOI / URL / file SHA), ``scope`` (organism, model,
  variable), ``transformation_lineage`` (how raw value got here),
  ``timestamp_utc``, ``recorded_by``, ``event_id``, optional
  ``supersedes``. Higher-level schema additions are deferred to v0.2;
  the *minimum* is non-negotiable from day one.
* **No silent inference.** If unit conversion or scaling is applied,
  it goes in ``transformation_lineage`` as a list of human-readable
  steps — not just an output value.
* **Bounded-tuning policy.** A parameter with a value outside its
  ``allowed_range`` (when one is recorded) is a *separate* event with
  ``event_kind == "tuned"`` and a mandatory ``tuning_justification``
  field. The store does not enforce — it records — but the linter does.
* **Backing store: JSON Lines** for v0.1. One file per scope (e.g.
  ``data/provenance/chassagnole.jsonl``). SQLite-backed view added in
  v0.2 once query patterns settle. Append is atomic by line.
* **No deletion API.** Period. If you need to "remove" a parameter,
  you write a ``superseded_by`` event with ``value: null``.

This module deliberately does NOT validate biology. It is a recorder.
The bounded-tuning lint, the value-range checker, and the cross-event
consistency report live in ``opencell/provenance/lint.py`` (v0.2).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

EVENT_KINDS = Literal["measured", "computed", "ingested", "tuned", "superseded_by"]
SOURCE_KINDS = Literal[
    "primary_literature",  # DOI of paper
    "secondary_literature",  # DOI of review
    "database",  # BRENDA / SABIO / BiGG entry
    "model_artifact",  # MATLAB .mat / SBML file
    "estimation",  # parameter-estimation run
    "expert_judgment",  # human assertion (must say who and why)
    "default_assumption",  # placeholder pending real source
]


@dataclass(frozen=True)
class ProvenanceEvent:
    """A single immutable provenance record.

    ``event_id`` is content-addressed (SHA256 of the canonical JSON of
    every other field). Two identical events collapse to one record;
    accidental double-write is harmless.
    """

    param_name: str
    value: object  # number, list, or null
    unit: str  # canonical (e.g. "mM", "1/s", "mM/s"); empty "" if dimensionless
    source_kind: str  # SOURCE_KINDS
    source_ref: str  # DOI / URL / file SHA / "expert:NAME"
    scope: dict[
        str, str
    ]  # e.g. {"organism": "E.coli", "model": "Chassagnole2002", "variable": "Vmax_PGI"}
    transformation_lineage: list[
        str
    ]  # ["Table 2 row 4 raw 1.5e-3 mol/m3/s", "convert to mM/s -> 1.5"]
    event_kind: str  # EVENT_KINDS
    timestamp_utc: str  # ISO 8601
    recorded_by: str  # "human:Drona" or "agent:param-extractor v1"
    notes: str = ""
    allowed_range: list[float] | None = None  # [low, high] in same unit
    tuning_justification: str = ""
    supersedes: str | None = None  # event_id of superseded record
    event_id: str = ""  # filled in by ``finalize``

    def finalize(self) -> ProvenanceEvent:
        """Compute ``event_id`` from all other fields and return a new
        frozen dataclass with it set."""
        d = asdict(self)
        d["event_id"] = ""
        canonical = json.dumps(d, sort_keys=True, default=str)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return ProvenanceEvent(**{**d, "event_id": digest})


class ProvenanceStore:
    """Append-only JSONL-backed parameter provenance store.

    One store per scope (typically per-model, e.g. ``chassagnole``,
    ``vilar``, ``mgenitalium``). The constructor opens (or creates) the
    backing file. ``record(event)`` appends one line; ``query()`` and
    ``current(param_name)`` read.

    The backing file is line-atomic on POSIX (single ``write`` syscall
    per record below 4 KiB), which suits our typical record size of
    ~500-1000 bytes. For records larger than 4 KiB we fall back to
    ``os.write`` with O_APPEND to retain atomicity.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, event: ProvenanceEvent) -> ProvenanceEvent:
        """Append one event to the store. Returns the finalized event
        (with ``event_id`` set). Idempotent: if the same content already
        exists, no-ops and returns the existing event."""
        if not event.event_id:
            event = event.finalize()
        existing = self._find_by_id(event.event_id)
        if existing is not None:
            return existing
        line = json.dumps(asdict(event), sort_keys=True, default=str)
        encoded = (line + "\n").encode("utf-8")
        # O_APPEND is atomic for writes up to PIPE_BUF on POSIX; we use
        # a single write syscall to preserve line atomicity even when
        # multiple processes append concurrently.
        fd = os.open(str(self.path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, encoded)
        finally:
            os.close(fd)
        return event

    def record_measured(
        self,
        *,
        param_name: str,
        value: object,
        unit: str,
        source_ref: str,
        scope: dict[str, str],
        transformation_lineage: list[str],
        recorded_by: str,
        source_kind: str = "primary_literature",
        allowed_range: list[float] | None = None,
        notes: str = "",
    ) -> ProvenanceEvent:
        """Convenience: record a value measured in a primary source."""
        return self.record(
            ProvenanceEvent(
                param_name=param_name,
                value=value,
                unit=unit,
                source_kind=source_kind,
                source_ref=source_ref,
                scope=scope,
                transformation_lineage=transformation_lineage,
                event_kind="measured",
                timestamp_utc=_utcnow_iso(),
                recorded_by=recorded_by,
                notes=notes,
                allowed_range=allowed_range,
            )
        )

    def record_tuned(
        self,
        *,
        param_name: str,
        value: object,
        unit: str,
        scope: dict[str, str],
        allowed_range: list[float],
        tuning_justification: str,
        supersedes: str,
        recorded_by: str,
        transformation_lineage: list[str] | None = None,
        notes: str = "",
    ) -> ProvenanceEvent:
        """Convenience: record a tuned value within a verified range.

        ``allowed_range`` and ``tuning_justification`` are *required* by
        the bounded-tuning policy — there is no overload that lets you
        skip them.
        """
        if value < allowed_range[0] or value > allowed_range[1]:
            raise ValueError(
                f"Tuned value {value} {unit} outside allowed_range "
                f"{allowed_range} for {param_name}. Bounded-tuning policy: "
                "if the range cannot accommodate, publish the discrepancy "
                "instead of widening the range."
            )
        return self.record(
            ProvenanceEvent(
                param_name=param_name,
                value=value,
                unit=unit,
                source_kind="estimation",
                source_ref="tuning_run",
                scope=scope,
                transformation_lineage=transformation_lineage or [],
                event_kind="tuned",
                timestamp_utc=_utcnow_iso(),
                recorded_by=recorded_by,
                notes=notes,
                allowed_range=allowed_range,
                tuning_justification=tuning_justification,
                supersedes=supersedes,
            )
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[ProvenanceEvent]:
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                yield ProvenanceEvent(**d)

    def all(self) -> list[ProvenanceEvent]:
        return list(self)

    def query(
        self, *, param_name: str | None = None, scope_filter: dict[str, str] | None = None
    ) -> list[ProvenanceEvent]:
        out = []
        for ev in self:
            if param_name is not None and ev.param_name != param_name:
                continue
            if scope_filter and not all(ev.scope.get(k) == v for k, v in scope_filter.items()):
                continue
            out.append(ev)
        return out

    def current(
        self, param_name: str, scope_filter: dict[str, str] | None = None
    ) -> ProvenanceEvent | None:
        """Return the most recent non-superseded event for the parameter.

        Resolution rule: walk events newest-first; skip any event that
        is referenced by a later event's ``supersedes`` field.
        """
        events = self.query(param_name=param_name, scope_filter=scope_filter)
        if not events:
            return None
        superseded_ids = {e.supersedes for e in events if e.supersedes}
        live = [e for e in events if e.event_id not in superseded_ids]
        if not live:
            return None
        # Most recent by timestamp (ties broken by event_id for determinism).
        return sorted(live, key=lambda e: (e.timestamp_utc, e.event_id))[-1]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_by_id(self, event_id: str) -> ProvenanceEvent | None:
        for ev in self:
            if ev.event_id == event_id:
                return ev
        return None


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
