"""Versioned schema/data-model constants for the L2.2 evidence index.

``evidence_index.json`` (``docs/phase_f/l2_2_design_a/evidence_index.json``)
is the ONE tracked artifact this package produces. It is generator-only:
never hand-edit it. Bump ``SCHEMA_VERSION`` on any incompatible change to
the row shape and update ``EVIDENCE_INDEX_SPEC.md`` in lockstep.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence.catalog import (  # noqa: E402
    CATALOG_PATH,
    DEFAULT_N_SEEDS,  # noqa: E402
    REPO_ROOT,
)
from scripts.l22_extraction import derive_scope as _ds  # noqa: E402  (reuse the one YAML loader)

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
# R7: DNASupercoiling's own tick-runner sibling module -- see
# `PROCESS_DEPENDENCY_FILES["DNASupercoiling"]["dnas_runner_helpers_module"]`
# and `runner_helpers_generic_hash`/`tick_runner_entry_hash` below.
DNAS_RUNNER_HELPERS_MODULE = REPO_ROOT / "tests" / "vivarium" / "_l2_2_dnas_runner_helpers.py"
# R11: ReplicationInitiation's own catalog-M-aware trace resolver/identity
# guard sibling module -- see
# `PROCESS_DEPENDENCY_FILES["ReplicationInitiation"]["repinit_runner_helpers_module"]`
# and `runner_helpers_generic_hash`'s R11 section below.
REPINIT_RUNNER_HELPERS_MODULE = REPO_ROOT / "tests" / "vivarium" / "_l2_2_repinit_runner_helpers.py"
# R12: ReplicationInitiation's own requested-M-vs-catalog-M-vs-process
# guard entrypoint (`sweep.runner_command` launches THIS script, never the
# generic `l2_2_design_a_runner.py`, for ReplicationInitiation jobs) -- see
# `PROCESS_DEPENDENCY_FILES["ReplicationInitiation"]["repinit_runner_entrypoint_module"]`.
REPINIT_RUNNER_ENTRYPOINT_MODULE = REPO_ROOT / "tests" / "vivarium" / "_l2_2_repinit_runner_entrypoint.py"
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
# These are process-AGNOSTIC (shared by every process). The process's own
# `oc_module` implementation file is hashed separately, under the
# `"oc_module"` key, by `sweep.current_source_hashes(oc_module=...)` /
# `generator._current_source_hashes(entry)` -- it is deliberately NOT part
# of this fixed dict because it differs per process (R2: a code change to
# `karr_dna_repair.py` must stale only DNARepair's row, never all 18).
#
# R6 catalog-provenance fix (2026-09-04): `PROCESS_CATALOG.yaml` (and, for
# `EVENT_CLASS_SOURCE_FILES` below, `event_registry.yaml`) used to be
# hashed here too, whole-file, under a `"catalog"`/`"l2_event_registry"`
# key -- exactly like `oc_module` BEFORE R2, that made an edit to ANY
# single process's own catalog/registry row invalidate EVERY in-scope
# process's evidence (empirically observed: a Cytokinesis-only M_ticks
# 4000->5000 edit staled all 19 unrelated design_a_per_tick + event_class
# rows at once). Both files are per-process-row YAML documents structurally
# identical in kind to `oc_module` (one file, many processes' own data)
# -- so, mirroring R2's fix for `oc_module`, each process's OWN resolved
# catalog/registry contract is now hashed separately instead, under the
# `"catalog_entry"` (and, for event_class, `"event_registry_entry"`) key
# computed by `process_contract_hashes()` below and merged in by
# `sweep.current_source_hashes()`/`generator._current_source_hashes()` the
# same way `oc_module` is -- never part of this fixed, process-agnostic
# dict. See `resolve_catalog_process_contract`/
# `resolve_event_registry_process_contract`/`process_contract_hashes` and
# EVIDENCE_INDEX_SPEC.md Section 13.18 for the full design and the
# migration of pre-existing tracked evidence to this scheme.
SWEEP_PROVENANCE_SOURCE_FILES = {
    "runner": RUNNER_SCRIPT,
    "helpers": RUNNER_HELPERS_MODULE,
    "projections": RUNNER_PROJECTIONS_MODULE,
    "vivarium_init": VIVARIUM_INIT_MODULE,
}

# Event-class bridge rows must stale on the EVENT path that actually
# produced/translated their authority, not on Design-A runner files they
# never touch. Keep the design_a_per_tick set above untouched for the 18
# existing sweep rows; event_class rows switch to this narrower shared set
# plus their process-specific dependencies below. `l2_event_registry`
# (whole-file `event_registry.yaml`) was removed for the same R6 reason
# `catalog` was: see this dict's sibling docstring above and
# `process_contract_hashes()`.
EVENT_CLASS_SOURCE_FILES = {
    "event_bridge": EVENT_BRIDGE_MODULE,
    "l2_event_runner": L2_EVENT_RUNNER_MODULE,
    "l2_event_metrics": L2_EVENT_METRICS_MODULE,
    "l2_event_evidence": L2_EVENT_EVIDENCE_MODULE,
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
# `opencell/m1/protein_complexes.py` -- direct, module-scope import of
# DNASupercoiling's own oc_module (karr_dna_supercoiling.py), verified by
# inspection.
M1_PROTEIN_COMPLEXES_MODULE = REPO_ROOT / "opencell" / "m1" / "protein_complexes.py"
# The three DNAS-only RNG-oracle ledger modules karr_dna_supercoiling.py
# directly imports (module scope): dnas_chromosome_release_ledger.py,
# dnas_process_rng_ledger.py, dnas_superhelical_density_ledger.py.
DNAS_CHROMOSOME_RELEASE_LEDGER_MODULE = REPO_ROOT / "opencell" / "vivarium" / "dnas_chromosome_release_ledger.py"
DNAS_PROCESS_RNG_LEDGER_MODULE = REPO_ROOT / "opencell" / "vivarium" / "dnas_process_rng_ledger.py"
DNAS_SUPERHELICAL_DENSITY_LEDGER_MODULE = REPO_ROOT / "opencell" / "vivarium" / "dnas_superhelical_density_ledger.py"
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
        # R7: DNASupercoiling's persistent-process-pool tick runner lives in
        # its own sibling module (extracted OUT of the shared, universally-
        # hashed `_l2_2_design_a_runner_helpers.py` -- see that module's
        # `"# ---- DNASupercoiling ----"` section docstring and
        # `_l2_2_dnas_runner_helpers.py`'s module docstring for the full R7
        # incident/rationale). Registering it here makes an edit to IT stale
        # only DNASupercoiling's row, exactly like every other entry in this
        # dict.
        "dnas_runner_helpers_module": DNAS_RUNNER_HELPERS_MODULE,
        # R9: the accepted candidate's own oc_module (karr_dna_supercoiling.py)
        # directly imports these four modules at module scope (verified by
        # inspection) -- the three DNAS-only RNG-oracle ledgers plus
        # opencell/m1/protein_complexes.py.
        "m1_protein_complexes_module": M1_PROTEIN_COMPLEXES_MODULE,
        "dnas_chromosome_release_ledger_module": DNAS_CHROMOSOME_RELEASE_LEDGER_MODULE,
        "dnas_process_rng_ledger_module": DNAS_PROCESS_RNG_LEDGER_MODULE,
        "dnas_superhelical_density_ledger_module": DNAS_SUPERHELICAL_DENSITY_LEDGER_MODULE,
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
        # R11: ReplicationInitiation's catalog-M-aware (M_ticks=200) trace
        # resolver/identity guard lives in its own sibling module (extracted
        # OUT of the shared, universally-hashed
        # `_l2_2_design_a_runner_helpers.py` -- see that module's
        # `"# ---- ReplicationInitiation (R11...)"` section docstring and
        # `_l2_2_repinit_runner_helpers.py`'s module docstring for the full
        # incident/rationale, mirroring R7's DNASupercoiling precedent
        # exactly). Registering it here makes an edit to IT stale only
        # ReplicationInitiation's row.
        "repinit_runner_helpers_module": REPINIT_RUNNER_HELPERS_MODULE,
        # R12: ReplicationInitiation's own requested-M validation entrypoint
        # (`sweep.runner_command` launches it in place of the generic
        # `l2_2_design_a_runner.py` for ReplicationInitiation jobs only) --
        # see `_l2_2_repinit_runner_entrypoint.py`'s module docstring.
        "repinit_runner_entrypoint_module": REPINIT_RUNNER_ENTRYPOINT_MODULE,
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

# The DNAS-only helper was first hashed while freshly generated with CRLF,
# then merged as Git-normalized LF despite identical Python source. Source
# provenance should bind executable text, not that transient line-ending
# difference. Keep all other dependency hashes raw-byte exact; this exception
# is deliberately process/key scoped. The RepInit sibling modules (R11/R12)
# hit the identical CRLF-on-Windows-then-LF-on-commit transient during this
# session and are registered here for the same reason.
LF_NORMALIZED_PROCESS_DEPENDENCIES = frozenset(
    {
        ("DNASupercoiling", "dnas_runner_helpers_module"),
        ("ReplicationInitiation", "repinit_runner_helpers_module"),
        ("ReplicationInitiation", "repinit_runner_entrypoint_module"),
    }
)


def _sha256_lf_normalized(path: Path) -> str | None:
    if not path.is_file():
        return None
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def process_dependency_hashes(process: str) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {}
    for name, path in PROCESS_DEPENDENCY_FILES.get(process, {}).items():
        if (process, name) in LF_NORMALIZED_PROCESS_DEPENDENCIES:
            hashes[name] = _sha256_lf_normalized(path)
        else:
            hashes[name] = _sha256_module_file(path)
    return hashes

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


# --- R7: per-process tick-runner CONTRACT hash (fail-closed, replaces the ---
# --- old whole-file `"helpers"` key coupling every process to every other --
#
# 2026-09 DNASupercoiling integration: the accepted DNASupercoiling-only
# persistent-process-pool fix to `_run_dna_supercoiling_tick` (in
# `_l2_2_design_a_runner_helpers.py`) staled ALL 18 in-scope
# `design_a_per_tick` rows at once, because `SWEEP_PROVENANCE_SOURCE_FILES`
# hashed the ENTIRE runner-helpers file, whole, under a process-agnostic
# `"helpers"` key -- structurally the exact same bug R2 (`oc_module`) and R6
# (`"catalog_entry"`/`"event_registry_entry"`) already fixed for other
# single shared files that hold many processes' own per-process data/code.
#
# The fix here cannot simply move DNASupercoiling's runner function to its
# own file and leave `"helpers"` a plain whole-file hash of
# `_l2_2_design_a_runner_helpers.py`: that file also holds real
# process-AGNOSTIC shared code (`_tick_dispatch`, `_apply_chromosome_update`,
# `_sample_seed`, `compute_w1`, `load_karr_oracle`, ...) that every process's
# verdict genuinely depends on, so a plain per-process split (hashing only
# each process's own runner function and dropping the whole-file check
# entirely) would silently STOP catching a real edit to that shared code --
# an actual weakening of the guard, which is exactly what this design must
# not do.
#
# Instead, `"helpers"` is redefined (`runner_helpers_generic_hash`) as the
# sha256 of this file's source with ONLY the per-process tick-runner
# function BODIES that `_tick_dispatch()` maps to -- and ONLY the ones still
# defined locally in this file -- redacted to a fixed placeholder. Every
# other line (imports, constants, `_tick_dispatch` itself, every other
# shared helper) is preserved verbatim, so an edit to any of that shared
# code still changes `"helpers"` for every process, exactly as before.
# `tick_runner_entry_hash(process)` is the complementary, genuinely
# per-process piece: it resolves the ACTUAL function `_tick_dispatch()`
# binds `process` to -- whether that is a plain local `def` in this file
# (today: every process except DNASupercoiling) or a name imported from a
# registered process-specific sibling module via a plain `from <module>
# import <name> as <local_name>` statement (today: DNASupercoiling, from
# `_l2_2_dnas_runner_helpers.py`) -- and hashes ONLY that function's own
# source text.
#
# Together, `"helpers"` (generic, redacted) + `"tick_runner"` (this
# process's own dispatched function, wherever it lives) cover EXACTLY the
# same source bytes the old whole-file `"helpers"` hash did for any given
# process, split so that an edit confined to one process's OWN runner
# function/module changes only that process's `"tick_runner"` value, never
# any other process's `"helpers"` OR `"tick_runner"` value. Both are
# resolved by STATIC AST inspection of the file text -- never by importing
# or executing `_l2_2_design_a_runner_helpers.py` or its dependencies --
# so computing them stays as cheap and side-effect-free as the plain
# whole-file hash it replaces.
_TICK_DISPATCH_FUNCTION_NAME = "_tick_dispatch"

# --- R11: ReplicationInitiation's own catalog-M-aware trace-resolver      ---
# --- redirect, excluded from the shared, process-agnostic "helpers" hash ---
#
# 2026-09 integration review round 2: an independent review rejected a
# candidate that placed genuine 200-tick ReplicationInitiation data at the
# generic, hardcoded `_100ticks.mat` path (filename token is part of this
# project's trace-identity contract, never a non-authoritative legacy
# label). The corrected design extracts ReplicationInitiation's own
# catalog-M-aware (M_ticks=200) trace-path resolution and identity
# validation into its own sibling module, `_l2_2_repinit_runner_helpers.py`
# (mirroring R7's DNASupercoiling tick-runner extraction exactly), and adds
# a single `if process(_name) == "ReplicationInitiation": return
# <sibling-bound-name>(...)` redirect at the very top of BOTH
# `_v2_seed_mat_path()` and `load_karr_oracle()` -- the two, and only two,
# call sites that resolve a Design-A process's on-disk v2 trace path.
#
# Unlike R7's DNASupercoiling case (whose tick-runner function ALREADY
# existed, as a local `def`, inside the shared file -- migrating it to an
# import rebinding changes WHERE it lives but not whether ANY span exists
# there at all), this redirect is a genuinely NEW addition: neither
# `_v2_seed_mat_path` nor `load_karr_oracle` had any ReplicationInitiation-
# specific code before it. Redacting it to a placeholder (as R7 does for
# tick-dispatch bodies) would therefore NOT reproduce the pre-R11 hash --
# a placeholder line is still a line that did not exist before. Instead,
# `_r11_repinit_insertion_spans` identifies this EXACT, narrow shape (see
# `_match_repinit_redirect_guard`) and `runner_helpers_generic_hash` DELETES
# those lines outright (never a placeholder) when computing the hash, so a
# tree with the R11 redirect and a tree without it hash IDENTICALLY for
# every process other than ReplicationInitiation -- exactly the invariant
# `migrate_r11_repinit_provenance.py` needs to mechanically prove the
# migration of the other 19 already-accepted rows' recorded `"helpers"`
# hash is safe, without rerunning their sweeps. A tree where the guard is
# ABSENT (e.g. the pre-R11 `543c737` blob) simply yields no spans to
# delete, which is what makes this hash produce the SAME value whether
# evaluated against that blob or the post-R11 tree.
#
# ReplicationInitiation's own row is covered by a SEPARATE mechanism: the
# sibling module is registered whole-file under
# `PROCESS_DEPENDENCY_FILES["ReplicationInitiation"]["repinit_runner_helpers_module"]`
# (same pattern as DNAS's `dnas_runner_helpers_module`), so an edit to it
# still stales ReplicationInitiation's own row, just never any other one.
_REPINIT_SIBLING_MODULE_NAME = "_l2_2_repinit_runner_helpers"
_REPINIT_REDIRECT_GUARD_FUNCTIONS = ("_v2_seed_mat_path", "load_karr_oracle")
# The redirect's call TARGET is pinned per guard-function, not accepted as
# "any Call" -- otherwise a future edit that repointed the guard at some
# OTHER function (while keeping the same `if <x> == "ReplicationInitiation":
# return <call>()` shape) would still match, still get deleted, and still
# hash-equal, silently hiding a real behavioral change from every OTHER
# process's provenance. `test_shared_files_r11_delta_is_exactly_the_
# documented_redirect` (tests/vivarium/test_l2_2_repinit_trace_identity.py)
# is the compensating, independent control: it line-diffs the WHOLE file
# against published main and asserts the added lines are byte-exact matches
# of the four expected lines (including these exact call targets) -- so
# even if this dict's pin and that test's pin were both wrong in the SAME
# way, a manual review of either source diff would still catch it.
_REPINIT_REDIRECT_GUARD_EXPECTED_CALLEE = {
    "_v2_seed_mat_path": "_repinit_v2_seed_mat_path",
    "load_karr_oracle": "_load_replication_initiation_v2_ensemble",
}


def _match_repinit_redirect_guard(stmt: Any, *, expected_callee: str) -> bool:
    """True iff `stmt` is EXACTLY `if <name> == "ReplicationInitiation":
    return <expected_callee>(...)` -- a single `ast.If` whose test is a
    two-operand `==` comparison with one `ast.Name` operand and one
    `ast.Constant` operand equal to the literal string
    `"ReplicationInitiation"`, and whose entire body is one `ast.Return` of
    an `ast.Call` whose callee is a bare `ast.Name` equal to
    `expected_callee` (never "any Call" -- see the module-level comment on
    `_REPINIT_REDIRECT_GUARD_EXPECTED_CALLEE` for why the callee itself
    must be pinned). Deliberately narrow: returns False (never raises) on
    any other shape, which simply means "this tree has nothing here to
    delete" -- e.g. `543c737`, before R11, where `stmt` would be the
    seed-0/docstring-adjacent code these two functions always had, not
    this guard."""
    import ast

    if not isinstance(stmt, ast.If):
        return False
    test = stmt.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
        return False
    operands = (test.left, test.comparators[0])
    literal_hits = [o for o in operands if isinstance(o, ast.Constant) and o.value == "ReplicationInitiation"]
    name_hits = [o for o in operands if isinstance(o, ast.Name)]
    if len(literal_hits) != 1 or len(name_hits) != 1:
        return False
    if len(stmt.body) != 1 or not isinstance(stmt.body[0], ast.Return):
        return False
    call = stmt.body[0].value
    return isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == expected_callee


def _r11_repinit_insertion_spans(tree: Any) -> list[tuple[int, int]]:
    """Line spans (1-based, inclusive) of the R11 ReplicationInitiation
    redirect scaffolding: the sibling-module import statement (if present,
    matched by `node.module`, never by guessing at names), and the single
    redirect guard at the first non-docstring statement of
    `_v2_seed_mat_path`/`load_karr_oracle` (if present AND it matches
    `_match_repinit_redirect_guard` exactly, INCLUDING that function's
    pinned expected callee). A tree with none of these (e.g. `543c737`)
    yields an empty list."""
    import ast

    spans: list[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == _REPINIT_SIBLING_MODULE_NAME:
            spans.append((node.lineno, node.end_lineno))
        if isinstance(node, ast.FunctionDef) and node.name in _REPINIT_REDIRECT_GUARD_FUNCTIONS:
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                body = body[1:]  # skip the function's own docstring, if any
            expected_callee = _REPINIT_REDIRECT_GUARD_EXPECTED_CALLEE[node.name]
            if body and _match_repinit_redirect_guard(body[0], expected_callee=expected_callee):
                spans.append((body[0].lineno, body[0].end_lineno))
    return spans


class _RunnerDispatchAuditError(RuntimeError):
    """Raised when `_tick_dispatch()`'s source no longer has the single,
    simple `return {"Process": name, ...}` shape these helpers require to
    stay fail-closed. Never silently falls back to a partial/guessed map."""


def _parse_runner_helpers_ast(path: Path = RUNNER_HELPERS_MODULE, *, source: str | None = None) -> tuple[str, Any]:
    """Parse `_l2_2_design_a_runner_helpers.py`'s AST. `source`, when given,
    is used VERBATIM instead of reading `path` from disk -- this is what
    lets `migrate_helpers_provenance.py` evaluate a `--pre-ref` git blob's
    text (via `git show`) with the EXACT SAME static-analysis code path
    used against the current tree, without ever checking that ref out."""
    import ast

    text = source if source is not None else path.read_text(encoding="utf-8")
    return text, ast.parse(text, filename=str(path))


def _static_tick_dispatch_map(tree: Any) -> dict[str, str]:
    """Statically resolve `_tick_dispatch()`'s returned dict literal to a
    ``{"ProcessName": "<local-name-it-is-bound-to>"}`` mapping, without
    importing or executing the module. Fails closed (raises
    `_RunnerDispatchAuditError`) on any shape it does not recognize --
    multiple/no `return`, a non-dict return value, a non-string-constant
    key, or a value that is not a bare `Name` -- rather than silently
    returning an incomplete map."""
    import ast

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == _TICK_DISPATCH_FUNCTION_NAME:
            returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
            if len(returns) != 1 or not isinstance(returns[0].value, ast.Dict):
                raise _RunnerDispatchAuditError(
                    f"{_TICK_DISPATCH_FUNCTION_NAME}() must have exactly one "
                    "`return {...}` statement returning a dict literal."
                )
            dict_node = returns[0].value
            mapping: dict[str, str] = {}
            for key_node, value_node in zip(dict_node.keys, dict_node.values, strict=True):
                if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
                    raise _RunnerDispatchAuditError(
                        f"{_TICK_DISPATCH_FUNCTION_NAME}() dict key {ast.dump(key_node)} "
                        "is not a plain string constant."
                    )
                if not isinstance(value_node, ast.Name):
                    raise _RunnerDispatchAuditError(
                        f"{_TICK_DISPATCH_FUNCTION_NAME}()['{key_node.value}'] value "
                        f"{ast.dump(value_node)} is not a plain bare name."
                    )
                mapping[key_node.value] = value_node.id
            return mapping
    raise _RunnerDispatchAuditError(f"{_TICK_DISPATCH_FUNCTION_NAME}() not found in {RUNNER_HELPERS_MODULE}")


def _top_level_function_source(tree: Any, source: str, name: str) -> tuple[int, int, str] | None:
    import ast

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(source, node)
            if segment is None:
                return None
            return node.lineno, node.end_lineno, segment
    return None


def _resolve_bound_name_source(tree: Any, source: str, bound_name: str) -> str | None:
    """Source text of whatever `bound_name` refers to in
    `_l2_2_design_a_runner_helpers.py`: either a local top-level `def
    bound_name(...)`, or -- for a name introduced by a plain top-level
    `from <module> import <real_name> as bound_name` (or, with no alias,
    `from <module> import bound_name`) -- the top-level `def` of
    `<real_name>` inside `<module>`, resolved as a sibling `.py` file next
    to `_l2_2_design_a_runner_helpers.py` itself (every registered runner
    sibling module, e.g. `_l2_2_dnas_runner_helpers.py`, lives there).
    Returns None if neither resolves (fails closed by making the caller's
    hash come back `None`, which the staleness checker treats as a
    guaranteed mismatch, never a guaranteed match)."""
    import ast

    local = _top_level_function_source(tree, source, bound_name)
    if local is not None:
        return local[2]

    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        for alias in node.names:
            local_name = alias.asname or alias.name
            if local_name != bound_name:
                continue
            sibling_path = RUNNER_HELPERS_MODULE.parent / f"{node.module}.py"
            if not sibling_path.is_file():
                return None
            sibling_source = sibling_path.read_text(encoding="utf-8")
            sibling_tree = ast.parse(sibling_source, filename=str(sibling_path))
            found = _top_level_function_source(sibling_tree, sibling_source, alias.name)
            return found[2] if found is not None else None
    return None


def runner_helpers_generic_hash(*, source: str | None = None) -> str | None:
    """sha256 of `_l2_2_design_a_runner_helpers.py` with:
      1. every per-process tick-runner BINDING that `_tick_dispatch()` maps
         a process to -- a local top-level `def <name>(...)`, OR a
         top-level `from <module> import <real_name> as <name>` that
         rebinds it to an external sibling module (today: DNASupercoiling
         only) -- replaced by a FIXED one-line placeholder naming only the
         local name (R7); and
      2. the R11 ReplicationInitiation trace-resolver redirect scaffolding
         (see this section's module-level comment) DELETED outright, not
         placeholdered, if present.
    (1) keys its placeholder purely by name (never by construct kind),
    which is what makes this hash produce the IDENTICAL value whether a
    given process's tick-runner currently lives as a local `def` or as an
    imported rebinding: migrating one to the other changes ONLY that
    process's own `"tick_runner"` hash, never this one. (2) is a genuinely
    NEW addition with no previous span to swap places with, so it is
    deleted (never placeholdered) so that a tree with it and a tree
    without it hash IDENTICALLY -- see `_r11_repinit_insertion_spans`'s
    docstring for why. Returns None if the file is missing (never silently
    treated as "unchanged").

    `source`, when given, is evaluated VERBATIM instead of reading the file
    from disk -- `migrate_helpers_provenance.py`/`migrate_r11_repinit_
    provenance.py` pass a `--pre-ref` git blob's text through here so they
    can compare "what would this hash have been at pre-ref" against "what
    is it now" without ever checking that ref out onto disk."""
    import ast

    if source is None and not RUNNER_HELPERS_MODULE.is_file():
        return None
    text, tree = _parse_runner_helpers_ast(source=source)
    dispatch_fn_names = set(_static_tick_dispatch_map(tree).values())
    edits: list[tuple[int, int, str | None]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in dispatch_fn_names:
            edits.append((node.lineno, node.end_lineno, f"# <<REDACTED_TICK_RUNNER_BODY:{node.name}>>\n"))
            continue
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                local_name = alias.asname or alias.name
                if local_name in dispatch_fn_names:
                    edits.append((node.lineno, node.end_lineno, f"# <<REDACTED_TICK_RUNNER_BODY:{local_name}>>\n"))
                    break
    for start, end in _r11_repinit_insertion_spans(tree):
        edits.append((start, end, None))
    if not edits:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines = text.splitlines(keepends=True)
    for start, end, placeholder in sorted(edits, key=lambda item: item[0], reverse=True):
        if placeholder is None:
            del lines[start - 1 : end]
        else:
            lines[start - 1 : end] = [placeholder]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def tick_runner_entry_hash(process: str, *, source: str | None = None) -> str | None:
    """sha256 of the ACTUAL source of the function
    `_l2_2_design_a_runner_helpers._tick_dispatch()` maps `process` to,
    right now -- resolved statically (see `_resolve_bound_name_source`).
    Process-specific by construction: an edit confined to ONE process's own
    runner function/module changes only that process's `"tick_runner"`
    value. Returns None if `process` is not a `_tick_dispatch()` key, or if
    its bound name cannot be resolved to source (both treated as a
    guaranteed staleness mismatch by the checker, never a pass).

    `source`, when given, is evaluated VERBATIM instead of reading the file
    from disk (see `runner_helpers_generic_hash`'s matching parameter)."""
    if source is None and not RUNNER_HELPERS_MODULE.is_file():
        return None
    text, tree = _parse_runner_helpers_ast(source=source)
    dispatch_map = _static_tick_dispatch_map(tree)
    bound_name = dispatch_map.get(process)
    if bound_name is None:
        return None
    resolved = _resolve_bound_name_source(tree, text, bound_name)
    if resolved is None:
        return None
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()


# --- R6: per-process catalog/registry CONTRACT hashes (fail-closed,      ---
# --- replaces the old whole-file `"catalog"`/`"l2_event_registry"` keys) ---
#
# 2026-09-04: the accepted Cytokinesis-only `M_ticks: 4000 -> 5000` catalog
# edit staled all 19 unrelated in-scope processes' `sweep_provenance.json`
# at once, because `SWEEP_PROVENANCE_SOURCE_FILES`/`EVENT_CLASS_SOURCE_FILES`
# hashed the ENTIRE `PROCESS_CATALOG.yaml` (and, for event_class rows, the
# entire `event_registry.yaml`) as one process-agnostic blob. Both files
# are structurally a list of per-process rows (`processes: [...]`, keyed by
# `name`/`process`) -- exactly the same shape problem R2 already solved for
# `oc_module` (one file holding every process's own implementation): the
# fix here is the same in kind -- hash each process's OWN row, resolved
# against whatever bucket/universal default it falls back to, never the
# surrounding file's bytes.
#
# "Resolved" (not "raw row bytes") is deliberate: a process that omits
# `N_seeds` inherits `universals.N_seeds`, and a process that omits
# `harness_type` inherits `buckets.<bucket>.harness_type` -- an edit to
# either default changes that process's REAL effective behavior even
# though its own row's bytes never changed, and must still stale it (see
# `resolve_catalog_process_contract`). Canonical JSON (`sort_keys=True`,
# no whitespace) makes the hash stable across YAML mapping key-order and
# comment-only edits (`yaml.safe_load` already drops comments and does not
# preserve mapping insertion order as anything the hash can see once
# re-serialized with `sort_keys=True`) -- only the RESOLVED VALUES matter.
#
# Only fields actually read by `verdict.py`, `generator.py`,
# `event_bridge.py`, or the runner (`tests/vivarium/l2_2_design_a_runner.py`
# for the catalog; `scripts/l2_event/runner.py` for the registry -- both
# verified by direct inspection) are included. Free-text fields nothing
# ever reads (`notes`, `rationale_M`, `event_sweep_blocked_on`,
# `seed_window.rationale`, `karr_artifact`, `deferred_reason`) are
# deliberately EXCLUDED -- including them would make routine
# documentation/provenance updates to a process's own row stale its
# evidence for no scientific reason, which is not what "affects
# evidence/verdict/scope" means.
#
# CORRECTED 2026-09-05 (Opus re-review of this same R6 fix): the first
# cut of this function silently omitted three fields that ARE read by
# code, an omission that would have let a real, evidence-affecting edit
# to any of them pass through without staling the process's evidence:
#   - `primary_projection` (an ORDERED list of dotted chromosome-field
#     paths) -- read directly by `tests/vivarium/l2_2_design_a_runner.py`'s
#     `_process_primary_projection()` (`entry.get("primary_projection",
#     ())`), which sizes/orders the per-tick projection vector and
#     verifies every DNADamage mechanism-canary channel
#     (`tests/scripts/test_dna_damage_mechanism_canary.py`); order is real
#     content (which component occupies which vector slot), never
#     incidental, so it is preserved (never sorted) below.
#   - `joint_check` (bool) -- read directly by the SAME runner's
#     `_process_joint_check()` (`entry.get("joint_check", False)`), which
#     gates whether a non-gating cross-complex Spearman-correlation
#     diagnostic block is computed/emitted for MacromolecularComplexation.
#   - `seed_window.tick_range_from_division` (a `[lo, hi]` tick-offset
#     pair, present only on the two division-anchored EVENT_CLASS rows,
#     Cytokinesis/FtsZPolymerization) -- this is the catalog's own
#     machine-checkable mirror of
#     `docs/phase_f/l2_event/division_window_spec.json`
#     (`tests/scripts/test_extract_dual_division_window_static.py::
#     test_catalog_and_spec_agree_on_cytokinesis_m_ticks` asserts
#     byte-for-byte agreement) and the human-maintained
#     `TICK_RANGE_FROM_DIVISION` constant in
#     `scripts/l2_event/ftsz_pre_division_evidence.py` that gates which
#     event windows `validate_seed_window()` accepts -- a silent edit to
#     this pair (as actually happened: Cytokinesis's window was
#     reconciled from `[-3999, 0]` to `[-4999, 0]` in the same 2026-09-04
#     change series that first exposed this whole R6 defect) changes
#     which windows are valid without changing `M_ticks`, so it must
#     independently stale evidence. ONLY `tick_range_from_division` is
#     included -- `seed_window.rationale` is free text (excluded, same as
#     `notes`/`rationale_M`), and a row with no `seed_window` at all
#     (every non-division-anchored process) resolves to `None`, never a
#     guessed/fabricated window.
def _canonical_content_hash(payload: dict[str, Any]) -> str:
    """sha256 of `payload` serialized as canonical JSON (sorted keys, no
    whitespace) -- stable regardless of the dict's construction/insertion
    order. List-valued fields (`event_channels`/`output_channels`/
    `input_channels`) keep their own declared order: that is real content
    (which channel is listed, not incidental formatting), not something
    this canonicalization is meant to neutralize."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _single_named_row(rows: Any, key: str, process: str, *, source: str) -> dict[str, Any]:
    """Exactly one row in `rows` (a parsed YAML `processes:` list) whose
    `key` field equals `process`. Fails closed (raises `ValueError`, never
    returns a guessed/partial/first-match row) if there are zero or more
    than one such row -- an unknown, missing, or duplicated/renamed process
    must never silently resolve to *some* contract."""
    if not isinstance(rows, list):
        raise ValueError(f"{source}: expected a list of process rows, got {type(rows).__name__}")
    matches = [row for row in rows if isinstance(row, dict) and row.get(key) == process]
    if not matches:
        raise ValueError(f"{source}: process {process!r} not found (no row with {key}={process!r})")
    if len(matches) > 1:
        raise ValueError(f"{source}: process {process!r} has {len(matches)} duplicate rows (key={key!r})")
    return matches[0]


def resolve_catalog_process_contract(process: str, catalog: dict[str, Any]) -> dict[str, Any]:
    """The RESOLVED subset of one PROCESS_CATALOG.yaml process row that can
    affect its evidence/verdict/scope -- see this module's R6 section
    docstring above for the field-selection rationale. `catalog` is an
    ALREADY-PARSED mapping (never a path), so a migration/audit tool can
    resolve a HISTORICAL catalog's contract straight from `git show
    <ref>:...` text without ever writing it to disk. Raises `ValueError`
    (fail-closed) via `_single_named_row` if `process` has zero or more
    than one matching row."""
    universals = catalog.get("universals", {}) or {}
    default_n_seeds = int(universals.get("N_seeds", DEFAULT_N_SEEDS))
    buckets = catalog.get("buckets", {}) or {}
    raw = _single_named_row(catalog.get("processes", []), "name", process, source="PROCESS_CATALOG.yaml")
    bucket = raw.get("bucket")
    bucket_meta = buckets.get(bucket, {}) or {}
    harness_type = raw.get("harness_type") or bucket_meta.get("harness_type")
    oc_module = str(raw.get("oc_module")) if raw.get("oc_module") else None
    # `primary_projection` is ORDER-SENSITIVE (which dotted-path component
    # occupies which projection-vector slot) -- kept as a `list()` of the
    # raw sequence, never sorted/deduped. Default `()` mirrors the
    # runner's own `entry.get("primary_projection", ())` fallback exactly.
    primary_projection = [str(component) for component in (raw.get("primary_projection") or ())]
    # `seed_window.tick_range_from_division` is the only structured
    # (non-free-text) sub-field of `seed_window` -- see this module's R6
    # docstring above. A row with no `seed_window` (every process except
    # the two division-anchored EVENT_CLASS rows) resolves to `None`,
    # never a guessed/fabricated window; `rationale` is deliberately never
    # read here.
    raw_seed_window = raw.get("seed_window") or {}
    tick_range_from_division = raw_seed_window.get("tick_range_from_division")
    seed_window = (
        {"tick_range_from_division": list(tick_range_from_division)}
        if tick_range_from_division is not None
        else None
    )
    return {
        "process": process,
        "bucket": bucket,
        "harness_type": harness_type,
        "in_scope_L2_2": bool(raw.get("in_scope_L2_2", False)),
        "M_ticks": raw.get("M_ticks"),
        "N_seeds": int(raw.get("N_seeds", default_n_seeds)),
        "primary_channel": raw.get("primary_channel"),
        "closed_form_dominant": str(raw.get("closed_form_dominant", "false")),
        "primary_distance": str(raw.get("primary_distance", "per_tick_vector_w1_mean")),
        "primary_projection": primary_projection,
        "joint_check": bool(raw.get("joint_check", False)),
        "event_channels": list(raw.get("event_channels") or ()),
        "output_channels": list(raw.get("output_channels") or ()),
        "input_channels": list(raw.get("input_channels") or ()),
        "seed_window": seed_window,
        "oc_module": oc_module,
    }


def resolve_event_registry_process_contract(process: str, registry: dict[str, Any]) -> dict[str, Any]:
    """Analogous resolved-contract extraction for
    `docs/phase_f/l2_event/event_registry.yaml`. The identical whole-file
    cross-contamination defect existed here too (verified empirically: the
    same commit that changed Cytokinesis's catalog M_ticks also appended
    Cytokinesis-only notes to this file, whose whole-file hash staled
    DNADamage's and RibosomeAssembly's rows even though neither process's
    own registry row changed). `adapter_id`/`adapter_status`/
    `event_timing_model`/`magnitude_gateable`/`required_n_seeds`/
    `in_scope_v4` ARE read by `scripts/l2_event/runner.py`'s gating logic
    (verified by direct inspection); `deferred_reason`/`notes` are not and
    are excluded for the same reason `notes`/`rationale_M` are excluded
    from the catalog contract above. `registry` is an already-parsed
    mapping for the same historical-resolution-without-disk-writes reason
    as `resolve_catalog_process_contract`."""
    raw = _single_named_row(registry.get("processes", []), "process", process, source="event_registry.yaml")
    return {
        "process": process,
        "in_scope_v4": bool(raw.get("in_scope_v4", False)),
        "adapter_id": raw.get("adapter_id"),
        "adapter_status": str(raw.get("adapter_status", "not_implemented")),
        "event_timing_model": raw.get("event_timing_model"),
        "magnitude_gateable": bool(raw.get("magnitude_gateable", False)),
        "required_n_seeds": int(raw.get("required_n_seeds", 50)),
    }


def catalog_entry_hash(process: str, catalog_path: Path = CATALOG_PATH) -> str:
    """`_canonical_content_hash(resolve_catalog_process_contract(...))` for
    `process` as PROCESS_CATALOG.yaml exists at `catalog_path` RIGHT NOW.
    Raises `ValueError` (fail-closed) for an unknown/missing process --
    never silently omitted from `source_hashes`."""
    catalog = _ds.load_catalog(Path(catalog_path))
    return _canonical_content_hash(resolve_catalog_process_contract(process, catalog))


def event_registry_entry_hash(process: str, registry_path: Path = L2_EVENT_REGISTRY_PATH) -> str:
    """`_canonical_content_hash(resolve_event_registry_process_contract(...))`
    for `process` as `event_registry.yaml` exists at `registry_path` RIGHT
    NOW. Raises `ValueError` (fail-closed) for an unknown/missing process."""
    registry = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
    return _canonical_content_hash(resolve_event_registry_process_contract(process, registry))


def process_contract_hashes(
    process: str | None,
    harness_type: str | None,
    *,
    catalog_path: Path = CATALOG_PATH,
    registry_path: Path = L2_EVENT_REGISTRY_PATH,
) -> dict[str, str | None]:
    """The process-specific replacement for the old whole-file `"catalog"`
    (and, for `event_class`, `"l2_event_registry"`) shared source-hash
    keys. Both `sweep.current_source_hashes()` (writer, at generation time)
    and `generator._current_source_hashes()` (checker, at audit time) call
    this and merge its result into the SAME `source_hashes` dict `oc_module`
    already lives in -- no new gating code path is needed, since the
    existing R2 per-key staleness loop (in both `sweep.evidence_is_valid`
    and `generator._check_sweep_provenance_staleness`) already iterates
    `source_hashes.items()` generically and flags any named entry whose
    current hash no longer matches (including the F5 bidirectional check
    that flags a RECORDED key no longer in the current expected set -- this
    is what makes an un-migrated sentinel still carrying the old whole-file
    `"catalog"` key fail closed rather than being silently ignored). Returns
    `{}` for a falsy `process` (mirrors the `oc_module`/`harness_type`
    None-handling convention elsewhere in this module).

    `catalog_path`/`registry_path` default to the real tracked files but
    are overridable -- `scripts/l22_evidence/migrate_catalog_provenance.py`
    passes its own `--catalog`/`--registry` paths through here (and its
    tests point them at a synthetic, throwaway catalog/registry), so this
    function's notion of "current" always matches whatever catalog/registry
    the CALLER is actually operating against, never silently the default."""
    if not process:
        return {}
    hashes: dict[str, str | None] = {"catalog_entry": catalog_entry_hash(process, catalog_path)}
    if harness_type == "event_class":
        hashes["event_registry_entry"] = event_registry_entry_hash(process, registry_path)
    return hashes


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
    "resolve_catalog_process_contract",
    "resolve_event_registry_process_contract",
    "catalog_entry_hash",
    "event_registry_entry_hash",
    "process_contract_hashes",
]
