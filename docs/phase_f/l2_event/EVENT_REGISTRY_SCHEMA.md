# L2.event Registry Schema

`docs/phase_f/l2_event/event_registry.yaml` — the versioned, event-class-only
process registry that backs `scripts/l2_event/registry.py`. This is a
**separate** file from `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` and
is never used to edit it: the catalog's content hash gates Design-A's own
staleness checks, so this task's L2.event work must not touch it. Instead,
this registry is *derived/validated* against the catalog's process names and
`harness_type` field, read-only, via `validate_against_catalog()` (which
reuses `scripts/l22_extraction/derive_scope.py`'s existing YAML parser).

## Versioning

`schema_version` (top-level int) must equal
`scripts.l2_event.schema.REGISTRY_SCHEMA_VERSION` (currently `1`). Bump both
together whenever a field below changes shape; `load_registry()` refuses to
parse a mismatched version rather than silently guessing at a migration.

## Top-level keys

| Key | Type | Meaning |
|---|---|---|
| `schema_version` | int | Must match `REGISTRY_SCHEMA_VERSION`. |
| `generated_from_catalog` | string | Free-text provenance note (which catalog snapshot/commit this registry was derived from). |
| `spec_ref` | string | Path to the ratified spec this registry implements (`docs/phase_f/L2_EVENT_GATE_SPEC_v4.md`). |
| `processes` | list of process rows | See below. |

## Per-process row fields

| Field | Type | Meaning |
|---|---|---|
| `process` | string | Canonical process name; must match `PROCESS_CATALOG.yaml`'s process `name` exactly. |
| `in_scope_v4` | bool | Whether this process is in the ratified v4 spec's gating scope (spec §8). `Cytokinesis` and `RibosomeAssembly` are `true`; `DNADamage` and `FtsZPolymerization` are `false`. |
| `adapter_id` | string or null | Stable adapter identifier (e.g. `ribosome_assembly.smoke.v1`), or `null` if no adapter exists yet. |
| `adapter_status` | string | One of `not_implemented`, `structural_smoke_only`, `gating_ready`. **No process may claim `gating_ready` in this foundation task** — enforced by `registry.py` cross-checks in tests, not by this schema doc alone. |
| `event_timing_model` | string or null | One of `scripts.l2_event.schema.EVENT_TIMING_MODELS` (`single_firing`, `repeated_firing`), or `null` if undetermined/not-yet-adapted. |
| `magnitude_gateable` | bool | D6's escape hatch: whether a non-redundant payload/magnitude channel exists to gate on. `false` for Cytokinesis (division-marker style event with no independent magnitude channel); the runner must emit `NOT_GATEABLE_REDUNDANT` for the payload channel rather than skip it silently. |
| `required_n_seeds` | int | Ensemble size the catalog declares (currently `50` for all four target processes). The runner refuses (`SINGLE_SEED_ENSEMBLE_REQUIRED`) any gate-mode run with fewer seeds than this. |
| `deferred_reason` | string or null | Required (non-null) when `in_scope_v4: false`; explains why, citing the spec section. |
| `notes` | string | Free-text ground-truth notes — in particular, corrections to any `PROCESS_CATALOG.yaml` inline `notes:` claim this task found to be stale or misleading (e.g. a "L2.2 GREEN" claim based on a single-seed identity replay or a quiescent 0-vs-0 trace, not a calibrated ensemble gate verdict). |

## Validation performed by `scripts/l2_event/registry.py`

* `load_registry()` — schema_version check, required-key presence,
  `event_timing_model` membership in `EVENT_TIMING_MODELS`, non-empty
  `processes` list. Raises `RegistryError` (not a silent default) on any
  violation.
* `validate_against_catalog()` — read-only cross-check: every registry
  process must exist in `PROCESS_CATALOG.yaml` with
  `harness_type: event_class`; `in_scope_v4: true` implies the catalog's
  `in_scope_L2_2` must also be true. Returns a list of human-readable
  problems (empty = consistent) — never raises, so callers can decide
  whether to treat a problem list as fatal.
* `registry_sha256()` — content hash of the registry file itself, recorded
  in each run's `provenance.json` (see `EVIDENCE_INDEX_SPEC.md`-style
  provenance conventions in `scripts/l2_event/evidence.py`).

## Non-goals

This registry never contains process-specific *biology* (no MATLAB
extraction references, no per-observable WID mappings, no numeric
tolerances) — that all belongs to the adapter layer
(`scripts/l2_event/adapters/`) or a future process-specific branch, not this
schema.
