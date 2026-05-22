# LLM Interaction Log Design

## Purpose and Scope

`opencell.provenance.llm_log` captures consequential LLM exchanges as immutable JSONL events. This log is complementary to `opencell.provenance.store`:

- `provenance.store` answers: "Where did this parameter/value come from?"
- `llm_log` answers: "Which model interaction led to this design or code decision?"

The objective is auditability and reproducibility for engineering and publication workflows. If an artifact was materially shaped by an LLM, there should be a durable record of the who/what/when/why.

## Why Content-Addressed Event IDs

Each event ID is derived from canonical JSON:

- `event_id = sha256(canonical_record_without_event_id)`
- Canonicalization uses sorted keys and compact JSON separators.

This gives three operational benefits:

1. Idempotency by content. Re-logging identical content produces the same `event_id`, which simplifies deduplication during downstream analysis.
2. Tamper-evident lineage. If an event body changes, the digest changes. A rewritten record cannot pretend to be the same event.
3. Stable references. Other artifacts (notes, commits, superseding records) can refer to `event_id` reliably.

The log file itself is append-only, so duplicate lines can exist physically; content addressing makes semantic identity explicit.

## Append-Only Philosophy

The design intentionally avoids update/delete APIs.

- No in-place edits.
- No deletion pathway in module API.
- Corrections are represented as new events with `supersedes=<prior_event_id>`.

This mirrors event sourcing and supports chronological reconstruction. Investigators can see what was believed at each point in time, then how later evidence amended earlier decisions.

## Schema Overview

Current schema version is `1.0.0` (field: `schema_version`).

Core identity and context fields:

- `schema_version`: schema marker for forward migration.
- `role`: actor role (main agent, sub-agent, critique, etc.).
- `model`: model identifier used for the interaction.
- `task_summary`: concise statement of intent.
- `output_summary`: concise statement of produced outcome.
- `prompt_summary`: optional prompt synopsis when safe to include.

Traceability fields:

- `decision_impact`: downstream implication/unblocked item.
- `linked_todo`: related task identifier.
- `linked_commits`: produced commit SHAs.
- `linked_artifacts`: produced/touched paths.
- `tags`: discoverability labels (see tag vocabulary doc).

Validation and quality fields:

- `verification_status`: `verified|accepted|rejected|pending|retrospective_inferred`.
- `verification_notes`: how output was checked.

Execution metadata fields:

- `temperature`, `tokens_in`, `tokens_out`: explicit nullable fields (unknown remains `null`, never silently inferred).
- `session_id`: optional session correlation.
- `supersedes`: optional prior event reference when correcting.
- `timestamp_utc`: write-time UTC ISO timestamp.
- `event_id`: content-addressed digest string.

Security guardrails:

- Before writing, `prompt_summary` and `output_summary` are checked for likely secrets.
- Detection raises `ValueError` (no silent scrubbing), forcing caller acknowledgement and redaction.

## When to Log / When Not to Log

When to log:

- Cross-model critiques that influence direction.
- Sub-agent dispatches that produce committed artifacts.
- Significant design decisions and reversals.
- Decision points needed to explain provenance of major outputs.

When not to log:

- Routine scratchpad/tool chatter (view/grep/edit loops).
- Duplicate asks in one active session with no new decision value.
- Any content forbidden by policy/system constraints.

Practical rule: log decisions, not keystrokes.

## Forward Migration Story (`schema_version`)

`schema_version` is included in serialization and therefore in `event_id` computation. That is intentional:

- Schema changes that alter semantics should produce distinct identities.
- Consumers can branch parsing/validation by `schema_version`.
- Mixed-version logs remain valid in one append-only file.

Recommended migration pattern:

1. Add parser support for old + new versions.
2. Start emitting new version at writers.
3. Keep old records immutable.
4. Use `supersedes` only for factual corrections, not schema rewrites.

## Alternatives and Trade-offs

### `provenance.store` only

Pros:

- Already tracks parameter/value origins.

Cons:

- Does not capture conversational model decisions and critiques with enough narrative context.

### SQLite event log

Pros:

- Indexed queries, transactions, schema constraints.

Cons:

- Higher operational and tooling overhead for lightweight agent workflows.
- Harder shell-native append and diff ergonomics compared to JSONL.

### Flat JSON snapshots

Pros:

- Simple to parse.

Cons:

- Encourages overwrite semantics and weakens chronological audit trail.

Current choice (append-only JSONL + content-addressed IDs) optimizes for low-friction writes, git-friendly storage, and strong forensic traceability while keeping migration options open.
