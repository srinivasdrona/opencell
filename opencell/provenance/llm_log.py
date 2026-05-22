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

DEFAULT_LOG_PATH = Path("opencell") / "provenance" / "llm_interactions.jsonl"
ROTATE_ENTRY_THRESHOLD = 100_000
_ROTATED_HEADER = {"rotated": True, "shards": "llm_interactions/"}
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


def _read_rotated_header(log_file: Path) -> dict | None:
    if not log_file.exists():
        return None
    raw = log_file.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and payload.get("rotated") is True:
        return payload
    return None


def _shards_dir(log_file: Path, header: dict | None = None) -> Path:
    if header and isinstance(header.get("shards"), str):
        return log_file.parent / header["shards"]
    return log_file.parent / "llm_interactions"


def _parse_timestamp(timestamp: str | None) -> datetime:
    if not timestamp:
        return datetime.min.replace(tzinfo=UTC)
    normalized = timestamp.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _month_bucket(timestamp: str | None) -> str:
    parsed = _parse_timestamp(timestamp)
    if parsed.year <= 1:
        return "unknown"
    return parsed.strftime("%Y-%m")


def _shard_path_for_record(log_file: Path, record: dict) -> Path:
    month = _month_bucket(record.get("timestamp_utc"))
    return _shards_dir(log_file) / f"{month}.jsonl"


def _iter_jsonl_file(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _count_jsonl_records(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                count += 1
    return count


def _rotate_to_shards(log_file: Path) -> None:
    if not log_file.exists():
        return
    if _read_rotated_header(log_file) is not None:
        return

    records = list(_iter_jsonl_file(log_file))
    if not records:
        return

    shards_directory = _shards_dir(log_file)
    shards_directory.mkdir(parents=True, exist_ok=True)

    shard_lines: dict[Path, list[str]] = {}
    for record in records:
        shard_path = _shard_path_for_record(log_file, record)
        shard_lines.setdefault(shard_path, []).append(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        )

    for shard_path, lines in sorted(shard_lines.items()):
        with shard_path.open("a", encoding="utf-8") as shard_fh:
            shard_fh.writelines(lines)
            shard_fh.flush()
            os.fsync(shard_fh.fileno())

    header_line = json.dumps(_ROTATED_HEADER, sort_keys=True, separators=(",", ":")) + "\n"
    with log_file.open("w", encoding="utf-8") as header_fh:
        header_fh.write(header_line)
        header_fh.flush()
        os.fsync(header_fh.fileno())


def _rotate_if_needed(log_file: Path) -> None:
    if not log_file.exists():
        return
    if _read_rotated_header(log_file) is not None:
        return
    if _count_jsonl_records(log_file) > ROTATE_ENTRY_THRESHOLD:
        _rotate_to_shards(log_file)


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
    _rotate_if_needed(p)

    header = _read_rotated_header(p)
    write_path = p
    if header is not None:
        write_path = _shards_dir(p, header) / f"{_month_bucket(record.timestamp_utc)}.jsonl"
        write_path.parent.mkdir(parents=True, exist_ok=True)

    with write_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())

    if write_path == p:
        _rotate_if_needed(p)
    return record.event_id


def iter_log(log_path: Path | str | None = None) -> Iterable[dict]:
    """Yield records from the log. Convenience for consumers (tests, queries)."""
    p = _resolve_path(log_path)
    if not p.exists():
        return
    header = _read_rotated_header(p)
    if header is None:
        yield from _iter_jsonl_file(p)
        return

    shards_directory = _shards_dir(p, header)
    if not shards_directory.exists():
        return

    records: list[dict] = []
    for shard_file in sorted(shards_directory.glob("*.jsonl")):
        records.extend(_iter_jsonl_file(shard_file))
    records.sort(key=lambda rec: _parse_timestamp(rec.get("timestamp_utc")))
    yield from records


__all__ = [
    "LlmLog",
    "Role",
    "VerificationStatus",
    "DEFAULT_LOG_PATH",
    "log_interaction",
    "iter_log",
]
