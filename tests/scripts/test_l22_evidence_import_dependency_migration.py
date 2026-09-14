"""Anti-tamper tests for import-dependency provenance backfill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import migrate_import_dependency_provenance as mig  # noqa: E402
from scripts.l22_evidence import schema, sweep  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "core.autocrlf", "false")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    digest = sweep._sha256_file(path)
    assert digest is not None
    return digest


def _write_replication_evidence(bundle_root: Path, source_ref: str) -> Path:
    entry = cat.in_scope_processes()["Replication"]
    evidence_dir = bundle_root / entry.name / schema.DESIGN_A_SUBDIR
    evidence_dir.mkdir(parents=True)
    _write_json(evidence_dir / "result.json", {"process": entry.name})
    _write_json(evidence_dir / "input_manifest.json", {"inputs": []})
    _write_json(evidence_dir / "provenance.json", {"git_sha": source_ref})
    _write_json(evidence_dir / "thresholds.json", {"channels": {}})
    _write_json(evidence_dir / "null_calibration.json", {"channels": {}})
    _write_json(evidence_dir / "SUMMARY.json", {"process": entry.name})
    _write_json(evidence_dir / "analytical_check.json", {"applicable": False})

    source_hashes = sweep.current_source_hashes(
        entry.oc_module,
        process=entry.name,
        harness_type=entry.harness_type,
    )
    for key in mig.NEW_DEPENDENCY_KEYS["Replication"]:
        source_hashes.pop(key)
    sidecar_hashes = {
        filename: _sha(evidence_dir / filename)
        for filename in schema.SWEEP_PROVENANCE_SIDECAR_FILES
    }
    _write_json(
        evidence_dir / schema.SWEEP_PROVENANCE_FILE,
        {
            "process": entry.name,
            "git_sha": source_ref,
            "source_hashes": source_hashes,
            "sidecar_hashes": sidecar_hashes,
        },
    )
    return evidence_dir


def _fixture(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo)
    protein_complexes = repo / "opencell" / "m1" / "protein_complexes.py"
    util_init = repo / "opencell" / "util" / "__init__.py"
    protein_complexes.parent.mkdir(parents=True)
    util_init.parent.mkdir(parents=True)
    protein_complexes.write_bytes(b"# protein complexes exact bytes\n")
    util_init.write_bytes(b"# util exact bytes\n")
    source_ref = _commit(repo, "evidence source dependencies")

    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "Replication",
        {
            **schema.PROCESS_DEPENDENCY_FILES["Replication"],
            "m1_protein_complexes_module": protein_complexes,
            "util_module": util_init,
        },
    )
    bundle = tmp_path / "bundle"
    evidence_dir = _write_replication_evidence(bundle, source_ref)
    return repo, source_ref, bundle, evidence_dir, protein_complexes, util_init


def _plan(repo: Path, source_ref: str, bundle: Path) -> mig.RowPlan:
    entry = cat.in_scope_processes()["Replication"]
    return mig.plan_row_migration(
        entry,
        source_ref=source_ref,
        dependency_keys=mig.NEW_DEPENDENCY_KEYS["Replication"],
        bundle_root=bundle,
        catalog_path=schema.CATALOG_PATH,
        registry_path=schema.L2_EVENT_REGISTRY_PATH,
        repo_root=repo,
    )


def test_exact_byte_proof_migrates_only_sweep_provenance(tmp_path, monkeypatch):
    repo, source_ref, bundle, evidence_dir, _, _ = _fixture(tmp_path, monkeypatch)
    before = {path: path.read_bytes() for path in evidence_dir.iterdir() if path.is_file()}

    plan = _plan(repo, source_ref, bundle)
    assert plan.status == mig.STATUS_WOULD_MIGRATE
    assert set(plan.proven_dependency_hashes or {}) == set(mig.NEW_DEPENDENCY_KEYS["Replication"])

    applied = mig.apply_plan({"Replication": plan})["Replication"]
    assert applied.status == mig.STATUS_MIGRATED

    after = {path: path.read_bytes() for path in evidence_dir.iterdir() if path.is_file()}
    changed = {path.name for path in before if before[path] != after[path]}
    assert changed == {schema.SWEEP_PROVENANCE_FILE}
    payload = json.loads((evidence_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    for key, digest in (plan.proven_dependency_hashes or {}).items():
        assert payload["source_hashes"][key] == digest


def test_dependency_byte_drift_refuses_without_writes(tmp_path, monkeypatch):
    repo, source_ref, bundle, evidence_dir, protein_complexes, _ = _fixture(tmp_path, monkeypatch)
    before = {path: path.read_bytes() for path in evidence_dir.iterdir() if path.is_file()}
    protein_complexes.write_bytes(b"# drift after evidence source\n")

    plan = _plan(repo, source_ref, bundle)
    assert plan.status == mig.STATUS_DEPENDENCY_DRIFT
    mig.apply_plan({"Replication": plan})
    assert {path: path.read_bytes() for path in evidence_dir.iterdir() if path.is_file()} == before


def test_dependency_missing_at_source_ref_refuses_without_writes(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo)
    protein_complexes = repo / "opencell" / "m1" / "protein_complexes.py"
    util_init = repo / "opencell" / "util" / "__init__.py"
    protein_complexes.parent.mkdir(parents=True)
    protein_complexes.write_bytes(b"# present at source\n")
    source_ref = _commit(repo, "source missing util")
    util_init.parent.mkdir(parents=True)
    util_init.write_bytes(b"# added only after source\n")

    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "Replication",
        {
            **schema.PROCESS_DEPENDENCY_FILES["Replication"],
            "m1_protein_complexes_module": protein_complexes,
            "util_module": util_init,
        },
    )
    bundle = tmp_path / "bundle"
    evidence_dir = _write_replication_evidence(bundle, source_ref)
    before = (evidence_dir / schema.SWEEP_PROVENANCE_FILE).read_bytes()

    plan = _plan(repo, source_ref, bundle)
    assert plan.status == mig.STATUS_DEPENDENCY_MISSING
    mig.apply_plan({"Replication": plan})
    assert (evidence_dir / schema.SWEEP_PROVENANCE_FILE).read_bytes() == before


def test_source_ref_must_be_bound_to_evidence(tmp_path, monkeypatch):
    repo, source_ref, bundle, evidence_dir, _, _ = _fixture(tmp_path, monkeypatch)
    (repo / "unrelated.txt").write_text("later tree\n", encoding="utf-8")
    unrelated_ref = _commit(repo, "unrelated later tree")
    payload_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["git_sha"] = unrelated_ref
    _write_json(payload_path, payload)

    plan = _plan(repo, source_ref, bundle)
    assert plan.status == mig.STATUS_SOURCE_REF_UNBOUND
