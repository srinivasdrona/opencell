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
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

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
# Canonical tag vocabulary reference: docs/llm_log_tag_vocabulary.md

_REPO_ROOT_CACHE: Path | None = None

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "aws_secret_access_key",
        re.compile(
            r'secret_access_key"?\s*[:=]\s*"?[A-Za-z0-9/+=]{40}"?',
            flags=re.IGNORECASE,
        ),
    ),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{36,}")),
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("azure_storage_sas_sig", re.compile(r"\?sig=[A-Za-z0-9%]{20,}")),
    ("generic_bearer_token", re.compile(r"Bearer [A-Za-z0-9._-]{20,}")),
)


@dataclass
class LlmLog:
    """One LLM interaction record.

    Fields with default ``None`` are optional. ``event_id`` and ``timestamp_utc``
    are filled in by ``log_interaction`` if left as default. ``schema_version``
    supports forward-migration of the serialized event format.
    """

    role: Role
    model: str
    task_summary: str
    output_summary: str
    schema_version: str = "1.0.0"

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
    return datetime.now(UTC).isoformat(timespec="seconds")


def _resolve_path(path: Path | str | None) -> Path:
    if path is None:
        path = DEFAULT_LOG_PATH
    p = Path(path)
    if not p.is_absolute():
        repo_root = _find_repo_root()
        p = repo_root / p
    return p


def _find_repo_root(start: Path | None = None) -> Path:
    global _REPO_ROOT_CACHE
    if start is None and _REPO_ROOT_CACHE is not None:
        return _REPO_ROOT_CACHE

    probe = (start if start is not None else Path(__file__)).resolve()
    if probe.is_file():
        probe = probe.parent

    for candidate in (probe, *probe.parents):
        if (candidate / ".git").is_dir() or (candidate / "pyproject.toml").is_file():
            if start is None:
                _REPO_ROOT_CACHE = candidate
            return candidate

    raise RuntimeError(
        "Could not find repo root: no .git or pyproject.toml in any parent directory"
    )


def _raise_if_likely_secret(field_name: str, value: str | None) -> None:
    if not value:
        return
    for pattern_name, pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            raise ValueError(f"Likely secret in {field_name}: {pattern_name}")


def log_interaction(record: LlmLog, log_path: Path | str | None = None) -> str:
    """Append ``record`` to the JSONL log. Returns the resulting event id.

    The record is mutated in place to fill in ``timestamp_utc`` and
    ``event_id`` if those were left blank.
    """
    if not record.timestamp_utc:
        record.timestamp_utc = _now_iso()
    if not record.event_id:
        record.event_id = record.compute_event_id()

    _raise_if_likely_secret("prompt_summary", record.prompt_summary)
    _raise_if_likely_secret("output_summary", record.output_summary)

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
