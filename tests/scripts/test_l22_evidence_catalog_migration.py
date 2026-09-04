"""Anti-tamper / correctness tests for
`scripts/l22_evidence/migrate_catalog_provenance.py` -- the one-shot tool
that migrates tracked `sweep_provenance.json` sentinels from the old
whole-file `"catalog"`/`"l2_event_registry"` keys to the new per-process
`"catalog_entry"`/`"event_registry_entry"` keys (R6 catalog-provenance
fix).

Every test here builds a SYNTHETIC, throwaway git repository under
`tmp_path` (never the real opencell repo) with its own tiny
`PROCESS_CATALOG.yaml`/`event_registry.yaml` and two commits (a "pre-ref"
state and a "current" state), plus a synthetic evidence bundle -- so these
tests exercise the REAL git-plumbing code path (`git show <ref>:<path>`,
including the worktree-gitdir resolution reused from `populate.py`)
without ever touching the real tracked catalog/registry/bundle.

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_catalog_migration.py -v`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import migrate_catalog_provenance as mig  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import sweep  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402

_CATALOG_V1 = """
universals:
  N_seeds: 50
buckets:
  ALGORITHMIC_DEEP:
    in_scope_L2_2: true
    harness_type: design_a_per_tick
  EVENT_CLASS:
    in_scope_L2_2: true
    harness_type: event_class
processes:
  - name: ProcA
    oc_module: ""
    bucket: ALGORITHMIC_DEEP
    in_scope_L2_2: true
    M_ticks: 100
    N_seeds: 50
    primary_channel: substrates
    output_channels: [substrates]
  - name: ProcB
    oc_module: ""
    bucket: ALGORITHMIC_DEEP
    in_scope_L2_2: true
    M_ticks: 100
    N_seeds: 50
    primary_channel: substrates
    output_channels: [substrates]
  - name: ProcEvent
    oc_module: ""
    bucket: EVENT_CLASS
    harness_type: event_class
    in_scope_L2_2: true
    M_ticks: 4000
    N_seeds: 50
    primary_channel: substrates
    event_channels: [chromosome]
    output_channels: [substrates, chromosome]
"""

_REGISTRY_V1 = """
schema_version: 1
processes:
  - process: ProcEvent
    in_scope_v4: true
    adapter_id: proc_event.gate.v1
    adapter_status: gating_ready
    event_timing_model: single_firing
    magnitude_gateable: false
    required_n_seeds: 50
    notes: "v1"
"""


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "-q"], cwd=repo_root)
    _run_git(["config", "user.email", "test@example.com"], cwd=repo_root)
    _run_git(["config", "user.name", "Test"], cwd=repo_root)
    _run_git(["config", "core.autocrlf", "false"], cwd=repo_root)


def _commit_all(repo_root: Path, message: str) -> str:
    _run_git(["add", "-A"], cwd=repo_root)
    _run_git(["commit", "-q", "-m", message], cwd=repo_root)
    return _run_git(["rev-parse", "HEAD"], cwd=repo_root).stdout.strip()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_mandatory_sidecars(evidence_dir: Path) -> None:
    _write_json(evidence_dir / "thresholds.json", {"channels": {}})
    _write_json(evidence_dir / "null_calibration.json", {"channels": {}})
    _write_json(evidence_dir / "SUMMARY.json", {"note": "fixture"})
    _write_json(evidence_dir / "analytical_check.json", {"applicable": False, "reason": "fixture"})


def _sha256_file(path: Path) -> str:
    digest = sweep._sha256_file(path)
    assert digest is not None
    return digest


def _real_input_record() -> dict:
    rel = "tests/vivarium/l2_2_design_a_runner.py"
    return {"path": rel, "sha256": sweep._sha256_file(schema.REPO_ROOT / rel)}


def _write_evidence_dir(
    bundle_root: Path,
    process: str,
    *,
    m_ticks: int,
    n_seeds: int,
    harness_type: str,
    catalog_hash: str,
    registry_hash: str | None = None,
    tamper_sidecar_after: bool = False,
    tamper_oc_module_hash: bool = False,
    mismatched_process_field: str | None = None,
) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    evidence_dir = bundle_root / process / subdir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    seeds = list(range(n_seeds))
    _write_json(
        evidence_dir / "result.json",
        {"process": process, "verdict": "PASS", "seeds": seeds, "ticks": m_ticks, "channels": {}, "warnings": []},
    )
    _write_json(
        evidence_dir / "input_manifest.json",
        {"resolved_seeds": seeds, "m_ticks": m_ticks, "inputs": [_real_input_record()]},
    )
    _write_json(evidence_dir / "provenance.json", {"generated_at": "2026-01-01T00:00:00+00:00", "git_sha": "deadbeef"})
    _write_mandatory_sidecars(evidence_dir)

    sidecar_hashes = {
        fname: _sha256_file(evidence_dir / fname) for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES if (evidence_dir / fname).is_file()
    }

    source_hashes = dict(sweep.current_source_hashes(None, process=None, harness_type=harness_type))
    # `current_source_hashes` (fixed) no longer computes catalog/registry
    # keys at all when `process=None` -- add the OLD-STYLE whole-file
    # key(s) explicitly, simulating a pre-migration sentinel.
    if tamper_oc_module_hash:
        source_hashes["oc_module"] = "0" * 64
    source_hashes["catalog"] = catalog_hash
    if harness_type == "event_class":
        assert registry_hash is not None
        source_hashes["l2_event_registry"] = registry_hash

    payload = {
        "schema_version": schema.SWEEP_PROVENANCE_SCHEMA_VERSION,
        "process": mismatched_process_field or process,
        "n_seeds": n_seeds,
        "m_ticks": m_ticks,
        "completion_status": schema.COMPLETION_STATUS_COMPLETE,
        "git_sha": "deadbeef",
        "git_dirty": False,
        "source_hashes": source_hashes,
        "sidecar_hashes": sidecar_hashes,
        "inputs_verified": True,
        "evaluator_schema_version": vd.EVALUATOR_SCHEMA_VERSION,
        "result_schema_version": schema.RESULT_SCHEMA_VERSION,
    }
    _write_json(evidence_dir / schema.SWEEP_PROVENANCE_FILE, payload)

    if tamper_sidecar_after:
        (evidence_dir / "thresholds.json").write_text(json.dumps({"channels": {"tampered": True}}), encoding="utf-8")

    return evidence_dir


@pytest.fixture
def repo_with_catalog(tmp_path):
    """A throwaway git repo with two commits: `pre_ref` (v1 catalog) and
    HEAD (Cytokinesis-analog `ProcEvent` M_ticks bumped 4000 -> 5000).
    Returns (repo_root, pre_ref, catalog_path, registry_path)."""
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    catalog_path = repo_root / "PROCESS_CATALOG.yaml"
    registry_path = repo_root / "event_registry.yaml"
    catalog_path.write_text(textwrap.dedent(_CATALOG_V1), encoding="utf-8")
    registry_path.write_text(textwrap.dedent(_REGISTRY_V1), encoding="utf-8")
    pre_ref = _commit_all(repo_root, "v1")

    edited = _CATALOG_V1.replace("M_ticks: 4000", "M_ticks: 5000")
    assert edited != _CATALOG_V1
    catalog_path.write_text(textwrap.dedent(edited), encoding="utf-8")
    _commit_all(repo_root, "v2: bump ProcEvent M_ticks")

    return repo_root, pre_ref, catalog_path, registry_path


def _pre_ref_hashes(repo_root: Path, pre_ref: str, catalog_path: Path, registry_path: Path) -> tuple[str, str]:
    catalog_text = mig.git_show_text(pre_ref, "PROCESS_CATALOG.yaml", repo_root=repo_root)
    registry_text = mig.git_show_text(pre_ref, "event_registry.yaml", repo_root=repo_root)
    return mig._sha256_text(catalog_text), mig._sha256_text(registry_text)


# --- Happy path: eligible rows migrate, ineligible rows are refused ------------


def test_plan_migrates_unrelated_rows_and_refuses_the_changed_one(tmp_path, repo_with_catalog):
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, pre_registry_hash = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)

    bundle_root = tmp_path / "bundle"
    _write_evidence_dir(bundle_root, "ProcA", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick", catalog_hash=pre_catalog_hash)
    _write_evidence_dir(bundle_root, "ProcB", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick", catalog_hash=pre_catalog_hash)
    # ProcEvent's OWN M_ticks changed between pre_ref and HEAD (4000->5000,
    # the Cytokinesis-analog case) -- its recorded catalog hash still
    # matches pre_ref (this row genuinely WAS generated then), but its
    # resolved contract now differs from the current tree.
    _write_evidence_dir(
        bundle_root, "ProcEvent", m_ticks=4000, n_seeds=50, harness_type="event_class",
        catalog_hash=pre_catalog_hash, registry_hash=pre_registry_hash,
    )

    plans = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)

    assert plans["ProcA"].status == mig.STATUS_WOULD_MIGRATE
    assert plans["ProcB"].status == mig.STATUS_WOULD_MIGRATE
    assert plans["ProcEvent"].status == mig.STATUS_CONTRACT_CHANGED

    applied = mig.apply_plan(plans)
    assert applied["ProcA"].status == mig.STATUS_MIGRATED
    assert applied["ProcB"].status == mig.STATUS_MIGRATED
    assert applied["ProcEvent"].status == mig.STATUS_CONTRACT_CHANGED  # untouched

    # ProcA/ProcB's sweep_provenance.json now carries catalog_entry, never
    # the old whole-file "catalog" key; ProcEvent's is completely untouched.
    proc_a_payload = json.loads((bundle_root / "ProcA" / "latest" / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert "catalog_entry" in proc_a_payload["source_hashes"]
    assert "catalog" not in proc_a_payload["source_hashes"]

    proc_event_payload = json.loads((bundle_root / "ProcEvent" / "latest_event" / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert "catalog" in proc_event_payload["source_hashes"]
    assert "catalog_entry" not in proc_event_payload["source_hashes"]

    # Never rewrites result.json/thresholds.json/etc -- only sweep_provenance.json.
    result_before = json.loads((bundle_root / "ProcA" / "latest" / "result.json").read_text(encoding="utf-8"))
    assert result_before["process"] == "ProcA"


def test_apply_never_touches_result_json_or_other_authority_files(tmp_path, repo_with_catalog):
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, _ = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)
    bundle_root = tmp_path / "bundle"
    evidence_dir = _write_evidence_dir(bundle_root, "ProcA", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick", catalog_hash=pre_catalog_hash)

    other_files = {
        fname: (evidence_dir / fname).read_bytes()
        for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES
        if fname != schema.SWEEP_PROVENANCE_FILE
    }

    plans = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    mig.apply_plan(plans)

    for fname, before_bytes in other_files.items():
        assert (evidence_dir / fname).read_bytes() == before_bytes, f"{fname} bytes changed -- migration must never touch authority/sidecar files"


# --- Idempotency / resumability --------------------------------------------------


def test_migration_is_idempotent(tmp_path, repo_with_catalog):
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, _ = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)
    bundle_root = tmp_path / "bundle"
    _write_evidence_dir(bundle_root, "ProcA", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick", catalog_hash=pre_catalog_hash)

    plans1 = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    applied1 = mig.apply_plan(plans1)
    assert applied1["ProcA"].status == mig.STATUS_MIGRATED

    payload_after_first = json.loads((bundle_root / "ProcA" / "latest" / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))

    plans2 = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    assert plans2["ProcA"].status == mig.STATUS_ALREADY_MIGRATED
    applied2 = mig.apply_plan(plans2)
    assert applied2["ProcA"].status == mig.STATUS_ALREADY_MIGRATED

    payload_after_second = json.loads((bundle_root / "ProcA" / "latest" / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert payload_after_second == payload_after_first


def test_atomic_write_uses_temp_file_and_os_replace(tmp_path, repo_with_catalog, monkeypatch):
    """A crash between the temp-file write and `os.replace` must never
    leave the ORIGINAL file corrupted -- verified by making `os.replace`
    raise and confirming the original sweep_provenance.json is untouched
    while a `.json.tmp` sibling exists (the resumable recovery artifact)."""
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, _ = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)
    bundle_root = tmp_path / "bundle"
    _write_evidence_dir(bundle_root, "ProcA", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick", catalog_hash=pre_catalog_hash)
    prov_path = bundle_root / "ProcA" / "latest" / schema.SWEEP_PROVENANCE_FILE
    original_bytes = prov_path.read_bytes()

    plans = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)

    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash between temp-write and replace")

    monkeypatch.setattr(mig.os, "replace", _boom)
    with pytest.raises(OSError):
        mig.apply_plan(plans)

    # Original untouched; a recoverable temp file was left behind.
    assert prov_path.read_bytes() == original_bytes
    tmp_path_written = prov_path.with_suffix(".json.tmp")
    assert tmp_path_written.is_file()

    # A fresh run (real os.replace restored) completes the migration.
    monkeypatch.undo()
    plans2 = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    applied2 = mig.apply_plan(plans2)
    assert applied2["ProcA"].status == mig.STATUS_MIGRATED
    final_payload = json.loads(prov_path.read_text(encoding="utf-8"))
    assert "catalog_entry" in final_payload["source_hashes"]


# --- Anti-tamper: refusal reasons ------------------------------------------------


def test_wrong_pre_ref_refuses_every_row(tmp_path, repo_with_catalog):
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, _ = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)
    bundle_root = tmp_path / "bundle"
    _write_evidence_dir(bundle_root, "ProcA", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick", catalog_hash=pre_catalog_hash)

    # HEAD itself is a real, resolvable, but WRONG ref (its catalog hash
    # differs from what was recorded at pre_ref).
    plans = mig.plan_migration(pre_ref="HEAD", bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    assert plans["ProcA"].status == mig.STATUS_PRE_REF_CATALOG_MISMATCH

    payload = json.loads((bundle_root / "ProcA" / "latest" / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert "catalog" in payload["source_hashes"]  # untouched


def test_nonexistent_pre_ref_raises_migration_error(tmp_path, repo_with_catalog):
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    bundle_root = tmp_path / "bundle"
    with pytest.raises(mig.MigrationError):
        mig.plan_migration(pre_ref="not-a-real-ref-at-all", bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)


def test_non_catalog_source_drift_refuses_migration(tmp_path, repo_with_catalog):
    """A recorded `oc_module`-equivalent source hash that no longer
    matches the current tree (simulated here by tampering a recorded
    source hash directly) must refuse migration, even though the catalog
    hash itself matches --pre-ref."""
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, _ = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)
    bundle_root = tmp_path / "bundle"
    _write_evidence_dir(
        bundle_root, "ProcA", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick",
        catalog_hash=pre_catalog_hash, tamper_oc_module_hash=True,
    )

    plans = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    assert plans["ProcA"].status == mig.STATUS_NON_CATALOG_SOURCE_DRIFT


def test_sidecar_mutation_after_generation_refuses_migration(tmp_path, repo_with_catalog):
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, _ = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)
    bundle_root = tmp_path / "bundle"
    _write_evidence_dir(
        bundle_root, "ProcA", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick",
        catalog_hash=pre_catalog_hash, tamper_sidecar_after=True,
    )

    plans = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    assert plans["ProcA"].status == mig.STATUS_SIDECAR_DRIFT


def test_event_class_registry_pre_ref_mismatch_refuses_migration(tmp_path, repo_with_catalog):
    """An event_class row whose recorded `l2_event_registry` hash does not
    match --pre-ref's registry state must be refused, even if its catalog
    hash matches -- proves the registry check is independent of the
    catalog check."""
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, _ = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)
    bundle_root = tmp_path / "bundle"
    _write_evidence_dir(
        bundle_root, "ProcEvent", m_ticks=4000, n_seeds=50, harness_type="event_class",
        catalog_hash=pre_catalog_hash, registry_hash="0" * 64,
    )

    plans = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    assert plans["ProcEvent"].status == mig.STATUS_PRE_REF_REGISTRY_MISMATCH


def test_harness_process_field_mismatch_refuses_migration(tmp_path, repo_with_catalog):
    """A sentinel copied from a different process's evidence directory
    (its `process` field no longer matches the directory it sits in) must
    be refused, never migrated onto the wrong row."""
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    pre_catalog_hash, _ = _pre_ref_hashes(repo_root, pre_ref, catalog_path, registry_path)
    bundle_root = tmp_path / "bundle"
    _write_evidence_dir(
        bundle_root, "ProcA", m_ticks=100, n_seeds=50, harness_type="design_a_per_tick",
        catalog_hash=pre_catalog_hash, mismatched_process_field="ProcB",
    )

    plans = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    assert plans["ProcA"].status == mig.STATUS_HARNESS_MISMATCH


def test_missing_evidence_reports_no_evidence(tmp_path, repo_with_catalog):
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    bundle_root = tmp_path / "bundle"  # never populated
    plans = mig.plan_migration(pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root)
    assert plans["ProcA"].status == mig.STATUS_NO_EVIDENCE
    assert plans["ProcB"].status == mig.STATUS_NO_EVIDENCE
    assert plans["ProcEvent"].status == mig.STATUS_NO_EVIDENCE


def test_unknown_process_filter_raises(tmp_path, repo_with_catalog):
    repo_root, pre_ref, catalog_path, registry_path = repo_with_catalog
    bundle_root = tmp_path / "bundle"
    with pytest.raises(mig.MigrationError, match="unknown"):
        mig.plan_migration(
            pre_ref=pre_ref, bundle_root=bundle_root, catalog_path=catalog_path, registry_path=registry_path,
            repo_root=repo_root, processes=["NotAProcess"],
        )
