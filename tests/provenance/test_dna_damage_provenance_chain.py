"""Focused regression on the DNADamage EVENT_CLASS provenance supersession chain.

The append-only ``opencell/provenance/llm_interactions.jsonl`` log accumulated a
malformed intermediate entry (event_id starting ``sha256:57ad7c35``) during the
agent/l2-event-dnadamage-20260805 remediation: a shell-quoting bug in
``bin\\oc-py.cmd`` truncated its ``verification_notes`` and dropped its
``supersedes``/``tags`` fields. The log is append-only -- that entry cannot be
edited or removed -- so correctness is instead enforced by the *live head* of
the chain: the newest entry that supersedes it.

This test does not hardcode that head's ``event_id`` (it is content-addressed
over a wall-clock timestamp, so it cannot be predicted ahead of logging). It
finds the head structurally (the entry whose ``supersedes`` points at the
malformed entry) and asserts that the chain, read from that head backward,
still carries the two facts a reviewer must be able to recover without
consulting git history:

* the PROCESS_CATALOG.yaml stale "L2.2 GREEN / blocked_on cleared" claim was
  retracted (a zero==zero quiescent-replay artifact, not real event-class
  evidence), and
* the production Rule-8 oracle-trace-read violation was removed and the Karr
  trace inventory broadened/classified (not just "no traces exist").

It also asserts every commit hash cited anywhere in that chain is a real,
reachable commit object -- catching the case where a future correction cites
an unreachable/typo'd SHA.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opencell.provenance.llm_log import iter_log  # noqa: E402

# The known-malformed entry. Its shape is now permanent, immutable history in
# an append-only log -- pinning its event_id and its two missing fields is a
# regression check on the log's own historical record, not a moving target.
_MALFORMED_EVENT_ID = (
    "sha256:57ad7c35b9916121c80ce4ff9a501211ffdcd19a8265c109e314c49c123e32fe"
)
_ORIGINAL_EVENT_ID = (
    "sha256:3e0dd4c3432ea32ad0d97d8e53d4b34663dc22c24d6fa4b7fe242f9402ed34ce"
)

# Facts the live chain head must still carry, in some entry reachable by
# walking `supersedes` back from the head. Substrings, not exact phrases, so
# minor future wording tweaks don't spuriously break this test.
_REQUIRED_CATALOG_RETRACTION_FACTS = ("L2.2 GREEN", "blocked_on")
_REQUIRED_RULE_8_FACTS = ("Rule 8", "vacuous")


def _git_dir(repo_root: Path) -> Path:
    """Resolve the real git object-database directory for ``repo_root``.

    Git worktrees created on this machine record their ``gitdir:`` pointer
    using a Windows-style absolute path (e.g. ``E:/opencell/.git/worktrees/
    <name>``). Native WSL git cannot resolve that path when the current
    working directory is itself under ``/mnt/e/...`` (it gets concatenated
    as a relative path onto the cwd instead of being treated as absolute),
    so plain ``git`` invocations fail with "not a git repository" even
    though the repository is perfectly valid. Translate the pointer to its
    ``/mnt/<drive>/...`` equivalent before shelling out.
    """
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return dot_git

    pointer = dot_git.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    assert pointer.startswith(prefix), f"Unexpected .git pointer format: {pointer!r}"
    raw_path = pointer[len(prefix) :].strip()

    if len(raw_path) >= 2 and raw_path[1] == ":":
        drive = raw_path[0].lower()
        rest = raw_path[2:].lstrip("/\\").replace("\\", "/")
        return Path(f"/mnt/{drive}/{rest}")
    return Path(raw_path)


def _commit_reachable(sha: str, git_dir: Path) -> bool:
    result = subprocess.run(
        ["git", f"--git-dir={git_dir}", "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _load_dna_damage_chain_entries() -> dict[str, dict]:
    entries = {
        record["event_id"]: record
        for record in iter_log(None)
        if "dnadamage" in record.get("tags", [])
        or record.get("event_id") in (_MALFORMED_EVENT_ID, _ORIGINAL_EVENT_ID)
    }
    return entries


def test_malformed_entry_is_present_and_permanently_documented() -> None:
    entries = _load_dna_damage_chain_entries()
    assert _MALFORMED_EVENT_ID in entries, (
        "The known-malformed provenance entry is missing from "
        "opencell/provenance/llm_interactions.jsonl -- the append-only log "
        "must never have entries removed."
    )
    malformed = entries[_MALFORMED_EVENT_ID]
    assert malformed["supersedes"] is None
    assert malformed["tags"] == []


def test_live_chain_head_supersedes_the_malformed_entry_directly() -> None:
    entries = _load_dna_damage_chain_entries()
    heads = [
        record
        for record in entries.values()
        if record.get("supersedes") == _MALFORMED_EVENT_ID
    ]
    assert heads, (
        "No provenance entry supersedes the malformed entry "
        f"({_MALFORMED_EVENT_ID}) directly. The live chain head must point "
        "at it (not skip over it to an earlier entry) so the graph matches "
        "real edit order."
    )
    assert len(heads) == 1, (
        "Exactly one entry should directly supersede the malformed entry; "
        f"found {len(heads)}: {[h['event_id'] for h in heads]}"
    )
    head = heads[0]
    assert head["tags"], "Live chain head must have non-empty tags."
    assert head["output_summary"], "Live chain head must have a non-empty output_summary."
    assert head["verification_notes"], (
        "Live chain head must have non-empty verification_notes."
    )


def _walk_chain_text(entries: dict[str, dict], head_event_id: str) -> tuple[str, list[str]]:
    """Concatenate text fields and collect linked_commits walking supersedes back."""
    text_parts: list[str] = []
    commits: list[str] = []
    seen: set[str] = set()
    current = head_event_id
    while current is not None and current not in seen:
        seen.add(current)
        record = entries.get(current)
        if record is None:
            break
        for field_name in ("task_summary", "output_summary", "verification_notes"):
            value = record.get(field_name)
            if value:
                text_parts.append(value)
        commits.extend(record.get("linked_commits") or [])
        current = record.get("supersedes")
    return "\n".join(text_parts), commits


def test_chain_retains_catalog_retraction_and_rule_8_facts() -> None:
    entries = _load_dna_damage_chain_entries()
    heads = [
        record
        for record in entries.values()
        if record.get("supersedes") == _MALFORMED_EVENT_ID
    ]
    assert heads, "Live chain head not found (see other test for the precise failure)."
    head = heads[0]

    chain_text, _ = _walk_chain_text(entries, head["event_id"])

    for fact in _REQUIRED_CATALOG_RETRACTION_FACTS:
        assert fact in chain_text, (
            f"Catalog-retraction fact {fact!r} not found walking the "
            "supersession chain back from the live head -- the chain must "
            "retain the PROCESS_CATALOG.yaml stale L2.2-GREEN retraction."
        )
    for fact in _REQUIRED_RULE_8_FACTS:
        assert fact in chain_text, (
            f"Rule-8 remediation fact {fact!r} not found walking the "
            "supersession chain back from the live head."
        )


def test_chain_commits_are_all_reachable_git_objects() -> None:
    entries = _load_dna_damage_chain_entries()
    heads = [
        record
        for record in entries.values()
        if record.get("supersedes") == _MALFORMED_EVENT_ID
    ]
    assert heads, "Live chain head not found (see other test for the precise failure)."
    head = heads[0]

    _, commits = _walk_chain_text(entries, head["event_id"])
    assert commits, "Expected at least one linked commit across the chain."

    git_dir = _git_dir(REPO_ROOT)
    unreachable = [sha for sha in commits if not _commit_reachable(sha, git_dir)]
    assert not unreachable, (
        f"Commit(s) cited in the DNADamage provenance chain are not reachable "
        f"git objects: {unreachable}"
    )
