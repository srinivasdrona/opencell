"""Versioned schema/data-model constants for the L2.2 evidence index.

``evidence_index.json`` (``docs/phase_f/l2_2_design_a/evidence_index.json``)
is the ONE tracked artifact this package produces. It is generator-only:
never hand-edit it. Bump ``SCHEMA_VERSION`` on any incompatible change to
the row shape and update ``EVIDENCE_INDEX_SPEC.md`` in lockstep.
"""

from __future__ import annotations

import hashlib
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

# --- H12 machine-evidence linkage --------------------------------------------
#
# Separate from result.json (the runner's own authority file, never
# hand-mutated by this package to add H12 support): H12_EVIDENCE_INDEX_PATH
# is a small tracked side-index mapping process name -> repo-relative path
# of that process's H12 machine-evidence artifact (produced by
# scripts/l22_evidence/h12.py). `generator.build_evidence_index` merges this
# file's entries into an in-memory copy of the loaded `result_payload`
# (only when `result.json` itself does not already carry an
# `h12_evidence_ref`) before mechanical re-derivation -- the on-disk
# result.json is never modified. See EVIDENCE_INDEX_SPEC.md "H12 evidence
# linkage" section.
H12_EVIDENCE_INDEX_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "h12_evidence_index.json"

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

# Version of the raw RUNNER EVIDENCE CONTRACT: the fixed set of
# channel-level fields (e.g. `per_tick_vector_w1_mean`'s `w1_oc_vs_karr`/
# `threshold`/`q95_null`/`n_nonzero_oc`/`n_nonzero_karr`; `per_component`'s
# `component_raw_w1`/`component_scales`/`scaled_distance_threshold`/
# `component_n_nonzero_oc`/`component_n_nonzero_karr`; `hurdle`'s seven
# fields; `fva_feasibility`'s five fields) that
# `tests/vivarium/l2_2_design_a_runner.py` writes into `result.json`/its
# sidecars and that every `verdict._rederive_*_channel` function reads as
# raw authority. Distinct from `SCHEMA_VERSION` (the `evidence_index.json`
# ROW shape) and `SWEEP_PROVENANCE_SCHEMA_VERSION` (the
# `sweep_provenance.json` SENTINEL shape): this one versions the RUNNER's
# OWN raw-evidence field contract, not this package's own output shapes --
# the runner itself is off-limits to modify (see module docstrings across
# this package), so bumping this constant is reserved for a FUTURE task
# that actually changes what raw fields the runner writes (unlike
# `verdict.EVALUATOR_SCHEMA_VERSION`, a mismatch here means the STORED RAW
# BYTES themselves no longer match what the current evaluator logic
# assumes, which content hashes alone cannot detect -- so this IS gating
# for both `sweep.evidence_is_valid` and
# `generator._check_sweep_provenance_staleness`, unlike
# `evaluator_schema_version`). Recorded on every fresh
# `sweep_provenance.json` sentinel by `sweep.build_sweep_provenance`; an
# ABSENT `result_schema_version` field (every sentinel written before this
# constant existed) is treated as version 1, not as missing/invalid -- see
# `sweep.evidence_is_valid`/`generator._check_sweep_provenance_staleness`.
# The current raw result.json/sidecar contract has not changed as part of
# introducing this constant, so its value is 1 and no existing evidence is
# staled by this change alone.
RESULT_SCHEMA_VERSION = 1

RUNNER_SCRIPT = REPO_ROOT / "tests" / "vivarium" / "l2_2_design_a_runner.py"
RUNNER_HELPERS_MODULE = REPO_ROOT / "tests" / "vivarium" / "_l2_2_design_a_runner_helpers.py"
RUNNER_PROJECTIONS_MODULE = REPO_ROOT / "tests" / "vivarium" / "_l2_2_design_a_projections.py"
EVENT_BRIDGE_MODULE = REPO_ROOT / "scripts" / "l22_evidence" / "event_bridge.py"
DNA_DAMAGE_EVENT_VERIFIER_MODULE = REPO_ROOT / "scripts" / "l22_evidence" / "dna_damage_event_verifier.py"
DNA_DAMAGE_STIMULUS_COHORT_MODULE = REPO_ROOT / "scripts" / "l2_event" / "dna_damage_stimulus_cohort.py"
L2_EVENT_RUNNER_MODULE = REPO_ROOT / "scripts" / "l2_event" / "runner.py"
L2_EVENT_METRICS_MODULE = REPO_ROOT / "scripts" / "l2_event" / "metrics.py"
L2_EVENT_EVIDENCE_MODULE = REPO_ROOT / "scripts" / "l2_event" / "evidence.py"
L2_EVENT_REGISTRY_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_event" / "event_registry.yaml"
# "Final zero-cost delta" (Opus5 ACCEPT bbc6aa6 conditional follow-up):
# every in-scope process's `oc_module` lives under `opencell/vivarium/`
# (`opencell/vivarium/karr_<process>.py` -- verified against every
# `PROCESS_CATALOG.yaml` entry, all 22 in-scope processes, not just the 18
# `design_a_per_tick` ones). Importing ANY of those files always executes
# `opencell/vivarium/__init__.py` FIRST (ordinary Python package-import
# semantics, identical in kind to the M1/M2/M3/state package-init entries
# above -- just wider in reach, since literally every oc_module sits
# inside this one package). That init module itself does module-scope
# `from opencell.vivarium.<mod> import ...` for `composite.py`,
# `karr_composite.py`, `karr_metabolism.py`, `karr_transcription.py`,
# `karr_translation.py`, `persist.py`, and `processes.py` -- verified by
# direct inspection -- so a change to `opencell/vivarium/__init__.py`
# itself (e.g. adding/removing/reordering what it imports/re-exports) is a
# real runtime dependency of every process's import, not a documentation
# nicety. Because it is genuinely shared by every process regardless of
# harness_type (unlike `l2_replay_common.py`, which only `design_a_per_tick`
# processes route through -- see `HARNESS_DEPENDENCY_FILES` below), it
# belongs in this always-applies, process-agnostic
# `SWEEP_PROVENANCE_SOURCE_FILES` dict, not the harness-scoped
# `HARNESS_DEPENDENCY_FILES` one -- observably, today, this only affects
# the 18 `design_a_per_tick` rows the sweep actually generates evidence
# for (no `event_class` sweep/evidence exists yet), but the key applies
# uniformly to whichever processes are later evaluated, exactly like the
# other four entries in this dict.
VIVARIUM_INIT_MODULE = REPO_ROOT / "opencell" / "vivarium" / "__init__.py"

# Named source files whose content hash `sweep_provenance.json` records at
# generation time and the generator re-checks against the CURRENT tree --
# the same names are used as dict keys on both sides so drift in any one of
# them is individually named in `reasons[]`, not just "something changed".
# These five are process-AGNOSTIC (shared by every process). The process's
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
    "vivarium_init": VIVARIUM_INIT_MODULE,
}

# Event-class bridge rows must stale on the EVENT path that actually
# produced/translated their authority, not on Design-A runner files they
# never touch. Keep the design_a_per_tick set above untouched for the 18
# existing sweep rows; event_class rows switch to this narrower shared set
# plus their process-specific dependencies below.
EVENT_CLASS_SOURCE_FILES = {
    "event_bridge": EVENT_BRIDGE_MODULE,
    "l2_event_runner": L2_EVENT_RUNNER_MODULE,
    "l2_event_metrics": L2_EVENT_METRICS_MODULE,
    "l2_event_evidence": L2_EVENT_EVIDENCE_MODULE,
    "l2_event_registry": L2_EVENT_REGISTRY_PATH,
    "catalog": CATALOG_PATH,
    "vivarium_init": VIVARIUM_INIT_MODULE,
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
# F1 (Opus5 final review): Metabolism's `karr_metabolism.py` (already
# hashed above) itself imports `opencell.m1.karr_metabolism_writeback` at
# module scope -- verified by direct inspection of
# `opencell/vivarium/karr_metabolism.py` -- which is not itself covered by
# any existing key, so a change to it would silently escape staleness
# detection.
KARR_METABOLISM_WRITEBACK_MODULE = REPO_ROOT / "opencell" / "m1" / "karr_metabolism_writeback.py"
# F5: `karr_metabolism.py` also imports `_Mcg16807` (the MCG RNG) from
# `opencell/vivarium/karr_protein_decay_light.py` -- verified by direct
# inspection. This file is ALSO ProteinDecay's own `oc_module` (hashed
# there under the `"oc_module"` key already), but for Metabolism it is an
# extra, separately-registered runtime dependency.
KARR_PROTEIN_DECAY_LIGHT_MODULE = REPO_ROOT / "opencell" / "vivarium" / "karr_protein_decay_light.py"
# Translation's own `oc_module` (`opencell/vivarium/karr_translation.py`)
# directly imports `from opencell.m3 import translation as tl` at module
# scope -- verified by direct inspection -- so its runtime numeric
# dependency is not fully covered by the `oc_module` hash alone either.
M3_TRANSLATION_MODULE = REPO_ROOT / "opencell" / "m3" / "translation.py"
# F5: `karr_translation.py` also does `from . import karr_translation_v3`
# at module scope (inside `_install_translation_v3_release_guard()`,
# called unconditionally at import time) -- verified by direct inspection.
# Registered here purely so the AST import-completeness audit (see
# `tests/scripts/_l22_ast_import_audit.py`) has zero uncovered first-party
# imports for Translation's `oc_module`; it is NOT believed to feed
# Translation's actual Design-A metric computation (the runner instantiates
# `KarrTranslationProcess` from `karr_translation.py` itself -- see
# `_l2_2_design_a_runner_helpers.py::_translation_process` --, never
# `KarrTranslationV3Process`, and the guard installer is wrapped in a bare
# `try/except Exception: return`, so a missing/broken `karr_translation_v3.py`
# does not even prevent Translation's process from working). Registering it
# anyway costs nothing and removes any doubt.
KARR_TRANSLATION_V3_MODULE = REPO_ROOT / "opencell" / "vivarium" / "karr_translation_v3.py"
# Transcription's own `oc_module` (`opencell/vivarium/karr_transcription.py`)
# imports `from opencell.m2 import transcription as tx` at module scope.
M2_TRANSCRIPTION_MODULE = REPO_ROOT / "opencell" / "m2" / "transcription.py"
# ProteinProcessingI's and RNAProcessing's own `oc_module` files both
# import helper functions (`_parse_wid_array`/`_resolve_fixture_path`)
# from `opencell/vivarium/karr_trna_aminoacylation.py` -- which is ALSO
# tRNAAminoacylation's own `oc_module` (hashed there already), but is an
# extra, separately-registered runtime dependency for these other two
# processes.
KARR_TRNA_AMINOACYLATION_MODULE = REPO_ROOT / "opencell" / "vivarium" / "karr_trna_aminoacylation.py"
# ProteinTranslocation's own `oc_module` does `from opencell.util import
# MatlabRandStream` at module scope -- verified by direct inspection.
# `opencell.util` is a PACKAGE (`opencell/util/__init__.py`), not a bare
# module: `UTIL_MODULE` binds the direct import target (`__init__.py`
# itself, a 1-line re-export shim), and `UTIL_MATLAB_RNG_MODULE` binds
# `opencell/util/matlab_rng.py` -- the file that actually defines
# `MatlabRandStream` and its RNG numeric logic, which `__init__.py`
# re-exports -- registered explicitly (both, like Metabolism's one-hop
# `karr_metabolism_writeback_module` above) since a change to the RNG
# implementation itself must stale ProteinTranslocation even though its
# `oc_module` only ever imports the package, never the submodule directly.
UTIL_MODULE = REPO_ROOT / "opencell" / "util" / "__init__.py"
UTIL_MATLAB_RNG_MODULE = REPO_ROOT / "opencell" / "util" / "matlab_rng.py"
# `opencell/m_gen_constants.py` is imported by DNASupercoiling's own
# `oc_module` (`GENOME_LENGTH_BP`) and, for the event-class DNADamage
# process, its own `oc_module` too -- both DIRECT, module-scope imports,
# verified by inspection.
M_GEN_CONSTANTS_MODULE = REPO_ROOT / "opencell" / "m_gen_constants.py"
# `chromosome_store.py`/`chromosome_views.py` are imported by SOME but not
# all chromosome-coupled processes' own `oc_module` implementation files
# (DNARepair imports both; DNASupercoiling/Replication/ReplicationInitiation
# import only `chromosome_store`; the event-class DNADamage imports both).
CHROMOSOME_STORE_MODULE = REPO_ROOT / "opencell" / "state" / "chromosome_store.py"
CHROMOSOME_VIEWS_MODULE = REPO_ROOT / "opencell" / "vivarium" / "chromosome_views.py"
# B1 (Opus5 "explicit registry REJECT" follow-up): `chromosome_store.py`
# itself (already registered above as `CHROMOSOME_STORE_MODULE` for every
# process that imports it) has its OWN one-hop dependency on
# `opencell/m_gen_constants.py` -- a CLASS-BODY-scope import (`class
# ChromosomeStore: ... from opencell.m_gen_constants import
# GENOME_LENGTH_BP as _GENOME_LENGTH_BP, N_CHROMOSOME_COMPARTMENTS as
# _N_CHROMOSOME_COMPARTMENTS`), executed at module-import time (class
# bodies execute on import, unlike function bodies) and consumed as the
# actual numeric default `shape` for every `ChromosomeStore()` constructed
# without an explicit shape -- verified by direct inspection of
# `opencell/state/chromosome_store.py`. This was a live gap: DNARepair,
# Replication, and ReplicationInitiation only import `chromosome_store`
# directly (never `m_gen_constants` themselves), so a change to
# `GENOME_LENGTH_BP`/`N_CHROMOSOME_COMPARTMENTS` previously stale NEITHER
# their `oc_module` hash NOR any registered dependency hash for those
# three processes, even though it changes their actual runtime chromosome
# shape default. DNASupercoiling and DNADamage already register
# `M_GEN_CONSTANTS_MODULE` because THEIR OWN `oc_module` imports it
# directly (module scope) -- unaffected/retained, not duplicated logic.
# Because the import lives inside `ChromosomeStore`'s class body, not
# module scope, it is (like `karr_translation_v3`'s function-body import)
# outside the TEST-ONLY AST completeness audit's module-scope-only
# detection surface by design; see the audit module's docstring and
# `_DOCUMENTED_EXCLUSIONS` in `test_l22_evidence_ast_completeness.py`.

# --- Package `__init__.py` execution (C2, Opus5 "explicit registry REJECT"
# follow-up) -----------------------------------------------------------------
#
# Importing ANY submodule of a Python package (e.g. `from opencell.m1
# import calc_flux_bounds`) always executes that package's own
# `__init__.py` first -- a real part of the runtime import surface, not
# an artifact of static analysis. `opencell/m1/__init__.py`,
# `opencell/m2/__init__.py`, and `opencell/m3/__init__.py` are registered
# for Metabolism/Transcription/Translation respectively (the one process
# each that imports a submodule of that package directly -- verified:
# `karr_metabolism.py` does `from opencell.m1 import calc_flux_bounds as
# cfb` / `from opencell.m1 import karr_metabolism as km`;
# `karr_transcription.py` does `from opencell.m2 import transcription as
# tx`; `karr_translation.py` does `from opencell.m3 import translation as
# tl`). `opencell/state/__init__.py` is registered for every process that
# imports `opencell.state.chromosome_store` -- mechanically confirmed by
# direct inspection to be exactly DNARepair, DNASupercoiling, Replication,
# ReplicationInitiation, and DNADamage (the same five processes already
# registering `CHROMOSOME_STORE_MODULE`; `ChromosomeCondensation` also
# imports it but is out of catalog scope and never looked up). `opencell/
# util/__init__.py` is ALREADY registered above as `UTIL_MODULE` for
# ProteinTranslocation (it IS the direct import target there, not an
# indirect package-init side effect, so no separate constant is needed).
#
# This registers each `__init__.py` FILE itself as one more hop -- the
# SAME "explicit, one-hop, not recursive" policy as every other entry in
# this registry (e.g. `karr_metabolism_writeback_module` for Metabolism).
# It does NOT recursively register whatever THAT `__init__.py` imports in
# turn: `opencell/m2/__init__.py` additionally does `from . import
# transcription_v2` and `opencell/m3/__init__.py` does `from . import
# translation_v2` -- neither `transcription_v2.py` nor `translation_v2.py`
# is separately hashed here (no evidence either file feeds the actual
# Design-A metric computation for Transcription/Translation; expanding
# would require re-verifying that call graph, which is out of this
# patch's explicit scope). A change to `m2/__init__.py`'s own import
# statements (e.g. adding/removing what it re-exports) is still caught by
# this entry; a change to `transcription_v2.py`'s CONTENT while `m2/
# __init__.py`'s own bytes stay the same would not be -- a disclosed,
# not-yet-closed residual gap, structurally identical to why this
# registry is not a generalized recursive-import-graph hasher elsewhere
# either.
M1_INIT_MODULE = REPO_ROOT / "opencell" / "m1" / "__init__.py"
M2_INIT_MODULE = REPO_ROOT / "opencell" / "m2" / "__init__.py"
M3_INIT_MODULE = REPO_ROOT / "opencell" / "m3" / "__init__.py"
STATE_INIT_MODULE = REPO_ROOT / "opencell" / "state" / "__init__.py"
L2_EVENT_RIBOSOME_GATE_ADAPTER_MODULE = REPO_ROOT / "scripts" / "l2_event" / "adapters" / "ribosome_assembly_gate.py"
L2_EVENT_RIBOSOME_SMOKE_ADAPTER_MODULE = REPO_ROOT / "scripts" / "l2_event" / "adapters" / "ribosome_assembly_smoke.py"
L2_EVENT_RIBOSOME_N50_GATE_MODULE = REPO_ROOT / "scripts" / "l2_event" / "ribosome_assembly_n50_gate.py"
L2_EVENT_RIBOSOME_SEED_AUDIT_MODULE = REPO_ROOT / "scripts" / "l2_event" / "ribosome_assembly_seed_audit.py"
L2_REPLAY_COMMON_MODULE = REPO_ROOT / "tests" / "vivarium" / "l2_replay_common.py"

# --- Explicit per-process runtime dependency registry (F1, corrected F5) ----
#
# A prior revision (F1) derived the chromosome_store/chromosome_views
# entries MECHANICALLY, by AST-scanning each process's own `oc_module`
# source at RUNTIME (inside `sweep.current_source_hashes`/
# `generator._current_source_hashes`, i.e. on the hot path that computes
# `sweep_provenance.json["source_hashes"]`). Opus5's review of that design
# rejected it: mechanical derivation belongs in a TEST-ONLY completeness
# AUDIT (see `tests/scripts/_l22_ast_import_audit.py` /
# `test_l22_evidence_ast_completeness.py`), never in the runtime
# hashing/staleness path itself -- the set of dependency keys a
# `sweep_provenance.json` sentinel is bound to must be a small, explicit,
# reviewable, hand-maintained registry (mirroring the existing
# `oc_module`/harness-scoped precedents), not a live AST re-parse of
# arbitrary source files every time evidence is generated or validated.
#
# `PROCESS_DEPENDENCY_FILES` (renamed from the narrower `METRIC_DEPENDENCY_
# FILES`, since it now also covers general per-process state-module
# imports, not just metric-evaluation call-graph edges) is therefore the
# ONE place a process's registered runtime numeric dependencies beyond its
# own `oc_module` and the four shared `SWEEP_PROVENANCE_SOURCE_FILES` live.
# Every entry here was verified by direct inspection of the corresponding
# `oc_module`'s actual import statements (see the per-constant comments
# above) -- never speculative, and never for a module already covered by
# `SWEEP_PROVENANCE_SOURCE_FILES` or that process's own `oc_module`. The
# TEST-ONLY AST completeness audit below cross-checks this registry
# against the real, current import graph and fails loudly if the two ever
# diverge (a new import added to a `karr_*.py` file without a matching
# registry entry, or a registry entry for an import that no longer
# exists) -- catching drift WITHOUT computing hashes from that audit.
#
# `sweep.current_source_hashes()`/`generator._current_source_hashes()`
# merge `PROCESS_DEPENDENCY_FILES.get(<process name>, {})`'s hashes into
# the SAME `source_hashes` dict `oc_module` already lives in -- no new
# gating code path: the existing staleness loop already iterates
# `source_hashes.items()` generically by name.
#
# DNADamage's entry below is `event_class` (not `design_a_per_tick`); it
# is registered here purely for AST-completeness-audit coverage and
# documentation. No event-class sweep exists yet, so
# `current_source_hashes(process="DNADamage", ...)` is never actually
# called by any evidence-generation path today -- this entry has ZERO
# effect on the Design-A tally.
#
# `ChromosomeCondensation` (out of scope: not in `catalog.in_scope_processes()`)
# is deliberately NOT registered here -- it is never looked up by any
# in-scope evidence row regardless, so omitting it has no staling impact
# either way; see EVIDENCE_INDEX_SPEC.md Section 13.11 for why it is
# excluded from the audit too (out-of-scope processes are never iterated).
PROCESS_DEPENDENCY_FILES: dict[str, dict[str, Path]] = {
    "Metabolism": {
        "fva_module": FVA_MODULE,
        "calc_flux_bounds_module": CALC_FLUX_BOUNDS_MODULE,
        "m1_karr_metabolism_module": M1_KARR_METABOLISM_MODULE,
        "karr_metabolism_writeback_module": KARR_METABOLISM_WRITEBACK_MODULE,
        "karr_protein_decay_light_module": KARR_PROTEIN_DECAY_LIGHT_MODULE,
        "m1_init_module": M1_INIT_MODULE,
    },
    "Translation": {
        "m3_translation_module": M3_TRANSLATION_MODULE,
        "karr_translation_v3_module": KARR_TRANSLATION_V3_MODULE,
        "m3_init_module": M3_INIT_MODULE,
    },
    "Transcription": {
        "m2_transcription_module": M2_TRANSCRIPTION_MODULE,
        "m2_init_module": M2_INIT_MODULE,
    },
    "ProteinProcessingI": {
        "karr_trna_aminoacylation_module": KARR_TRNA_AMINOACYLATION_MODULE,
    },
    "RNAProcessing": {
        "karr_trna_aminoacylation_module": KARR_TRNA_AMINOACYLATION_MODULE,
    },
    "ProteinTranslocation": {
        "util_module": UTIL_MODULE,
        "util_matlab_rng_module": UTIL_MATLAB_RNG_MODULE,
    },
    "DNARepair": {
        "chromosome_store_module": CHROMOSOME_STORE_MODULE,
        "chromosome_views_module": CHROMOSOME_VIEWS_MODULE,
        "m_gen_constants_module": M_GEN_CONSTANTS_MODULE,
        "state_init_module": STATE_INIT_MODULE,
    },
    "DNASupercoiling": {
        "chromosome_store_module": CHROMOSOME_STORE_MODULE,
        "m_gen_constants_module": M_GEN_CONSTANTS_MODULE,
        "state_init_module": STATE_INIT_MODULE,
    },
    "Replication": {
        "chromosome_store_module": CHROMOSOME_STORE_MODULE,
        "m_gen_constants_module": M_GEN_CONSTANTS_MODULE,
        "state_init_module": STATE_INIT_MODULE,
    },
    "ReplicationInitiation": {
        "chromosome_store_module": CHROMOSOME_STORE_MODULE,
        "m_gen_constants_module": M_GEN_CONSTANTS_MODULE,
        "state_init_module": STATE_INIT_MODULE,
    },
    "DNADamage": {
        "dna_damage_event_verifier_module": DNA_DAMAGE_EVENT_VERIFIER_MODULE,
        "dna_damage_stimulus_cohort_module": DNA_DAMAGE_STIMULUS_COHORT_MODULE,
        "chromosome_store_module": CHROMOSOME_STORE_MODULE,
        "chromosome_views_module": CHROMOSOME_VIEWS_MODULE,
        "m_gen_constants_module": M_GEN_CONSTANTS_MODULE,
        "l2_projections_module": RUNNER_PROJECTIONS_MODULE,
        "l2_replay_common_module": L2_REPLAY_COMMON_MODULE,
        "state_init_module": STATE_INIT_MODULE,
    },
    "RibosomeAssembly": {
        "l2_event_ribosome_gate_adapter_module": L2_EVENT_RIBOSOME_GATE_ADAPTER_MODULE,
        "l2_event_ribosome_smoke_adapter_module": L2_EVENT_RIBOSOME_SMOKE_ADAPTER_MODULE,
        "l2_event_ribosome_n50_gate_module": L2_EVENT_RIBOSOME_N50_GATE_MODULE,
        "l2_event_ribosome_seed_audit_module": L2_EVENT_RIBOSOME_SEED_AUDIT_MODULE,
    },
}

# --- Harness-level shared dependency (F1: `l2_replay_common.py`) ------------
#
# `tests/vivarium/_l2_2_design_a_runner_helpers.py` (already hashed above as
# `"helpers"`) does a bare `import l2_replay_common` and calls its state/
# projection/update-function helpers for every `design_a_per_tick` process
# -- verified by direct inspection. This is scoped by `harness_type`
# (bound for all 18 `design_a_per_tick` processes, never the 4
# `event_class` ones, which do not go through this runner/helpers module at
# all) rather than by process name, since it is a runner-harness-level
# dependency, not a per-process one -- keyed the same way
# `SWEEP_PROVENANCE_SOURCE_FILES` is, just scoped narrower than "always".
HARNESS_DEPENDENCY_FILES: dict[str, dict[str, Path]] = {
    "design_a_per_tick": {"l2_replay_common": L2_REPLAY_COMMON_MODULE},
}


def harness_dependency_hashes(harness_type: str | None) -> dict[str, str | None]:
    """sha256 of every module registered in `HARNESS_DEPENDENCY_FILES` for
    `harness_type` (e.g. `l2_replay_common.py` for every
    `design_a_per_tick` process) -- empty dict for `None`/an unregistered
    harness_type (e.g. `event_class`, which is intentionally unregistered:
    that harness does not exist yet and does not go through this runner)."""
    return {name: _sha256_module_file(path) for name, path in HARNESS_DEPENDENCY_FILES.get(harness_type or "", {}).items()}


def shared_source_files_for_harness(harness_type: str | None) -> dict[str, Path]:
    """Named source files that every row of `harness_type` should bind.

    `design_a_per_tick` preserves the historical runner/helpers/projections
    set. `event_class` rows bind to the event bridge + L2.event shared
    machinery instead, so a Design-A helper edit does not stale an
    event-class authority row while an event-bridge/adapter edit does.
    Unknown/None falls back to the design_a/default set for backward
    compatibility with existing call sites.
    """
    if harness_type == "event_class":
        return EVENT_CLASS_SOURCE_FILES
    return SWEEP_PROVENANCE_SOURCE_FILES


def _sha256_module_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

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
# P2 zero-activity guard: a PRIMARY channel/component whose OC side has
# zero nonzero observations/events while Karr's side has real (nonzero)
# activity. Distinct from `STATUS_PRIMARY_VACUOUS` (which only fires when
# BOTH sides are zero): here the SUT provably never exhibited behavior
# Karr did on a channel/component the catalog designates as primary, which
# a scaled/hardcoded-scale distance formula could otherwise silently PASS.
# Deliberately excluded from `GREEN_CHANNEL_VERDICTS`/
# `NON_GATING_CHANNEL_VERDICTS` below so it gates as non-green exactly
# like `STATUS_PRIMARY_VACUOUS`. Never applied to non-primary channels/
# components, and never applied to a component where both sides are zero.
STATUS_PRIMARY_ACTIVITY_MISSING = "PRIMARY_ACTIVITY_MISSING"
# Primary low-sample false-green fix: a PRIMARY channel/component whose
# n_nonzero (W1: `n_nonzero_oc`/`n_nonzero_karr`; per_component: a single
# component's `component_n_nonzero_oc`/`component_n_nonzero_karr`; hurdle:
# `n_events_oc`/`n_events_karr`) is below `MIN_NONZERO_EVENTS` on EITHER
# side, checked strictly AFTER the both-zero `STATUS_PRIMARY_VACUOUS` case
# and the OC-zero/Karr-nonzero `STATUS_PRIMARY_ACTIVITY_MISSING` case have
# already been ruled out. Before this fix, a primary channel/component
# with too few samples to trust silently fell through to the generic,
# NON-GATING `"INSUFFICIENT_SAMPLES"` verdict -- excluding it from
# process-level aggregation entirely and letting the process go green off
# its OTHER (non-primary) channels alone, even though the primary
# comparison itself was never actually validated at adequate sample size.
# Deliberately excluded from `GREEN_CHANNEL_VERDICTS`/
# `NON_GATING_CHANNEL_VERDICTS` below so it gates as non-green exactly
# like `STATUS_PRIMARY_VACUOUS`/`STATUS_PRIMARY_ACTIVITY_MISSING`. Never
# applied to non-primary channels/components (those keep the pre-existing,
# non-gating `"INSUFFICIENT_SAMPLES"` verdict), and never applied to a
# per_component component where both sides are genuinely zero (that
# component is a trivial always-zero component, not a low-sample one --
# see `verdict._rederive_per_component_scaled_channel`).
STATUS_PRIMARY_INSUFFICIENT_SAMPLES = "PRIMARY_INSUFFICIENT_SAMPLES"
STATUS_NO_GATEABLE_CHANNELS = "NO_GATEABLE_CHANNELS"
STATUS_FAIL = "FAIL"
STATUS_PASS = "PASS"
# A row whose runner-produced evidence is otherwise complete/matching but
# whose sweep_provenance.json shows a source-file (runner/helpers/
# projections/catalog) hash mismatch versus the CURRENT tree. An
# unknown/missing git SHA alone does NOT trigger this status as long as
# every source hash still matches (git SHA is recorded informationally,
# not gating -- see the SWEEP_PROVENANCE_FILE docstring above). Likewise,
# a `evaluator_schema_version` mismatch alone does NOT trigger this status
# (as of v3): the recorded value is still written and surfaced on every
# row informationally (`row["sweep_provenance"]["evaluator_schema_version"]`),
# but re-deriving already-stored, byte-identical raw metrics under newer
# mechanical-verdict logic is exactly what this evaluator-only hardening
# is FOR -- gating staleness on it as well would force a full sweep rerun
# every time `verdict.py`'s logic is fixed, even when no process/oracle/
# threshold changed and every raw field the new logic needs was already
# present. A genuinely MISSING raw field a newer evaluator requires is
# still caught (as `STATUS_MISSING_EVALUATOR` on the affected channel/
# process, never silently treated as stale-and-skippable). Distinct from
# STATUS_MISSING_EVIDENCE (nothing was produced at all) and
# STATUS_STALE_VS_TREE (an `input_manifest` source drifted): this
# specifically means "this evidence was produced before/without the
# provenance hardening (or under stale source files) and must be
# regenerated", never inferred as compliant. UNLIKE `evaluator_schema_version`,
# a `result_schema_version` mismatch DOES trigger this status: it means the
# STORED RAW result.json/sidecar BYTES themselves were produced under a
# different raw-evidence field contract than the one the current evaluator
# assumes, which no source/sidecar content hash can ever detect (those
# hashes only prove the evidence was generated by the code currently on
# disk, not that its raw field SHAPE matches what that code now expects) --
# see `RESULT_SCHEMA_VERSION`'s own docstring. A sentinel with no
# `result_schema_version` field at all (every sentinel written before that
# constant existed) is treated as version 1, never as missing/invalid.
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

__all__ = [name for name in globals() if name.isupper()] + [
    "CATALOG_PATH",
    "default_evidence_root",
    "harness_dependency_hashes",
    "shared_source_files_for_harness",
]
