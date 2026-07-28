"""Versioned schema/data-model constants for the L2.2 evidence index.

``evidence_index.json`` (``docs/phase_f/l2_2_design_a/evidence_index.json``)
is the ONE tracked artifact this package produces. It is generator-only:
never hand-edit it. Bump ``SCHEMA_VERSION`` on any incompatible change to
the row shape and update ``EVIDENCE_INDEX_SPEC.md`` in lockstep.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence.catalog import CATALOG_PATH, REPO_ROOT  # noqa: E402

SCHEMA_VERSION = 1

# --- Canonical evidence locations -------------------------------------------
#
# Mirrors the runner-native output layout documented in
# docs/phase_f/l2_2_design_a/L2_2_DESIGN_A_SPEC.md section 13
# (result.json / input_manifest.json / provenance.json / thresholds.json /
# null_calibration.json / SUMMARY.json / allocator_inputs.json), simplified
# to a single `latest/` directory per process instead of timestamped run
# directories plus a `latest` symlink -- Windows junctions/symlinks are a
# known operational trap on this project's Windows host (see the PM OS
# TRAPS.md), so we avoid them here entirely.
EVIDENCE_ROOT = REPO_ROOT / "artifacts" / "l2_2_gates"

# design_a_per_tick harness evidence lives directly under <process>/latest/.
DESIGN_A_SUBDIR = "latest"
# event_class processes route to a distinct sub-directory: the L2.event
# harness does not exist yet (see PROCESS_CATALOG.yaml harness_type policy),
# so this is reserved for forward compatibility and is expected to be empty
# (-> MISSING_EVIDENCE) until that harness is built.
EVENT_CLASS_SUBDIR = "latest_event"

# The one tracked generator output.
INDEX_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "evidence_index.json"

# --- Authority files ---------------------------------------------------------

REQUIRED_AUTHORITY_FILES = ("result.json", "input_manifest.json", "provenance.json")
OPTIONAL_SIDECAR_FILES = (
    "thresholds.json",
    "null_calibration.json",
    "SUMMARY.json",
    "allocator_inputs.json",
    "analytical_check.json",
)

# --- Verdict vocab ------------------------------------------------------------

# Channel-level verdicts that are mechanically re-derived as "green" (never
# trusted from the stored result.json["channels"][c]["verdict"] string).
GREEN_CHANNEL_VERDICTS = frozenset({"PASS", "SEED_NOISE"})
# Channel verdicts that are reported but excluded from process-level
# aggregation (per L2_2_DESIGN_A_SPEC.md section 8.2).
NON_GATING_CHANNEL_VERDICTS = frozenset({"EVENT_CHANNEL_DEFERRED", "INSUFFICIENT_SAMPLES"})

# Mirrors universals.min_events_for_distribution in PROCESS_CATALOG.yaml.
MIN_NONZERO_EVENTS = 30

# Warning-string sentinel prefixes that unconditionally demote a process row
# to non-green, regardless of any stored verdict.
HARD_FAIL_SENTINEL_PREFIXES = (
    "KARR_SINGLE_SEED_REUSED",
    "TRIVIAL_RNG_LEAK",
    "PRIMARY_CHANNEL_ORACLE_LAUNDERING",
)
# A demotion from FAIL to informational applied by the runner when
# closed_form_dominant is confirmed. Still non-green here unless linked H12
# evidence is present with a machine-checked nontrivial sample count.
DETERMINISTIC_CONVERGENCE_PREFIX = "PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE"

# --- Row-level status codes (used as `reasons[]` prefixes / mechanical_verdict) --

STATUS_MISSING_EVIDENCE = "MISSING_EVIDENCE"
STATUS_SCHEMA_INVALID = "SCHEMA_INVALID"
STATUS_STALE_VS_TREE = "STALE_VS_TREE"
STATUS_PROCESS_NAME_MISMATCH = "PROCESS_NAME_MISMATCH"
STATUS_NM_MISMATCH = "NM_MISMATCH"
STATUS_MISSING_EVALUATOR = "MISSING_EVALUATOR"
STATUS_SENTINEL_FAIL = "SENTINEL_FAIL"
STATUS_DEFERRED = "DEFERRED"
STATUS_PRIMARY_VACUOUS = "PRIMARY_CHANNEL_VACUOUS"
STATUS_NO_GATEABLE_CHANNELS = "NO_GATEABLE_CHANNELS"
STATUS_FAIL = "FAIL"
STATUS_PASS = "PASS"

__all__ = [name for name in globals() if name.isupper()] + ["CATALOG_PATH"]
