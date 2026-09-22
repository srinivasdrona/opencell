from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import pre_l25_honesty as honesty


def _write_yaml(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _build_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    catalog = {
        "processes": [
            {
                "name": "DeterministicProc",
                "oc_module": "opencell/vivarium/deterministic.py",
                "in_scope_L2_2": False,
            },
            {
                "name": "StochasticProc",
                "oc_module": "opencell/vivarium/stochastic.py",
                "in_scope_L2_2": True,
            },
        ]
    }
    _write_yaml(
        root / "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
        catalog,
    )
    evidence_index = {
        "rows": [
            {
                "process": "StochasticProc",
                "mechanical_verdict": "PASS",
            }
        ]
    }
    evidence_path = root / "docs/phase_f/l2_2_design_a/evidence_index.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence_index), encoding="utf-8")
    _write_yaml(
        root / "data/karr_method_inventory/oc_method_map.yaml",
        {
            "processes": {
                "DeterministicProc": {
                    "oc_files": ["opencell/vivarium/deterministic.py"]
                },
                "StochasticProc": {
                    "oc_files": ["opencell/vivarium/stochastic.py"]
                },
            }
        },
    )
    _write_yaml(root / "data/schemas/per_process_wiring/_schema.yaml", {"type": "object"})
    for name, module in (
        ("DeterministicProc", "deterministic.py"),
        ("StochasticProc", "stochastic.py"),
    ):
        _write_yaml(
            root / f"data/schemas/per_process_wiring/{name}.yaml",
            {"process": {"name": name}},
        )
        _write_yaml(
            root / f"data/schemas/per_process/{name.lower()}.toml",
            {"name": name},
        )
        audit = root / f"docs/phase_f/audits/{name}_semantic_audit.md"
        audit.parent.mkdir(parents=True, exist_ok=True)
        audit.write_text(f"# {name}\nverified\n", encoding="utf-8")
        oc_path = root / "opencell/vivarium" / module
        oc_path.parent.mkdir(parents=True, exist_ok=True)
        oc_path.write_text(f'class {name}:\n    pass\n', encoding="utf-8")

    digest, count = honesty.compute_source_digest(root)
    baseline = {
        "schema_version": "1.0",
        "canonical_process_count": 2,
        "source_tree": {"sha256": digest, "file_count": count},
        "processes": [
            {
                "name": "DeterministicProc",
                "behavior_gate": "L2.1",
                "behavior_verdict": "GENUINE",
                "eligibility": "ELIGIBLE",
                "findings": [
                    {
                        "id": "DET-SHAPE",
                        "kind": "IMPLEMENTATION_SHAPE_DIFFERENCE",
                        "disposition": "ACCEPTED_EQUIVALENT",
                        "summary": "Equivalent implementation shape.",
                        "evidence": [
                            {
                                "path": "opencell/vivarium/deterministic.py",
                                "lines": "1-2",
                            }
                        ],
                    }
                ],
            },
            {
                "name": "StochasticProc",
                "behavior_gate": "L2.2",
                "behavior_verdict": "PASS",
                "eligibility": "BLOCKED_CODE_DEVIATION",
                "findings": [
                    {
                        "id": "STOCH-GAP",
                        "kind": "CODE_DEVIATION",
                        "disposition": "OPEN",
                        "summary": "Synthetic open gap.",
                        "evidence": [
                            {
                                "path": "opencell/vivarium/stochastic.py",
                                "lines": "1-2",
                            }
                        ],
                    }
                ],
            },
        ],
        "summary": {"eligible": 1, "blocked": 1},
    }
    baseline_path = root / "baseline.yaml"
    _write_yaml(baseline_path, baseline)
    return root, baseline_path


def test_valid_baseline_derives_blocked_process(tmp_path: Path) -> None:
    root, baseline_path = _build_root(tmp_path)
    result = honesty.audit_baseline(
        baseline_path,
        root=root,
        expected_process_count=None,
    )
    assert result.integrity_ok
    assert not result.all_eligible
    assert result.eligible_count == 1
    assert result.blocked_count == 1
    assert any("StochasticProc/STOCH-GAP" in blocker for blocker in result.blockers)


def test_open_blocker_cannot_be_marked_eligible(tmp_path: Path) -> None:
    root, baseline_path = _build_root(tmp_path)
    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    baseline["processes"][1]["eligibility"] = "ELIGIBLE"
    baseline["summary"] = {"eligible": 2, "blocked": 0}
    _write_yaml(baseline_path, baseline)

    result = honesty.audit_baseline(
        baseline_path,
        root=root,
        expected_process_count=None,
    )
    assert not result.integrity_ok
    assert any("derived='BLOCKED_CODE_DEVIATION'" in problem for problem in result.problems)


def test_source_change_invalidates_baseline(tmp_path: Path) -> None:
    root, baseline_path = _build_root(tmp_path)
    target = root / "opencell/vivarium/stochastic.py"
    target.write_text("class StochasticProc:\n    value = 1\n", encoding="utf-8")

    result = honesty.audit_baseline(
        baseline_path,
        root=root,
        expected_process_count=None,
    )
    assert not result.integrity_ok
    assert any("source_tree.sha256 is stale" in problem for problem in result.problems)


def test_l2_2_verdict_drift_invalidates_baseline(tmp_path: Path) -> None:
    root, baseline_path = _build_root(tmp_path)
    evidence_path = root / "docs/phase_f/l2_2_design_a/evidence_index.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["rows"][0]["mechanical_verdict"] = "FAIL"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    digest, count = honesty.compute_source_digest(root)
    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    baseline["source_tree"] = {"sha256": digest, "file_count": count}
    _write_yaml(baseline_path, baseline)

    result = honesty.audit_baseline(
        baseline_path,
        root=root,
        expected_process_count=None,
    )
    assert not result.integrity_ok
    assert any("L2.2 evidence='FAIL'" in problem for problem in result.problems)
    assert any("derived='BLOCKED_LOWER_GATE'" in problem for problem in result.problems)
    assert any("L2.2 verdict is FAIL" in blocker for blocker in result.blockers)


def test_missing_process_entry_fails_registry_integrity(tmp_path: Path) -> None:
    root, baseline_path = _build_root(tmp_path)
    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    baseline["processes"] = baseline["processes"][:1]
    baseline["summary"] = {"eligible": 1, "blocked": 1}
    _write_yaml(baseline_path, baseline)

    result = honesty.audit_baseline(
        baseline_path,
        root=root,
        expected_process_count=None,
    )
    assert not result.integrity_ok
    assert any("process registry mismatch" in problem for problem in result.problems)


def test_out_of_range_evidence_line_fails(tmp_path: Path) -> None:
    root, baseline_path = _build_root(tmp_path)
    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    baseline["processes"][0]["findings"][0]["evidence"][0]["lines"] = "1-99"
    _write_yaml(baseline_path, baseline)

    result = honesty.audit_baseline(
        baseline_path,
        root=root,
        expected_process_count=None,
    )
    assert not result.integrity_ok
    assert any("outside 1-2" in problem for problem in result.problems)


def test_open_nonblocking_kind_is_rejected(tmp_path: Path) -> None:
    root, baseline_path = _build_root(tmp_path)
    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    finding = baseline["processes"][0]["findings"][0]
    finding["disposition"] = "OPEN"
    _write_yaml(baseline_path, baseline)

    result = honesty.audit_baseline(
        baseline_path,
        root=root,
        expected_process_count=None,
    )
    assert not result.integrity_ok
    assert any("invalid for nonblocking kind" in problem for problem in result.problems)


def test_tracked_baseline_is_current_and_fail_closed() -> None:
    result = honesty.audit_baseline()
    assert result.integrity_ok
    assert result.process_count == 28
    assert result.eligible_count == 3
    assert result.blocked_count == 25
    assert not result.all_eligible
    assert any("Metabolism/MET-CODE-DEVIATIONS" in item for item in result.blockers)
    assert any("Metabolism/MET-EVIDENCE-CONFIG" in item for item in result.blockers)
