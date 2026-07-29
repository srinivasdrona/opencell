"""L2.2 evidence-index generator (generator-only; never hand-edit the output).

Reads ``docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`` for scope and, for
every ``in_scope_L2_2`` process, looks for machine-produced runner evidence
under ``<evidence_root>/<Process>/{latest,latest_event}/`` -- by default the
live, gitignored sweep-output tree (``artifacts/l2_2_gates``) if present
locally, otherwise the tracked, portable evidence bundle
(``docs/phase_f/l2_2_design_a/evidence_bundle``); see
``schema.default_evidence_root()``. Emits one row per process (never zero,
never duplicated, never extra), mechanically re-deriving the process
verdict from raw channel numbers via ``scripts.l22_evidence.verdict`` -- the
stored ``result.json["verdict"]`` string is never trusted as authority.

CLI:
    bin\\oc-py scripts/l22_evidence/generator.py bundle [--source-root PATH] [--bundle-root PATH]
    bin\\oc-py scripts/l22_evidence/generator.py generate [--out PATH] [--evidence-root PATH] [--verify-input-files]
    bin\\oc-py scripts/l22_evidence/generator.py audit [--index PATH] [--evidence-root PATH] [--require-all-pass] [--verify-input-files]

See ``docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md`` for the full
contract, including why ``audit`` works by regenerating the index from
scratch and diffing against the tracked file rather than trusting anything
already written to disk, and why ``bundle`` exists (portable evidence: the
authority files must not live *only* under gitignored ``artifacts/``).
"""


from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"unreadable: {exc}"


def _evidence_dir_for(entry: cat.ProcessEntry, evidence_root: Path) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    return evidence_root / entry.name / subdir


def _resolve_input_path(path_str: str) -> Path:
    """Resolve one `input_manifest.json["inputs"][*]["path"]` against the
    CURRENT tree.

    The runner (`tests/vivarium/l2_2_design_a_runner.py`, off-limits to
    modify per this project's evidence-gate contract) always records
    *absolute* paths rooted in whatever worktree it happened to execute in.
    A relative path is resolved against the current `cat.REPO_ROOT` as
    before. An absolute path is tried as-is first (the common case: same
    worktree the evidence was generated in, unmoved) -- if that exists we
    use it directly so genuine content drift is still caught exactly as
    before. Only if that fails do we fall back to matching the longest path
    suffix that resolves to a real file under the CURRENT `cat.REPO_ROOT`;
    this is what lets staleness checking work when the evidence bundle is
    read from a *different* worktree/clone root than the one that generated
    it (e.g. a fresh clone, or another worktree of the same repo) without
    ever touching the runner's own path-recording behavior.
    """
    path = Path(str(path_str))
    if not path.is_absolute():
        return cat.REPO_ROOT / path
    if path.is_file():
        return path
    parts = path.parts
    for i in range(1, len(parts)):
        candidate = cat.REPO_ROOT / Path(*parts[i:])
        if candidate.is_file():
            return candidate
    return path  # give up; caller reports "no longer exists"


def _check_current_tree_staleness(
    input_manifest: dict[str, Any],
    *,
    entry: cat.ProcessEntry | None = None,
    strict_input_files: bool = False,
) -> list[str]:
    """Recompute sha256 of every path input_manifest.json declares it consumed,
    as those files exist *right now* in the working tree, and flag any drift.

    This is what catches a committed evidence directory going stale after the
    catalog, the runner source, or an oracle .mat file changes underneath it.

    R3: `inputs` must be non-empty (an empty/missing list is never silently
    treated as "nothing to check") and every entry needs a `path` + `sha256`.
    Entries classified as raw Karr-oracle data (`_classify_input_kind` ==
    "oracle_data") are gitignored and intentionally absent in a portable/
    fresh-clone evidence-bundle-only checkout -- by default (`strict_input_
    files=False`) a missing oracle-data file is NOT flagged stale here (the
    sweep launcher's own `inputs_verified` attestation in
    `sweep_provenance.json`, checked by `_check_sweep_provenance_staleness`,
    is the authority for "this hash was confirmed correct once, when the
    data WAS mounted"); pass `strict_input_files=True` (the CLI's
    `--verify-input-files`) to instead require the oracle data be mounted
    and rehash it for real. Every "code" input (runner/helpers/projections,
    always tracked in git) is unconditionally rehashed in both modes. Also
    checks `resolved_seeds` covers exactly `range(entry.n_seeds)` -- this is
    the "seed coverage sufficient to identify all 50" requirement: the
    single hashed oracle-data file legitimately contains every seed's data
    internally, so seed coverage is established via this field rather than
    one hash entry per seed.
    """
    reasons: list[str] = []
    inputs = input_manifest.get("inputs") or []
    if not inputs:
        reasons.append(f"{schema.STATUS_EMPTY_INPUT_MANIFEST}: input_manifest.json has no non-empty 'inputs' list")
    for record in inputs:
        path_str = record.get("path")
        recorded_sha = record.get("sha256")
        if not path_str or not recorded_sha:
            reasons.append(f"{schema.STATUS_STALE_VS_TREE}: malformed input_manifest record {record!r}")
            continue
        kind = _classify_input_kind(path_str)
        if kind == "oracle_data" and not strict_input_files:
            # Portable/fresh-clone default: trust the sweep-time
            # inputs_verified attestation instead of requiring the raw,
            # gitignored oracle .mat file to be physically present (or, if it
            # happens to be mounted anyway, re-hashed) here. Re-verification
            # of mounted oracle data is opt-in via strict_input_files.
            continue
        path = _resolve_input_path(str(path_str))
        current_sha = _sha256_file(path)
        if current_sha is None:
            suffix = (
                " (--verify-input-files requested but the raw oracle data is not mounted at this path -- "
                "expected in a fresh clone/bundle-only checkout; omit --verify-input-files for the portable audit)"
                if kind == "oracle_data"
                else ""
            )
            reasons.append(f"{schema.STATUS_STALE_VS_TREE}: input {path_str} no longer exists on disk{suffix}")
        elif current_sha != recorded_sha:
            reasons.append(
                f"{schema.STATUS_STALE_VS_TREE}: input {path_str} sha256 changed since evidence was generated "
                f"(recorded={recorded_sha[:12]}.., current={current_sha[:12]}..)"
            )

    if entry is not None and entry.n_seeds is not None:
        expected_seeds = list(range(entry.n_seeds))
        resolved_seeds = input_manifest.get("resolved_seeds")
        actual_seeds = sorted(resolved_seeds) if isinstance(resolved_seeds, list) else None
        if actual_seeds != expected_seeds:
            reasons.append(
                f"{schema.STATUS_NM_MISMATCH}: input_manifest.json resolved_seeds={actual_seeds!r} "
                f"do not cover expected {entry.n_seeds} seeds (0..{entry.n_seeds - 1})"
            )
    return reasons


def _current_source_hashes(entry: cat.ProcessEntry | None = None) -> dict[str, str | None]:
    """sha256 of the runner/helpers/projections/catalog files as they exist
    RIGHT NOW. Mirrors `sweep.current_source_hashes()` exactly (both read
    the same `schema.SWEEP_PROVENANCE_SOURCE_FILES` dict) -- duplicated here
    rather than importing `sweep` so this read-only audit/generator module
    never depends on the execution-launcher module.

    `entry`, when given, additionally hashes THAT process's own
    `oc_module` implementation file under the `"oc_module"` key (R2) -- the
    same process-specific SUT hash `sweep.current_source_hashes(oc_module=...)`
    computes at generation time, so a code change to a single
    `karr_<process>.py` stales only that process's row here too. It also
    hashes `entry.name`'s registered runtime dependency modules, if any
    (`schema.PROCESS_DEPENDENCY_FILES` -- F5: a single explicit,
    hand-maintained registry, NEVER mechanically AST-derived here -- e.g.
    Metabolism's `fva_module`/`calc_flux_bounds_module`/
    `m1_karr_metabolism_module`/`karr_metabolism_writeback_module`/
    `karr_protein_decay_light_module`, DNARepair's `chromosome_store_module`/
    `chromosome_views_module`), same stale-only-that-process property, and
    `entry.harness_type`'s shared harness-scoped dependency modules, if any
    (`schema.HARNESS_DEPENDENCY_FILES`, e.g. every `design_a_per_tick`
    process's `l2_replay_common` -- never for `event_class`), mirroring
    `sweep.current_source_hashes(process=..., harness_type=...)`."""
    hashes = {name: _sha256_file(path) for name, path in schema.SWEEP_PROVENANCE_SOURCE_FILES.items()}
    if entry is not None and entry.oc_module:
        hashes["oc_module"] = _sha256_file(cat.REPO_ROOT / entry.oc_module)
    if entry is not None:
        for name, path in schema.PROCESS_DEPENDENCY_FILES.get(entry.name, {}).items():
            hashes[name] = _sha256_file(path)
        hashes.update(schema.harness_dependency_hashes(entry.harness_type))
    return hashes


def _classify_input_kind(path_str: str) -> str:
    """"oracle_data" for a raw Karr-oracle `.mat` input (gitignored, never
    tracked -- see `schema.ORACLE_DATA_PATH_PREFIX`), "code" for anything
    else (the runner/helpers/projections source files, always tracked in
    git and therefore present in any clone). Resolves via
    `_resolve_input_path` first so this classification works whether the
    manifest's own path is absolute (live tree) or already repo-relative
    (bundle)."""
    resolved = _resolve_input_path(str(path_str))
    try:
        rel = resolved.relative_to(cat.REPO_ROOT).as_posix()
    except ValueError:
        rel = str(path_str).replace("\\", "/")
    return "oracle_data" if rel.startswith(schema.ORACLE_DATA_PATH_PREFIX) else "code"


def _check_sweep_provenance_staleness(
    payload: dict[str, Any], entry: cat.ProcessEntry, evidence_dir: Path
) -> list[str]:
    """Reasons a `sweep_provenance.json` payload makes a row stale:

    R1 sentinel binding -- the sentinel must actually BELONG to this
    process/N/M and its completion_status must say the run finished, and
    its OWN recorded sha256 of every fixed tracked authority/sidecar file
    (`sidecar_hashes`) must match the bytes actually sitting in
    `evidence_dir` right now. A `sweep_provenance.json` copied wholesale
    from a DIFFERENT process's evidence directory fails the process check
    immediately; one hand-edited to merely rename its `process` field still
    fails the sidecar-hash check, since those hashes were computed from the
    other process's (differently-sized/differently-timestamped) files.

    R2 SUT hash -- a source-file (runner/helpers/projections/catalog/
    oc_module/metric-dependency-module) hash that no longer matches the
    CURRENT tree.

    R3 input attestation -- `inputs_verified` must be exactly True (the
    sweep launcher only ever sets this after actually rehashing
    `input_manifest.json`'s inputs at generation time; see
    `sweep._verify_input_manifest`).

    An unknown/missing real git SHA is recorded on the row informationally
    (see `row["sweep_provenance"]["git_sha"]` in `build_process_row`) but
    does NOT by itself add a reason here: content hashes are the gating
    authority, since they directly prove the evidence matches the code now
    on disk, whereas git plumbing for a Windows-linked worktree is
    inherently more fragile. Distinct from `_check_current_tree_staleness`
    (which checks `input_manifest.json`'s OWN recorded inputs, e.g. the
    oracle .mat file) -- this checks the sweep-launcher's independent
    provenance record instead, since the runner's
    `provenance.json["git_sha"]` can never itself be trusted (see
    schema.py's SWEEP_PROVENANCE_FILE docstring)."""
    reasons: list[str] = []

    if payload.get("process") != entry.name:
        reasons.append(
            f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json process={payload.get('process')!r} "
            f"!= expected {entry.name!r} (sentinel copied from a different process?)"
        )
    if entry.n_seeds is not None and payload.get("n_seeds") != entry.n_seeds:
        reasons.append(
            f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json n_seeds={payload.get('n_seeds')!r} "
            f"!= catalog N_seeds={entry.n_seeds!r}"
        )
    if entry.m_ticks is not None and payload.get("m_ticks") != entry.m_ticks:
        reasons.append(
            f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json m_ticks={payload.get('m_ticks')!r} "
            f"!= catalog M_ticks={entry.m_ticks!r}"
        )
    if payload.get("completion_status") != schema.COMPLETION_STATUS_COMPLETE:
        reasons.append(
            f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json completion_status="
            f"{payload.get('completion_status')!r} != {schema.COMPLETION_STATUS_COMPLETE!r}"
        )
    if payload.get("inputs_verified") is not True:
        reasons.append(
            f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json inputs_verified is not True "
            "(input_manifest.json inputs were never mechanically re-hashed at generation time)"
        )

    recorded_sidecar_hashes = payload.get("sidecar_hashes") or {}
    for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES:
        current_sidecar = _sha256_file(evidence_dir / fname)
        recorded_sidecar = recorded_sidecar_hashes.get(fname)
        if current_sidecar is None:
            reasons.append(f"{schema.STATUS_STALE_PROVENANCE}: {fname} no longer exists on disk for sentinel binding")
        elif recorded_sidecar is None:
            reasons.append(f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json missing sidecar_hashes[{fname!r}]")
        elif recorded_sidecar != current_sidecar:
            reasons.append(
                f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json sidecar_hashes[{fname!r}] "
                "does not match current file bytes (sentinel does not belong to this evidence)"
            )

    recorded_hashes = payload.get("source_hashes") or {}
    current_hashes = _current_source_hashes(entry)
    for name, current in current_hashes.items():
        recorded = recorded_hashes.get(name)
        if current is None:
            reasons.append(f"{schema.STATUS_STALE_PROVENANCE}: current source file for {name!r} no longer exists on disk")
        elif recorded is None:
            reasons.append(f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json missing source hash for {name!r}")
        elif recorded != current:
            reasons.append(
                f"{schema.STATUS_STALE_PROVENANCE}: {name} source changed since evidence was generated "
                f"(recorded={recorded[:12]}.., current={current[:12]}..)"
            )
    # F5 bidirectional check: a key present in the RECORDED source_hashes
    # but absent from the CURRENT expected set (e.g. a since-shrunk/renamed
    # `schema.PROCESS_DEPENDENCY_FILES` entry, or a hand-tampered sentinel
    # that added a spurious key) must also stale the row -- the per-key
    # loop above only ever checks "is every CURRENTLY-expected key present
    # and matching", never "does the recorded key SET exactly equal the
    # current expected key set", so an extra recorded key would otherwise
    # be silently ignored forever.
    extra_keys = sorted(set(recorded_hashes) - set(current_hashes))
    if extra_keys:
        reasons.append(
            f"{schema.STATUS_STALE_PROVENANCE}: sweep_provenance.json source_hashes has extra/unexpected "
            f"key(s) {extra_keys!r} not part of the current expected dependency set"
        )

    recorded_schema_version = payload.get("evaluator_schema_version")
    if recorded_schema_version != vd.EVALUATOR_SCHEMA_VERSION:
        reasons.append(
            f"{schema.STATUS_STALE_PROVENANCE}: evaluator_schema_version {recorded_schema_version!r} "
            f"!= current {vd.EVALUATOR_SCHEMA_VERSION!r}"
        )
    return reasons


def build_process_row(entry: cat.ProcessEntry, evidence_root: Path, *, strict_input_files: bool = False) -> dict[str, Any]:
    evidence_dir = _evidence_dir_for(entry, evidence_root)
    row: dict[str, Any] = {
        "process": entry.name,
        "bucket": entry.bucket,
        "harness_type": entry.harness_type,
        # High-sensitivity catalog soft flags. Hashing PROCESS_CATALOG.yaml
        # alone does not make these trustworthy -- see EVIDENCE_INDEX_SPEC.md
        # "soft flags" section. Supporting evidence (or its absence) is
        # surfaced via `reasons` below, not silently assumed.
        "catalog_soft_flags": {
            "harness_type": entry.harness_type,
            "N_seeds": entry.n_seeds,
            "M_ticks": entry.m_ticks,
            "primary_channel": entry.primary_channel,
            "closed_form_dominant": entry.closed_form_dominant,
            "primary_distance": entry.primary_distance,
            "in_scope_L2_2": True,
        },
        "evidence_dir": cat.relative_to_repo(evidence_dir),
        "reasons": [],
        "artifact_hashes": {},
    }

    # Mandatory files: the three runner authority files, every mandatory
    # sidecar the runner unconditionally writes alongside them, and the
    # sweep-launcher's own sweep_provenance.json completion sentinel (see
    # schema.py). Missing ANY of these means evidence generation itself did
    # not complete (or predates the provenance hardening) -- MISSING_EVIDENCE,
    # never inferred as compliant.
    mandatory_files = schema.REQUIRED_AUTHORITY_FILES + schema.MANDATORY_SIDECAR_FILES + (schema.SWEEP_PROVENANCE_FILE,)
    missing_authority = [name for name in mandatory_files if not (evidence_dir / name).is_file()]
    if missing_authority:
        # Deliberately does not interpolate `row["evidence_dir"]` here: that
        # field is environment-relative (live artifacts/ tree vs. the
        # tracked portable bundle -- see `schema.default_evidence_root()`)
        # and is already scrubbed out of audit/content-hash comparison for
        # exactly that reason (see `_scrub_environment_relative`). Baking
        # the same path into this reasons string would silently defeat that
        # scrubbing and make an otherwise byte-identical row compare unequal
        # purely because one invocation read from the bundle and another
        # from the live tree. `row["evidence_dir"]` remains available as its
        # own field for humans who want the concrete path.
        row["reasons"].append(
            f"{schema.STATUS_MISSING_EVIDENCE}: missing required/mandatory file(s) {missing_authority} "
            f"for process {entry.name}"
        )
        row["mechanical_verdict"] = schema.STATUS_MISSING_EVIDENCE
        row["green"] = False
        return row

    # INFORMATIONAL_ONLY_FILES (large raw per-seed/tick arrays, e.g.
    # allocator_inputs.json) are deliberately never mirrored into the
    # tracked portable bundle, never read for verdict re-derivation, and
    # never hashed anywhere (not even in sweep_provenance.json) -- no
    # verdict calculation ever consumes them, so tracking a hash for them
    # would be authority theater, not evidence. If they were hashed into
    # `artifact_hashes` here, a row generated from the live tree (where the
    # file happens to exist) would carry an extra hash entry a
    # bundle-sourced regeneration of the SAME evidence could never
    # reproduce, making the tracked index falsely non-portable even though
    # nothing about the actual evidence differs.
    #
    # `input_manifest.json` is excluded from `artifact_hashes` for a related
    # but distinct reason: `bundle_process_evidence` normalizes its
    # `inputs[*]["path"]` entries to repo-relative before mirroring into the
    # tracked bundle (so a fresh clone never has this machine's absolute
    # worktree path baked into a tracked file), so its raw bytes legitimately
    # differ between the live tree and the bundle even for byte-identical
    # underlying evidence. Its actual content (resolved_seeds/m_ticks/inputs)
    # is still read and mechanically checked below regardless of hashing.
    for fname in mandatory_files:
        if fname == "input_manifest.json":
            continue
        digest = _sha256_file(evidence_dir / fname)
        if digest is not None:
            row["artifact_hashes"][fname] = digest

    result_payload, result_err = _load_json(evidence_dir / "result.json")
    manifest_payload, manifest_err = _load_json(evidence_dir / "input_manifest.json")
    provenance_payload, provenance_err = _load_json(evidence_dir / "provenance.json")
    sweep_provenance_payload, sweep_provenance_err = _load_json(evidence_dir / schema.SWEEP_PROVENANCE_FILE)

    schema_reasons: list[str] = []
    for label, err in (
        ("result.json", result_err),
        ("input_manifest.json", manifest_err),
        ("provenance.json", provenance_err),
        (schema.SWEEP_PROVENANCE_FILE, sweep_provenance_err),
    ):
        if err:
            schema_reasons.append(f"{schema.STATUS_SCHEMA_INVALID}: {label} {err}")
    for fname in schema.MANDATORY_SIDECAR_FILES:
        _, sidecar_err = _load_json(evidence_dir / fname)
        if sidecar_err:
            schema_reasons.append(f"{schema.STATUS_SCHEMA_INVALID}: {fname} {sidecar_err}")

    if result_payload is None or manifest_payload is None or provenance_payload is None or sweep_provenance_payload is None:
        row["reasons"].extend(schema_reasons)
        row["mechanical_verdict"] = schema.STATUS_SCHEMA_INVALID
        row["green"] = False
        return row

    all_reasons: list[str] = list(schema_reasons)
    all_reasons.extend(_check_current_tree_staleness(manifest_payload, entry=entry, strict_input_files=strict_input_files))
    all_reasons.extend(_check_sweep_provenance_staleness(sweep_provenance_payload, entry, evidence_dir))

    process_verdict = vd.rederive_process(entry.name, entry, result_payload)
    all_reasons.extend(process_verdict.reasons)
    row["channel_verdicts"] = process_verdict.channel_verdicts
    # Every warning result.json records verbatim, gating or not (e.g. a
    # non-gating Translation seed-shift note) -- `rederive_process` only
    # ever *acts* on the subset that matches a hard-fail/H12-demotion
    # sentinel prefix; the full list must still be visible here so a
    # non-gating warning is never silently dropped from the tracked index.
    row["warnings"] = [str(warning) for warning in result_payload.get("warnings", ())]

    final_verdict = process_verdict.mechanical_verdict
    if all_reasons and final_verdict == schema.STATUS_PASS:
        # process_verdict itself saw no reasons, but staleness/schema checks
        # above did -- never let a row read PASS with open reasons attached.
        final_verdict = schema.STATUS_FAIL

    row["reasons"] = all_reasons
    row["mechanical_verdict"] = final_verdict
    row["green"] = final_verdict == schema.STATUS_PASS
    row["provenance_git_sha"] = provenance_payload.get("git_sha")
    row["sweep_provenance"] = {
        # Informational only -- see _check_sweep_provenance_staleness: an
        # unknown/missing git_sha here does NOT by itself change
        # `mechanical_verdict`/`green` above.
        "git_sha": sweep_provenance_payload.get("git_sha"),
        "git_dirty": sweep_provenance_payload.get("git_dirty"),
        "evaluator_schema_version": sweep_provenance_payload.get("evaluator_schema_version"),
        "completion_status": sweep_provenance_payload.get("completion_status"),
        "inputs_verified": sweep_provenance_payload.get("inputs_verified"),
    }
    return row



def build_evidence_index(
    *,
    evidence_root: Path | None = None,
    catalog_path: Path = schema.CATALOG_PATH,
    strict_input_files: bool = False,
) -> dict[str, Any]:
    if evidence_root is None:
        evidence_root = schema.default_evidence_root()
    entries = cat.in_scope_processes(catalog_path)
    rows = [
        build_process_row(entries[name], evidence_root, strict_input_files=strict_input_files) for name in sorted(entries)
    ]

    tally: dict[str, int] = {}
    for row in rows:
        tally[row["mechanical_verdict"]] = tally.get(row["mechanical_verdict"], 0) + 1

    aggregate_verdict = "GREEN" if rows and all(row["green"] for row in rows) else "NON_GREEN"

    payload: dict[str, Any] = {
        "schema_version": schema.SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog_path": cat.relative_to_repo(catalog_path),
        "catalog_sha256": cat.catalog_sha256(catalog_path),
        "evidence_root": cat.relative_to_repo(evidence_root),
        "n_in_scope": len(rows),
        "aggregate_verdict": aggregate_verdict,
        "tally": tally,
        "rows": rows,
    }
    payload["content_hash"] = content_hash(payload)
    return payload


def content_hash(payload: dict[str, Any]) -> str:
    """Deterministic content hash, excluding `generated_at`/`content_hash`
    itself, `evidence_root`, and each row's `evidence_dir`.

    Two calls to build_evidence_index() against an unchanged tree/catalog
    must produce identical content_hash values even though `generated_at`
    differs between calls. `evidence_root`/`evidence_dir` are excluded for
    the same reason: they record *where this particular invocation happened
    to read bytes from* (the live sweep-output tree vs. the tracked,
    portable bundle -- see `schema.default_evidence_root()`), not durable
    evidence identity. Since the bundle is a byte-for-byte mirror of the
    live tree's compact files, `artifact_hashes` (content-based) is already
    the true tamper-evidence anchor; hashing the ambient read-location on
    top of that would make the same underlying evidence produce a different
    content_hash purely depending on which machine/clone regenerated it,
    which is exactly the false-mismatch this exclusion prevents.
    """
    scrubbed = _scrub_environment_relative(payload)
    scrubbed.pop("generated_at", None)
    scrubbed.pop("content_hash", None)
    canonical = json.dumps(scrubbed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scrub_environment_relative(payload: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy `payload` with `evidence_root` (top level) and every row's
    `evidence_dir` removed. See `content_hash()` docstring for why."""
    scrubbed = copy.deepcopy(payload)
    scrubbed.pop("evidence_root", None)
    for row in scrubbed.get("rows", ()):
        row.pop("evidence_dir", None)
    return scrubbed


def write_index(payload: dict[str, Any], path: Path = schema.INDEX_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class AuditResult:
    ok: bool
    aggregate_verdict: str
    tally: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def _strip_volatile(payload: dict[str, Any]) -> dict[str, Any]:
    scrubbed = _scrub_environment_relative(payload)
    scrubbed.pop("generated_at", None)
    scrubbed.pop("content_hash", None)
    return scrubbed


def audit(
    *,
    index_path: Path = schema.INDEX_PATH,
    evidence_root: Path | None = None,
    catalog_path: Path = schema.CATALOG_PATH,
    strict_input_files: bool = False,
) -> AuditResult:
    """Integrity check: does the tracked index match a fresh regeneration?

    This is the sole tamper/staleness defense: rather than trusting the
    stored index's own internal fields, `audit` rebuilds the index from
    scratch (mechanically re-deriving every verdict from raw evidence, per
    `verdict.rederive_process`) and diffs it against what's tracked on disk.
    Any hand-edit, stale commit, missing/extra row, or forged content_hash
    shows up as a mismatch here -- integrity can PASS even when the
    aggregate verdict is NON_GREEN (that's the honest, expected state before
    process closure); integrity FAILS only when the tracked file has drifted
    from the truth.

    `evidence_root=None` (the default) resolves via
    `schema.default_evidence_root()`: the live sweep-output tree if present
    locally, otherwise the tracked, portable evidence bundle -- so this
    succeeds in a fresh clone that has never run the sweep, not just on a
    machine that has.

    `strict_input_files=False` (the default, and the ONLY mode the tracked
    `evidence_index.json` is ever generated/committed with) never requires
    the raw, gitignored Karr-oracle `.mat` files to be physically present --
    a fresh clone that never mounted/populated them still gets an honest
    audit result (see `_check_current_tree_staleness`). Pass
    `strict_input_files=True` (the CLI's `--verify-input-files`) as an
    opt-in DIAGNOSTIC to additionally rehash oracle-data inputs for real
    when the data IS mounted locally -- this is never used for the tracked
    index itself, since it would make the same evidence produce a different
    result depending purely on whether raw data happens to be mounted on
    the machine that ran it.
    """
    problems: list[str] = []
    if not index_path.is_file():
        return AuditResult(ok=False, aggregate_verdict="NON_GREEN", problems=[f"{index_path} does not exist; run `generate` first"])

    try:
        stored = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return AuditResult(ok=False, aggregate_verdict="NON_GREEN", problems=[f"stored index is not valid JSON: {exc}"])

    fresh = build_evidence_index(evidence_root=evidence_root, catalog_path=catalog_path, strict_input_files=strict_input_files)

    # Always validate the stored content_hash against the stored payload,
    # regardless of whether `_strip_volatile(stored) != _strip_volatile(fresh)`
    # below fires. This must never be nested inside that branch: a payload
    # hand-tampered ONLY in a way `_strip_volatile` doesn't compare (e.g. the
    # `content_hash` field itself, in isolation) would otherwise pass through
    # this check entirely uncaught whenever the rest of the stored payload
    # happens to still equal a fresh regeneration.
    recorded_hash = stored.get("content_hash")
    if recorded_hash != content_hash(stored):
        problems.append("stored content_hash does not match the stored payload (index was edited after hashing)")

    if _strip_volatile(stored) != _strip_volatile(fresh):
        problems.append(
            "stored evidence_index.json does not match a fresh regeneration from the current catalog + "
            "evidence tree (hand-edited, stale, or tampered). Run `generate` and commit the refreshed index."
        )
        stored_processes = {row.get("process") for row in stored.get("rows", ())}
        fresh_processes = {row["process"] for row in fresh["rows"]}
        if stored_processes != fresh_processes:
            problems.append(
                f"row-set mismatch: stored has extra {sorted(stored_processes - fresh_processes)}, "
                f"missing {sorted(fresh_processes - stored_processes)}"
            )

    return AuditResult(
        ok=not problems,
        aggregate_verdict=fresh["aggregate_verdict"],
        tally=fresh["tally"],
        problems=problems,
    )


def _normalize_input_manifest_paths(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an `input_manifest.json` payload with every
    `inputs[*]["path"]` rewritten to a repo-relative POSIX path.

    The runner (off-limits to modify) always records absolute paths rooted
    in whatever worktree produced the evidence. Bundling those bytes
    verbatim would bake this machine's absolute worktree path into a
    tracked file, which both leaks local filesystem layout and breaks in a
    fresh clone at a different location. Paths that cannot be resolved
    under the current `cat.REPO_ROOT` (or that already live outside it) are
    left untouched rather than guessed at.
    """
    normalized = copy.deepcopy(payload)
    for record in normalized.get("inputs", ()):
        path_str = record.get("path")
        if not path_str:
            continue
        resolved = _resolve_input_path(str(path_str))
        try:
            record["path"] = resolved.relative_to(cat.REPO_ROOT).as_posix()
        except ValueError:
            continue  # not under REPO_ROOT (or unresolved) -- leave as recorded
    return normalized


def bundle_process_evidence(
    *,
    source_root: Path | None = None,
    bundle_root: Path = schema.BUNDLE_ROOT,
    catalog_path: Path = schema.CATALOG_PATH,
) -> dict[str, list[str]]:
    """Mirror compact per-process authority + sidecar files into the tracked,
    portable BUNDLE_ROOT, deliberately excluding `schema.BUNDLE_EXCLUDE_FILES`
    (large raw per-seed/tick arrays that stay local-only under the gitignored
    live `artifacts/` tree).

    Every mandatory file is copied byte-for-byte EXCEPT `input_manifest.json`,
    whose `inputs[*]["path"]` entries are normalized to repo-relative POSIX
    paths first (see `_normalize_input_manifest_paths`) so the tracked bundle
    never embeds an absolute worktree path. `artifact_hashes` in a generated
    row therefore also excludes `input_manifest.json` (see `build_process_row`)
    so this legitimate byte-level rewrite can never look like tampering.
    All other files -- including the new `sweep_provenance.json` sentinel --
    are copied verbatim, so their hashes match the live tree exactly. Never
    touches `source_root`. A process with no evidence yet under `source_root`
    is simply skipped (its existing bundle entry, if any, is left alone --
    this never silently deletes a previously-committed bundle for a process
    that happens to be unavailable in the *current* source tree).
    """
    if source_root is None:
        source_root = schema.EVIDENCE_ROOT
    entries = cat.in_scope_processes(catalog_path)
    wanted_files = [
        name for name in (schema.REQUIRED_AUTHORITY_FILES + schema.OPTIONAL_SIDECAR_FILES + (schema.SWEEP_PROVENANCE_FILE,))
        if name not in schema.BUNDLE_EXCLUDE_FILES
    ]
    copied: dict[str, list[str]] = {}
    for name in sorted(entries):
        entry = entries[name]
        subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
        src_dir = source_root / name / subdir
        if not src_dir.is_dir():
            continue
        dst_dir = bundle_root / name / subdir
        dst_dir.mkdir(parents=True, exist_ok=True)
        copied_files: list[str] = []
        for fname in wanted_files:
            src_file = src_dir / fname
            if not src_file.is_file():
                continue
            if fname == "input_manifest.json":
                payload, err = _load_json(src_file)
                if payload is None:
                    continue  # unreadable -- generator will report this via schema_reasons
                normalized = _normalize_input_manifest_paths(payload)
                (dst_dir / fname).write_text(
                    json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            else:
                (dst_dir / fname).write_bytes(src_file.read_bytes())
            copied_files.append(fname)
        copied[name] = copied_files
    return copied


def _cmd_generate(args: argparse.Namespace) -> int:
    evidence_root = Path(args.evidence_root) if args.evidence_root else None
    payload = build_evidence_index(
        evidence_root=evidence_root, catalog_path=Path(args.catalog), strict_input_files=args.verify_input_files
    )
    out_path = Path(args.out)
    write_index(payload, out_path)
    print(f"wrote {out_path} ({payload['n_in_scope']} rows, aggregate={payload['aggregate_verdict']})")
    print(f"  evidence_root: {payload['evidence_root']}")
    for status, count in sorted(payload["tally"].items()):
        print(f"  {status}: {count}")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    evidence_root = Path(args.evidence_root) if args.evidence_root else None
    result = audit(
        index_path=Path(args.index),
        evidence_root=evidence_root,
        catalog_path=Path(args.catalog),
        strict_input_files=args.verify_input_files,
    )
    print(f"integrity: {'OK' if result.ok else 'FAIL'}")
    print(f"aggregate_verdict (mechanically re-derived): {result.aggregate_verdict}")
    for status, count in sorted(result.tally.items()):
        print(f"  {status}: {count}")
    for problem in result.problems:
        print(f"PROBLEM: {problem}")

    if not result.ok:
        return 1
    if args.require_all_pass and result.aggregate_verdict != "GREEN":
        print("--require-all-pass: aggregate verdict is not GREEN; this is the acceptance gate, not yet activated in CI")
        return 2
    return 0


def _cmd_bundle(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root) if args.source_root else None
    bundle_root = Path(args.bundle_root)
    copied = bundle_process_evidence(source_root=source_root, bundle_root=bundle_root, catalog_path=Path(args.catalog))
    n_files = sum(len(files) for files in copied.values())
    print(f"bundled {len(copied)} process dir(s), {n_files} file(s) into {bundle_root}")
    for name in sorted(copied):
        print(f"  {name}: {copied[name]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Regenerate evidence_index.json from the catalog + evidence tree.")
    gen.add_argument("--out", default=str(schema.INDEX_PATH))
    gen.add_argument(
        "--evidence-root",
        default=None,
        help="Default: live artifacts/l2_2_gates if present locally, else the tracked evidence_bundle/.",
    )
    gen.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    gen.add_argument(
        "--verify-input-files",
        action="store_true",
        help="Diagnostic only, never used for the tracked index: also rehash raw oracle-data "
        "input_manifest.json inputs against the current tree (requires the data to be mounted "
        "locally). Default: trust the sweep-time inputs_verified attestation instead.",
    )
    gen.set_defaults(func=_cmd_generate)

    aud = sub.add_parser("audit", help="Verify the tracked evidence_index.json is truthful and untampered.")
    aud.add_argument("--index", default=str(schema.INDEX_PATH))
    aud.add_argument(
        "--evidence-root",
        default=None,
        help="Default: live artifacts/l2_2_gates if present locally, else the tracked evidence_bundle/.",
    )
    aud.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    aud.add_argument(
        "--require-all-pass",
        action="store_true",
        help="Acceptance gate: exit nonzero unless every in-scope process is GREEN. "
        "Expected to fail (exit 2) until process closure; not yet wired into CI.",
    )
    aud.add_argument(
        "--verify-input-files",
        action="store_true",
        help="Strict mode: also rehash raw oracle-data input_manifest.json inputs against the "
        "current tree (only succeeds if the gitignored oracle .mat data happens to be mounted "
        "locally). Default (off): portable -- trusts the sweep-time inputs_verified attestation, "
        "never requires raw oracle data to be present, e.g. in a fresh clone.",
    )
    aud.set_defaults(func=_cmd_audit)

    bun = sub.add_parser(
        "bundle",
        help="Mirror compact per-process authority/sidecar files from the live sweep-output tree into the "
        "tracked, portable evidence_bundle/ (excludes large raw-array sidecars).",
    )
    bun.add_argument("--source-root", default=None, help="Default: live artifacts/l2_2_gates.")
    bun.add_argument("--bundle-root", default=str(schema.BUNDLE_ROOT))
    bun.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    bun.set_defaults(func=_cmd_bundle)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
