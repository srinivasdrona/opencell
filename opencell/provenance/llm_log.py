"""LLM interaction log — append-only JSONL record of agent decisions.

Companion to ``opencell.provenance.store`` (which logs parameter origins).
This module logs *LLM exchanges that shaped the repo*: code generation,
design critiques, sub-agent dispatches, cross-model reviews. The goal is
methodology reproducibility — when a paper or audit later asks "which
model produced this artifact under what conditions?", the answer is one
``jq`` query away.

Design rules (mirror ``store.py``):

* **Append-only.** No update, no delete. Corrections are new events with a
  ``supersedes`` field referencing the prior ``event_id``.
* **Content-addressed.** ``event_id = "sha256:" + hex(canonical_json)``,
  computed over every field except ``event_id`` itself. Logging the same
  content twice is idempotent on the id — the JSONL line is appended
  twice, but consumers can dedupe.
* **No silent inference.** Token counts and temperature, when not known,
  are explicitly ``null`` rather than zero or estimated.

What to log (policy, enforced by the agent at call sites, not by this module):

* Cross-model critiques (Opus reviewed by GPT-5.4 or vice versa).
* Sub-agent dispatches that produce committed artifacts (code, docs, blog).
* Significant design decisions ("evict MATLAB", "switch oracle", etc.)
* Reversals of prior decisions.

What NOT to log:

* Routine view/grep/edit tool calls (the agent's own scratch work).
* Same question asked twice in one session.
* Anything the agent's system prompt forbids (e.g. system-prompt verbatim).

CLI usage (the form invoked by agents from the shell)::

    python scripts/log_llm_interaction.py \\
        --role main_agent \\
        --model claude-opus-4.7 \\
        --task-summary "Wire MATLAB MCOS extract path" \\
        --output-summary "Chose option b2; 44 fixtures extracted" \\
        --linked-todo m1-mcos-decision \\
        --linked-commits 611bb0e,b219c6a \\
        --verification-status verified

Python usage (programmatic, e.g. from a sub-agent harness)::

    from opencell.provenance.llm_log import LlmLog, log_interaction
    log_interaction(LlmLog(
        role="cross_model_critique",
        model="gpt-5.4",
        task_summary="Review of D.2 design v3 proposal",
        ...
    ))
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

Role = Literal[
    "main_agent",
    "sub_agent",
    "background_agent",
    "cross_model_critique",
    "user_prompt",
    "retrospective",
]

VerificationStatus = Literal[
    "verified",
    "accepted",
    "rejected",
    "pending",
    "retrospective_inferred",
]

DEFAULT_LOG_PATH = Path("data") / "provenance" / "llm_interactions.jsonl"


@dataclass
class LlmLog:
    """One LLM interaction record.

    Fields with default ``None`` are optional. ``event_id`` and ``timestamp_utc``
    are filled in by ``log_interaction`` if left as default.
    """

    role: Role
    model: str
    task_summary: str
    output_summary: str

    prompt_summary: str | None = None
    decision_impact: str | None = None
    linked_todo: str | None = None
    linked_commits: list[str] = field(default_factory=list)
    linked_artifacts: list[str] = field(default_factory=list)
    verification_status: VerificationStatus = "pending"
    verification_notes: str | None = None
    temperature: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    session_id: str | None = None
    supersedes: str | None = None
    tags: list[str] = field(default_factory=list)

    timestamp_utc: str = ""
    event_id: str = ""

    def canonical(self) -> str:
        """JSON serialization used for content addressing.

        Excludes ``event_id`` (since it's derived) but includes every other
        field, with sorted keys for stability across Python versions.
        """
        d = asdict(self)
        d.pop("event_id", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    def compute_event_id(self) -> str:
        h = hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()
        return f"sha256:{h}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolve_path(path: Path | str | None) -> Path:
    if path is None:
        path = DEFAULT_LOG_PATH
    p = Path(path)
    if not p.is_absolute():
        # Resolve relative to the repo root (parent of opencell/).
        repo_root = Path(__file__).resolve().parents[2]
        p = repo_root / p
    return p


def log_interaction(record: LlmLog, log_path: Path | str | None = None) -> str:
    """Append ``record`` to the JSONL log. Returns the resulting event id.

    The record is mutated in place to fill in ``timestamp_utc`` and
    ``event_id`` if those were left blank.
    """
    if not record.timestamp_utc:
        record.timestamp_utc = _now_iso()
    if not record.event_id:
        record.event_id = record.compute_event_id()

    p = _resolve_path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(asdict(record), sort_keys=True, separators=(",", ":"))
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return record.event_id


def iter_log(log_path: Path | str | None = None) -> Iterable[dict]:
    """Yield records from the log. Convenience for consumers (tests, queries)."""
    p = _resolve_path(log_path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


__all__ = [
    "LlmLog",
    "Role",
    "VerificationStatus",
    "DEFAULT_LOG_PATH",
    "log_interaction",
    "iter_log",
]
