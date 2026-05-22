# LLM Log Tag Vocabulary

## Scope

This document defines canonical `tags` values for `data/provenance/llm_interactions.jsonl` and future records written via `opencell.provenance.llm_log`.

The current module does not enforce tags in code; this is an operator-facing vocabulary for consistency.

## Normalization Rules

- Case: always lowercase.
- Spelling: prefer plain words and stable separators (`-` for single token labels, `:` for namespace hierarchy).
- Hierarchy: use `namespace:value` for structured tags.

Recommended hierarchy examples:

- `phase:a3.3`
- `process:m2v3`
- `review:opus-4.6`
- `model:gpt-5.5`
- `decision:architecture`

## Canonical Values Currently Observed

The existing log (`data/provenance/llm_interactions.jsonl`) currently contains these canonical tags:

- `architecture-decision`
- `critique-gap-1`
- `critique-round-4`
- `d2`
- `karr-fidelity`
- `meta`
- `option-a3`
- `provenance`
- `resolved`

No case variants were found in the current file; all existing values are already lowercase.

## Canonicalization Guidance for Future Entries

Keep existing historical values unchanged. For new entries, prefer namespaced forms where useful:

- Keep or map topic tags to namespaces: `topic:d2`, `topic:provenance`.
- Represent decision category explicitly: `decision:architecture` (instead of only `architecture-decision`).
- Encode process stage in namespace form: `phase:critique-round-4`.
- Encode resolution state in namespace form: `status:resolved`.
- Encode options consistently: `option:a3`.

If legacy flat tags are reused for continuity, keep spellings exact and lowercase.

## Suggested Alias Map (Writer Discipline, Not Enforcement)

- `architecture-decision` -> `decision:architecture`
- `d2` -> `topic:d2`
- `provenance` -> `topic:provenance`
- `resolved` -> `status:resolved`
- `option-a3` -> `option:a3`
- `critique-round-4` -> `phase:critique-round-4`

Use both old and new tags during a transition period if query stability matters.
