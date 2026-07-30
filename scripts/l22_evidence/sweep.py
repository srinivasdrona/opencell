"""Resumable, bounded-parallel sweep launcher for the L2.2 Design-A runner.

Drives the existing, UNMODIFIED ``tests/vivarium/l2_2_design_a_runner.py``
across the 18 ``design_a_per_tick`` in-scope processes at their real catalog
``N_seeds``/``M_ticks`` values, writing each process's runner-native
evidence to ``artifacts/l2_2_gates/<Process>/latest/`` -- the exact
directory the evidence generator (``scripts/l22_evidence/generator.py``)
already reads (see ``schema.py``). This module only decides *when* and
*with what arguments* to invoke the existing runner subprocess and records
what happened; it never touches biology, metrics, thresholds, catalog
values, or verdict evaluators, and it never overrides the runner's own
output.

Resume semantics: a job is considered "already satisfied" only if its
output directory contains the three mandatory authority files
(``result.json``, ``input_manifest.json``, ``provenance.json``) plus every
mandatory sidecar (``thresholds.json``, ``null_calibration.json``,
``SUMMARY.json``, ``analytical_check.json``) AND a valid, current, tracked
``sweep_provenance.json`` completion sentinel -- itself written by this
module, never the runner, since the runner's own ``provenance.json`` git
SHA is permanently ``"unknown"`` in this project's WSL/Windows-linked-
worktree environment. All of it must parse as valid JSON, match the
requested process/seed/tick counts, carry a real (non-"unknown") git SHA,
match the CURRENT sha256 of the runner/helpers/projections/catalog source
files AND the process's own ``oc_module`` implementation file, match the
CURRENT evaluator schema version, and match the sentinel's OWN recorded
sha256 of every fixed tracked authority/sidecar file sitting next to it
(``sidecar_hashes`` -- this is what makes a sentinel copied from a
DIFFERENT process's evidence directory fail even if its ``process``/
``n_seeds``/``m_ticks`` fields are hand-edited to match) -- any missing,
unknown, or mismatched field makes the evidence stale and eligible for
rerun, never ``DONE_VALID`` / skippable-as-valid. Never existence-only.
``--force`` overrides this and reruns unconditionally. This mirrors
``scripts/l22_extraction/launcher.py``'s "skip_valid / generate_missing /
regenerate_invalid" resume policy for the raw-oracle extraction sweep.

Every rerun (forced or not) writes to a fresh TEMP sibling output dir/log
and is only atomically swapped into the real ``<process>/latest/`` path
after its output passes validation -- a crashed or failed rerun always
leaves prior valid evidence completely untouched (see ``run_job``). A
per-process ``O_EXCL`` lock file prevents two concurrently-running
``sweep.py run`` invocations from relaunching the same process at once.

CLI:
    bin\\oc-py scripts/l22_evidence/sweep.py plan  [--processes P1,P2,...] [--out PATH]
    bin\\oc-py scripts/l22_evidence/sweep.py run   [--processes P1,P2,...] [--max-workers N]
                                                    [--force] [--report-out PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402
from scripts.l22_evidence.populate import _git_dirty, _git_sha  # noqa: E402

REPO_ROOT = cat.REPO_ROOT
RUNNER_SCRIPT = REPO_ROOT / "tests" / "vivarium" / "l2_2_design_a_runner.py"
DEFAULT_LOG_DIR = REPO_ROOT / "artifacts" / "l2_2_gates" / "_sweep_logs"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "sweep_report.json"
DEFAULT_STATUS_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "sweep_status.json"

# Status vocabulary for JobResult.status -- distinct from the evidence
# index's own mechanical_verdict vocabulary (schema.py), since this module
# reports *execution* outcome, not re-derived scientific verdict.
JOB_STATUS_SKIPPED_VALID = "SKIPPED_VALID"
JOB_STATUS_RAN_OK = "RAN_EXIT_0"
JOB_STATUS_RAN_FAIL = "RAN_NONZERO_EXIT"
JOB_STATUS_RAN_INVALID_EVIDENCE = "RAN_EXIT_0_INVALID_EVIDENCE"
JOB_STATUS_START_ERROR = "FAILED_TO_START"
# A second, concurrently-running `sweep.py run` invocation already holds the
# per-process O_EXCL lock for this exact process -- this run did not (and
# must not) relaunch it. Distinct from every other status: no attempt was
# made at all, existing evidence (valid or not) is untouched either way.
JOB_STATUS_LOCKED_SKIPPED = "LOCKED_SKIPPED_CONCURRENT"


@dataclass(frozen=True)
class SweepJob:
    process: str
    seeds: int  # count; runner resolves this to explicit seeds range(seeds)
    m_ticks: int
    output_dir: Path
    log_path: Path
    # Repo-relative path to this process's karr_*.py implementation (R2 SUT
    # hash), e.g. "opencell/vivarium/karr_dna_repair.py"; None if the
    # catalog declares no implementation for this process.
    oc_module: str | None = None
    # `plan_sweep` only ever builds jobs from `entry.harness_type ==
    # "design_a_per_tick"` catalog entries (see below) -- this field is
    # fixed at that value by construction, never inferred implicitly, so
    # `current_source_hashes(harness_type=job.harness_type)` binds the
    # F1 harness-scoped dependency (`l2_replay_common.py`) explicitly
    # rather than by relying on "this module happens to only ever be
    # called this way".
    harness_type: str = "design_a_per_tick"


@dataclass
class JobResult:
    process: str
    status: str
    exit_code: int | None
    started_at: str | None
    finished_at: str | None
    duration_s: float | None
    log_path: str
    output_dir: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "process": self.process,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "log_path": self.log_path,
            "output_dir": self.output_dir,
            "reason": self.reason,
        }


def plan_sweep(
    processes: list[str] | None = None,
    *,
    catalog_path: Path = schema.CATALOG_PATH,
    evidence_root: Path = schema.EVIDENCE_ROOT,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> list[SweepJob]:
    """Build the ordered job list: one job per requested (default: every
    in-scope) ``design_a_per_tick`` process, at its real catalog N_seeds/
    M_ticks. Never guesses M_ticks -- a design_a_per_tick process with no
    catalog M_ticks raises explicitly rather than silently defaulting."""
    entries = cat.in_scope_processes(catalog_path)
    design_a = {name: entry for name, entry in entries.items() if entry.harness_type == "design_a_per_tick"}

    if processes is None:
        wanted = sorted(design_a)
    else:
        unknown = [p for p in processes if p not in design_a]
        if unknown:
            raise ValueError(
                f"process(es) not in-scope design_a_per_tick: {unknown}; available: {sorted(design_a)}"
            )
        wanted = list(processes)

    jobs: list[SweepJob] = []
    for name in wanted:
        entry = design_a[name]
        if entry.m_ticks is None:
            raise ValueError(f"catalog process {name!r} has no M_ticks; refusing to guess a sweep tick count")
        jobs.append(
            SweepJob(
                process=name,
                seeds=int(entry.n_seeds),
                m_ticks=int(entry.m_ticks),
                output_dir=evidence_root / name / schema.DESIGN_A_SUBDIR,
                log_path=log_dir / f"{name}.log",
                oc_module=entry.oc_module,
                harness_type=entry.harness_type,
            )
        )
    return jobs


def _load_json_safe(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_source_hashes(
    oc_module: str | None = None, *, process: str | None = None, harness_type: str | None = None
) -> dict[str, str | None]:
    """sha256 of the runner/helpers/projections/catalog files as they exist
    RIGHT NOW -- both `build_sweep_provenance` (recording what evidence was
    generated against) and `evidence_is_valid` (checking whether that
    recording still matches the current tree) call this, so drift in any of
    these four sources after evidence was generated shows up as an
    individually-named stale entry rather than a generic mismatch.

    `oc_module`, when given (a repo-relative path string, e.g.
    "opencell/vivarium/karr_dna_repair.py" -- see `catalog.ProcessEntry.
    oc_module`), additionally hashes that ONE process's own implementation
    file under the `"oc_module"` key. This is process-specific by
    construction (unlike the four shared entries above), which is exactly
    what makes a code change to a single process's `karr_<process>.py`
    stale only THAT process's row (R2), never all 18.

    `process`, when given and present in `schema.PROCESS_DEPENDENCY_FILES`
    (F5: renamed from the narrower `METRIC_DEPENDENCY_FILES` -- see that
    registry's module docstring for why this is an explicit, hand-
    maintained dict rather than mechanically AST-derived), additionally
    hashes that process's registered runtime dependency modules (e.g.
    Metabolism's `fva.py`/`calc_flux_bounds.py`/`karr_metabolism.py`/
    `karr_metabolism_writeback.py`/`karr_protein_decay_light.py`,
    DNARepair's `chromosome_store.py`/`chromosome_views.py`) under their
    own named keys -- same stale-only-that-process property, for source
    files that are neither one of the four shared entries nor the
    process's `oc_module`.

    `harness_type`, when given and present in
    `schema.HARNESS_DEPENDENCY_FILES` (currently just
    `"design_a_per_tick"` -> `l2_replay_common.py`, F1), additionally
    hashes that harness's shared dependency modules -- scoped by harness,
    not by process name, since every `design_a_per_tick` process (never
    `event_class`) runs through the same `l2_replay_common.py` helpers."""
    hashes = {name: _sha256_file(path) for name, path in schema.SWEEP_PROVENANCE_SOURCE_FILES.items()}
    if oc_module:
        hashes["oc_module"] = _sha256_file(REPO_ROOT / oc_module)
    if process:
        for name, path in schema.PROCESS_DEPENDENCY_FILES.get(process, {}).items():
            hashes[name] = _sha256_file(path)
    if harness_type:
        hashes.update(schema.harness_dependency_hashes(harness_type))
    return hashes


def _recover_crashed_swap(output_dir: Path) -> None:
    """If a previous `run_job` crashed between its two `os.replace()` calls
    (moving the old `output_dir` aside to `<output_dir>.prev` and moving the
    validated replacement into `output_dir`'s place -- `os.replace` cannot
    atomically replace a non-empty directory in a single syscall, so a
    two-step rename is the smallest possible crash window), `output_dir`
    will be missing while `<output_dir>.prev` still holds the last-known-good
    evidence. Restore it before anything evaluates validity, so old evidence
    is never silently lost to a crash mid-swap."""
    backup_dir = output_dir.parent / f"{output_dir.name}.prev"
    if not output_dir.exists() and backup_dir.is_dir():
        os.replace(backup_dir, output_dir)


def _authority_and_sidecars_match(output_dir: Path, *, process: str, seeds: int, m_ticks: int) -> tuple[bool, str | None]:
    """Core request-matching check shared by `evidence_is_valid` (an
    existing, possibly-final `output_dir`) and `run_job` (a freshly-run TEMP
    output dir, before it is ever swapped into place): every
    REQUIRED_AUTHORITY_FILES + MANDATORY_SIDECAR_FILES entry must exist,
    parse as JSON, and match the requested process/seeds/ticks. Deliberately
    does NOT check `schema.SWEEP_PROVENANCE_FILE` -- callers that need that
    (only `evidence_is_valid`, since a fresh temp dir never has it yet) check
    it themselves."""
    missing = [f for f in schema.REQUIRED_AUTHORITY_FILES + schema.MANDATORY_SIDECAR_FILES if not (output_dir / f).is_file()]
    if missing:
        return False, f"missing required/mandatory file(s): {missing}"

    result = _load_json_safe(output_dir / "result.json")
    manifest = _load_json_safe(output_dir / "input_manifest.json")
    provenance = _load_json_safe(output_dir / "provenance.json")
    if result is None or manifest is None or provenance is None:
        return False, "one or more authority files failed to parse as JSON"
    for fname in schema.MANDATORY_SIDECAR_FILES:
        if _load_json_safe(output_dir / fname) is None:
            return False, f"{fname} failed to parse as JSON"

    expected_seeds = list(range(seeds))
    if result.get("process") != process:
        return False, f"result.json process={result.get('process')!r} != expected {process!r}"
    if sorted(result.get("seeds", [])) != expected_seeds:
        return False, f"result.json seeds do not match expected {seeds}-seed request"
    if int(result.get("ticks", -1)) != m_ticks:
        return False, f"result.json ticks={result.get('ticks')!r} != expected {m_ticks}"
    if sorted(manifest.get("resolved_seeds", [])) != expected_seeds:
        return False, "input_manifest.json resolved_seeds do not match expected seed request"
    if int(manifest.get("m_ticks", -1)) != m_ticks:
        return False, f"input_manifest.json m_ticks={manifest.get('m_ticks')!r} != expected {m_ticks}"

    return True, None


def evidence_is_valid(job: SweepJob) -> tuple[bool, str | None]:
    """True only if `job.output_dir` already holds complete, parseable,
    request-matching runner evidence AND a tracked, current
    `sweep_provenance.json` completion sentinel -- never existence-only, and
    never true for evidence that predates the provenance hardening (missing
    sweep_provenance.json) or was generated against a since-changed
    runner/helpers/projections/catalog source file OR a since-changed
    `schema.RESULT_SCHEMA_VERSION` raw-evidence field contract (an absent
    `result_schema_version` on the sentinel is treated as version 1, never
    as invalid). An unknown/missing git SHA does NOT alone invalidate
    evidence whose source hashes still match (see build_sweep_provenance
    below). Nor does a since-changed `evaluator_schema_version` alone
    invalidate otherwise-current evidence (as of v3): that field is still
    recorded on the sentinel purely informationally -- whether stored raw
    evidence needs a sweep RERUN is answered by content hashes
    (source/sidecar) and `result_schema_version` alone; whether it can be
    safely re-scored under newer mechanical-verdict logic is a separate,
    evaluator-side question answered by `verdict.py`'s own per-channel
    `required_fields` checks, never by this launcher-side rerun gate.
    Returns (False, <reason>) for every way it can be invalid, so
    `--force`-less reruns have an honest, inspectable reason for why a job
    was (not) skipped."""
    _recover_crashed_swap(job.output_dir)

    ok, reason = _authority_and_sidecars_match(job.output_dir, process=job.process, seeds=job.seeds, m_ticks=job.m_ticks)
    if not ok:
        return False, reason

    if not (job.output_dir / schema.SWEEP_PROVENANCE_FILE).is_file():
        return (
            False,
            f"missing completion sentinel {schema.SWEEP_PROVENANCE_FILE} "
            "(evidence predates provenance hardening, or the run never completed)",
        )
    sweep_prov = _load_json_safe(job.output_dir / schema.SWEEP_PROVENANCE_FILE)
    if sweep_prov is None:
        return False, f"{schema.SWEEP_PROVENANCE_FILE} failed to parse as JSON"
    if sweep_prov.get("process") != job.process:
        return False, f"{schema.SWEEP_PROVENANCE_FILE} process={sweep_prov.get('process')!r} != expected {job.process!r}"
    if int(sweep_prov.get("n_seeds", -1)) != job.seeds or int(sweep_prov.get("m_ticks", -1)) != job.m_ticks:
        return False, f"{schema.SWEEP_PROVENANCE_FILE} n_seeds/m_ticks do not match current catalog request"
    if sweep_prov.get("completion_status") != schema.COMPLETION_STATUS_COMPLETE:
        return (
            False,
            f"{schema.SWEEP_PROVENANCE_FILE} completion_status={sweep_prov.get('completion_status')!r} "
            f"!= {schema.COMPLETION_STATUS_COMPLETE!r}",
        )
    if sweep_prov.get("inputs_verified") is not True:
        return False, f"{schema.SWEEP_PROVENANCE_FILE} inputs_verified is not True"

    # R1 sentinel binding: the sentinel's OWN recorded hash of every fixed
    # tracked authority/sidecar file must match what is actually sitting
    # next to it right now -- catches a sentinel whose identifying fields
    # were hand-edited to match this process while its hashes still point
    # at a different process's (or stale) evidence bytes.
    recorded_sidecar_hashes = sweep_prov.get("sidecar_hashes") or {}
    for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES:
        current_sidecar = _sha256_file(job.output_dir / fname)
        if current_sidecar is None or recorded_sidecar_hashes.get(fname) != current_sidecar:
            return False, f"{schema.SWEEP_PROVENANCE_FILE} sidecar_hashes[{fname!r}] is stale/unknown vs current file"

    # git_sha/git_dirty are recorded informationally (see build_sweep_provenance)
    # but are NOT gating authority here: source content hashes below are what
    # actually prove the evidence matches the code now on disk, and Windows-
    # linked-worktree git plumbing is fragile enough that an unknown SHA alone
    # must not invalidate otherwise-matching, otherwise-current evidence.
    recorded_hashes = sweep_prov.get("source_hashes") or {}
    current_hashes = current_source_hashes(job.oc_module, process=job.process, harness_type=job.harness_type)
    for name, current in current_hashes.items():
        if current is None or recorded_hashes.get(name) != current:
            return False, f"{schema.SWEEP_PROVENANCE_FILE} source hash for {name!r} is stale/unknown vs current tree"
    # F5 bidirectional check: a key present in the RECORDED source_hashes
    # but absent from the CURRENT expected set (e.g. a since-shrunk/renamed
    # `schema.PROCESS_DEPENDENCY_FILES` entry, or a hand-tampered sentinel
    # that added a spurious key) must also invalidate the sentinel -- the
    # per-key loop above only ever checks "is every CURRENTLY-expected key
    # present and matching", never "does the recorded key SET exactly equal
    # the current expected key set", so an extra recorded key would
    # otherwise be silently ignored forever.
    extra_keys = sorted(set(recorded_hashes) - set(current_hashes))
    if extra_keys:
        return (
            False,
            f"{schema.SWEEP_PROVENANCE_FILE} source_hashes has extra/unexpected key(s) {extra_keys!r} "
            "not part of the current expected dependency set",
        )

    # NOTE (v3): `evaluator_schema_version` is intentionally NOT compared
    # against `vd.EVALUATOR_SCHEMA_VERSION` here -- see the function
    # docstring above for why gating a sweep RERUN on it would be
    # ceremonial (it would force every process to be re-run any time
    # `verdict.py`'s mechanical re-derivation logic is fixed, even though
    # no process/oracle/threshold changed and the stored raw evidence is
    # already sufficient to re-score). The value is still written into
    # every sentinel by `build_sweep_provenance` below, purely
    # informationally.

    # `result_schema_version` IS gating, unlike `evaluator_schema_version`
    # above: it means the STORED RAW result.json/sidecar BYTES were
    # produced under a different raw-evidence field contract than the one
    # this sweep launcher and the current evaluator both assume -- content
    # hashes alone cannot detect that (they only prove the bytes were
    # produced by the code currently on disk, not that their field SHAPE
    # matches). Absent (every sentinel written before this field existed)
    # is treated as version 1, never as missing/invalid -- see
    # `schema.RESULT_SCHEMA_VERSION`'s own docstring.
    recorded_result_schema_version = sweep_prov.get("result_schema_version", 1)
    if recorded_result_schema_version != schema.RESULT_SCHEMA_VERSION:
        return (
            False,
            f"{schema.SWEEP_PROVENANCE_FILE} result_schema_version={recorded_result_schema_version!r} "
            f"!= current schema.RESULT_SCHEMA_VERSION={schema.RESULT_SCHEMA_VERSION!r}",
        )

    return True, None


def build_sweep_provenance(
    job: SweepJob, *, output_dir: Path, repo_root: Path = REPO_ROOT, inputs_verified: bool
) -> dict[str, Any]:
    """The independent, sweep-launcher-written provenance record for a
    completed job's `output_dir` -- written ONLY after `run_job` confirms
    `_authority_and_sidecars_match` AND `_verify_input_manifest`, and
    written LAST (this file's mere presence is the completion sentinel
    `evidence_is_valid` requires).

    Records the REAL git SHA + dirty flag (reusing the already-accepted
    worktree-gitdir resolution in `populate.py`, since the runner's own
    `provenance.json["git_sha"]` is permanently "unknown" in this project's
    WSL/Windows-linked-worktree environment) purely informationally --
    gating authority is `source_hashes` + `sidecar_hashes` + (unlike
    `evaluator_schema_version`, which is recorded but no longer gating; see
    `evidence_is_valid`'s docstring) `result_schema_version` below, since
    content hashes are what actually prove the evidence was generated
    against the code now on disk, and `result_schema_version` is what
    proves the stored raw bytes' FIELD CONTRACT still matches what the
    current evaluator expects (see `evidence_is_valid`,
    `schema.RESULT_SCHEMA_VERSION`). Deliberately does NOT track
    `allocator_inputs.json`: it is large diagnostic bulk that no verdict
    calculation ever reads, so hashing it would be authority theater, not
    evidence (see `schema.INFORMATIONAL_ONLY_FILES`).

    `sidecar_hashes` (R1) binds this sentinel to the exact bytes of every
    fixed tracked authority/sidecar file in `output_dir` -- computed HERE,
    from `output_dir` itself (the about-to-be-final directory), so a
    sentinel copied into a different process's directory can never pass
    `evidence_is_valid`/the generator's staleness check even if its
    `process`/`n_seeds`/`m_ticks` fields are hand-edited to match.
    `source_hashes["oc_module"]` (R2) is this ONE process's own
    implementation file, so a code change to a single `karr_<process>.py`
    stales only that process's row. `source_hashes` additionally carries
    this process's registered runtime dependency modules, if any
    (`schema.PROCESS_DEPENDENCY_FILES` -- F5: a single explicit,
    hand-maintained registry, NEVER mechanically AST-derived at this
    hashing site -- e.g. Metabolism's `fva_module`/`calc_flux_bounds_module`/
    `m1_karr_metabolism_module`/`karr_metabolism_writeback_module`/
    `karr_protein_decay_light_module`, DNARepair's `chromosome_store_module`/
    `chromosome_views_module`), and this job's harness-scoped shared
    dependency modules, if any (`schema.HARNESS_DEPENDENCY_FILES`, e.g.
    every `design_a_per_tick` job's `l2_replay_common`) -- same
    stale-only-that-process(-or-harness) property. `inputs_verified` (R3)
    must be passed in True by the caller ONLY after `_verify_input_manifest`
    has actually rehashed every `input_manifest.json` input against the
    tree at generation time (guaranteed available then) -- never
    fabricated here."""
    sidecar_hashes = {
        fname: _sha256_file(output_dir / fname)
        for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES
        if (output_dir / fname).is_file()
    }
    return {
        "schema_version": schema.SWEEP_PROVENANCE_SCHEMA_VERSION,
        "process": job.process,
        "n_seeds": job.seeds,
        "m_ticks": job.m_ticks,
        "completion_status": schema.COMPLETION_STATUS_COMPLETE,
        "git_sha": _git_sha(repo_root),
        "git_dirty": _git_dirty(repo_root),
        "source_hashes": current_source_hashes(job.oc_module, process=job.process, harness_type=job.harness_type),
        "sidecar_hashes": sidecar_hashes,
        "inputs_verified": bool(inputs_verified),
        "evaluator_schema_version": vd.EVALUATOR_SCHEMA_VERSION,
        "result_schema_version": schema.RESULT_SCHEMA_VERSION,
        "written_at": datetime.now(UTC).isoformat(),
    }


def _verify_input_manifest(manifest: dict[str, Any] | None, *, repo_root: Path = REPO_ROOT) -> tuple[bool, str | None]:
    """R3: actually rehash every `input_manifest.json["inputs"]` entry
    against the CURRENT tree at generation time -- guaranteed available
    right now (the runner just read these exact files a moment ago) even
    though the raw oracle `.mat` file it points at is gitignored and will
    be intentionally absent in a fresh clone later. This one-time
    attestation is what `sweep_provenance.json["inputs_verified"]` records,
    so a later portable/fresh-clone audit can trust the recorded hash
    without needing the raw data re-mounted (see
    `generator._check_current_tree_staleness`'s `strict_input_files` for
    the opt-in rehash-when-mounted path instead). Also requires a
    non-empty `inputs` list -- an empty or missing list is never silently
    treated as "nothing to verify"."""
    if not manifest:
        return False, "input_manifest.json missing or unparseable"
    inputs = manifest.get("inputs")
    if not inputs:
        return False, "input_manifest.json has no non-empty 'inputs' list"
    for record in inputs:
        path_str = record.get("path")
        recorded_sha = record.get("sha256")
        if not path_str or not recorded_sha:
            return False, f"malformed input_manifest record {record!r}"
        path = Path(str(path_str))
        if not path.is_absolute():
            path = repo_root / path
        current = _sha256_file(path)
        if current is None:
            return False, f"input {path_str} does not exist right after the run completed"
        if current != recorded_sha:
            return (
                False,
                f"input {path_str} sha256 mismatch immediately after run "
                f"(recorded={recorded_sha[:12]}.., current={current[:12]}..)",
            )
    return True, None


def _normalize_input_manifest_file(tmp_output_dir: Path, *, repo_root: Path = REPO_ROOT) -> None:
    """Rewrite `input_manifest.json["inputs"][*]["path"]` in-place to
    repo-relative POSIX paths, run right after `_verify_input_manifest`
    confirms the recorded (runner-written, always-absolute) paths and
    hashes are correct.

    Without this, the LIVE tree's `input_manifest.json` keeps the runner's
    absolute worktree paths while `generator.bundle_process_evidence`
    separately normalizes a COPY when mirroring it into the tracked bundle
    (`generator._normalize_input_manifest_paths`) -- two different byte
    representations of the same logical evidence. R1's
    `sweep_provenance.json["sidecar_hashes"]["input_manifest.json"]` is
    computed from whichever bytes exist in `tmp_output_dir` at sentinel-
    write time, so without this normalization happening BEFORE that hash
    is taken, a bundle-sourced audit would always see a sidecar_hashes
    mismatch (the bundle's normalized bytes vs. the sentinel's hash of the
    live, absolute-path bytes) and incorrectly report every process as
    stale. Normalizing here, before the sentinel is written, makes the
    live tree and the (now merely byte-identical-copy) bundle agree from
    generation time onward, so `generator.bundle_process_evidence`'s own
    normalization pass becomes a no-op on already-normalized input.

    F2 (Opus5 final review): ALWAYS writes the canonical serialized form
    (`json.dumps(..., indent=2, sort_keys=True) + "\n"`, matching
    `generator.bundle_process_evidence`'s own serialization exactly) even
    when every path is already relative and no `path` value itself
    changes -- there used to be a `changed` guard that skipped the
    rewrite entirely in that case, which meant a manifest already holding
    repo-relative paths but written by the runner with different
    whitespace/key-ordering than the canonical form would silently keep
    those different bytes, breaking the live-tree/bundle byte-identity
    guarantee the docstring above depends on. Removed: this function must
    make the live tree's bytes match a fresh canonical write
    unconditionally, not just when there was a path to rewrite."""
    manifest_path = tmp_output_dir / "input_manifest.json"
    payload = _load_json_safe(manifest_path)
    if payload is None:
        return
    for record in payload.get("inputs", ()):
        path_str = record.get("path")
        if not path_str:
            continue
        path = Path(str(path_str))
        if not path.is_absolute():
            continue
        try:
            logical = path.resolve().relative_to(repo_root).as_posix()
        except ValueError:
            continue
        record["path"] = logical
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sanitize_dangling_temp_refs(tmp_output_dir: Path, *, final_output_dir: Path, repo_root: Path = REPO_ROOT) -> None:
    """Rewrite the handful of self-referential absolute paths the runner
    bakes into its own output (`result.json["allocator_inputs_ref"
    /"provenance_ref"]`, `provenance.json["oracle_path"]`) to a repo-
    relative LOGICAL path instead.

    `run_job` always runs the child in a TEMP rebuild directory first (see
    module docstring); the runner has no choice but to record paths rooted
    in THAT temp directory, which is renamed/removed the instant the atomic
    swap below completes -- left untouched, `allocator_inputs_ref`/
    `provenance_ref` would be permanently dangling absolute paths in every
    worktree, not just a portable/fresh-clone one. `provenance.json`'s
    `oracle_path` is not dangling (it points at the real, persistent oracle
    `.mat` file) but is still a worktree-specific absolute path with no
    place in a tracked, portable bundle -- normalized the same way as
    `input_manifest.json`'s own paths (see `generator._normalize_input_
    manifest_paths`). Only touches these three known bookkeeping fields --
    never anything `verdict.rederive_process` reads (channels/warnings/
    seeds/ticks/process/verdict are untouched) -- so this is metadata
    bookkeeping, not "overriding the runner's own output" in any biology/
    metrics/verdict sense."""
    result_path = tmp_output_dir / "result.json"
    result_payload = _load_json_safe(result_path)
    if result_payload is not None:
        changed = False
        for key in ("allocator_inputs_ref", "provenance_ref"):
            value = result_payload.get(key)
            if not value:
                continue
            fname = Path(str(value)).name
            try:
                logical = (final_output_dir / fname).resolve().relative_to(repo_root).as_posix()
            except ValueError:
                logical = str(value)
            if result_payload[key] != logical:
                result_payload[key] = logical
                changed = True
        if changed:
            result_path.write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    provenance_path = tmp_output_dir / "provenance.json"
    provenance_payload = _load_json_safe(provenance_path)
    if provenance_payload is not None:
        oracle_path = provenance_payload.get("oracle_path")
        if oracle_path:
            candidate = Path(str(oracle_path))
            if candidate.is_absolute():
                try:
                    logical = candidate.resolve().relative_to(repo_root).as_posix()
                except ValueError:
                    logical = str(oracle_path)
                if provenance_payload["oracle_path"] != logical:
                    provenance_payload["oracle_path"] = logical
                    provenance_path.write_text(
                        json.dumps(provenance_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )


def runner_command(job: SweepJob, *, python_exe: str | None = None) -> list[str]:
    """The exact, unmodified runner CLI invocation for `job`. Seeds are
    passed as a plain count ("50"), which the runner's own `_parse_seed_spec`
    resolves to the explicit `range(50)` -- i.e. seeds 0..49, the real
    Karr-oracle seed count already populated on disk."""
    return [
        python_exe or sys.executable,
        str(RUNNER_SCRIPT),
        "--process",
        job.process,
        "--seeds",
        str(job.seeds),
        "--ticks",
        str(job.m_ticks),
        "--output-dir",
        str(job.output_dir),
    ]


def _read_lock_pid(lock_path: Path) -> int | None:
    """Best-effort read of the PID a lock file's holder wrote into it (see
    `_acquire_lock`). Returns None for anything unreadable/non-numeric --
    treated as "cannot confirm liveness", handled conservatively by callers."""
    try:
        return int(lock_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_is_alive(pid: int) -> bool:
    """Pure liveness check via `os.kill(pid, 0)` -- sends no signal, never
    terminates or otherwise touches the target process. `PermissionError`
    means the PID exists but is owned by someone else: still alive, so
    treated as live rather than silently reaped."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_path_for(job: SweepJob) -> Path:
    """Per-process O_EXCL lock path -- disjoint per process by construction
    (parents differ 1:1 with `job.process`, exactly like `output_dir`/
    `log_path` themselves), so a second, independently-launched `sweep.py
    run` invocation cannot relaunch the SAME process concurrently while this
    one still holds it, without blocking unrelated processes from running in
    parallel within the SAME invocation (those never contend for this lock
    at all -- `run_sweep`'s ThreadPoolExecutor workers each call `run_job`
    for a distinct process)."""
    return job.output_dir.parent / f".{job.output_dir.name}.sweep.lock"


def _acquire_lock(lock_path: Path) -> int:
    """Atomically create-or-fail `lock_path` (`O_EXCL`); raises
    `FileExistsError` if another process ALIVE right now already holds it.
    This is the only mechanism that prevents two concurrent sweep
    invocations from double-launching the same process.

    A STALE lock (its recorded PID is no longer alive -- e.g. a prior sweep
    invocation crashed/was killed without reaching its `finally:
    _release_lock`) is silently reaped and retried exactly once here,
    rather than permanently blocking every future rerun of this process.
    This is intentionally the simplest possible reap policy (no lease
    timestamps, no lock versioning, no distributed-lock framework) -- a
    LIVE lock is never touched or signaled beyond the pure `os.kill(pid, 0)`
    liveness probe in `_pid_is_alive`."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        held_pid = _read_lock_pid(lock_path)
        if held_pid is not None and not _pid_is_alive(held_pid):
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        else:
            raise
    os.write(fd, str(os.getpid()).encode("utf-8"))
    return fd


def _release_lock(fd: int, lock_path: Path) -> None:
    try:
        os.close(fd)
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _atomic_replace_dir(tmp_dir: Path, final_dir: Path) -> None:
    """Replace `final_dir` with `tmp_dir`'s content, preserving the OLD
    `final_dir` at `<final_dir>.prev` across the (unavoidably two-step,
    since POSIX `rename()` cannot atomically replace a non-empty directory
    in a single syscall) swap, so a crash between the two renames still
    leaves the old evidence recoverable (see `_recover_crashed_swap`) rather
    than silently losing it."""
    backup_dir = final_dir.parent / f"{final_dir.name}.prev"
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    if final_dir.exists():
        os.replace(final_dir, backup_dir)
    os.replace(tmp_dir, final_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)


def run_job(
    job: SweepJob,
    *,
    force: bool = False,
    command_builder: Callable[[SweepJob], list[str]] = runner_command,
    cwd: Path = REPO_ROOT,
) -> JobResult:
    """Run a single job, honoring resume-by-validation unless `force`.
    Never overwrites already-valid evidence unless explicitly forced. The
    child's exact exit code is captured directly via `subprocess.run` (no
    shell wrapper involved), so wrapper exit-code-masking bugs elsewhere in
    this project's tooling cannot affect this launcher.

    Atomicity/locking: the child runner always writes to a freshly-created
    TEMP sibling directory/log (never `job.output_dir`/`job.log_path`
    directly). Only after the run exits 0 AND its output passes
    `_authority_and_sidecars_match` is `sweep_provenance.json` written into
    the temp dir (the completion sentinel, written last) and the temp
    dir/log atomically swapped into place. On any failure (nonzero exit,
    failed-to-start, or exit-0-but-invalid-evidence) `job.output_dir`/
    `job.log_path` are left completely untouched -- old valid evidence, if
    any, survives a crashed or failed rerun. A per-process O_EXCL lock
    (`_lock_path_for`) held for the duration of the attempt ensures a
    second, concurrently-running `sweep.py run` invocation cannot relaunch
    the SAME process at the same time; it returns JOB_STATUS_LOCKED_SKIPPED
    immediately instead of blocking or double-running -- `_acquire_lock`
    only raises for a LIVE holder (a STALE lock is reaped and this attempt
    proceeds normally instead), so JOB_STATUS_LOCKED_SKIPPED always means
    "another sweep invocation is genuinely running this process right now"
    and is treated as a hard failure by `_cmd_run` (nonzero exit), never a
    silent no-op."""
    _recover_crashed_swap(job.output_dir)

    if not force:
        valid, reason = evidence_is_valid(job)
        if valid:
            return JobResult(
                process=job.process,
                status=JOB_STATUS_SKIPPED_VALID,
                exit_code=None,
                started_at=None,
                finished_at=None,
                duration_s=None,
                log_path=cat.relative_to_repo(job.log_path),
                output_dir=cat.relative_to_repo(job.output_dir),
                reason="existing evidence already valid; use --force to rerun",
            )

    lock_path = _lock_path_for(job)
    try:
        lock_fd = _acquire_lock(lock_path)
    except FileExistsError:
        return JobResult(
            process=job.process,
            status=JOB_STATUS_LOCKED_SKIPPED,
            exit_code=None,
            started_at=None,
            finished_at=None,
            duration_s=None,
            log_path=cat.relative_to_repo(job.log_path),
            output_dir=cat.relative_to_repo(job.output_dir),
            reason=(
                f"another sweep invocation (live PID) holds {cat.relative_to_repo(lock_path)}; "
                f"not relaunching {job.process} concurrently -- in progress elsewhere, not a failure of THIS "
                "job, but sweep.py's own exit code is nonzero so this is never silently reported as success"
            ),
        )

    try:
        if not force:
            # Re-check now that the lock is held: a concurrent sweep may
            # have completed + released this exact job while this one
            # waited/lost the race to acquire the lock first.
            valid, reason = evidence_is_valid(job)
            if valid:
                return JobResult(
                    process=job.process,
                    status=JOB_STATUS_SKIPPED_VALID,
                    exit_code=None,
                    started_at=None,
                    finished_at=None,
                    duration_s=None,
                    log_path=cat.relative_to_repo(job.log_path),
                    output_dir=cat.relative_to_repo(job.output_dir),
                    reason="existing evidence already valid (confirmed after acquiring lock); use --force to rerun",
                )

        unique = f"{os.getpid()}-{time.time_ns()}"
        tmp_output_dir = job.output_dir.parent / f".{job.output_dir.name}.rebuild-{unique}"
        tmp_log_path = job.log_path.parent / f".{job.log_path.name}.rebuild-{unique}"
        tmp_output_dir.mkdir(parents=True, exist_ok=False)
        tmp_log_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_job = SweepJob(
            process=job.process,
            seeds=job.seeds,
            m_ticks=job.m_ticks,
            output_dir=tmp_output_dir,
            log_path=tmp_log_path,
            oc_module=job.oc_module,
        )
        command = command_builder(tmp_job)
        started_at = datetime.now(UTC).isoformat()
        start_perf = time.perf_counter()
        try:
            with tmp_log_path.open("w", encoding="utf-8") as log_handle:
                log_handle.write(f"# command: {command}\n# started_at: {started_at}\n")
                log_handle.flush()
                completed = subprocess.run(
                    command,
                    cwd=str(cwd),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            exit_code = completed.returncode
        except OSError as exc:
            finished_at = datetime.now(UTC).isoformat()
            try:
                os.replace(tmp_log_path, job.log_path)
            except OSError:
                pass
            shutil.rmtree(tmp_output_dir, ignore_errors=True)
            return JobResult(
                process=job.process,
                status=JOB_STATUS_START_ERROR,
                exit_code=None,
                started_at=started_at,
                finished_at=finished_at,
                duration_s=time.perf_counter() - start_perf,
                log_path=cat.relative_to_repo(job.log_path),
                output_dir=cat.relative_to_repo(job.output_dir),
                reason=f"failed to start subprocess: {exc}",
            )

        finished_at = datetime.now(UTC).isoformat()
        duration_s = time.perf_counter() - start_perf

        invalid_reason: str | None = None
        if exit_code == 0:
            fresh_valid, invalid_reason = _authority_and_sidecars_match(
                tmp_output_dir, process=job.process, seeds=job.seeds, m_ticks=job.m_ticks
            )
        else:
            fresh_valid = False

        inputs_verified = False
        if exit_code == 0 and fresh_valid:
            # R3: rehash input_manifest.json's own recorded inputs against
            # the tree RIGHT NOW, before anything is swapped into place --
            # the one moment the raw oracle .mat file is guaranteed present
            # regardless of environment (the runner just read it). Failure
            # here demotes this run to invalid evidence exactly like a
            # failed _authority_and_sidecars_match check, never silently
            # recorded as verified.
            manifest_payload = _load_json_safe(tmp_output_dir / "input_manifest.json")
            inputs_verified, inputs_reason = _verify_input_manifest(manifest_payload, repo_root=REPO_ROOT)
            if not inputs_verified:
                fresh_valid = False
                invalid_reason = f"input_manifest verification failed: {inputs_reason}"

        if exit_code == 0 and fresh_valid:
            _normalize_input_manifest_file(tmp_output_dir, repo_root=REPO_ROOT)
            _sanitize_dangling_temp_refs(tmp_output_dir, final_output_dir=job.output_dir, repo_root=REPO_ROOT)
            provenance_payload = build_sweep_provenance(
                job, output_dir=tmp_output_dir, repo_root=REPO_ROOT, inputs_verified=inputs_verified
            )
            (tmp_output_dir / schema.SWEEP_PROVENANCE_FILE).write_text(
                json.dumps(provenance_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            _atomic_replace_dir(tmp_output_dir, job.output_dir)
            os.replace(tmp_log_path, job.log_path)
            return JobResult(
                process=job.process,
                status=JOB_STATUS_RAN_OK,
                exit_code=exit_code,
                started_at=started_at,
                finished_at=finished_at,
                duration_s=duration_s,
                log_path=cat.relative_to_repo(job.log_path),
                output_dir=cat.relative_to_repo(job.output_dir),
                reason=None,
            )

        # Failure (nonzero exit, or exit 0 but invalid evidence): leave
        # job.output_dir/job.log_path completely untouched -- any previously
        # valid evidence survives. The failed attempt's raw output/log stay
        # at their temp paths for postmortem, referenced in `reason`.
        tail = _tail_lines(tmp_log_path, n=20)
        if exit_code != 0:
            status = JOB_STATUS_RAN_FAIL
            reason = f"nonzero exit {exit_code}; log tail: {tail}"
        else:
            status = JOB_STATUS_RAN_INVALID_EVIDENCE
            reason = f"exit 0 but produced evidence failed validation: {invalid_reason}; log tail: {tail}"
        reason += (
            f" (raw failed-attempt output preserved at {cat.relative_to_repo(tmp_output_dir)}, "
            f"log at {cat.relative_to_repo(tmp_log_path)})"
        )
        return JobResult(
            process=job.process,
            status=status,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=duration_s,
            log_path=cat.relative_to_repo(job.log_path),
            output_dir=cat.relative_to_repo(job.output_dir),
            reason=reason,
        )
    finally:
        _release_lock(lock_fd, lock_path)


def _tail_lines(path: Path, *, n: int = 20) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "<log unreadable>"
    return "\n".join(lines[-n:])


# Interim-status vocabulary -- distinct from JobResult.status. `run_sweep()`
# only returns (and `write_sweep_report()` only writes) once EVERY requested
# job has finished, which is unusable for honest progress reporting on a
# long sweep still partway through (e.g. while a multi-hour Metabolism job
# is still running). `status_snapshot()` is a read-only, non-invasive
# inspector: it never starts, stops, or waits on any process -- it only
# looks at what is already on disk right now -- so it is always safe to run
# concurrently with an in-flight `sweep.py run` invocation.
STATUS_DONE_VALID = "DONE_VALID_EVIDENCE"
STATUS_DONE_INVALID_OR_FAILED = "DONE_NO_VALID_EVIDENCE"
STATUS_IN_PROGRESS = "IN_PROGRESS_OR_UNKNOWN"
STATUS_NOT_STARTED = "NOT_STARTED"


def status_snapshot(jobs: list[SweepJob]) -> list[dict[str, Any]]:
    """Read-only interim status for `jobs`, safe to call while a real sweep
    `run` is still executing elsewhere. Never inspects process state (no PID
    lookups) -- only what is already durably on disk: whether valid evidence
    exists, whether a log file exists (implying a run was at least attempted
    and may still be in progress), and the stored (non-authoritative) runner
    verdict/warnings for human-readable context."""
    rows: list[dict[str, Any]] = []
    for job in jobs:
        valid, reason = evidence_is_valid(job)
        log_exists = job.log_path.is_file()
        row: dict[str, Any] = {
            "process": job.process,
            "seeds": job.seeds,
            "m_ticks": job.m_ticks,
            "output_dir": cat.relative_to_repo(job.output_dir),
            "log_path": cat.relative_to_repo(job.log_path) if log_exists else None,
        }
        if valid:
            row["status"] = STATUS_DONE_VALID
            row["reason"] = None
            result = _load_json_safe(job.output_dir / "result.json")
            if result is not None:
                row["stored_verdict"] = result.get("verdict")
                row["stored_bucket"] = result.get("bucket")
                row["stored_warnings"] = result.get("warnings", [])
        elif log_exists:
            log_text = job.log_path.read_text(encoding="utf-8", errors="replace")
            log_looks_finished = any(
                marker in log_text for marker in ("Traceback", "Error", "error", "ticks, but oracle only provides")
            )
            row["status"] = STATUS_DONE_INVALID_OR_FAILED if log_looks_finished else STATUS_IN_PROGRESS
            row["reason"] = reason
            row["log_tail"] = _tail_lines(job.log_path, n=5)
        else:
            row["status"] = STATUS_NOT_STARTED
            row["reason"] = reason
        rows.append(row)
    return rows


def write_status_snapshot(rows: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    """Compact tracked JSON: one interim status row per job, plus a tally.
    Excludes raw per-tick arrays/channel numbers -- same compactness
    discipline as `write_sweep_report()`."""
    tally: dict[str, int] = {}
    for r in rows:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_jobs": len(rows),
        "tally": tally,
        "jobs": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def run_sweep(
    jobs: list[SweepJob],
    *,
    max_workers: int = 2,
    force: bool = False,
    command_builder: Callable[[SweepJob], list[str]] = runner_command,
    cwd: Path = REPO_ROOT,
) -> list[JobResult]:
    """Bounded-parallel execution of `jobs`. Every job's output_dir/log_path
    is disjoint by construction (`plan_sweep` derives them 1:1 from process
    name), so no two concurrent workers ever write the same file. Returns
    results in the SAME order as `jobs` (not completion order), so a
    resumed/partial sweep's report is stable regardless of scheduling."""
    if max_workers < 1:
        raise ValueError(f"max_workers must be >= 1, got {max_workers}")

    results: list[JobResult | None] = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_index = {
            pool.submit(run_job, job, force=force, command_builder=command_builder, cwd=cwd): i
            for i, job in enumerate(jobs)
        }
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            results[i] = future.result()
    return [r for r in results if r is not None]


def write_sweep_report(results: list[JobResult], path: Path = DEFAULT_REPORT_PATH) -> dict[str, Any]:
    """Compact, tracked JSON summary of one sweep invocation: process,
    execution status, exit code, timing, disjoint output/log paths, and a
    failure reason where relevant. Deliberately excludes raw per-tick
    arrays or channel numbers -- that detail lives in the runner's own
    result.json (evidence_root), which this report only points at."""
    tally: dict[str, int] = {}
    for r in results:
        tally[r.status] = tally.get(r.status, 0) + 1
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_jobs": len(results),
        "tally": tally,
        "jobs": [r.to_dict() for r in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _parse_processes_arg(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def _cmd_plan(args: argparse.Namespace) -> int:
    jobs = plan_sweep(
        _parse_processes_arg(args.processes),
        evidence_root=Path(args.evidence_root),
        log_dir=Path(args.log_dir),
    )
    for job in jobs:
        valid, reason = evidence_is_valid(job)
        status = "SKIP(valid)" if valid else f"WOULD-RUN({reason})"
        print(f"{job.process:28s} seeds={job.seeds:<3d} ticks={job.m_ticks:<4d} {status}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    jobs = plan_sweep(
        _parse_processes_arg(args.processes),
        evidence_root=Path(args.evidence_root),
        log_dir=Path(args.log_dir),
    )
    rows = status_snapshot(jobs)
    report = write_status_snapshot(rows, Path(args.status_out))
    print(f"wrote {args.status_out} ({report['n_jobs']} jobs)")
    for status, count in sorted(report["tally"].items()):
        print(f"  {status}: {count}")
    for row in rows:
        extra = f" verdict={row.get('stored_verdict')}" if row["status"] == STATUS_DONE_VALID else ""
        print(f"    {row['process']:28s} {row['status']}{extra}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    jobs = plan_sweep(
        _parse_processes_arg(args.processes),
        evidence_root=Path(args.evidence_root),
        log_dir=Path(args.log_dir),
    )
    results = run_sweep(jobs, max_workers=args.max_workers, force=args.force)
    report = write_sweep_report(results, Path(args.report_out))
    print(f"wrote {args.report_out} ({report['n_jobs']} jobs)")
    for status, count in sorted(report["tally"].items()):
        print(f"  {status}: {count}")
    # A child that ran and exited nonzero, ran but produced no valid
    # evidence, never started at all, or was LOCKED_SKIPPED by a live
    # concurrent sweep invocation are all HARD failures from THIS
    # invocation's point of view -- nonzero exit regardless of which one
    # occurred. Only JOB_STATUS_SKIPPED_VALID (evidence already valid,
    # genuinely nothing to do) never causes a nonzero exit.
    # JOB_STATUS_LOCKED_SKIPPED specifically means "another invocation is
    # live and actually working on this process right now": that is neither
    # a silent success (this invocation did not produce/confirm evidence
    # for it) nor a hard error in the crashed/broken sense, so it is
    # reported explicitly here rather than folded into a generic "FAILED"
    # count -- but it still makes `_cmd_run`'s own exit nonzero, since a
    # caller that only checks the exit code must never see 0 while some
    # requested process was not actually handled by this invocation.
    hard_failure_statuses = (JOB_STATUS_START_ERROR, JOB_STATUS_RAN_FAIL, JOB_STATUS_RAN_INVALID_EVIDENCE)
    locked_live = [r for r in results if r.status == JOB_STATUS_LOCKED_SKIPPED]
    for r in locked_live:
        print(f"  IN-PROGRESS elsewhere (live lock): {r.process} -- {r.reason}")
    any_hard_failure = any(r.status in hard_failure_statuses for r in results) or bool(locked_live)
    return 1 if any_hard_failure else 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Print the resume-aware plan without running anything.")
    plan.add_argument("--processes", help="Comma-separated subset; default is all 18 design_a_per_tick.")
    plan.add_argument("--evidence-root", default=str(schema.EVIDENCE_ROOT))
    plan.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    plan.set_defaults(func=_cmd_plan)

    run = sub.add_parser("run", help="Run the sweep (bounded-parallel, resumable).")
    run.add_argument("--processes", help="Comma-separated subset; default is all 18 design_a_per_tick.")
    run.add_argument("--max-workers", type=int, default=2)
    run.add_argument("--force", action="store_true", help="Rerun even if existing evidence is already valid.")
    run.add_argument("--evidence-root", default=str(schema.EVIDENCE_ROOT))
    run.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    run.add_argument("--report-out", default=str(DEFAULT_REPORT_PATH))
    run.set_defaults(func=_cmd_run)

    status = sub.add_parser(
        "status",
        help="Read-only interim progress snapshot; safe to run while `run` is executing elsewhere.",
    )
    status.add_argument("--processes", help="Comma-separated subset; default is all 18 design_a_per_tick.")
    status.add_argument("--evidence-root", default=str(schema.EVIDENCE_ROOT))
    status.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    status.add_argument("--status-out", default=str(DEFAULT_STATUS_PATH))
    status.set_defaults(func=_cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
