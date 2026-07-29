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

# --- Portable evidence bundle -------------------------------------------------
#
# EVIDENCE_ROOT above is fully gitignored (.gitignore line ~30): it is the
# *live* directory the sweep launcher writes runner-native output to, and it
# legitimately does not exist in a fresh clone. That is fine for `result.json`
# et al (compact JSON, cheap to regenerate by re-running the sweep) but it
# means `generate`/`audit` had no tracked fallback to read from at all in a
# fresh clone -- the whole index would look like MISSING_EVIDENCE regardless
# of what is actually committed. BUNDLE_ROOT is a tracked mirror of just the
# compact authority + sidecar files (never `BUNDLE_EXCLUDE_FILES`, which hold
# large raw per-seed/tick arrays) under the same `<process>/<subdir>/` layout;
# see `generator.bundle_process_evidence()`. `default_evidence_root()` below
# is what `generate`/`audit` actually use when no `--evidence-root` is given.
BUNDLE_ROOT = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "evidence_bundle"

# --- Authority files ---------------------------------------------------------

REQUIRED_AUTHORITY_FILES = ("result.json", "input_manifest.json", "provenance.json")

# The runner (`tests/vivarium/l2_2_design_a_runner.py`) unconditionally
# writes every one of these for every design_a_per_tick process -- see its
# `_write_json` calls around evidence emission. A missing one means evidence
# generation itself did not complete (or was truncated/corrupted), never a
# legitimate "not applicable" case: `analytical_check.json` itself is always
# written, using `{"applicable": false, "reason": ...}` for processes with no
# analytical evaluator, rather than omitting the file. These are therefore
# MANDATORY for a row to be green, exactly like REQUIRED_AUTHORITY_FILES.
MANDATORY_SIDECAR_FILES = (
    "thresholds.json",
    "null_calibration.json",
    "SUMMARY.json",
    "analytical_check.json",
)
# Never required to exist and never mirrored into the tracked portable
# bundle: allocator_inputs.json holds large raw per-seed/tick arrays that no
# verdict calculation reads (it is diagnostic bulk, not gating authority --
# see scope-correction note in EVIDENCE_INDEX_SPEC.md Section 13.7). It is
# intentionally NOT tracked or hashed anywhere, including
# sweep_provenance.json: tracking a hash for a file nothing ever checks
# would be authority theater, not evidence.
INFORMATIONAL_ONLY_FILES = ("allocator_inputs.json",)

# Back-compat aliases for the pre-hardening names: `OPTIONAL_SIDECAR_FILES`
# used to mean "hashed when present, mirrored into the bundle when present";
# that concept is now split into MANDATORY_SIDECAR_FILES (required, always
# hashed+bundled) and INFORMATIONAL_ONLY_FILES (never required, never
# hashed, never bundled -- purely diagnostic bulk).
OPTIONAL_SIDECAR_FILES = MANDATORY_SIDECAR_FILES + INFORMATIONAL_ONLY_FILES
BUNDLE_EXCLUDE_FILES = INFORMATIONAL_ONLY_FILES

# --- Sweep-launcher-written provenance sidecar -------------------------------
#
# `provenance.json` above is runner-written and, in this project's WSL/
# Windows-linked-worktree environment, its own `git_sha` field is always the
# literal string "unknown" (the runner's plain `git rev-parse HEAD` cannot
# resolve a Windows-created worktree's `gitdir:` pointer file under native
# WSL git -- a pre-existing runner limitation that is out of scope to fix,
# since the runner itself is off-limits to modify). `sweep_provenance.json`
# is therefore written independently by `scripts/l22_evidence/sweep.py`
# itself (reusing the already-accepted worktree-gitdir-resolution logic in
# `populate.py`), AFTER the runner's own mandatory files are confirmed
# present/parseable/matching -- i.e. its mere presence is the "completion
# sentinel written last" for a given evidence directory. It records: the
# REAL git SHA (never "unknown") + dirty flag when resolvable -- recorded
# for human inspection but NOT itself gating (see scope-correction note
# below), sha256 of the runner/helpers/projections/catalog source files as
# they existed at generation time (so later drift is mechanically
# detectable, exactly like `_check_current_tree_staleness` already does for
# `input_manifest.json`'s own inputs), and the evaluator schema version that
# scored the result.
#
# Gating authority is the source-file content hashes + evaluator schema
# version, NOT git_sha/git_dirty: an unknown/missing git SHA alone does not
# make a row stale as long as every recorded source hash and the evaluator
# schema version still match the CURRENT tree. Git plumbing (resolving a
# Windows-linked worktree's real HEAD) is inherently more fragile than a
# plain sha256 comparison, and content hashes are what actually prove the
# evidence was generated against the code now on disk -- the SHA is
# corroborating metadata, not the authority itself.
SWEEP_PROVENANCE_FILE = "sweep_provenance.json"
# Bumped 1 -> 2 for the R1/R2/R3 sentinel-binding hardening series: v2
# sweep_provenance.json additionally carries `completion_status`,
# `sidecar_hashes` (R1: binds the sentinel to the exact bytes of every
# fixed tracked authority/sidecar file sitting next to it -- a sentinel
# copied wholesale from a different process's evidence dir, even with its
# `process`/`n_seeds`/`m_ticks` fields hand-edited to match, no longer
# validates because those files' hashes won't match), a per-process
# `oc_module` entry in `source_hashes` (R2), and `inputs_verified` (R3).
# See `sweep.build_sweep_provenance` / `generator._check_sweep_provenance_staleness`.
SWEEP_PROVENANCE_SCHEMA_VERSION = 2

# The sentinel's own recorded `completion_status` must equal this exact
# string; anything else (missing, partial, hand-edited) is non-green.
COMPLETION_STATUS_COMPLETE = "COMPLETE"

RUNNER_SCRIPT = REPO_ROOT / "tests" / "vivarium" / "l2_2_design_a_runner.py"
RUNNER_HELPERS_MODULE = REPO_ROOT / "tests" / "vivarium" / "_l2_2_design_a_runner_helpers.py"
RUNNER_PROJECTIONS_MODULE = REPO_ROOT / "tests" / "vivarium" / "_l2_2_design_a_projections.py"

# Named source files whose content hash `sweep_provenance.json` records at
# generation time and the generator re-checks against the CURRENT tree --
# the same names are used as dict keys on both sides so drift in any one of
# them is individually named in `reasons[]`, not just "something changed".
# These four are process-AGNOSTIC (shared by every process). The process's
# own `oc_module` implementation file is hashed separately, under the
# `"oc_module"` key, by `sweep.current_source_hashes(oc_module=...)` /
# `generator._current_source_hashes(entry)` -- it is deliberately NOT part
# of this fixed dict because it differs per process (R2: a code change to
# `karr_dna_repair.py` must stale only DNARepair's row, never all 18).
SWEEP_PROVENANCE_SOURCE_FILES = {
    "runner": RUNNER_SCRIPT,
    "helpers": RUNNER_HELPERS_MODULE,
    "projections": RUNNER_PROJECTIONS_MODULE,
    "catalog": CATALOG_PATH,
}

# --- Per-process metric-evaluation dependency modules (beyond the four
# shared SWEEP_PROVENANCE_SOURCE_FILES and a process's own oc_module) ------
#
# Some processes' metric computation reads modules that are neither one of
# the four shared files above nor that process's own `oc_module` (its
# `opencell/vivarium/karr_<process>.py` implementation). Metabolism is the
# known case: its `fva_feasibility` channel (see
# `verdict._rederive_fva_channel`) is computed by
# `_metabolism_fva_sample_feasibility()` in `l2_2_design_a_runner.py`
# (already hashed as `"runner"`), which calls
# `opencell.m1.calc_flux_bounds.compute_bounds`,
# `opencell.m1.fva.fva_range`/`substrate_delta_range_from_fva`, and
# `opencell.m1.karr_metabolism.solve_fba`/`load_default` (via
# `_l2_2_design_a_runner_helpers.py`'s `_metabolism_model()`, already
# hashed as `"helpers"`) -- none of which is itself hashed by any existing
# key, so a change to one of these three `opencell/m1/*.py` modules would
# otherwise change Metabolism's actual FVA feasibility computation without
# staling its evidence at all.
#
# PROCESS_CATALOG.yaml does not declare which metric_type/aggregation a
# process's channels use -- that is an opt-in choice made by the runner's
# process factory (`process.l2_2_metric_type = "fva_feasibility"`, set only
# for Metabolism in `_l2_2_design_a_runner_helpers.py`), not a catalog
# field -- so there is no mechanical rule to derive this registry from the
# catalog today. This is therefore a small, explicit, hand-maintained
# by-process-name registry (mirroring the R2 `oc_module` precedent of a
# process-specific hash), not a generalized dependency-graph scanner. Keep
# it minimal: only add an entry once a metric evaluator is VERIFIED (by
# tracing the runner's actual call graph, as above) to read output that
# module computes -- never speculatively, and never for a module already
# covered by `SWEEP_PROVENANCE_SOURCE_FILES` or a process's `oc_module`.
FVA_MODULE = REPO_ROOT / "opencell" / "m1" / "fva.py"
CALC_FLUX_BOUNDS_MODULE = REPO_ROOT / "opencell" / "m1" / "calc_flux_bounds.py"
M1_KARR_METABOLISM_MODULE = REPO_ROOT / "opencell" / "m1" / "karr_metabolism.py"

METRIC_DEPENDENCY_FILES: dict[str, dict[str, Path]] = {
    "Metabolism": {
        "fva_module": FVA_MODULE,
        "calc_flux_bounds_module": CALC_FLUX_BOUNDS_MODULE,
        "m1_karr_metabolism_module": M1_KARR_METABOLISM_MODULE,
    },
}

# The fixed set of tracked authority/sidecar files R1 binds a
# sweep_provenance.json sentinel to (via its own `sidecar_hashes` field) --
# every file `build_process_row` requires unconditionally, minus nothing.
# Defined once here so sweep.py (writer) and generator.py (verifier) can
# never drift apart on which files are bound.
SWEEP_PROVENANCE_SIDECAR_FILES = REQUIRED_AUTHORITY_FILES + MANDATORY_SIDECAR_FILES


def default_evidence_root() -> Path:
    """The evidence root `generate`/`audit` read from when none is given.

    Prefers the live sweep-output tree (EVIDENCE_ROOT) when it exists and is
    non-empty locally -- this is the unmodified, pre-existing behavior for
    anyone iterating against a real local sweep. Falls back to the tracked,
    portable BUNDLE_ROOT otherwise (e.g. a fresh clone that never ran the
    sweep locally). Both hold byte-identical copies of every file `generate`
    actually reads, so this choice never changes which verdict is produced --
    only where the bytes are read from.
    """
    if EVIDENCE_ROOT.is_dir() and any(EVIDENCE_ROOT.iterdir()):
        return EVIDENCE_ROOT
    return BUNDLE_ROOT


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
# A row whose runner-produced evidence is otherwise complete/matching but
# whose sweep_provenance.json shows a source-file (runner/helpers/
# projections/catalog) hash mismatch versus the CURRENT tree, or an
# evaluator_schema_version mismatch versus the CURRENT
# `verdict.EVALUATOR_SCHEMA_VERSION`. An unknown/missing git SHA alone does
# NOT trigger this status as long as every source hash and the evaluator
# schema version still match (git SHA is recorded informationally, not
# gating -- see the SWEEP_PROVENANCE_FILE docstring above). Distinct from
# STATUS_MISSING_EVIDENCE (nothing was produced at all) and
# STATUS_STALE_VS_TREE (an `input_manifest` source drifted): this
# specifically means "this evidence was produced before/without the
# provenance hardening (or under stale source files) and must be
# regenerated", never inferred as compliant.
STATUS_STALE_PROVENANCE = "STALE_SWEEP_PROVENANCE"

# `input_manifest.json["inputs"]` is empty, missing, or every entry is
# missing a `path`/`sha256` key -- R3: a non-empty, hash-backed inputs list
# is mandatory for design_a_per_tick evidence to be trusted at all, never
# silently treated as "nothing to check".
STATUS_EMPTY_INPUT_MANIFEST = "EMPTY_INPUT_MANIFEST"

# Path prefix convention that marks an `input_manifest.json["inputs"]`
# entry as raw Karr-oracle data (e.g. "data/m1_sources/karr_native/..."):
# gitignored, never tracked in git, and intentionally absent in a fresh
# clone / portable evidence-bundle-only checkout. Entries under this prefix
# are exempt from `generator._check_current_tree_staleness`'s current-tree
# rehash UNLESS `--verify-input-files` is explicitly requested (and the
# data happens to be mounted locally) -- see that function's
# `strict_input_files` parameter. Every OTHER input path (runner/helpers/
# projections code, all tracked in git) is always rehashed unconditionally,
# in both modes.
ORACLE_DATA_PATH_PREFIX = "data/"

__all__ = [name for name in globals() if name.isupper()] + ["CATALOG_PATH", "default_evidence_root"]
